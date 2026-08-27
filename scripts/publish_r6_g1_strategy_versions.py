"""Idempotently admit the four G0-frozen R6 Strategy Versions.

This command mutates only Strategy Catalog Draft/Version/Publish/lifecycle
tables.  It never creates an R6 family, matrix, attempt, replay, paper
activation, provider connection, or broker order.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Mapping

from atomic_strategies.feature_requests import resolve_feature_requests
from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.atomic_benchmark.domain import build_slot_binding, build_version_binding
from backtest.feature_adapters import CompletedOneMinuteKbarFeatureAdapter
from config import backtest as backtest_settings
from features.specifications import FeatureSpecificationRegistry
from strategy_catalog.application import AtomicStrategyCatalogService
from strategy_catalog.drafts import PublishStrategyRequest
from strategy_catalog.parameter_schema import canonical_digest
from strategy_catalog.postgres_repository import PostgresAtomicStrategyRepository


ACTOR_ID = "r6-g1-research-operator"
ACTOR_SESSION_ID = "r6-g1-version-admission-v1"
CHANGE_NOTE = "R6 G1 frozen atomic-entry benchmark Version admission"


@dataclass(frozen=True)
class FrozenAdmission:
    strategy_id: str
    parameters: Mapping[str, object]
    configuration_digest: str
    template_digest: str
    parameter_schema_digest: str
    implementation_digest: str
    feature_request_digest: str
    feature_specification_digest: str
    feature_implementation_digest: str
    feature_runtime_identity_digest: str


FROZEN_ADMISSIONS = (
    FrozenAdmission(
        strategy_id="breakout_previous_high_entry",
        parameters={
            "buffer_bps": "0",
            "entry_window_start": "09:02",
            "entry_window_end": "12:45",
        },
        configuration_digest="71c9825e3dae63177c6895245fe0d56e097b83d2eb755eac93ca812a7dfa6958",
        template_digest="0bb9a3ada6cf743a60eb23497deb3a216c06e2c242ee1ba7a4e326a7f5c3778a",
        parameter_schema_digest="be49db61ef2c085b53d5e08423db572693b0ac9a0ab12dbde814da2eeea7ddea",
        implementation_digest="2bbd4d022933ee03a03dd29d859c3d74aba4799a4135bc8cd8acf74254506370",
        feature_request_digest="66c46a87f173141a540e1371c98e550c1dab9ac35ab6c0e923e229f363c76d31",
        feature_specification_digest="bb0e2ae9f141448e624cf94d7266fe10531bcb0918741de955a959f37a34e1f1",
        feature_implementation_digest="c9231f6978acd99c945f6cc13e26d70468e2203389d94b2d6b16b280e211b323",
        feature_runtime_identity_digest="b184cba15c9ac4abdb6fc26448d579d6bb929fed72bc5ddec59bc62ae82f23a4",
    ),
    FrozenAdmission(
        strategy_id="volume_acceleration_entry",
        parameters={
            "window_minutes": 2,
            "baseline_window_count": 5,
            "minimum_complete_baseline_windows": 4,
            "baseline_method": "MEDIAN",
            "minimum_acceleration_ratio": "1.5",
            "entry_window_start": "09:10",
            "entry_window_end": "12:45",
        },
        configuration_digest="56751a5c501ac430456120694ca242dc49dc1846fdbd06823817162b805cdf3d",
        template_digest="b27cdb41b10fb83bbc1655a9f576503e5aced11df5f35d0739334b2c2560c156",
        parameter_schema_digest="ce34e90236e8008a33c5b4dccba93dc7dbd85908f46de249ed24d8fa47ee3b9d",
        implementation_digest="3924423a7648551bb0acb9de7f23c7a6bea69050eadf9d32561767e9a84ca411",
        feature_request_digest="99a8f980c267efed179fdef10b7a62781e8aab1a51fa3ae8fbd27ebd5059b15d",
        feature_specification_digest="cdebd91a5a9091efbc16e1086ef1da7369cf38888477b723fac4cd30d2eca6c8",
        feature_implementation_digest="faf3cf76dfe6c724a018285bdd49fbab1c2bf5901623bf598916fa609c1d4763",
        feature_runtime_identity_digest="7c8fc1c979188eb3d5dbae1e5eff94ea220b61b7f0f76f8f2bac28fb72d77dad",
    ),
    FrozenAdmission(
        strategy_id="opening_range_breakout_entry",
        parameters={
            "opening_range_minutes": 15,
            "breakout_buffer_pct": "0.1",
            "entry_window_start": "09:15",
            "entry_window_end": "11:00",
        },
        configuration_digest="a99f9896b877a4373c5943fba8ea80992e9f4c8723f9e93ce6bc13f0c8684b3b",
        template_digest="a711753a466229b0a78dd811fdcc68c9403c3d923067e7dd7e587ce608527d39",
        parameter_schema_digest="ea78ef7f319982f398b895edd796bd5b08ffaa689825163cb8ffd7904c762717",
        implementation_digest="66c3002c71c74fa4fc2bddafac55d521b1397332d5600697590ce2468420dece",
        feature_request_digest="3bd2bd03231b2198abbc0ddf5d043c3934330ef4b45f203691c6164357618770",
        feature_specification_digest="3dbd053c9dd8f6ace260911f1527f5a8e81394b8440afd4897bada380fb3c5a4",
        feature_implementation_digest="569a74b31344df02ad36e57e5bd1cc6a76fc956d955b50049e53ee42ec335a1b",
        feature_runtime_identity_digest="f80f409f5f0971a85db2d478265d0bc4b0f46bc233d1ad8135bd6bf7c10b31b9",
    ),
    FrozenAdmission(
        strategy_id="ema_crossover_entry",
        parameters={
            "fast_period": 5,
            "slow_period": 20,
            "entry_window_start": "09:20",
            "entry_window_end": "12:45",
        },
        configuration_digest="1f898e9c17b067ab89613a97bf7511557a28af9166474bb362db97cacae3a334",
        template_digest="711503591d07722d7bc4e2ada6a5d9e675a8c0a47c3695336afeffe4a160d2a7",
        parameter_schema_digest="ae164be56dcba6b8f0ee6e7c1097bb27b80ba05cb204b8cbed0d5e3673c966ca",
        implementation_digest="6124c9d0581f8f675c3723cec199e0fcbabdef0f5930c2949ba45fde5152f8a3",
        feature_request_digest="b32290073e444c285218a7abbd9c6634a559e7ddc42a219d1ca01084545bac52",
        feature_specification_digest="1a51e9775eeb5f526fc978a509a42d4063c5483a27fd7f881caf0963f19d0c5e",
        feature_implementation_digest="32ea06d3df0c01cebbec86b6b8bb55c8eb0a306f7624bfa674a70d6cbbc8755a",
        feature_runtime_identity_digest="74a2ecbd575cbfffec2d83ca8aa8f3af961b0a6582247d7c6a1d1f708c80d8c5",
    ),
)

FROZEN_BINDING_TARGETS = (
    (1, "breakout_previous_high_entry", "71c9825e3dae63177c6895245fe0d56e097b83d2eb755eac93ca812a7dfa6958", "ef5541b185951aca1b83a35ff582b3489669381ec5ce99289b8f1c73b5fe08cd"),
    (2, "rolling_return_entry", "681aa02fda0e0390b626c7db1be7fa921a0b176ab45a7a5d99608e946b3f2967", "c15bc531dba13bb829fc9c171c3dd8da277115e159a668e40eedf3837b864e7a"),
    (3, "volume_acceleration_entry", "56751a5c501ac430456120694ca242dc49dc1846fdbd06823817162b805cdf3d", "fb155920d9fcb96e777404a89ee167b1819b1965d5f502b4b9c5d28a7699e4c9"),
    (4, "opening_range_breakout_entry", "a99f9896b877a4373c5943fba8ea80992e9f4c8723f9e93ce6bc13f0c8684b3b", "8e4a3cd8d37c072ca00157c5aec3bed184eaaa285c243202e663bac74e869dcb"),
    (5, "ema_crossover_entry", "1f898e9c17b067ab89613a97bf7511557a28af9166474bb362db97cacae3a334", "858b863d0cd4abbbb563b3d52e9d1ec8b16e289b4f19b532c188716ed939f465"),
    (6, "rsi_oversold_entry", "f90f85c194bee56b587712d213c6eda06207242ea5770d8549441f1cc98a4ed3", "cd3c57ae47e6b95064f8ba561015addef4ba0201d4e44f38b66539c8f7ce1aad"),
    (7, "bollinger_lower_reentry_entry", "1143834e51682660121ba74b7118e3e3dc7485da5be55e766bd33d8a45fc81ae", "c80f7edd7ce1452401a249c347c70796d807e0ba21f2440bdff3c6acb9274612"),
)


def _configuration(template: Any, parameters: Mapping[str, object]) -> dict[str, object]:
    canonical = template.validate_parameters(parameters)
    return {
        "strategy_id": template.strategy_id,
        "parameters": canonical,
        "parameter_schema_version": template.parameter_schema.version,
        "parameter_schema_digest": template.parameter_schema.schema_digest,
        "parameters_digest": canonical_digest(canonical),
        "template_digest": template.template_digest,
        "implementation_digest": template.implementation_digest,
    }


def _verify_frozen(registry: AtomicStrategyRegistry, frozen: FrozenAdmission) -> None:
    strategy = registry.strategy(frozen.strategy_id)
    template = strategy.template
    configuration = _configuration(template, frozen.parameters)
    request = resolve_feature_requests(template, configuration["parameters"])[0]
    specification = FeatureSpecificationRegistry().get(request.feature_id)
    checks = {
        "configuration_digest": canonical_digest(configuration),
        "template_digest": template.template_digest,
        "parameter_schema_digest": template.parameter_schema.schema_digest,
        "implementation_digest": template.implementation_digest,
        "feature_request_digest": request.request_digest,
        "feature_specification_digest": specification.specification_digest,
        "feature_implementation_digest": specification.implementation_digest,
        "feature_runtime_identity_digest": request.runtime_identity_digest(
            adapter_identity=CompletedOneMinuteKbarFeatureAdapter.identity,
            cadence=specification.cadence,
        ),
    }
    for field, actual in checks.items():
        if actual != getattr(frozen, field):
            raise RuntimeError(
                f"{frozen.strategy_id} {field} drift: "
                f"expected={getattr(frozen, field)} actual={actual}"
            )


def _row_mapping(cursor: Any, row: object) -> dict[str, object]:
    if isinstance(row, Mapping):
        return dict(row)
    return {
        str(column.name): value
        for column, value in zip(cursor.description, row, strict=True)
    }


def _json_mapping(value: object, label: str) -> dict[str, object]:
    resolved = json.loads(value) if isinstance(value, str) else value
    if not isinstance(resolved, Mapping):
        raise RuntimeError(f"{label} 必須是 JSON object")
    return dict(resolved)


def _durable_version(
    connection: Any,
    *,
    registry: AtomicStrategyRegistry,
    strategy_id: str,
    configuration_digest: str,
    expected_actor_id: str | None = None,
    expected_actor_session_id: str | None = None,
    expected_change_note: str | None = None,
) -> dict[str, object] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                v.strategy_version_id AS version_id,
                v.strategy_id AS version_strategy_id,
                v.source_draft_id,
                v.version_number,
                v.parameters_json AS version_parameters_json,
                v.parameter_schema_version,
                v.parameter_schema_digest,
                v.parameters_digest AS version_parameters_digest,
                v.template_digest,
                v.implementation_digest,
                v.configuration_digest,
                v.change_note AS version_change_note,
                v.created_by AS version_created_by,
                stored_template.template_digest AS stored_template_digest,
                stored_template.implementation_digest AS stored_implementation_digest,
                stored_template.parameter_schema_version AS stored_schema_version,
                stored_template.parameter_schema_digest AS stored_schema_digest,
                draft.strategy_id AS draft_strategy_id,
                draft.revision AS draft_revision,
                draft.parameters_json AS draft_parameters_json,
                draft.parameters_digest AS draft_parameters_digest,
                draft.change_note AS draft_change_note,
                draft.created_by AS draft_created_by,
                draft.updated_by AS draft_updated_by,
                draft.published_strategy_version_id,
                draft.published_event_id AS draft_published_event_id,
                draft.published_operation_id AS draft_published_operation_id,
                draft.published_at AS draft_published_at,
                state.status AS lifecycle_status,
                state.last_sequence AS lifecycle_sequence,
                state.last_event_id AS lifecycle_event_id,
                state.projection_digest AS lifecycle_projection_digest,
                event.sequence AS event_sequence,
                event.event_type,
                event.from_status,
                event.to_status,
                event.evidence_json,
                event.evidence_digest,
                event.reason AS event_reason,
                event.actor_id AS event_actor_id,
                event.actor_session_id AS event_actor_session_id,
                event.idempotency_key AS event_idempotency_key,
                event.request_digest AS event_request_digest,
                event.expected_sequence AS event_expected_sequence,
                event.occurred_at AS event_occurred_at,
                event.event_digest,
                operation.publish_operation_id,
                operation.idempotency_key AS operation_idempotency_key,
                operation.request_digest AS operation_request_digest,
                operation.expected_draft_revision,
                operation.strategy_version_id AS operation_version_id,
                operation.published_event_id AS operation_event_id,
                operation.result_digest AS publish_result_digest,
                outbox.outbox_id,
                outbox.event_digest AS outbox_event_digest,
                outbox.topic AS outbox_topic,
                outbox.payload_json AS outbox_payload_json,
                outbox.payload_digest AS outbox_payload_digest
            FROM backtest.strategy_versions AS v
            LEFT JOIN backtest.strategy_templates AS stored_template
              ON stored_template.strategy_id = v.strategy_id
            LEFT JOIN backtest.strategy_version_drafts AS draft
              ON draft.draft_id = v.source_draft_id
            LEFT JOIN backtest.strategy_version_state AS state
              ON state.strategy_version_id = v.strategy_version_id
            LEFT JOIN backtest.strategy_version_events AS event
              ON event.event_id = state.last_event_id
            LEFT JOIN backtest.strategy_publish_operations AS operation
              ON operation.strategy_version_id = v.strategy_version_id
            LEFT JOIN backtest.strategy_lifecycle_outbox AS outbox
              ON outbox.event_id = event.event_id
            WHERE v.strategy_id = %s AND v.configuration_digest = %s
            ORDER BY v.version_number
            """,
            (strategy_id, configuration_digest),
        )
        rows = [_row_mapping(cursor, row) for row in cursor.fetchall()]
    if len(rows) > 1:
        raise RuntimeError(f"{strategy_id} durable publication evidence 不唯一")
    if not rows:
        return None
    row = rows[0]
    required = (
        "source_draft_id",
        "lifecycle_event_id",
        "publish_operation_id",
        "outbox_id",
    )
    if any(row[field] is None for field in required):
        raise RuntimeError(f"{strategy_id} durable publication evidence 不完整")

    template = registry.strategy(strategy_id).template
    parameters = _json_mapping(row["version_parameters_json"], "Version parameters")
    canonical_parameters = template.validate_parameters(parameters)
    configuration = {
        "strategy_id": str(row["version_strategy_id"]),
        "parameters": parameters,
        "parameter_schema_version": str(row["parameter_schema_version"]),
        "parameter_schema_digest": str(row["parameter_schema_digest"]),
        "parameters_digest": str(row["version_parameters_digest"]),
        "template_digest": str(row["template_digest"]),
        "implementation_digest": str(row["implementation_digest"]),
    }
    expected_configuration = _configuration(template, canonical_parameters)
    if (
        parameters != canonical_parameters
        or configuration != expected_configuration
        or row["stored_template_digest"] != template.template_digest
        or row["stored_implementation_digest"] != template.implementation_digest
        or row["stored_schema_version"] != template.parameter_schema.version
        or row["stored_schema_digest"] != template.parameter_schema.schema_digest
    ):
        raise RuntimeError(f"{strategy_id} durable Version configuration drift")
    rebuilt_configuration_digest = canonical_digest(configuration)
    if (
        rebuilt_configuration_digest != row["configuration_digest"]
        or rebuilt_configuration_digest != configuration_digest
    ):
        raise RuntimeError(f"{strategy_id} configuration digest 無法重建")

    draft_parameters = _json_mapping(row["draft_parameters_json"], "Draft parameters")
    version_id = str(row["version_id"])
    event_id = str(row["lifecycle_event_id"])
    operation_id = str(row["publish_operation_id"])
    source_draft_id = str(row["source_draft_id"])
    expected_draft_revision = int(row["expected_draft_revision"])
    if (
        row["draft_strategy_id"] != strategy_id
        or int(row["draft_revision"]) != expected_draft_revision + 1
        or draft_parameters != parameters
        or canonical_digest(draft_parameters) != row["draft_parameters_digest"]
        or row["published_strategy_version_id"] != version_id
        or row["draft_published_event_id"] != event_id
        or row["draft_published_operation_id"] != operation_id
        or row["draft_published_at"] is None
    ):
        raise RuntimeError(f"{strategy_id} sealed Draft evidence drift")

    evidence = {**configuration, "source_draft_id": source_draft_id}
    event_document = {
        "event_id": event_id,
        "strategy_version_id": version_id,
        "sequence": 1,
        "event_type": "PUBLISHED",
        "from_status": None,
        "to_status": "PUBLISHED",
        "evidence_digest": canonical_digest(evidence),
        "actor_id": str(row["event_actor_id"]),
        "actor_session_id": str(row["event_actor_session_id"]),
        "idempotency_key": str(row["event_idempotency_key"]),
        "request_digest": str(row["event_request_digest"]),
        "expected_sequence": 0,
        "occurred_at": row["event_occurred_at"].isoformat(),
    }
    request = PublishStrategyRequest(
        draft_id=source_draft_id,
        idempotency_key=str(row["event_idempotency_key"]),
        expected_draft_revision=expected_draft_revision,
        actor_id=str(row["event_actor_id"]),
        actor_session_id=str(row["event_actor_session_id"]),
        change_note=str(row["event_reason"]),
    )
    if (
        int(row["event_sequence"]) != 1
        or row["event_type"] != "PUBLISHED"
        or row["from_status"] is not None
        or row["to_status"] != "PUBLISHED"
        or _json_mapping(row["evidence_json"], "event evidence") != evidence
        or row["evidence_digest"] != canonical_digest(evidence)
        or int(row["event_expected_sequence"]) != 0
        or row["event_request_digest"] != request.request_digest
        or row["event_digest"] != canonical_digest(event_document)
    ):
        raise RuntimeError(f"{strategy_id} publish event evidence drift")

    result_document = {
        "publish_operation_id": operation_id,
        "draft_id": source_draft_id,
        "strategy_version_id": version_id,
        "published_event_id": event_id,
        "version_number": int(row["version_number"]),
        "configuration_digest": rebuilt_configuration_digest,
    }
    if (
        row["operation_idempotency_key"] != row["event_idempotency_key"]
        or row["operation_request_digest"] != request.request_digest
        or expected_draft_revision < 1
        or row["operation_version_id"] != version_id
        or row["operation_event_id"] != event_id
        or row["publish_result_digest"] != canonical_digest(result_document)
    ):
        raise RuntimeError(f"{strategy_id} publish operation result drift")

    projection = {
        "strategy_version_id": version_id,
        "status": "PUBLISHED",
        "last_sequence": 1,
        "last_event_id": event_id,
    }
    if (
        row["lifecycle_status"] != "PUBLISHED"
        or int(row["lifecycle_sequence"]) != 1
        or row["lifecycle_projection_digest"] != canonical_digest(projection)
    ):
        raise RuntimeError(f"{strategy_id} lifecycle projection drift")

    outbox_payload = {**event_document, "event_digest": row["event_digest"]}
    if (
        row["outbox_event_digest"] != row["event_digest"]
        or row["outbox_topic"] != "strategy.lifecycle.v1"
        or _json_mapping(row["outbox_payload_json"], "outbox payload")
        != outbox_payload
        or row["outbox_payload_digest"] != canonical_digest(outbox_payload)
    ):
        raise RuntimeError(f"{strategy_id} lifecycle outbox evidence drift")

    if expected_actor_id is not None and (
        row["event_actor_id"] != expected_actor_id
        or row["version_created_by"] != expected_actor_id
        or row["draft_created_by"] != expected_actor_id
        or row["draft_updated_by"] != expected_actor_id
    ):
        raise RuntimeError(f"{strategy_id} publication actor drift")
    if expected_actor_id is not None and expected_draft_revision != 1:
        raise RuntimeError(f"{strategy_id} publication Draft revision drift")
    if (
        expected_actor_session_id is not None
        and row["event_actor_session_id"] != expected_actor_session_id
    ):
        raise RuntimeError(f"{strategy_id} publication actor session drift")
    if expected_change_note is not None and (
        row["event_reason"] != expected_change_note
        or row["version_change_note"] != expected_change_note
        or row["draft_change_note"] != expected_change_note
    ):
        raise RuntimeError(f"{strategy_id} publication change note drift")

    return {
        "strategy_version_id": version_id,
        "version_number": int(row["version_number"]),
        "configuration_digest": rebuilt_configuration_digest,
        "lifecycle_status": "PUBLISHED",
        "lifecycle_sequence": 1,
        "lifecycle_event_id": event_id,
        "lifecycle_projection_digest": canonical_digest(projection),
        "publish_operation_id": operation_id,
        "publish_result_digest": canonical_digest(result_document),
        "publish_actor_id": str(row["event_actor_id"]),
        "publish_actor_session_id": str(row["event_actor_session_id"]),
        "replayed": True,
    }


def _existing_version(
    connection: Any,
    frozen: FrozenAdmission,
    registry: AtomicStrategyRegistry,
) -> dict[str, object] | None:
    return _durable_version(
        connection,
        registry=registry,
        strategy_id=frozen.strategy_id,
        configuration_digest=frozen.configuration_digest,
        expected_actor_id=ACTOR_ID,
        expected_actor_session_id=ACTOR_SESSION_ID,
        expected_change_note=CHANGE_NOTE,
    )


def _verify_lifecycle(value: Mapping[str, object], frozen: FrozenAdmission) -> None:
    if value["configuration_digest"] != frozen.configuration_digest:
        raise RuntimeError(f"{frozen.strategy_id} configuration digest mismatch")
    if value["lifecycle_status"] != "PUBLISHED" or value["lifecycle_sequence"] != 1:
        raise RuntimeError(f"{frozen.strategy_id} lifecycle 必須停在 PUBLISHED sequence 1")
    expected = canonical_digest(
        {
            "strategy_version_id": value["strategy_version_id"],
            "status": "PUBLISHED",
            "last_sequence": 1,
            "last_event_id": value["lifecycle_event_id"],
        }
    )
    if value["lifecycle_projection_digest"] != expected:
        raise RuntimeError(f"{frozen.strategy_id} lifecycle projection digest mismatch")


def publish_versions(connection: Any, *, execute: bool) -> tuple[dict[str, object], ...]:
    registry = AtomicStrategyRegistry()
    repository = PostgresAtomicStrategyRepository(connection)
    service = AtomicStrategyCatalogService(repository, registry.templates())
    results: list[dict[str, object]] = []
    for frozen in FROZEN_ADMISSIONS:
        _verify_frozen(registry, frozen)
        existing = _existing_version(connection, frozen, registry)
        if existing is not None:
            _verify_lifecycle(existing, frozen)
            results.append({"strategy_id": frozen.strategy_id, **existing})
            continue
        if not execute:
            results.append(
                {
                    "strategy_id": frozen.strategy_id,
                    "configuration_digest": frozen.configuration_digest,
                    "action": "WOULD_PUBLISH",
                }
            )
            continue
        key_suffix = f"{frozen.strategy_id}:{frozen.configuration_digest}"
        draft = service.create_draft(
            frozen.strategy_id,
            frozen.parameters,
            actor_id=ACTOR_ID,
            change_note=CHANGE_NOTE,
            idempotency_key=f"r6-g1-draft-v1:{key_suffix}",
            operation_scope=f"r6:g1:version-admission:{frozen.strategy_id}",
        )
        published = service.publish(
            PublishStrategyRequest(
                draft_id=draft.draft_id,
                idempotency_key=f"r6-g1-publish-v1:{key_suffix}",
                expected_draft_revision=1,
                actor_id=ACTOR_ID,
                actor_session_id=ACTOR_SESSION_ID,
                change_note=CHANGE_NOTE,
            )
        )
        current = _existing_version(connection, frozen, registry)
        if current is None or current["strategy_version_id"] != published.strategy_version_id:
            raise RuntimeError(f"{frozen.strategy_id} publish result 無法由 durable state 重建")
        current = {
            **current,
            "publish_operation_id": published.publish_operation_id,
            "publish_result_digest": published.result_digest,
            "replayed": published.replayed,
        }
        _verify_lifecycle(current, frozen)
        results.append({"strategy_id": frozen.strategy_id, **current})
    return tuple(results)


def binding_inventory(connection: Any) -> tuple[dict[str, object], ...]:
    registry = AtomicStrategyRegistry()
    new_admissions = {
        (item.strategy_id, item.configuration_digest): item
        for item in FROZEN_ADMISSIONS
    }
    values: list[dict[str, object]] = []
    for slot, strategy_id, configuration_digest, specification_digest in FROZEN_BINDING_TARGETS:
        is_new = (strategy_id, configuration_digest) in new_admissions
        durable = _durable_version(
            connection,
            registry=registry,
            strategy_id=strategy_id,
            configuration_digest=configuration_digest,
            expected_actor_id=ACTOR_ID if is_new else None,
            expected_actor_session_id=ACTOR_SESSION_ID if is_new else None,
            expected_change_note=CHANGE_NOTE if is_new else None,
        )
        if durable is None:
            raise RuntimeError(
                f"{strategy_id} frozen configuration 必須恰有一個 Version"
            )
        version_binding = build_version_binding(
            hypothesis_spec_digest=specification_digest,
            strategy_version_id=str(durable["strategy_version_id"]),
            version_number=int(durable["version_number"]),
            strategy_configuration_digest=configuration_digest,
            lifecycle_status=str(durable["lifecycle_status"]),
            lifecycle_sequence=int(durable["lifecycle_sequence"]),
            lifecycle_event_id=str(durable["lifecycle_event_id"]),
            lifecycle_projection_digest=str(durable["lifecycle_projection_digest"]),
        )
        slot_binding = build_slot_binding(
            slot_sequence=slot,
            hypothesis_spec_digest=specification_digest,
            version_binding=version_binding,
        )
        values.append(
            {
                "slot_sequence": slot,
                "strategy_id": strategy_id,
                **version_binding,
                "version_binding_digest": canonical_digest(version_binding),
                "hypothesis_id": slot_binding["hypothesis_id"],
                "slot_digest": canonical_digest(slot_binding),
            }
        )
    return tuple(values)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Idempotently publish the four G0-frozen R6 G1 Strategy Versions."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform the four scoped Strategy Catalog publications.",
    )
    arguments = parser.parse_args()
    if backtest_settings.BACKTEST_DATABASE_BACKEND != "postgresql":
        raise RuntimeError("R6 G1 Version admission 只支援 application PostgreSQL")
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("請安裝 PostgreSQL optional dependency") from error
    with psycopg.connect(backtest_settings.BACKTEST_DATABASE_URL) as connection:
        results = publish_versions(connection, execute=arguments.execute)
        bindings = (
            binding_inventory(connection)
            if arguments.execute
            or all("strategy_version_id" in result for result in results)
            else ()
        )
    print(
        json.dumps(
            {"executed": arguments.execute, "versions": results, "bindings": bindings},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
