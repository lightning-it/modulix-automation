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
    """Prevent a return to the missing, unqualified Squid role stub."""

    def test_all_proxy_entrypoints_use_the_same_protected_role(self):
        for path in RUNBOOKS:
            with self.subTest(path=path):
                play = yaml.safe_load(path.read_text(encoding="utf-8"))[0]
                self.assertEqual(play["hosts"], "forward_proxies")
                self.assertIs(play["become"], True)
                self.assertIs(play["any_errors_fatal"], True)
                self.assertEqual(play["serial"], 1)
                self.assertEqual(len(play["roles"]), 1)
                role = play["roles"][0]
                self.assertEqual(role["role"], "lit.ubuntu.forward_proxy")
                self.assertIs(role["forward_proxy_enabled"], True)

    def test_unqualified_squid_role_is_absent(self):
        for path in RUNBOOKS:
            with self.subTest(path=path):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("role: squid", source)


if __name__ == "__main__":
    unittest.main()
