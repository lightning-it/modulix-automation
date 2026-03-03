# Ansible automation

This repo uses **ansible-navigator** with the **Wunder devtools execution environment** to avoid local
tooling dependencies.

---

## ansible-navigator configuration

The bundled `ansible-navigator.yml` config:
- Enables the execution environment via Docker
- Uses `quay.io/l-it/ee-wunder-ansible-ubi9:v1.7.0`
- (Optional) mounts the Docker socket for roles that need it
- Passes `ANSIBLE_CONFIG` and `ANSIBLE_VAULT_PASSWORD_FILE`
- Disables playbook artifacts and uses stdout mode

---

## Prerequisites: Ansible Collections

Playbooks in this repository depend on additional Ansible Collections (e.g. `lit.foundational`).
They must be installed into the local vendor directory **before** running playbooks:

### Install / update required collections

```bash
ansible-navigator exec -- \
  ansible-galaxy collection install -r /runner/project/collections/requirements.yml \
  -p /runner/project/collections-dev --force
```

### Initial inventory setup
```bash
ansible-navigator run init-inventory.yml -e g_inventory_version=<BRANCH> -e github_token=<PAT>
```

---

## Running playbooks

00 Gateway (baremetal+RHEL9) setup:

```bash
ansible-navigator run playbooks/stage-1/infrastructure-platform-baremetal/01-oob-virtualmedia-install.yml \
  -i inventories/corp/inventory.yml --limit gw01.prd.edge.pub.l-it.io

ansible-navigator run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit gw01.prd.edge.pub.l-it.io

ansible-navigator run playbooks/stage-2b/01-gateway.yml \
  -i inventories/corp/inventory.yml --limit gw01.prd.edge.pub.l-it.io
```

01 vSphere ESXi setup:

```bash
ansible-navigator run playbooks/stage-1/infrastructure-platform-vsphere/01-esxi-os_install.yml \
  -i inventories/corp/inventory.yml --limit vsphere_esxi

ansible-navigator run playbooks/stage-1/infrastructure-platform-vsphere/02-esxi-setup.yml \
  -i inventories/corp/inventory.yml --limit vsphere_esxi
```

02 vSphere vCenter setup:

```bash
ansible-navigator run playbooks/stage-1/infrastructure-platform-vsphere/FIXME \
  -i inventories/corp/inventory.yml --limit vcenter-com.mgmt.corp.l-it.io
```

10 Firewall (VM+RHEL9) setup:

10.1 DMZ

```bash
ansible-navigator run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.dmz.corp.l-it.io

ansible-navigator run playbooks/stage-2b/10-firewall.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.dmz.corp.l-it.io
```

10.2 COM

```bash
ansible-navigator run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.com.corp.l-it.io

ansible-navigator run playbooks/stage-2b/10-firewall.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.com.corp.l-it.io
```

10.3 INT

```bash
ansible-navigator run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.int.corp.l-it.io

ansible-navigator run playbooks/stage-2b/10-firewall.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.int.corp.l-it.io
```

10.4 ISO

```bash
ansible-navigator run playbooks/stage-1/infrastructure-platform-vsphere/20-vm-template.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.iso.corp.l-it.io

ansible-navigator run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.iso.corp.l-it.io

ansible-navigator run playbooks/stage-2b/10-firewall.yml \
  -i inventories/corp/inventory.yml --limit fw01.prd.iso.corp.l-it.io
```

20 Workstations(VM+RHEL9) setup:

20.1 DMZ

```bash
ansible-navigator run playbooks/stage-1/infrastructure-platform-vsphere/20-vm-template.yml \
  -i inventories/corp/inventory.yml --limit workstation01.prd.dmz.corp.l-it.io

ansible-navigator run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit workstation01.prd.dmz.corp.l-it.io

ansible-navigator run playbooks/stage-2b/11-workstation.yml \
  -i inventories/corp/inventory.yml --limit workstation01.prd.dmz.corp.l-it.io
```

21 Wunderbox(VM+RHEL9) setup:

```bash
ansible-navigator run playbooks/stage-1/infrastructure-platform-vsphere/90-vm-destroy.yml \
  -i inventories/corp/inventory.yml --limit wunderbox01.prd.dmz.corp.l-it.io

ansible-navigator run playbooks/stage-1/infrastructure-platform-vsphere/20-vm-template.yml \
  -i inventories/corp/inventory.yml --limit wunderbox01.prd.dmz.corp.l-it.io

ansible-navigator run playbooks/stage-2a/traditional-operating-systems/rhel9/01-base-setup.yml \
  -i inventories/corp/inventory.yml --limit wunderbox01.prd.dmz.corp.l-it.io

ansible-navigator run playbooks/stage-2b/12-wunderbox.yml \
  -i inventories/corp/inventory.yml --limit wunderbox01.prd.dmz.corp.l-it.io
```

---

## Vault + Nexus notes

The Vault bootstrap writes its init output to the target only. The repo must not store secrets.

Recommended flow:
- First run (`vault_bootstrap`): Vault init runs on the target; the init payload is kept in memory for unseal and
  root token, and the encrypted init file is written to the target.
- Subsequent runs: unseal/root token come from vaulted inventory vars (`vault_init.*`, e.g.
  `group_vars/wunderboxes/vault-init.yml`). The playbooks do not read the encrypted init file on the target.
- `vault_config` creates AppRole roles and stores credentials in Vault KV at:
  - `stage-2c/<inventory_hostname>/nexus/approle-kv`
  - `stage-2c/<inventory_hostname>/nexus/approle-pki`
- `nexus` reads AppRole credentials from those KV paths at runtime. It needs `VAULT_TOKEN` with read access.

Best practice: use a short‑lived, least‑privilege token for KV read + PKI issue, not a root token.

```bash
ansible-navigator run playbooks/stage-2b/12-wunderbox.yml -i inventories/corp/inventory.yml --limit wunderbox02.prd.dmz.corp.l-it.io -t vault
```

## Inventory and roles

- Inventory: `inventories/corp/inventory.yml`
- Roles path: `./roles` (set in `ansible.cfg`)
- Adjust vars in `group_vars/` and `host_vars/` as needed.

---

## OCP

### Install
```bash
VAULT_TOKEN=$(cat $HOME/.vault-token) ansible-navigator run playbooks/stage-2c/container-platform-ocp4/20-ocp-install.yml -i inventories/corp/inventory.yml -l ocp -e install_agent_hashi_vault_auth_method=token
```

### GitOps
```bash
VAULT_TOKEN=$(cat $HOME/.vault-token) ansible-navigator run playbooks/stage-2c/container-platform-ocp4/21-post-install.yml -i inventories/corp/inventory.yml -l ocp -e install_agent_hashi_vault_auth_method=token -e approve_all=true
```

### Destroy
```bash
VAULT_TOKEN=$(cat $HOME/.vault-token) ansible-navigator run playbooks/stage-2c/container-platform-ocp4/99-ocp-destroy.yml -i inventories/corp/inventory.yml -l ocp -e install_agent_hashi_vault_auth_method=token
```

---

## Secrets

- **Do not commit secrets.**
- Use:
  - Ansible Vault (`ANSIBLE_VAULT_PASSWORD_FILE`)
  - SOPS or your preferred secret store
