# Controller AppRole from an existing 1Password item

The default backend remains `ansible_vault`. Its existing encrypted-document
checks are retained, with an added password-custody preflight before opening
the tunnel and shared cleanup of backend-specific credential facts afterward.
These are intentional lifecycle changes, not byte-for-byte preservation.
`hashicorp_vault_controller_auth.backend: onepassword_memory`
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
the child environment from fixed settings, never ambient PATH, HOME, 1Password,
Vault, cloud or loader values. It uses the pinned EE's absolute executable
`/opt/app-root/bin/ansible-playbook`, a fixed system PATH and a new private
HOME/TMPDIR per invocation, preventing user-home plugin discovery.
The launcher rejects execution unless it is Linux PID 1 with parent PID 0,
before reading stdin or allocating credential memory. Launch with the pinned
EE's `/opt/app-root/bin/python3 -I` directly (or a wrapper that uses `exec`), in
a private PID namespace: no `--init`/tini, `--pid=host` or `podman exec`.
On success, error, timeout or handled interruption the launcher exits; Linux
then kills every remaining process in its namespace, including `setsid()`
descendants. Process-group cleanup also retires ordinary workers promptly.
The source/project must be read-only and approved; this is not an isolation
boundary against malicious playbooks or another process with the same UID.
A failed
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
The shared selector clears backend-specific intermediate facts on both success
and failure. Consumers use only `_hetzner_hashicorp_vault_auth`; the shared
transport close lifecycle clears this output and both intermediate facts before
attempting socket removal, including for OS, TLS, migration and recovery callers.
The Raft snapshot caller uses the same backend-neutral authentication contract.
AppRole authentication is not backup encryption custody: the backup runbook
still requires its existing Ansible Vault password-file contract. A shared
validator used by both legacy authentication and backup checks canonical,
symlink-free protected parent directories, a distinct readable regular file,
root/controller ownership, single link, 0400/0600 mode, and 1-byte-to-1-MiB size.
Backup validates before secret reads/dumps. At encryption the helper opens and
validates the password again and reads only that exact open descriptor. The
pinned Ansible Vault library encrypts in the same helper process, with core dumps
disabled: no child process can retain an inherited password handle. The backup
runbook invokes the trusted running controller's `ansible_playbook_python` with
`-I`, not a PATH lookup or a hard-coded image filesystem path. The memory-profile
launcher itself still uses its explicitly pinned EE executable contract.
The backup
file is also opened descriptor-relatively without following symlinks in its
private directory and written through that descriptor, with mode 0600. Replacing
the password pathname or its parent cannot redirect that read. The early metadata
lookup is only a preflight, not a promise about a later pathname open. The
legacy backend still uses Ansible's initially loaded Vault secret; its added
metadata preflight does not replace that existing decryption mechanism.
The metadata validator never reads the password value. The encryptor reads it
only in process memory, never into logs or a new credential file. This memory-only
launcher deliberately does not supply that separate backup encryption key.

The controller contract retains schema, subject, AppRole name and auth mount.
Its `onepassword` mapping must contain exactly `item_id`, `vault_id`,
`item_version` (positive integer), `item_title` and `ca_sha256`. The item must be
the exact Secure Note and contain one JSON `notesPlain` field with the matching
schema/subject/auth method/role/mount plus the existing `role_id` and `secret_id`.
Duplicate JSON keys, ambiguous notes, drift and unsealed input fail closed.
AppRole strings retain the existing 16–4096-character, no-CR/LF contract,
including punctuation such as `=`. They are explicitly Ansible-unsafe data;
template-looking credential text is passed literally, never evaluated.
The public CA must be the exact hash-pinned,
protected non-symlink file beneath the canonical project `.secrets` directory.
Mount the project, plugins and CA read-only in the execution environment.

HTTPS verification, the existing inventory-bound SSH tunnel, single-host guards,
deployment gates and caller-owned tunnel cleanup remain mandatory. Selecting a
credential backend does not approve deployment or relax those gates. This
backend neither installs 1Password in the container nor mounts an engine socket.
Environment-specific item IDs, invocations and evidence belong in the private
operations repository, not in this generic public documentation.
