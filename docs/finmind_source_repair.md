# FinMind source-repair workflow

This workflow preserves the original FinMind acquisition response and adds an
auditable overlay only after independent minute-level evidence is reviewed.
It never converts daily OHLC into a one-minute bar.

## Lifecycle

1. `QUARANTINED`: an `EMPTY` or `INVALID` FinMind partition conflicts with
   trusted reference evidence. The original row, raw response, and digests stay
   unchanged.
2. `PENDING_REVIEW`: an alternate source supplies raw evidence plus canonical
   minute bars with explicit exchange-local timestamps, `COMMON_LOTS` volume,
   and observable minute-end semantics.
3. `APPROVED`: a named reviewer approves the exact raw and canonical evidence
   digests with a written rationale.
4. `ACTIVE`: a separate actor activates that exact approval. Dataset snapshot
   identity then includes the repair lineage and the issue code
   `ALTERNATE_SOURCE_REPAIR`.

Any non-active case makes the affected symbol fail closed with
`SOURCE_REPAIR_PENDING` during FinMind snapshot planning. An active overlay is
read from the repair tables; `finmind_history_partitions` is never overwritten.

## Current quarantined case

- Case: `finmind-repair-9f08aa0024440e4601ac`
- Target: `finmind-sponsor-864f26b849120817 / 9960 / 2026-03-20`
- Reason: `OFFICIAL_PRICE_FINMIND_EMPTY`
- Evidence: `research/finmind_source_repair_9960_20260320_tpex_daily_v1.json`
- State: `QUARANTINED`
- Result: 9960 stays excluded until a timestamped minute source is proposed,
  reviewed, and activated.

## Commands

Inspect and audit without provider access:

```bash
.venv/bin/python scripts/manage_finmind_source_repair.py \
  --database data/finmind_sponsor/history.sqlite3 \
  status --case-id finmind-repair-9f08aa0024440e4601ac

.venv/bin/python scripts/manage_finmind_source_repair.py \
  --database data/finmind_sponsor/history.sqlite3 audit
```

Propose alternate minute evidence. `raw-response.json` is the unmodified source
response. `canonical-bars.json` is a JSON array of `HistoricalBar.to_dict()`
objects with explicit timestamps and `session_date`.

```bash
.venv/bin/python scripts/manage_finmind_source_repair.py \
  --database data/finmind_sponsor/history.sqlite3 \
  propose-minute \
  --case-id finmind-repair-9f08aa0024440e4601ac \
  --source-name ALTERNATE_PROVIDER \
  --source-uri 'https://provider.example/source-record' \
  --observed-at 2026-08-27T09:00:00+08:00 \
  --evidence-file raw-response.json \
  --bars-file canonical-bars.json
```

Review the exact candidate returned by the proposal:

```bash
.venv/bin/python scripts/manage_finmind_source_repair.py \
  --database data/finmind_sponsor/history.sqlite3 \
  review \
  --case-id finmind-repair-9f08aa0024440e4601ac \
  --evidence-id REPLACE_WITH_CANDIDATE_EVIDENCE_ID \
  --decision APPROVE \
  --reviewer REVIEWER_ID \
  --rationale 'verified source, timestamps, OHLCV, units, and session bounds'
```

Activation is a separate transition and must reference the returned approval:

```bash
.venv/bin/python scripts/manage_finmind_source_repair.py \
  --database data/finmind_sponsor/history.sqlite3 \
  activate \
  --case-id finmind-repair-9f08aa0024440e4601ac \
  --review-id REPLACE_WITH_APPROVAL_REVIEW_ID \
  --actor DATASET_CURATOR_ID \
  --change-note 'activate reviewed minute overlay for the next snapshot plan'
```

Run `audit` after every transition. Do not activate evidence sourced only at
daily grain, missing raw bytes, lacking timezone-aware minute timestamps, using
an unknown volume unit, or failing target/session/digest validation.

## Current credential safety block

The next candidate source is Fugle Historical Candles, evaluated only for the
single quarantined `9960 / 2026-03-20` case. The offline normalizer converts
Fugle start labels to observable minute-end labels and requires exact TPEx daily
OHLC, total-volume, and turnover reconciliation before producing candidate
bars.

The configured Fugle credential was disclosed in tool output during discovery.
It is prohibited from use, and no Shioaji or other credential fallback is
allowed. The durable block record is
`research/finmind_source_repairs/9960_20260320_credential_rotation_block_v1.json`.
Do not run `scripts/capture_fugle_source_repair_candidate.py` until the owner
has revoked or rotated the key, configured the replacement without displaying
it, and explicitly resumed the single-target capture. The case remains
`QUARANTINED`; this block is not an approval or activation.

The owner confirmed rotation and explicitly resumed the single-target capture
at `2026-08-27T09:42:55+08:00`. The secret-free confirmation is recorded in
`research/finmind_source_repairs/9960_20260320_fugle_credential_rotation_v1.json`.
The capture command requires that record and freezes its canonical digest into
the request metadata; the credential value remains environment-only.

One bounded Fugle request was captured in
`research/finmind_source_repairs/fugle_9960_20260320_v1`. Fugle returned one
start-labelled bar at 10:55 with OHLC 22.9 and one common lot. Because TPEx
reports exactly one transaction, 1,000 shares, and NT$22,900, the offline
candidate gate can prove the amount exactly even though Fugle omitted the
requested `turnover` field. The source omission remains explicit in validation.

The derived candidate is in
`research/finmind_source_repairs/fugle_9960_20260320_candidate_v1` and converts
the established start label to observable minute end 10:56. Evidence
`finmind-repair-evidence-ac310a47f4e804507a79` is now `PENDING_REVIEW`.
It has not been approved or activated, and 9960 remains excluded from Dataset
snapshots until those separate transitions are explicitly authorized.
