#!/usr/bin/env bash
set -euo pipefail

owner="${COPR_OWNER:-}"
project="${COPR_PROJECT:-modulix}"
package="${COPR_PACKAGE:-modulix-automation-runtime}"
clone_url="${COPR_CLONE_URL:-https://github.com/lightning-it/modulix-automation.git}"
commitish="${COPR_COMMIT:-main}"
subdir="${COPR_SUBDIR:-.}"
spec_path="${COPR_SPEC:-packaging/rpm/modulix-automation-runtime.spec}"
webhook_rebuild="${COPR_WEBHOOK_REBUILD:-on}"
rotate_webhook_secret=false

usage() {
  cat <<'EOF'
Configure a COPR SCM package for modulix-automation-runtime (GitHub webhook flow).

This wraps:
  copr-cli add-package-scm / edit-package-scm
with method=make_srpm and webhook-rebuild=on.

Usage:
  packaging/rpm/configure-copr-scm.sh [options]

Options:
  --owner <name>          COPR owner (required if COPR_OWNER is unset)
  --project <name>        COPR project (default: modulix)
  --package <name>        COPR package name (default: modulix-automation-runtime)
  --clone-url <url>       SCM clone URL (default: https://github.com/lightning-it/modulix-automation.git)
  --commit <ref>          Git branch/tag/sha to build (default: main)
  --subdir <path>         Subdirectory in repository (default: .)
  --spec <path>           Spec path relative to subdir (default: packaging/rpm/modulix-automation-runtime.spec)
  --webhook-rebuild on|off  Enable webhook rebuilds (default: on)
  --rotate-webhook-secret Regenerate webhook secret in COPR
  -h, --help              Show this help

Examples:
  COPR_OWNER=lightning-it packaging/rpm/configure-copr-scm.sh
  packaging/rpm/configure-copr-scm.sh --owner lightning-it --project modulix --commit main
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --owner)
      owner="${2:?missing value for --owner}"
      shift 2
      ;;
    --project)
      project="${2:?missing value for --project}"
      shift 2
      ;;
    --package)
      package="${2:?missing value for --package}"
      shift 2
      ;;
    --clone-url)
      clone_url="${2:?missing value for --clone-url}"
      shift 2
      ;;
    --commit)
      commitish="${2:?missing value for --commit}"
      shift 2
      ;;
    --subdir)
      subdir="${2:?missing value for --subdir}"
      shift 2
      ;;
    --spec)
      spec_path="${2:?missing value for --spec}"
      shift 2
      ;;
    --webhook-rebuild)
      webhook_rebuild="${2:?missing value for --webhook-rebuild}"
      shift 2
      ;;
    --rotate-webhook-secret)
      rotate_webhook_secret=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "${owner}" ]]; then
  echo "Missing COPR owner. Set COPR_OWNER or pass --owner." >&2
  exit 1
fi

case "${webhook_rebuild}" in
  on|off) ;;
  *)
    echo "Invalid value for --webhook-rebuild: ${webhook_rebuild} (use on|off)." >&2
    exit 1
    ;;
esac

if ! command -v copr-cli >/dev/null 2>&1; then
  echo "copr-cli is required but not installed." >&2
  exit 1
fi

copr_ref="${owner}/${project}"

if copr-cli get-package "${copr_ref}" --name "${package}" --output-format json >/dev/null 2>&1; then
  action="edit-package-scm"
else
  action="add-package-scm"
fi

copr-cli "${action}" "${copr_ref}" \
  --name "${package}" \
  --clone-url "${clone_url}" \
  --commit "${commitish}" \
  --subdir "${subdir}" \
  --spec "${spec_path}" \
  --method make_srpm \
  --webhook-rebuild "${webhook_rebuild}"

if [[ "${rotate_webhook_secret}" == true ]]; then
  copr-cli new-webhook-secret "${copr_ref}"
fi

echo
echo "Configured ${copr_ref}/${package} for SCM + make_srpm + webhook-rebuild=${webhook_rebuild}."
echo "Next step (UI): copy webhook URL from COPR Settings -> Integrations and add it in GitHub Webhooks."
