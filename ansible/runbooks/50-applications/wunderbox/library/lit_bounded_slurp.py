#!/usr/bin/python
"""Read one regular dump with an enforced byte ceiling, including file growth."""

import base64
import os
import stat

from ansible.module_utils.basic import AnsibleModule

MAX_BYTES = 64 * 1024 * 1024


def read_bounded(src, max_bytes):
    if type(max_bytes) is not int or not 0 < max_bytes <= MAX_BYTES:
        raise ValueError("explicit backup limit must be within 1..64 MiB")
    if (
        not isinstance(src, str)
        or not src.startswith("/")
        or any(part in ("", ".", "..") for part in src.split("/")[1:])
    ):
        raise ValueError("absolute canonical dump path required")
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in src.split("/")[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
            )
            os.close(parent)
            parent = child
        fd = os.open(
            src.rsplit("/", 1)[1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent,
        )
    finally:
        os.close(parent)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_size > max_bytes
        ):
            raise ValueError("dump exceeds bounded regular-file contract")
        # Read at most limit+1; a stat-only check would race a growing file.
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("dump grew beyond backup limit")
        final = os.fstat(fd)
        if (
            len(data) != info.st_size
            or final.st_nlink != 1
            or final.st_size != info.st_size
            or final.st_mtime_ns != info.st_mtime_ns
            or final.st_ctime_ns != info.st_ctime_ns
        ):
            raise ValueError("dump changed during bounded read")
        return data
    finally:
        os.close(fd)


def main():
    module = AnsibleModule(
        argument_spec={
            "src": {"type": "path", "required": True},
            "max_bytes": {"type": "int", "required": True},
        },
        supports_check_mode=True,
    )
    try:
        data = read_bounded(module.params["src"], module.params["max_bytes"])
    except Exception:
        module.fail_json(msg="Bounded backup read failed", _ansible_no_log=True)
    module.exit_json(
        changed=False,
        encoding="base64",
        content=base64.b64encode(data).decode("ascii"),
        _ansible_no_log=True,
    )


if __name__ == "__main__":
    main()
