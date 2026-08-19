from datetime import date
from pathlib import Path

from premarket.calendar import HistoricalContractResolver
from premarket.models import ContractIdentityStatus


FIXTURE = Path(__file__).parent / "fixtures" / "taifex_contract_roll_history.json"


def test_historical_contract_identity_uses_dated_mapping() -> None:
    resolver = HistoricalContractResolver.from_path(FIXTURE)

    identity = resolver.resolve(date(2026, 8, 18))

    assert identity.status is ContractIdentityStatus.RESOLVED_HISTORICALLY
    assert identity.resolved_contract_code == "TXF202608"
    assert identity.resolution_method == "DATED_CONTRACT_ROLL_MAPPING"


def test_missing_historical_mapping_stays_unresolved() -> None:
    resolver = HistoricalContractResolver.from_path(FIXTURE)

    identity = resolver.resolve(date(2025, 12, 31))

    assert identity.status is ContractIdentityStatus.UNRESOLVED
    assert identity.resolved_contract_code is None
    assert "TXFR1" not in identity.resolution_method
