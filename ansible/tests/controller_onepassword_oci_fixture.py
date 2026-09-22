"""Synthetic OCI integration fixture; run as the container's PID 1.

Mount the repository read-only at /source and an empty public-evidence directory
at /evidence. Execute with the pinned EE's Python and either success or wait.
No credentials, host agent, network or container-engine socket are required.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fixture", ROOT / "tests/wunderbox/test_controller_onepassword.py"
)
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)

if os.getpid() != 1 or sys.argv[1:] not in (["success"], ["wait"]):
    raise SystemExit("fixture requires PID 1 and success/wait mode")

root = Path(tempfile.mkdtemp(prefix="controller-oci-", dir="/tmp"))
secrets = root / ".secrets"
secrets.mkdir(mode=0o700)
ca = secrets / "ca.crt"
ca.write_bytes(
    re.search(
        rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
        Path("/etc/pki/tls/certs/ca-bundle.crt").read_bytes(),
        re.S,
    ).group(0)
)
ca.chmod(0o600)
contract, item = fixture.fixture()
contract["onepassword"]["ca_sha256"] = hashlib.sha256(ca.read_bytes()).hexdigest()
note = json.loads(item["fields"][0]["value"])
note["secret_id"] = "{{ synthetic_undefined }}=literal"
item["fields"][0]["value"] = json.dumps(note)

plugins = root / "lookup_plugins"
plugins.mkdir(mode=0o700)
(plugins / "fixture_detach.py").write_text("""
import os,time
from pathlib import Path
from ansible.plugins.lookup import LookupBase
class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        fd=int(os.environ['LIT_CONTROLLER_ONEPASSWORD_FD'])
        reader,writer=os.pipe()
        if os.fork()==0:
            os.close(reader)
            os.setsid()
            assert os.pread(fd,1,0)==b'{'
            Path('/evidence/detached').write_text('synthetic descriptor readable')
            os.write(writer,b'1')
            os.close(writer)
            count=0
            while True:
                Path('/evidence/heartbeat').write_text(str(count))
                count+=1
                time.sleep(0.1)
        os.close(writer)
        assert os.read(reader,1)==b'1'
        os.close(reader)
        return ['ready']
""")
play = root / "fixture.yml"
tasks = [
    {
        "ansible.builtin.set_fact": {
            "memory": "{{ query('lit_controller_onepassword', contract, ca_path=ca, project_root=root) | first }}"
        },
        "no_log": True,
    },
    {
        "ansible.builtin.assert": {
            "that": [
                "memory.role_id == 'synthetic-role-000000000'",
                "memory.secret_id | b64encode == expected_secret_b64",
                "lookup('ansible.builtin.env', 'SSH_AUTH_SOCK') == ''",
                "lookup('ansible.builtin.env', 'HOME') != '/untrusted/home'",
                "query('fixture_detach') | first == 'ready'",
            ]
        },
        "no_log": True,
    },
]
if sys.argv[1] == "wait":
    tasks.append({"ansible.builtin.pause": {"seconds": 30}})
import base64

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
                    "expected_secret_b64": base64.b64encode(
                        note["secret_id"].encode()
                    ).decode(),
                },
                "tasks": tasks,
            }
        ]
    )
)
fakebin = root / "fake-bin"
fakebin.mkdir()
fake = fakebin / "ansible-playbook"
fake.write_text("#!/bin/sh\nexit 97\n")
fake.chmod(0o700)
reader, writer = os.pipe()
os.write(writer, json.dumps(item).encode())
os.close(writer)
os.dup2(reader, 0)
os.close(reader)
environment = dict(
    os.environ,
    PATH=str(fakebin),
    HOME="/untrusted/home",
    SSH_AUTH_SOCK="/untrusted/agent",
)
# Ansible also discovers playbook-adjacent plugins. Make the fixture project
# explicit instead of depending on that implicit search behavior or image cwd.
os.chdir(root)
os.execve(
    "/opt/app-root/bin/python3",
    [
        "/opt/app-root/bin/python3",
        "-I",
        str(ROOT / "lookup_plugins/lit_controller_onepassword.py"),
        "--",
        "-i",
        "localhost,",
        "-c",
        "local",
        str(play),
    ],
    environment,
)
