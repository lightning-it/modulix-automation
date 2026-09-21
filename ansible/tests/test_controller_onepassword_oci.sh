#!/usr/bin/env bash
# Real namespace-init integration; synthetic data only, no socket/secret mounts.
set -euo pipefail
engine="${1:-docker}"
image="${CONTROLLER_EE_IMAGE:-quay.io/l-it/ee-wunder-devtools-ubi9@sha256:82e9586f082f8818aba9e8c12b4cab696dda31b025bf561e7e9fdfd1037e7d25}"
[[ "$engine" == docker || "$engine" == podman ]]
[[ "$image" =~ ^quay.io/l-it/ee-wunder-devtools-ubi9@sha256:[0-9a-f]{64}$ ]]
repo="$(cd "$(dirname "$0")/../.." && pwd -P)"
evidence="$(mktemp -d "${CONTROLLER_OCI_EVIDENCE_ROOT:-${TMPDIR:-/tmp}}/controller-oci.XXXXXX")"
run_id="${evidence##*/}"

owned_container() {
  local cid="$1"
  [[ "$cid" =~ ^[0-9a-f]{64}$ ]] &&
    [[ "$("$engine" inspect --format '{{ index .Config.Labels "lit.controller-memory-test" }}' "$cid" 2>/dev/null)" == "$run_id" ]]
}
cleanup() {
  local file cid
  for file in "$evidence/success.cid" "$evidence/wait.cid"; do
    if [[ -f "$file" ]]; then
      cid="$(<"$file")"
      if owned_container "$cid"; then
        "$engine" rm -f "$cid" >/dev/null
      fi
    fi
  done
}
trap cleanup EXIT

for mode in success wait; do
  mkdir "$evidence/$mode"
  # Only public synthetic evidence is mounted. The private parent/cid files are
  # not mounted; allow the capability-dropped container UID to write on Docker.
  chmod 0777 "$evidence/$mode"
  "$engine" run --rm --pull=never --network=none --read-only --user=0:0 \
    --cap-drop=ALL --security-opt=no-new-privileges --security-opt=label=disable \
    --tmpfs /tmp:rw,mode=1777 -e PYTHONDONTWRITEBYTECODE=1 \
    --label "lit.controller-memory-test=$run_id" --cidfile "$evidence/$mode.cid" \
    -v "$repo:/source:ro" -v "$evidence/$mode:/evidence:rw" "$image" \
    /opt/app-root/bin/python3 -I /source/ansible/tests/controller_onepassword_oci_fixture.py "$mode" \
    >"$evidence/$mode.log" 2>&1 &
  observer_pid=$!
  if [[ "$mode" == wait ]]; then
    for ((attempt=0; attempt<100; attempt++)); do
      [[ -s "$evidence/$mode/heartbeat" ]] && break
      sleep 0.1
    done
    test -s "$evidence/$mode/heartbeat"
    cid="$(<"$evidence/$mode.cid")"
    owned_container "$cid"
    "$engine" kill --signal TERM "$cid" >/dev/null
  fi
  result=0
  wait "$observer_pid" || result=$?
  if [[ "$mode" == success ]]; then
    test "$result" -eq 0
  else
    test "$result" -eq 2
  fi
  test -s "$evidence/$mode/detached"
  test -s "$evidence/$mode/heartbeat"
  cp "$evidence/$mode/heartbeat" "$evidence/$mode-stopped"
  sleep 0.3
  cmp "$evidence/$mode/heartbeat" "$evidence/$mode-stopped"
  printf 'PASS: PID-1 %s kills detached descriptor holder\n' "$mode"
done
printf 'Synthetic OCI evidence: %s\n' "$evidence"
