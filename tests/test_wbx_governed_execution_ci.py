"""Semantic contract tests for the mandatory governed-execution CI gate."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "wbx-governed-execution-ci.yml"
DEVTOOLS_IMAGE_PATTERN = r"quay\.io/l-it/ee-wunder-devtools-ubi9@sha256:[0-9a-f]{64}"


def strings(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)
    else:
        yield str(value)


class GovernedExecutionWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow_text = WORKFLOW.read_text(encoding="utf-8")
        cls.workflow = yaml.load(cls.workflow_text, Loader=yaml.BaseLoader)
        cls.job = cls.workflow["jobs"]["governed-execution-contract"]
        cls.container = cls.job["container"]
        cls.devtools_image = cls.container["image"]
        cls.steps = {step["name"]: step for step in cls.job["steps"]}

    def test_gate_always_reports_for_pull_requests_and_protected_pushes(self) -> None:
        events = self.workflow["on"]
        self.assertEqual(set(events), {"pull_request", "push"})
        for event in events.values():
            self.assertEqual(event, {"branches": ["develop", "main"]})
            self.assertNotIn("paths", event)
            self.assertNotIn("paths-ignore", event)

    def test_job_identity_runtime_and_permissions_are_exact(self) -> None:
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        self.assertEqual(self.job["name"], "Governed execution contract")
        self.assertEqual(self.job["runs-on"], "ubuntu-24.04")
        self.assertEqual(self.job["timeout-minutes"], "10")
        self.assertEqual(self.job["permissions"], {"contents": "read"})
        self.assertEqual(
            self.container,
            {"image": self.devtools_image, "options": "--user 0:0"},
        )
        self.assertRegex(self.devtools_image, rf"^{DEVTOOLS_IMAGE_PATTERN}$")
        self.assertEqual(
            re.findall(DEVTOOLS_IMAGE_PATTERN, self.workflow_text),
            [self.devtools_image],
        )
        self.assertNotIn("if", self.job)
        self.assertNotIn("continue-on-error", self.job)

    def test_checkout_action_is_immutably_pinned_and_credential_averse(self) -> None:
        checkout = self.steps["Checkout exact candidate"]
        self.assertEqual(
            checkout,
            {
                "name": "Checkout exact candidate",
                "uses": "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                "with": {"persist-credentials": "false"},
            },
        )
        uses = [step["uses"] for step in self.job["steps"] if "uses" in step]
        self.assertEqual(uses, [checkout["uses"]])
        self.assertRegex(
            checkout["uses"],
            r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$",
        )

    def test_every_run_step_is_unconditional_and_fail_closed(self) -> None:
        run_steps = [step for step in self.job["steps"] if "run" in step]
        self.assertEqual(len(run_steps), 3)
        for step in run_steps:
            with self.subTest(step=step["name"]):
                self.assertEqual(step["shell"], "bash")
                self.assertTrue(step["run"].startswith("set -euo pipefail\n"))
                self.assertNotIn("if", step)
                self.assertNotIn("continue-on-error", step)

    def test_syntax_format_and_static_analysis_cover_runtime_components(self) -> None:
        run = self.steps["Validate executable syntax and format"]["run"]
        for command in (
            "python3 -m py_compile",
            "bash -n",
            "black --check",
            "shellcheck",
            "yamllint .github/workflows/wbx-governed-execution-ci.yml",
        ):
            with self.subTest(command=command):
                self.assertIn(command, run)
        for path in (
            "ansible/callback_plugins/lit_governed_evidence.py",
            "ansible/scripts/ansible-nav",
            "ansible/scripts/ansible-nav-local",
            "ansible/scripts/governed-ansible-root-launcher",
            "ansible/scripts/runtime-collection-provenance.py",
            "ansible/tests/test_ansible_nav.sh",
            "ansible/tests/test_ansible_nav_local.sh",
            "scripts/governed-ansible-exec.py",
            "scripts/render-wbx-gate-manifest-template.py",
            "scripts/wbx-governed-exec.py",
            "tests/test_governed_ansible_exec.py",
            "tests/test_governed_runtime_support.py",
            "tests/test_wbx_governed_execution_ci.py",
            "tests/test_wbx_governed_execution_policy.py",
        ):
            with self.subTest(path=path):
                self.assertIn(path, run)

    def test_functional_contract_steps_are_exact(self) -> None:
        recorder = self.steps["Run governed recorder and policy contracts"]["run"]
        wrappers = self.steps["Run execution wrapper contracts"]["run"]
        for command in (
            'private_tmp="$(mktemp -d /root/governed-tests.XXXXXX)"',
            'export TMPDIR="$private_tmp"',
            "/usr/bin/python3.11 tests/test_governed_ansible_exec.py",
            "python3 tests/test_governed_runtime_support.py",
            "/usr/bin/python3.11 tests/test_wbx_governed_execution_policy.py",
            "python3 tests/test_wbx_governed_execution_ci.py",
        ):
            with self.subTest(command=command):
                self.assertIn(command, recorder)
        self.assertIn("ansible/tests/test_ansible_nav.sh", wrappers)
        self.assertIn("ansible/tests/test_ansible_nav_local.sh", wrappers)

    def test_no_secret_or_write_capability_is_declared_anywhere(self) -> None:
        flattened = "\n".join(strings(self.workflow))
        for forbidden in (
            "contents: write",
            "actions: write",
            "checks: write",
            "id-token: write",
            "issues: write",
            "packages: write",
            "pull-requests: write",
            "secrets.",
            "persist-credentials: true",
            "pull_request_target",
            "workflow_run",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, flattened)

    def test_namespace_lifecycle_is_a_real_separate_oci_job(self) -> None:
        job = self.workflow["jobs"]["controller-memory-namespace"]
        self.assertEqual(job["runs-on"], "ubuntu-24.04")
        self.assertEqual(job["timeout-minutes"], "5")
        self.assertEqual(job["permissions"], {"contents": "read"})
        self.assertEqual(job["env"]["CONTROLLER_EE_IMAGE"], self.devtools_image)
        self.assertNotIn("container", job)
        self.assertNotIn("if", job)
        self.assertNotIn("continue-on-error", job)
        self.assertEqual(job["steps"][0], self.steps["Checkout exact candidate"])
        run = job["steps"][1]["run"]
        self.assertTrue(run.startswith("set -euo pipefail\n"))
        self.assertIn('docker pull "$CONTROLLER_EE_IMAGE"', run)
        self.assertIn(
            "bash ansible/tests/test_controller_onepassword_oci.sh docker", run
        )


if __name__ == "__main__":
    unittest.main()
