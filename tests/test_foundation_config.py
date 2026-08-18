from dataclasses import FrozenInstanceError

import pytest

from config.foundation import (
    FOUNDATION_CONTRACT_VERSION,
    FOUNDATION_DEFAULTS,
    FOUNDATION_FEATURE_FLAGS,
    PersistentJournalAuthority,
    ProjectionTransport,
    WebExposure,
)


def test_foundation_defaults_document_the_approved_phase_zero_boundary() -> None:
    assert FOUNDATION_DEFAULTS.contract_version == FOUNDATION_CONTRACT_VERSION
    assert FOUNDATION_DEFAULTS.persistent_journal_authority is PersistentJournalAuthority.POSTGRESQL
    assert FOUNDATION_DEFAULTS.raw_capture_retention == "review_required"
    assert FOUNDATION_DEFAULTS.web_exposure is WebExposure.LOOPBACK_SINGLE_USER
    assert FOUNDATION_DEFAULTS.initial_projection_transport is ProjectionTransport.POLLING
    assert FOUNDATION_DEFAULTS.ci_python_versions == ("3.11", "3.12")
    assert FOUNDATION_DEFAULTS.pilot_symbols == ()


def test_foundation_feature_flags_are_all_disabled_and_immutable() -> None:
    assert not any(vars(FOUNDATION_FEATURE_FLAGS).values())

    with pytest.raises(FrozenInstanceError):
        FOUNDATION_FEATURE_FLAGS.journal_enabled = True  # type: ignore[misc]
