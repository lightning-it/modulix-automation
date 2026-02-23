# Support Matrix

This matrix defines supported execution modes for ModuLix automation.

## Runtime modes

| Mode | Status | Notes |
|---|---|---|
| Toolbox wrapper + EE (`ansible/scripts/ansible-nav`) | Supported (default) | Canonical path for customer operations |
| Host-native execution | Supported with prerequisites | Operator must ensure equivalent toolchain and collections |

## Container engines (wrapper mode)

| Engine | Status | Notes |
|---|---|---|
| Podman | Supported | Preferred on RHEL-like hosts |
| Docker | Supported | Supported when available on host |

## Image contract (wrapper mode)

| Component | Value |
|---|---|
| Default toolbox image | `quay.io/l-it/ee-wunder-toolbox-ubi9:v1.4.0` |
| Execution style | `ansible-navigator run --ee true` |

## Collection source

- Base collections: auto-bootstrapped from `ansible/collections/requirements.yml`
  into `ansible/collections` when missing/changed (default behavior).
- RH-certified/AAP profile: use
  `ANSIBLE_TOOLBOX_COLLECTIONS_REQUIREMENTS=/runner/project/collections/requirements-rh.yml`
  (requires Automation Hub access).
- Local overlays for development: `ansible/scripts/install-local-collections`
  into `ansible/collections-dev`.
- Effective search precedence: `collections-dev` -> `collections` -> EE/system paths.
