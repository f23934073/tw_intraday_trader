# Findings & Decisions

## Requirements
- When Shioaji daily market-data traffic is exhausted, show the condition in the dashboard's upper-right status area.
- Preserve local-paper and market-data-only boundaries; do not add broker orders, account reads, CA, or trade subscriptions.
- Avoid repeated Snapshot/Kbar calls merely to discover quota status.
- Preserve the large unrelated dirty worktree.

## Research Findings
- Live evidence from the preceding diagnosis showed `remaining_bytes < 0`, while Shioaji Snapshot returned empty data. The badge should rely on `api.usage()`, not infer exhaustion from an empty candidate list.
- `ShioajiProvider.market_data_usage()` already normalizes connections, bytes used, limit bytes, and remaining bytes.
- The upper-right status area is `.topbar-actions` and currently owns the scan Snapshot pill plus the local-simulation transport pill.
- `DashboardService` owns the same Provider instance used by the scan, so a small `provider_usage()` read method can reuse the existing adapter without creating another Shioaji login.
- The dashboard snapshot is cached, while the app already has bounded polling hooks. Usage should therefore use its own small endpoint and refresh cadence rather than mutating the cached scan payload.
- Existing static tests already guard status markup, module ownership, and app initialization; focused service/API tests can use a fake usage-capable provider without importing the native SDK.
- The existing `.status` display rule would override the browser's default `hidden` behavior, so the new badge needs an explicit `[hidden] { display: none; }` rule.
- The main application entrypoint is cache-versioned; the version was advanced so a reload cannot reuse JavaScript that predates the warning.
- `get_momentum_dashboard_service()` independently calls `ShioajiMomentumStream.connect_from_env()` and is not governed by `PROVIDER=mock`. Browser startup therefore observed one Shioaji subscription lifecycle message despite the main page reporting MockProvider. This is pre-existing and outside the quota-badge change, but it matters when claiming an offline dashboard smoke.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Exhausted means a positive limit with `remaining_bytes <= 0` or `bytes_used >= limit_bytes` | Handles the observed negative remainder and avoids calling an unknown/zero limit exhausted. |
| Hide the Shioaji-specific badge for providers with no usage contract | Mock mode should remain truthful rather than displaying a false healthy Shioaji state. |
| Poll only while the document is visible and no more often than once per minute | Daily quota status does not require the two-second quote cadence. |

## Remaining Limitation
- The badge reads usage from the main DashboardService Provider. The separate Momentum WebSocket can still establish its own Shioaji market-data session from `.env`; unifying or disabling that lifecycle in Mock mode is a separate change.

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
- `market_data/provider.py`
- `dashboard/service.py`
- `dashboard/server.py`
- `dashboard/static/index.html`
- `dashboard/static/js/app.js`
- `dashboard/static/css/dashboard.css`
