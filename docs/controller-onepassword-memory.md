# Controller AppRole from an existing 1Password item

The default backend remains `ansible_vault`. Its existing encrypted-document
checks are retained, with an added password-custody preflight before opening
the tunnel and shared cleanup of backend-specific credential facts afterward.
The normal and AAP-local execution profiles both discover the project lookup
plugins without relying on an ambient lookup-plugin environment override.
These are intentional lifecycle changes, not byte-for-byte preservation.
`hashicorp_vault_controller_auth.backend: onepassword_memory`
is an explicit alternative for a trusted desktop-to-Linux-EE transport. There is
no automatic fallback or credential generation.
The memory resolver rejects a simultaneously configured Ansible Vault password
file or identity list (environment or active Ansible configuration). Select the
dedicated password-file-free profile; the legacy backend's separate backup-key
contract is not a fallback credential source for this memory profile.

The trusted outer transport selects the approved 1Password account, vault and
immutable item using the existing desktop CLI. It sends exactly one JSON item
over stdin to `ansible/lookup_plugins/lit_controller_onepassword.py` in the pinned
Linux execution environment. Public `ansible-playbook` arguments follow `--`.
Do not paste item JSON into a terminal, command argument, environment value or
file. The outer transport must validate its CLI/account identity, capture errors
without secret output, and never retry a mutating playbook automatically.
Input is limited to 1 MiB and must reach EOF within 30 seconds; a stalled or
oversized producer fails before credential-memory allocation or Ansible launch.
The memory profile retains the normal profile's collection search locations and
explicitly disables controller output and target syslog of task arguments.

The launcher creates a sealed, owner-bound anonymous memory descriptor and
inherits only its numeric handle into Ansible. It uses the dedicated
`controller-onepassword.cfg` profile (no legacy password file), disables secret
logging and disk fact caching, and emits only redacted JSON status metadata:
the Ansible return code and secret-output flag, or a generic launch-stopped
marker on failure. It never emits subprocess output or credential contents. It builds
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
The TLS custody caller also clears its own copied authentication mappings and
secret-bearing Vault responses before closing the transport, even on failure.
The Raft snapshot caller uses the same backend-neutral authentication contract.
AppRole authentication is not backup encryption custody: the backup runbook
still requires its existing Ansible Vault password-file contract. A shared
validator used by both legacy authentication and backup checks canonical,
symlink-free protected parent directories, a distinct readable regular file,
root/controller ownership, single link, 0400/0600 mode, and 1-byte-to-1-MiB size.
It also rejects empty/whitespace-only key material before any secret read/dump.
The controller action reads and pins that key through the checked descriptor,
closes it before invoking the remote module, and exclusively reserves a
new 0600 output in a no-follow private directory before reading the remote dump.
The outer backup lifecycle clears database, Object Storage and secret-bundle
response facts in an always block, including failures after transport closure.
The remote bounded reader accepts an explicit inventory
`wunderbox_management_backup.max_dump_bytes` limit between 1 and 67108864 bytes
(64 MiB); no implicit capacity default is used. Its descriptor-based read stops
at limit+1 even if the file grows after stat, rejecting oversized dumps before
returning their payload. Multiple hardlinks are rejected before and after read.
Remote dump parent directories are traversed through held no-follow descriptors;
symlinked ancestors and noncanonical paths are rejected before reading the file.
A final stat of the held descriptor must match the
initial size, modification time and change time, and the read length must match
that size. Changes fail closed; the producer must supply a completed, immutable
dump (this check is not a filesystem snapshot). Encoded and decoded lengths are
checked again on the controller. Operators must size this limit for the actual
controller memory budget (allow at least 20 times the limit as headroom for JSON, base64 and Vault
encryption allocations); larger databases need a separately reviewed streaming
backup path, not a raised hard ceiling or plaintext fallback.
The bounded dump is read into controller memory and encrypted there by the pinned
Ansible Vault library; only ciphertext is written through the reserved descriptor.
No plaintext controller fetch file, secret-bearing module argument, encryption
subprocess or inherited password handle is used. Existing destination files,
hardlinks and symlinks are rejected before the remote read. Failures can leave
an empty or partial ciphertext file for diagnosis, never a plaintext artifact;
there is no automatic retry or pathname-based cleanup of that reserved output.
There is no in-place plaintext-file encryption interface. The obsolete CLI path
is explicitly rejected; all backup encryption uses the ciphertext-only action.
Replacing the password pathname or its parent cannot redirect its read, and
replacing the output parent cannot redirect the checked descriptor's write.
The memory-profile launcher retains its pinned EE executable contract. The early custody
lookup is only a preflight, not a promise about a later pathname open. The
legacy backend still uses Ansible's initially loaded Vault secret; its added
custody preflight does not replace that existing decryption mechanism.
The custody preflight validates both protected file metadata and bounded,
non-empty password material in process memory. The encryptor independently pins
that material before any remote dump read. Neither path writes it to logs or a
new credential file. This memory-only launcher deliberately does not supply that
separate backup encryption key.

The controller contract retains schema, subject, AppRole name and auth mount.
Its `onepassword` mapping must contain exactly `item_id`, `vault_id`,
`item_version` (positive integer), `item_title` and `ca_sha256`. The item must be
the exact Secure Note and contain one JSON `notesPlain` field with the matching
schema/subject/auth method/role/mount plus the existing `role_id` and `secret_id`.
Duplicate JSON keys, non-JSON numeric constants, non-finite numbers, ambiguous
notes, drift and unsealed input fail closed.
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
