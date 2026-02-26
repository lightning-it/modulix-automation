# run-modulix scripts

## Overview

Use `run-modulix.sh` to run Modulix automation playbooks from published container images.
It mounts the current directory as the runtime workspace.
It uses an inventory, a Vault password file, an SSH agent, and registry auth during execution.

## Preparation

`run-modulix.sh` uses published images on `quay.io`.

```bash
export INVENTORY_DIR="$PWD/ansible-inventory-lit/inventories"
export VAULT_PASS_FILE="$PWD/.vault-pass.txt"
export AUTHFILE="$PWD/.podman-auth.json"
[[ -s "$VAULT_PASS_FILE" ]] || { echo "ERROR: missing or empty Vault password file: $VAULT_PASS_FILE" >&2; false; }
```

```bash
# required for SSH: forward your running ssh-agent
test -n "$SSH_AUTH_SOCK"
test -S "$SSH_AUTH_SOCK"
ssh-add -L
```

```bash
# one-time (or when token changed): create authfile and authenticate outside the script
mkdir -p "$(dirname "$AUTHFILE")"
rm -f "$AUTHFILE"  # remove invalid/empty file if present
podman login --authfile "$AUTHFILE" quay.io
chmod 600 "$AUTHFILE"
```

```bash
# only after initial Vault setup/bootstrap is completed
export VAULT_TOKEN="$(
  ./run-modulix.sh --inventory "$INVENTORY_DIR" vault root-token
)"
```

## Execution

```bash
./run-modulix.sh --inventory "$INVENTORY_DIR" services wunderbox \
  -i inventories/corp/inventory.yml --limit <HOST>
```

```bash
./run-modulix.sh --inventory "$INVENTORY_DIR" services wunderbox --rebuild \
  -i inventories/corp/inventory.yml --limit <HOST>
```

```bash
./run-modulix.sh --inventory "$INVENTORY_DIR" services aap \
  -i inventories/corp/inventory.yml --limit <HOST>
```

```bash
./run-modulix.sh --inventory "$INVENTORY_DIR" services aap --rebuild \
  -i inventories/corp/inventory.yml --limit <HOST>
```
