"""PostgreSQL adapter for atomic Strategy Draft and Publish transactions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from strategy_catalog.drafts import (
    PublishStrategyRequest,
    PublishStrategyResult,
    StrategyDraft,
    StrategyTemplate,
    StrategyVersion,
)
from strategy_catalog.lifecycle import StrategyLifecycleStatus
from strategy_catalog.parameter_schema import canonical_digest, canonical_json
from strategy_catalog.repository import StrategyCatalogConflict
from strategy_catalog.domain import StrategyRole
from strategy_catalog.sets import (
    CompositionPolicy,
    ExactStrategySetSnapshot,
    StrategySetMemberSnapshot,
)


def _json(value: Mapping[str, Any] | list[Any]) -> str:
    return canonical_json(value)


def _decode_json(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return dict(json.loads(str(value)))


def _row(cursor: Any, raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    return {
        column.name if hasattr(column, "name") else column[0]: raw[index]
        for index, column in enumerate(cursor.description)
    }


class PostgresAtomicStrategyRepository:
    """Uses PostgreSQL row locks; schema creation belongs to migrations only."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def upsert_template(self, template: StrategyTemplate) -> None:
        document = template.template_document
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO backtest.strategy_templates (
                    strategy_id, display_name_zh_tw, role, session_phase,
                    implementation_version, implementation_digest,
                    parameter_schema_version, parameter_schema_digest,
                    parameter_schema_json,
                    required_capabilities_json, feature_requirements_json,
                    runtime_bindings_json, description_zh_tw, template_digest
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                    %s::jsonb, %s::jsonb, %s::jsonb, %s, %s
                )
                ON CONFLICT (strategy_id) DO UPDATE SET
                    display_name_zh_tw = EXCLUDED.display_name_zh_tw,
                    role = EXCLUDED.role,
                    session_phase = EXCLUDED.session_phase,
                    implementation_version = EXCLUDED.implementation_version,
                    implementation_digest = EXCLUDED.implementation_digest,
                    parameter_schema_version = EXCLUDED.parameter_schema_version,
                    parameter_schema_digest = EXCLUDED.parameter_schema_digest,
                    parameter_schema_json = EXCLUDED.parameter_schema_json,
                    required_capabilities_json = EXCLUDED.required_capabilities_json,
                    feature_requirements_json = EXCLUDED.feature_requirements_json,
                    runtime_bindings_json = EXCLUDED.runtime_bindings_json,
                    description_zh_tw = EXCLUDED.description_zh_tw,
                    template_digest = EXCLUDED.template_digest,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    template.strategy_id,
                    template.display_name_zh_tw,
                    template.role.value,
                    template.session_phase.value,
                    template.implementation_version,
                    template.implementation_digest,
                    template.parameter_schema.version,
                    template.parameter_schema.schema_digest,
                    _json(template.parameter_schema.schema_document),
                    _json(list(template.required_capabilities)),
                    _json([dict(item) for item in template.feature_requirements]),
                    _json(dict(template.runtime_bindings)),
                    template.description_zh_tw,
                    template.template_digest,
                ),
            )

    def create_draft(
        self,
        template: StrategyTemplate,
        parameters: Mapping[str, object],
        *,
        actor_id: str,
        change_note: str = "",
    ) -> StrategyDraft:
        if not actor_id.strip():
            raise ValueError("actor_id 不可為空")
        canonical = template.validate_parameters(parameters)
        parameters_digest = canonical_digest(canonical)
        draft_id = str(uuid4())
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT template_digest
                FROM backtest.strategy_templates
                WHERE strategy_id = %s
                """,
                (template.strategy_id,),
            )
            raw_template = cursor.fetchone()
            if raw_template is None:
                raise StrategyCatalogConflict(
                    "STRATEGY_TEMPLATE_NOT_REGISTERED",
                    f"策略 Template 尚未註冊：{template.strategy_id}",
                )
            stored_digest = (
                raw_template[0]
                if not isinstance(raw_template, Mapping)
                else raw_template["template_digest"]
            )
            if str(stored_digest) != template.template_digest:
                raise StrategyCatalogConflict(
                    "TEMPLATE_DIGEST_MISMATCH",
                    "資料庫 Template 與目前部署程式不一致",
                )
            cursor.execute(
                """
                INSERT INTO backtest.strategy_version_drafts (
                    draft_id, strategy_id, revision, parameters_json,
                    parameters_digest, change_note, created_by, updated_by
                ) VALUES (%s, %s, 1, %s::jsonb, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    draft_id,
                    template.strategy_id,
                    _json(canonical),
                    parameters_digest,
                    change_note.strip(),
                    actor_id.strip(),
                    actor_id.strip(),
                ),
            )
            return self._draft(_row(cursor, cursor.fetchone()))

    def get_draft(self, draft_id: str) -> StrategyDraft:
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT * FROM backtest.strategy_version_drafts WHERE draft_id = %s",
                (draft_id,),
            )
            raw = cursor.fetchone()
            if raw is None:
                raise StrategyCatalogConflict("DRAFT_NOT_FOUND", f"找不到 Draft：{draft_id}")
            return self._draft(_row(cursor, raw))

    def get_version(self, strategy_version_id: str) -> StrategyVersion:
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT * FROM backtest.strategy_versions WHERE strategy_version_id = %s",
                (strategy_version_id,),
            )
            raw = cursor.fetchone()
            if raw is None:
                raise StrategyCatalogConflict(
                    "STRATEGY_VERSION_NOT_FOUND",
                    f"找不到 Strategy Version：{strategy_version_id}",
                )
            row = _row(cursor, raw)
            return StrategyVersion(
                strategy_version_id=str(row["strategy_version_id"]),
                strategy_id=str(row["strategy_id"]),
                source_draft_id=str(row["source_draft_id"]),
                version_number=int(row["version_number"]),
                parameters=_decode_json(row["parameters_json"]),
                parameter_schema_version=str(row["parameter_schema_version"]),
                parameter_schema_digest=str(row["parameter_schema_digest"]),
                parameters_digest=str(row["parameters_digest"]),
                template_digest=str(row["template_digest"]),
                implementation_digest=str(row["implementation_digest"]),
                configuration_digest=str(row["configuration_digest"]),
                change_note=str(row["change_note"]),
                created_by=str(row["created_by"]),
                created_at=row["created_at"],
                published_at=row["published_at"],
            )

    def publish_draft(
        self,
        request: PublishStrategyRequest,
        template: StrategyTemplate,
    ) -> PublishStrategyResult:
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM backtest.strategy_version_drafts
                WHERE draft_id = %s
                FOR UPDATE
                """,
                (request.draft_id,),
            )
            raw_draft = cursor.fetchone()
            if raw_draft is None:
                raise StrategyCatalogConflict(
                    "DRAFT_NOT_FOUND",
                    f"找不到 Draft：{request.draft_id}",
                )
            draft = _row(cursor, raw_draft)

            replay = self._publish_operation(cursor, request.draft_id, request.idempotency_key)
            if replay is not None:
                if replay["request_digest"] != request.request_digest:
                    raise StrategyCatalogConflict(
                        "IDEMPOTENCY_CONFLICT",
                        "相同 idempotency key 的 Publish 內容不同",
                    )
                return PublishStrategyResult(
                    publish_operation_id=str(replay["publish_operation_id"]),
                    draft_id=request.draft_id,
                    strategy_version_id=str(replay["strategy_version_id"]),
                    published_event_id=str(replay["published_event_id"]),
                    version_number=int(replay["version_number"]),
                    configuration_digest=str(replay["configuration_digest"]),
                    result_digest=str(replay["result_digest"]),
                    replayed=True,
                )

            if draft["published_strategy_version_id"] is not None:
                raise StrategyCatalogConflict(
                    "DRAFT_ALREADY_PUBLISHED",
                    "Draft 已發布，其他 idempotency key 不可建立第二個 Version",
                    details={
                        "strategy_version_id": str(draft["published_strategy_version_id"]),
                        "published_event_id": str(draft["published_event_id"]),
                    },
                )
            if int(draft["revision"]) != request.expected_draft_revision:
                raise StrategyCatalogConflict(
                    "DRAFT_REVISION_CONFLICT",
                    "Draft revision 已變更",
                    details={"current_revision": int(draft["revision"])},
                )
            if str(draft["strategy_id"]) != template.strategy_id:
                raise StrategyCatalogConflict(
                    "TEMPLATE_MISMATCH",
                    "Publish Template 與 Draft strategy_id 不一致",
                )

            cursor.execute(
                """
                SELECT template_digest
                FROM backtest.strategy_templates
                WHERE strategy_id = %s
                FOR UPDATE
                """,
                (template.strategy_id,),
            )
            raw_template = cursor.fetchone()
            if raw_template is None:
                raise StrategyCatalogConflict(
                    "STRATEGY_TEMPLATE_NOT_REGISTERED",
                    f"策略 Template 尚未註冊：{template.strategy_id}",
                )
            stored_template_digest = (
                raw_template[0]
                if not isinstance(raw_template, Mapping)
                else raw_template["template_digest"]
            )
            if str(stored_template_digest) != template.template_digest:
                raise StrategyCatalogConflict(
                    "TEMPLATE_DIGEST_MISMATCH",
                    "Publish 時 Template 已變更，請重新驗證 Draft",
                )

            parameters = template.validate_parameters(_decode_json(draft["parameters_json"]))
            parameters_digest = canonical_digest(parameters)
            if parameters_digest != str(draft["parameters_digest"]):
                raise StrategyCatalogConflict(
                    "DRAFT_PARAMETERS_DIGEST_MISMATCH",
                    "Draft parameters digest 驗證失敗",
                )

            cursor.execute(
                """
                SELECT COALESCE(MAX(version_number), 0) + 1
                FROM backtest.strategy_versions
                WHERE strategy_id = %s
                """,
                (template.strategy_id,),
            )
            version_number = int(cursor.fetchone()[0])
            now = datetime.now(timezone.utc)
            version_id = str(uuid4())
            event_id = str(uuid4())
            operation_id = str(uuid4())
            outbox_id = str(uuid4())
            configuration = {
                "strategy_id": template.strategy_id,
                "parameters": parameters,
                "parameter_schema_version": template.parameter_schema.version,
                "parameter_schema_digest": template.parameter_schema.schema_digest,
                "parameters_digest": parameters_digest,
                "template_digest": template.template_digest,
                "implementation_digest": template.implementation_digest,
            }
            configuration_digest = canonical_digest(configuration)
            evidence = {**configuration, "source_draft_id": request.draft_id}
            evidence_digest = canonical_digest(evidence)
            event_document = {
                "event_id": event_id,
                "strategy_version_id": version_id,
                "sequence": 1,
                "event_type": "PUBLISHED",
                "from_status": None,
                "to_status": StrategyLifecycleStatus.PUBLISHED.value,
                "evidence_digest": evidence_digest,
                "actor_id": request.actor_id,
                "actor_session_id": request.actor_session_id,
                "idempotency_key": request.idempotency_key,
                "request_digest": request.request_digest,
                "expected_sequence": 0,
                "occurred_at": now.isoformat(),
            }
            event_digest = canonical_digest(event_document)
            projection_digest = canonical_digest(
                {
                    "strategy_version_id": version_id,
                    "status": StrategyLifecycleStatus.PUBLISHED.value,
                    "last_sequence": 1,
                    "last_event_id": event_id,
                }
            )
            result_document = {
                "publish_operation_id": operation_id,
                "draft_id": request.draft_id,
                "strategy_version_id": version_id,
                "published_event_id": event_id,
                "version_number": version_number,
                "configuration_digest": configuration_digest,
            }
            result_digest = canonical_digest(result_document)
            outbox_payload = {**event_document, "event_digest": event_digest}
            outbox_payload_digest = canonical_digest(outbox_payload)

            cursor.execute(
                """
                INSERT INTO backtest.strategy_versions (
                    strategy_version_id, strategy_id, source_draft_id,
                    version_number, parameters_json, parameter_schema_version,
                    parameter_schema_digest, parameters_digest, template_digest,
                    implementation_digest, configuration_digest, change_note,
                    created_by, created_at, published_at
                ) VALUES (
                    %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    version_id,
                    template.strategy_id,
                    request.draft_id,
                    version_number,
                    _json(parameters),
                    template.parameter_schema.version,
                    template.parameter_schema.schema_digest,
                    parameters_digest,
                    template.template_digest,
                    template.implementation_digest,
                    configuration_digest,
                    request.change_note.strip() or str(draft["change_note"]),
                    request.actor_id,
                    now,
                    now,
                ),
            )
            cursor.execute(
                """
                INSERT INTO backtest.strategy_version_events (
                    event_id, strategy_version_id, sequence, event_type,
                    from_status, to_status, evidence_json, evidence_digest,
                    reason, actor_id, actor_session_id, idempotency_key,
                    request_digest, expected_sequence, occurred_at, event_digest
                ) VALUES (
                    %s, %s, 1, 'PUBLISHED', NULL, %s, %s::jsonb, %s, %s,
                    %s, %s, %s, %s, 0, %s, %s
                )
                """,
                (
                    event_id,
                    version_id,
                    StrategyLifecycleStatus.PUBLISHED.value,
                    _json(evidence),
                    evidence_digest,
                    request.change_note.strip(),
                    request.actor_id,
                    request.actor_session_id,
                    request.idempotency_key,
                    request.request_digest,
                    now,
                    event_digest,
                ),
            )
            cursor.execute(
                """
                INSERT INTO backtest.strategy_version_state (
                    strategy_version_id, status, last_sequence, last_event_id,
                    projection_digest, updated_at
                ) VALUES (%s, %s, 1, %s, %s, %s)
                """,
                (
                    version_id,
                    StrategyLifecycleStatus.PUBLISHED.value,
                    event_id,
                    projection_digest,
                    now,
                ),
            )
            cursor.execute(
                """
                INSERT INTO backtest.strategy_lifecycle_outbox (
                    outbox_id, event_id, event_digest, topic, payload_json,
                    payload_digest, delivery_status, delivery_attempts, created_at
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, 'PENDING', 0, %s)
                """,
                (
                    outbox_id,
                    event_id,
                    event_digest,
                    "strategy.lifecycle.v1",
                    _json(outbox_payload),
                    outbox_payload_digest,
                    now,
                ),
            )
            cursor.execute(
                """
                INSERT INTO backtest.strategy_publish_operations (
                    publish_operation_id, draft_id, idempotency_key,
                    request_digest, expected_draft_revision,
                    strategy_version_id, published_event_id, result_digest,
                    committed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    operation_id,
                    request.draft_id,
                    request.idempotency_key,
                    request.request_digest,
                    request.expected_draft_revision,
                    version_id,
                    event_id,
                    result_digest,
                    now,
                ),
            )
            cursor.execute(
                """
                UPDATE backtest.strategy_version_drafts
                SET revision = revision + 1,
                    published_strategy_version_id = %s,
                    published_event_id = %s,
                    published_operation_id = %s,
                    published_at = %s,
                    updated_at = %s,
                    updated_by = %s
                WHERE draft_id = %s AND revision = %s
                """,
                (
                    version_id,
                    event_id,
                    operation_id,
                    now,
                    now,
                    request.actor_id,
                    request.draft_id,
                    request.expected_draft_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise StrategyCatalogConflict(
                    "DRAFT_REVISION_CONFLICT",
                    "Draft revision 在 Publish transaction 中發生衝突",
                )
            return PublishStrategyResult(
                publish_operation_id=operation_id,
                draft_id=request.draft_id,
                strategy_version_id=version_id,
                published_event_id=event_id,
                version_number=version_number,
                configuration_digest=configuration_digest,
                result_digest=result_digest,
            )

    def save_strategy_set(
        self,
        snapshot: ExactStrategySetSnapshot,
        *,
        actor_id: str,
    ) -> bool:
        if not actor_id.strip():
            raise ValueError("actor_id 不可為空")
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT strategy_set_version_id, snapshot_digest
                FROM backtest.strategy_set_versions
                WHERE strategy_set_version_id = %s
                   OR (strategy_set_id = %s AND version_number = %s)
                """,
                (
                    snapshot.strategy_set_version_id,
                    snapshot.strategy_set_id,
                    snapshot.version_number,
                ),
            )
            existing = cursor.fetchone()
            if existing is not None:
                existing_row = _row(cursor, existing)
                if (
                    str(existing_row["strategy_set_version_id"])
                    != snapshot.strategy_set_version_id
                    or str(existing_row["snapshot_digest"]) != snapshot.snapshot_digest
                ):
                    raise StrategyCatalogConflict(
                        "STRATEGY_SET_VERSION_CONFLICT",
                        "Strategy Set Version 已存在且內容不同",
                    )
                return False

            for member in snapshot.ordered_members:
                cursor.execute(
                    """
                    SELECT version.strategy_id, version.configuration_digest,
                           version.implementation_digest, template.role
                    FROM backtest.strategy_versions AS version
                    JOIN backtest.strategy_templates AS template
                      ON template.strategy_id = version.strategy_id
                    WHERE version.strategy_version_id = %s
                    """,
                    (member.strategy_version_id,),
                )
                raw = cursor.fetchone()
                if raw is None:
                    raise StrategyCatalogConflict(
                        "STRATEGY_SET_MEMBER_NOT_FOUND",
                        f"找不到 Strategy Set member：{member.strategy_version_id}",
                    )
                stored = _row(cursor, raw)
                expected = (
                    member.strategy_id,
                    member.configuration_digest,
                    member.implementation_digest,
                    member.role.value,
                )
                actual = (
                    str(stored["strategy_id"]),
                    str(stored["configuration_digest"]),
                    str(stored["implementation_digest"]),
                    str(stored["role"]),
                )
                if actual != expected:
                    raise StrategyCatalogConflict(
                        "STRATEGY_SET_MEMBER_MISMATCH",
                        f"Strategy Set member digest/role 不一致：{member.strategy_version_id}",
                    )

            cursor.execute(
                """
                INSERT INTO backtest.strategy_set_versions (
                    strategy_set_version_id, strategy_set_id, version_number,
                    display_name_zh_tw, stage, aggregation_policy,
                    minimum_trigger_count, snapshot_json, snapshot_digest,
                    created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    snapshot.strategy_set_version_id,
                    snapshot.strategy_set_id,
                    snapshot.version_number,
                    snapshot.display_name_zh_tw,
                    snapshot.stage.value,
                    snapshot.policy.value,
                    snapshot.minimum_trigger_count,
                    _json(snapshot.to_dict()),
                    snapshot.snapshot_digest,
                    actor_id.strip(),
                ),
            )
            for member in snapshot.ordered_members:
                cursor.execute(
                    """
                    INSERT INTO backtest.strategy_set_members (
                        strategy_set_version_id, strategy_version_id,
                        member_order, attribution_priority, member_role,
                        configuration_digest, implementation_digest
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        snapshot.strategy_set_version_id,
                        member.strategy_version_id,
                        member.member_order,
                        member.attribution_priority,
                        member.role.value,
                        member.configuration_digest,
                        member.implementation_digest,
                    ),
                )
            return True

    def get_strategy_set(self, strategy_set_version_id: str) -> ExactStrategySetSnapshot:
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM backtest.strategy_set_versions
                WHERE strategy_set_version_id = %s
                """,
                (strategy_set_version_id,),
            )
            raw_set = cursor.fetchone()
            if raw_set is None:
                raise StrategyCatalogConflict(
                    "STRATEGY_SET_VERSION_NOT_FOUND",
                    f"找不到 Strategy Set Version：{strategy_set_version_id}",
                )
            set_row = _row(cursor, raw_set)
            cursor.execute(
                """
                SELECT member.*, version.strategy_id
                FROM backtest.strategy_set_members AS member
                JOIN backtest.strategy_versions AS version
                  ON version.strategy_version_id = member.strategy_version_id
                WHERE member.strategy_set_version_id = %s
                ORDER BY member.member_order
                """,
                (strategy_set_version_id,),
            )
            members = tuple(
                StrategySetMemberSnapshot(
                    strategy_version_id=str(row["strategy_version_id"]),
                    strategy_id=str(row["strategy_id"]),
                    role=StrategyRole(str(row["member_role"])),
                    configuration_digest=str(row["configuration_digest"]),
                    implementation_digest=str(row["implementation_digest"]),
                    member_order=int(row["member_order"]),
                    attribution_priority=int(row["attribution_priority"]),
                )
                for row in (_row(cursor, raw) for raw in cursor.fetchall())
            )
            return ExactStrategySetSnapshot(
                strategy_set_version_id=str(set_row["strategy_set_version_id"]),
                strategy_set_id=str(set_row["strategy_set_id"]),
                version_number=int(set_row["version_number"]),
                display_name_zh_tw=str(set_row["display_name_zh_tw"]),
                stage=StrategyRole(str(set_row["stage"])),
                policy=CompositionPolicy(str(set_row["aggregation_policy"])),
                members=members,
                minimum_trigger_count=int(set_row["minimum_trigger_count"]),
            )

    @staticmethod
    def _publish_operation(cursor: Any, draft_id: str, key: str) -> dict[str, Any] | None:
        cursor.execute(
            """
            SELECT operation.*, version.version_number, version.configuration_digest
            FROM backtest.strategy_publish_operations AS operation
            JOIN backtest.strategy_versions AS version
              ON version.strategy_version_id = operation.strategy_version_id
            WHERE operation.draft_id = %s AND operation.idempotency_key = %s
            """,
            (draft_id, key),
        )
        raw = cursor.fetchone()
        return _row(cursor, raw) if raw is not None else None

    @staticmethod
    def _draft(row: Mapping[str, Any]) -> StrategyDraft:
        return StrategyDraft(
            draft_id=str(row["draft_id"]),
            strategy_id=str(row["strategy_id"]),
            revision=int(row["revision"]),
            parameters=_decode_json(row["parameters_json"]),
            parameters_digest=str(row["parameters_digest"]),
            change_note=str(row["change_note"]),
            created_by=str(row["created_by"]),
            updated_by=str(row["updated_by"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            published_strategy_version_id=(
                str(row["published_strategy_version_id"])
                if row["published_strategy_version_id"] is not None
                else None
            ),
            published_event_id=(
                str(row["published_event_id"])
                if row["published_event_id"] is not None
                else None
            ),
            published_operation_id=(
                str(row["published_operation_id"])
                if row["published_operation_id"] is not None
                else None
            ),
            published_at=row["published_at"],
        )

    def _transaction(self):
        connection = self._connection

        class _Transaction:
            def __enter__(self_nonlocal):
                self_nonlocal.cursor = connection.cursor()
                return self_nonlocal.cursor

            def __exit__(self_nonlocal, error_type, error, traceback):
                try:
                    if error_type is None:
                        connection.commit()
                    else:
                        connection.rollback()
                finally:
                    self_nonlocal.cursor.close()
                return False

        return _Transaction()
