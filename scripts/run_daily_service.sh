#!/usr/bin/env bash
set -euo pipefail

root=/mnt/workspace/work/white-box-code-review

# GITCODE_API_TOKEN is persisted before the non-interactive early return.
# shellcheck source=/dev/null
source /home/developer/.bashrc
: "${GITCODE_API_TOKEN:?missing GITCODE_API_TOKEN after sourcing /home/developer/.bashrc}"

cd "$root"
exec "$root/.venv/bin/python" "$root/scripts/daily_refresh_and_push.py"
