# Inventory baseline

This repository ships only a dummy inventory baseline.
Environment-specific inventory data is platform-owned and must be provided per deployment environment.

Default placeholder path:
- `inventories/example/inventory.yml`

## Wunderbox service toggles

`playbooks/stage-2b/12-wunderbox.yml` supports per-task service toggles from inventory.

Preferred structure:

```yaml
all:
  vars:
    services:
      wunderbox:
        repos: enabled
        firewall: enabled
        coredns: enabled
        dhcp: enabled
        nginx_deploy: enabled
        vault_deploy: enabled
        vault_bootstrap: enabled
        vault_validate: enabled
        vault_ops: enabled
        vault_config: enabled
        minio_deploy: enabled
        minio_config: enabled
        minio_bootstrap: enabled
        nexus_deploy: enabled
        nginx_config: enabled
        nexus_config: enabled
```

Accepted values:
- enabled: `enabled`, `true`, `yes`, `on`, `1`, `y`
- disabled: anything else (for example `disabled` / `false`)

If a toggle is not set, it is treated as disabled.

Flat overrides are also supported for compatibility, for example:
- `wunderbox_service_repos: enabled`
- `wunderbox_service_vault_config: disabled`
