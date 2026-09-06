#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Virtual environment not found at $ROOT_DIR/.venv"
  echo "Create it with: cd hack-projects/resq-mesh && python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi

echo "=== RESQ-Mesh full validation ==="
echo
echo "[1/2] Running full app smoke test"
"$PYTHON" "$ROOT_DIR/app/agent.py"
echo
echo "[2/2] Running unit tests"
"$PYTHON" -m unittest tests.test_resilience tests.test_solver tests.test_capabilities tests.test_mission tests.test_tools -v
echo
echo "Validation completed successfully."
