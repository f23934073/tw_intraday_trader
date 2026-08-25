"""PostgreSQL adapter for atomic Strategy Draft and Publish transactions."""

from __future__ import annotations

import hashlib
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
from strategy_catalog.paper_activation import (
    PaperActivationCatalogSnapshot,
    PaperActivationMember,
    StrategyLifecycleProjection,
)
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

    def __init__(
        self,
        connection: Any | None = None,
        *,
        pool: Any | None = None,
        owns_pool: bool = False,
    ) -> None:
        if (connection is None) == (pool is None):
            raise ValueError("exactly one of connection or pool is required")
        self._connection = connection
        self._pool = pool
        self._owns_pool = owns_pool

    def close(self) -> None:
        if self._pool is not None:
            if self._owns_pool:
                self._pool.close()
            return
        self._connection.close()

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
        idempotency_key: str | None = None,
        operation_scope: str | None = None,
    ) -> StrategyDraft:
        if not actor_id.strip():
            raise ValueError("actor_id 不可為空")
        canonical = template.validate_parameters(parameters)
        parameters_digest = canonical_digest(canonical)
        scope = operation_scope or f"strategy-draft:create:{template.strategy_id}"
        request_digest = canonical_digest(
            {
                "contract_version": "strategy-draft-create-v1",
                "strategy_id": template.strategy_id,
                "parameters": canonical,
                "change_note": change_note.strip(),
            }
        )
        with self._transaction() as cursor:
            if idempotency_key:
                self._lock_mutation(cursor, scope, idempotency_key)
                replay = self._mutation_operation(cursor, scope, idempotency_key)
                if replay is not None:
                    self._assert_mutation_digest(replay, request_digest)
                    result = _decode_json(replay["result_json"])
                    return self._draft_from_result(result)
            self._verify_template(cursor, template)
            draft_id = str(uuid4())
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
            draft = self._draft(_row(cursor, cursor.fetchone()))
            if idempotency_key:
                result = {"draft": self._draft_result(draft)}
                self._record_mutation(
                    cursor,
                    scope=scope,
                    idempotency_key=idempotency_key,
                    request_digest=request_digest,
                    result=result,
                    actor_id=actor_id,
                    action="DRAFT_CREATED",
                    resource_type="STRATEGY_DRAFT",
                    resource_id=draft.draft_id,
                    before_digest=None,
                    after_digest=draft.parameters_digest,
                    change_note=change_note,
                )
            return draft

    def update_draft(
        self,
        draft_id: str,
        template: StrategyTemplate,
        parameters: Mapping[str, object],
        *,
        expected_revision: int,
        actor_id: str,
        change_note: str,
        idempotency_key: str,
    ) -> StrategyDraft:
        if expected_revision <= 0:
            raise ValueError("expected_revision 必須大於 0")
        if not actor_id.strip() or not idempotency_key.strip():
            raise ValueError("actor_id 與 idempotency_key 不可為空")
        canonical = template.validate_parameters(parameters)
        parameters_digest = canonical_digest(canonical)
        scope = f"strategy-draft:update:{draft_id}"
        request_digest = canonical_digest(
            {
                "contract_version": "strategy-draft-update-v1",
                "draft_id": draft_id,
                "expected_revision": expected_revision,
                "parameters": canonical,
                "change_note": change_note.strip(),
            }
        )
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT * FROM backtest.strategy_version_drafts WHERE draft_id = %s FOR UPDATE",
                (draft_id,),
            )
            raw = cursor.fetchone()
            if raw is None:
                raise StrategyCatalogConflict("DRAFT_NOT_FOUND", f"找不到 Draft：{draft_id}")
            current = self._draft(_row(cursor, raw))
            replay = self._mutation_operation(cursor, scope, idempotency_key)
            if replay is not None:
                self._assert_mutation_digest(replay, request_digest)
                result = _decode_json(replay["result_json"])
                return self._draft_from_result(result)
            if current.is_sealed:
                raise StrategyCatalogConflict("DRAFT_ALREADY_PUBLISHED", "已發布 Draft 不可修改")
            if current.revision != expected_revision:
                raise StrategyCatalogConflict(
                    "DRAFT_REVISION_CONFLICT",
                    "Draft revision 已變更",
                    details={"current_revision": current.revision},
                )
            if current.strategy_id != template.strategy_id:
                raise StrategyCatalogConflict("TEMPLATE_MISMATCH", "Draft 與 Template 不一致")
            self._verify_template(cursor, template)
            cursor.execute(
                """
                UPDATE backtest.strategy_version_drafts
                SET revision = revision + 1,
                    parameters_json = %s::jsonb,
                    parameters_digest = %s,
                    change_note = %s,
                    updated_by = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE draft_id = %s AND revision = %s
                RETURNING *
                """,
                (
                    _json(canonical),
                    parameters_digest,
                    change_note.strip(),
                    actor_id.strip(),
                    draft_id,
                    expected_revision,
                ),
            )
            updated = self._draft(_row(cursor, cursor.fetchone()))
            self._record_mutation(
                cursor,
                scope=scope,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
                result={"draft": self._draft_result(updated)},
                actor_id=actor_id,
                action="DRAFT_UPDATED",
                resource_type="STRATEGY_DRAFT",
                resource_id=draft_id,
                before_digest=current.parameters_digest,
                after_digest=updated.parameters_digest,
                change_note=change_note,
            )
            return updated

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

    def list_drafts(self, strategy_id: str | None = None) -> tuple[StrategyDraft, ...]:
        with self._transaction() as cursor:
            if strategy_id:
                cursor.execute(
                    """
                    SELECT * FROM backtest.strategy_version_drafts
                    WHERE strategy_id = %s
                    ORDER BY updated_at DESC, draft_id
                    """,
                    (strategy_id,),
                )
            else:
                cursor.execute(
                    "SELECT * FROM backtest.strategy_version_drafts ORDER BY updated_at DESC, draft_id"
                )
            return tuple(self._draft(_row(cursor, raw)) for raw in cursor.fetchall())

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
            return self._version(_row(cursor, raw))

    def list_versions(self, strategy_id: str | None = None) -> tuple[StrategyVersion, ...]:
        with self._transaction() as cursor:
            if strategy_id:
                cursor.execute(
                    """
                    SELECT * FROM backtest.strategy_versions
                    WHERE strategy_id = %s
                    ORDER BY version_number DESC
                    """,
                    (strategy_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM backtest.strategy_versions
                    ORDER BY strategy_id, version_number DESC
                    """
                )
            return tuple(self._version(_row(cursor, raw)) for raw in cursor.fetchall())

    def replay_publish(
        self,
        request: PublishStrategyRequest,
    ) -> PublishStrategyResult | None:
        """Replay a committed Publish without consulting the deployed Registry."""

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
            replay = self._publish_operation(
                cursor,
                request.draft_id,
                request.idempotency_key,
            )
            if replay is not None:
                return self._replayed_publish_result(request, replay)
            if draft["published_strategy_version_id"] is not None:
                raise StrategyCatalogConflict(
                    "DRAFT_ALREADY_PUBLISHED",
                    "Draft 已發布，其他 idempotency key 不可建立第二個 Version",
                    details={
                        "strategy_version_id": str(draft["published_strategy_version_id"]),
                        "published_event_id": str(draft["published_event_id"]),
                    },
                )
            return None

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
                return self._replayed_publish_result(request, replay)

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
        idempotency_key: str | None = None,
        change_note: str = "",
    ) -> bool:
        if not actor_id.strip():
            raise ValueError("actor_id 不可為空")
        scope = f"strategy-set:create:{snapshot.strategy_set_id}"
        request_digest = canonical_digest(
            {
                "contract_version": "strategy-set-create-v1",
                "snapshot": snapshot.to_dict(),
                "change_note": change_note.strip(),
            }
        )
        with self._transaction() as cursor:
            if idempotency_key:
                self._lock_mutation(cursor, scope, idempotency_key)
                replay = self._mutation_operation(cursor, scope, idempotency_key)
                if replay is not None:
                    self._assert_mutation_digest(replay, request_digest)
                    return False
            cursor.execute(
                """
                SELECT strategy_set_version_id
                FROM backtest.strategy_set_versions
                WHERE strategy_set_id = %s
                ORDER BY strategy_set_version_id
                FOR UPDATE
                """,
                (snapshot.strategy_set_id,),
            )
            cursor.fetchall()
            cursor.execute(
                """
                SELECT 1
                FROM backtest.strategy_set_archives
                WHERE strategy_set_id = %s
                """,
                (snapshot.strategy_set_id,),
            )
            if cursor.fetchone() is not None:
                raise StrategyCatalogConflict(
                    "STRATEGY_SET_ARCHIVED",
                    "Strategy Set 已封存，不可新增修訂",
                )
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
            if idempotency_key:
                self._record_mutation(
                    cursor,
                    scope=scope,
                    idempotency_key=idempotency_key,
                    request_digest=request_digest,
                    result={
                        "strategy_set_version_id": snapshot.strategy_set_version_id,
                        "snapshot_digest": snapshot.snapshot_digest,
                    },
                    actor_id=actor_id,
                    action=(
                        "STRATEGY_SET_CREATED"
                        if snapshot.version_number == 1
                        else "STRATEGY_SET_REVISED"
                    ),
                    resource_type="STRATEGY_SET_VERSION",
                    resource_id=snapshot.strategy_set_version_id,
                    before_digest=None,
                    after_digest=snapshot.snapshot_digest,
                    change_note=change_note,
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
            stored_snapshot = _decode_json(set_row["snapshot_json"])
            stored_digest = str(set_row["snapshot_digest"])
            if canonical_digest(stored_snapshot) != stored_digest:
                raise StrategyCatalogConflict(
                    "STRATEGY_SET_INTEGRITY_ERROR",
                    "Strategy Set snapshot_json 與 snapshot_digest 不一致",
                )
            try:
                snapshot = ExactStrategySetSnapshot(
                    strategy_set_version_id=str(set_row["strategy_set_version_id"]),
                    strategy_set_id=str(set_row["strategy_set_id"]),
                    version_number=int(set_row["version_number"]),
                    display_name_zh_tw=str(set_row["display_name_zh_tw"]),
                    stage=StrategyRole(str(set_row["stage"])),
                    policy=CompositionPolicy(str(set_row["aggregation_policy"])),
                    members=members,
                    minimum_trigger_count=int(set_row["minimum_trigger_count"]),
                )
            except (TypeError, ValueError) as error:
                raise StrategyCatalogConflict(
                    "STRATEGY_SET_INTEGRITY_ERROR",
                    "Strategy Set relational projection 無法重建",
                ) from error
            if snapshot.to_dict() != stored_snapshot or snapshot.snapshot_digest != stored_digest:
                raise StrategyCatalogConflict(
                    "STRATEGY_SET_INTEGRITY_ERROR",
                    "Strategy Set relational projection 與 immutable snapshot 不一致",
                )
            return snapshot

    def list_strategy_sets(self) -> tuple[ExactStrategySetSnapshot, ...]:
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT version.strategy_set_version_id
                FROM backtest.strategy_set_versions AS version
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM backtest.strategy_set_archives AS archive
                    WHERE archive.strategy_set_id = version.strategy_set_id
                )
                ORDER BY version.created_at DESC, version.strategy_set_version_id
                """
            )
            identifiers = tuple(str(raw[0]) for raw in cursor.fetchall())
        return tuple(self.get_strategy_set(identifier) for identifier in identifiers)

    def is_strategy_set_archived(self, strategy_set_version_id: str) -> bool:
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM backtest.strategy_set_versions AS version
                    JOIN backtest.strategy_set_archives AS archive
                      ON archive.strategy_set_id = version.strategy_set_id
                    WHERE version.strategy_set_version_id = %s
                )
                """,
                (strategy_set_version_id,),
            )
            return bool(cursor.fetchone()[0])

    def archive_strategy_set(
        self,
        strategy_set_version_id: str,
        *,
        actor_id: str,
        idempotency_key: str,
        change_note: str,
    ) -> bool:
        if not actor_id.strip() or not idempotency_key.strip() or not change_note.strip():
            raise ValueError("Strategy Set archive actor、idempotency key 與說明不可為空")
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT strategy_set_id, snapshot_digest
                FROM backtest.strategy_set_versions
                WHERE strategy_set_version_id = %s
                """,
                (strategy_set_version_id,),
            )
            raw = cursor.fetchone()
            if raw is None:
                raise StrategyCatalogConflict(
                    "STRATEGY_SET_VERSION_NOT_FOUND",
                    f"找不到 Strategy Set Version：{strategy_set_version_id}",
                )
            row = _row(cursor, raw)
            strategy_set_id = str(row["strategy_set_id"])
            before_digest = str(row["snapshot_digest"])
            cursor.execute(
                """
                SELECT strategy_set_version_id
                FROM backtest.strategy_set_versions
                WHERE strategy_set_id = %s
                ORDER BY strategy_set_version_id
                FOR UPDATE
                """,
                (strategy_set_id,),
            )
            cursor.fetchall()
            scope = f"strategy-set:archive:{strategy_set_id}"
            archive_document = {
                "contract_version": "strategy-set-archive-v1",
                "strategy_set_id": strategy_set_id,
                "source_strategy_set_version_id": strategy_set_version_id,
                "actor_id": actor_id.strip(),
                "change_note": change_note.strip(),
            }
            request_digest = canonical_digest(archive_document)
            self._lock_mutation(cursor, scope, idempotency_key)
            replay = self._mutation_operation(cursor, scope, idempotency_key)
            if replay is not None:
                self._assert_mutation_digest(replay, request_digest)
                return False
            cursor.execute(
                """
                SELECT archive_digest
                FROM backtest.strategy_set_archives
                WHERE strategy_set_id = %s
                """,
                (strategy_set_id,),
            )
            existing_archive = cursor.fetchone()
            if existing_archive is not None:
                existing_archive_digest = str(existing_archive[0])
                self._record_mutation(
                    cursor,
                    scope=scope,
                    idempotency_key=idempotency_key,
                    request_digest=request_digest,
                    result={
                        "strategy_set_id": strategy_set_id,
                        "strategy_set_version_id": strategy_set_version_id,
                        "archive_digest": existing_archive_digest,
                        "already_archived": True,
                    },
                    actor_id=actor_id,
                    action="STRATEGY_SET_ARCHIVE_REPLAYED",
                    resource_type="STRATEGY_SET",
                    resource_id=strategy_set_id,
                    before_digest=existing_archive_digest,
                    after_digest=existing_archive_digest,
                    change_note=change_note,
                )
                return False
            archive_digest = canonical_digest(archive_document)
            cursor.execute(
                """
                INSERT INTO backtest.strategy_set_archives (
                    strategy_set_id, source_strategy_set_version_id,
                    archived_by, archive_note, archive_digest
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    strategy_set_id,
                    strategy_set_version_id,
                    actor_id.strip(),
                    change_note.strip(),
                    archive_digest,
                ),
            )
            self._record_mutation(
                cursor,
                scope=scope,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
                result={
                    "strategy_set_id": strategy_set_id,
                    "strategy_set_version_id": strategy_set_version_id,
                    "archive_digest": archive_digest,
                },
                actor_id=actor_id,
                action="STRATEGY_SET_ARCHIVED",
                resource_type="STRATEGY_SET",
                resource_id=strategy_set_id,
                before_digest=before_digest,
                after_digest=archive_digest,
                change_note=change_note,
            )
            return True

    def get_paper_activation_snapshot(
        self,
        strategy_set_version_id: str,
    ) -> PaperActivationCatalogSnapshot:
        """Read and lock exact Set/Version/lifecycle evidence in one transaction."""

        expected_set = self.get_strategy_set(strategy_set_version_id)
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT version.snapshot_json, version.snapshot_digest,
                       archive.strategy_set_id AS archived_strategy_set_id
                FROM backtest.strategy_set_versions AS version
                LEFT JOIN backtest.strategy_set_archives AS archive
                  ON archive.strategy_set_id = version.strategy_set_id
                WHERE version.strategy_set_version_id = %s
                FOR SHARE OF version
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
            if set_row["archived_strategy_set_id"] is not None:
                raise StrategyCatalogConflict(
                    "STRATEGY_SET_ARCHIVED",
                    "Strategy Set 已封存，不可啟動新的 Local Paper",
                    details={"strategy_set_version_id": strategy_set_version_id},
                )
            locked_document = _decode_json(set_row["snapshot_json"])
            locked_digest = str(set_row["snapshot_digest"])
            if (
                locked_document != expected_set.to_dict()
                or locked_digest != expected_set.snapshot_digest
                or canonical_digest(locked_document) != locked_digest
            ):
                raise StrategyCatalogConflict(
                    "STRATEGY_SET_INTEGRITY_ERROR",
                    "Paper activation 的 Strategy Set snapshot 已漂移",
                )

            cursor.execute(
                """
                SELECT member.member_order, version.*, state.status,
                       state.last_sequence, state.last_event_id,
                       state.projection_digest,
                       event.event_id AS lifecycle_event_id,
                       event.sequence AS lifecycle_event_sequence,
                       event.event_type AS lifecycle_event_type,
                       event.from_status AS lifecycle_event_from_status,
                       event.to_status AS lifecycle_event_to_status,
                       event.evidence_json AS lifecycle_event_evidence_json,
                       event.evidence_digest AS lifecycle_event_evidence_digest,
                       event.reason AS lifecycle_event_reason,
                       event.actor_id AS lifecycle_event_actor_id,
                       event.actor_session_id AS lifecycle_event_actor_session_id,
                       event.idempotency_key AS lifecycle_event_idempotency_key,
                       event.request_digest AS lifecycle_event_request_digest,
                       event.expected_sequence AS lifecycle_event_expected_sequence,
                       event.occurred_at AS lifecycle_event_occurred_at,
                       event.event_digest AS lifecycle_event_digest
                FROM backtest.strategy_set_members AS member
                JOIN backtest.strategy_versions AS version
                  ON version.strategy_version_id = member.strategy_version_id
                JOIN backtest.strategy_version_state AS state
                  ON state.strategy_version_id = version.strategy_version_id
                JOIN backtest.strategy_version_events AS event
                  ON event.event_id = state.last_event_id
                WHERE member.strategy_set_version_id = %s
                ORDER BY member.member_order
                FOR SHARE OF version, state, event
                """,
                (strategy_set_version_id,),
            )
            rows = tuple(_row(cursor, raw) for raw in cursor.fetchall())
            members: list[PaperActivationMember] = []
            for row in rows:
                try:
                    lifecycle = StrategyLifecycleProjection(
                        strategy_version_id=str(row["strategy_version_id"]),
                        status=StrategyLifecycleStatus(str(row["status"])),
                        last_sequence=int(row["last_sequence"]),
                        last_event_id=str(row["last_event_id"]),
                        projection_digest=str(row["projection_digest"]),
                    )
                except (TypeError, ValueError) as error:
                    raise StrategyCatalogConflict(
                        "STRATEGY_LIFECYCLE_INTEGRITY_ERROR",
                        "Paper activation lifecycle projection 無法驗證",
                    ) from error
                lifecycle_evidence = _decode_json(
                    row["lifecycle_event_evidence_json"]
                )
                lifecycle_evidence_digest = canonical_digest(lifecycle_evidence)
                lifecycle_event_document = {
                    "event_id": str(row["lifecycle_event_id"]),
                    "strategy_version_id": lifecycle.strategy_version_id,
                    "sequence": int(row["lifecycle_event_sequence"]),
                    "event_type": str(row["lifecycle_event_type"]),
                    "from_status": (
                        str(row["lifecycle_event_from_status"])
                        if row["lifecycle_event_from_status"] is not None
                        else None
                    ),
                    "to_status": str(row["lifecycle_event_to_status"]),
                    "evidence_digest": str(row["lifecycle_event_evidence_digest"]),
                    "actor_id": str(row["lifecycle_event_actor_id"]),
                    "actor_session_id": str(
                        row["lifecycle_event_actor_session_id"]
                    ),
                    "idempotency_key": str(
                        row["lifecycle_event_idempotency_key"]
                    ),
                    "request_digest": str(row["lifecycle_event_request_digest"]),
                    "expected_sequence": int(
                        row["lifecycle_event_expected_sequence"]
                    ),
                    "occurred_at": row[
                        "lifecycle_event_occurred_at"
                    ].astimezone(timezone.utc).isoformat(),
                }
                if (
                    lifecycle.last_event_id != lifecycle_event_document["event_id"]
                    or lifecycle.last_sequence
                    != lifecycle_event_document["sequence"]
                    or lifecycle.status.value
                    != lifecycle_event_document["to_status"]
                    or lifecycle_evidence_digest
                    != str(row["lifecycle_event_evidence_digest"])
                    or canonical_digest(lifecycle_event_document)
                    != str(row["lifecycle_event_digest"])
                ):
                    raise StrategyCatalogConflict(
                        "STRATEGY_LIFECYCLE_INTEGRITY_ERROR",
                        "Paper activation lifecycle event 與 projection 不一致",
                    )
                if lifecycle.status is not StrategyLifecycleStatus.PAPER_APPROVED:
                    raise StrategyCatalogConflict(
                        "STRATEGY_VERSION_NOT_PAPER_APPROVED",
                        (
                            f"Strategy Version {lifecycle.strategy_version_id} "
                            f"目前是 {lifecycle.status.value}，不可啟動 Local Paper"
                        ),
                        details={
                            "strategy_version_id": lifecycle.strategy_version_id,
                            "status": lifecycle.status.value,
                            "last_sequence": lifecycle.last_sequence,
                            "last_event_id": lifecycle.last_event_id,
                        },
                    )
                members.append(
                    PaperActivationMember(
                        version=self._version(row),
                        lifecycle=lifecycle,
                    )
                )
            try:
                return PaperActivationCatalogSnapshot(
                    strategy_set=expected_set,
                    members=tuple(members),
                )
            except ValueError as error:
                raise StrategyCatalogConflict(
                    "PAPER_ACTIVATION_INTEGRITY_ERROR",
                    "Paper activation member projection 不完整",
                ) from error

    def record_audit_event(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor_id: str,
        operation_scope: str,
        idempotency_key: str,
        outcome: str,
        request_digest: str | None = None,
        before_digest: str | None = None,
        after_digest: str | None = None,
        change_note: str = "",
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not actor_id.strip() or not idempotency_key.strip():
            raise ValueError("audit actor_id 與 idempotency_key 不可為空")
        audit_event_id = str(uuid4())
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO backtest.strategy_audit_events (
                    audit_event_id, action, resource_type, resource_id, actor_id,
                    before_digest, after_digest, change_note, operation_scope,
                    idempotency_key, outcome, request_digest, details_json
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                )
                RETURNING *
                """,
                (
                    audit_event_id,
                    action.strip(),
                    resource_type.strip(),
                    resource_id.strip(),
                    actor_id.strip(),
                    before_digest,
                    after_digest,
                    change_note.strip(),
                    operation_scope.strip(),
                    idempotency_key.strip(),
                    outcome.strip().upper(),
                    request_digest,
                    _json(dict(details or {})),
                ),
            )
            return self._audit_event(_row(cursor, cursor.fetchone()))

    def list_audit_events(self, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        if not 1 <= limit <= 500:
            raise ValueError("audit limit 必須介於 1 與 500")
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM backtest.strategy_audit_events
                ORDER BY occurred_at DESC, audit_event_id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return tuple(self._audit_event(_row(cursor, raw)) for raw in cursor.fetchall())

    @staticmethod
    def _audit_event(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "audit_event_id": str(row["audit_event_id"]),
            "action": str(row["action"]),
            "resource_type": str(row["resource_type"]),
            "resource_id": str(row["resource_id"]),
            "actor_id": str(row["actor_id"]),
            "before_digest": str(row["before_digest"]) if row["before_digest"] is not None else None,
            "after_digest": str(row["after_digest"]) if row["after_digest"] is not None else None,
            "change_note": str(row["change_note"]),
            "operation_scope": str(row["operation_scope"]),
            "idempotency_key": str(row["idempotency_key"]),
            "outcome": str(row.get("outcome") or "SUCCESS"),
            "request_digest": str(row["request_digest"]) if row.get("request_digest") is not None else None,
            "details": _decode_json(row.get("details_json") or {}),
            "occurred_at": row["occurred_at"].isoformat(),
        }

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
    def _replayed_publish_result(
        request: PublishStrategyRequest,
        replay: Mapping[str, Any],
    ) -> PublishStrategyResult:
        if str(replay["request_digest"]) != request.request_digest:
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

    @staticmethod
    def _draft_result(draft: StrategyDraft) -> dict[str, Any]:
        return {
            "draft_id": draft.draft_id,
            "strategy_id": draft.strategy_id,
            "revision": draft.revision,
            "parameters": dict(draft.parameters),
            "parameters_digest": draft.parameters_digest,
            "change_note": draft.change_note,
            "created_by": draft.created_by,
            "updated_by": draft.updated_by,
            "created_at": draft.created_at.isoformat(),
            "updated_at": draft.updated_at.isoformat(),
            "published_strategy_version_id": draft.published_strategy_version_id,
            "published_event_id": draft.published_event_id,
            "published_operation_id": draft.published_operation_id,
            "published_at": draft.published_at.isoformat() if draft.published_at else None,
        }

    @staticmethod
    def _draft_from_result(result: Mapping[str, Any]) -> StrategyDraft:
        snapshot = result.get("draft")
        if not isinstance(snapshot, Mapping):
            raise StrategyCatalogConflict(
                "IDEMPOTENCY_RESULT_INTEGRITY_ERROR",
                "Draft mutation 缺少 immutable operation result",
            )
        return StrategyDraft(
            draft_id=str(snapshot["draft_id"]),
            strategy_id=str(snapshot["strategy_id"]),
            revision=int(snapshot["revision"]),
            parameters=dict(snapshot["parameters"]),
            parameters_digest=str(snapshot["parameters_digest"]),
            change_note=str(snapshot["change_note"]),
            created_by=str(snapshot["created_by"]),
            updated_by=str(snapshot["updated_by"]),
            created_at=datetime.fromisoformat(str(snapshot["created_at"])),
            updated_at=datetime.fromisoformat(str(snapshot["updated_at"])),
            published_strategy_version_id=(
                str(snapshot["published_strategy_version_id"])
                if snapshot.get("published_strategy_version_id") is not None
                else None
            ),
            published_event_id=(
                str(snapshot["published_event_id"])
                if snapshot.get("published_event_id") is not None
                else None
            ),
            published_operation_id=(
                str(snapshot["published_operation_id"])
                if snapshot.get("published_operation_id") is not None
                else None
            ),
            published_at=(
                datetime.fromisoformat(str(snapshot["published_at"]))
                if snapshot.get("published_at") is not None
                else None
            ),
        )

    @staticmethod
    def _version(row: Mapping[str, Any]) -> StrategyVersion:
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

    @staticmethod
    def _verify_template(cursor: Any, template: StrategyTemplate) -> None:
        cursor.execute(
            "SELECT template_digest FROM backtest.strategy_templates WHERE strategy_id = %s",
            (template.strategy_id,),
        )
        raw = cursor.fetchone()
        if raw is None:
            raise StrategyCatalogConflict(
                "STRATEGY_TEMPLATE_NOT_REGISTERED",
                f"策略 Template 尚未註冊：{template.strategy_id}",
            )
        stored = raw[0] if not isinstance(raw, Mapping) else raw["template_digest"]
        if str(stored) != template.template_digest:
            raise StrategyCatalogConflict(
                "TEMPLATE_DIGEST_MISMATCH",
                "資料庫 Template 與目前部署程式不一致",
            )

    @staticmethod
    def _draft_by_id(cursor: Any, draft_id: str) -> StrategyDraft:
        cursor.execute(
            "SELECT * FROM backtest.strategy_version_drafts WHERE draft_id = %s",
            (draft_id,),
        )
        raw = cursor.fetchone()
        if raw is None:
            raise StrategyCatalogConflict("DRAFT_NOT_FOUND", f"找不到 Draft：{draft_id}")
        return PostgresAtomicStrategyRepository._draft(_row(cursor, raw))

    @staticmethod
    def _mutation_operation(cursor: Any, scope: str, key: str) -> dict[str, Any] | None:
        cursor.execute(
            """
            SELECT * FROM backtest.strategy_mutation_operations
            WHERE operation_scope = %s AND idempotency_key = %s
            """,
            (scope, key),
        )
        raw = cursor.fetchone()
        return _row(cursor, raw) if raw is not None else None

    @staticmethod
    def _lock_mutation(cursor: Any, scope: str, key: str) -> None:
        """Serialize resource-creating retries before the durable replay lookup."""

        digest = hashlib.sha256(f"{scope}\0{key}".encode("utf-8")).digest()
        lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))

    @staticmethod
    def _assert_mutation_digest(operation: Mapping[str, Any], request_digest: str) -> None:
        if str(operation["request_digest"]) != request_digest:
            raise StrategyCatalogConflict(
                "IDEMPOTENCY_CONFLICT",
                "相同 idempotency key 的 mutation 內容不同",
            )

    @staticmethod
    def _record_mutation(
        cursor: Any,
        *,
        scope: str,
        idempotency_key: str,
        request_digest: str,
        result: Mapping[str, Any],
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        before_digest: str | None,
        after_digest: str,
        change_note: str,
    ) -> None:
        result_document = dict(result)
        result_digest = canonical_digest(result_document)
        cursor.execute(
            """
            INSERT INTO backtest.strategy_mutation_operations (
                operation_scope, idempotency_key, request_digest, result_json,
                result_digest, actor_id
            ) VALUES (%s, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                scope,
                idempotency_key,
                request_digest,
                _json(result_document),
                result_digest,
                actor_id.strip(),
            ),
        )
        cursor.execute(
            """
            INSERT INTO backtest.strategy_audit_events (
                audit_event_id, action, resource_type, resource_id, actor_id,
                before_digest, after_digest, change_note, operation_scope,
                idempotency_key, outcome, request_digest, details_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'SUCCESS', %s, '{}'::jsonb)
            """,
            (
                str(uuid4()),
                action,
                resource_type,
                resource_id,
                actor_id.strip(),
                before_digest,
                after_digest,
                change_note.strip(),
                scope,
                idempotency_key,
                request_digest,
            ),
        )

    def _transaction(self):
        if self._pool is not None:
            pool = self._pool

            class _PoolTransaction:
                def __enter__(self_nonlocal):
                    self_nonlocal.connection_context = pool.connection()
                    connection = self_nonlocal.connection_context.__enter__()
                    self_nonlocal.cursor_context = connection.cursor()
                    return self_nonlocal.cursor_context.__enter__()

                def __exit__(self_nonlocal, error_type, error, traceback):
                    cursor_suppressed = self_nonlocal.cursor_context.__exit__(
                        error_type, error, traceback
                    )
                    connection_suppressed = self_nonlocal.connection_context.__exit__(
                        error_type, error, traceback
                    )
                    return cursor_suppressed or connection_suppressed

            return _PoolTransaction()
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
