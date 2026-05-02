#!/bin/sh
set -eu

if [ "$#" -eq 0 ]; then
  echo "usage: scripts/with-modern-node.sh <command> [args...]" >&2
  exit 64
fi

is_modern_node() {
  [ -x "$1" ] || return 1
  "$1" -e 'const major = Number(process.versions.node.split(".")[0]); process.exit(major >= 18 ? 0 : 1)' >/dev/null 2>&1
}

select_node() {
  if command -v node >/dev/null 2>&1; then
    command -v node
  fi

  [ -n "${NVM_BIN:-}" ] && printf '%s\n' "$NVM_BIN/node"
  [ -n "${VOLTA_HOME:-}" ] && printf '%s\n' "$VOLTA_HOME/bin/node"
  [ -n "${ASDF_DATA_DIR:-}" ] && printf '%s\n' "$ASDF_DATA_DIR/shims/node"
  printf '%s\n' \
    "/opt/homebrew/bin/node" \
    "/usr/local/bin/node" \
    "/usr/bin/node"
}

for candidate in $(select_node); do
  if is_modern_node "$candidate"; then
    node_dir=$(dirname "$candidate")
    export PATH="$node_dir:$PATH"
    exec "$@"
  fi
done

echo "webcalyzer-web requires Node.js 18 or newer to build and run the frontend." >&2
echo "Install a current Node.js release or place it before older Node versions on PATH." >&2
exit 1
