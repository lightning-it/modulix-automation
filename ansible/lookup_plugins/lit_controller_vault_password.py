"""Validate existing controller password-file custody without reading its value."""

import os
import stat

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase


def validate_password_file(path, forbidden_paths=()):
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
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    return path


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
