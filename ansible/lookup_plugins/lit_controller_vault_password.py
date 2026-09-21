"""Validate password custody; hold its checked descriptor through encryption."""

from contextlib import contextmanager
import os
import resource
import stat
import sys

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase
from ansible.parsing.vault import VaultLib, VaultSecret


@contextmanager
def open_protected_file(path, forbidden_paths=(), *, backup=False, create=False):
    if create and not backup:
        raise ValueError("creation is restricted to encrypted backup output")
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
            if create and current + "/" + part == os.path.dirname(path):
                try:
                    os.mkdir(part, 0o700, dir_fd=parent)
                except FileExistsError:
                    pass
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
        if backup and stat.S_IMODE(os.fstat(parent).st_mode) != 0o700:
            raise ValueError("private backup directory required")
        fd = os.open(
            path.rsplit("/", 1)[1],
            (os.O_RDWR if backup else os.O_RDONLY)
            | os.O_NOFOLLOW
            | os.O_NONBLOCK
            | ((os.O_CREAT | os.O_EXCL) if create else 0),
            0o600,
            dir_fd=parent,
        )
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid not in (0, os.geteuid())
                or stat.S_IMODE(info.st_mode)
                not in ((0o600, 0o640, 0o644) if backup else (0o400, 0o600))
                or (not create and info.st_size <= 0)
                or (not backup and info.st_size > 1048576)
            ):
                raise ValueError("protected regular password file required")
            yield fd
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def validate_password_file(path, forbidden_paths=()):
    # Early metadata preflight only, not a capability for a subsequent open.
    with open_protected_file(path, forbidden_paths):
        return path


def encrypt_from_descriptor(fd, ciphertext):
    password = os.pread(fd, 1048577, 0).strip()
    if not password or len(password) > 1048576:
        raise ValueError("non-empty bounded password required")
    # The pinned Ansible library encrypts in-process. No child is created and
    # the checked password descriptor is never inherited by another process.
    with open_protected_file(ciphertext, backup=True) as output_fd:
        os.fchmod(output_fd, 0o600)
        with os.fdopen(os.dup(output_fd), "r+b") as output:
            data = VaultLib().encrypt(output.read(), VaultSecret(password))
            output.seek(0)
            output.write(data)
            output.truncate()
            output.flush()
            os.fsync(output.fileno())
    return 0


def encrypt_backup(password_path, ciphertext):
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if not os.path.isabs(ciphertext) or os.path.normpath(ciphertext) != ciphertext:
        raise ValueError("absolute backup path required")
    with open_protected_file(password_path, (ciphertext,)) as fd:
        return encrypt_from_descriptor(fd, ciphertext)


def write_encrypted_payload(password_fd, output_fd, plaintext):
    """Only ciphertext crosses the already validated output descriptor."""
    password = os.pread(password_fd, 1048577, 0).strip()
    if not password or len(password) > 1048576:
        raise ValueError("non-empty bounded password required")
    data = VaultLib().encrypt(plaintext, VaultSecret(password))
    with os.fdopen(os.dup(output_fd), "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


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
