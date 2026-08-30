#!/usr/bin/env bash
# Safe local PostgreSQL Dashboard launcher — invoked by project-root `make run`.
#
# Semantics (ported from hive task112_start_pg_demo.sh):
#   * repo root is derived from this script's location (no hard-coded path)
#   * process-level database overrides are UNSET so the PostgreSQL settings in
#     `.env` win (the dashboard loads `.env` itself via load_dotenv)
#   * PROVIDER is forced to `mock` and the trading journal to `memory`
#   * settings live in a fresh throwaway temp dir; incremental sync is off
#   * historical backtest data (sealed Datasets) is read from the repo's
#     `data/backtest` so PostgreSQL-bound Datasets stay discoverable; an
#     inherited BACKTEST_DATA_DIR is never honoured (explicit override below)
#   * this script never prints DSNs/credentials, never creates a database and
#     never mutates repository files
#
# Overrides:
#   TW_DASHBOARD_BACKTEST_DATA_DIR  historical data root handed to the dashboard
#                                   as BACKTEST_DATA_DIR (default: <repo>/data/backtest;
#                                   must already exist; relative paths resolve
#                                   against the invoking directory)
#   TW_DASHBOARD_PYTHON             interpreter to exec (default: <repo>/.venv/bin/python)
#   TMPDIR                          parent for the throwaway settings directory
set -euo pipefail

invoke_dir="$PWD"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$script_dir/.." && pwd)"
cd "$repo"

python_bin="${TW_DASHBOARD_PYTHON:-$repo/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  echo "找不到可執行的 Python：${python_bin}（預期為 ${repo}/.venv/bin/python）" >&2
  exit 1
fi

# Historical backtest data root. Only the explicit TW_DASHBOARD_* override is
# honoured; an inherited BACKTEST_DATA_DIR is replaced so a stray shell export
# cannot silently point the dashboard at an empty directory.
if [[ -n "${TW_DASHBOARD_BACKTEST_DATA_DIR:-}" ]]; then
  data_dir_source="TW_DASHBOARD_BACKTEST_DATA_DIR"
  requested_data_dir="$TW_DASHBOARD_BACKTEST_DATA_DIR"
  [[ "$requested_data_dir" == /* ]] || requested_data_dir="${invoke_dir%/}/$requested_data_dir"
else
  data_dir_source="預設值"
  requested_data_dir="$repo/data/backtest"
fi
if [[ ! -d "$requested_data_dir" ]]; then
  echo "歷史回測資料目錄不存在或不是目錄：${requested_data_dir}（來源：${data_dir_source}）" >&2
  echo "請確認 <repo>/data/backtest 已有 sealed Dataset，或以 TW_DASHBOARD_BACKTEST_DATA_DIR 指定既有目錄。" >&2
  exit 1
fi
backtest_data_dir="$(cd "$requested_data_dir" && pwd -P)"

manifest_count=0
for manifest in "$backtest_data_dir"/*/manifest.json; do
  [[ -f "$manifest" ]] && manifest_count=$((manifest_count + 1))
done

tmp_root="${TMPDIR:-/tmp}"
demo_dir="$(mktemp -d "${tmp_root%/}/tw-intraday-pg-dashboard.XXXXXX")"
echo "安全暫存目錄（settings）：$demo_dir"
echo "歷史回測資料目錄（BACKTEST_DATA_DIR，${data_dir_source}）：$backtest_data_dir"
echo "偵測到的歷史 Dataset manifest 數量：$manifest_count"
if [[ "$manifest_count" -eq 0 ]]; then
  echo "警告：資料目錄內沒有任何 */manifest.json，Dashboard 將看不到歷史 Dataset。" >&2
fi
if [[ ! -f "$repo/.env" ]]; then
  echo "警告：找不到 ${repo}/.env；Dashboard 需要其中的 PostgreSQL 設定才能啟動回測資料庫。" >&2
fi
echo "啟動後請開啟：http://127.0.0.1:8000/"

exec env \
  -u BACKTEST_DATABASE_BACKEND \
  -u BACKTEST_DATABASE_URL \
  -u DATABASE_URL \
  -u POSTGRESQL_DSN \
  -u PostgreSQL_DSN \
  -u TW_DASHBOARD_BACKTEST_DATA_DIR \
  PROVIDER=mock \
  TRADING_JOURNAL_BACKEND=memory \
  LOCAL_PAPER_SETTINGS_PATH="$demo_dir/settings-v1.json" \
  BACKTEST_DATA_DIR="$backtest_data_dir" \
  BACKTEST_INCREMENTAL_SYNC_ENABLED=false \
  "$python_bin" -m dashboard
