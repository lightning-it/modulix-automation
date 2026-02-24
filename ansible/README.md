# Ansible automation

## Overview

This repo supports two runtime modes:

- As-code mode (`scripts/ansible-nav`): host wrapper that starts the toolbox
  container and runs playbooks in the nested Ansible EE.
- In-container mode (`ansible-nav-local`): run directly inside the toolbox
  container when only container access is available.

In both cases, host installation of `ansible-navigator` is not required.

## Get Started

### As-code mode (`ansible-nav`)

#### 1) Run (collections are handled automatically)

`./scripts/ansible-nav run ...` auto-installs base collections from
`collections/requirements.yml` by default.
If `RH_AUTOMATION_HUB_TOKEN` is set and `collections/requirements-rh.yml` exists,
it is selected automatically instead.

`ANSIBLE_TOOLBOX_AUTO_COLLECTIONS` controls this bootstrap behavior:

- `true` (default): always install collections before `run` (`--force`).
- `auto`: install only when cache is missing or requirements changed.
- `false`: do not install; assume collections are already present.

Use `auto` for faster day-to-day operator runs. Use `true` for strict
reproducibility (for example CI or fresh environments).

For manual collection install modes, see `Tasks` -> `Install collections`.

#### 2) Run a single playbook

```bash
./scripts/ansible-nav run playbooks/<stage-or-service>/<playbook>.yml \
  -i inventories/corp/inventory.yml --limit <host-or-group>
```

#### 3) Run a runbook/service pipeline

```bash
./scripts/ansible-nav run playbooks/services/<service>-rebuild.yml \
  -i inventories/corp/inventory.yml --limit <host-or-group>
```

For full workflows and all variants, see `Tasks`.

### In-container mode (`ansible-nav-local`)

If you only have the toolbox image and mount your local workspace, use
`ansible-nav-local` inside the container:

```bash
podman run --rm -it \
  --privileged \
  --security-opt label=disable \
  --user 0:0 \
  -v "$PWD":/runner/project:Z \
  -w /runner/project \
  -v "$HOME/.ssh:/runner/.ssh:ro,Z" \
  -e HOME=/runner \
  -e ANSIBLE_TOOLBOX_NAV_EE_ENABLED=true \
  quay.io/l-it/ee-wunder-toolbox-ubi9:v1.5.0 \
  ansible-nav-local run playbooks/<stage-or-service>/<playbook>.yml \
  -i inventories/corp/inventory.yml --limit <host-or-group>
```

`ANSIBLE_TOOLBOX_NAV_EE_ENABLED=true` is required in this example because
`ansible-nav-local` defaults to `--ee false`. EE engine/image and `ANSIBLE_CONFIG`
come from `ansible-navigator.yml` unless you override them.

Why these container flags are used in this mode:

- `--privileged`: allows nested container execution when `ansible-navigator` starts
  the inner execution environment container.
- `--security-opt label=disable`: avoids SELinux labeling conflicts for bind mounts
  and nested container access on SELinux hosts.
- `--user 0:0`: runs toolbox as root so nested Podman operations can start reliably.

If you run `ansible-nav-local` with `ANSIBLE_TOOLBOX_NAV_EE_ENABLED=false`, these
flags are usually not required.

---

## Tasks

### As-code mode (`ansible-nav`)

#### Use the runtime wrapper

Default usage:

```bash
./scripts/ansible-nav run <playbook.yml> -i inventories/corp/inventory.yml --limit <host-or-group>
```

Container engine selection is automatic by default. Manual override is documented in `Reference` (`ANSIBLE_TOOLBOX_ENGINE`).

#### Install collections

Choose one install mode:

1) Base dependencies only (runtime path):

```bash
./scripts/ansible-nav exec -- \
  ansible-galaxy collection install -r /runner/project/collections/requirements.yml \
  -p /runner/project/collections --force
```

2) RH extension collections at runtime (single public EE model):

```bash
RH_AUTOMATION_HUB_TOKEN=<token> ./scripts/install-rh-collections
```

#### Internal engineering workflows

This is outside the supported platform operations path.
It is intended for platform engineering teams that develop or extend collections.
For controlled development procedures, see:

- `lcp-docs/30-modulix/50-development/00-index.md`
- `lcp-docs/30-modulix/50-development/01-ansible-collections/10-ansible-collection-development.md`

#### Execute runbooks

Use runbooks as the execution contract for service rollout and rebuild order.
This README documents runtime mechanics (`ansible-nav` and `ansible-nav-local`),
while runbook content and sequencing live in:

- `lcp-docs/30-modulix/30-runbooks/00-index.md`

Execution pattern:

```bash
./scripts/ansible-nav run <runbook-or-service-playbook.yml> \
  -i inventories/corp/inventory.yml --limit <host-or-group>
```

### In-container mode (`ansible-nav-local`)

After starting the toolbox container (see Get Started), use the same playbook
syntax with `ansible-nav-local`:

```bash
ansible-nav-local run <playbook.yml> \
  -i inventories/corp/inventory.yml --limit <host-or-group>
```

---

## Reference

### Execution model

#### As-code mode (`ansible-nav`)

`scripts/ansible-nav` runs the toolbox image directly via Podman or Docker.

Default toolbox image:
- `quay.io/l-it/ee-wunder-toolbox-ubi9:v1.5.0`

Wrapper behavior (`scripts/ansible-nav`):
- External inventories are auto-mounted from `../../ansible-inventory-lit/inventories` to `/runner/project/inventories` when available.
- When inventory mount is active, `-i inventories/...` is automatically rewritten to `/runner/project/inventories/...` for execution environment compatibility.
- Host SSH directory is auto-mounted from `~/.ssh` to `/runner/.ssh` so inventory paths like `/runner/.ssh/id_ed25519` work inside the execution environment.
- Host `SSH_AUTH_SOCK` is auto-mounted to `/runner/ssh-agent.sock` and exported in-container.
- For `exec`, wrapper runs with host UID/GID and sets `HOME=/runner`.
- For `run`, execution is always nested in toolbox:
  - toolbox starts as privileged root to support nested podman.
  - `ansible-nav-local` runs `ansible-navigator` with EE enabled.
  - inner EE container engine is fixed to `podman`.
  - run EE image:
    - `ANSIBLE_TOOLBOX_RUN_EE_IMAGE` (default: `quay.io/l-it/ee-wunder-ansible-ubi9:v1.9.3`).
- For `exec`, when a container API socket exists (`/var/run/docker.sock`, `/run/docker.sock`, or `/run/user/$UID/podman/podman.sock`), it is mounted to `/var/run/docker.sock` in the toolbox container.
- For AAP runs (`playbook path contains "aap"` or `--tags/-t` includes `aap`), wrapper runs
  `scripts/install-rh-collections` automatically before playbook execution when
  `ANSIBLE_TOOLBOX_RH_COLLECTIONS_MODE=auto` (default).

#### In-container mode (`ansible-nav-local`)

- Execute from inside toolbox container.
- `ansible-nav-local` runs `ansible-navigator` directly.
- Use the same playbook paths, inventory flags, and limits as in as-code mode.
- EE defaults are taken from `ansible-navigator.yml`.
- For RH collection profile resolution, provide `RH_AUTOMATION_HUB_TOKEN`.
- Full runtime variable reference: `../docs/runtime-contract.md`.

### Inventory and roles

- Inventory: `inventories/corp/inventory.yml`
- Roles path: `./roles` (set in `ansible.cfg`)
- Adjust vars in `group_vars/` and `host_vars/` as needed.
- Inventory is environment-specific and is not provided as a universal ModuLix baseline.
- Platform teams must define inventory to match their infrastructure and operating context
  (host/group model, network zones, access paths, and required runtime inputs).

## Security

### Secrets flow (Vault/Nexus)

The Vault bootstrap writes its init output to the target only. The repo must not store secrets.

Recommended flow:
- First run (`vault_bootstrap`): Vault init runs on the target; the init payload is kept in memory for unseal and root token, and the encrypted init file is written to the target.
- Subsequent runs: unseal/root token come from vaulted inventory vars (`vault_init.*`, e.g. `group_vars/wunderboxes/vault-init.yml`). The playbooks do not read the encrypted init file on the target.
- `vault_config` creates AppRole roles and stores credentials in Vault KV at:
  - `stage-2c/<inventory_hostname>/nexus/approle-kv`
  - `stage-2c/<inventory_hostname>/nexus/approle-pki`
- `nexus` reads AppRole credentials from those KV paths at runtime. It needs `VAULT_TOKEN` with read access.

Best practice: use a short-lived, least-privilege token for KV read + PKI issue, not a root token.

### Runtime secret inputs

- Required at runtime, depending on playbook:
  - `ANSIBLE_VAULT_PASSWORD_FILE`
  - `VAULT_TOKEN`
- Do not commit secret values to the repository.

## Related Docs

- `../docs/runtime-contract.md`
- `../docs/support-matrix.md`
- `lcp-docs/30-modulix/README.md`
- `lcp-docs/30-modulix/01-overview.md`
- `lcp-docs/30-modulix/02-getting-started.md`
- `lcp-docs/30-modulix/03-automation.md`
- `lcp-docs/30-modulix/04-security.md`
- `lcp-docs/30-modulix/05-patching.md`
- `lcp-docs/30-modulix/20-services/00-index.md`
- `lcp-docs/30-modulix/30-runbooks/00-index.md`
- `lcp-docs/30-modulix/40-containers/00-index.md`
- `lcp-docs/30-modulix/41-rpms/00-index.md`
- `lcp-docs/30-modulix/42-ansible-collections/00-index.md`
- `lcp-docs/30-modulix/90-troubleshooting/00-index.md`
