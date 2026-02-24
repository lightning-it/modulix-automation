#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_SRPM_DIR="${SCRIPT_DIR}/dist"

owner="${COPR_OWNER:-}"
project="${COPR_PROJECT:-modulix}"
chroot="${COPR_CHROOT:-epel-9-x86_64}"
srpm_path=""
create_project=false

usage() {
  cat <<'EOF'
Publish a modulix-automation-runtime SRPM to Fedora COPR.

Prerequisites:
  - copr-cli installed
  - ~/.config/copr configured with API credentials

Usage:
  packaging/rpm/publish-copr.sh [options]

Options:
  --owner <name>       COPR owner (or use COPR_OWNER env)
  --project <name>     COPR project name (default: modulix)
  --chroot <name>      COPR chroot for project creation (default: epel-9-x86_64)
  --srpm <path>        Path to source RPM (default: latest in packaging/rpm/dist)
  --create-project     Create project when missing
  -h, --help           Show help

Examples:
  COPR_OWNER=lightning-it packaging/rpm/publish-copr.sh --create-project
  packaging/rpm/publish-copr.sh --owner lightning-it --project modulix --srpm packaging/rpm/dist/modulix-automation-runtime-0.1.0-1.src.rpm
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
    --chroot)
      chroot="${2:?missing value for --chroot}"
      shift 2
      ;;
    --srpm)
      srpm_path="${2:?missing value for --srpm}"
      shift 2
      ;;
    --create-project)
      create_project=true
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
  echo "Missing COPR owner. Provide --owner or COPR_OWNER." >&2
  exit 1
fi

if ! command -v copr-cli >/dev/null 2>&1; then
  echo "copr-cli is required but not installed." >&2
  exit 1
fi

if [[ -z "${srpm_path}" ]]; then
  srpm_path="$(find "${DEFAULT_SRPM_DIR}" -maxdepth 1 -type f -name '*.src.rpm' | sort | tail -n 1)"
fi
if [[ -z "${srpm_path}" || ! -f "${srpm_path}" ]]; then
  echo "No SRPM found. Build one first with packaging/rpm/build-srpm.sh." >&2
  exit 1
fi

if [[ "${create_project}" == true ]]; then
  copr-cli create --chroot "${chroot}" "${project}" || true
fi

copr-cli build "${owner}/${project}" "${srpm_path}"
echo "Submitted ${srpm_path} to COPR ${owner}/${project}"
