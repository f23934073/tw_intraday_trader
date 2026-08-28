from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from backtest.domain import canonical_json, digest
from backtest.research_replay.artifact_store import ReplayArtifactStore
from backtest.research_replay.domain import (
    ResearchReplayIntegrityError,
    build_ledger,
    build_ledger_manifest,
    build_order_derivation,
    build_replay,
    build_result_manifest,
    cost_identity,
)
from tests.test_signal_ledger_replay_domain import _decision, _identity, _order, _pipeline


def _publish_all(root):
    (
        _,
        ledger,
        derivation,
        ledger_manifest,
        match,
        match_manifest,
        replay,
        result_manifest,
    ) = _pipeline()
    store = ReplayArtifactStore(root, chunk_size=1)
    ledger_path = store.publish_ledger(
        manifest=ledger_manifest,
        ledger_rows=reversed(ledger.rows),
        order_rows=reversed(derivation.rows),
    )
    match_path = store.publish_match_plan(
        manifest=match_manifest,
        match_rows=reversed(match.rows),
    )
    result_path = store.publish_result(
        manifest=result_manifest,
        episode_rows=reversed(replay.episodes),
        modeled_entry_rows=reversed(replay.modeled_entries),
        modeled_exit_rows=reversed(replay.modeled_exits),
    )
    return (
        store,
        ledger,
        derivation,
        ledger_manifest,
        match,
        match_manifest,
        replay,
        result_manifest,
        ledger_path,
        match_path,
        result_path,
    )


def test_clean_root_publication_is_canonical_and_replayable(tmp_path) -> None:
    first = _publish_all(tmp_path / "first")
    second = _publish_all(tmp_path / "second")

    first_store, ledger, derivation, ledger_manifest, match, match_manifest, replay, result_manifest, *_ = first
    second_store = second[0]
    assert first_store.load_ledger(ledger_manifest["ledger_manifest_digest"]).ledger_rows == ledger.rows
    assert first_store.load_ledger(ledger_manifest["ledger_manifest_digest"]).order_rows == derivation.rows
    assert first_store.load_match_plan(match_manifest["match_plan_manifest_digest"]).rows == match.rows
    assert first_store.load_result(result_manifest["result_manifest_digest"]).episodes == replay.episodes
    assert second_store.load_result(result_manifest["result_manifest_digest"]).manifest == result_manifest


def test_external_sort_uses_bounded_fan_in_and_canonical_sequence(tmp_path) -> None:
    taipei = ZoneInfo("Asia/Taipei")
    start = datetime(2026, 1, 1, 9, 1, tzinfo=taipei)
    decisions = [
        _decision(f"decision-{index}", "2330", start + timedelta(minutes=index))
        for index in range(150)
    ]
    ledger = build_ledger(baseline_run_id="run-baseline", decisions=decisions)
    derivation = build_order_derivation(
        ledger_rows=ledger.rows,
        orders=[_order(decision, index) for index, decision in enumerate(decisions, 1)],
    )
    manifest = build_ledger_manifest(
        identity=_identity(), ledger=ledger, order_derivation=derivation
    )
    store = ReplayArtifactStore(tmp_path, chunk_size=1, merge_fan_in=4)

    store.publish_ledger(
        manifest=manifest,
        ledger_rows=reversed(ledger.rows),
        order_rows=reversed(derivation.rows),
    )
    loaded = store.load_ledger(manifest["ledger_manifest_digest"])

    assert len(loaded.ledger_rows) == 150
    assert [row["sequence"] for row in loaded.ledger_rows] == list(range(1, 151))


def test_same_digest_publication_replays_without_new_identity(tmp_path) -> None:
    store, ledger, derivation, ledger_manifest, *_ = _publish_all(tmp_path)

    first = store.publish_ledger(
        manifest=ledger_manifest,
        ledger_rows=ledger.rows,
        order_rows=derivation.rows,
    )
    second = store.publish_ledger(
        manifest=ledger_manifest,
        ledger_rows=reversed(ledger.rows),
        order_rows=reversed(derivation.rows),
    )

    assert first == second


def test_duplicate_sequence_is_rejected_before_publication(tmp_path) -> None:
    _, ledger, derivation, ledger_manifest, *_ = _publish_all(tmp_path / "source")
    store = ReplayArtifactStore(tmp_path / "target", chunk_size=1)

    with pytest.raises(ResearchReplayIntegrityError, match="sequence"):
        store.publish_ledger(
            manifest=ledger_manifest,
            ledger_rows=(ledger.rows[0], ledger.rows[0]),
            order_rows=derivation.rows,
        )

    duplicate_signal = deepcopy(ledger.rows[0])
    duplicate_signal["sequence"] = 2
    with pytest.raises(ResearchReplayIntegrityError, match="signal_id"):
        store.publish_ledger(
            manifest=ledger_manifest,
            ledger_rows=(ledger.rows[0], duplicate_signal),
            order_rows=derivation.rows,
        )

    category = tmp_path / "target" / "ledgers"
    assert not list(category.glob("*")) if category.exists() else True


def test_payload_blank_line_and_manifest_unknown_field_fail_closed(tmp_path) -> None:
    store, _, _, ledger_manifest, _, _, _, _, ledger_path, *_ = _publish_all(tmp_path)
    payload = ledger_path / "ledger.jsonl"
    payload.write_bytes(b"\n" + payload.read_bytes())
    with pytest.raises(ResearchReplayIntegrityError):
        store.load_ledger(ledger_manifest["ledger_manifest_digest"])

    fresh = _publish_all(tmp_path / "fresh")
    fresh_store, _, _, fresh_manifest, *_, fresh_path, _, _ = fresh
    manifest_path = fresh_path / "manifest.json"
    raw = manifest_path.read_text()
    manifest_path.write_text(raw.replace("{", '{"locator":"/tmp/private",', 1))
    with pytest.raises(ResearchReplayIntegrityError):
        fresh_store.load_ledger(fresh_manifest["ledger_manifest_digest"])


def test_unknown_file_and_payload_byte_tamper_fail_closed(tmp_path) -> None:
    store, *values = _publish_all(tmp_path)
    result_manifest = values[6]
    result_path = values[9]
    (result_path / "locator.txt").write_text("not identity")
    with pytest.raises(ResearchReplayIntegrityError, match="file set"):
        store.load_result(result_manifest["result_manifest_digest"])


def test_result_load_rebuilds_economic_formula_beyond_manifest_digests(tmp_path) -> None:
    store, *values = _publish_all(tmp_path)
    result_path = values[9]
    episode_path = result_path / "episodes.jsonl"
    manifest_path = result_path / "manifest.json"
    episodes = [json.loads(line) for line in episode_path.read_text().splitlines()]
    episodes[0]["net_pnl"] = "1"
    payload = b"".join(
        (canonical_json(row) + "\n").encode("utf-8") for row in episodes
    )
    episode_path.write_bytes(payload)

    manifest = json.loads(manifest_path.read_text())
    manifest["episode_rows_sha256"] = hashlib.sha256(payload).hexdigest()
    manifest["result_projection_digest"] = digest(
        {
            "episode_rows_sha256": manifest["episode_rows_sha256"],
            "modeled_entry_rows_sha256": manifest["modeled_entry_rows_sha256"],
            "modeled_exit_rows_sha256": manifest["modeled_exit_rows_sha256"],
            "summary_digest": manifest["summary_digest"],
        }
    )
    body = {key: value for key, value in manifest.items() if key != "result_manifest_digest"}
    new_digest = digest(body)
    manifest["result_manifest_digest"] = new_digest
    new_path = result_path.parent / new_digest
    result_path.rename(new_path)
    (new_path / "manifest.json").write_text(canonical_json(manifest) + "\n")

    with pytest.raises(ResearchReplayIntegrityError, match="economic formula"):
        store.load_result(new_digest)


def test_result_publication_rejects_relabelled_cost_identity(tmp_path) -> None:
    (
        _,
        _,
        _,
        ledger_manifest,
        match,
        match_manifest,
        _,
        _,
    ) = _pipeline()
    replay = build_replay(
        match_rows=match.rows,
        min_lot_shares=1000,
        slippage_bps="500",
        commission_rate="0.02",
        sell_tax_rate="0.01",
    )
    manifest = build_result_manifest(
        replay_id="replay-expensive",
        registration_revision=1,
        ledger_manifest=ledger_manifest,
        match_manifest=match_manifest,
        replay=replay,
        min_lot_shares=1000,
        slippage_bps="500",
        commission_rate="0.02",
        sell_tax_rate="0.01",
    )
    relabelled = deepcopy(manifest)
    relabelled["cost_identity_digest"] = digest(
        cost_identity(
            min_lot_shares=1000,
            slippage_bps="5",
            commission_rate="0.001425",
            sell_tax_rate="0.003",
        )
    )
    body = {
        key: value
        for key, value in relabelled.items()
        if key != "result_manifest_digest"
    }
    relabelled["result_manifest_digest"] = digest(body)
    store = ReplayArtifactStore(tmp_path)

    with pytest.raises(ResearchReplayIntegrityError, match="cost identity"):
        store.publish_result(
            manifest=relabelled,
            episode_rows=replay.episodes,
            modeled_entry_rows=replay.modeled_entries,
            modeled_exit_rows=replay.modeled_exits,
        )

    results = tmp_path / "results"
    assert not list(results.glob("*")) if results.exists() else True


def test_interrupt_before_manifest_publication_leaves_no_partial_pair(
    tmp_path, monkeypatch
) -> None:
    _, ledger, derivation, ledger_manifest, *_ = _publish_all(tmp_path / "source")
    target_root = tmp_path / "interrupted"
    store = ReplayArtifactStore(target_root, chunk_size=1)

    def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(store, "_write_manifest", interrupt)
    with pytest.raises(KeyboardInterrupt):
        store.publish_ledger(
            manifest=ledger_manifest,
            ledger_rows=ledger.rows,
            order_rows=derivation.rows,
        )

    category = target_root / "ledgers"
    assert not list(category.glob("*")) if category.exists() else True
