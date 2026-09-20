"""Static contract for the standard LIT forward-proxy orchestration."""

from pathlib import Path
import unittest

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUNBOOKS = (
    REPOSITORY_ROOT / "ansible" / "runbooks" / "20-network" / "proxy" / "10-squid.yml",
    REPOSITORY_ROOT
    / "ansible"
    / "playbooks"
    / "stage-2b"
    / "core-tenant"
    / "20-proxy-setup.yml",
)


class ForwardProxyOrchestrationTests(unittest.TestCase):
    """Keep the portable service and Ubuntu client adapter ordered together."""

    def test_all_proxy_entrypoints_use_the_same_protected_role(self):
        for path in RUNBOOKS:
            with self.subTest(path=path):
                plays = yaml.safe_load(path.read_text(encoding="utf-8"))
                self.assertEqual(len(plays), 2)
                preflight, play = plays
                self.assertEqual(preflight["hosts"], "all:localhost")
                self.assertEqual(preflight["connection"], "local")
                self.assertIs(preflight["become"], False)
                self.assertIs(preflight["gather_facts"], False)
                self.assertIs(preflight["any_errors_fatal"], True)
                self.assertEqual(len(preflight["tasks"]), 1)
                preflight_task = preflight["tasks"][0]
                self.assertEqual(preflight_task["delegate_to"], "localhost")
                self.assertIs(preflight_task["run_once"], True)
                preflight_assertions = preflight_task[
                    "ansible.builtin.assert"
                ]["that"]
                self.assertIn("forward_proxy_target_host is defined", preflight_assertions)
                self.assertIn("ansible_limit is defined", preflight_assertions)
                self.assertIn(
                    "forward_proxy_limit_hosts | length == 2",
                    preflight_assertions,
                )
                self.assertTrue(
                    any(
                        "in groups.get('forward_proxies', [])" in assertion
                        for assertion in preflight_assertions
                    )
                )
                self.assertTrue(
                    any(
                        "['localhost', forward_proxy_target_host_effective]"
                        in assertion
                        for assertion in preflight_assertions
                    )
                )
                self.assertEqual(play["hosts"], "forward_proxies")
                self.assertIs(play["become"], True)
                self.assertIs(play["any_errors_fatal"], True)
                self.assertEqual(play["serial"], 1)
                self.assertEqual(len(play["pre_tasks"]), 2)
                guard, plan_stop = play["pre_tasks"]
                assertions = guard["ansible.builtin.assert"]["that"]
                self.assertIn("ansible_limit is defined", assertions)
                self.assertTrue(
                    any(
                        "['localhost', inventory_hostname]" in assertion
                        for assertion in assertions
                    )
                )
                self.assertTrue(
                    any(
                        "forward_proxy_target_host" in assertion
                        and "inventory_hostname" in assertion
                        for assertion in assertions
                    )
                )
                self.assertIn("ansible_play_hosts_all | length == 1", assertions)
                self.assertIn(
                    "ansible_play_hosts_all == [inventory_hostname]", assertions
                )
                self.assertEqual(plan_stop["ansible.builtin.meta"], "end_play")
                self.assertEqual(
                    plan_stop["when"],
                    "forward_proxy_orchestration_action | default('plan') == 'plan'",
                )
                self.assertEqual(len(play["roles"]), 2)
                service_role, client_role = play["roles"]
                self.assertEqual(service_role["role"], "lit.supplementary.forward_proxy")
                self.assertIs(service_role["forward_proxy_enabled"], True)
                self.assertEqual(client_role["role"], "lit.ubuntu.forward_proxy_client")
                self.assertIs(client_role["forward_proxy_client_enabled"], True)

    def test_unqualified_squid_role_is_absent(self):
        for path in RUNBOOKS:
            with self.subTest(path=path):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("role: squid", source)


if __name__ == "__main__":
    unittest.main()
