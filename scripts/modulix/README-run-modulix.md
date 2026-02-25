# run-modulix scripts

Playbooks are executed from the container image.

```bash
export INVENTORY_DIR="$PWD/ansible-inventory-lit/inventories"
export VAULT_PASS_FILE="$PWD/.vault-pass.txt"
test -s "$VAULT_PASS_FILE"  # required: Ansible Vault password file (.vault-pass.txt)
```

`run-modulix.sh` uses published images on `quay.io`.

```bash
export VAULT_TOKEN="$(
  ./run-modulix.sh --inventory "$INVENTORY_DIR" vault root-token
)"
```

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
