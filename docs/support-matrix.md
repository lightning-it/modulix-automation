# Support Matrix

This matrix defines supported execution modes for ModuLix automation.

## Runtime modes

| Mode | Status | Notes |
|---|---|---|
| Toolbox wrapper + EE (`ansible/scripts/ansible-nav`) | Supported (default) | Canonical path for platform operations |
| Host-native execution | Supported with prerequisites | Operator must ensure equivalent toolchain and collections |
| Runtime RH extension collection install (`ansible/scripts/install-rh-collections`) | Supported | Single-public-EE model for AAP/CaC dependency delivery |

## Container engines (wrapper mode)

| Engine | Status | Notes |
|---|---|---|
| Podman | Supported | Preferred on RHEL-like hosts |
| Docker | Supported | Supported when available on host |

## Image contract (wrapper mode)

| Component | Value |
|---|---|
| Default toolbox image | `quay.io/l-it/ee-wunder-toolbox-ubi9:v1.5.0` |
| Execution style | `ansible-navigator run --ee true` |

## Collection source

- Base collections: bootstrap is enabled by default (`ANSIBLE_TOOLBOX_AUTO_COLLECTIONS=true`).
- Default profile: `ansible/collections/requirements.yml`.
- RH-certified/AAP profile is selected automatically when
  `RH_AUTOMATION_HUB_TOKEN` is set and `ansible/collections/requirements-rh.yml`
  is present.
- Local overlays for development: `ansible/scripts/install-local-collections`
  into `ansible/collections-dev`.
- Effective search precedence: `collections-dev` -> `collections` -> EE/system paths.
