# Broker / Account Freshness Evidence: Read-only Intake

這是 broker/account evidence 的 intake 清單。它不新增 adapter、Portfolio
contract、API route 或 account polling；在 read-only source 另行核准前，它只用於
確認將來可以蒐集什麼證據。

## 授權前提

- 僅允許讀取 positions、orders、accounting 與 buying power。
- 禁止送出、取消、修改委託；禁止啟用 CA；禁止訂閱 order/deal callback 作為此
  calibration 的捷徑。
- 每個 source endpoint、帳戶 scope、環境（simulation/real data source）與
  permissions 必須由 owner 明確確認；不得從 quote login 假設 account read 可用。
- Artifact 不得保存 credential、完整 account number、委託內容或交易明細。只保存
  review 所需的時間／狀態 metadata 與可審核 source reference。

## 每個 read-only observation 的必要欄位

| 欄位 | 說明 |
|---|---|
| `probe_id` | 不可重複的 evidence observation id。 |
| `evidence_kind` | `POSITIONS`、`ORDERS`、`ACCOUNTING` 或 `BUYING_POWER`。 |
| `environment` | 已核准的 source environment；不可由 quote capture 推定。 |
| `source_reference` | 不含憑證與敏感帳號的 endpoint/version/reference。 |
| `request_started_at` | client 發起 read-only request 的 timezone-aware 時間。 |
| `response_received_at` | client 收到 provider response 的 timezone-aware 時間。 |
| `source_as_of_at` | provider 明確提供的資料 as-of；若未提供必須為 `null` 並標示缺失。 |
| `projection_updated_at` | read-only response 寫入 calibration projection 的時間；若尚未有 projection，不得偽造。 |
| `outcome` | `SUCCESS`、`TIMEOUT`、`AUTH_DENIED`、`RATE_LIMITED`、`SOURCE_ERROR` 或 `PARSE_ERROR`。 |
| `error_class` | 成功為 `null`；失敗時只記錄可審核的 error class，不記 token 或 response body。 |

## Evidence-kind 對應

| Evidence kind | 只可支持的後續 threshold |
|---|---|
| `POSITIONS` | `broker_positions_stale_after_ms` |
| `ORDERS` | `broker_orders_stale_after_ms` |
| `ACCOUNTING` | `broker_accounting_stale_after_ms` |
| `BUYING_POWER` | `buying_power_stale_after_ms` |

四類 observation 必須分別分析。不能以其中一類 response time、quote latency、或
UI polling interval 推導另一類 threshold。

## Intake review gate

開始實作任何 read-only capture 前，reviewer 必須確認：

1. source 的 execution/accounting authority 與 environment。
2. endpoint 能提供或不能提供 `source_as_of_at` 的事實。
3. authorization scope 不含任何 mutation 或 callback side effect。
4. rate-limit、timeout、維護時段和資料延遲的 evidence source。
5. artifact retention、redaction 與 integrity digest 作法。

完成這些 intake 項目不會解除 `FreshnessPolicyV1` blocker；它只使下一輪
read-only evidence capture 可以在不擴張 Portfolio scope 的條件下開始。
