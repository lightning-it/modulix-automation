"""Explicit controller-only lookup of one pinned, sealed 1Password item.

Also serves as the Linux EE launcher: JSON on stdin, public ansible-playbook
arguments after --. Neither secret contents nor subprocess output are emitted.
The desktop-side trusted transport must select the approved account and item.
"""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import ssl
import stat
import subprocess
import sys

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase

LIMIT = 1048576
FD_ENV = "LIT_CONTROLLER_ONEPASSWORD_FD"
MEMORY_NAME = "lit-controller-onepassword"
SEALS = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def decode(value):
    return json.loads(value, object_pairs_hook=unique_object)


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
        isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._~:+/-]{16,4096}", value)
        for value in result.values()
    ):
        raise ValueError("invalid AppRole material")
    return result


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


def launch(args):
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
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
        env = dict(
            os.environ,
            **{FD_ENV: str(fd)},
            ANSIBLE_NO_LOG="true",
            ANSIBLE_DEBUG="false",
            ANSIBLE_LOG_PATH="/dev/null",
            ANSIBLE_CACHE_PLUGIN="memory",
            ANSIBLE_RETRY_FILES_ENABLED="false",
            ANSIBLE_DISPLAY_ARGS_TO_STDOUT="false",
        )
        env.pop("ANSIBLE_VAULT_PASSWORD_FILE", None)
        env.pop("ANSIBLE_VAULT_IDENTITY_LIST", None)
        env["ANSIBLE_CONFIG"] = str(
            Path(__file__).resolve().parents[1] / "controller-onepassword.cfg"
        )
        env["ANSIBLE_LOOKUP_PLUGINS"] = str(Path(__file__).resolve().parent)
        env["PWD"] = os.getcwd()
        result = subprocess.run(
            ["ansible-playbook", *args[1:]],
            env=env,
            pass_fds=(fd,),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1800,
            check=False,
        )
        print(json.dumps({"ansible_rc": result.returncode, "secret_output": False}))
        return result.returncode
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        sys.exit(launch(sys.argv[1:]))
    except Exception:
        print('{"controller_launch_stopped":true,"secret_output":false}')
        sys.exit(2)
