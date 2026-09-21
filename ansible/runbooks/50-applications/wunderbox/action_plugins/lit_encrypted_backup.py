"""Fetch a dump into controller memory; persist ciphertext only."""

import base64
import importlib.util
from pathlib import Path
import resource

from ansible.plugins.action import ActionBase

HELPER = (
    Path(__file__).resolve().parents[4]
    / "lookup_plugins/lit_controller_vault_password.py"
)
SPEC = importlib.util.spec_from_file_location("lit_backup_custody", HELPER)
CUSTODY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CUSTODY)


class ActionModule(ActionBase):
    TRANSFERS_FILES = False
    _supports_check_mode = False

    def run(self, tmp=None, task_vars=None):
        super().run(tmp, task_vars)
        reserved = False
        try:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            args = self._task.args
            if set(args) != {"src", "dest", "password_file"}:
                raise ValueError("exact backup inputs required")
            # Validate and reserve both descriptors BEFORE any remote read.
            # O_EXCL rejects existing files/symlinks, including hardlinks.
            with CUSTODY.open_protected_file(
                args["password_file"], (args["dest"],)
            ) as password_fd:
                with CUSTODY.open_protected_file(
                    args["dest"], backup=True, create=True
                ) as output_fd:
                    reserved = True
                    fetched = self._execute_module(
                        module_name="ansible.builtin.slurp",
                        module_args={"src": args["src"]},
                        task_vars=task_vars,
                        tmp=tmp,
                    )
                    if fetched.get("failed") or fetched.get("encoding") != "base64":
                        raise ValueError("backup read failed")
                    plaintext = base64.b64decode(fetched["content"], validate=True)
                    CUSTODY.write_encrypted_payload(password_fd, output_fd, plaintext)
            return {"changed": True, "_ansible_no_log": True}
        except Exception:
            # Never return the module response, arguments, plaintext or secrets.
            # A failed new output is empty/partial ciphertext, never plaintext;
            # retain it for diagnosis, without unsafe pathname-based cleanup.
            return {
                "failed": True,
                "changed": reserved,
                "msg": "Protected encrypted backup failed; no automatic retry",
                "_ansible_no_log": True,
            }
