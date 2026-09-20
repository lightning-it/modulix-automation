"""Static fail-closed guards for the Wunderbox orchestration runbooks."""

from collections.abc import Mapping
from pathlib import Path
import unittest

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUNBOOK_DIRECTORY = (
    REPOSITORY_ROOT / "ansible" / "runbooks" / "50-applications" / "wunderbox"
)
GUARD_PATH = RUNBOOK_DIRECTORY / "tasks" / "orchestration-guard.yml"


def load_yaml(path: Path):
    """Load one repository YAML document."""
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def normalized_task_module_names(task):
    """Return FQCN and short module names from supported Ansible task forms."""
    module_names = {key for key in task if isinstance(key, str)}
    for action_key in ("action", "local_action"):
        action = task.get(action_key)
        module_name = None
        if isinstance(action, str):
            action_parts = action.split(maxsplit=1)
            if action_parts:
                module_name = action_parts[0]
        elif isinstance(action, Mapping):
            module_name = action.get("module")
        if isinstance(module_name, str):
            module_names.add(module_name)

    return module_names | {name.rsplit(".", 1)[-1] for name in module_names}


class WunderboxRunbookSafetyTests(unittest.TestCase):
    """Keep target, approval, preflight, and retirement guards reviewable."""

    def test_all_public_runbooks_are_single_host_fail_closed(self):
        for name in ("05-prepare.yml", "07-preflight.yml", "10-deploy.yml", "20-ops.yml"):
            with self.subTest(runbook=name):
                plays = load_yaml(RUNBOOK_DIRECTORY / name)
                play = plays[-1]
                self.assertEqual(play["hosts"], "wunderboxes")
                self.assertEqual(play["serial"], 1)
                self.assertIs(play["any_errors_fatal"], True)
                self.assertIs(play["gather_facts"], True)

                guard_import = play["pre_tasks"][0]
                self.assertEqual(
                    guard_import["ansible.builtin.import_tasks"],
                    "tasks/orchestration-guard.yml",
                )
                self.assertIn("always", guard_import["tags"])

    def test_target_guard_requires_limit_inventory_request_and_host_facts(self):
        guard = GUARD_PATH.read_text(encoding="utf-8")

        for condition in (
            "ansible_limit is defined",
            "ansible_limit | string | trim == inventory_hostname",
            "ansible_play_hosts_all | length == 1",
            "ansible_play_hosts_all == [inventory_hostname]",
            "inventory_hostname == wunderbox_orchestration.target.fqdn",
            "wunderbox_request_target.id == wunderbox_orchestration.target.id",
            "wunderbox_request_target.fqdn == wunderbox_orchestration.target.fqdn",
            "wunderbox_request_target.ipv4 == wunderbox_orchestration.target.ipv4",
            "wunderbox_request_target.provider_id",
            "== wunderbox_orchestration.target.provider_id",
            "ansible_facts.get('fqdn', '') == wunderbox_orchestration.target.fqdn",
            "ansible_facts.get('default_ipv4', {}).get('address', '')",
            "ansible_host | string == wunderbox_orchestration.target.ipv4",
        ):
            with self.subTest(condition=condition):
                self.assertIn(condition, guard)

    def test_inventory_gate_cannot_supply_observed_runtime_approval(self):
        guard = GUARD_PATH.read_text(encoding="utf-8")

        self.assertIn("wunderbox_orchestration.gate.required_status == 'approved'", guard)
        self.assertIn("wunderbox_request_gate.observed_status", guard)
        self.assertIn("== wunderbox_orchestration.gate.required_status", guard)
        self.assertIn("wunderbox_request_gate.id == wunderbox_orchestration.gate.id", guard)
        self.assertNotIn("wunderbox_orchestration.gate.observed_status", guard)
        self.assertNotIn("wunderbox_orchestration.approval_tokens.token", guard)

        for phase in ("prepare", "deploy", "retirement"):
            with self.subTest(phase=phase):
                self.assertIn(f"approval_tokens.{phase}_sha256", guard)
                self.assertIn(f"wunderbox_{phase}_approval_token", guard)
                self.assertIn("hash('sha256')", guard)

    def test_productive_plays_default_to_a_read_only_end_play(self):
        for name in ("05-prepare.yml", "10-deploy.yml"):
            with self.subTest(runbook=name):
                play = load_yaml(RUNBOOK_DIRECTORY / name)[-1]
                self.assertIs(play["vars"]["_wunderbox_orchestration_mutating"], True)
                end_play = play["pre_tasks"][1]
                self.assertEqual(end_play["ansible.builtin.meta"], "end_play")
                self.assertIn("ansible_check_mode", end_play["when"])
                self.assertIn("default('plan') == 'plan'", end_play["when"])
                self.assertIn("always", end_play["tags"])

    def test_deploy_imports_unskippable_preflight_first(self):
        deploy = load_yaml(RUNBOOK_DIRECTORY / "10-deploy.yml")
        self.assertEqual(
            deploy[0]["ansible.builtin.import_playbook"], "07-preflight.yml"
        )

        preflight = load_yaml(RUNBOOK_DIRECTORY / "07-preflight.yml")[0]
        self.assertIs(preflight["vars"]["_wunderbox_orchestration_mutating"], False)
        for task in preflight["tasks"]:
            with self.subTest(task=task["name"]):
                self.assertIn("always", task["tags"])

    def test_preflight_and_guard_tasks_are_read_only(self):
        forbidden_modules = {
            "ansible.builtin.copy",
            "ansible.builtin.file",
            "ansible.builtin.include_role",
            "ansible.builtin.package",
            "ansible.builtin.service",
            "ansible.builtin.systemd_service",
            "ansible.builtin.template",
            "copy",
            "file",
            "include_role",
            "package",
            "service",
            "systemd_service",
            "template",
        }

        task_sets = (
            load_yaml(GUARD_PATH),
            load_yaml(RUNBOOK_DIRECTORY / "07-preflight.yml")[0]["tasks"],
        )
        for tasks in task_sets:
            for task in tasks:
                with self.subTest(task=task["name"]):
                    modules = normalized_task_module_names(task)
                    self.assertFalse(forbidden_modules.intersection(modules))
                    if "command" in modules:
                        self.assertIs(task.get("changed_when"), False)

    def test_retirement_requires_inventory_and_runtime_opt_in(self):
        deploy = load_yaml(RUNBOOK_DIRECTORY / "10-deploy.yml")[-1]
        retirement = next(
            task
            for task in deploy["tasks"]
            if task["name"] == "Retire Semaphore from Wunderbox when disabled"
        )
        conditions = "\n".join(retirement["when"])
        self.assertIn("wunderbox_retirement_requested", conditions)
        self.assertIn("semaphore_deploy", conditions)

        guard = GUARD_PATH.read_text(encoding="utf-8")
        self.assertIn("wunderbox_orchestration.retirement.allowed | bool", guard)
        self.assertIn("wunderbox_retirement_approval_token", guard)
        self.assertIn("or not ansible_check_mode", guard)

    def test_public_documentation_uses_only_sanitized_contract_values(self):
        readme = (RUNBOOK_DIRECTORY / "README.md").read_text(encoding="utf-8")
        self.assertIn("example.invalid", readme)
        self.assertIn("192.0.2.10", readme)
        self.assertIn("deploy_sha256: disabled", readme)

    def test_controller_ssh_trust_is_exact_fingerprint_bound(self):
        path = RUNBOOK_DIRECTORY / "21-controller-ssh-trust.yml"
        play = load_yaml(path)[0]
        source = path.read_text(encoding="utf-8")

        self.assertEqual(play["hosts"], "wunderboxes")
        self.assertEqual(play["connection"], "local")
        self.assertIs(play["gather_facts"], False)
        self.assertEqual(play["serial"], 1)
        self.assertIs(play["any_errors_fatal"], True)
        for required in (
            "ansible_limit | string | trim == inventory_hostname",
            "ansible_play_hosts_all == [inventory_hostname]",
            "openssh_server_host_key_ed25519_fingerprint",
            "hetzner_baremetal_rescue_known_hosts_path is defined",
            "hetzner_baremetal_rescue_known_hosts_path\n            | default('')",
            "ssh-keyscan",
            "{{ ansible_port | string }}",
            "== _wunderbox_controller_ssh_trust_expected_fingerprint",
            "PIN-WUNDERBOX-OPENSSH:",
            "ansible.builtin.known_hosts",
            "Inspect the controller trust directory before mutation",
            "_wunderbox_controller_ssh_trust_directory_before.stat.islnk",
            "Inspect the controller trust file before mutation",
            "_wunderbox_controller_ssh_trust_file_before.stat.islnk",
            "not _wunderbox_controller_ssh_trust_readback.stat.islnk",
            "_wunderbox_controller_ssh_trust_readback.stat.mode == '0600'",
        ):
            with self.subTest(required=required):
                self.assertIn(required, source)

        self.assertLess(
            source.index("Require the inventory-pinned OpenSSH fingerprint"),
            source.index("Pin the verified installed OpenSSH host key"),
        )
        self.assertLess(
            source.index("Inspect the controller trust directory before mutation"),
            source.index("Create the private controller trust directory"),
        )
        self.assertLess(
            source.index("Inspect the controller trust file before mutation"),
            source.index("Pin the verified installed OpenSSH host key"),
        )

    def test_management_gateway_requires_vault_only_certificate_custody(self):
        runbook = load_yaml(RUNBOOK_DIRECTORY / "30-management-services.yml")[-1]
        source = (RUNBOOK_DIRECTORY / "30-management-services.yml").read_text(
            encoding="utf-8"
        )

        custody_guard = next(
            task
            for task in runbook["pre_tasks"]
            if task["name"] == "Enforce Vault-only public certificate custody"
        )
        assertions = custody_guard["ansible.builtin.assert"]["that"]
        normalized_assertions = {" ".join(assertion.split()) for assertion in assertions}
        self.assertIn(
            "nginx_config_tls_source | default('', true) == 'vault'",
            normalized_assertions,
        )
        self.assertIn(
            "not ( nginx_config_vault_allow_local_fallback | default(true) | bool )",
            normalized_assertions,
        )
        self.assertIn("vault_secret_bundle_generate_missing: false", source)
        for key in ("ca_certificate", "client_certificate", "private_key"):
            self.assertIn(f"name: {key}", source)

    def test_management_services_always_close_scoped_vault_transport(self):
        runbook = load_yaml(RUNBOOK_DIRECTORY / "30-management-services.yml")[-1]

        lifecycle = next(
            task
            for task in runbook["tasks"]
            if task["name"]
            == "Execute the management-service lifecycle through scoped Vault access"
        )
        lifecycle_tasks = lifecycle["block"]
        lifecycle_cleanup = lifecycle["always"]

        self.assertEqual(
            lifecycle_tasks[0]["name"],
            "Resolve scoped controller HashiCorp Vault authentication",
        )
        self.assertEqual(
            lifecycle_tasks[0]["ansible.builtin.include_tasks"],
            "../../00-common/tasks/resolve-hashicorp-vault-auth.yml",
        )
        self.assertEqual(
            lifecycle_cleanup[-1]["ansible.builtin.include_tasks"],
            "../../00-common/tasks/close-hashicorp-vault-ssh-tunnel.yml",
        )
        self.assertEqual(
            lifecycle_cleanup[0]["ansible.builtin.set_fact"][
                "_hetzner_hashicorp_vault_auth"
            ],
            {},
        )
        for task in (lifecycle_tasks[0], lifecycle_cleanup[-1]):
            include_path = task["ansible.builtin.include_tasks"]
            self.assertTrue((RUNBOOK_DIRECTORY / include_path).resolve().is_file())

    def test_keycloak_target_does_not_resolve_disabled_netbox_secret(self):
        runbook = load_yaml(RUNBOOK_DIRECTORY / "30-management-services.yml")[-1]
        lifecycle = next(
            task
            for task in runbook["tasks"]
            if task["name"]
            == "Execute the management-service lifecycle through scoped Vault access"
        )
        lifecycle_tasks = {task["name"]: task for task in lifecycle["block"]}

        for name in (
            "Resolve NetBox OIDC client secret from Vault",
            "Capture the NetBox OIDC client secret bundle",
        ):
            with self.subTest(task=name):
                self.assertEqual(
                    lifecycle_tasks[name]["when"],
                    "_wunderbox_management_selected in ['netbox', 'all']",
                )
                self.assertEqual(
                    set(lifecycle_tasks[name]["tags"]), {"netbox", "sso"}
                )

        self.assertNotIn(
            "_wunderbox_management_selected in ['keycloak', 'netbox', 'all']",
            (RUNBOOK_DIRECTORY / "30-management-services.yml").read_text(
                encoding="utf-8"
            ),
        )

    def test_management_tls_custody_separates_issuer_and_kv_approles(self):
        path = RUNBOOK_DIRECTORY / "20-management-tls-custody.yml"
        play = load_yaml(path)[0]
        source = path.read_text(encoding="utf-8")
        apply_source = (
            RUNBOOK_DIRECTORY / "tasks/apply-management-tls-custody.yml"
        ).read_text(encoding="utf-8")
        normalized_apply_source = " ".join(apply_source.split())
        readback_source = (
            RUNBOOK_DIRECTORY / "tasks/readback-management-tls-custody.yml"
        ).read_text(encoding="utf-8")

        self.assertEqual(play["hosts"], "hetzner_baremetal")
        self.assertEqual(play["serial"], 1)
        self.assertIs(play["any_errors_fatal"], True)
        self.assertIs(play["gather_facts"], False)
        for required in (
            "APPLY-WUNDERBOX-MANAGEMENT-TLS:",
            "hetzner_baremetal_vault.pki_controller_auth",
            "hetzner_baremetal_vault.controller_auth",
            "_management_tls_candidate_sha256",
            "_management_tls_candidate_schema_version: 2",
            "custody_schema_version: \"{{ _management_tls_custody_schema_version }}\"",
            "exact_pki_ca_endpoints",
            "Forget short-lived Vault tokens",
            "close-hashicorp-vault-ssh-tunnel.yml",
        ):
            self.assertIn(required, source)
        self.assertIn("options:", apply_source)
        self.assertIn("cas:", apply_source)
        self.assertIn(".get('data', {})", apply_source)
        self.assertIn(".get('metadata', {})", apply_source)
        self.assertIn("private_key:", apply_source)
        self.assertIn(
            "_management_tls_existing_data.schema_version | default(0) | int",
            apply_source,
        )
        self.assertIn(
            "_management_tls_existing_data.ca_chain_source | default('')",
            apply_source,
        )
        self.assertIn(
            "_management_tls_existing_data.root_mount | default('')",
            apply_source,
        )
        self.assertIn(
            "_management_tls_existing_data.ca_chain | select('string') "
            "| map('trim') | reject('equalto', '') | list | length ) == 2",
            normalized_apply_source,
        )
        self.assertIn(
            "_management_tls_issued_ca_chain | select('string') | map('trim') "
            "| reject('equalto', '') | list | length == 2",
            normalized_apply_source,
        )
        self.assertIn(
            "_management_tls_existing_data.alt_names is sequence",
            normalized_apply_source,
        )
        self.assertIn(
            "_management_tls_existing_data.alt_names is not string",
            normalized_apply_source,
        )
        self.assertIn(
            'schema_version: "{{ _management_tls_custody_schema_version }}"',
            apply_source,
        )
        self.assertIn("no_log: true", apply_source)
        self.assertIn(
            "Read the exact public intermediate certificate for custody",
            apply_source,
        )
        self.assertIn(
            "Read the exact public root certificate for custody",
            apply_source,
        )
        self.assertIn(
            'ca_chain: "{{ _management_tls_issued_ca_chain }}"',
            apply_source,
        )
        self.assertIn(
            'ca_chain_source: "{{ _management_tls_contract.ca_chain_source }}"',
            apply_source,
        )
        self.assertIn(
            "_management_tls_stored.root_mount == _management_tls_contract.root_mount",
            readback_source,
        )
        self.assertIn(
            "== _management_tls_custody_schema_version",
            readback_source,
        )
        self.assertNotIn("issued TLS contract diagnostics", apply_source)
        self.assertIn("== ['deny']", readback_source)
        capability_guard = next(
            task
            for task in load_yaml(
                RUNBOOK_DIRECTORY / "tasks/readback-management-tls-custody.yml"
            )
            if task["name"] == "Require separated issuer and custody capabilities"
        )
        capability_assertions = capability_guard["ansible.builtin.assert"]["that"]
        for path_variable in (
            "_management_tls_issue_path",
            "_management_tls_kv_data_path",
            "_management_tls_kv_metadata_path",
        ):
            matching_assertions = [
                assertion
                for assertion in capability_assertions
                if path_variable in assertion
            ]
            self.assertGreaterEqual(len(matching_assertions), 1)
            self.assertTrue(
                all("| default([])" in assertion for assertion in matching_assertions)
            )
        self.assertIn("issuer_and_custody_capabilities_separated: true", readback_source)
        self.assertIn("public_key_fingerprints.sha256", readback_source)

        management_source = (RUNBOOK_DIRECTORY / "30-management-services.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "not (nginx_config_vault_issue_missing | default(true) | bool)",
            management_source,
        )
        self.assertIn(
            "must already be present in Vault KV before gateway deploy",
            management_source,
        )
        self.assertIn("* 86400 < _management_tls_contract.ttl_seconds", source)
        for field in ("pki_mount", "pki_role", "kv_mount", "kv_path"):
            self.assertIn(
                f"_management_tls_contract.{field} | default('')",
                source,
            )
        normalized_management_source = " ".join(management_source.split())
        self.assertNotIn(
            "public_tls_material_present_in_vault', false ) is sameas true or",
            normalized_management_source,
        )

    def test_management_guards_default_missing_inventory_contracts(self):
        for name in (
            "30-management-services.yml",
            "31-management-backup.yml",
            "33-management-acceptance.yml",
        ):
            with self.subTest(runbook=name):
                source = (RUNBOOK_DIRECTORY / name).read_text(encoding="utf-8")
                self.assertIn(
                    "wunderbox_goal07_management_services | default({})", source
                )
                self.assertIn("'external_prerequisites'", source)
                self.assertIn("is mapping", source)
                self.assertNotIn(
                    "wunderbox_goal07_management_services.external_prerequisites.",
                    source,
                )
                if name == "31-management-backup.yml":
                    self.assertNotIn("wunderbox_management_backup.", source)
                    for key in (
                        "backup_dir",
                        "database",
                        "database_user",
                        "container",
                    ):
                        self.assertNotIn(
                            f"_management_backup_contract.{key}", source
                        )

    def test_management_acceptance_verifies_vault_tls_files_and_identity(self):
        source = (RUNBOOK_DIRECTORY / "33-management-acceptance.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("Vault-only private-key custody", source)
        self.assertIn("stat.mode == '0600'", source)
        self.assertIn("-checkend", source)
        self.assertIn("-checkhost", source)
        self.assertIn("Verify NGINX certificate and private key match", source)

    def test_management_acceptance_verifies_vault_mtls_files_and_identity(self):
        source = (RUNBOOK_DIRECTORY / "33-management-acceptance.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("Require Vault-backed Alloy mTLS files", source)
        self.assertIn("atlas_loki_mtls_material_present_in_vault", source)
        self.assertIn("Verify Alloy client certificate against its Vault CA bundle", source)
        self.assertIn("Verify Alloy client certificate and private key match", source)


if __name__ == "__main__":
    unittest.main()
