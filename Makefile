# Project-root convenience targets for tw_intraday_trader.
#
#   make run   Start the local PostgreSQL Dashboard safely (mock provider,
#              in-memory journal, throwaway settings/data dirs, process-level
#              DB env overrides cleared so `.env` PostgreSQL settings win).
#              Semantics live in scripts/run_local_dashboard.sh.

.PHONY: run

run:
	bash scripts/run_local_dashboard.sh
