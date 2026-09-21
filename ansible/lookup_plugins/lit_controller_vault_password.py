"""Validate password custody and reserve ciphertext-only output descriptors."""

from contextlib import contextmanager
import os
import stat

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase
from ansible.parsing.vault import VaultLib, VaultSecret


@contextmanager
def open_protected_file(path, forbidden_paths=(), *, create_backup=False):
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
            if create_backup and current + "/" + part == os.path.dirname(path):
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
        if create_backup and stat.S_IMODE(os.fstat(parent).st_mode) != 0o700:
            raise ValueError("private backup directory required")
        fd = os.open(
            path.rsplit("/", 1)[1],
            ((os.O_WRONLY | os.O_CREAT | os.O_EXCL) if create_backup else os.O_RDONLY)
            | os.O_NOFOLLOW
            | os.O_NONBLOCK,
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
                not in ((0o600,) if create_backup else (0o400, 0o600))
                or (not create_backup and info.st_size <= 0)
                or (not create_backup and info.st_size > 1048576)
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
    raise SystemExit("No command-line encryption interface; use the protected action")
