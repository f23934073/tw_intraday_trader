# R5 revision 2 Research Disposition

```text
Recorded at: 2026-08-26 (Asia/Taipei)
Gate: R5 revision 2 G5
Disposition: RESEARCH REJECT / HOLD / NOT ELIGIBLE
Lifecycle mutation: NONE
R6 authorization: NONE
Local Paper / Broker / Real-money: PROHIBITED
```

## Immutable evidence

- Baseline Run: `run-91ad87981676414da87b928398fa43c9`
- Replay: `replay-e70d205528ef4e5f891f3d6f3c99997a`
- Control contract: `r5-signal-ledger-replay-v2`
- Registration revision: `1`
- Result manifest digest:
  `420ef2dd3c3e814e0691eef0531c2c6f787789278675d092b86df3e1f9fa3347`
- Postflight digest:
  `ca041816dd69454ce53d321fa8a78cb0188a267d5ab2b7c864eb58051a557ad9`
- Accepted episodes / modeled entries / modeled exits:
  `128802 / 128802 / 128802`
- Provider calls / broker calls: `0 / 0`

## Primary decision metric

- Mean pre-slippage return: `-0.001356902463282666`
- Frozen decision rule: mean pre-slippage return `<= 0` means
  `above_vwap_entry` research reject and no further parameter tuning on the
  same Dataset.
- Rule result: `TRUE`.

## Secondary evidence

- Mean net return: `-0.008198722720797699`
- Median pre-slippage return: `-0.001620745542949757`
- Median net return: `-0.008461266957050243`
- Profit factor: `0.379778394606756598`
- Wins / losses / ties: `33629 / 95173 / 0`
- Pre-slippage price P&L: `-143770050`
- Explicit costs: `289116272.865185625`
- Net P&L: `-482357421.040185625`

## Decision

The exact `above_vwap_entry` plus session-close exit research protocol is
rejected. The allocation-neutral replay is negative before slippage and costs,
so transaction friction is not the root cause and cannot rescue the signal.

This decision is deliberately scoped:

- Record the Research disposition as `HOLD / NOT ELIGIBLE`; keep the Strategy
  Version lifecycle unchanged and do not promote it.
- Do not tune this strategy again on the same Dataset.
- Do not mutate Strategy lifecycle state, publish a new Version, or activate
  Local Paper.
- Do not interpret Replay acceptance as performance qualification.
- Do not open R6 automatically. Any independent atomic-strategy benchmark or
  portfolio-allocation study requires a separately frozen contract, explicit
  authorization, and new research evidence.

## Review state

```text
G5 disposition: RESEARCH REJECT / HOLD / NOT ELIGIBLE
G5 Formal Gate: APPROVED / PASSED
Formal progress: 100%
```
