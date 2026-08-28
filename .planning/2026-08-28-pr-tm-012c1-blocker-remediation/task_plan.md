# PR-TM-012C1 blocker remediation

## Goal

Make the next formal PR-TM-012C1 session admissible without weakening the data-only boundary or altering today's immutable BLOCKED evidence.

## Success criteria

1. Shioaji and both PostgreSQL connections have a reviewed unattended execution path that is not blocked by the Codex network sandbox.
2. Local Paper and Shadow DSNs remain explicit, distinct, least-privilege, and verifiably reachable from that path.
3. The next trading day's canonical input bundle is produced only from real candidate artifacts through the existing pending-review, human-approval, and promotion workflow.
4. No order/fill/match/Position/broker/CA/trade-callback capability is added.

## Phases

- [completed] Audit the current external-runner implementation/design, deployment prerequisites, DSN health, automation capabilities, and available input candidates.
- [completed] Implement the smallest remediation required for unattended provider and PostgreSQL access.
- [completed] Prepare a non-qualifying reviewed-input candidate packet for the next trading day if legitimate source artifacts exist. No packet was created because no legitimate sources exist.
- [completed] Verify operational readiness with host-side read-only PostgreSQL and provider simulation health checks without running a formal C0/C1 session.
- [completed] Report the remaining human input-review gate precisely.

## Decisions

- Today's `premarket_20260828.json` remains immutable and will not be retried or replaced.
- A draft packet can never substitute for human approval or canonical promotion.
- External host installation is a distinct state change and will be performed only if the reviewed prerequisites are satisfied and authority is explicit.

## Errors

- Official OpenAI documentation search did not surface a supported narrow automation loopback exception; local Codex capability and repo design still require direct inspection.
- Existing external deployment templates are intentionally installation-ineligible; enabling them as-is would weaken reviewed boundaries without restoring connectivity.
