# ModuLix helper scripts

Helper scripts for day-to-day automation in this repository.

## Layout

```text
scripts/
  ansible-nav
  github/clone-all.sh
  wunder-devtools-ee.sh
  test-ansible.sh
ansible/scripts/
  ansible-nav
  install-local-collections
  install-rh-collections
```

## Requirements

- `git`
- `gh` (GitHub CLI) for `scripts/github/clone-all.sh`
- `podman` or `docker` for containerized helper workflows

## Quick usage

Clone all repositories from a GitHub owner:

```bash
./scripts/github/clone-all.sh <owner> [options]
./scripts/github/clone-all.sh lightning-it --ssh --target-dir ~/sources
```

Run pre-commit inside the devtools container:

```bash
mkdir -p "$HOME/.cache/pre-commit"
systemctl --user enable --now podman.socket
SOCK="/run/user/$(id -u)/podman/podman.sock"
REPO="$PWD"

podman run --rm \
  --userns keep-id \
  --user "$(id -u):$(id -g)" \
  --security-opt label=disable \
  -v "$REPO":"$REPO":z \
  -v "$HOME/.cache":"$HOME/.cache":z \
  -v "$SOCK":"$SOCK" \
  -w "$REPO" \
  -e XDG_CACHE_HOME="$HOME/.cache" \
  -e PRE_COMMIT_HOME="$HOME/.cache/pre-commit" \
  -e DOCKER_HOST="unix://$SOCK" \
  -e GIT_CONFIG_COUNT=1 \
  -e GIT_CONFIG_KEY_0=safe.directory \
  -e GIT_CONFIG_VALUE_0="$REPO" \
  quay.io/l-it/ee-wunder-devtools-ubi9:latest \
  pre-commit run --all-files
```

Run basic ansible sanity checks:

```bash
./scripts/test-ansible.sh
```

Run ansible-navigator wrapper from repository root:

```bash
./scripts/ansible-nav run playbooks/services/02-aap-rebuild.yml -i inventories/corp/inventory.yml --limit <host>
```

Behavior note:
- Docker-based hooks require access to a container API socket in the runtime where `pre-commit` executes.
