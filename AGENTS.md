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
  quay.io/l-it/ee-wunder-devtools-ubi9:v1.6.0 \
  pre-commit run --all-files
```

### 2) Run RPM parse/build checks in container

```bash
podman run --rm \
  --security-opt label=disable \
  -v "$PWD":/workspace:Z \
  -w /workspace \
  quay.io/l-it/ee-wunder-devtools-ubi9:v1.6.0 \
  bash -lc 'set -euo pipefail; rpmspec -P packaging/rpm/modulix-automation-runtime.spec >/tmp/modulix.spec.out; ./packaging/rpm/build-srpm.sh --version 0.1.0 --release 1'
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
