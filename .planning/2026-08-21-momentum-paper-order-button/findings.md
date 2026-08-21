# Findings & Decisions

## Requirements
- Add a 「模擬下單」 button to the supplied momentum detail dialog.
- Clicking it should open the existing local-paper ticket, not create a new order form.
- Preserve the local-only simulation boundary and unrelated worktree changes.

## UI Findings
- The dialog header is owned by `dashboard/static/index.html`.
- Momentum dialog state and its current item are owned by `dashboard/static/js/workspaces/momentum.js`.
- The existing simulation module exports `openOrderTicket(symbol, price)` and is already registered in the shared `services` object.
- The header currently has only the close button; a small action group can contain the new button and close button.
- Mobile rules already make the dialog full-screen, so the action group must remain compact and the button label must stay visible.

## Interaction Contract
- Use `item.intraday.price.value` only when its status is `VALID`.
- Otherwise use `candidate.stock.price`; if neither exists, still prefill the symbol and let the user enter the limit price.
- Close the momentum dialog without restoring focus, then open the order ticket so its existing focus behavior takes over.

## Browser Evidence
- The Mock dashboard rendered the new button beside the close control without overlapping the title or body.
- Clicking it from the 3231 detail closed the dialog and opened the existing order drawer.
- The ticket values were `symbol=3231`, `side=BUY`, and `limit_price=176.50`, proving the valid intraday price took precedence over the 105.50 candidate snapshot.
