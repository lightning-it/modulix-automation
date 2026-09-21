"""Synthetic-only negative and real Ansible transport regression tests."""

import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

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
    def setUp(self):
        self.runtime = tempfile.TemporaryDirectory()
        self.addCleanup(self.runtime.cleanup)

    def child_env(self, fd, agent_socket=None):
        return MODULE.child_environment(fd, self.runtime.name, agent_socket)

    def test_child_environment_is_allowlisted(self):
        unsafe = {
            "OP_SESSION_test": "synthetic",
            "OP_SERVICE_ACCOUNT_TOKEN": "synthetic",
            "VAULT_TOKEN": "synthetic",
            "AWS_SECRET_ACCESS_KEY": "synthetic",
            "LD_PRELOAD": "synthetic",
            "ANSIBLE_CONFIG": "/untrusted",
            "SSH_AUTH_SOCK": "/ambient-agent-not-authorized",
            "PATH": "/untrusted/bin",
            "HOME": "/untrusted/home",
            "TMPDIR": "/untrusted/tmp",
        }
        with patch.dict(os.environ, unsafe):
            env = self.child_env(42)
        for key in unsafe:
            self.assertNotEqual(env.get(key), unsafe[key])
        self.assertEqual(env[MODULE.FD_ENV], "42")
        self.assertEqual(env["ANSIBLE_NO_LOG"], "true")
        self.assertEqual(env["PATH"], MODULE.SYSTEM_PATH)
        self.assertEqual(env["HOME"], self.runtime.name)

    def test_launch_rejects_non_init_before_reading_credentials(self):
        with patch.object(MODULE.os, "getpid", return_value=2):
            with patch.object(MODULE.sys, "stdin") as source:
                with self.assertRaises(ValueError):
                    MODULE.launch(["--", "unused.yml"])
                source.buffer.read.assert_not_called()

    def test_namespace_init_requires_zero_parent(self):
        with patch.object(MODULE.os, "getpid", return_value=1):
            with patch.object(MODULE.os, "getppid", return_value=10):
                with self.assertRaises(ValueError):
                    MODULE.require_namespace_init()

    def test_agent_requires_explicit_private_owned_socket(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "agent")
            with socket.socket(socket.AF_UNIX) as agent:
                agent.bind(path)
                os.chmod(path, 0o600)
                with patch.dict(os.environ, SSH_AUTH_SOCK="/ambient-other-agent"):
                    self.assertNotIn("SSH_AUTH_SOCK", self.child_env(42))
                    self.assertEqual(self.child_env(42, path)["SSH_AUTH_SOCK"], path)
                alias = Path(directory) / "alias"
                alias.symlink_to(path)
                regular = Path(directory) / "regular"
                regular.touch(mode=0o600)
                for invalid in ("relative", str(alias), str(regular)):
                    with self.subTest(path=invalid), self.assertRaises(ValueError):
                        self.child_env(42, invalid)
                with patch.object(MODULE.os, "geteuid", return_value=os.geteuid() + 1):
                    with self.assertRaises(ValueError):
                        self.child_env(42, path)
                os.chmod(path, 0o666)
                with self.assertRaises(ValueError):
                    self.child_env(42, path)
                os.chmod(path, 0o600)
                os.chmod(directory, 0o777)
                with self.assertRaises(ValueError):
                    self.child_env(42, path)
                os.chmod(directory, 0o700)

    def test_backup_vault_lifecycle_cleanup_on_success_and_each_failure(self):
        runbook = ROOT / "runbooks/50-applications/wunderbox/31-management-backup.yml"
        play = yaml.safe_load(runbook.read_text())[0]
        lifecycle = play["tasks"][0]
        self.assertEqual(len(lifecycle["block"]), 5)
        resolver = lifecycle["block"][0]["ansible.builtin.include_tasks"]
        self.assertTrue((runbook.parent / resolver).resolve().is_file())
        self.assertIn(
            "validate-controller-vault-password-file.yml", str(play["pre_tasks"][-1])
        )
        self.assertIn("end_play", str(play["pre_tasks"][-2]))
        self.assertFalse(any("resolve-hashicorp" in str(t) for t in play["pre_tasks"]))
        self.assertNotIn("vault_secret_bundle", str(play["tasks"][1:]))
        close = lifecycle["always"][-1]["ansible.builtin.include_tasks"]
        close_path = (runbook.parent / close).resolve()
        self.assertTrue(close_path.is_file())
        # Exercise the actual runbook's block/always structure and real cleanup
        # include, replacing only network/secret operations with synthetic tasks.
        plays = []
        for failure_index in (-1, 0, 1, 2, 3, 4):
            candidate = copy.deepcopy(lifecycle)
            candidate["block"] = [
                {
                    "name": task["name"],
                    "ansible.builtin.assert": {"that": index != failure_index},
                }
                for index, task in enumerate(candidate["block"])
            ]
            candidate["always"][-1]["ansible.builtin.include_tasks"] = str(close_path)
            plays.append(
                {
                    "hosts": "localhost",
                    "gather_facts": False,
                    "tasks": [
                        {
                            "ansible.builtin.set_fact": {
                                "_hetzner_hashicorp_vault_auth": {"synthetic": True},
                                "_hetzner_vault_memory_auth": {"synthetic": True},
                                "_hetzner_vault_ssh_tunnel_ready": True,
                                "_hetzner_vault_tunnel_control_path_validated": False,
                                "synthetic_failure_seen": False,
                            }
                        },
                        {
                            "block": [candidate],
                            "rescue": [
                                {
                                    "ansible.builtin.set_fact": {
                                        "synthetic_failure_seen": True
                                    }
                                }
                            ],
                        },
                        {
                            "ansible.builtin.assert": {
                                "that": [
                                    "_hetzner_hashicorp_vault_auth == {}",
                                    "_hetzner_vault_memory_auth == {}",
                                    "not _hetzner_vault_ssh_tunnel_ready",
                                    "_hetzner_vault_tunnel_control_path is none",
                                    f"synthetic_failure_seen == {failure_index >= 0}",
                                ]
                            }
                        },
                    ],
                }
            )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cleanup.yml"
            path.write_text(yaml.safe_dump(plays))
            env = self.child_env(42)
            env.pop(MODULE.FD_ENV)
            result = subprocess.run(
                ["ansible-playbook", "-i", "localhost,", "-c", "local", str(path)],
                env=env,
                text=True,
                capture_output=True,
                timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_timeout_terminates_descriptor_holding_process_group(self):
        fd = os.memfd_create(MODULE.MEMORY_NAME, os.MFD_ALLOW_SEALING)
        self.addCleanup(os.close, fd)
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory) / "child.pid"
            code = (
                "import os,time; from pathlib import Path; "
                "pid=os.fork(); "
                f"Path({str(pidfile)!r}).write_text(str(os.getpid())) if pid==0 else None; "
                "time.sleep(30)"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                MODULE.run_child(
                    [sys.executable, "-c", code], self.child_env(fd), fd, timeout=1
                )
            pid = int(pidfile.read_text())
            proc = Path(f"/proc/{pid}/stat")
            if proc.exists():
                self.assertEqual(proc.read_text().split()[2], "Z")

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
            ("secret_id", "synthetic-secret\ninvalid"),
        ]:
            candidate = copy.deepcopy(item)
            note = json.loads(candidate["fields"][0]["value"])
            note[field] = value
            candidate["fields"][0]["value"] = json.dumps(note)
            with self.subTest(field=field), self.assertRaises(ValueError):
                MODULE.validate_item(candidate, contract)

    def test_approle_characters_are_literal_not_templates(self):
        contract, item = fixture()
        for value in ("valid=credential:with space", "{{ lookup('pipe', 'false') }}"):
            note = json.loads(item["fields"][0]["value"])
            note["secret_id"] = value
            item["fields"][0]["value"] = json.dumps(note)
            result = MODULE.validate_item(item, contract)["secret_id"]
            self.assertEqual(result, value)
            self.assertTrue(result.__UNSAFE__)

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
                                            "(query('lit_controller_onepassword', contract, ca_path=ca, project_root=root) | first).role_id == 'synthetic-role-000000000'",
                                            "lookup('ansible.builtin.env', 'SSH_AUTH_SOCK') == ''",
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
                SSH_AUTH_SOCK="/ambient-agent-must-not-reach-the-child",
            )
            # Unit layer: exercise the real Ansible transport while mocking ONLY
            # the namespace-init precondition. The separate OCI fixture runs the
            # unmodified launcher as real PID 1 and proves namespace teardown.
            unit_runner = [
                sys.executable,
                "-c",
                "import runpy,sys; m=runpy.run_path(sys.argv[1]); "
                "m['launch'].__globals__['require_namespace_init']=lambda:None; "
                "sys.exit(m['launch'](sys.argv[2:]))",
                str(PLUGIN),
            ]
            result = subprocess.run(
                [
                    *unit_runner,
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
            agent_path = str(root / "agent.sock")
            with socket.socket(socket.AF_UNIX) as agent:
                agent.bind(agent_path)
                os.chmod(agent_path, 0o600)
                body = yaml.safe_load(play.read_text())
                body[0]["tasks"][0]["ansible.builtin.assert"]["that"][
                    1
                ] = f"lookup('ansible.builtin.env', 'SSH_AUTH_SOCK') == '{agent_path}'"
                play.write_text(yaml.safe_dump(body))
                opted_in = subprocess.run(
                    [
                        *unit_runner,
                        "--ssh-agent-socket",
                        agent_path,
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
                self.assertEqual(
                    opted_in.returncode, 0, opted_in.stdout + opted_in.stderr
                )
                self.assertNotIn("synthetic-secret", opted_in.stdout + opted_in.stderr)
            body[0]["tasks"][0]["ansible.builtin.assert"]["that"][
                1
            ] = "lookup('ansible.builtin.env', 'SSH_AUTH_SOCK') == ''"
            play.write_text(yaml.safe_dump(body))
            item["version"] = 2
            rejected = subprocess.run(
                [
                    *unit_runner,
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
