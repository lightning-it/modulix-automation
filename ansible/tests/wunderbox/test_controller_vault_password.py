"""Existing password-file custody checks; synthetic metadata fixtures only."""

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import yaml
from ansible.parsing.vault import VaultLib, VaultSecret

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "password_guard", ROOT / "lookup_plugins/lit_controller_vault_password.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PasswordCustodyTests(unittest.TestCase):
    def test_backup_runbook_invokes_atomic_encryptor(self):
        runbook = ROOT / "runbooks/50-applications/wunderbox/31-management-backup.yml"
        tasks = yaml.safe_load(runbook.read_text())[0]["tasks"]
        task = next(
            t for t in tasks if "_management_backup_encrypt_result" == t.get("register")
        )
        self.assertTrue(task["no_log"])
        argv = task["ansible.builtin.command"]["argv"]
        self.assertEqual(argv[:2], ["/opt/app-root/bin/python3", "-I"])
        helper = Path(argv[2].replace("{{ playbook_dir }}", str(runbook.parent)))
        self.assertEqual(helper.resolve(), Path(MODULE.__file__).resolve())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            password = root / "password"
            password.write_bytes(b"synthetic-password")
            password.chmod(0o600)
            backup = root / "backup"
            backup.write_bytes(b"synthetic-content")
            result = subprocess.run(
                [*argv[:2], str(helper), "encrypt", str(password), str(backup)],
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, b"")
            vault = VaultLib([("default", VaultSecret(b"synthetic-password"))])
            self.assertEqual(vault.decrypt(backup.read_bytes()), b"synthetic-content")

    def test_encryption_consumes_checked_inode_after_path_or_parent_swap(self):
        actual_consumer = MODULE.encrypt_from_descriptor
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
                    backup.write_bytes(b"synthetic-backup-payload")
                    checked_fds = []

                    def swap_then_consume(fd, destination):
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
                            return actual_consumer(fd, destination)

                    with mock.patch.object(
                        MODULE, "encrypt_from_descriptor", side_effect=swap_then_consume
                    ):
                        self.assertEqual(
                            MODULE.encrypt_backup(str(password), str(backup)), 0
                        )
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
            with mock.patch.object(MODULE, "encrypt_from_descriptor") as consumer:
                with self.assertRaises(ValueError):
                    MODULE.encrypt_backup(str(password), str(root / "backup"))
                consumer.assert_not_called()
            password.chmod(0o600)
            fds = []

            def fail(fd, destination):
                fds.append(fd)
                raise RuntimeError("synthetic encryption failure")

            with mock.patch.object(MODULE, "encrypt_from_descriptor", side_effect=fail):
                with self.assertRaises(RuntimeError):
                    MODULE.encrypt_backup(str(password), str(root / "backup"))
            for fd in fds:
                with self.assertRaises(OSError):
                    os.fstat(fd)

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
