#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

export RUN_EE_IMAGE="${RUN_EE_IMAGE:-localhost/ee-wunder-ansible-ubi9-certified:local-modulix-rpmtest}"
export RUN_TOOLBOX_IMAGE="${RUN_TOOLBOX_IMAGE:-localhost/ee-wunder-toolbox-ubi9:local-modulix-rpmtest}"

exec "${SCRIPT_DIR}/run-modulix.sh" "$@"
