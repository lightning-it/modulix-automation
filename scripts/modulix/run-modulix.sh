#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  run-modulix.sh --inventory <PATH> services <wunderbox|aap> [--rebuild] [--playbook <PATH>] [ansible args...]
  run-modulix.sh --inventory <PATH> vault root-token [--vault-file <PATH>]
  run-modulix.sh --inventory <PATH> vault export-token [--vault-file <PATH>]
USAGE
}

die() {
  echo "Error: $*" >&2
  exit 1
}

abs_path() {
  local p="$1"
  [[ "$p" == /* ]] || p="$PWD/$p"
  readlink -f -- "$p"
}

runner_path() {
  local p
  p="$(abs_path "$1")"
  case "$p" in
    "$PWD_ABS") echo "/runner/project" ;;
    "$PWD_ABS"/*) echo "/runner/project/${p#"$PWD_ABS"/}" ;;
    *) die "path must be inside current directory ($PWD_ABS): $1" ;;
  esac
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

[[ "${1:-}" == "--inventory" && -n "${2:-}" ]] || {
  usage
  die "missing required --inventory <PATH>"
}

PWD_ABS="$(readlink -f -- "$PWD")"
INVENTORY_DIR="$(abs_path "$2")"
shift 2

case "$INVENTORY_DIR" in
  "$PWD_ABS"|"$PWD_ABS"/*) ;;
  *) die "--inventory must be inside current directory ($PWD_ABS): $INVENTORY_DIR" ;;
esac
[[ -d "$INVENTORY_DIR" ]] || die "--inventory is not a directory: $INVENTORY_DIR"

RUN_EE_IMAGE="${RUN_EE_IMAGE:-quay.io/l-it/ee-wunder-ansible-ubi9-certified:v1.11.6}"
RUN_TOOLBOX_IMAGE="${RUN_TOOLBOX_IMAGE:-quay.io/l-it/ee-wunder-toolbox-ubi9:v1.7.0}"
VAULT_PASS_FILE="$(abs_path "${VAULT_PASS_FILE:-$PWD_ABS/.vault-pass.txt}")"
AUTHFILE="$(abs_path "${AUTHFILE:-$PWD_ABS/.podman-auth.json}")"
RUN_USE_HOST_EE_IMAGE="${RUN_USE_HOST_EE_IMAGE:-true}"
RUN_SKIP_AUTH="${RUN_SKIP_AUTH:-false}"
RUN_SKIP_CERT_CHECK="${RUN_SKIP_CERT_CHECK:-false}"

case "$RUN_USE_HOST_EE_IMAGE" in
  true|false) ;;
  *) die "RUN_USE_HOST_EE_IMAGE must be true or false (got: $RUN_USE_HOST_EE_IMAGE)" ;;
esac

case "$RUN_SKIP_AUTH" in
  true|false) ;;
  *) die "RUN_SKIP_AUTH must be true or false (got: $RUN_SKIP_AUTH)" ;;
esac

case "$RUN_SKIP_CERT_CHECK" in
  true|false) ;;
  *) die "RUN_SKIP_CERT_CHECK must be true or false (got: $RUN_SKIP_CERT_CHECK)" ;;
esac

case "$VAULT_PASS_FILE" in
  "$PWD_ABS"|"$PWD_ABS"/*) ;;
  *) die "VAULT_PASS_FILE must be inside current directory ($PWD_ABS): $VAULT_PASS_FILE" ;;
esac
[[ -f "$VAULT_PASS_FILE" && -r "$VAULT_PASS_FILE" && -s "$VAULT_PASS_FILE" ]] || {
  die "required file missing or unreadable: $VAULT_PASS_FILE"
}

case "$AUTHFILE" in
  "$PWD_ABS"|"$PWD_ABS"/*) ;;
  *) die "AUTHFILE must be inside current directory ($PWD_ABS): $AUTHFILE" ;;
esac

RUNNER_INVENTORY_DIR="$(runner_path "$INVENTORY_DIR")"
RUNNER_VAULT_PASS_FILE="$(runner_path "$VAULT_PASS_FILE")"
RUNNER_AUTHFILE="$(runner_path "$AUTHFILE")"
SSH_AUTH_SOCK_HOST=""

is_remote_image() {
  [[ "$1" != localhost/* ]]
}

ensure_authfile_for_remote() {
  local image="$1"
  [[ "$RUN_SKIP_AUTH" == "true" ]] && return
  if is_remote_image "$image"; then
    [[ -f "$AUTHFILE" && -s "$AUTHFILE" ]] || die "remote image requires authfile: $AUTHFILE (run: podman login --authfile \"$AUTHFILE\" quay.io or set RUN_SKIP_AUTH=true)"
  fi
}

require_ssh_agent() {
  local candidate=""
  [[ -n "${SSH_AUTH_SOCK:-}" ]] || die "SSH_AUTH_SOCK is not set. Start ssh-agent and load key(s) with ssh-add."

  candidate="$(readlink -f -- "$SSH_AUTH_SOCK" 2>/dev/null || true)"
  if [[ -n "$candidate" && -S "$candidate" ]]; then
    SSH_AUTH_SOCK_HOST="$candidate"
    return
  fi

  if [[ -S "$SSH_AUTH_SOCK" ]]; then
    SSH_AUTH_SOCK_HOST="$SSH_AUTH_SOCK"
    return
  fi

  die "SSH_AUTH_SOCK is not a valid socket: $SSH_AUTH_SOCK"
}

pull_image() {
  local image="$1"
  local pull_args=()
  if [[ "$image" == localhost/* ]]; then
    podman image exists "$image" || die "local image not found: $image"
    echo "Using local image: $image" >&2
    return
  fi
  if [[ "$RUN_SKIP_AUTH" != "true" ]]; then
    pull_args+=( --authfile "$AUTHFILE" )
  fi
  if [[ "$RUN_SKIP_CERT_CHECK" == "true" ]]; then
    pull_args+=( --tls-verify=false )
  fi
  podman pull "${pull_args[@]}" "$image" >/dev/null
}

run_toolbox() {
  local interactive="$1"
  shift

  local tty=()
  [[ "$interactive" == true ]] && tty=( -it )

  local envs=(
    -e HOME=/runner/project
    -e ANSIBLE_TOOLBOX_NAV_EE_ENABLED=true
    -e "ANSIBLE_TOOLBOX_NAV_EE_IMAGE=$RUN_EE_IMAGE"
    -e "ANSIBLE_TOOLBOX_NAV_SKIP_AUTH=$RUN_SKIP_AUTH"
    -e "ANSIBLE_TOOLBOX_NAV_SKIP_CERT_CHECK=$RUN_SKIP_CERT_CHECK"
    -e ANSIBLE_TOOLBOX_AUTO_COLLECTIONS=false
    -e "ANSIBLE_VAULT_PASSWORD_FILE=$RUNNER_VAULT_PASS_FILE"
  )
  if [[ "$RUN_SKIP_AUTH" != "true" ]]; then
    envs+=( -e "REGISTRY_AUTH_FILE=$RUNNER_AUTHFILE" )
  fi
  if [[ "$RUN_USE_HOST_EE_IMAGE" == "true" ]]; then
    envs+=( -e ANSIBLE_TOOLBOX_NAV_PULL_POLICY=never )
  fi
  [[ -n "${VAULT_TOKEN:-}" ]] && envs+=( -e "VAULT_TOKEN=${VAULT_TOKEN}" )
  local socket_mount=()
  if [[ -n "$SSH_AUTH_SOCK_HOST" ]]; then
    envs+=( -e "SSH_AUTH_SOCK=$SSH_AUTH_SOCK_HOST" )
    socket_mount+=( -v "$SSH_AUTH_SOCK_HOST:$SSH_AUTH_SOCK_HOST" )
  fi

  podman run --rm "${tty[@]}" \
    --privileged \
    --security-opt label=disable \
    --user 0:0 \
    -w /runner/project \
    -v "$PWD_ABS:/runner/project:Z" \
    "${socket_mount[@]}" \
    "${envs[@]}" \
    "$RUN_TOOLBOX_IMAGE" \
    "$@"
}

rewrite_inventory_args() {
  local out=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -i|--inventory)
        [[ $# -ge 2 ]] || die "$1 requires a value"
        if [[ "$2" == inventories/* ]]; then
          out+=( "$1" "$RUNNER_INVENTORY_DIR/${2#inventories/}" )
        else
          out+=( "$1" "$2" )
        fi
        shift 2
        ;;
      --inventory=*)
        local inv="${1#*=}"
        if [[ "$inv" == inventories/* ]]; then
          out+=( "--inventory=$RUNNER_INVENTORY_DIR/${inv#inventories/}" )
        else
          out+=( "$1" )
        fi
        shift
        ;;
      *)
        out+=( "$1" )
        shift
        ;;
    esac
  done
  printf '%s\0' "${out[@]}"
}

run_services() {
  local service="$1"
  shift || true

  require_ssh_agent

  local rebuild=false
  local playbook_override=""
  local expect_playbook=false
  local args=()
  local a
  for a in "$@"; do
    if [[ "$expect_playbook" == true ]]; then
      playbook_override="$a"
      expect_playbook=false
      continue
    fi
    case "$a" in
      --rebuild|-r|rebuild) rebuild=true ;;
      --playbook|-p) expect_playbook=true ;;
      --playbook=*|-p=*)
        playbook_override="${a#*=}"
        [[ -n "$playbook_override" ]] || die "--playbook requires a non-empty value"
        ;;
      *) args+=( "$a" ) ;;
    esac
  done
  [[ "$expect_playbook" == false ]] || die "--playbook requires a value"

  local playbook=""
  local default_limit=""
  case "$service" in
    wunderbox)
      default_limit="wunderbox01.prd.dmz.corp.l-it.io"
      if [[ "$rebuild" == true ]]; then
        playbook="/opt/modulix/ansible/playbooks/services/01-wunderbox-rebuild.yml"
      else
        playbook="/opt/modulix/ansible/playbooks/stage-2b/12-wunderbox.yml"
      fi
      ;;
    aap)
      default_limit="aap01.prd.dmz.corp.l-it.io"
      if [[ "$rebuild" == true ]]; then
        playbook="/opt/modulix/ansible/playbooks/services/02-aap-rebuild.yml"
      else
        playbook="/opt/modulix/ansible/playbooks/stage-2b/13-aap.yml"
      fi
      ;;
    *) die "unsupported service '$service' (use: wunderbox | aap)" ;;
  esac

  if [[ -n "$playbook_override" ]]; then
    case "$playbook_override" in
      /*) playbook="$playbook_override" ;;
      playbooks/*) playbook="/opt/modulix/ansible/$playbook_override" ;;
      ansible/playbooks/*) playbook="/runner/project/$playbook_override" ;;
      *.yml|*.yaml) playbook="/opt/modulix/ansible/playbooks/$playbook_override" ;;
      *) die "invalid --playbook path '$playbook_override' (use absolute path, playbooks/..., ansible/playbooks/..., or <subpath>.yml)" ;;
    esac
  fi

  local has_inventory=false
  local has_limit=false
  for a in "${args[@]}"; do
    [[ "$a" == "-i" || "$a" == "--inventory" || "$a" == --inventory=* ]] && has_inventory=true
    [[ "$a" == "-l" || "$a" == "--limit" ]] && has_limit=true
  done
  [[ "$has_inventory" == true ]] || die "services mode requires -i/--inventory"

  if [[ "$has_limit" == false ]]; then
    args+=( --limit "$default_limit" )
  fi

  local run_args=()
  while IFS= read -r -d '' a; do
    run_args+=( "$a" )
  done < <(rewrite_inventory_args "${args[@]}")

  local has_vault_token=false
  local expect_extra=false
  for a in "${run_args[@]}"; do
    if [[ "$expect_extra" == true ]]; then
      [[ "$a" == *vault_token* ]] && has_vault_token=true
      expect_extra=false
      continue
    fi
    case "$a" in
      -e|--extra-vars)
        expect_extra=true
        ;;
      --extra-vars=*|-e=*|-e*)
        [[ "$a" == *vault_token* ]] && has_vault_token=true
        ;;
    esac
  done

  if [[ "$has_vault_token" == false ]]; then
    [[ -n "${VAULT_TOKEN:-}" ]] || die "set VAULT_TOKEN or pass -e vault_token=..."
    run_args+=( -e "vault_token=${VAULT_TOKEN}" )
  fi

  ensure_authfile_for_remote "$RUN_EE_IMAGE"
  ensure_authfile_for_remote "$RUN_TOOLBOX_IMAGE"
  pull_image "$RUN_TOOLBOX_IMAGE"
  if [[ "$RUN_USE_HOST_EE_IMAGE" == "true" ]]; then
    local ee_archive=""
    local runner_ee_archive=""
    local cache_dir="$PWD_ABS/.run-modulix-cache"

    pull_image "$RUN_EE_IMAGE"
    echo "Syncing run EE image from host store into toolbox: $RUN_EE_IMAGE" >&2

    mkdir -p -- "$cache_dir"
    ee_archive="$(mktemp "$cache_dir/run-ee-image.XXXXXX.tar")"
    runner_ee_archive="$(runner_path "$ee_archive")"

    if ! podman save -o "$ee_archive" "$RUN_EE_IMAGE" >/dev/null; then
      rm -f -- "$ee_archive"
      die "failed to export run EE image from host store: $RUN_EE_IMAGE"
    fi

    if ! run_toolbox true bash -lc '
      set -euo pipefail
      ee_archive="$1"
      shift
      podman load -i "$ee_archive" >/dev/null
      exec ansible-nav-local run "$@"
    ' -- "$runner_ee_archive" "$playbook" "${run_args[@]}"; then
      rm -f -- "$ee_archive"
      return 1
    fi

    rm -f -- "$ee_archive"
    return 0
  fi

  run_toolbox true ansible-nav-local run "$playbook" "${run_args[@]}"
}

resolve_vault_file() {
  local p="$1"
  if [[ "$p" == inventories/* ]]; then
    echo "$INVENTORY_DIR/${p#inventories/}"
  else
    abs_path "$p"
  fi
}

run_vault_root_token() {
  local user_vault=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --vault-file)
        [[ -n "${2:-}" ]] || die "--vault-file requires a value"
        user_vault="$(resolve_vault_file "$2")"
        shift 2
        ;;
      *) die "unsupported argument for vault root-token: $1" ;;
    esac
  done

  local host_candidates=()
  if [[ -n "$user_vault" ]]; then
    [[ -f "$user_vault" ]] || die "vault file not found: $user_vault"
    host_candidates=( "$user_vault" )
  else
    host_candidates=(
      "$INVENTORY_DIR/corp/group_vars/wunderboxes/vault-init.yml"
      "$INVENTORY_DIR/corp/group_vars/all/vault-init.yml"
      "$INVENTORY_DIR/corp/group_vars/all/ansible-vault.yml"
      "$INVENTORY_DIR/corp/group_vars/all/vault_auth.yml"
      "$INVENTORY_DIR/corp/group_vars/wunderboxes/vault.yml"
      "$INVENTORY_DIR/corp/group_vars/all/vault.yml"
    )
    local hv
    for hv in "$INVENTORY_DIR"/corp/host_vars/*/vault-init.yml; do
      [[ -f "$hv" ]] && host_candidates+=( "$hv" )
    done
  fi

  local candidates=()
  local f
  for f in "${host_candidates[@]}"; do
    [[ -f "$f" ]] && candidates+=( "$(runner_path "$f")" )
  done
  [[ ${#candidates[@]} -gt 0 ]] || die "no candidate vault file found"

  ensure_authfile_for_remote "$RUN_TOOLBOX_IMAGE"
  pull_image "$RUN_TOOLBOX_IMAGE"

  run_toolbox false bash -lc '
    set -euo pipefail

    for f in "$@"; do
      [[ -f "$f" ]] || continue

      tmp="$(mktemp)"
      err="$(mktemp)"
      if ansible-vault view "$f" >"$tmp" 2>"$err"; then
        :
      elif grep -qi "input is not vault encrypted data" "$err"; then
        cp "$f" "$tmp"
      else
        cat "$err" >&2
        rm -f "$tmp" "$err"
        exit 1
      fi

      line="$(grep -E "^[[:space:]]*(root_token|root-token|vault_token)[[:space:]]*:" "$tmp" | head -n1 || true)"
      rm -f "$err"
      if [[ -z "$line" ]]; then
        rm -f "$tmp"
        continue
      fi

      token="${line#*:}"
      token="${token%%#*}"
      token="$(printf "%s" "$token" | xargs)"
      token="${token#\"}"
      token="${token%\"}"
      rm -f "$tmp"

      if [[ -n "$token" && "$token" != *"{{"* && "$token" != *"{%"* ]]; then
        printf "%s\n" "$token"
        exit 0
      fi
    done

    echo "ERROR: root_token/vault_token not found in candidate vault files" >&2
    exit 2
  ' -- "${candidates[@]}"
}

run_vault_export_token() {
  local token
  token="$(run_vault_root_token "$@")"
  printf "export VAULT_TOKEN=%q\n" "$token"
}

mode="${1:-}"
case "$mode" in
  services)
    service="${2:-wunderbox}"
    shift $(( $# >= 2 ? 2 : $# ))
    run_services "$service" "$@"
    ;;
  vault)
    sub="${2:-root-token}"
    shift $(( $# >= 2 ? 2 : $# ))
    case "$sub" in
      root-token) run_vault_root_token "$@" ;;
      export-token) run_vault_export_token "$@" ;;
      *) die "unsupported vault subcommand '$sub' (use: root-token | export-token)" ;;
    esac
    ;;
  *)
    usage
    die "unsupported mode '$mode' (expected: services | vault)"
    ;;
esac
