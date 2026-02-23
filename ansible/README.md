# Ansible automation

This repo uses `scripts/ansible-nav` as a container wrapper that runs
`ansible-navigator` and related commands in the toolbox image, so **ansible-navigator is not required** on the host.

Execution modes:

- `ansible-nav`: host wrapper (starts toolbox container via Podman/Docker).
- `ansible-nav-local`: in-container runner (executes `ansible-navigator` directly, no nested container runtime).

---

## Quick Start

### 1) Install collections (choose one mode)

`./scripts/ansible-nav run ...` auto-installs base collections from
`collections/requirements.yml` by default.
If `RH_AUTOMATION_HUB_TOKEN` is set and `collections/requirements-rh.yml` exists,
it is selected automatically instead.
Default is `ANSIBLE_TOOLBOX_AUTO_COLLECTIONS=true`; set
`ANSIBLE_TOOLBOX_AUTO_COLLECTIONS=false` to disable bootstrap.

Base dependencies only:

```bash
./scripts/ansible-nav exec -- \
  ansible-galaxy collection install -r /runner/project/collections/requirements.yml \
  -p /runner/project/collections --force
```

Local collection overlays only (`ansible-collection-*` repos):
run this after base dependencies are already installed.

```bash
./scripts/install-local-collections
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

### 4) Image-only execution (no git clone of modulix repo)

If you only have the toolbox image and mount your local Ansible workspace, use
`ansible-nav-local` directly inside the container:

```bash
podman run --rm -it \
  --userns keep-id \
  --security-opt label=disable \
  -v "$PWD":/runner/project:Z \
  -w /runner/project \
  -v "$HOME/.ssh:/runner/.ssh:ro,Z" \
  -e HOME=/runner \
  -e ANSIBLE_CONFIG=/runner/project/ansible.cfg \
  quay.io/l-it/ee-wunder-toolbox-ubi9:v1.1.0 \
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

2) Local collection overlays only:

```bash
./scripts/install-local-collections
```

Only selected local collections:

```bash
./scripts/install-local-collections foundational rhel
```

This script only builds and installs local `ansible-collection-*` repos.

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

`scripts/ansible-nav` runs the toolbox image directly via Podman or Docker and executes `ansible-navigator` inside the container.
Default image:
- `quay.io/l-it/ee-wunder-toolbox-ubi9:v1.1.0`

In-container usage:
- `ansible-nav-local` executes `ansible-navigator` directly.
- `ansible-nav` auto-falls back to `ansible-nav-local` when run inside a container without Podman/Docker.

Wrapper behavior (`scripts/ansible-nav`):
- When a container API socket exists (`/var/run/docker.sock`, `/run/docker.sock`, or `/run/user/$UID/podman/podman.sock`), it is mounted to `/var/run/docker.sock` in the execution environment.
- External inventories are auto-mounted from `../../ansible-inventory-lit/inventories` to `/runner/project/inventories` when available.
- When inventory mount is active, `-i inventories/...` is automatically rewritten to `/runner/project/inventories/...` for execution environment compatibility.
- Host SSH directory is auto-mounted from `~/.ssh` to `/runner/.ssh` so inventory paths like `/runner/.ssh/id_ed25519` work inside the execution environment.
- Host `SSH_AUTH_SOCK` is auto-mounted to `/runner/ssh-agent.sock` and exported in-container.
- Runs with host UID/GID and sets `HOME=/runner`.

Inventory mount controls:
- `ANSIBLE_TOOLBOX_MOUNT_INVENTORIES=auto|true|false` (default: `auto`)
- `ANSIBLE_TOOLBOX_INVENTORY_SOURCE=/path/to/inventories`

SSH mount controls:
- `ANSIBLE_TOOLBOX_MOUNT_SSH=auto|true|false` (default: `auto`)
- `ANSIBLE_TOOLBOX_SSH_SOURCE=/path/to/.ssh`
- `ANSIBLE_TOOLBOX_MOUNT_SSH_AGENT=auto|true|false` (default: `auto`)

Image/engine controls:
- `ANSIBLE_TOOLBOX_ENGINE=auto|podman|docker` (default: `auto`)
- `ANSIBLE_TOOLBOX_IMAGE=<image:tag>` (default: `quay.io/l-it/ee-wunder-toolbox-ubi9:v1.1.0`)
- `ANSIBLE_TOOLBOX_PULL_POLICY=missing|always|never` (default: `missing`)
- `ANSIBLE_TOOLBOX_NAV_MODE=stdout|interactive` (default: `stdout`)
- `ANSIBLE_TOOLBOX_NAV_EE_ENABLED=true|false` (default: `false`)
- `ANSIBLE_TOOLBOX_NAV_CACHE_DIR=/tmp/.cache` (default: `/tmp/.cache`)
- `ANSIBLE_TOOLBOX_NAV_COLLECTION_DOC_CACHE_PATH=/tmp/.cache/ansible-navigator/collection_doc_cache.db`

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
