"""Existing password-file custody checks; synthetic metadata fixtures only."""

import base64
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import yaml
from ansible.parsing.vault import VaultLib, VaultSecret

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "password_guard", ROOT / "lookup_plugins/lit_controller_vault_password.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ACTION_PATH = (
    ROOT / "runbooks/50-applications/wunderbox/action_plugins/lit_encrypted_backup.py"
)
ACTION_SPEC = importlib.util.spec_from_file_location("encrypted_backup", ACTION_PATH)
ACTION = importlib.util.module_from_spec(ACTION_SPEC)
ACTION_SPEC.loader.exec_module(ACTION)
READER_PATH = ACTION_PATH.parent.parent / "library/lit_bounded_slurp.py"
READER_SPEC = importlib.util.spec_from_file_location("bounded_reader", READER_PATH)
READER = importlib.util.module_from_spec(READER_SPEC)
READER_SPEC.loader.exec_module(READER)


class PasswordCustodyTests(unittest.TestCase):
    def test_backup_runbook_invokes_memory_encryptor_in_real_ansible(self):
        runbook = ROOT / "runbooks/50-applications/wunderbox/31-management-backup.yml"
        tasks = yaml.safe_load(runbook.read_text())[0]["tasks"]
        task = next(
            t for t in tasks if "_management_backup_encrypt_result" == t.get("register")
        )
        self.assertTrue(task["no_log"])
        self.assertIn("lit_encrypted_backup", task)
        self.assertFalse(any("ansible.builtin.fetch" in t for t in tasks))
        self.assertNotIn("delegate_to", task)  # slurp must read the managed host
        self.assertEqual(ACTION.HELPER, Path(MODULE.__file__))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            password = root / "password"
            password.write_bytes(b"synthetic-password")
            password.chmod(0o600)
            source = root / "remote-dump"
            source.write_bytes(b"synthetic-content")
            backup = root / "new-private-directory" / "backup"
            play = root / "test.yml"
            play.write_text(
                yaml.safe_dump(
                    [
                        {
                            "hosts": "localhost",
                            "gather_facts": False,
                            "tasks": [
                                {
                                    "lit_encrypted_backup": {
                                        "src": str(source),
                                        "dest": str(backup),
                                        "password_file": str(password),
                                        "max_bytes": 1024,
                                    },
                                    "no_log": True,
                                }
                            ],
                        }
                    ]
                )
            )
            result = subprocess.run(
                [
                    "/opt/app-root/bin/ansible-playbook",
                    "-i",
                    "localhost,",
                    "-c",
                    "local",
                    str(play),
                ],
                env=dict(
                    os.environ,
                    ANSIBLE_CONFIG=str(ROOT / "controller-onepassword.cfg"),
                    ANSIBLE_ACTION_PLUGINS=str(ACTION_PATH.parent),
                    ANSIBLE_LIBRARY=str(READER_PATH.parent),
                ),
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn(b"synthetic-content", result.stdout + result.stderr)
            vault = VaultLib([("default", VaultSecret(b"synthetic-password"))])
            self.assertEqual(vault.decrypt(backup.read_bytes()), b"synthetic-content")
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
            self.assertEqual(backup.parent.stat().st_mode & 0o777, 0o700)

    def test_memory_fetch_rejects_existing_destination_and_symlink_parent(self):
        for kind in ("symlink", "hardlink", "regular", "parent-symlink"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                password = root / "password"
                password.write_bytes(b"synthetic-password")
                password.chmod(0o600)
                victim = root / "victim"
                victim.write_bytes(b"unchanged")
                parent = root / "backups"
                parent.mkdir(mode=0o700)
                backup = parent / "backup"
                if kind == "symlink":
                    backup.symlink_to(victim)
                elif kind == "hardlink":
                    os.link(victim, backup)
                elif kind == "regular":
                    backup.write_bytes(b"unchanged")
                else:
                    parent.rmdir()
                    parent.symlink_to(root, target_is_directory=True)
                action = object.__new__(ACTION.ActionModule)
                action._task = SimpleNamespace(
                    args={
                        "src": "/synthetic/remote",
                        "dest": str(backup),
                        "password_file": str(password),
                        "max_bytes": 1024,
                    }
                )
                with mock.patch.object(ACTION.ActionBase, "run", return_value={}):
                    with mock.patch.object(action, "_execute_module") as fetch:
                        result = action.run(task_vars={})
                self.assertTrue(result["failed"])
                fetch.assert_not_called()
                self.assertEqual(victim.read_bytes(), b"unchanged")

    def test_memory_fetch_uses_open_inode_after_parent_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            password = root / "password"
            password.write_bytes(b"synthetic-password")
            password.chmod(0o600)
            parent = root / "backups"
            backup = parent / "dump"
            action = object.__new__(ACTION.ActionModule)
            action._task = SimpleNamespace(
                args={
                    "src": "/synthetic/remote",
                    "dest": str(backup),
                    "password_file": str(password),
                    "max_bytes": 1024,
                }
            )

            def swap(**kwargs):
                self.assertEqual(backup.read_bytes(), b"")
                parent.rename(root / "retired")
                parent.mkdir(mode=0o700)
                backup.write_bytes(b"unchanged")
                return {
                    "encoding": "base64",
                    "content": base64.b64encode(b"payload").decode(),
                }

            with mock.patch.object(ACTION.ActionBase, "run", return_value={}):
                with mock.patch.object(action, "_execute_module", side_effect=swap):
                    result = action.run(task_vars={})
            self.assertNotIn("failed", result)
            self.assertEqual(backup.read_bytes(), b"unchanged")
            vault = VaultLib([("default", VaultSecret(b"synthetic-password"))])
            self.assertEqual(
                vault.decrypt((root / "retired/dump").read_bytes()), b"payload"
            )

    def test_memory_fetch_failure_is_redacted_and_never_writes_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            password = root / "password"
            password.write_bytes(b"synthetic-password")
            password.chmod(0o600)
            backup = root / "backup"
            action = object.__new__(ACTION.ActionModule)
            action._task = SimpleNamespace(
                args={
                    "src": "/synthetic/remote",
                    "dest": str(backup),
                    "password_file": str(password),
                    "max_bytes": 1024,
                }
            )
            with mock.patch.object(ACTION.ActionBase, "run", return_value={}):
                with mock.patch.object(
                    action,
                    "_execute_module",
                    return_value={
                        "failed": True,
                        "msg": "synthetic-secret",
                        "content": "synthetic-secret",
                    },
                ):
                    result = action.run(task_vars={})
            self.assertTrue(result["failed"])
            self.assertTrue(result["changed"])
            self.assertNotIn("synthetic-secret", str(result))
            self.assertEqual(backup.read_bytes(), b"")

    def test_bounded_reader_rejects_size_growth_symlink_and_fifo(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "dump"
            source.write_bytes(b"01234567")
            self.assertEqual(READER.read_bounded(str(source), 8), b"01234567")
            for limit in (0, -1, True, "8", 64 * 1024 * 1024 + 1, 7):
                with self.subTest(limit=limit), self.assertRaises(ValueError):
                    READER.read_bounded(str(source), limit)
            info = source.stat()
            with mock.patch.object(
                READER.os,
                "fstat",
                return_value=SimpleNamespace(st_mode=info.st_mode, st_size=0),
            ):
                with self.assertRaises(ValueError):
                    READER.read_bounded(str(source), 7)
            link = source.parent / "link"
            link.symlink_to(source)
            fifo = source.parent / "fifo"
            os.mkfifo(fifo)
            for invalid in (link, fifo, source.parent):
                with self.subTest(path=invalid), self.assertRaises(
                    (ValueError, OSError)
                ):
                    READER.read_bounded(str(invalid), 8)

    def test_bounded_reader_rejects_changes_during_or_after_read(self):
        for mode in ("grow-during", "grow-after", "shrink-after", "rewrite-after"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "dump"
                source.write_bytes(b"01234567")
                original_fstat = os.fstat
                calls = []

                def mutate_at_boundary(fd):
                    calls.append(fd)
                    before = original_fstat(fd)
                    boundary = 1 if mode == "grow-during" else 2
                    if len(calls) == boundary:
                        replacement = {
                            "grow-during": b"012345678",
                            "grow-after": b"012345678",
                            "shrink-after": b"0123",
                            "rewrite-after": b"abcdefgh",
                        }[mode]
                        source.write_bytes(replacement)
                        os.utime(
                            source,
                            ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000),
                        )
                    # First stat precedes the injected write; the final stat
                    # observes it. Growth stays under the explicit capacity.
                    return before if len(calls) == 1 else original_fstat(fd)

                with mock.patch.object(
                    READER.os, "fstat", side_effect=mutate_at_boundary
                ):
                    with self.assertRaisesRegex(
                        ValueError, "changed during bounded read"
                    ):
                        READER.read_bounded(str(source), 16)
                with self.assertRaises(OSError):
                    original_fstat(calls[0])

    def test_capacity_failure_precedes_fetch_and_payload_decode(self):
        for limit in (0, -1, True, "8", 64 * 1024 * 1024 + 1, 3):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                password = root / "password"
                password.write_bytes(b"synthetic-password")
                password.chmod(0o600)
                backup = root / "dump"
                action = object.__new__(ACTION.ActionModule)
                action._task = SimpleNamespace(
                    args={
                        "src": "/remote",
                        "dest": str(backup),
                        "password_file": str(password),
                        "max_bytes": limit,
                    }
                )
                with mock.patch.object(ACTION.ActionBase, "run", return_value={}):
                    with mock.patch.object(
                        action,
                        "_execute_module",
                        return_value={"encoding": "base64", "content": "AAAAAA=="},
                    ) as fetch:
                        with mock.patch.object(ACTION.base64, "b64decode") as decoder:
                            result = action.run(task_vars={})
                self.assertTrue(result["failed"])
                decoder.assert_not_called()
                if limit != 3:
                    fetch.assert_not_called()
                    self.assertFalse(backup.exists())
                else:
                    self.assertEqual(backup.read_bytes(), b"")

    def test_encryption_consumes_checked_inode_after_path_or_parent_swap(self):
        actual_consumer = ACTION.CUSTODY.write_encrypted_payload
        for replace_parent in (False, True):
            with self.subTest(replace_parent=replace_parent):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    custody = root / "custody"
                    custody.mkdir(mode=0o700)
                    password = custody / "password"
                    password.write_bytes(b"synthetic-original-password")
                    password.chmod(0o600)
                    backup = root / "backup.dump"
                    checked_fds = []

                    def swap_then_consume(fd, destination_fd, plaintext):
                        checked_fds.append(fd)
                        self.assertFalse(os.get_inheritable(fd))
                        if replace_parent:
                            custody.rename(root / "retired")
                            custody.mkdir(mode=0o700)
                        else:
                            password.rename(custody / "retired")
                        password.write_bytes(b"synthetic-replacement-password")
                        password.chmod(0o600)
                        with mock.patch(
                            "subprocess.Popen",
                            side_effect=AssertionError("no child allowed"),
                        ):
                            return actual_consumer(fd, destination_fd, plaintext)

                    action = object.__new__(ACTION.ActionModule)
                    action._task = SimpleNamespace(
                        args={
                            "src": "/synthetic/remote",
                            "dest": str(backup),
                            "password_file": str(password),
                            "max_bytes": 1024,
                        }
                    )
                    with mock.patch.object(
                        ACTION.CUSTODY,
                        "write_encrypted_payload",
                        side_effect=swap_then_consume,
                    ):
                        with mock.patch.object(
                            ACTION.ActionBase, "run", return_value={}
                        ):
                            with mock.patch.object(
                                action,
                                "_execute_module",
                                return_value={
                                    "encoding": "base64",
                                    "content": base64.b64encode(
                                        b"synthetic-backup-payload"
                                    ).decode(),
                                },
                            ):
                                result = action.run(task_vars={})
                        self.assertNotIn("failed", result)
                    for fd in checked_fds:
                        with self.assertRaises(OSError):
                            os.fstat(fd)
                    encrypted = backup.read_bytes()
                    self.assertTrue(encrypted.startswith(b"$ANSIBLE_VAULT;"))
                    original = VaultLib(
                        [("default", VaultSecret(b"synthetic-original-password"))]
                    )
                    self.assertEqual(
                        original.decrypt(encrypted), b"synthetic-backup-payload"
                    )
                    replaced = VaultLib(
                        [("default", VaultSecret(b"synthetic-replacement-password"))]
                    )
                    with self.assertRaises(Exception):
                        replaced.decrypt(encrypted)

    def test_invalid_custody_never_starts_encryptor_and_closes_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            password = root / "password"
            password.write_text("synthetic-password")
            password.chmod(0o644)
            backup = root / "backup"
            action = object.__new__(ACTION.ActionModule)
            action._task = SimpleNamespace(
                args={
                    "src": "/synthetic/remote",
                    "dest": str(backup),
                    "password_file": str(password),
                    "max_bytes": 1024,
                }
            )
            with mock.patch.object(ACTION.ActionBase, "run", return_value={}):
                with mock.patch.object(action, "_execute_module") as fetch:
                    self.assertTrue(action.run(task_vars={})["failed"])
                fetch.assert_not_called()
            self.assertFalse(backup.exists())
            password.chmod(0o600)
            fds = []

            def fail(fd, output_fd, plaintext):
                fds.extend((fd, output_fd))
                raise RuntimeError("synthetic encryption failure")

            with mock.patch.object(
                ACTION.CUSTODY, "write_encrypted_payload", side_effect=fail
            ):
                with mock.patch.object(ACTION.ActionBase, "run", return_value={}):
                    with mock.patch.object(
                        action,
                        "_execute_module",
                        return_value={"encoding": "base64", "content": "cGF5bG9hZA=="},
                    ):
                        self.assertTrue(action.run(task_vars={})["failed"])
            self.assertEqual(backup.read_bytes(), b"")
            for fd in fds:
                with self.assertRaises(OSError):
                    os.fstat(fd)

    def test_encryption_and_write_failure_never_leave_plaintext(self):
        for failing_call in ("encrypt", "fsync"):
            with self.subTest(
                failing_call=failing_call
            ), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                password = root / "password"
                password.write_bytes(b"synthetic-password")
                password.chmod(0o600)
                backup = root / "backup"
                action = object.__new__(ACTION.ActionModule)
                action._task = SimpleNamespace(
                    args={
                        "src": "/synthetic/remote",
                        "dest": str(backup),
                        "password_file": str(password),
                        "max_bytes": 1024,
                    }
                )
                owner = (
                    ACTION.CUSTODY.VaultLib
                    if failing_call == "encrypt"
                    else ACTION.CUSTODY.os
                )
                with mock.patch.object(
                    owner, failing_call, side_effect=OSError("synthetic failure")
                ):
                    with mock.patch.object(ACTION.ActionBase, "run", return_value={}):
                        with mock.patch.object(
                            action,
                            "_execute_module",
                            return_value={
                                "encoding": "base64",
                                "content": base64.b64encode(
                                    b"synthetic-plaintext-payload"
                                ).decode(),
                            },
                        ):
                            result = action.run(task_vars={})
                self.assertTrue(result["failed"])
                contents = backup.read_bytes()
                self.assertNotIn(b"synthetic-plaintext-payload", contents)
                if failing_call == "encrypt":
                    self.assertEqual(contents, b"")
                else:
                    self.assertTrue(contents.startswith(b"$ANSIBLE_VAULT;"))

    def test_obsolete_in_place_cli_is_rejected_without_touching_files(self):
        self.assertFalse(hasattr(MODULE, "encrypt_backup"))
        self.assertFalse(hasattr(MODULE, "encrypt_from_descriptor"))
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "old-input"
            backup.write_bytes(b"synthetic-old-input")
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(MODULE.__file__),
                    "encrypt",
                    "/absent",
                    str(backup),
                ],
                capture_output=True,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(b"synthetic-old-input", result.stdout + result.stderr)
            self.assertEqual(backup.read_bytes(), b"synthetic-old-input")

    def test_metadata_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = root / "custody"
            value.write_text("synthetic-fixture-only")
            value.chmod(0o600)
            self.assertEqual(MODULE.validate_password_file(str(value)), str(value))
            value.chmod(0o400)
            self.assertEqual(MODULE.validate_password_file(str(value)), str(value))
            link = root / "alias"
            link.symlink_to(value)
            fifo = root / "fifo"
            os.mkfifo(fifo, 0o600)
            for path in (
                "",
                "relative",
                str(root),
                str(root / "missing"),
                str(link),
                str(fifo),
                str(root) + "/../custody",
            ):
                with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                    MODULE.validate_password_file(path)
            with self.assertRaises(ValueError):
                MODULE.validate_password_file(str(value), [str(value)])
            for mode in (0o000, 0o644, 0o666, 0o700):
                value.chmod(mode)
                with self.subTest(mode=mode), self.assertRaises((ValueError, OSError)):
                    MODULE.validate_password_file(str(value))
            value.chmod(0o600)
            alias = root / "hardlink"
            os.link(value, alias)
            with self.assertRaises(ValueError):
                MODULE.validate_password_file(str(value))
            alias.unlink()
            value.write_text("")
            with self.assertRaises(ValueError):
                MODULE.validate_password_file(str(value))
            with value.open("wb") as stream:
                stream.truncate(1048577)
            with self.assertRaises(ValueError):
                MODULE.validate_password_file(str(value))
            value.write_text("synthetic")
            root.chmod(0o777)
            with self.assertRaises(ValueError):
                MODULE.validate_password_file(str(value))
            root.chmod(0o700)

    def test_shared_include_resolves_in_real_ansible(self):
        helper = (
            ROOT
            / "runbooks/00-common/tasks/validate-controller-vault-password-file.yml"
        )
        tasks = yaml.safe_load(helper.read_text())
        self.assertTrue(all(task.get("no_log") for task in tasks))
        legacy = (
            helper.parent / "resolve-hashicorp-vault-auth-ansible-vault.yml"
        ).read_text()
        self.assertLess(
            legacy.index(helper.name),
            legacy.index("ensure-hashicorp-vault-ssh-tunnel.yml"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            password = root / "password"
            password.write_text("synthetic-fixture-only")
            password.chmod(0o600)
            play = root / "test.yml"
            play.write_text(
                yaml.safe_dump(
                    [
                        {
                            "hosts": "localhost",
                            "gather_facts": False,
                            "vars": {
                                "hetzner_baremetal_vault": {
                                    "ca_cert_path": str(root / "ca"),
                                    "controller_auth": {
                                        "backend": "onepassword_memory"
                                    },
                                }
                            },
                            "tasks": tasks
                            + [
                                {
                                    "ansible.builtin.assert": {
                                        "that": f"_hetzner_vault_validated_password_file == '{password}'"
                                    }
                                }
                            ],
                        }
                    ]
                )
            )
            env = dict(
                os.environ,
                ANSIBLE_CONFIG=str(ROOT / "controller-onepassword.cfg"),
                ANSIBLE_LOOKUP_PLUGINS=str(ROOT / "lookup_plugins"),
                ANSIBLE_VAULT_PASSWORD_FILE=str(password),
            )
            result = subprocess.run(
                [
                    "/opt/app-root/bin/ansible-playbook",
                    "-i",
                    "localhost,",
                    "-c",
                    "local",
                    str(play),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
