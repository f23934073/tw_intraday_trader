# Local Paper Kill Switch durability runbook

## 適用範圍

本 runbook 只處理 `LOCAL_PAPER_SIMULATION` 的 automated-strategy Kill Switch。它不會自動 cancel、平倉或賣出，不會持久化一般 stop，也不會呼叫 Shioaji／券商下單、CA 或 trade callback。

唯一 durable truth 是既有 Trading Journal 的固定 control session：

- `session_id=local-paper-global-control-v1`
- `mode=LOCAL_PAPER_CONTROL`
- event kinds：`local_paper_kill_switch_engaged.v1`、`local_paper_kill_switch_reset.v1`
- `execution_boundary=LOCAL_ONLY`

PostgreSQL backend 才是 restart-safe。memory backend 只供開發與 focused tests，status 會明示 `durability=EPHEMERAL_MEMORY`、`restart_safe=false`。

## 操作前檢查

1. Dashboard 必須只綁 loopback；mutation 仍需符合 Host／Origin／CSRF 檢查。
2. 讀取 `GET /api/simulation/automated-strategy`，確認 `kill_switch.control_state`、`revision`、`durability`、`recovered` 與 `recovery_error`。
3. `RECOVERY_REQUIRED` 時不得送 reset。先停止 automated worker、保留 Journal，不得刪除或改寫 event，修復資料庫／contract 問題後重啟並重新 replay。
4. reset 必須使用畫面最新的 exact engaged revision；成功後 controller 仍是 `STOPPED / MANUAL_START_REQUIRED`。

## Engage／reset contract

Engage 使用 retry-stable key；相同 key 與相同 actor/reason 只回放原 receipt：

```json
{
  "actor_id": "local-operator",
  "idempotency_key": "kill-engage-unique-operation",
  "reason": "operator supplied incident reason"
}
```

Reset 必須包含 exact revision 與解除原因：

```json
{
  "actor_id": "local-operator",
  "idempotency_key": "kill-reset-unique-operation",
  "expected_revision": 3,
  "reason": "operator review completed"
}
```

HTTP 結果：新 transition `201`、相同 operation replay `200`、stale revision／conflicting retry `409`、格式錯誤 `422`、Journal/recovery unavailable `503`。

## PostgreSQL destructive UAT

UAT 會刪除 disposable database 的 `trading` schema，以及 legacy `public.journal_sessions`、`public.journal_records`、`public.projection_checkpoints`、`public.journal_schema_migrations` tables。只可提供明確的一次性 `TEST_POSTGRES_DSN`；資料庫名稱必須含獨立的 `test` token。例外情況需另外明示 `ALLOW_POSTGRES_TEST_SCHEMA_RESET=1`，不得對正式或共享資料庫使用。

```bash
TEST_POSTGRES_DSN='postgresql://REDACTED/disposable_test_db' \
  /path/to/pytest -q tests/test_kill_switch_postgres.py
```

測試覆蓋：fresh migrations、Process A engage、Process B restart recovery、first-status KILLED、start rejection、response-loss retry、conflicting retry、concurrent reaffirm、stale/exact reset、Process C stopped recovery、settings-session rotation、DB failure 與 replay corruption。

缺少 `TEST_POSTGRES_DSN` 時，pytest skip 只能算 `PostgreSQL destructive UAT = BLOCKED / NOT PASSED`，不能當 waiver 或完成證據。

## Evidence 記錄

保存以下非敏感摘要；不要保存 DSN、credential、account identifier、持倉或資金內容：

- candidate commit／worktree HEAD
- 完整命令（DSN 必須以 `REDACTED` 取代）
- UTC／Asia-Taipei 執行時間
- exit code、passed／failed／skipped counts
- control event kinds、revision、resulting state、Journal sequence
- Process B／C 第一個 status 摘要
- settings rotation 前後 revision
- concurrency 與 failure-injection 結果

## Recovery 與 rollback

- `RECOVERY_REQUIRED` 對 automated start/intent 等同 engaged，且一般 reset route 不可清除。
- engage 已成功但 controller checkpoint 失敗時，durable control event 仍是 authority；保持自動策略停止並調查 checkpoint。
- engaged／`RECOVERY_REQUIRED` 時不得回滾到不認得 control events 的舊版本。
- 回滾前需確認 controller stopped、沒有 automated worker／pending automated entry，且 authoritative state 已由正常 replay 得到 `DISENGAGED`。
- Journal event 永遠保留，不刪除、不重寫；修正採 forward-fix。
