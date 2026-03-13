# Agent Instructions

## Mandatory validation gate (containerized)

Before finishing any change in this repository, run a full validation pass in
the devtools container. Do not rely on host-installed tooling.

### 1) Run pre-commit (includes YAML lint and inventory checks)

```bash
podman run --rm \
  --security-opt label=disable \
  --userns keep-id \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e GIT_CONFIG_COUNT=1 \
  -e GIT_CONFIG_KEY_0=safe.directory \
  -e GIT_CONFIG_VALUE_0=/workspace \
  -v "$PWD":/workspace:Z \
  -w /workspace \
  quay.io/l-it/ee-wunder-devtools-ubi9:v1.8.1 \
  pre-commit run --all-files
```

### 2) Run RPM parse/build checks in container

```bash
podman run --rm \
  --security-opt label=disable \
  -v "$PWD":/workspace:Z \
  -w /workspace \
  quay.io/l-it/ee-wunder-devtools-ubi9:v1.8.1 \
  bash -lc 'set -euo pipefail; tmpdir=$(mktemp -d); cp -a /workspace/. "$tmpdir"/; cd "$tmpdir"; rpmspec -P packaging/rpm/modulix-automation-runtime.spec >/tmp/modulix.spec.out; ./packaging/rpm/build-srpm.sh --version 0.1.0 --release 1; cp -f packaging/rpm/dist/*.src.rpm /workspace/packaging/rpm/dist/'
```

## RPM validation fallback

When host tooling is missing for RPM checks, do not stop at a local limitation.

- If `rpmspec` and/or `rpmbuild` are not available on the host, run RPM parse/build
  validation in the devtools container first.
- If the devtools image itself lacks `rpmspec`/`rpmbuild`, document that result and
  continue with an RPM-capable containerized fallback (for example Fedora + `rpm-build`).
- Only report a limitation after the devtools-container path has been attempted.
- Avoid statements like:
  - `Could not run RPM parse/build locally because rpmspec/rpmbuild are not installed in this environment.`
  without also documenting the devtools-container attempt and result.

## Playbook Design Default (Inventory-Driven)

For stage playbooks (for example `ansible/playbooks/stage-2b/12-wunderbox.yml`), default behavior MUST be inventory-driven.

1. Playbooks SHOULD orchestrate roles, not implement business/configuration logic that belongs in inventory or roles.
2. Service enablement MUST come from inventory toggles (`services.<group>.*` and/or `wunderbox_service_*` overrides).
3. Service configuration values (endpoints, ports, credentials, DB settings, host mappings) MUST come from inventory/group vars/host vars.
4. Playbooks MUST NOT silently generate environment-specific defaults for service credentials or topology.
5. Cross-service wiring SHOULD be expressed as inventory variables (or role defaults that map inventory inputs), not large `set_fact`/fallback blocks in playbooks.
6. If values are required, fail fast with clear assertions instead of deriving hidden defaults in playbook code.
