#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
SPEC_FILE="${SCRIPT_DIR}/modulix-automation-runtime.spec"
OUTPUT_DIR="${SCRIPT_DIR}/dist"
RPMBUILD_TOPDIR="${SCRIPT_DIR}/.rpmbuild"

version="${MODULIX_RPM_VERSION:-}"
release="${MODULIX_RPM_RELEASE:-1}"
has_git_repo=false

if command -v git >/dev/null 2>&1 && git -C "${REPO_ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  has_git_repo=true
fi

usage() {
  cat <<'EOF'
Build a source RPM for modulix-automation-runtime.

Usage:
  packaging/rpm/build-srpm.sh [options]

Options:
  --version <v>     RPM version (default: latest git tag without leading v, or 0.1.0)
  --release <r>     RPM release number (default: 1)
  --spec <path>     Spec file path (default: packaging/rpm/modulix-automation-runtime.spec)
  --output-dir <d>  Output directory for the src.rpm (default: packaging/rpm/dist)
  -h, --help        Show help

Examples:
  packaging/rpm/build-srpm.sh --version 0.1.0 --release 1
  packaging/rpm/build-srpm.sh --spec packaging/rpm/modulix-automation-runtime.spec
  MODULIX_RPM_VERSION=0.1.1 packaging/rpm/build-srpm.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      version="${2:?missing value for --version}"
      shift 2
      ;;
    --release)
      release="${2:?missing value for --release}"
      shift 2
      ;;
    --spec)
      SPEC_FILE="${2:?missing value for --spec}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:?missing value for --output-dir}"
      shift 2
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

if [[ -z "${version}" ]]; then
  if [[ "${has_git_repo}" == true ]]; then
    tag="$(git -C "${REPO_ROOT}" describe --tags --abbrev=0 2>/dev/null || true)"
    version="${tag#v}"
  elif [[ -n "${GITHUB_REF_NAME:-}" ]]; then
    version="${GITHUB_REF_NAME#v}"
  fi
fi
if [[ -z "${version}" ]]; then
  version="0.1.0"
fi
version="${version//-/.}"

if [[ "${SPEC_FILE}" != /* ]]; then
  SPEC_FILE="${REPO_ROOT}/${SPEC_FILE}"
fi
if [[ ! -f "${SPEC_FILE}" ]]; then
  echo "Spec file not found: ${SPEC_FILE}" >&2
  exit 1
fi

spec_basename="$(basename "${SPEC_FILE}")"
package_name="$(awk '/^Name:[[:space:]]*/ {print $2; exit}' "${SPEC_FILE}")"
if [[ -z "${package_name}" ]]; then
  echo "Unable to determine package name from spec: ${SPEC_FILE}" >&2
  exit 1
fi

for cmd in rpmbuild gzip tar; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}" >&2
    exit 1
  fi
done

mkdir -p "${RPMBUILD_TOPDIR}/SOURCES" "${RPMBUILD_TOPDIR}/SPECS" "${RPMBUILD_TOPDIR}/SRPMS" "${OUTPUT_DIR}"
spec_out="${RPMBUILD_TOPDIR}/SPECS/${spec_basename}"
cp -f "${SPEC_FILE}" "${spec_out}"

# Embed concrete version/release into the spec stored in the SRPM.
# COPR rebuilds SRPMs without custom --define flags, so macro fallbacks in the
# original spec can otherwise point to a different source tarball name.
sed -i \
  -e "s|^%global[[:space:]]\\+modulix_version.*$|%global modulix_version ${version}|" \
  -e "s|^%global[[:space:]]\\+modulix_release.*$|%global modulix_release ${release}|" \
  "${spec_out}"

source_tar="${RPMBUILD_TOPDIR}/SOURCES/modulix-${version}.tar.gz"
if [[ "${has_git_repo}" == true ]]; then
  git -C "${REPO_ROOT}" archive --format=tar --prefix="modulix-${version}/" HEAD | gzip -n > "${source_tar}"
else
  tar -C "${REPO_ROOT}" \
    --exclude-vcs \
    --exclude='./packaging/rpm/.rpmbuild' \
    --exclude='./packaging/rpm/dist' \
    --transform "s,^\.$,modulix-${version}," \
    --transform "s,^\./,modulix-${version}/," \
    -czf "${source_tar}" \
    .
fi

rpmbuild -bs "${spec_out}" \
  --define "_topdir ${RPMBUILD_TOPDIR}"

srpm_pattern="${package_name}-${version}-${release}*.src.rpm"
srpm="$(find "${RPMBUILD_TOPDIR}/SRPMS" -maxdepth 1 -type f -name "${srpm_pattern}" | sort | head -n 1)"
if [[ -z "${srpm}" ]]; then
  srpm="$(find "${RPMBUILD_TOPDIR}/SRPMS" -maxdepth 1 -type f -name '*.src.rpm' | sort | head -n 1)"
fi
if [[ -z "${srpm}" ]]; then
  echo "Failed to locate generated SRPM." >&2
  exit 1
fi

cp -f "${srpm}" "${OUTPUT_DIR}/"
echo "SRPM built: ${OUTPUT_DIR}/$(basename "${srpm}")"
