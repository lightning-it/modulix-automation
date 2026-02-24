# ModuLix Automation

ModuLix automation is the delivery source-of-truth for platform automation baselines.
It is delivered as the `modulix-automation-runtime` RPM.

## Delivery model

- Delivery artifact: `modulix-automation-runtime` RPM
- Default runtime: toolbox wrapper + EE (`scripts/ansible-nav`)
- Runtime payload: Ansible and collection set provided by the configured EE image
- RH extension collections (AAP/CaC) can be installed at runtime from
  `ansible/collections/requirements-rh.yml` (Automation Hub token required)
- Optional runtime: host-native execution (supported with prerequisites)

Canonical release-coupled docs in this repo:

- Runtime contract: `docs/runtime-contract.md`
- Support matrix: `docs/support-matrix.md`
- Packaging/build: `packaging/rpm/README.md`

## Quick start (default)

```bash
cd ansible
./scripts/ansible-nav run playbooks/services/01-wunderbox-rebuild.yml \
  -i inventories/example/inventory.yml --limit wunderbox01.prd.dmz.corp.l-it.io
```

## Development

When developing local Ansible collections from sibling repos (for example
`ansible-collection-supplementary`, `ansible-collection-foundational`), install
them as local overlays before running playbooks:

```bash
cd ansible
./scripts/install-local-collections
```

What this does:

- Builds local `ansible-collection-*` sources into tarballs.
- Installs them into `ansible/collections-dev`.
- Ensures local overlays take precedence over `ansible/collections` during runs.

## Full operator documentation

Curated operator guides, architecture, runbooks and troubleshooting live in:

- `https://github.com/lightning-it/lcp-docs/tree/main/ModuLix`

## Security statement

- No secrets in repository.
- Provide secrets via runtime inputs (for example `ANSIBLE_VAULT_PASSWORD_FILE`, `VAULT_TOKEN`, ssh-agent).
