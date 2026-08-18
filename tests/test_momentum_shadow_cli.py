from pathlib import Path

import pytest

from scripts.run_momentum_shadow import _validate_args, build_parser


def valid_args():
    return build_parser().parse_args(
        [
            "--account-subscription-limit",
            "200",
            "--reserved-headroom",
            "20",
            "--scanner-cadence-seconds",
            "10",
            "--scanner-count",
            "100",
            "--candidate-ttl-seconds",
            "30",
            "--scanner-min-observations",
            "2",
            "--queue-capacity",
            "4096",
            "--required-stream-max-age-seconds",
            "5",
            "--scanner-rank",
            "CHANGE_PERCENT",
            "--scanner-rank",
            "VOLUME",
        ]
    )


def test_shadow_cli_requires_explicit_capacity_cadence_and_scanner_inputs():
    args = valid_args()
    _validate_args(args)

    assert args.account_subscription_limit == 200
    assert args.reserved_headroom == 20
    assert args.scanner_rank == ["CHANGE_PERCENT", "VOLUME"]


def test_shadow_cli_rejects_scanner_count_above_provider_contract():
    args = valid_args()
    args.scanner_count = 201

    with pytest.raises(ValueError, match="between 1 and 200"):
        _validate_args(args)


def test_entire_shadow_entry_path_contains_no_execution_call():
    root = Path(__file__).parents[1]
    source = "\n".join(
        (root / path).read_text(encoding="utf-8")
        for path in (
            "scripts/run_momentum_shadow.py",
            "runtime/momentum_shadow.py",
            "market_data/shioaji_momentum_stream.py",
        )
    )

    assert "from trading" not in source
    assert "import trading" not in source
    assert "place_order" not in source
    assert "activate_ca" not in source
    assert "set_order_callback" not in source
