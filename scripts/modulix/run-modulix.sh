#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  run-modulix.sh --inventory <PATH> services <wunderbox|aap> [--rebuild] [ansible args...]
  run-modulix.sh --inventory <PATH> vault root-token [--vault-file <inventories/.../vault-init.yml>]
  run-modulix.sh --inventory <PATH> vault export-token [--vault-file <inventories/.../vault-init.yml>]

Examples:
  run-modulix.sh --inventory /path/to/inventories services wunderbox -i inventories/corp/inventory.yml
  run-modulix.sh --inventory /path/to/inventories services wunderbox --rebuild -i inventories/corp/inventory.yml --limit wunderbox01.prd.dmz.corp.l-it.io
  run-modulix.sh --inventory /path/to/inventories services aap --rebuild -i inventories/corp/inventory.yml --limit aap01.prd.dmz.corp.l-it.io
  run-modulix.sh --inventory /path/to/inventories vault root-token
  run-modulix.sh --inventory /path/to/inventories vault export-token
  run-modulix.sh --inventory /path/to/inventories vault root-token --vault-file inventories/corp/group_vars/wunderboxes/vault-init.yml
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" != "--inventory" || -z "${2:-}" ]]; then
  echo "Error: missing required --inventory <PATH> argument." >&2
  usage
  exit 1
fi
export INVENTORY_DIR="${2}"
shift 2

if [[ -z "${VAULT_PASS_FILE:-}" ]]; then
  VAULT_PASS_FILE="/home/rene/sources/modulix-automation/ansible/.vault-pass.txt"
fi
export VAULT_PASS_FILE
export CON_REGISTRY=quay.io/l-it
export RUN_EE_IMAGE="${CON_REGISTRY}/ee-wunder-ansible-ubi9-certified:v1.11.6"
export RUN_TOOLBOX_IMAGE="${CON_REGISTRY}/ee-wunder-toolbox-ubi9:v1.5.4"
export AUTHFILE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/containers/auth.json"

quay_login() {
  mkdir -p "$(dirname "$AUTHFILE")"
  podman login --authfile "$AUTHFILE" -u='l-it+pulltoken' -p='OA96PKS6S483X81FR4MUATYHIQ2HDKS7MMK2SZSW0IY1XGIAP84SBNM3B16SF5GP' quay.io 1>&2
}

pull_image() {
  local image="$1"
  podman pull --authfile "$AUTHFILE" "$image" 1>&2
}

require_nonempty_file() {
  local path="$1"
  local label="$2"

  if [[ -z "$path" ]]; then
    echo "Error: ${label} is empty" >&2
    exit 1
  fi
  if [[ ! -f "$path" ]]; then
    echo "Error: ${label} not found: $path" >&2
    exit 1
  fi
  if [[ ! -r "$path" ]]; then
    echo "Error: ${label} is not readable: $path" >&2
    exit 1
  fi
  if [[ ! -s "$path" ]]; then
    echo "Error: ${label} is empty: $path" >&2
    exit 1
  fi
}

require_directory() {
  local path="$1"
  local label="$2"

  if [[ -z "$path" ]]; then
    echo "Error: ${label} is empty" >&2
    exit 1
  fi
  if [[ ! -d "$path" ]]; then
    echo "Error: ${label} is not a directory: $path" >&2
    exit 1
  fi
  if [[ ! -r "$path" ]]; then
    echo "Error: ${label} is not readable: $path" >&2
    exit 1
  fi
}

require_env_var() {
  local name="$1"
  local hint="${2:-}"
  if [[ -z "${!name:-}" ]]; then
    echo "Error: required environment variable ${name} is not set." >&2
    if [[ -n "$hint" ]]; then
      echo "Hint: $hint" >&2
    fi
    exit 1
  fi
}

run_in_toolbox_interactive() {
  local env_args=(
    -e HOME=/runner
    -e REGISTRY_AUTH_FILE=/runner/.config/containers/auth.json
    -e ANSIBLE_TOOLBOX_NAV_EE_ENABLED=true
    -e ANSIBLE_TOOLBOX_NAV_EE_IMAGE="$RUN_EE_IMAGE"
    -e ANSIBLE_TOOLBOX_AUTO_COLLECTIONS=false
    -e ANSIBLE_VAULT_PASSWORD_FILE=/opt/modulix/ansible/.vault-pass.txt
  )
  if [[ -n "${VAULT_TOKEN:-}" ]]; then
    env_args+=( -e "VAULT_TOKEN=${VAULT_TOKEN}" )
  fi

  podman run --rm -it \
    --privileged \
    --security-opt label=disable \
    --user 0:0 \
    -w /opt/modulix/ansible \
    -v "$INVENTORY_DIR:/opt/modulix/ansible/inventories:ro,Z" \
    -v "$VAULT_PASS_FILE:/opt/modulix/ansible/.vault-pass.txt:ro,Z" \
    -v "$HOME/.ssh:/runner/.ssh:ro,Z" \
    -v "$AUTHFILE:/runner/.config/containers/auth.json:ro,Z" \
    "${env_args[@]}" \
    "$RUN_TOOLBOX_IMAGE" \
    "$@"
}

run_in_toolbox_batch() {
  local env_args=(
    -e HOME=/runner
    -e REGISTRY_AUTH_FILE=/runner/.config/containers/auth.json
    -e ANSIBLE_TOOLBOX_NAV_EE_ENABLED=true
    -e ANSIBLE_TOOLBOX_NAV_EE_IMAGE="$RUN_EE_IMAGE"
    -e ANSIBLE_TOOLBOX_AUTO_COLLECTIONS=false
    -e ANSIBLE_VAULT_PASSWORD_FILE=/opt/modulix/ansible/.vault-pass.txt
  )
  if [[ -n "${VAULT_TOKEN:-}" ]]; then
    env_args+=( -e "VAULT_TOKEN=${VAULT_TOKEN}" )
  fi

  podman run --rm \
    --privileged \
    --security-opt label=disable \
    --user 0:0 \
    -w /opt/modulix/ansible \
    -v "$INVENTORY_DIR:/opt/modulix/ansible/inventories:ro,Z" \
    -v "$VAULT_PASS_FILE:/opt/modulix/ansible/.vault-pass.txt:ro,Z" \
    -v "$HOME/.ssh:/runner/.ssh:ro,Z" \
    -v "$AUTHFILE:/runner/.config/containers/auth.json:ro,Z" \
    "${env_args[@]}" \
    "$RUN_TOOLBOX_IMAGE" \
    "$@"
}

run_services() {
  local service="${1:-wunderbox}"
  shift || true

  require_directory "$INVENTORY_DIR" "INVENTORY_DIR"
  require_nonempty_file "$VAULT_PASS_FILE" "VAULT_PASS_FILE"
  require_env_var "VAULT_TOKEN" "Export VAULT_TOKEN before running services (HashiCorp Vault access token)."

  # Parse local script flags first; pass everything else through to ansible.
  local rebuild=false
  local passthrough_args=()
  local arg=""
  for arg in "$@"; do
    case "$arg" in
      --rebuild|-r|rebuild)
        rebuild=true
        ;;
      *)
        passthrough_args+=( "$arg" )
        ;;
    esac
  done
  set -- "${passthrough_args[@]}"

  local default_limit=""
  local playbook=""
  case "$service" in
    wunderbox)
      default_limit="wunderbox01.prd.dmz.corp.l-it.io"
      if [[ "$rebuild" == true ]]; then
        playbook="playbooks/services/01-wunderbox-rebuild.yml"
      else
        playbook="playbooks/stage-2b/12-wunderbox.yml"
      fi
      ;;
    aap)
      default_limit="aap01.prd.dmz.corp.l-it.io"
      if [[ "$rebuild" == true ]]; then
        playbook="playbooks/services/02-aap-rebuild.yml"
      else
        playbook="playbooks/stage-2b/13-aap.yml"
      fi
      ;;
    *)
      echo "Error: unsupported service '$service'. Use: wunderbox | aap" >&2
      usage
      exit 1
      ;;
  esac

  # Detect whether caller already supplied inventory and/or limit.
  local has_inventory=false
  local has_limit=false
  for arg in "$@"; do
    [[ "$arg" == "-i" || "$arg" == "--inventory" ]] && has_inventory=true
    [[ "$arg" == "--limit" || "$arg" == "-l" ]] && has_limit=true
  done

  if [[ "$has_inventory" == false ]]; then
    echo "Error: services mode requires playbook inventory via -i/--inventory (no default is applied)." >&2
    exit 1
  fi

  local run_args=()
  if [[ "$has_limit" == false ]]; then
    run_args+=( --limit "$default_limit" )
  fi
  run_args+=( "$@" )

  # Ensure vault token is available as an Ansible extra var for nested EE runs.
  # Operator can still override explicitly by passing -e/--extra-vars vault_token=...
  local has_vault_token_extra_var=false
  local expect_extra_value=false
  for arg in "$@"; do
    if [[ "$expect_extra_value" == true ]]; then
      if [[ "$arg" == *"vault_token"* ]]; then
        has_vault_token_extra_var=true
      fi
      expect_extra_value=false
      continue
    fi
    case "$arg" in
      -e|--extra-vars)
        expect_extra_value=true
        ;;
      --extra-vars=*|-e=*)
        if [[ "${arg#*=}" == *"vault_token"* ]]; then
          has_vault_token_extra_var=true
        fi
        ;;
      -e*)
        if [[ "${arg#-e}" == *"vault_token"* ]]; then
          has_vault_token_extra_var=true
        fi
        ;;
    esac
  done
  if [[ "$has_vault_token_extra_var" == false ]]; then
    run_args+=( -e "vault_token=${VAULT_TOKEN}" )
  fi

  quay_login
  pull_image "$RUN_EE_IMAGE"
  pull_image "$RUN_TOOLBOX_IMAGE"

  run_in_toolbox_interactive ansible-nav-local run "$playbook" "${run_args[@]}"
}

run_vault_root_token() {
  local vault_file=""

  require_directory "$INVENTORY_DIR" "INVENTORY_DIR"
  require_nonempty_file "$VAULT_PASS_FILE" "VAULT_PASS_FILE"

  while [[ $# -gt 0 ]]; do
    case "${1:-}" in
      --vault-file)
        vault_file="${2:-}"
        if [[ -z "$vault_file" ]]; then
          echo "Error: --vault-file requires a value" >&2
          exit 1
        fi
        shift 2
        ;;
      *)
        echo "Error: unsupported argument for vault root-token: $1" >&2
        usage
        exit 1
        ;;
    esac
  done

  quay_login
  pull_image "$RUN_TOOLBOX_IMAGE"

  run_in_toolbox_batch bash -lc '
    set -euo pipefail
    shopt -s nullglob
    user_path="${1:-}"
    vault_candidates=()
    if [[ -n "$user_path" ]]; then
      if [[ "$user_path" == /* ]]; then
        vault_candidates+=( "$user_path" )
      else
        vault_candidates+=( "/opt/modulix/ansible/$user_path" )
      fi
    else
      vault_candidates+=(
        "/opt/modulix/ansible/inventories/corp/group_vars/wunderboxes/vault-init.yml"
        "/opt/modulix/ansible/inventories/corp/group_vars/all/vault-init.yml"
        "/opt/modulix/ansible/inventories/corp/group_vars/all/ansible-vault.yml"
        "/opt/modulix/ansible/inventories/corp/group_vars/all/vault_auth.yml"
        "/opt/modulix/ansible/inventories/corp/group_vars/wunderboxes/vault.yml"
        "/opt/modulix/ansible/inventories/corp/group_vars/all/vault.yml"
      )
      for candidate in /opt/modulix/ansible/inventories/corp/host_vars/*/vault-init.yml; do
        vault_candidates+=( "$candidate" )
      done
    fi

    found_file=false
    for vault_file in "${vault_candidates[@]}"; do
      if [[ ! -f "$vault_file" ]]; then
        continue
      fi
      found_file=true

      tmp_view="$(mktemp)"
      tmp_err="$(mktemp)"

      if ansible-vault view "$vault_file" >"$tmp_view" 2>"$tmp_err"; then
        :
      else
        # Allow plain YAML files too (not vault-encrypted).
        if grep -qi "input is not vault encrypted data" "$tmp_err"; then
          cat "$vault_file" >"$tmp_view"
        else
          cat "$tmp_err" >&2
          rm -f "$tmp_view" "$tmp_err"
          exit 1
        fi
      fi

      token_out=""
      if token_out="$(python3 - "$tmp_view" "$vault_file" 2>"$tmp_err" <<'"'"'PY'"'"'
import re
import sys

view_file = sys.argv[1]
source_file = sys.argv[2]
text = open(view_file, "r", encoding="utf-8").read()
token = None

try:
    import yaml  # type: ignore
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        data = {}
except Exception:
    data = {}

def deep_get(obj, path):
    cur = obj
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur

def normalize_token(raw):
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None
    # Ignore templated/unevaluated values from inventory defaults.
    if "{{" in value or "{%" in value:
        return None
    return value

candidates = [
    ("vault_init", "root_token"),
    ("vault_init", "root-token"),
    ("vault", "root_token"),
    ("vault", "root-token"),
    ("vault", "token"),
    ("vault_token",),
    ("root_token",),
    ("root-token",),
]
for path in candidates:
    value = normalize_token(deep_get(data, path))
    if value:
        token = value
        break

if token is None:
    patterns = [
        r"(?m)^\\s*root_token\\s*:\\s*[\\x22\\x27]?([^\\x22\\x27\\n#]+)",
        r"(?m)^\\s*root-token\\s*:\\s*[\\x22\\x27]?([^\\x22\\x27\\n#]+)",
        r"(?m)^\\s*vault_token\\s*:\\s*[\\x22\\x27]?([^\\x22\\x27\\n#]+)",
    ]
    for pat in patterns:
        match = re.search(pat, text)
        if match:
            value = normalize_token(match.group(1))
            if value:
                token = value
                break

if not token:
    print(f"ERROR: root_token/vault_token not found in {source_file}", file=sys.stderr)
    sys.exit(2)

# stdout only token; stderr can be used for diagnostics from caller.
print(token)
PY
)"; then
        py_rc=0
      else
        py_rc=$?
      fi

      if [[ "$py_rc" -eq 0 ]]; then
        rm -f "$tmp_view" "$tmp_err"
        printf "%s\n" "$token_out"
        exit 0
      fi

      if [[ "$py_rc" -ne 2 || -n "$user_path" ]]; then
        cat "$tmp_err" >&2
      fi
      rm -f "$tmp_view" "$tmp_err"

      if [[ "$py_rc" -ne 2 ]]; then
        exit "$py_rc"
      fi
    done

    if [[ "$found_file" == false ]]; then
      if [[ -n "$user_path" ]]; then
        echo "ERROR: vault file not found: ${vault_candidates[0]}" >&2
      else
        echo "ERROR: could not auto-detect vault source file. Use --vault-file inventories/.../vault-init.yml" >&2
      fi
      exit 1
    fi

    if [[ -n "$user_path" ]]; then
      echo "ERROR: root_token/vault_token not found in ${vault_candidates[0]}" >&2
    else
      echo "ERROR: root_token/vault_token not found in auto-detected vault files" >&2
    fi
    exit 2
  ' -- "$vault_file"
}

run_vault_export_token() {
  local token=""
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
      root-token)
        run_vault_root_token "$@"
        ;;
      export-token)
        run_vault_export_token "$@"
        ;;
      *)
        echo "Error: unsupported vault subcommand '$sub'. Use: root-token | export-token" >&2
        usage
        exit 1
        ;;
    esac
    ;;
  *)
    echo "Error: unsupported mode '$mode'. Expected: services | vault" >&2
    usage
    exit 1
    ;;
esac
