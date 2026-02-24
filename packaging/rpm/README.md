# modulix-automation-runtime RPM packaging

This directory contains RPM packaging assets for publishing ModuLix scripts as
`modulix-automation-runtime`.

## What gets packaged

- Runtime payload under `/opt/modulix`:
  - `/opt/modulix/scripts`
  - `/opt/modulix/ansible` (playbooks, config, collections requirements, scripts)
  - `/opt/modulix/ansible/inventories` is shipped as a dummy baseline only
    (`example/inventory.yml` with localhost)
- Wrapper commands under `/usr/bin`:
  - `ansible-nav`
  - `ansible-nav-local`
  - `install-local-collections`
  - `clone-all.sh`

Wrappers are used instead of raw symlinks so scripts that rely on
`BASH_SOURCE[0]` still resolve their repository-relative paths correctly.

Environment-specific inventory is not packaged. Provide your target inventory by
mounting it into `/opt/modulix/ansible/inventories` or by updating that path on
the host/toolbox runtime.

## Build SRPM

```bash
packaging/rpm/build-srpm.sh --version 0.1.0 --release 1
```

Output:

- `packaging/rpm/dist/modulix-automation-runtime-<version>-<release>.<dist>.src.rpm`

## Publish to COPR

```bash
COPR_OWNER=<copr-owner> packaging/rpm/publish-copr.sh --create-project
```

or with explicit arguments:

```bash
packaging/rpm/publish-copr.sh \
  --owner <copr-owner> \
  --project modulix \
  --srpm packaging/rpm/dist/modulix-automation-runtime-0.1.0-1.<dist>.src.rpm
```

This `publish-copr.sh` path is a direct SRPM upload fallback.
Preferred for ongoing builds is the webhook-driven SCM workflow below.

## GitHub Actions automation

Workflow: `.github/workflows/rpm-srpm-ci.yml`

- On pull requests touching RPM packaging files:
  - Builds SRPM and uploads it as a workflow artifact.
- On tag push matching `v*`:
  - Builds SRPM and uploads it as a workflow artifact.
  - Publishes the SRPM to COPR (requires `COPR_CONFIG` secret).
  - RPM version is derived from the tag (`v1.2.3` -> `1.2.3`).
- `semantic-release` workflow on `main` can generate these `v*` tags automatically from commit messages.
- On manual `workflow_dispatch`:
  - Builds SRPM with optional overrides:
    - `version`
    - `release`
    - `build_script`
    - `spec_path`
    - `output_dir`
    - `srpm_glob`
    - `artifact_prefix`
  - Does not publish to COPR.

Build script contract for workflow:
- The workflow invokes the configured `build_script` with:
  - `--version <v>`
  - `--release <r>`
  - `--spec <path>`
  - `--output-dir <path>`

Repository settings for COPR publish job:
- Secret:
  - `COPR_CONFIG` (contents of your `~/.config/copr` credentials file)
- Optional repository variables:
  - `COPR_OWNER`
  - `COPR_PROJECT`

## COPR publish via GitHub Webhook (optional)

If you publish through GitHub Actions tag workflow above, the COPR webhook is optional.
Do not enable both mechanisms unless you intentionally want duplicate builds.

Use COPR SCM integration with GitHub webhook as documented:
https://docs.pagure.org/copr.copr/user_documentation.html#github-webhooks

1. In COPR, create package `modulix-automation-runtime` with source type `SCM`.
2. Set clone URL to this repository.
3. Set build method to `make srpm` (uses `.copr/Makefile`).
4. Enable auto-rebuild.
5. In COPR project `Settings` -> `Integrations`, copy the GitHub webhook URL.
6. In GitHub repo `Settings` -> `Webhooks`, create webhook:
   - Payload URL: COPR webhook URL
   - Content type: `application/json`
   - Events: branch or tag creation (or all pushes, based on your policy)

Notes:
- `.copr/Makefile` runs `packaging/rpm/build-srpm.sh` and puts SRPM into COPR `$(outdir)`.
- If you use plain tags like `v1.2.3`, configure the webhook URL to include package name as
  described in COPR docs (e.g. `.../github/<owner>/<project>/modulix-automation-runtime/`).
- Alternatively, use tags in `modulix-automation-runtime-<version>` format.

### CLI setup (matches COPR docs flow)

Preferred: run from containerized devtools (no `copr-cli` needed on host):

```bash
podman run --rm -it \
  --userns keep-id \
  -v "$PWD":/workspace:Z -w /workspace \
  -v "$HOME/.config/copr:/home/wunder/.config/copr:ro,Z" \
  -e COPR_OWNER=<copr-owner> \
  -e COPR_PROJECT=modulix \
  -e COPR_PACKAGE=modulix-automation-runtime \
  localhost/ee-wunder-devtools-ubi9:local \
  bash /workspace/packaging/rpm/configure-copr-scm.sh
```

Host alternative (requires `copr-cli` installed on host):

```bash
COPR_OWNER=<copr-owner> COPR_PROJECT=modulix COPR_PACKAGE=modulix-automation-runtime \
  packaging/rpm/configure-copr-scm.sh
```

This executes `copr-cli add-package-scm` (or `edit-package-scm`) with:
- `--method make_srpm`
- `--webhook-rebuild on`
- package `modulix-automation-runtime`

Optional webhook secret rotation:

```bash
COPR_OWNER=<copr-owner> packaging/rpm/configure-copr-scm.sh --rotate-webhook-secret
```

### Disable webhook rebuild (when publishing only from GitHub tag workflow)

Use this when your release policy is tag-driven GitHub Actions publish (`v*` tags):

```bash
podman run --rm -it \
  --userns keep-id \
  -v "$PWD":/workspace:Z -w /workspace \
  -v "$HOME/.config/copr:/home/wunder/.config/copr:ro,Z" \
  -e COPR_OWNER=<copr-owner> \
  -e COPR_PROJECT=modulix \
  -e COPR_PACKAGE=modulix-automation-runtime \
  localhost/ee-wunder-devtools-ubi9:local \
  bash -lc 'bash /workspace/packaging/rpm/configure-copr-scm.sh --webhook-rebuild off'
```
