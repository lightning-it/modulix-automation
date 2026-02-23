# Support Matrix

This matrix defines supported execution modes for ModuLix automation.

## Runtime modes

| Mode | Status | Notes |
|---|---|---|
| Toolbox wrapper + EE (`ansible/scripts/ansible-nav`) | Supported (default) | Canonical path for customer operations |
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
| Default wrapper image | `quay.io/l-it/ee-wunder-toolbox-ubi9:v1.5.0` |
| Default run EE image | `quay.io/l-it/ee-wunder-ansible-ubi9:v1.9.3` |
| `run` execution style | Wrapper container + in-container `ansible-nav-local` + nested ansible EE |
| Inner run container engine | `podman` (fixed) |
| `run` toolbox mode | Privileged root toolbox runtime for nested podman |

## Collection source

- Base collections: provided by configured EE image.
- Local overlays for development only: `ansible/scripts/install-local-collections`.
- RH extension overlays (Automation Hub): `ansible/collections/requirements-rh.yml`.
