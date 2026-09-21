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
logging and disk fact caching, and emits only the Ansible return code. A failed
or timed-out Apply is not proof that no remote changes occurred: follow the
runbook's rollback/readback procedure, not an automatic retry.

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
