#!/usr/bin/env bash
set -euo pipefail

root=/mnt/workspace/work/white-box-code-review

# GITCODE_API_TOKEN is persisted before the non-interactive early return.
# shellcheck source=/dev/null
source /home/developer/.bashrc
: "${GITCODE_API_TOKEN:?missing GITCODE_API_TOKEN after sourcing /home/developer/.bashrc}"

# PM2's Node IPC variables are invalid after this wrapper execs Python. If they
# leak into `node --check`, Node treats the inherited descriptor as its own IPC
# channel and aborts in libuv before validating the file.
unset NODE_CHANNEL_FD NODE_CHANNEL_SERIALIZATION_MODE

cd "$root"
exec "$root/.venv/bin/python" "$root/scripts/daily_refresh_and_push.py"
