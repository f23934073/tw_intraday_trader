"""Non-formal, read-only institutional MVP utilities.

Layer:     L1-B (MVP Evaluation)
Lineage:   B  (institutional_data -> institutional_mvp -> backtest)
Depends:   institutional_data, backtest
Consumed:  config.institutional_mvp
Status:    NON_FORMAL

Lineage A (institutional_research -> institutional_prior) is a separate stack
and must not be imported from here. See
architecture/contracts/institutional_bounded_context.md.
"""
