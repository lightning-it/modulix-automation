%global modulix_version %{?_modulix_version:%{_modulix_version}}%{!?_modulix_version:0.1.0}
%global modulix_release %{?_modulix_release:%{_modulix_release}}%{!?_modulix_release:1}

Name:           modulix-automation-runtime
Version:        %{modulix_version}
Release:        %{modulix_release}%{?dist}
Summary:        ModuLix helper scripts for toolbox workflows
License:        GPL-2.0-only
URL:            https://github.com/lightning-it/modulix-automation
Source0:        modulix-%{version}.tar.gz
BuildArch:      noarch
Provides:       modulix-scripts = %{version}-%{release}
Obsoletes:      modulix-scripts < %{version}-%{release}

Requires:       bash
Requires:       git

%description
Command-line helper scripts and Ansible runtime baseline from the ModuLix
repository packaged for RHEL-compatible systems.

The scripts are installed under /opt/modulix and exposed via wrapper commands
in %{_bindir}.

%prep
%autosetup -n modulix-%{version}

%build
# Nothing to build for script packaging.

%install
rm -rf %{buildroot}

install -d %{buildroot}/opt/modulix
cp -a scripts %{buildroot}/opt/modulix/
cp -a ansible %{buildroot}/opt/modulix/

# Remove local-only runtime artifacts from packaged payload.
rm -rf %{buildroot}/opt/modulix/ansible/.toolbox-podman
rm -f %{buildroot}/opt/modulix/ansible/.vault-pass.txt
rm -f %{buildroot}/opt/modulix/ansible/ansible-navigator.log
rm -f %{buildroot}/opt/modulix/ansible/ansible-automation-platform-containerized-setup-bundle-*.tar.gz

# Replace inventories with a neutral dummy baseline.
rm -rf %{buildroot}/opt/modulix/ansible/inventories
install -d %{buildroot}/opt/modulix/ansible/inventories/example
cat > %{buildroot}/opt/modulix/ansible/inventories/README.md <<'EOF'
# Inventory baseline

The packaged `modulix-automation-runtime` RPM does not ship environment-specific inventory.
Provide your own inventory in this directory (or mount an external inventory path)
before running `ansible-nav` / `ansible-nav-local`.
EOF
cat > %{buildroot}/opt/modulix/ansible/inventories/example/inventory.yml <<'EOF'
---
all:
  hosts:
    localhost:
      ansible_connection: local
EOF

# Ensure script payload is executable.
find %{buildroot}/opt/modulix -type f -name '*.sh' -exec chmod 0755 {} \;
chmod 0755 %{buildroot}/opt/modulix/ansible/scripts/ansible-nav
chmod 0755 %{buildroot}/opt/modulix/ansible/scripts/ansible-nav-local
chmod 0755 %{buildroot}/opt/modulix/ansible/scripts/install-local-collections
chmod 0755 %{buildroot}/opt/modulix/ansible/scripts/install-rh-collections

install -d %{buildroot}%{_bindir}

cat > %{buildroot}%{_bindir}/ansible-nav <<'EOF'
#!/usr/bin/env bash
exec /opt/modulix/ansible/scripts/ansible-nav "$@"
EOF

cat > %{buildroot}%{_bindir}/ansible-nav-local <<'EOF'
#!/usr/bin/env bash
exec /opt/modulix/ansible/scripts/ansible-nav-local "$@"
EOF

cat > %{buildroot}%{_bindir}/install-local-collections <<'EOF'
#!/usr/bin/env bash
exec /opt/modulix/ansible/scripts/install-local-collections "$@"
EOF

cat > %{buildroot}%{_bindir}/clone-all.sh <<'EOF'
#!/usr/bin/env bash
exec /opt/modulix/scripts/github/clone-all.sh "$@"
EOF

chmod 0755 \
  %{buildroot}%{_bindir}/ansible-nav \
  %{buildroot}%{_bindir}/ansible-nav-local \
  %{buildroot}%{_bindir}/install-local-collections \
  %{buildroot}%{_bindir}/clone-all.sh

%files
%license LICENSE
%doc README.md scripts/README.md
%{_bindir}/ansible-nav
%{_bindir}/ansible-nav-local
%{_bindir}/install-local-collections
%{_bindir}/clone-all.sh
/opt/modulix

%changelog
* Thu Feb 19 2026 Lightning IT <opensource@l-it.io> - %{version}-%{release}
- Initial RPM packaging for ModuLix scripts.
