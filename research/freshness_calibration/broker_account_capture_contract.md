# Broker / Account Freshness Capture Contract

## Scope

此工具只為 `FreshnessPolicyV1` 的 broker/account evidence 蒐證。它不是
Portfolio adapter、帳務 projection 或委託服務，也不會凍結任何 threshold。

每次 capture 僅限一個已登入的股票帳戶範圍，且必須符合以下 guardrails：

- `subscribe_trade=False`
- 不送出、取消或修改委託
- 不啟用 CA
- 不註冊 order/deal callback
- 不呼叫 `update_status`
- endpoint 失敗不重試
- response 只投影為 redacted metadata；不得寫入憑證、帳號、持倉、餘額、損益或委託明細

## Evidence grain

一個 provider endpoint call 是一筆 observation，保存：

- `request_started_at`、`response_received_at`、`projection_updated_at`
- 單調時鐘計算出的 `round_trip_ms`
- provider 明確提供時才保存 `source_as_of_at`；只有 business date 時必須標記
  `DATE_ONLY_NOT_AS_OF`，不可把它當 source freshness
- endpoint 形狀（container type、row count、field names），不保存 values
- `outcome`、sanitized `error_class`、capability disposition

| Evidence kind | Read-only source | 目前 disposition |
|---|---|---|
| `POSITIONS` | `api.list_positions` | 可以蒐集 response-timing/as-of availability evidence |
| `ACCOUNTING` | `api.list_profit_loss` | 可以蒐集 response-timing/as-of availability evidence |
| `BUYING_POWER` | `api.account_balance` | 呼叫可確認 account-balance endpoint，但不當成 documented buying power；不可選 threshold |
| `ORDERS` | `api.update_status` + `api.list_trades` | 不呼叫；需要 action-like refresh，於本授權下保留 constrained gap |

`ORDERS` gap 與 `BUYING_POWER` limitation 都是有意保留的 evidence 結果，不能以
quote cadence、UI polling、account balance 或 local cache 補推 threshold。

## Artifact and review

Artifacts 寫入 `research/captures/freshness_broker_account/`，使用 exclusive create
並可用 inspector 取得 SHA-256。每個 artifact 都含完整禁用 guardrails 與
`threshold_selection=PROHIBITED_IN_CAPTURE_ARTIFACT`。

一次 capture 只證明一個時間點的 endpoint behaviour。必須在交易時段跨交易日重複
蒐集、檢查 error/timeout/schema/as-of availability，再由 reviewer 決定是否有足夠
evidence 凍結每一類 threshold。直到八個 threshold 都已 review 並 FROZEN，
`FreshnessPolicyV1` 仍是 `BLOCKING_EVIDENCE`，Portfolio Phase 1 仍被封鎖。
