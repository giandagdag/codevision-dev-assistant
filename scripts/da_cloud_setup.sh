#!/usr/bin/env bash
# Cloud start-up script for Claude Code cloud sessions.
# Why: cloud sessions start on a fresh machine with Python 3.13, but this project needs 3.14.
# This script builds the project's .venv with Python 3.14 and installs requirements-home.txt,
# so tests, ruff and the smoke check can run in the cloud while Gian is away from his laptop.
# It does nothing on Gian's laptop: it only runs when CLAUDE_CODE_REMOTE is "true".

set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}"

# uv is a fast installer that can also download Python itself.
if ! command -v uv >/dev/null 2>&1; then
  python3 -m pip install --quiet --break-system-packages uv
fi

# Build .venv once per machine. .venv is in .gitignore, so it never reaches GitHub.
if [ ! -x .venv/bin/python ]; then
  uv venv --quiet --python 3.14 .venv
fi

VIRTUAL_ENV="$PWD/.venv" uv pip install --quiet -r requirements-home.txt

echo "Cloud setup done: $(.venv/bin/python --version) in .venv with requirements-home.txt"
