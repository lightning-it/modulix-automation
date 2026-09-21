# Controller AppRole from an existing 1Password item

The default backend remains `ansible_vault`, with the original encrypted-file
checks unchanged. `hashicorp_vault_controller_auth.backend: onepassword_memory`
is an explicit alternative for a trusted desktop-to-Linux-EE transport. There is
no automatic fallback or credential generation.

The trusted outer transport selects the approved 1Password account, vault and
immutable item using the existing desktop CLI. It sends exactly one JSON item
over stdin to `ansible/lookup_plugins/lit_controller_onepassword.py` in the pinned
Linux execution environment. Public `ansible-playbook` arguments follow `--`.
Do not paste item JSON into a terminal, command argument, environment value or
file. The outer transport must validate its CLI/account identity, capture errors
without secret output, and never retry a mutating playbook automatically.

The launcher creates a sealed, owner-bound anonymous memory descriptor and
inherits only its numeric handle into Ansible. It uses the dedicated
`controller-onepassword.cfg` profile (no legacy password file), disables secret
logging and disk fact caching, and emits only the Ansible return code. It builds
the child environment from an explicit public-runtime allowlist, never ambient
1Password, Vault, cloud or loader credentials. The child has a separate process
group, which is killed on exit, timeout or handled interruption. Run this launcher
as the main process of a one-shot isolated EE: EE teardown also terminates
processes that deliberately create a different session. A failed
or timed-out Apply is not proof that no remote changes occurred: follow the
runbook's rollback/readback procedure, not an automatic retry.

Ambient `SSH_AUTH_SOCK` is dropped by default. Only when the selected trusted
playbook requires managed SSH may the trusted outer transport explicitly pass
`--ssh-agent-socket /runner/agent -- <public playbook arguments>` to the launcher.
The path must be absolute, canonical, a Unix socket owned by the execution UID,
and inaccessible to group/other users. Mount the existing agent at that exact
path; do not export a private key. The socket is revalidated before launch and
grants agent use to the entire trusted Ansible invocation, not individual tasks.
Do not use this profile to isolate mutually untrusted playbook tasks. Keep the
existing inventory-pinned identity and strict host checks; remote forwarding
remains disabled.

The backup runbook closes its caller-owned Vault tunnel in an `always` section
immediately after collecting credentials, including resolver/read failures.
AppRole authentication is not backup encryption custody: the backup runbook
still requires its existing Ansible Vault password-file contract and now rejects
missing custody before any secret read or database dump. This memory-only
launcher deliberately does not supply that separate backup encryption key.

The controller contract retains schema, subject, AppRole name and auth mount.
Its `onepassword` mapping must contain exactly `item_id`, `vault_id`,
`item_version` (positive integer), `item_title` and `ca_sha256`. The item must be
the exact Secure Note and contain one JSON `notesPlain` field with the matching
schema/subject/auth method/role/mount plus the existing `role_id` and `secret_id`.
Duplicate JSON keys, ambiguous notes, drift, unsealed input and template-bearing
credential values fail closed. The public CA must be the exact hash-pinned,
protected non-symlink file beneath the canonical project `.secrets` directory.
Mount the project, plugins and CA read-only in the execution environment.

HTTPS verification, the existing inventory-bound SSH tunnel, single-host guards,
deployment gates and caller-owned tunnel cleanup remain mandatory. Selecting a
credential backend does not approve deployment or relax those gates. This
backend neither installs 1Password in the container nor mounts an engine socket.
Environment-specific item IDs, invocations and evidence belong in the private
operations repository, not in this generic public documentation.
