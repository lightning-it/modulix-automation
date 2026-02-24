# Agent Instructions

## RPM validation fallback

When host tooling is missing for RPM checks, do not stop at a local limitation.

- If `rpmspec` and/or `rpmbuild` are not available on the host, run RPM parse/build
  validation in the devtools container first.
- Only report a limitation after the devtools-container path has been attempted.
- Avoid statements like:
  - `Could not run RPM parse/build locally because rpmspec/rpmbuild are not installed in this environment.`
  without also documenting the devtools-container attempt and result.
