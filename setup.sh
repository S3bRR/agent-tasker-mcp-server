#!/usr/bin/env bash
# AgentTasker MCP Server setup

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
RECREATE=0
QUIET=0

usage() {
  cat <<'EOF'
Usage: ./setup.sh [options]

Options:
  --venv-dir PATH   Virtual environment directory (default: ./.venv)
  --recreate        Delete and recreate the virtual environment
  --quiet           Reduce setup output
  --help            Show this help text

Environment:
  VENV_DIR          Same as --venv-dir
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --venv-dir)
      [[ $# -lt 2 ]] && { echo "Error: --venv-dir requires a path"; exit 1; }
      VENV_DIR="$2"
      shift 2
      ;;
    --recreate)
      RECREATE=1
      shift
      ;;
    --quiet)
      QUIET=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown option '$1'"
      usage
      exit 1
      ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 not found on PATH"
  exit 1
fi

PYTHON_BIN="$(command -v python3)"
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  FOUND="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  echo "Error: Python 3.10+ required (found $FOUND at $PYTHON_BIN)"
  exit 1
fi

if [[ "$RECREATE" -eq 1 && -d "$VENV_DIR" ]]; then
  rm -rf "$VENV_DIR"
fi

if [[ ! -d "$VENV_DIR" ]]; then
  [[ "$QUIET" -eq 0 ]] && echo "Creating virtual environment: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  [[ "$QUIET" -eq 0 ]] && echo "Using existing virtual environment: $VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"

if [[ "$QUIET" -eq 1 ]]; then
  "$VENV_PY" -m pip install --upgrade pip >/dev/null
  "$VENV_PY" -m pip install "$ROOT_DIR" >/dev/null
else
  "$VENV_PY" -m pip install --upgrade pip
  "$VENV_PY" -m pip install "$ROOT_DIR"
fi

find "$ROOT_DIR" -maxdepth 1 -name '*.egg-info' -prune -exec rm -rf {} +

"$VENV_DIR/bin/agent-tasker-mcp-server" --help >/dev/null

cat <<EOF

Setup complete.

Python:
  $VENV_PY

Server entrypoint:
  $VENV_DIR/bin/agent-tasker-mcp-server

Run locally:
  $VENV_DIR/bin/agent-tasker-mcp-server --workers 8

MCP config (local clone):
{
  "command": "$VENV_DIR/bin/agent-tasker-mcp-server",
  "args": ["--workers", "8"]
}
EOF
