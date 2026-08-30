#!/usr/bin/env bash
# Safe local PostgreSQL Dashboard launcher — invoked by project-root `make run`.
#
# Semantics (ported from hive task112_start_pg_demo.sh):
#   * repo root is derived from this script's location (no hard-coded path)
#   * process-level database overrides are UNSET so the PostgreSQL settings in
#     `.env` win (the dashboard loads `.env` itself via load_dotenv)
#   * PROVIDER is forced to `mock` and the trading journal to `memory`
#   * settings/data live in a fresh throwaway temp dir; incremental sync is off
#   * this script never prints DSNs/credentials, never creates a database and
#     never mutates repository files
#
# Overrides (mainly for tests):
#   TW_DASHBOARD_PYTHON  interpreter to exec (default: <repo>/.venv/bin/python)
#   TMPDIR               parent for the throwaway settings/data directory
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$script_dir/.." && pwd)"
cd "$repo"

python_bin="${TW_DASHBOARD_PYTHON:-$repo/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  echo "找不到可執行的 Python：${python_bin}（預期為 ${repo}/.venv/bin/python）" >&2
  exit 1
fi

tmp_root="${TMPDIR:-/tmp}"
demo_dir="$(mktemp -d "${tmp_root%/}/tw-intraday-pg-dashboard.XXXXXX")"
mkdir -p "$demo_dir/backtest"
echo "安全暫存目錄（settings/data）：$demo_dir"
echo "啟動後請開啟：http://127.0.0.1:8000/"

exec env \
  -u BACKTEST_DATABASE_BACKEND \
  -u BACKTEST_DATABASE_URL \
  -u DATABASE_URL \
  -u POSTGRESQL_DSN \
  -u PostgreSQL_DSN \
  PROVIDER=mock \
  TRADING_JOURNAL_BACKEND=memory \
  LOCAL_PAPER_SETTINGS_PATH="$demo_dir/settings-v1.json" \
  BACKTEST_DATA_DIR="$demo_dir/backtest" \
  BACKTEST_INCREMENTAL_SYNC_ENABLED=false \
  "$python_bin" -m dashboard
