# Ansible automation

This repo uses `scripts/ansible-nav` as a container wrapper:
- toolbox image for wrapper/utility execution
- nested ansible EE image for playbook `run` via Podman in toolbox
Host installation of `ansible-navigator` is not required.

Execution modes:

- `ansible-nav`: host wrapper (starts toolbox container via Podman/Docker).
- `ansible-nav-local`: in-container runner (executes `ansible-navigator` directly).

---

## Quick Start

### 1) Install collections (choose one mode)

Base dependencies only:

```bash
./scripts/ansible-nav exec -- \
  ansible-galaxy collection install -r /runner/project/collections/requirements.yml \
  -p /runner/project/collections --force
```

Local collection development mode (`ansible-collection-*` repos):
builds local collections, applies optional workspace overlays from
`collections/requirements.yml` (non-`lit.*` entries), and resolves
collection dependencies from each collection `galaxy.yml`.

```bash
./scripts/install-local-collections
```

RH extension collections (single public EE model):

```bash
RH_HUB_TOKEN=<token> ./scripts/install-rh-collections
```

### 2) Run a full Wunderbox rebuild

```bash
./scripts/ansible-nav run playbooks/services/01-wunderbox-rebuild.yml \
  -i inventories/corp/inventory.yml --limit wunderbox01.prd.dmz.corp.l-it.io
```

### 3) Run a single playbook

```bash
./scripts/ansible-nav run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit wunderbox01.prd.dmz.corp.l-it.io
```

For full workflows and all variants, see `How-To`.

### 4) Manual nested execution from toolbox image (optional)

If you only have the toolbox image and mount your local Ansible workspace, use
`ansible-nav-local` directly inside the container:

```bash
podman run --rm -it \
  --privileged \
  --security-opt label=disable \
  --user 0:0 \
  -v "$PWD":/runner/project:Z \
  -w /runner/project \
  -v "$HOME/.ssh:/runner/.ssh:ro,Z" \
  -e HOME=/runner \
  -e ANSIBLE_CONFIG=/runner/project/ansible.cfg \
  -e ANSIBLE_TOOLBOX_NAV_EE_ENABLED=true \
  -e ANSIBLE_TOOLBOX_NAV_CONTAINER_ENGINE=podman \
  -e ANSIBLE_TOOLBOX_NAV_EE_IMAGE=quay.io/l-it/ee-wunder-ansible-ubi9:v1.9.3 \
  quay.io/l-it/ee-wunder-toolbox-ubi9:v1.5.0 \
  ansible-nav-local run playbooks/stage-2b/13-aap.yml \
  -i inventories/corp/inventory.yml --limit aap01.prd.dmz.corp.l-it.io
```

---

## How-To

### Use the runtime wrapper

Default usage:

```bash
./scripts/ansible-nav run <playbook.yml> -i inventories/corp/inventory.yml --limit <host-or-group>
```

Force engine when needed:

```bash
ANSIBLE_TOOLBOX_ENGINE=podman ./scripts/ansible-nav run ...
ANSIBLE_TOOLBOX_ENGINE=docker ./scripts/ansible-nav run ...
```

### Install collections

Choose one install mode:

1) Base dependencies only (no local collection development):

```bash
./scripts/ansible-nav exec -- \
  ansible-galaxy collection install -r /runner/project/collections/requirements.yml \
  -p /runner/project/collections --force
```

2) Local collection development mode (dependencies + local overlays):

```bash
./scripts/install-local-collections
```

3) RH extension collections at runtime (single public EE model):

```bash
RH_HUB_TOKEN=<token> ./scripts/install-rh-collections
```

Only selected local collections:

```bash
./scripts/install-local-collections foundational rhel
```

Dependency resolution source of truth in local mode:

- Collection dependencies: each local collection `galaxy.yml`
- Workspace overlays: `collections/requirements.yml` (non-`lit.*` only)
- RH extension overlays: `collections/requirements-rh.yml` (Automation Hub source)

Disable workspace overlays when needed:

```bash
REQUIREMENTS_FILE= ./scripts/install-local-collections
```

### Run playbooks

00 Gateway (baremetal+RHEL9) setup:

```bash
./scripts/ansible-nav run playbooks/stage-1/infrastructure-platform-baremetal/01-oob-virtualmedia-install.yml \
  -i inventories/corp/inventory.yml --limit gw01.prd.edge.pub.l-it.io

./scripts/ansible-nav run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit gw01.prd.edge.pub.l-it.io

./scripts/ansible-nav run playbooks/stage-2b/01-gateway.yml \
  -i inventories/corp/inventory.yml --limit gw01.prd.edge.pub.l-it.io
```

01 vSphere ESXi setup:

```bash
./scripts/ansible-nav run playbooks/stage-1/infrastructure-platform-vsphere/01-esxi-os_install.yml \
  -i inventories/corp/inventory.yml --limit vsphere_esxi

./scripts/ansible-nav run playbooks/stage-1/infrastructure-platform-vsphere/02-esxi-setup.yml \
  -i inventories/corp/inventory.yml --limit vsphere_esxi
```

02 vSphere vCenter setup:

```bash
./scripts/ansible-nav run playbooks/stage-1/infrastructure-platform-vsphere/FIXME \
  -i inventories/corp/inventory.yml --limit vcenter-com.mgmt.corp.l-it.io
```

10 Firewall (VM+RHEL9) setup:

10.1 DMZ

```bash
./scripts/ansible-nav run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.dmz.corp.l-it.io

./scripts/ansible-nav run playbooks/stage-2b/10-firewall.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.dmz.corp.l-it.io
```

10.2 COM

```bash
./scripts/ansible-nav run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.com.corp.l-it.io

./scripts/ansible-nav run playbooks/stage-2b/10-firewall.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.com.corp.l-it.io
```

10.3 INT

```bash
./scripts/ansible-nav run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.int.corp.l-it.io

./scripts/ansible-nav run playbooks/stage-2b/10-firewall.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.int.corp.l-it.io
```

10.4 ISO

```bash
./scripts/ansible-nav run playbooks/stage-1/infrastructure-platform-vsphere/20-vm-template.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.iso.corp.l-it.io

./scripts/ansible-nav run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.iso.corp.l-it.io

./scripts/ansible-nav run playbooks/stage-2b/10-firewall.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.iso.corp.l-it.io
```

20 Workstations (VM+RHEL9) setup:

20.1 DMZ

```bash
./scripts/ansible-nav run playbooks/stage-1/infrastructure-platform-vsphere/20-vm-template.yml \
  -i inventories/corp/inventory.yml --limit workstation01.prd.dmz.corp.l-it.io

./scripts/ansible-nav run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit workstation01.prd.dmz.corp.l-it.io

./scripts/ansible-nav run playbooks/stage-2b/11-workstation.yml \
  -i inventories/corp/inventory.yml --limit workstation01.prd.dmz.corp.l-it.io
```

21 Wunderbox (VM+RHEL9) setup:

```bash
./scripts/ansible-nav run playbooks/stage-1/infrastructure-platform-vsphere/90-vm-destroy.yml \
  -i inventories/corp/inventory.yml --limit wunderbox01.prd.dmz.corp.l-it.io

./scripts/ansible-nav run playbooks/stage-1/infrastructure-platform-vsphere/20-vm-template.yml \
  -i inventories/corp/inventory.yml --limit wunderbox01.prd.dmz.corp.l-it.io

./scripts/ansible-nav run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit wunderbox01.prd.dmz.corp.l-it.io

./scripts/ansible-nav run playbooks/stage-2b/12-wunderbox.yml \
  -i inventories/corp/inventory.yml --limit wunderbox01.prd.dmz.corp.l-it.io
```

21.1 Wunderbox rebuild (single pipeline playbook):

```bash
./scripts/ansible-nav run playbooks/services/01-wunderbox-rebuild.yml \
  -i inventories/corp/inventory.yml --limit wunderbox01.prd.dmz.corp.l-it.io
```

22 AAP (VM+RHEL9) setup:

```bash
./scripts/ansible-nav run playbooks/stage-1/infrastructure-platform-vsphere/90-vm-destroy.yml \
  -i inventories/corp/inventory.yml --limit aap01.prd.dmz.corp.l-it.io

./scripts/ansible-nav run playbooks/stage-1/infrastructure-platform-vsphere/20-vm-template.yml \
  -i inventories/corp/inventory.yml --limit aap01.prd.dmz.corp.l-it.io

./scripts/ansible-nav run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit aap01.prd.dmz.corp.l-it.io

./scripts/ansible-nav run playbooks/stage-2b/13-aap.yml \
  -i inventories/corp/inventory.yml --limit aap01.prd.dmz.corp.l-it.io
```

22.1 AAP rebuild (single pipeline playbook):

```bash
./scripts/ansible-nav run playbooks/services/02-aap-rebuild.yml \
  -i inventories/corp/inventory.yml --limit aap01.prd.dmz.corp.l-it.io
```

---

## Knowledge Base

### Runtime wrapper details

`scripts/ansible-nav` runs the toolbox image directly via Podman or Docker.
Default image:
- `quay.io/l-it/ee-wunder-toolbox-ubi9:v1.5.0`

In-container usage:
- `ansible-nav-local` executes `ansible-navigator` directly.

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

Inventory mount controls:
- `ANSIBLE_TOOLBOX_MOUNT_INVENTORIES=auto|true|false` (default: `auto`)
- `ANSIBLE_TOOLBOX_INVENTORY_SOURCE=/path/to/inventories`

SSH mount controls:
- `ANSIBLE_TOOLBOX_MOUNT_SSH=auto|true|false` (default: `auto`)
- `ANSIBLE_TOOLBOX_SSH_SOURCE=/path/to/.ssh`
- `ANSIBLE_TOOLBOX_MOUNT_SSH_AGENT=auto|true|false` (default: `auto`)

Image/engine controls:
- `ANSIBLE_TOOLBOX_ENGINE=auto|podman|docker` (default: `auto`)
- `ANSIBLE_TOOLBOX_IMAGE=<image:tag>` (default: `quay.io/l-it/ee-wunder-toolbox-ubi9:v1.5.0`)
- `ANSIBLE_TOOLBOX_RUN_EE_IMAGE=<image:tag>` (default: `quay.io/l-it/ee-wunder-ansible-ubi9:v1.9.3`)
- `ANSIBLE_TOOLBOX_PULL_POLICY=missing|always|never` (default: `missing`)
- `ANSIBLE_TOOLBOX_NAV_MODE=stdout|interactive` (default: `stdout`)
- `ANSIBLE_TOOLBOX_NAV_EE_IMAGE=<image:tag>` (default: ansible-navigator config image)
- `ANSIBLE_TOOLBOX_NAV_CACHE_DIR=/tmp/.cache` (default: `/tmp/.cache`)
- `ANSIBLE_TOOLBOX_NAV_COLLECTION_DOC_CACHE_PATH=/tmp/.cache/ansible-navigator/collection_doc_cache.db`
- `ANSIBLE_TOOLBOX_RH_COLLECTIONS_MODE=auto|always|never` (default: `auto`)
- `ANSIBLE_TOOLBOX_RH_COLLECTIONS_STRICT=true|false` (default: `true`)
- `ANSIBLE_TOOLBOX_RH_COLLECTIONS_REQUIREMENTS=./collections/requirements-rh.yml`
- `ANSIBLE_TOOLBOX_RH_COLLECTIONS_TARGET=./collections-dev`
- `RH_COLLECTIONS_USE=true|false` (default: `true`)

Automation Hub env inputs:
- `RH_HUB_TOKEN` (preferred)
- `AUTOMATION_HUB_TOKEN` (fallback)
- `RH_AUTOMATION_HUB_TOKEN` (fallback)
- `AUTOMATION_HUB_GALAXY_SERVER` (optional override, default:
  `https://console.redhat.com/api/automation-hub/content/published/`)

Notes:
- `RH_AUTOMATION_HUB_TOKEN` offline tokens are used via Automation Hub `auth_url` flow.

### Vault + Nexus notes

The Vault bootstrap writes its init output to the target only. The repo must not store secrets.

Recommended flow:
- First run (`vault_bootstrap`): Vault init runs on the target; the init payload is kept in memory for unseal and root token, and the encrypted init file is written to the target.
- Subsequent runs: unseal/root token come from vaulted inventory vars (`vault_init.*`, e.g. `group_vars/wunderboxes/vault-init.yml`). The playbooks do not read the encrypted init file on the target.
- `vault_config` creates AppRole roles and stores credentials in Vault KV at:
  - `stage-2c/<inventory_hostname>/nexus/approle-kv`
  - `stage-2c/<inventory_hostname>/nexus/approle-pki`
- `nexus` reads AppRole credentials from those KV paths at runtime. It needs `VAULT_TOKEN` with read access.

Best practice: use a short-lived, least-privilege token for KV read + PKI issue, not a root token.

### Inventory and roles

- Inventory: `inventories/corp/inventory.yml`
- Roles path: `./roles` (set in `ansible.cfg`)
- Adjust vars in `group_vars/` and `host_vars/` as needed.

### Secrets

- **Do not commit secrets.**
- Use:
  - Ansible Vault (`ANSIBLE_VAULT_PASSWORD_FILE`)
  - SOPS or your preferred secret store
