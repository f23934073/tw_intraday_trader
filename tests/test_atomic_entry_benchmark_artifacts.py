from __future__ import annotations

import hashlib
from copy import deepcopy

import pytest

from backtest.atomic_benchmark.artifacts import (
    SlotBundleInput,
    build_family_release,
    build_ledger_manifest,
    build_match_manifest,
    build_postflight,
    build_public_bundle,
    build_result_manifest,
    frame_member,
    verify_ledger_manifest,
    verify_public_bundle,
)
from backtest.atomic_benchmark.domain import (
    ALGORITHM_CONTRACT_DIGEST,
    COST_IDENTITY_DIGEST,
    AtomicBenchmarkIntegrityError,
    FirstTriggerAdmission,
    build_episode,
    build_match_plan,
    build_summary,
    canonical_object_bytes,
)
from backtest.domain import digest
from tests.test_atomic_entry_benchmark_domain import SHA, _bar


def _common(slot: int, hypothesis_id: str) -> dict:
    return {
        "matrix_id": "r6-matrix-test",
        "registration_digest": SHA,
        "family_id": "r6-family-test",
        "research_baseline_digest": SHA,
        "slot_sequence": slot,
        "hypothesis_id": hypothesis_id,
        "strategy_id": f"strategy-{slot}",
        "strategy_version_id": f"version-{slot}",
        "strategy_configuration_digest": SHA,
        "strategy_implementation_digest": SHA,
        "lifecycle_sequence": 1,
        "lifecycle_event_id": f"event-{slot}",
        "lifecycle_projection_digest": SHA,
        "dataset_id": "dataset-1",
        "dataset_digest": SHA,
        "dataset_bars_sha256": SHA,
        "dataset_binding_revision": 1,
        "protocol_core_digest": SHA,
        "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
        "algorithm_implementation_digest": SHA,
    }


def _slot(slot: int = 1):
    hypothesis = hashlib.sha256(f"hypothesis-{slot}".encode()).hexdigest()
    owner = FirstTriggerAdmission()
    signal = owner.consider(
        matrix_id="r6-matrix-test",
        registration_digest=SHA,
        slot_sequence=slot,
        hypothesis_id=hypothesis,
        strategy_id=f"strategy-{slot}",
        strategy_version_id=f"version-{slot}",
        strategy_configuration_digest=SHA,
        strategy_implementation_digest=SHA,
        feature_request_identity_digest=SHA,
        source_bar=_bar("2026-01-05T09:01:00"),
        evaluation_status="TRIGGERED",
        evaluation_document={"observed": {"slot": slot}, "threshold": {}},
        feature_input_evidence={"input_digest": SHA},
    )
    assert signal is not None
    bars = (
        _bar("2026-01-05T09:01:00"),
        _bar("2026-01-05T09:02:00", open_price="100", close="100"),
        _bar("2026-01-05T13:30:00", open_price="102", close="102"),
    )
    match = build_match_plan(ledger_rows=(signal,), bars=bars)
    episode = build_episode(match.rows[0])
    common = _common(slot, hypothesis)
    common["dataset_bars_sha256"] = match.source_bars_sha256
    ledger_manifest = build_ledger_manifest(
        identity=common, ledger_rows=(signal,)
    )
    match_manifest = build_match_manifest(
        ledger_manifest=ledger_manifest, match_plan=match
    )
    summary = build_summary(
        (episode,), family_id="r6-family-test", hypothesis_id=hypothesis
    )
    result = build_result_manifest(
        replay_id=f"replay-{slot}",
        match_manifest=match_manifest,
        episode_rows=(episode,),
        summary=summary,
    )
    postflight = build_postflight(
        ledger_manifest=ledger_manifest,
        ledger_rows=(signal,),
        match_manifest=match_manifest,
        match_rows=match.rows,
        result_manifest=result,
        episode_rows=(episode,),
        source_bar_count=match.source_bar_count,
        source_bars_sha256=match.source_bars_sha256,
        source_eof_verified=True,
        dataset_verified=True,
        version_lifecycle_verified=True,
        no_external_calls=True,
    )
    return hypothesis, signal, match, episode, ledger_manifest, match_manifest, result, postflight


def _expanded_episodes(base: dict, count: int) -> tuple[dict, ...]:
    rows = []
    for sequence in range(1, count + 1):
        match_id = hashlib.sha256(f"match-{sequence}".encode()).hexdigest()
        rows.append(
            {
                **base,
                "sequence": sequence,
                "match_id": match_id,
                "episode_id": digest(
                    {
                        "schema_version": "r6-episode-id-v1",
                        "match_id": match_id,
                        "cost_identity_digest": COST_IDENTITY_DIGEST,
                    }
                ),
                "signal_id": hashlib.sha256(
                    f"signal-{sequence}".encode()
                ).hexdigest(),
                "semantic_key": hashlib.sha256(
                    f"semantic-{sequence}".encode()
                ).hexdigest(),
            }
        )
    return tuple(rows)


def _accepted_postflight_for_result(postflight: dict, result: dict) -> dict:
    updated = deepcopy(postflight)
    updated.update(
        {
            "expected_result_manifest_digest": result["result_manifest_digest"],
            "actual_result_manifest_digest": result["result_manifest_digest"],
            "expected_result_projection_digest": result["result_projection_digest"],
            "actual_result_projection_digest": result["result_projection_digest"],
            "recomputed_summary": result["summary"],
        }
    )
    updated["postflight_digest"] = digest(
        {
            key: value
            for key, value in updated.items()
            if key != "postflight_digest"
        }
    )
    return updated


def test_manifest_unknown_field_and_self_digest_tamper_fail_closed() -> None:
    *_, ledger, _, _, _ = _slot()
    with pytest.raises(AtomicBenchmarkIntegrityError, match="unknown"):
        verify_ledger_manifest({**ledger, "created_at": "now"})
    tampered = {**ledger, "ledger_signal_count": 2}
    with pytest.raises(AtomicBenchmarkIntegrityError, match="digest"):
        verify_ledger_manifest(tampered)


def test_postflight_recomputes_all_adjacent_parity_and_accepts_integrity() -> None:
    *_, postflight = _slot()
    assert postflight["verdict"] == "ACCEPTED"
    assert postflight["acceptance_conditions"]["ledger_match_parity"] is True
    assert postflight["acceptance_conditions"]["match_episode_parity"] is True


def test_postflight_rejects_same_count_signal_substitution() -> None:
    hypothesis, signal, match, episode, ledger, match_manifest, result, _ = _slot()
    substituted = {**episode, "signal_id": "b" * 64}
    postflight = build_postflight(
        ledger_manifest=ledger,
        ledger_rows=(signal,),
        match_manifest=match_manifest,
        match_rows=match.rows,
        result_manifest=result,
        episode_rows=(substituted,),
        source_bar_count=match.source_bar_count,
        source_bars_sha256=match.source_bars_sha256,
        source_eof_verified=True,
        dataset_verified=True,
        version_lifecycle_verified=True,
        no_external_calls=True,
    )
    assert postflight["verdict"] == "REJECTED"
    assert postflight["diagnostics"]["match_minus_episode_count"] == 1
    assert postflight["diagnostics"]["episode_minus_match_count"] == 1


def test_postflight_rejects_dataset_source_sha_mismatch() -> None:
    _, signal, match, episode, ledger, match_manifest, result, _ = _slot()
    postflight = build_postflight(
        ledger_manifest=ledger,
        ledger_rows=(signal,),
        match_manifest=match_manifest,
        match_rows=match.rows,
        result_manifest=result,
        episode_rows=(episode,),
        source_bar_count=match.source_bar_count,
        source_bars_sha256="b" * 64,
        source_eof_verified=True,
        dataset_verified=True,
        version_lifecycle_verified=True,
        no_external_calls=True,
    )
    assert postflight["verdict"] == "REJECTED"
    assert postflight["acceptance_conditions"]["dataset_verified"] is False


def test_postflight_rejects_self_consistent_common_identity_substitution() -> None:
    _, signal, match, episode, ledger, match_manifest, result, _ = _slot()
    changed = {**result, "dataset_id": "dataset-foreign"}
    changed["result_manifest_digest"] = digest(
        {key: value for key, value in changed.items() if key != "result_manifest_digest"}
    )
    postflight = build_postflight(
        ledger_manifest=ledger,
        ledger_rows=(signal,),
        match_manifest=match_manifest,
        match_rows=match.rows,
        result_manifest=changed,
        episode_rows=(episode,),
        source_bar_count=match.source_bar_count,
        source_bars_sha256=match.source_bars_sha256,
        source_eof_verified=True,
        dataset_verified=True,
        version_lifecycle_verified=True,
        no_external_calls=True,
    )
    assert postflight["verdict"] == "REJECTED"
    assert postflight["acceptance_conditions"]["exact_identity"] is False


@pytest.mark.parametrize(
    ("field", "alias"),
    (
        ("source_eof_verified", "false"),
        ("dataset_verified", 1),
        ("version_lifecycle_verified", "true"),
        ("no_external_calls", 0),
    ),
)
def test_postflight_rejects_non_boolean_evidence_aliases(field: str, alias: object) -> None:
    _, signal, match, episode, ledger, match_manifest, result, _ = _slot()
    evidence: dict[str, object] = {
        "source_eof_verified": True,
        "dataset_verified": True,
        "version_lifecycle_verified": True,
        "no_external_calls": True,
    }
    evidence[field] = alias
    with pytest.raises(AtomicBenchmarkIntegrityError, match="exact boolean"):
        build_postflight(
            ledger_manifest=ledger,
            ledger_rows=(signal,),
            match_manifest=match_manifest,
            match_rows=match.rows,
            result_manifest=result,
            episode_rows=(episode,),
            source_bar_count=match.source_bar_count,
            source_bars_sha256=match.source_bars_sha256,
            **evidence,
        )


def test_framing_golden_vector() -> None:
    frame = frame_member("slots/01/result_manifest.json", b"{}\n")
    assert frame.hex() == (
        "0000001d736c6f74732f30312f726573756c745f6d616e69666573742e6a736f6e"
        "00000000000000037b7d0a"
    )
    assert hashlib.sha256(frame).hexdigest() == (
        "5401347ec77cbd9bd93b1a82a3f181b4c507246e789e34b697ed12f87dd7da2b"
    )


def test_public_bundle_is_all_seven_and_reproducible() -> None:
    slots = [_slot(slot) for slot in range(1, 8)]
    attempts = [
        {
            "slot_sequence": slot,
            "attempt_id": f"attempt-{slot}",
            "attempt_revision": 1,
            "accepted_retry_generation": 1,
            "hypothesis_id": values[0],
            "result_manifest_digest": values[6]["result_manifest_digest"],
            "result_projection_digest": values[6]["result_projection_digest"],
            "postflight_digest": values[7]["postflight_digest"],
        }
        for slot, values in enumerate(slots, start=1)
    ]
    release = build_family_release(
        family_id="r6-family-test",
        matrix_id="r6-matrix-test",
        registration_digest=SHA,
        research_baseline_digest=SHA,
        protocol_core_digest=SHA,
        accepted_attempts=attempts,
    )
    inputs = [
        SlotBundleInput(
            result_manifest=values[6],
            postflight=values[7],
            episode_rows=(values[3],),
        )
        for values in slots
    ]
    first = build_public_bundle(family_release=release, slot_inputs=inputs)
    second = build_public_bundle(family_release=release, slot_inputs=inputs)
    assert first == second
    assert first.manifest["bundle_member_count"] == 21
    assert first.manifest["ordered_slot_payloads"][0]["episode_chunks"][0][
        "path"
    ] == "slots/01/episodes/00000001.jsonl"


def test_public_bundle_rejects_member_byte_tamper() -> None:
    slots = [_slot(slot) for slot in range(1, 8)]
    attempts = [
        {
            "slot_sequence": slot,
            "attempt_id": f"attempt-{slot}",
            "attempt_revision": 1,
            "accepted_retry_generation": 1,
            "hypothesis_id": values[0],
            "result_manifest_digest": values[6]["result_manifest_digest"],
            "result_projection_digest": values[6]["result_projection_digest"],
            "postflight_digest": values[7]["postflight_digest"],
        }
        for slot, values in enumerate(slots, start=1)
    ]
    release = build_family_release(
        family_id="r6-family-test",
        matrix_id="r6-matrix-test",
        registration_digest=SHA,
        research_baseline_digest=SHA,
        protocol_core_digest=SHA,
        accepted_attempts=attempts,
    )
    bundle = build_public_bundle(
        family_release=release,
        slot_inputs=[
            SlotBundleInput(values[6], values[7], (values[3],)) for values in slots
        ],
    )
    members = list(bundle.members)
    members[0] = (members[0][0], members[0][1] + b" ")
    with pytest.raises(AtomicBenchmarkIntegrityError, match="member evidence"):
        verify_public_bundle(
            bundle.manifest, members=members, family_release=release
        )


def test_public_bundle_rejects_self_consistent_outer_manifest_tamper() -> None:
    slots = [_slot(slot) for slot in range(1, 8)]
    attempts = [
        {
            "slot_sequence": slot,
            "attempt_id": f"attempt-{slot}",
            "attempt_revision": 1,
            "accepted_retry_generation": 1,
            "hypothesis_id": values[0],
            "result_manifest_digest": values[6]["result_manifest_digest"],
            "result_projection_digest": values[6]["result_projection_digest"],
            "postflight_digest": values[7]["postflight_digest"],
        }
        for slot, values in enumerate(slots, start=1)
    ]
    release = build_family_release(
        family_id="r6-family-test",
        matrix_id="r6-matrix-test",
        registration_digest=SHA,
        research_baseline_digest=SHA,
        protocol_core_digest=SHA,
        accepted_attempts=attempts,
    )
    bundle = build_public_bundle(
        family_release=release,
        slot_inputs=[
            SlotBundleInput(values[6], values[7], (values[3],)) for values in slots
        ],
    )
    manifest = deepcopy(bundle.manifest)
    members = list(bundle.members)
    members[0] = (members[0][0], canonical_object_bytes({}))
    descriptor = manifest["ordered_slot_payloads"][0]
    descriptor["result_manifest_byte_count"] = len(members[0][1])
    descriptor["result_manifest_file_sha256"] = hashlib.sha256(
        members[0][1]
    ).hexdigest()
    manifest["bundle_content_byte_count"] = sum(
        len(content) for _, content in members
    )
    manifest["bundle_payload_sha256"] = hashlib.sha256(
        b"".join(frame_member(path, content) for path, content in members)
    ).hexdigest()
    manifest["bundle_manifest_digest"] = digest(
        {
            key: value
            for key, value in manifest.items()
            if key != "bundle_manifest_digest"
        }
    )
    with pytest.raises(AtomicBenchmarkIntegrityError, match="result manifest"):
        verify_public_bundle(
            manifest, members=members, family_release=release
        )


def test_public_bundle_rejects_physical_chunk_repartition() -> None:
    slots = [_slot(slot) for slot in range(1, 8)]
    first = slots[0]
    first_episodes = _expanded_episodes(first[3], 10001)
    first_summary = build_summary(
        first_episodes,
        family_id=first[6]["family_id"],
        hypothesis_id=first[0],
    )
    first_result = build_result_manifest(
        replay_id=first[6]["replay_id"],
        match_manifest=first[5],
        episode_rows=first_episodes,
        summary=first_summary,
    )
    results = [first_result, *(values[6] for values in slots[1:])]
    postflights = [
        _accepted_postflight_for_result(first[7], first_result),
        *(values[7] for values in slots[1:]),
    ]
    attempts = [
        {
            "slot_sequence": slot,
            "attempt_id": f"attempt-{slot}",
            "attempt_revision": 1,
            "accepted_retry_generation": 1,
            "hypothesis_id": values[0],
            "result_manifest_digest": results[slot - 1]["result_manifest_digest"],
            "result_projection_digest": results[slot - 1]["result_projection_digest"],
            "postflight_digest": postflights[slot - 1]["postflight_digest"],
        }
        for slot, values in enumerate(slots, start=1)
    ]
    release = build_family_release(
        family_id="r6-family-test",
        matrix_id="r6-matrix-test",
        registration_digest=SHA,
        research_baseline_digest=SHA,
        protocol_core_digest=SHA,
        accepted_attempts=attempts,
    )
    episode_sets = [first_episodes, *((values[3],) for values in slots[1:])]
    bundle = build_public_bundle(
        family_release=release,
        slot_inputs=[
            SlotBundleInput(results[index], postflights[index], episode_sets[index])
            for index in range(7)
        ],
    )
    manifest = deepcopy(bundle.manifest)
    members = list(bundle.members)
    first_chunk_path = "slots/01/episodes/00000001.jsonl"
    final_chunk_path = "slots/01/episodes/00000002.jsonl"
    member_index = {path: index for index, (path, _) in enumerate(members)}
    original = (
        members[member_index[first_chunk_path]][1]
        + members[member_index[final_chunk_path]][1]
    )
    lines = original.splitlines(keepends=True)
    repartitioned = (b"".join(lines[:9999]), b"".join(lines[9999:]))
    for path, content in zip(
        (first_chunk_path, final_chunk_path), repartitioned, strict=True
    ):
        members[member_index[path]] = (path, content)
    chunks = manifest["ordered_slot_payloads"][0]["episode_chunks"]
    for descriptor, content in zip(chunks, repartitioned, strict=True):
        descriptor["byte_count"] = len(content)
        descriptor["sha256"] = hashlib.sha256(content).hexdigest()
    manifest["bundle_payload_sha256"] = hashlib.sha256(
        b"".join(frame_member(path, content) for path, content in members)
    ).hexdigest()
    manifest["bundle_manifest_digest"] = digest(
        {
            key: value
            for key, value in manifest.items()
            if key != "bundle_manifest_digest"
        }
    )

    with pytest.raises(AtomicBenchmarkIntegrityError, match="physical chunk"):
        verify_public_bundle(manifest, members=members, family_release=release)


def test_bundle_builder_requires_all_seven_slots() -> None:
    values = _slot(1)
    attempt = {
        "slot_sequence": 1,
        "attempt_id": "attempt-1",
        "attempt_revision": 1,
        "accepted_retry_generation": 1,
        "hypothesis_id": values[0],
        "result_manifest_digest": values[6]["result_manifest_digest"],
        "result_projection_digest": values[6]["result_projection_digest"],
        "postflight_digest": values[7]["postflight_digest"],
    }
    with pytest.raises(AtomicBenchmarkIntegrityError, match="seven attempts"):
        build_family_release(
            family_id="r6-family-test",
            matrix_id="r6-matrix-test",
            registration_digest=SHA,
            research_baseline_digest=SHA,
            protocol_core_digest=SHA,
            accepted_attempts=[attempt],
        )
