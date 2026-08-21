# Findings & Decisions

## Requirements

- Status is approved with conditions; begin implementation.
- PR-001 allowlist: `institutional_data/domain.py`, `serialization.py`, `validation.py`, package init, tests, and fixtures.
- Update the implementation plan to use contract-first JSON validation before migration/repository work.
- Explicitly exclude API, Dashboard, CandidatePool, strategy, migration, repository, official source adapter, and live ingestion.
- Preserve Candidate Prior != Entry Trigger, BuyScore isolation, look-ahead guards, PIT research boundary, evidence lineage, and real-money prohibition.
- Reviewer recommends the first research slice later prioritize flow rank/persistence/consensus, with momentum confirmation as the first combined candidate hypothesis.
- Add watchlist compression ratio, setup coverage, and daily monitoring load to later evaluation metrics.

## Research Findings

- Worktree already contains active freshness-calibration product/test/evidence changes and an untracked institutional implementation plan. They must be preserved and not reformatted or absorbed into this PR.
- The previous review established a minimal immutable row/partition contract, exact component formulas, explicit trade-scope identity, historical `usable_from_session`, and fail-closed validation.
- The reviewer rejects an early migration because factor/evaluation/artifact schemas may change; PR-001 should prove contract bytes and invariants using JSON only.
- Existing immutable contracts use frozen dataclasses, `StrEnum`, timezone-aware timestamps, integer volume/share units, Decimal-safe canonical JSON, and SHA256 content identities. PR-001 should match these conventions rather than introduce a validation library.
- Existing domain models put impossible single-object states in `__post_init__`; reconciliation and source-quality failures are evaluated separately. Institutional rows should follow the same split.
- `pyproject.toml` uses an explicit package include allowlist and does not contain `institutional_data*`. Adding the package without one surgical include change would work in the checkout but be absent from built distributions.
- Existing canonical serializers are owned by `premarket` or `backtest`; importing either would invert bounded-context ownership. PR-001 needs a small institutional serializer rather than cross-domain coupling.
- Reviewer changes were integrated into the architecture plan: PR-001 is JSON contract-only; migration moves after schema checkpoints; `ResearchRunManifest v0` precedes the formal composite manifest; first diagnostics are foreign/trust rank-persistence-consensus; momentum confirmation becomes the first combined hypothesis; evaluation gains compression, setup coverage, monitoring load, and successful no-trade outcomes.
- First diff review found three bounded correctness gaps: a directly constructed scope decision could contradict its status/reasons, date parsers could hide a wrong JSON type behind a generic ISO error, and partition validation did not compare row retrieval/first-observed timestamps with the manifest.
- Second review found the public canonical serializer could hash a naive `datetime` even though all institutional timestamps require timezone provenance; it now fails closed instead.
- Plan/code reconciliation found the earlier long-term contract still showed per-row source schema/digest fields and a formal-size manifest. The plan now documents the exact PR-001 v1 bytes and defers source/parser/coverage/research fields through explicit future schema versions.
- No persistence, network, runtime, strategy, API, UI, CandidatePool, or broker dependency entered the new package.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Separate constructor invariants from batch validation | A row object should never be structurally invalid; cross-row/partition reconciliation belongs in a pure validation report. |
| Canonical JSON uses sorted keys, compact separators, UTF-8, and string Decimals | Stable SHA256 and no binary-float drift. |
| Scope compatibility is explicit, not inferred from provider names | Ratio eligibility depends on included/excluded trade classes and correction policy. |
| No generic research-feature framework in PR-001 | It would be speculative and violates the smallest approved slice. |
| Add only `institutional_data*` to package discovery | Packaging is a necessary part of adding the approved package, not a new feature surface. |
| Model a finite trade-scope set plus explicit compatibility decision | This makes compatible/incompatible/unknown deterministic without binding the domain to a provider adapter. |
| Keep raw parser fixtures out of PR-001 | The approved slice validates normalized contract artifacts; official HTML/JSON parser fixtures begin in PR-002. |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| The attachment's `My request` field is blank | The attached text itself explicitly authorizes formal work and restricts the first PR, so implementation proceeds under that narrow scope. |

## Resources

- Reviewer feedback: `/Users/stevehuang-work/.codex/attachments/944a527f-2659-4971-9fc7-426af2ef40ba/pasted-text.txt`
- Approved plan: `architecture/institutional_premarket_candidate_implementation_plan.md`
- Repository: `/Users/stevehuang-work/Documents/tw_intraday_trader`
