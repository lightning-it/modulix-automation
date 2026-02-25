# run-modulix scripts

Playbooks are executed from the container image. Only inventory, vault password file, SSH auth, and optional AAP bundle are mounted from host.

```bash
export INVENTORY_DIR="$PWD/ansible-inventory-lit/inventories"
export VAULT_PASS_FILE="$PWD/.vault-pass.txt"
test -s "$VAULT_PASS_FILE"  # required: Ansible Vault password file (.vault-pass.txt)
```

`run-modulix.sh` defaults to published images on `quay.io`.

`run-modulix-local.sh` defaults to local images:

```bash
podman build --format docker \
  -t localhost/ee-wunder-toolbox-ubi9:local-modulix-rpmtest \
  /home/rene/sources/container-ee-wunder-toolbox-ubi9
```

```bash
podman build --format docker \
  --build-arg COLLECTION_PROFILE=certified \
  -t localhost/ee-wunder-ansible-ubi9-certified:local-modulix-rpmtest \
  /home/rene/sources/container-ee-wunder-ansible-ubi9
```

```bash
# optional for AAP: bundle is auto-mounted from $PWD if file exists
ls -1 ansible-automation-platform-containerized-setup-bundle-*.tar.gz
```

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

```bash
./run-modulix-local.sh --inventory "$INVENTORY_DIR" services aap \
  -i inventories/corp/inventory.yml --limit <HOST>
```

```bash
./run-modulix-local.sh --inventory "$INVENTORY_DIR" services wunderbox \
  -i inventories/corp/inventory.yml --limit <HOST>
```
