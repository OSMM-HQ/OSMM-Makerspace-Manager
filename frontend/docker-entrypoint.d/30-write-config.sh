#!/bin/sh
set -eu

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

fail() {
  echo "Invalid runtime config: $1" >&2
  exit 1
}

validate_js_string() {
  name="$1"
  value="$2"
  if printf '%s' "$value" | grep -q '[[:cntrl:]"\\`<>]'; then
    fail "$name contains unsafe characters"
  fi
}

validate_api_url() {
  value="$1"
  validate_js_string "TENANT_API_URL" "$value"
  case "$value" in
    /*|http://*|https://*) ;;
    *) fail "TENANT_API_URL must be a relative /api path or an http(s) URL" ;;
  esac
}

validate_tenant_token() {
  value="$1"
  validate_js_string "TENANT_TOKEN" "$value"
  token_len="$(printf '%s' "$value" | wc -c | tr -d ' ')"
  if [ "$token_len" -gt 256 ]; then
    fail "TENANT_TOKEN must be 256 characters or fewer"
  fi
  if [ -n "$value" ] && ! printf '%s' "$value" | grep -Eq '^[A-Za-z0-9._:-]+$'; then
    fail "TENANT_TOKEN may only contain letters, numbers, dot, underscore, colon, and dash"
  fi
}

api_url="${TENANT_API_URL:-${VITE_API_URL:-/api}}"
tenant_token="${TENANT_TOKEN:-${VITE_TENANT_TOKEN:-}}"
case "${TENANT_ORIGIN_BOOTSTRAP:-}" in
  true|1) origin_bootstrap=true ;;
  *) origin_bootstrap=false ;;
esac
config_path="${TENANT_CONFIG_PATH:-/usr/share/nginx/html/config.js}"

validate_api_url "$api_url"
validate_tenant_token "$tenant_token"

cat > "$config_path" <<EOF
window.__TENANT__ = {
  apiUrl: "$(json_escape "$api_url")",
  tenantToken: "$(json_escape "$tenant_token")",
  originBootstrap: $origin_bootstrap
};
EOF
