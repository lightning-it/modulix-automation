# run-modulix.sh

```bash
export INVENTORY_DIR=/home/rene/sources/ansible-inventory-lit/inventories
export VAULT_PASS_FILE=/home/rene/sources/modulix-automation/ansible/.vault-pass.txt
test -s "$VAULT_PASS_FILE"  # required: Ansible Vault password file (.vault-pass.txt)
```

```bash
export VAULT_TOKEN="$(
  /home/rene/sources/modulix-automation/scripts/modulix/run-modulix.sh --inventory "$INVENTORY_DIR" vault root-token
)"
```

```bash
/home/rene/sources/modulix-automation/scripts/modulix/run-modulix.sh --inventory "$INVENTORY_DIR" services wunderbox \
  -i inventories/corp/inventory.yml --limit <HOST>
```

```bash
/home/rene/sources/modulix-automation/scripts/modulix/run-modulix.sh --inventory "$INVENTORY_DIR" services wunderbox --rebuild \
  -i inventories/corp/inventory.yml --limit <HOST>
```

```bash
/home/rene/sources/modulix-automation/scripts/modulix/run-modulix.sh --inventory "$INVENTORY_DIR" services aap \
  -i inventories/corp/inventory.yml --limit <HOST>
```

```bash
/home/rene/sources/modulix-automation/scripts/modulix/run-modulix.sh --inventory "$INVENTORY_DIR" services aap --rebuild \
  -i inventories/corp/inventory.yml --limit <HOST>
```
