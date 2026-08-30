# Project-root convenience targets for tw_intraday_trader.
#
#   make run   Start the local PostgreSQL Dashboard safely (mock provider,
#              in-memory journal, throwaway settings dir, process-level DB env
#              overrides cleared so `.env` PostgreSQL settings win). Historical
#              backtest data is read from <repo>/data/backtest by default so
#              PostgreSQL-bound sealed Datasets stay visible; override with
#              `make run TW_DASHBOARD_BACKTEST_DATA_DIR=/existing/dir`.
#              Semantics live in scripts/run_local_dashboard.sh.

.PHONY: run

run:
	bash scripts/run_local_dashboard.sh
