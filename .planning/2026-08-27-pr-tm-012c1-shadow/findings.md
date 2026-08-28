# Findings: PR-TM-012C1 Shadow evidence 2026-08-27

- Prior automation memory says 2026-08-27 is a reviewed TWSE trading day, but this run must verify the current calendar artifact.
- Prior readiness audit found no reviewed 2026-08-27 canonical input bundle and a restricted sandbox that denied Shioaji loopback bind and both loopback PostgreSQL connections.
- Subsequent repository work added immutable review/promotion guards; current filesystem state must be rechecked without generating or modifying inputs.
- Production Shadow Gate begins and must remain `NOT_PASSED` for a single-day run.
- At 08:38:30 Asia/Taipei the run remained in the pre-open window.
- `config/twse_calendar_2026.json` is `twse_calendar_2026_v1`; 2026-08-27 is a Thursday within coverage and absent from annual/exceptional closure lists, so it is a reviewed trading day.
- `.env` has non-empty `LOCAL_PAPER_DATABASE_URL` and `TRADE_MANAGEMENT_SHADOW_DATABASE_URL` names; values were not exposed. C0/C1 will enforce actual connection and separation semantics.
- Canonical `research/trade_management_shadow/session_inputs/2026-08-27/` is absent. Only the legacy `PENDING_REVIEW`, `formal_c1_eligible=false` missing-source draft packet exists. This is already an independent hard C1 blocker.
- New intended artifacts `premarket_20260827.json` and `c1_20260827.json` plus sidecars are absent, so exclusive immutable targets are available.
- The reviewed C0 ran exactly once at prepared time 08:39:02+08:00 and exited 2 with status `BLOCKED`.
- Provider preflight failed closed with `LOOPBACK_BIND_DENIED`; identity is `shioaji:unknown:simulation=true`, login/logout are false, `subscribe_trade=false`, `execution_authority=false`, `execution_enabled=false`, and `evidence_only=true`.
- PostgreSQL reported configured but `connected=false`, `OPERATIONALERROR`, `transaction_read_only=false`, and no verified tables or migrations. Its zero row counts are not authoritative while disconnected.
- Fixture/historical rehearsal passed, but `qualifying_real_session=false`; it has no Production Shadow Gate effect.
- Readiness report digest/sidecar is `69d73ed4c59b95a9965adc2b347b39bb34c71f170ee9cb65dc1b2e3b587e6a3b`; artifact file SHA-256 is `5316d07cfdd8884761729ad87dce1a3bb21ef3ecf343fc45ec8d038b93b888d6`.
- C1 was not invoked. Market journal SHA-256, event/decision/journal counts, lost evidence, live replay parity, live recovery, checkpoint rebuild, and finalization are all `N/A`.
- Production Shadow Gate remains `NOT_PASSED`.
