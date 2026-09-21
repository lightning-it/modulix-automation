"""Validate password custody; hold its checked descriptor through encryption."""

from contextlib import contextmanager
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase


@contextmanager
def open_password_file(path, forbidden_paths=()):
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or os.path.normpath(path) != path
        or path == "/"
        or path in forbidden_paths
    ):
        raise ValueError("canonical distinct password file required")
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    current = ""
    try:
        # Descriptor-relative traversal rejects symlinked ancestors and a
        # nonblocking final open rejects FIFOs/devices without reading secrets.
        for part in path.split("/")[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
            )
            os.close(parent)
            parent = child
            current += "/" + part
            info = os.fstat(parent)
            root_group = (
                info.st_uid == 0 and info.st_gid == 0 and not info.st_mode & 0o002
            )
            sticky_tmp = (
                current == "/tmp"
                and info.st_uid == 0
                and info.st_gid == 0
                and stat.S_IMODE(info.st_mode) == 0o1777
            )
            if info.st_uid not in (0, os.geteuid()) or (
                info.st_mode & 0o022 and not root_group and not sticky_tmp
            ):
                raise ValueError("unprotected password parent")
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
                or stat.S_IMODE(info.st_mode) not in (0o400, 0o600)
                or not 0 < info.st_size <= 1048576
            ):
                raise ValueError("protected regular password file required")
            yield fd
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def validate_password_file(path, forbidden_paths=()):
    # Early metadata preflight only, not a capability for a subsequent open.
    with open_password_file(path, forbidden_paths):
        return path


def encrypt_backup(password_path, ciphertext):
    if not os.path.isabs(ciphertext) or os.path.normpath(ciphertext) != ciphertext:
        raise ValueError("absolute backup path required")
    with open_password_file(password_path, (ciphertext,)) as fd:
        with tempfile.TemporaryDirectory(prefix="vault-encrypt-", dir="/tmp") as home:
            # Ansible's pinned CLI preserves /proc/self/fd paths (follow=False).
            # Keep this validated inode open until the actual consumer exits.
            # A pathname/parent replacement cannot redirect its password read.
            result = subprocess.run(
                [
                    "/opt/app-root/bin/ansible-vault",
                    "encrypt",
                    "--vault-password-file",
                    f"/proc/self/fd/{fd}",
                    "--",
                    ciphertext,
                ],
                pass_fds=(fd,),
                env={
                    "PATH": "/opt/app-root/bin:/usr/bin:/bin",
                    "LANG": "C.UTF-8",
                    "HOME": home,
                    "ANSIBLE_CONFIG": str(
                        Path(__file__).resolve().parents[1]
                        / "controller-onepassword.cfg"
                    ),
                    "ANSIBLE_VAULT_PASSWORD_FILE": "",
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1800,
                check=True,
            )
            return result.returncode


class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        try:
            if len(terms) != 1:
                raise ValueError("one password path required")
            return [validate_password_file(terms[0], kwargs.get("forbidden_paths", ()))]
        except Exception:
            raise AnsibleError(
                "Protected controller password-file validation failed"
            ) from None


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4 or sys.argv[1] != "encrypt":
            raise ValueError("encrypt, password path and backup path required")
        sys.exit(encrypt_backup(sys.argv[2], sys.argv[3]))
    except Exception:
        print("Protected backup encryption failed", file=sys.stderr)
        sys.exit(2)
