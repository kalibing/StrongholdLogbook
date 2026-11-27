#!/usr/bin/env bash
# Linux / macOS 本地开发：SQLite 后端 + 导入 worker + Vite，Ctrl+C 一起退出。
# 用法：scripts/dev.sh            （API 8000 / 网页 5173）
#       scripts/dev.sh --no-worker
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
python="$root/.venv/bin/python"
[[ -x $python ]] || { echo "缺少虚拟环境：python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt" >&2; exit 1; }

mkdir -p "$root/.local"
export LOGBOOK_DB=sqlite
export LOGBOOK_SQLITE="$root/.local/logbook.sqlite3"
export PUBLIC_ORIGIN=http://localhost:5173
export PYTHONPATH="$root/backend"

echo "存储：SQLite  $LOGBOOK_SQLITE"
echo "首次使用请先建账号：(cd backend && ../.venv/bin/python -m logbook.admin create-user <用户名>)"

pids=()
trap 'kill "${pids[@]}" 2>/dev/null || true' EXIT INT TERM
(cd "$root/backend" && exec "$python" -m uvicorn logbook.api:app --host 127.0.0.1 --port 8000 --reload) & pids+=($!)
if [[ ${1:-} != --no-worker ]]; then
  (cd "$root/backend" && exec "$python" -m logbook.worker) & pids+=($!)
fi
(cd "$root/frontend" && exec npm run dev) & pids+=($!)
wait
