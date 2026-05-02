#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WEB_DIR="$REPO_ROOT/web"
VENV_DIR="$REPO_ROOT/.venv"
CACHE_DIR="$REPO_ROOT/.webcalyzer-launcher"
HOST="${WEBCALYZER_HOST:-127.0.0.1}"
PORT="${WEBCALYZER_PORT:-8765}"
URL="http://$HOST:$PORT"

log() {
  printf '[webcalyzer-launcher] %s\n' "$*"
}

fail() {
  printf '\n[webcalyzer-launcher] ERROR: %s\n' "$*" >&2
  exit 1
}

find_python() {
  local candidate
  for candidate in "${PYTHON:-}" python3 python; do
    [ -n "$candidate" ] || continue
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
        command -v "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

fingerprint() {
  "$VENV_PYTHON" "$REPO_ROOT/scripts/launcher_fingerprint.py" "$1" "$REPO_ROOT"
}

cache_matches() {
  local name="$1"
  local value="$2"
  local cache_file="$CACHE_DIR/$name.sha256"
  [ -f "$cache_file" ] && [ "$(cat "$cache_file")" = "$value" ]
}

write_cache() {
  local name="$1"
  local value="$2"
  printf '%s' "$value" > "$CACHE_DIR/$name.sha256"
}

python_imports_ok() {
  "$VENV_PYTHON" -c 'import fastapi, uvicorn, webcalyzer' >/dev/null 2>&1
}

wait_and_open_browser() {
  (
    for _ in $(seq 1 90); do
      "$VENV_PYTHON" - "$URL/api/meta" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=1) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
      if [ "$?" -eq 0 ]; then
        open "$URL" >/dev/null 2>&1 || true
        exit 0
      fi
      sleep 1
    done
  ) &
}

cd "$REPO_ROOT" || exit 1
mkdir -p "$CACHE_DIR"

SYSTEM_PYTHON="$(find_python)" || fail "Python 3.11 or newer was not found. Install Python first, then rerun this launcher."

if [ ! -x "$VENV_DIR/bin/python" ]; then
  log "Creating local Python environment at .venv"
  "$SYSTEM_PYTHON" -m venv "$VENV_DIR" || fail "Could not create .venv."
fi

VENV_PYTHON="$VENV_DIR/bin/python"

PYTHON_FP="$(fingerprint python)"
if ! cache_matches python "$PYTHON_FP" || ! python_imports_ok; then
  log "Installing Python package into .venv"
  "$VENV_PYTHON" -m pip install -e "$REPO_ROOT" || fail "Python dependency install failed. Check your internet connection for first-time setup."
  write_cache python "$PYTHON_FP"
else
  log "Python environment is up to date"
fi

DEPS_FP="$(fingerprint frontend-deps)"
if ! cache_matches frontend-deps "$DEPS_FP" || [ ! -d "$WEB_DIR/node_modules" ]; then
  log "Installing frontend dependencies"
  cd "$WEB_DIR" || exit 1
  if [ -f package-lock.json ]; then
    ./scripts/with-modern-node.sh npm ci || fail "Frontend dependency install failed. Check Node.js/npm and your internet connection for first-time setup."
  else
    ./scripts/with-modern-node.sh npm install || fail "Frontend dependency install failed. Check Node.js/npm and your internet connection for first-time setup."
  fi
  cd "$REPO_ROOT" || exit 1
  write_cache frontend-deps "$DEPS_FP"
else
  log "Frontend dependencies are up to date"
fi

BUILD_FP="$(fingerprint frontend-build)"
if ! cache_matches frontend-build "$BUILD_FP" || [ ! -f "$WEB_DIR/dist/index.html" ]; then
  log "Building frontend bundle"
  cd "$WEB_DIR" || exit 1
  ./scripts/with-modern-node.sh npm run build || fail "Frontend build failed."
  cd "$REPO_ROOT" || exit 1
  write_cache frontend-build "$BUILD_FP"
else
  log "Frontend bundle is up to date"
fi

log "Launching webcalyzer at $URL"
log "Press Control-C in this terminal to stop the server."
wait_and_open_browser
exec "$VENV_PYTHON" -m webcalyzer serve \
  --host "$HOST" \
  --port "$PORT" \
  --root "$REPO_ROOT" \
  --templates-dir "$REPO_ROOT/configs"
