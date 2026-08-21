# Task Plan: Momentum Detail Paper Order Button

## Goal
Add a visible, accessible 「模擬下單」 button to the momentum detail header that reuses the existing local-paper order ticket and pre-fills the current symbol and best available displayed price.

## Current Phase
Complete

## Phases

### Phase 1: Discovery
- [x] Inspect the supplied screenshot and locate the momentum detail dialog.
- [x] Trace the existing `openOrderTicket(symbol, price)` entrypoint and module dependencies.
- [x] Confirm unrelated dirty-worktree changes must be preserved.
- **Status:** complete

### Phase 2: Implementation
- [x] Add the header action and responsive styling.
- [x] Route the action to the existing simulation workspace with symbol and price.
- [x] Update focused UI contracts.
- **Status:** complete

### Phase 3: Verification
- [x] Run focused UI and JavaScript checks.
- [x] Run the relevant regression suite.
- [x] Verify the interaction in the local browser.
- **Status:** complete

### Phase 4: Delivery
- [x] Summarize behavior and verification.
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Place the action beside the close button | Matches the user's highlighted header area and keeps the primary action visible without scrolling. |
| Reuse `services.openOrderTicket` | Keeps one simulation form and one submission path. |
| Prefer a valid intraday price, then candidate snapshot price | Uses the freshest displayed evidence without inventing a price. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Local browser-test server could not bind port 8011 in the sandbox | Use scoped localhost permission; no product files were affected. |
| Final progress patch used a stale sentence | Re-read the isolated plan and applied the status update against the current text. |
