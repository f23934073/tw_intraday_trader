# Mypy baseline — 2026-08-28

## Scope and configuration

- Plan: `CI-001`
- Source at measurement start: `18c08713e4bb953457ab531db133c96d2b9132dd` plus the completed Ruff-only cleanup
- Mypy: `2.3.1`
- Python target: `3.11`
- Files: `signals`, `features`, `atomic_strategies` (30 source files)
- All three packages retain `disallow_untyped_defs = true`.
- `market_data.*` uses `follow_imports = "silent"`: its type information remains available to the target packages, while errors inside that explicitly out-of-scope dependency do not expand this gate.

The first unrestricted import-following measurement reported 48 errors in 17 files: 46 in the three target packages plus 2 inside imported `market_data` modules. The formal three-package baseline is therefore 46 errors in 15 files.

## Errors by package

| Package | Errors | Files with errors | Checked files | Downgraded? |
|---|---:|---:|---:|---|
| `features` | 24 | 2 | 9 | No |
| `signals` | 13 | 4 | 7 | No |
| `atomic_strategies` | 9 | 9 | 14 | No |
| **Total** | **46** | **15** | **30** | **No** |

No package exceeded the plan's `>50` downgrade threshold.

## Errors by code

| Error code | Count | Resolution class |
|---|---:|---|
| `no-untyped-def` | 15 | Added concrete parameter and return annotations. |
| `operator` | 12 | Added explicit `Decimal` narrowing/casts and `None` guards without changing arithmetic. |
| `arg-type` | 9 | Made completed-bar Protocol attributes read-only and preserved structural typing. |
| `misc` | 6 | Typed the existing dynamic initializer calls and used distinct branch-local bar variables. |
| `assignment` | 4 | Declared the feature-result union and used branch-specific variables. |
| **Total** | **46** | |

## Concentration and repair

| File | Errors | Repair |
|---|---:|---|
| `features/engine.py` | 14 | Typed `FeatureSpecification`, declared the result union, and separated branch-local bar/source-as-of variables. |
| `features/ema.py` | 10 | Replaced tuple membership with explicit `is None` guards so mypy can narrow all EMA values. |
| `signals/momentum.py` | 5 | Typed signal component input/output and used static `Decimal` casts in predicates. |
| `signals/opening_momentum.py` | 5 | Same type-only predicate and component annotations as the limit-up evaluator. |
| `signals/momentum_state.py` | 2 | Typed `FeatureValue` and the existing dynamic initializer call. |
| Eight atomic entry implementations | 8 | Typed optional observed/threshold mappings. |
| `atomic_strategies/registry.py` | 1 | Typed the template tuple return. |
| `signals/projection.py` | 1 | Typed the existing dynamic initializer call. |

Completed-bar Protocol fields were expressed as read-only properties in `features/{opening_range,ema,rsi,bollinger,rolling}.py`, matching their frozen dataclass implementations without narrowing the runtime-neutral Protocol API.

## Final result

`python -m mypy` reports `Success: no issues found in 30 source files`.

- No target package was downgraded.
- No new `type: ignore` comment was added.
- No runtime branch, calculation, serialization order, provider boundary, or trading behavior was changed.
