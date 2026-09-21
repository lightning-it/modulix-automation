"""Existing password-file custody checks; synthetic metadata fixtures only."""

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "password_guard", ROOT / "lookup_plugins/lit_controller_vault_password.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PasswordCustodyTests(unittest.TestCase):
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
