"""Synthetic-only negative and real Ansible transport regression tests."""

import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "lookup_plugins/lit_controller_onepassword.py"
SPEC = importlib.util.spec_from_file_location("controller_op", PLUGIN)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    contract = {
        "schema_version": 1,
        "auth_method": "approle",
        "subject": "test-controller",
        "role_name": "test-controller",
        "auth_mount_point": "approle",
        "onepassword": {
            "item_id": "a" * 26,
            "vault_id": "b" * 26,
            "item_version": 1,
            "item_title": "Synthetic controller",
            "ca_sha256": "c" * 64,
        },
    }
    note = {key: value for key, value in contract.items() if key != "onepassword"}
    note.update(role_id="synthetic-role-000000000", secret_id="synthetic-secret-000000")
    item = {
        "id": "a" * 26,
        "vault": {"id": "b" * 26},
        "version": 1,
        "title": "Synthetic controller",
        "category": "SECURE_NOTE",
        "fields": [{"id": "notesPlain", "value": json.dumps(note)}],
    }
    return contract, item


class ControllerCredentialTests(unittest.TestCase):
    def test_exact_item(self):
        contract, item = fixture()
        self.assertEqual(
            set(MODULE.validate_item(item, contract)), {"role_id", "secret_id"}
        )

    def test_metadata_drift_and_boolean_version_rejected(self):
        contract, item = fixture()
        for field, value in [
            ("id", "z" * 26),
            ("version", 2),
            ("version", True),
            ("title", "Other"),
            ("category", "LOGIN"),
            ("vault", {"id": "z" * 26}),
        ]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                MODULE.validate_item(dict(item, **{field: value}), contract)

    def test_wrong_scope_and_template_credentials_rejected(self):
        contract, item = fixture()
        for field, value in [
            ("subject", "other"),
            ("role_name", "other"),
            ("auth_mount_point", "other"),
            ("schema_version", True),
            ("secret_id", "{{ unsafe_expression }}"),
        ]:
            candidate = copy.deepcopy(item)
            note = json.loads(candidate["fields"][0]["value"])
            note[field] = value
            candidate["fields"][0]["value"] = json.dumps(note)
            with self.subTest(field=field), self.assertRaises(ValueError):
                MODULE.validate_item(candidate, contract)

    def test_duplicate_notes_and_json_keys_rejected(self):
        contract, item = fixture()
        item["fields"] *= 2
        with self.assertRaises(ValueError):
            MODULE.validate_item(item, contract)
        with self.assertRaises(ValueError):
            MODULE.decode('{"id":1,"id":2}')

    def test_sealed_memory_required(self):
        _, item = fixture()
        fd = os.memfd_create(MODULE.MEMORY_NAME, os.MFD_ALLOW_SEALING)
        self.addCleanup(os.close, fd)
        os.write(fd, json.dumps(item).encode())
        with self.assertRaises(ValueError):
            MODULE.read_item(fd)
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, MODULE.SEALS)
        self.assertEqual(MODULE.read_item(fd), item)
        with self.assertRaises(OSError):
            os.write(fd, b"altered")

    def test_plain_file_not_accepted_as_memory_input(self):
        with tempfile.TemporaryFile() as source:
            source.write(b"{}")
            source.flush()
            with self.assertRaises((ValueError, OSError)):
                MODULE.read_item(source.fileno())

    def test_selector_preserves_default_and_protected_tasks(self):
        tasks = ROOT / "runbooks/00-common/tasks"
        selector = yaml.safe_load(
            (tasks / "resolve-hashicorp-vault-auth.yml").read_text()
        )
        self.assertTrue(all(task.get("no_log") is True for task in selector))
        includes = [
            task for task in selector if "ansible.builtin.include_tasks" in task
        ]
        self.assertEqual(len(includes), 2)
        self.assertIn("default('ansible_vault')", includes[0]["when"])
        memory = yaml.safe_load(
            (tasks / "resolve-hashicorp-vault-auth-onepassword.yml").read_text()
        )
        self.assertTrue(all(task.get("no_log") is True for task in memory))
        self.assertEqual(
            memory[2]["ansible.builtin.include_tasks"],
            "ensure-hashicorp-vault-ssh-tunnel.yml",
        )
        self.assertIn(
            "_hetzner_vault_ssh_tunnel_ready",
            memory[3]["ansible.builtin.assert"]["that"][0],
        )

    def test_real_ansible_launcher_and_ca_boundaries(self):
        contract, item = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secrets = root / ".secrets"
            secrets.mkdir(mode=0o700)
            ca = secrets / "ca.crt"
            bundle = re.search(
                rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
                Path("/etc/pki/tls/certs/ca-bundle.crt").read_bytes(),
                re.S,
            ).group(0)
            ca.write_bytes(bundle)
            ca.chmod(0o600)
            digest = hashlib.sha256(bundle).hexdigest()
            contract["onepassword"]["ca_sha256"] = digest
            self.assertEqual(
                MODULE.public_ca_digest(str(ca), str(root), digest), digest
            )
            with self.assertRaises(ValueError):
                MODULE.public_ca_digest(str(ca), str(root), "f" * 64)
            alias = secrets / "alias.crt"
            alias.symlink_to(ca)
            with self.assertRaises(OSError):
                MODULE.public_ca_digest(str(alias), str(root), digest)
            ca.chmod(0o666)
            with self.assertRaises(ValueError):
                MODULE.public_ca_digest(str(ca), str(root), digest)
            ca.chmod(0o600)
            play = root / "test.yml"
            play.write_text(
                yaml.safe_dump(
                    [
                        {
                            "hosts": "localhost",
                            "gather_facts": False,
                            "vars": {
                                "contract": contract,
                                "ca": str(ca),
                                "root": str(root),
                            },
                            "tasks": [
                                {
                                    "name": "Validate synthetic input",
                                    "no_log": True,
                                    "ansible.builtin.assert": {
                                        "that": [
                                            "lookup('lit_controller_onepassword', contract, ca_path=ca, project_root=root).role_id == 'synthetic-role-000000000'"
                                        ]
                                    },
                                }
                            ],
                        }
                    ]
                )
            )
            config = root / "ansible.cfg"
            config.write_text("[defaults]\n")
            env = dict(
                os.environ,
                ANSIBLE_CONFIG=str(config),
                ANSIBLE_LOOKUP_PLUGINS=str(PLUGIN.parent),
            )
            result = subprocess.run(
                [
                    "python3",
                    str(PLUGIN),
                    "--",
                    "-i",
                    "localhost,",
                    "-c",
                    "local",
                    str(play),
                ],
                input=json.dumps(item),
                text=True,
                capture_output=True,
                env=env,
                timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["ansible_rc"], 0)
            self.assertNotIn("synthetic-secret", result.stdout + result.stderr)
            item["version"] = 2
            rejected = subprocess.run(
                [
                    "python3",
                    str(PLUGIN),
                    "--",
                    "-i",
                    "localhost,",
                    "-c",
                    "local",
                    str(play),
                ],
                input=json.dumps(item),
                text=True,
                capture_output=True,
                env=env,
                timeout=45,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertNotIn("synthetic-secret", rejected.stdout + rejected.stderr)
            self.assertEqual(
                set(json.loads(rejected.stdout)), {"ansible_rc", "secret_output"}
            )


if __name__ == "__main__":
    unittest.main()
