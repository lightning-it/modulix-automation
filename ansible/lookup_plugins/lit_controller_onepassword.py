"""Explicit controller-only lookup of one pinned, sealed 1Password item.

Also serves as the Linux EE launcher: JSON on stdin, public ansible-playbook
arguments after --. Neither secret contents nor subprocess output are emitted.
The desktop-side trusted transport must select the approved account and item.
"""

import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import signal
import ssl
import stat
import subprocess
import sys
import tempfile

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase
from ansible.utils.unsafe_proxy import wrap_var

LIMIT = 1048576
FD_ENV = "LIT_CONTROLLER_ONEPASSWORD_FD"
MEMORY_NAME = "lit-controller-onepassword"
PLAYBOOK = "/opt/app-root/bin/ansible-playbook"
SYSTEM_PATH = (
    "/opt/app-root/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
)
SEALS = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def decode(value):
    def reject_constant(value):
        raise ValueError("non-JSON numeric constant")

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("non-finite JSON number")
        return result

    return json.loads(
        value,
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
        parse_float=finite_float,
    )


def read_item(fd):
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 0
        or info.st_uid != os.geteuid()
        or not 0 < info.st_size <= LIMIT
        or fcntl.fcntl(fd, fcntl.F_GET_SEALS) & SEALS != SEALS
        or os.readlink(f"/proc/self/fd/{fd}") != f"/memfd:{MEMORY_NAME} (deleted)"
    ):
        raise ValueError("untrusted memory input")
    return decode(os.pread(fd, LIMIT + 1, 0))


def validate_item(item, contract):
    pins = contract["onepassword"]
    if set(pins) != {"item_id", "vault_id", "item_version", "item_title", "ca_sha256"}:
        raise ValueError("invalid pin contract")
    for key in ("item_id", "vault_id"):
        if not re.fullmatch(r"[a-z0-9]{26}", pins[key]):
            raise ValueError("invalid immutable id")
    if (
        type(pins["item_version"]) is not int
        or pins["item_version"] < 1
        or not isinstance(pins["item_title"], str)
        or not pins["item_title"]
        or not re.fullmatch(r"[0-9a-f]{64}", pins["ca_sha256"])
    ):
        raise ValueError("invalid version or CA pin")
    if (
        item["id"] != pins["item_id"]
        or item["vault"]["id"] != pins["vault_id"]
        or type(item["version"]) is not int
        or item["version"] != pins["item_version"]
        or item["title"] != pins["item_title"]
        or item["category"] != "SECURE_NOTE"
    ):
        raise ValueError("item identity drift")
    notes = [field for field in item["fields"] if field.get("id") == "notesPlain"]
    if len(notes) != 1:
        raise ValueError("ambiguous note")
    document = decode(notes[0]["value"])
    if (
        type(contract["schema_version"]) is not int
        or contract["schema_version"] != 1
        or type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or contract["auth_method"] != "approle"
        or document["auth_method"] != "approle"
        or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,127}", contract["subject"])
        or document["subject"] != contract["subject"]
        or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,127}", contract["role_name"])
        or document["role_name"] != contract["role_name"]
        or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._/-]*", contract["auth_mount_point"]
        )
        or contract["auth_mount_point"].endswith("/")
        or any(
            part in ("", ".", "..") for part in contract["auth_mount_point"].split("/")
        )
        or document["auth_mount_point"] != contract["auth_mount_point"]
    ):
        raise ValueError("AppRole identity drift")
    result = {key: document[key] for key in ("role_id", "secret_id")}
    if not all(
        isinstance(value, str) and re.fullmatch(r"[^\r\n]{16,4096}", value)
        for value in result.values()
    ):
        raise ValueError("invalid AppRole material")
    # Credential strings are data, including valid punctuation/template-looking
    # text. They must never be interpreted as a second Jinja expression.
    return wrap_var(result)


def public_ca_digest(path, project_root, expected):
    # Walk descriptors so a symlink swap cannot redirect a path component.
    if (
        not isinstance(project_root, str)
        or not project_root.startswith("/")
        or os.path.normpath(project_root) != project_root
        or not path.startswith(project_root + "/.secrets/")
        or os.path.normpath(path) != path
    ):
        raise ValueError("CA outside canonical project secrets root")
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    current = ""
    try:
        for part in path.split("/")[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
            )
            os.close(parent)
            parent = child
            current += "/" + part
            info = os.fstat(parent)
            sticky_tmp = (
                current == "/tmp"
                and info.st_uid == 0
                and stat.S_IMODE(info.st_mode) == 0o1777
            )
            if info.st_uid not in (0, os.geteuid()) or (
                info.st_mode & 0o022 and not sticky_tmp
            ):
                raise ValueError("unprotected CA parent")
        fd = os.open(
            path.rsplit("/", 1)[1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent,
        )
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid not in (0, os.geteuid())
                or stat.S_IMODE(info.st_mode) not in (0o400, 0o444, 0o600, 0o644)
                or not 0 < info.st_size <= LIMIT
            ):
                raise ValueError("unprotected CA file")
            data = os.read(fd, LIMIT + 1)
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise ValueError("CA pin mismatch")
    ssl.create_default_context(cadata=data.decode("ascii"))
    return digest


class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        try:
            if len(terms) != 1 or not re.fullmatch(
                r"[0-9]+", os.environ.get(FD_ENV, "")
            ):
                raise ValueError("missing memory descriptor")
            contract = terms[0]
            result = validate_item(read_item(int(os.environ[FD_ENV])), contract)
            result["ca_sha256"] = public_ca_digest(
                kwargs["ca_path"],
                kwargs["project_root"],
                contract["onepassword"]["ca_sha256"],
            )
            return [result]
        except Exception:
            # Neither parser exceptions nor secret input may reach callbacks.
            raise AnsibleError(
                "Pinned controller credential validation failed"
            ) from None


def validated_agent_socket(path):
    # The trusted outer transport opts in explicitly; ambient agent access is
    # never enough. This capability is for the trusted Ansible invocation, not
    # a sandbox separating mutually untrusted tasks within one playbook.
    if not isinstance(path, str) or not os.path.isabs(path):
        raise ValueError("absolute managed SSH agent socket required")
    if os.path.realpath(path) != path:
        raise ValueError("canonical managed SSH agent socket required")
    for parent in Path(path).parents:
        info = parent.lstat()
        sticky_tmp = (
            str(parent) == "/tmp"
            and info.st_uid == 0
            and stat.S_IMODE(info.st_mode) == 0o1777
        )
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in (0, os.geteuid())
            or (info.st_mode & 0o022 and not sticky_tmp)
        ):
            raise ValueError("protected SSH agent parent required")
    info = os.lstat(path)
    if (
        not stat.S_ISSOCK(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("private owner-controlled SSH agent socket required")
    return path


def child_environment(fd, runtime_dir, agent_socket=None):
    # No caller environment is inherited, including PATH and HOME/plugin search
    # locations. runtime_dir is freshly created by the trusted launcher.
    env = {
        "PATH": SYSTEM_PATH,
        "HOME": runtime_dir,
        "TMPDIR": runtime_dir,
        "LANG": "C.UTF-8",
        "ANSIBLE_LOCAL_TEMP": runtime_dir + "/ansible-tmp",
    }
    if agent_socket is not None:
        env["SSH_AUTH_SOCK"] = validated_agent_socket(agent_socket)
    env.update(
        **{FD_ENV: str(fd)},
        ANSIBLE_NO_LOG="true",
        ANSIBLE_DEBUG="false",
        ANSIBLE_LOG_PATH="/dev/null",
        ANSIBLE_CACHE_PLUGIN="memory",
        ANSIBLE_RETRY_FILES_ENABLED="false",
        ANSIBLE_DISPLAY_ARGS_TO_STDOUT="false",
        ANSIBLE_STDOUT_CALLBACK="default",
        PYTHONDONTWRITEBYTECODE="1",
        PWD=os.getcwd(),
        ANSIBLE_CONFIG=str(
            Path(__file__).resolve().parents[1] / "controller-onepassword.cfg"
        ),
        ANSIBLE_LOOKUP_PLUGINS=str(Path(__file__).resolve().parent),
    )
    return env


def run_child(command, env, fd, timeout=1800):
    child = subprocess.Popen(
        command,
        env=env,
        pass_fds=(fd,),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        return child.wait(timeout=timeout)
    finally:
        # Includes forked workers retaining the credential FD, also after a
        # successful leader exit. The enforced namespace-init exit also kills
        # escaped sessions, which cannot be reached by this process group.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=5)


def interrupted(signum, frame):
    raise InterruptedError("controller interrupted")


def require_namespace_init():
    # Linux tears down EVERY remaining process in a PID namespace when its init
    # exits, including setsid/double-fork descendants. Do not accept --pid=host,
    # podman exec, --init/tini or a wrapper that leaves this launcher as a child.
    if sys.platform != "linux" or os.getpid() != 1 or os.getppid() != 0:
        raise ValueError("one-shot execution as PID namespace init required")


def launch(args):
    require_namespace_init()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    signal.signal(signal.SIGTERM, interrupted)
    agent_socket = None
    if args[:1] == ["--ssh-agent-socket"]:
        if len(args) < 4 or args[2] != "--":
            raise ValueError("explicit managed SSH transport arguments required")
        agent_socket = validated_agent_socket(args[1])
        args = args[2:]
    if not args or args[0] != "--" or len(args) == 1:
        raise ValueError("public playbook arguments required")
    if any(
        arg.startswith(("--vault-password-file", "--vault-id", "--ask-vault-pass"))
        for arg in args[1:]
    ):
        raise ValueError("legacy password options are outside the memory profile")
    payload = sys.stdin.buffer.read(LIMIT + 1)
    if not 0 < len(payload) <= LIMIT:
        raise ValueError("input size")
    decode(payload)
    fd = os.memfd_create(MEMORY_NAME, os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC)
    try:
        with os.fdopen(os.dup(fd), "wb") as output:
            output.write(payload)
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, SEALS)
        with tempfile.TemporaryDirectory(
            prefix="lit-controller-", dir="/tmp"
        ) as runtime:
            rc = run_child(
                [PLAYBOOK, *args[1:]], child_environment(fd, runtime, agent_socket), fd
            )
        print(json.dumps({"ansible_rc": rc, "secret_output": False}))
        return rc
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        sys.exit(launch(sys.argv[1:]))
    except (Exception, KeyboardInterrupt):
        print('{"controller_launch_stopped":true,"secret_output":false}')
        sys.exit(2)
