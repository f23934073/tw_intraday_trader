from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from runtime.trade_management_artifact_io import require_complete_artifact_pair
from runtime.trade_management_input_loading import (
    parse_risk_snapshot_document,
    require_risk_snapshot_capture_window,
)
from runtime.trade_management_runtime_identity import runtime_code_identity
from scripts import prepare_trade_management_shadow_inputs as prepare_cli
from scripts import promote_trade_management_shadow_inputs as promote_cli
from scripts import review_trade_management_shadow_inputs as review_cli
from scripts import run_trade_management_shadow_c1 as c1_cli
from tests.test_live_entry_thesis_draft import decision, policy
from trading.live_entry_thesis_draft import LiveTradeThesisDraftBuilder
from trading.trade_management_serialization import (
    serialize_live_entry_decision,
    serialize_trade_thesis_draft,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def _output(project_root: Path, market_date: str, attempt_id: str) -> Path:
    return (
        project_root
        / "research"
        / "trade_management_shadow"
        / "session_input_drafts"
        / market_date
        / "attempts"
        / attempt_id
        / "review_packet.json"
    )


def _approval_output(project_root: Path, market_date: str, attempt_id: str) -> Path:
    return (
        project_root
        / "research"
        / "trade_management_shadow"
        / "session_input_approvals"
        / market_date
        / "attempts"
        / attempt_id
        / "review_approval.json"
    )


def _write_candidate_sources(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True)
    entry = decision()
    draft = LiveTradeThesisDraftBuilder().build(entry, policy())
    paths = {
        "entry_decision": root / "live_entry_decision.json",
        "thesis_draft": root / "trade_thesis_draft.json",
        "shadow_policy": root / "shadow_policy.json",
        "risk_snapshot": root / "risk_snapshot.json",
    }
    paths["entry_decision"].write_text(serialize_live_entry_decision(entry))
    paths["thesis_draft"].write_text(serialize_trade_thesis_draft(draft))
    paths["shadow_policy"].write_text(
        json.dumps(
            {
                "exit_policy_version": "thesis-exit-policy-v1",
                "risk_policy": {
                    "version": "risk-v1",
                    "allow_strategy_origin": False,
                    "max_order_notional": "200000",
                    "max_position_notional": "300000",
                    "max_daily_loss": "50000",
                    "fresh_book_sides": ["BUY", "SELL"],
                },
                "volume_baseline_shares": "1000",
                "shares_per_lot": 1000,
                "remaining_quantity_shares": 1000,
                "fill_model_version": "shadow-observation-no-fill-v1",
            },
            sort_keys=True,
        )
    )
    paths["risk_snapshot"].write_text(
        json.dumps(
            {
                "data_health_state": "HEALTHY",
                "market_open": True,
                "instrument_tradable": True,
                "available_cash": "0",
                "current_position_shares": 1000,
                "pending_buy_shares": 0,
                "pending_sell_shares": 0,
                "daily_realized_pnl": "-999999",
                "book_age_seconds": 0,
                "provenance": {
                    "version": "trade-management-risk-snapshot-provenance-v1",
                    "session_id": entry.session_id,
                    "symbol": entry.symbol,
                    "market_date": entry.signal_at.value.date().isoformat(),
                    "captured_at": entry.signal_at.value.replace(
                        hour=8,
                        minute=30,
                        second=0,
                        microsecond=0,
                    ).isoformat(),
                    "source_identity": "reviewed-local-paper-risk-snapshot:test",
                },
            },
            sort_keys=True,
        )
    )
    return paths


def test_missing_sources_create_pending_packet_without_canonical_inputs(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(prepare_cli, "PROJECT_ROOT", tmp_path)
    output = _output(tmp_path, "2026-08-27", "missing-sources-01")

    result = prepare_cli.main(
        [
            "--market-date",
            "2026-08-27",
            "--attempt-id",
            "missing-sources-01",
            "--output",
            str(output),
        ]
    )

    assert result == 2
    packet = json.loads(output.read_text())
    assert packet["status"] == "PENDING_REVIEW"
    assert packet["reviewed"] is False
    assert packet["formal_c1_eligible"] is False
    assert packet["candidate_valid"] is False
    assert packet["attempt_id"] == "missing-sources-01"
    assert packet["blockers"] == [
        "MISSING_SOURCE:entry_decision",
        "MISSING_SOURCE:risk_snapshot",
        "MISSING_SOURCE:shadow_policy",
        "MISSING_SOURCE:thesis_draft",
    ]
    assert not (
        tmp_path
        / "research"
        / "trade_management_shadow"
        / "session_inputs"
        / "2026-08-27"
    ).exists()
    sidecar = output.with_suffix(".json.sha256")
    assert len(sidecar.read_text().strip()) == 64


def test_valid_candidates_are_bound_but_remain_pending_review(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(prepare_cli, "PROJECT_ROOT", tmp_path)
    sources = _write_candidate_sources(tmp_path / "source")
    output = _output(tmp_path, "2026-08-20", "candidate-01")

    result = prepare_cli.main(
        [
            "--market-date",
            "2026-08-20",
            "--attempt-id",
            "candidate-01",
            "--entry-decision-source",
            str(sources["entry_decision"]),
            "--thesis-draft-source",
            str(sources["thesis_draft"]),
            "--shadow-policy-source",
            str(sources["shadow_policy"]),
            "--risk-snapshot-source",
            str(sources["risk_snapshot"]),
            "--output",
            str(output),
        ]
    )

    assert result == 0
    packet = json.loads(output.read_text())
    assert packet["status"] == "PENDING_REVIEW"
    assert packet["candidate_valid"] is True
    assert packet["blockers"] == []
    assert packet["reviewed"] is False
    assert packet["review_approval"] is None
    assert packet["formal_c1_eligible"] is False
    assert packet["binding"]["session_id"] == decision().session_id
    assert packet["binding"]["symbol"] == decision().symbol
    assert set(packet["candidate_sources"]) == {
        "entry_decision",
        "thesis_draft",
        "shadow_policy",
        "risk_snapshot",
    }
    assert all(
        len(item["sha256"]) == 64
        for item in packet["candidate_sources"].values()
    )


def test_draft_packet_cannot_be_written_to_canonical_input_directory(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(prepare_cli, "PROJECT_ROOT", tmp_path)
    output = (
        tmp_path
        / "research"
        / "trade_management_shadow"
        / "session_inputs"
        / "2026-08-27"
        / "review_packet.json"
    )

    with pytest.raises(ValueError, match="REVIEW_PACKET_PATH_MISMATCH"):
        prepare_cli.main(
            [
                "--market-date",
                "2026-08-27",
                "--attempt-id",
                "unsafe-01",
                "--output",
                str(output),
            ]
        )
    assert not output.exists()


def test_c1_accepts_only_exact_canonical_input_paths_and_approval(tmp_path) -> None:
    market_date = decision().signal_at.value.date()
    expected = tmp_path / "session_inputs" / market_date.isoformat()
    args = SimpleNamespace(
        entry_decision=expected / "live_entry_decision.json",
        thesis_draft=expected / "trade_thesis_draft.json",
        shadow_policy=expected / "shadow_policy.json",
        risk_snapshot=expected / "risk_snapshot.json",
        input_approval=expected / "review_approval.json",
    )
    c1_cli._require_canonical_input_paths(
        args,
        market_date=market_date,
        session_inputs_root=tmp_path / "session_inputs",
    )

    args.entry_decision = tmp_path / "session_input_drafts" / "candidate.json"
    with pytest.raises(RuntimeError, match="C1_CANONICAL_INPUT_PATH_MISMATCH"):
        c1_cli._require_canonical_input_paths(
            args,
            market_date=market_date,
            session_inputs_root=tmp_path / "session_inputs",
        )


def test_distinct_attempts_are_immutable_and_retryable(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(prepare_cli, "PROJECT_ROOT", tmp_path)
    first = _output(tmp_path, "2026-08-27", "missing-01")
    second = _output(tmp_path, "2026-08-27", "missing-02")

    assert prepare_cli.main(
        [
            "--market-date",
            "2026-08-27",
            "--attempt-id",
            "missing-01",
            "--output",
            str(first),
        ]
    ) == 2
    assert prepare_cli.main(
        [
            "--market-date",
            "2026-08-27",
            "--attempt-id",
            "missing-02",
            "--output",
            str(second),
        ]
    ) == 2
    with pytest.raises(FileExistsError):
        prepare_cli.main(
            [
                "--market-date",
                "2026-08-27",
                "--attempt-id",
                "missing-01",
                "--output",
                str(first),
            ]
        )


def test_candidate_files_are_read_once_for_digest_and_validation(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(prepare_cli, "PROJECT_ROOT", tmp_path)
    sources = _write_candidate_sources(tmp_path / "source")
    resolved_sources = {path.resolve() for path in sources.values()}
    read_counts = {path: 0 for path in resolved_sources}
    original = Path.read_bytes

    def counted_read(path: Path) -> bytes:
        resolved = path.resolve()
        if resolved in read_counts:
            read_counts[resolved] += 1
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read)
    output = _output(tmp_path, "2026-08-20", "single-read-01")
    result = prepare_cli.main(
        [
            "--market-date",
            "2026-08-20",
            "--attempt-id",
            "single-read-01",
            "--entry-decision-source",
            str(sources["entry_decision"]),
            "--thesis-draft-source",
            str(sources["thesis_draft"]),
            "--shadow-policy-source",
            str(sources["shadow_policy"]),
            "--risk-snapshot-source",
            str(sources["risk_snapshot"]),
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert set(read_counts.values()) == {1}


def test_review_then_promotion_binds_canonical_inputs_and_c1_approval(
    monkeypatch,
    tmp_path,
) -> None:
    for cli in (prepare_cli, review_cli, promote_cli, c1_cli):
        monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    sources = _write_candidate_sources(tmp_path / "source")
    packet = _output(tmp_path, "2026-08-20", "approved-01")
    approval = _approval_output(tmp_path, "2026-08-20", "approved-01")
    canonical = (
        tmp_path
        / "research"
        / "trade_management_shadow"
        / "session_inputs"
        / "2026-08-20"
    )
    assert prepare_cli.main(
        [
            "--market-date",
            "2026-08-20",
            "--attempt-id",
            "approved-01",
            "--entry-decision-source",
            str(sources["entry_decision"]),
            "--thesis-draft-source",
            str(sources["thesis_draft"]),
            "--shadow-policy-source",
            str(sources["shadow_policy"]),
            "--risk-snapshot-source",
            str(sources["risk_snapshot"]),
            "--output",
            str(packet),
        ]
    ) == 0
    assert review_cli.main(
        [
            "--review-packet",
            str(packet),
            "--reviewer-id",
            "human-reviewer-01",
            "--reviewed-at",
            "2026-08-20T08:31:00+08:00",
            "--review-note",
            "Reviewed source provenance and policy bindings.",
            "--output",
            str(approval),
        ]
    ) == 0
    assert not canonical.exists()
    assert promote_cli.main(
        [
            "--review-approval",
            str(approval),
            "--output-dir",
            str(canonical),
        ]
    ) == 0
    args = SimpleNamespace(
        entry_decision=canonical / "live_entry_decision.json",
        thesis_draft=canonical / "trade_thesis_draft.json",
        shadow_policy=canonical / "shadow_policy.json",
        risk_snapshot=canonical / "risk_snapshot.json",
        input_approval=canonical / "review_approval.json",
    )
    c1_cli._require_canonical_input_paths(
        args,
        market_date=decision().signal_at.value.date(),
        session_inputs_root=canonical.parent,
    )
    canonical_sources = {
        (canonical / filename).resolve() for filename in c1_cli.SOURCE_FILENAMES.values()
    }
    read_counts = {path: 0 for path in canonical_sources}
    original_read_bytes = Path.read_bytes

    def counted_canonical_read(path: Path) -> bytes:
        resolved = path.resolve()
        if resolved in read_counts:
            read_counts[resolved] += 1
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counted_canonical_read)
    verified, source_contents, bundle = c1_cli._load_and_verify_input_approval(
        args,
        market_date=decision().signal_at.value.date(),
    )
    assert verified["reviewer_id"] == "human-reviewer-01"
    assert verified["formal_c1_eligible"] is True
    assert set(source_contents) == set(c1_cli.SOURCE_FILENAMES)
    assert bundle["approval_digest"] == verified["approval_digest"]
    assert set(read_counts.values()) == {1}

    original_packet = original_read_bytes(packet)
    tampered_packet = json.loads(original_packet)
    tampered_packet["binding"]["symbol"] = "2317"
    packet.write_text(json.dumps(tampered_packet), encoding="utf-8")
    with pytest.raises(RuntimeError, match="ARTIFACT_CANONICAL_DIGEST_MISMATCH"):
        c1_cli._load_and_verify_input_approval(
            args,
            market_date=decision().signal_at.value.date(),
        )

    packet.write_bytes(original_packet)
    bundle_lock = canonical / "bundle_manifest.json.write.lock"
    bundle_lock.write_text("INCOMPLETE_ARTIFACT_PAIR\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="INCOMPLETE_ARTIFACT_PAIR"):
        c1_cli._load_and_verify_input_approval(
            args,
            market_date=decision().signal_at.value.date(),
        )


def test_promotion_rejects_source_changed_after_review(monkeypatch, tmp_path) -> None:
    for cli in (prepare_cli, review_cli, promote_cli, c1_cli):
        monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    sources = _write_candidate_sources(tmp_path / "source")
    packet = _output(tmp_path, "2026-08-20", "tamper-01")
    approval = _approval_output(tmp_path, "2026-08-20", "tamper-01")
    prepare_cli.main(
        [
            "--market-date", "2026-08-20",
            "--attempt-id", "tamper-01",
            "--entry-decision-source", str(sources["entry_decision"]),
            "--thesis-draft-source", str(sources["thesis_draft"]),
            "--shadow-policy-source", str(sources["shadow_policy"]),
            "--risk-snapshot-source", str(sources["risk_snapshot"]),
            "--output", str(packet),
        ]
    )
    review_cli.main(
        [
            "--review-packet", str(packet),
            "--reviewer-id", "human-reviewer-01",
            "--reviewed-at", "2026-08-20T08:31:00+08:00",
            "--review-note", "Reviewed before tamper.",
            "--output", str(approval),
        ]
    )
    sources["shadow_policy"].write_text(
        sources["shadow_policy"].read_text() + " ",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="APPROVED_SOURCE_DIGEST_MISMATCH"):
        promote_cli.main(
            [
                "--review-approval", str(approval),
                "--output-dir", str(
                    tmp_path
                    / "research/trade_management_shadow/session_inputs/2026-08-20"
                ),
            ]
        )


def test_risk_snapshot_provenance_mismatch_blocks_candidate(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(prepare_cli, "PROJECT_ROOT", tmp_path)
    sources = _write_candidate_sources(tmp_path / "source")
    risk = json.loads(sources["risk_snapshot"].read_text(encoding="utf-8"))
    risk["provenance"]["symbol"] = "2317"
    sources["risk_snapshot"].write_text(json.dumps(risk), encoding="utf-8")
    output = _output(tmp_path, "2026-08-20", "stale-risk-01")

    result = prepare_cli.main(
        [
            "--market-date", "2026-08-20",
            "--attempt-id", "stale-risk-01",
            "--entry-decision-source", str(sources["entry_decision"]),
            "--thesis-draft-source", str(sources["thesis_draft"]),
            "--shadow-policy-source", str(sources["shadow_policy"]),
            "--risk-snapshot-source", str(sources["risk_snapshot"]),
            "--output", str(output),
        ]
    )

    packet = json.loads(output.read_text(encoding="utf-8"))
    assert result == 2
    assert packet["candidate_valid"] is False
    assert "RISK_SNAPSHOT_PROVENANCE_MISMATCH" in packet["blockers"][0]


def test_incomplete_artifact_pair_lock_is_fail_closed(tmp_path) -> None:
    artifact = tmp_path / "review_packet.json"
    artifact.write_text("{}\n", encoding="utf-8")
    artifact.with_suffix(".json.sha256").write_text("0" * 64 + "\n")
    artifact.with_suffix(".json.write.lock").write_text(
        "INCOMPLETE_ARTIFACT_PAIR\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="INCOMPLETE_ARTIFACT_PAIR"):
        require_complete_artifact_pair(artifact)


def test_c1_rejects_canonical_input_changed_after_promotion(
    monkeypatch,
    tmp_path,
) -> None:
    for cli in (prepare_cli, review_cli, promote_cli, c1_cli):
        monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    sources = _write_candidate_sources(tmp_path / "source")
    packet = _output(tmp_path, "2026-08-20", "canonical-tamper-01")
    approval = _approval_output(
        tmp_path,
        "2026-08-20",
        "canonical-tamper-01",
    )
    canonical = tmp_path / "research/trade_management_shadow/session_inputs/2026-08-20"
    prepare_cli.main([
        "--market-date", "2026-08-20",
        "--attempt-id", "canonical-tamper-01",
        "--entry-decision-source", str(sources["entry_decision"]),
        "--thesis-draft-source", str(sources["thesis_draft"]),
        "--shadow-policy-source", str(sources["shadow_policy"]),
        "--risk-snapshot-source", str(sources["risk_snapshot"]),
        "--output", str(packet),
    ])
    review_cli.main([
        "--review-packet", str(packet),
        "--reviewer-id", "human-reviewer-01",
        "--reviewed-at", "2026-08-20T08:31:00+08:00",
        "--review-note", "Reviewed before canonical tamper.",
        "--output", str(approval),
    ])
    promote_cli.main([
        "--review-approval", str(approval),
        "--output-dir", str(canonical),
    ])
    (canonical / "risk_snapshot.json").write_text(
        (canonical / "risk_snapshot.json").read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    args = SimpleNamespace(
        entry_decision=canonical / "live_entry_decision.json",
        thesis_draft=canonical / "trade_thesis_draft.json",
        shadow_policy=canonical / "shadow_policy.json",
        risk_snapshot=canonical / "risk_snapshot.json",
        input_approval=canonical / "review_approval.json",
    )

    with pytest.raises(
        RuntimeError,
        match="INPUT_APPROVAL_CANONICAL_DIGEST_MISMATCH",
    ):
        c1_cli._load_and_verify_input_approval(
            args,
            market_date=decision().signal_at.value.date(),
        )


def test_c1_rejects_symlinked_canonical_date_directory(tmp_path) -> None:
    root = tmp_path / "session_inputs"
    real = tmp_path / "approved_bundle"
    real.mkdir()
    root.mkdir()
    (root / "2026-08-20").symlink_to(real, target_is_directory=True)
    args = SimpleNamespace(
        entry_decision=root / "2026-08-20/live_entry_decision.json",
        thesis_draft=root / "2026-08-20/trade_thesis_draft.json",
        shadow_policy=root / "2026-08-20/shadow_policy.json",
        risk_snapshot=root / "2026-08-20/risk_snapshot.json",
        input_approval=root / "2026-08-20/review_approval.json",
    )

    with pytest.raises(RuntimeError, match="C1_CANONICAL_INPUT_SYMLINK_REJECTED"):
        c1_cli._require_canonical_input_paths(
            args,
            market_date=decision().signal_at.value.date(),
            session_inputs_root=root,
        )


def test_c1_rejects_canonical_sources_without_review_approval(tmp_path) -> None:
    canonical = tmp_path / "session_inputs/2026-08-20"
    args = SimpleNamespace(
        entry_decision=canonical / "live_entry_decision.json",
        thesis_draft=canonical / "trade_thesis_draft.json",
        shadow_policy=canonical / "shadow_policy.json",
        risk_snapshot=canonical / "risk_snapshot.json",
        input_approval=canonical / "review_approval.json",
    )

    with pytest.raises(RuntimeError, match="ARTIFACT_PAIR_INCOMPLETE"):
        c1_cli._load_and_verify_input_approval(
            args,
            market_date=decision().signal_at.value.date(),
        )


def test_promotion_rejects_symlinked_canonical_root(monkeypatch, tmp_path) -> None:
    for cli in (prepare_cli, review_cli, promote_cli):
        monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    sources = _write_candidate_sources(tmp_path / "source")
    packet = _output(tmp_path, "2026-08-20", "symlink-root-01")
    approval = _approval_output(tmp_path, "2026-08-20", "symlink-root-01")
    assert prepare_cli.main([
        "--market-date", "2026-08-20",
        "--attempt-id", "symlink-root-01",
        "--entry-decision-source", str(sources["entry_decision"]),
        "--thesis-draft-source", str(sources["thesis_draft"]),
        "--shadow-policy-source", str(sources["shadow_policy"]),
        "--risk-snapshot-source", str(sources["risk_snapshot"]),
        "--output", str(packet),
    ]) == 0
    assert review_cli.main([
        "--review-packet", str(packet),
        "--reviewer-id", "human-reviewer-01",
        "--reviewed-at", "2026-08-20T08:31:00+08:00",
        "--review-note", "Reviewed before symlink boundary test.",
        "--output", str(approval),
    ]) == 0
    shadow_root = tmp_path / "research/trade_management_shadow"
    redirected = tmp_path / "redirected-session-inputs"
    redirected.mkdir()
    (shadow_root / "session_inputs").symlink_to(
        redirected,
        target_is_directory=True,
    )

    with pytest.raises(RuntimeError, match="ARTIFACT_PATH_SYMLINK_REJECTED"):
        promote_cli.main([
            "--review-approval", str(approval),
            "--output-dir", str(shadow_root / "session_inputs/2026-08-20"),
        ])


def test_promotion_lock_contention_is_fail_closed(monkeypatch, tmp_path) -> None:
    for cli in (prepare_cli, review_cli, promote_cli):
        monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    sources = _write_candidate_sources(tmp_path / "source")
    packet = _output(tmp_path, "2026-08-20", "lock-contention-01")
    approval = _approval_output(tmp_path, "2026-08-20", "lock-contention-01")
    assert prepare_cli.main([
        "--market-date", "2026-08-20",
        "--attempt-id", "lock-contention-01",
        "--entry-decision-source", str(sources["entry_decision"]),
        "--thesis-draft-source", str(sources["thesis_draft"]),
        "--shadow-policy-source", str(sources["shadow_policy"]),
        "--risk-snapshot-source", str(sources["risk_snapshot"]),
        "--output", str(packet),
    ]) == 0
    assert review_cli.main([
        "--review-packet", str(packet),
        "--reviewer-id", "human-reviewer-01",
        "--reviewed-at", "2026-08-20T08:31:00+08:00",
        "--review-note", "Reviewed before contention test.",
        "--output", str(approval),
    ]) == 0
    canonical_parent = (
        tmp_path / "research/trade_management_shadow/session_inputs"
    )
    canonical_parent.mkdir(parents=True)
    lock = canonical_parent / ".2026-08-20.promotion.lock"
    lock.write_text("existing-owner\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        promote_cli.main([
            "--review-approval", str(approval),
            "--output-dir", str(canonical_parent / "2026-08-20"),
        ])
    assert lock.read_text(encoding="utf-8") == "existing-owner\n"
    assert not (canonical_parent / "2026-08-20").exists()


def test_c1_rejects_retained_promotion_commit_lock(tmp_path) -> None:
    market_date = decision().signal_at.value.date()
    root = tmp_path / "session_inputs"
    expected = root / market_date.isoformat()
    root.mkdir()
    (root / f".{market_date.isoformat()}.promotion.lock").write_text(
        "INCOMPLETE_CANONICAL_PROMOTION\n",
        encoding="utf-8",
    )
    args = SimpleNamespace(
        entry_decision=expected / "live_entry_decision.json",
        thesis_draft=expected / "trade_thesis_draft.json",
        shadow_policy=expected / "shadow_policy.json",
        risk_snapshot=expected / "risk_snapshot.json",
        input_approval=expected / "review_approval.json",
    )

    with pytest.raises(RuntimeError, match="C1_CANONICAL_PROMOTION_INCOMPLETE"):
        c1_cli._require_canonical_input_paths(
            args,
            market_date=market_date,
            session_inputs_root=root,
        )


def test_preflight_artifact_reader_rejects_incomplete_pair(tmp_path) -> None:
    artifact = tmp_path / "c0.json"
    artifact.write_text('{"status":"READY"}\n', encoding="utf-8")
    artifact.with_suffix(".json.sha256").write_text("a" * 64 + "\n")
    artifact.with_suffix(".json.write.lock").write_text(
        "INCOMPLETE_ARTIFACT_PAIR\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="INCOMPLETE_ARTIFACT_PAIR"):
        c1_cli._read_preflight_artifact(artifact)


def test_preflight_artifact_reader_hashes_the_admitted_bytes_once(
    monkeypatch,
    tmp_path,
) -> None:
    artifact = tmp_path / "c0.json"
    content = b'{"status":"READY"}\n'
    artifact.write_bytes(content)
    artifact.with_suffix(".json.sha256").write_text("b" * 64 + "\n")
    reads = 0
    original = Path.read_bytes

    def counted_read(path: Path) -> bytes:
        nonlocal reads
        if path == artifact:
            reads += 1
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read)
    value, file_digest, sidecar_digest = c1_cli._read_preflight_artifact(artifact)

    assert value == {"status": "READY"}
    assert file_digest == hashlib.sha256(content).hexdigest()
    assert sidecar_digest == "b" * 64
    assert reads == 1


def test_runtime_identity_covers_all_input_workflow_entrypoints(tmp_path) -> None:
    for relative in (
        "runtime/core.py",
        "scripts/preflight_trade_management_shadow.py",
        "scripts/run_trade_management_shadow_c1.py",
        "scripts/prepare_trade_management_shadow_inputs.py",
        "scripts/review_trade_management_shadow_inputs.py",
        "scripts/promote_trade_management_shadow_inputs.py",
        "pyproject.toml",
        "uv.lock",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative + ":v1\n", encoding="utf-8")
    before = runtime_code_identity(
        project_root=tmp_path,
        git_head_value="a" * 40,
    )
    review_script = tmp_path / "scripts/review_trade_management_shadow_inputs.py"
    review_script.write_text("AUTO_APPROVE = True\n", encoding="utf-8")

    assert runtime_code_identity(
        project_root=tmp_path,
        git_head_value="a" * 40,
    ) != before


def test_risk_snapshot_capture_must_be_inside_reviewed_preopen_window(
    tmp_path,
) -> None:
    sources = _write_candidate_sources(tmp_path / "source")
    value = json.loads(sources["risk_snapshot"].read_text(encoding="utf-8"))
    value["provenance"]["captured_at"] = "2026-08-20T13:30:00+08:00"
    sources["risk_snapshot"].write_text(json.dumps(value), encoding="utf-8")
    _, provenance = parse_risk_snapshot_document(
        sources["risk_snapshot"].read_bytes()
    )

    with pytest.raises(
        ValueError,
        match="RISK_SNAPSHOT_CAPTURE_OUTSIDE_PREOPEN_WINDOW",
    ):
        require_risk_snapshot_capture_window(
            provenance,
            window_start=datetime(2026, 8, 20, 8, 30, tzinfo=TAIPEI),
            window_end=datetime(2026, 8, 20, 9, 0, tzinfo=TAIPEI),
            admitted_at=datetime(2026, 8, 20, 8, 35, tzinfo=TAIPEI),
        )


def test_risk_snapshot_capture_cannot_be_after_c1_admission(tmp_path) -> None:
    sources = _write_candidate_sources(tmp_path / "source")
    value = json.loads(sources["risk_snapshot"].read_text(encoding="utf-8"))
    value["provenance"]["captured_at"] = "2026-08-20T08:40:00+08:00"
    sources["risk_snapshot"].write_text(json.dumps(value), encoding="utf-8")
    _, provenance = parse_risk_snapshot_document(
        sources["risk_snapshot"].read_bytes()
    )

    with pytest.raises(ValueError, match="RISK_SNAPSHOT_CAPTURE_AFTER_ADMISSION"):
        require_risk_snapshot_capture_window(
            provenance,
            window_start=datetime(2026, 8, 20, 8, 30, tzinfo=TAIPEI),
            window_end=datetime(2026, 8, 20, 9, 0, tzinfo=TAIPEI),
            admitted_at=datetime(2026, 8, 20, 8, 35, tzinfo=TAIPEI),
        )


def test_review_cannot_precede_risk_snapshot_capture(monkeypatch, tmp_path) -> None:
    for cli in (prepare_cli, review_cli):
        monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    sources = _write_candidate_sources(tmp_path / "source")
    packet = _output(tmp_path, "2026-08-20", "early-review-01")
    approval = _approval_output(tmp_path, "2026-08-20", "early-review-01")
    assert prepare_cli.main([
        "--market-date", "2026-08-20",
        "--attempt-id", "early-review-01",
        "--entry-decision-source", str(sources["entry_decision"]),
        "--thesis-draft-source", str(sources["thesis_draft"]),
        "--shadow-policy-source", str(sources["shadow_policy"]),
        "--risk-snapshot-source", str(sources["risk_snapshot"]),
        "--output", str(packet),
    ]) == 0

    with pytest.raises(RuntimeError, match="INPUT_REVIEW_PRECEDES_RISK_CAPTURE"):
        review_cli.main([
            "--review-packet", str(packet),
            "--reviewer-id", "human-reviewer-01",
            "--reviewed-at", "2026-08-20T08:29:00+08:00",
            "--review-note", "Invalid early review.",
            "--output", str(approval),
        ])
    assert not approval.exists()


def test_prepare_rejects_risk_snapshot_captured_after_operation(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(prepare_cli, "PROJECT_ROOT", tmp_path)
    sources = _write_candidate_sources(tmp_path / "source")
    packet = _output(tmp_path, "2026-08-20", "future-capture-01")

    result = prepare_cli.main(
        [
            "--market-date", "2026-08-20",
            "--attempt-id", "future-capture-01",
            "--entry-decision-source", str(sources["entry_decision"]),
            "--thesis-draft-source", str(sources["thesis_draft"]),
            "--shadow-policy-source", str(sources["shadow_policy"]),
            "--risk-snapshot-source", str(sources["risk_snapshot"]),
            "--output", str(packet),
        ],
        now=datetime(2026, 8, 20, 8, 29, tzinfo=TAIPEI),
    )

    assert result == 2
    value = json.loads(packet.read_text(encoding="utf-8"))
    assert value["candidate_valid"] is False
    assert any(
        "RISK_SNAPSHOT_CAPTURE_AFTER_OBSERVATION" in blocker
        for blocker in value["blockers"]
    )


def test_review_rejects_review_timestamp_after_operation(
    monkeypatch,
    tmp_path,
) -> None:
    for cli in (prepare_cli, review_cli):
        monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    sources = _write_candidate_sources(tmp_path / "source")
    packet = _output(tmp_path, "2026-08-20", "future-review-01")
    approval = _approval_output(tmp_path, "2026-08-20", "future-review-01")
    assert prepare_cli.main(
        [
            "--market-date", "2026-08-20",
            "--attempt-id", "future-review-01",
            "--entry-decision-source", str(sources["entry_decision"]),
            "--thesis-draft-source", str(sources["thesis_draft"]),
            "--shadow-policy-source", str(sources["shadow_policy"]),
            "--risk-snapshot-source", str(sources["risk_snapshot"]),
            "--output", str(packet),
        ],
        now=datetime(2026, 8, 20, 8, 30, tzinfo=TAIPEI),
    ) == 0

    with pytest.raises(
        RuntimeError,
        match="INPUT_REVIEW_TIME_AFTER_OBSERVATION",
    ):
        review_cli.main(
            [
                "--review-packet", str(packet),
                "--reviewer-id", "human-reviewer-01",
                "--reviewed-at", "2026-08-20T08:32:00+08:00",
                "--review-note", "Invalid future review time.",
                "--output", str(approval),
            ],
            now=datetime(2026, 8, 20, 8, 31, tzinfo=TAIPEI),
        )
    assert not approval.exists()


def _valid_c0_component_payloads() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    provider_signed = {
        "credential_keys_present": ["API_KEY", "SECRET"],
        "login_succeeded": True,
        "logout_succeeded": True,
        "subscribe_trade": False,
        "environment_identity": "shioaji:1.7.2:simulation=true",
        "error_code": None,
    }
    provider = {
        **provider_signed,
        "digest": c1_cli._canonical_digest(provider_signed),
    }
    postgres_signed = {
        "dsn_configured": True,
        "driver_version": "3.2.9",
        "connected": True,
        "transaction_read_only": True,
        "server_major": 16,
        "table_names": [
            "journal_records",
            "journal_schema_migrations",
            "journal_sessions",
            "projection_checkpoints",
        ],
        "migration_versions": ["001_initial.sql"],
        "evidence_row_counts": [
            ["journal_sessions", 0],
            ["journal_records", 0],
            ["projection_checkpoints", 0],
        ],
        "evidence_scope_session_id": "tm-c1-20260820",
        "error_code": None,
    }
    postgres = {
        **postgres_signed,
        "evidence_row_counts": {
            name: count for name, count in postgres_signed["evidence_row_counts"]
        },
        "digest": c1_cli._canonical_digest(postgres_signed),
    }
    rehearsal_signed = {
        "test_targets": ["tests/test_trade_management_c1_session.py"],
        "historical_replay_verified": True,
        "operational_composition_verified": True,
        "journal_recovery_verified": True,
        "replay_parity_matched": True,
        "readiness_report_deterministic": True,
        "execution_enabled": False,
        "qualifying_real_session": False,
    }
    rehearsal = {
        "source_class": "TEST_FIXTURE_AND_HISTORICAL_REPLAY",
        **rehearsal_signed,
        "digest": c1_cli._canonical_digest(rehearsal_signed),
    }
    report = {
        "provider_preflight_digest": provider["digest"],
        "postgres_preflight_digest": postgres["digest"],
        "rehearsal_digest": rehearsal["digest"],
    }
    return provider, postgres, rehearsal, report


@pytest.mark.parametrize(
    ("component_name", "field_name"),
    (
        ("provider", "login_succeeded"),
        ("postgres", "connected"),
        ("rehearsal", "historical_replay_verified"),
    ),
)
def test_c1_recomputes_c0_component_payload_digests(
    component_name: str,
    field_name: str,
) -> None:
    provider, postgres, rehearsal, report = _valid_c0_component_payloads()
    components = {
        "provider": provider,
        "postgres": postgres,
        "rehearsal": rehearsal,
    }
    c1_cli._require_c0_component_digests(
        provider=provider,
        postgres=postgres,
        rehearsal=rehearsal,
        report=report,
    )
    components[component_name][field_name] = False

    with pytest.raises(RuntimeError, match="C0_COMPONENT_DIGEST_MISMATCH"):
        c1_cli._require_c0_component_digests(
            provider=provider,
            postgres=postgres,
            rehearsal=rehearsal,
            report=report,
        )


def test_promotion_implementation_has_no_replacing_directory_rename() -> None:
    source = Path(promote_cli.__file__).read_text(encoding="utf-8")

    assert "os.rename(" not in source


def test_external_design_serializes_by_date_and_allows_clean_git_check() -> None:
    design = (
        Path(__file__).parents[1]
        / "architecture/trade_management_shadow_external_execution_design.md"
    ).read_text(encoding="utf-8")

    assert "keyed by market date; it records the session ID" in design
    assert "/usr/bin/git status --porcelain --untracked-files=all" in design


@pytest.mark.parametrize("workflow_cli", (prepare_cli, review_cli, promote_cli))
def test_input_workflow_has_no_provider_database_or_execution_capability(
    workflow_cli,
) -> None:
    source = Path(workflow_cli.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    assert imported.isdisjoint(
        {
            "ShioajiMomentumStream",
            "PostgresJournalRepository",
            "OrderCommand",
            "OrderApplicationService",
            "LocalPaperCommandService",
        }
    )
    assert referenced.isdisjoint(
        {"Broker", "Position", "place_order", "activate_ca", "subscribe_trade"}
    )


@pytest.mark.parametrize(
    "module_name",
    (
        "scripts.prepare_trade_management_shadow_inputs",
        "scripts.review_trade_management_shadow_inputs",
        "scripts.promote_trade_management_shadow_inputs",
    ),
)
def test_input_workflow_import_does_not_load_concrete_runtime_adapters(
    module_name: str,
) -> None:
    forbidden = (
        "scripts.preflight_trade_management_shadow",
        "scripts.run_trade_management_shadow_c1",
        "market_data.shioaji_momentum_stream",
        "trading.postgres_journal",
        "shioaji",
        "psycopg",
    )
    script = (
        "import sys; "
        f"import {module_name}; "
        f"forbidden={forbidden!r}; "
        "print([name for name in forbidden if name in sys.modules])"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=prepare_cli.PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "[]"
