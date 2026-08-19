# Findings & Decisions

## Requirements

- The candidate list must be a visible sidebar function rather than content below the home overview.

## Research Findings

- `overview-view` currently contains both the home summary/premarket panel and the candidate list/detail dashboard grid.
- Workspace switching is local JavaScript in `setWorkspace`; candidate selection, rendering, and provider-backed history are independent of the overview workspace.
- The dedicated candidate workspace keeps the existing `candidate-list`, `candidate-detail`, and history behavior intact, so no API contract changes are needed.
- Home workspace copy now describes its actual scope: market summary, data health, and premarket context; it directs users to the candidate workspace for stock evaluation.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Add a `candidates` workspace | It uses the existing workspace pattern and avoids a new route or API. |
| Return to the invoking workspace after closing an order drawer | A simulated order started from candidate evaluation should not unexpectedly land on the home overview. |

## Issues Encountered
| Issue | Resolution |
|--------|------------|

## Resources

- `dashboard/static/index.html`
- `tests/test_backtest_dashboard_ui.py`
