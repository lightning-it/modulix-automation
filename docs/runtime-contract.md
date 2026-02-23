# Runtime Contract

This document defines the canonical execution contract for ModuLix automation releases.

## Primary entrypoint

- Wrapper: `ansible/scripts/ansible-nav`
- Subcommands:
  - `run <playbook.yml> [playbook args...]`
  - `exec -- <command> [args...]`

## Default runtime behavior

- Runs inside toolbox container image:
  - default `ANSIBLE_TOOLBOX_IMAGE=quay.io/l-it/ee-wunder-toolbox-ubi9:v1.5.0`
- Host container engine can be `podman` or `docker` (`ANSIBLE_TOOLBOX_ENGINE`).
- `run` always executes in nested mode:
  - toolbox container runs `ansible-nav-local`
  - `ansible-nav-local` runs `ansible-navigator` with execution environment enabled
  - inner execution environment container engine is fixed to `podman`
  - toolbox run-mode starts privileged as root to enable nested podman
- Playbook runtime image:
  - default `ANSIBLE_TOOLBOX_RUN_EE_IMAGE=quay.io/l-it/ee-wunder-ansible-ubi9:v1.9.3`
- Base collections come from the configured run EE image and local workspace overlays.
- For AAP runs, RH extension collections can be prepared at runtime before playbook execution.

## Runtime options

Supported wrapper options (environment variables):

- `ANSIBLE_TOOLBOX_ENGINE=auto|podman|docker`
- `ANSIBLE_TOOLBOX_IMAGE=<image:tag>`
- `ANSIBLE_TOOLBOX_RUN_EE_IMAGE=<image:tag>`
- `ANSIBLE_TOOLBOX_PULL_POLICY=missing|always|never`
- `ANSIBLE_TOOLBOX_NAV_MODE=stdout|interactive`
- `ANSIBLE_TOOLBOX_NAV_EE_IMAGE=<image:tag>` (optional override for `ansible-nav-local`)
- `ANSIBLE_TOOLBOX_MOUNT_INVENTORIES=auto|true|false`
- `ANSIBLE_TOOLBOX_INVENTORY_SOURCE=/path/to/inventories`
- `ANSIBLE_TOOLBOX_MOUNT_SSH=auto|true|false`
- `ANSIBLE_TOOLBOX_SSH_SOURCE=/path/to/.ssh`
- `ANSIBLE_TOOLBOX_MOUNT_SSH_AGENT=auto|true|false`
- `ANSIBLE_TOOLBOX_RH_COLLECTIONS_MODE=auto|always|never`
- `ANSIBLE_TOOLBOX_RH_COLLECTIONS_STRICT=true|false`
- `ANSIBLE_TOOLBOX_RH_COLLECTIONS_REQUIREMENTS=./collections/requirements-rh.yml`
- `ANSIBLE_TOOLBOX_RH_COLLECTIONS_TARGET=./collections-dev`
- `RH_COLLECTIONS_USE=true|false`

## Required runtime inputs

Depending on playbook:

- inventory (`-i ...`)
- SSH key material (`~/.ssh` and/or ssh-agent)
- secrets (`ANSIBLE_VAULT_PASSWORD_FILE`, `VAULT_TOKEN`, etc.)
- for AAP/CaC execution with `requirements-rh.yml`: `RH_HUB_TOKEN` (preferred), `AUTOMATION_HUB_TOKEN`, or `RH_AUTOMATION_HUB_TOKEN`
  - offline token values are used via Automation Hub `auth_url` flow

## Host-native execution (optional)

Host-native execution is allowed, but the operator must provide equivalent prerequisites:

- compatible `ansible-core`/`ansible-navigator`
- required Ansible collections
- equivalent secret and SSH handling

The containerized wrapper remains the default supported path.
