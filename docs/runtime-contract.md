# Runtime Contract

This document defines the canonical execution contract for ModuLix automation releases.

## Primary entrypoint

- Wrapper: `ansible/scripts/ansible-nav`
- Subcommands:
  - `run <playbook.yml> [ansible-navigator run args...]`
  - `exec -- <command> [args...]`

## Default runtime behavior

- Runs inside toolbox container image:
  - default `ANSIBLE_TOOLBOX_IMAGE=quay.io/l-it/ee-wunder-toolbox-ubi9:v1.4.0`
- `ansible-navigator run` is always executed with `--ee true`.
- Collections are resolved from `ANSIBLE_COLLECTIONS_PATH` with local project overlays first.
- `ansible/scripts/ansible-nav-local run` bootstraps collections by default
  (`ANSIBLE_TOOLBOX_AUTO_COLLECTIONS=true`).
- Default requirements profile: `ansible/collections/requirements.yml`.
- If `RH_AUTOMATION_HUB_TOKEN` is set and `ansible/collections/requirements-rh.yml`
  exists, that RH profile is selected automatically.

## Runtime options

Supported wrapper options (environment variables):

- `ANSIBLE_TOOLBOX_ENGINE=auto|podman|docker`
- `ANSIBLE_TOOLBOX_IMAGE=<image:tag>`
- `ANSIBLE_TOOLBOX_PULL_POLICY=missing|always|never`
- `ANSIBLE_TOOLBOX_NAV_MODE=stdout|interactive`
- `ANSIBLE_TOOLBOX_MOUNT_INVENTORIES=auto|true|false`
- `ANSIBLE_TOOLBOX_INVENTORY_SOURCE=/path/to/inventories`
- `ANSIBLE_TOOLBOX_MOUNT_SSH=auto|true|false`
- `ANSIBLE_TOOLBOX_SSH_SOURCE=/path/to/.ssh`
- `ANSIBLE_TOOLBOX_MOUNT_SSH_AGENT=auto|true|false`

## Required runtime inputs

Depending on playbook:

- inventory (`-i ...`)
- SSH key material (`~/.ssh` and/or ssh-agent)
- secrets (`ANSIBLE_VAULT_PASSWORD_FILE`, `VAULT_TOKEN`, etc.)

## Host-native execution (optional)

Host-native execution is allowed, but the operator must provide equivalent prerequisites:

- compatible `ansible-core`/`ansible-navigator`
- required Ansible collections
- equivalent secret and SSH handling

The containerized wrapper remains the default supported path.
