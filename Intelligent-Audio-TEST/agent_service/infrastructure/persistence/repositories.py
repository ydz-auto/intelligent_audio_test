# -*- coding: utf-8 -*-
"""SQLAlchemy 仓储实现（domain 端口的适配器）。

会话工厂注入：生产用 ``shared.models.database.create_db_session``（独立
Session，close 不影响调用链），测试注入 ``sessionmaker(bind=test_engine)``。
每个方法自开自关事务；跨线程写入靠 DB 唯一约束 + 进程内 run 级锁兜底。
"""
import logging
import threading
import uuid
import weakref
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from agent_service.domain.enums import (
    CompactionLevel, EventType, RunStatus, StepStatus, ToolCallStatus, ToolRisk,
)
from agent_service.domain.model.entities import (
    AgentArtifact, AgentContextSnapshot, AgentRun, AgentRunEvent, AgentSession,
    AgentStep, AgentToolCall,
)
from agent_service.domain.repositories import (
    ArtifactRepository, ContextSnapshotRepository, EventRepository,
    RunRepository, SessionRepository, StepRepository, ToolCallRepository,
)
from agent_service.infrastructure.persistence.models.agent_models import (
    AgentArtifact as AgentArtifactPO,
    AgentContextSnapshot as AgentContextSnapshotPO,
    AgentRun as AgentRunPO,
    AgentRunEvent as AgentRunEventPO,
    AgentSession as AgentSessionPO,
    AgentStep as AgentStepPO,
    AgentToolCall as AgentToolCallPO,
)
from shared.utils.time_utils import utcnow

logger = logging.getLogger(__name__)

# run 级事件序列化锁（进程内；跨进程由 (run_id, sequence) 唯一约束兜底）。
# 弱引用：没有线程持有某 run 的锁时自动回收，长跑服务不会按 run 数线性增长。
_run_locks: 'weakref.WeakValueDictionary[str, threading.RLock]' = (
    weakref.WeakValueDictionary())
_run_locks_guard = threading.Lock()


def _run_lock(run_id: str) -> threading.RLock:
    with _run_locks_guard:
        lock = _run_locks.get(run_id)
        if lock is None:
            lock = threading.RLock()
            _run_locks[run_id] = lock
        return lock


def _enum_value(value):
    return value.value if hasattr(value, 'value') else value


# ---------------------------------------------------------------- converters

def _to_session(row: AgentSessionPO) -> AgentSession:
    return AgentSession(
        id=row.id, owner_id=row.owner_id, tenant_id=row.tenant_id,
        title=row.title or '', active_skill=row.active_skill,
        model=row.model or '', created_at=row.created_at, updated_at=row.updated_at,
    )


def _to_run(row: AgentRunPO) -> AgentRun:
    return AgentRun(
        id=row.id, session_id=row.session_id, owner_id=row.owner_id,
        tenant_id=row.tenant_id, status=RunStatus(row.status),
        model=row.model or '', budget=row.budget or {},
        token_in=row.token_in or 0, token_out=row.token_out or 0,
        idempotency_key=row.idempotency_key,
        cancel_requested=bool(row.cancel_requested),
        error=row.error, started_at=row.started_at, finished_at=row.finished_at,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _to_event(row: AgentRunEventPO) -> AgentRunEvent:
    return AgentRunEvent(
        id=row.id, run_id=row.run_id, sequence=row.sequence,
        type=EventType(row.type), payload=row.payload or {},
        created_at=row.created_at,
    )


def _to_step(row: AgentStepPO) -> AgentStep:
    return AgentStep(
        id=row.id, run_id=row.run_id, index=row.index,
        status=StepStatus(row.status), plan_snapshot=row.plan_snapshot,
        error=row.error, created_at=row.created_at, updated_at=row.updated_at,
    )


def _to_tool_call(row: AgentToolCallPO) -> AgentToolCall:
    return AgentToolCall(
        id=row.id, run_id=row.run_id, step_id=row.step_id,
        tool_call_id=row.tool_call_id, tool=row.tool,
        arguments=row.arguments or {}, args_hash=row.args_hash,
        risk=ToolRisk(row.risk), status=ToolCallStatus(row.status),
        result=row.result, result_ref=row.result_ref,
        latency_ms=row.latency_ms, permission_decision=row.permission_decision,
        error=row.error, idempotency_key=row.idempotency_key,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _to_artifact(row: AgentArtifactPO) -> AgentArtifact:
    return AgentArtifact(
        id=row.id, run_id=row.run_id, kind=row.kind, uri=row.uri,
        size=row.size or 0, metadata=row.artifact_metadata or {},
        created_at=row.created_at,
    )


def _to_snapshot(row: AgentContextSnapshotPO) -> AgentContextSnapshot:
    return AgentContextSnapshot(
        id=row.id, run_id=row.run_id, version=row.version,
        token_count=row.token_count or 0, dropped_ids=row.dropped_ids or [],
        memo=row.memo or {}, level=CompactionLevel(row.level),
        created_at=row.created_at,
    )


class _BaseRepo:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def _session(self):
        return self._session_factory()


# ---------------------------------------------------------------- sessions

class SqlSessionRepository(_BaseRepo, SessionRepository):
    def add(self, session: AgentSession) -> AgentSession:
        db = self._session()
        try:
            row = AgentSessionPO(
                id=session.id, owner_id=session.owner_id,
                tenant_id=session.tenant_id, title=session.title or '',
                active_skill=session.active_skill, model=session.model or '',
                created_at=session.created_at or utcnow(),
                updated_at=session.updated_at or utcnow(),
            )
            db.add(row)
            db.commit()
            return _to_session(row)
        finally:
            db.close()

    def get(self, session_id: str) -> Optional[AgentSession]:
        db = self._session()
        try:
            row = db.get(AgentSessionPO, session_id)
            return _to_session(row) if row else None
        finally:
            db.close()

    def get_for_owner(self, session_id: str, owner_id: int,
                      tenant_id: str) -> Optional[AgentSession]:
        db = self._session()
        try:
            row = db.query(AgentSessionPO).filter(
                AgentSessionPO.id == session_id,
                AgentSessionPO.owner_id == owner_id,
                AgentSessionPO.tenant_id == tenant_id,
            ).one_or_none()
            return _to_session(row) if row else None
        finally:
            db.close()

    def touch(self, session_id: str) -> None:
        db = self._session()
        try:
            db.query(AgentSessionPO).filter(
                AgentSessionPO.id == session_id
            ).update({'updated_at': utcnow()}, synchronize_session=False)
            db.commit()
        finally:
            db.close()


# ---------------------------------------------------------------- runs

class SqlRunRepository(_BaseRepo, RunRepository):
    def add(self, run: AgentRun) -> AgentRun:
        db = self._session()
        try:
            row = AgentRunPO(
                id=run.id, session_id=run.session_id, owner_id=run.owner_id,
                tenant_id=run.tenant_id, status=run.status.value,
                model=run.model or '', budget=run.budget or {},
                token_in=run.token_in, token_out=run.token_out,
                idempotency_key=run.idempotency_key,
                cancel_requested=run.cancel_requested, error=run.error,
                started_at=run.started_at, finished_at=run.finished_at,
                created_at=run.created_at or utcnow(),
                updated_at=run.updated_at or utcnow(),
            )
            db.add(row)
            db.commit()
            return _to_run(row)
        finally:
            db.close()

    def add_if_absent(self, run: AgentRun) -> tuple:
        """幂等插入：同 key 已存在时返回已有 run（并发插入由唯一索引兜底）。"""
        if run.idempotency_key:
            existing = self.get_by_idempotency_key(run.idempotency_key)
            if existing is not None:
                return existing, False
        db = self._session()
        try:
            row = AgentRunPO(
                id=run.id, session_id=run.session_id, owner_id=run.owner_id,
                tenant_id=run.tenant_id, status=run.status.value,
                model=run.model or '', budget=run.budget or {},
                token_in=run.token_in, token_out=run.token_out,
                idempotency_key=run.idempotency_key,
                cancel_requested=run.cancel_requested, error=run.error,
                started_at=run.started_at, finished_at=run.finished_at,
                created_at=run.created_at or utcnow(),
                updated_at=run.updated_at or utcnow(),
            )
            db.add(row)
            db.commit()
            return _to_run(row), True
        except IntegrityError:
            db.rollback()
            existing = self.get_by_idempotency_key(run.idempotency_key)
            if existing is not None:
                return existing, False
            raise
        finally:
            db.close()

    def get(self, run_id: str) -> Optional[AgentRun]:
        db = self._session()
        try:
            row = db.get(AgentRunPO, run_id)
            return _to_run(row) if row else None
        finally:
            db.close()

    def get_for_owner(self, run_id: str, owner_id: int,
                      tenant_id: str) -> Optional[AgentRun]:
        db = self._session()
        try:
            row = db.query(AgentRunPO).filter(
                AgentRunPO.id == run_id,
                AgentRunPO.owner_id == owner_id,
                AgentRunPO.tenant_id == tenant_id,
            ).one_or_none()
            return _to_run(row) if row else None
        finally:
            db.close()

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[AgentRun]:
        db = self._session()
        try:
            row = db.query(AgentRunPO).filter(
                AgentRunPO.idempotency_key == idempotency_key
            ).one_or_none()
            return _to_run(row) if row else None
        finally:
            db.close()

    def list_session_runs(self, session_id: str, limit: int) -> List[AgentRun]:
        """返回会话**最近** ``limit`` 个 run，按时间升序（末位即 latest）。

        上下文回灌与「会话最近消息」都要的是最近对话；正序取最早 N 个会把
        最新的轮次静默丢掉。
        """
        bounded = max(1, int(limit))
        db = self._session()
        try:
            rows = db.query(AgentRunPO).filter(
                AgentRunPO.session_id == session_id
            ).order_by(
                AgentRunPO.created_at.desc(), AgentRunPO.id.desc()
            ).limit(bounded).all()
            return [_to_run(r) for r in reversed(rows)]
        finally:
            db.close()

    def list_active(self) -> List[AgentRun]:
        db = self._session()
        try:
            rows = db.query(AgentRunPO).filter(
                AgentRunPO.status.in_([s.value for s in RunStatus if s.is_active])
            ).order_by(AgentRunPO.created_at.asc()).all()
            return [_to_run(r) for r in rows]
        finally:
            db.close()

    def count_for_session(self, session_id: str) -> int:
        db = self._session()
        try:
            return db.query(func.count(AgentRunPO.id)).filter(
                AgentRunPO.session_id == session_id
            ).scalar() or 0
        finally:
            db.close()

    def transition_if(self, run_id: str, from_statuses: Iterable[RunStatus],
                      target: RunStatus, *, error: Optional[str] = None,
                      started_at: Optional[datetime] = None,
                      finished_at: Optional[datetime] = None) -> bool:
        allowed = [s.value for s in from_statuses]
        values: Dict[str, Any] = {'status': target.value, 'updated_at': utcnow()}
        if error is not None:
            values['error'] = error
        if started_at is not None:
            values['started_at'] = started_at
        if finished_at is not None:
            values['finished_at'] = finished_at
        db = self._session()
        try:
            hit = db.query(AgentRunPO).filter(
                AgentRunPO.id == run_id,
                AgentRunPO.status.in_(allowed),
            ).update(values, synchronize_session=False)
            db.commit()
            return bool(hit)
        finally:
            db.close()

    def update_tokens(self, run_id: str, token_in_delta: int,
                      token_out_delta: int) -> None:
        if not token_in_delta and not token_out_delta:
            return
        db = self._session()
        try:
            db.query(AgentRunPO).filter(AgentRunPO.id == run_id).update({
                'token_in': func.coalesce(AgentRunPO.token_in, 0) + token_in_delta,
                'token_out': func.coalesce(AgentRunPO.token_out, 0) + token_out_delta,
                'updated_at': utcnow(),
            }, synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def request_cancel(self, run_id: str) -> bool:
        db = self._session()
        try:
            hit = db.query(AgentRunPO).filter(
                AgentRunPO.id == run_id,
                AgentRunPO.status.in_([s.value for s in RunStatus if s.is_active]),
            ).update({'cancel_requested': True, 'updated_at': utcnow()},
                     synchronize_session=False)
            db.commit()
            return bool(hit)
        finally:
            db.close()


# ---------------------------------------------------------------- events

class SqlEventRepository(_BaseRepo, EventRepository):
    _MAX_RETRIES = 8

    def append(self, run_id: str, event_type,
               payload: Dict[str, Any]) -> AgentRunEvent:
        last_error = None
        with _run_lock(run_id):
            for attempt in range(self._MAX_RETRIES):
                db = self._session()
                try:
                    current = db.query(func.max(AgentRunEventPO.sequence)).filter(
                        AgentRunEventPO.run_id == run_id
                    ).scalar() or 0
                    row = AgentRunEventPO(
                        id=str(uuid.uuid4()), run_id=run_id,
                        sequence=int(current) + 1,
                        type=_enum_value(event_type),
                        payload=payload or {},
                        created_at=utcnow(),
                    )
                    db.add(row)
                    db.commit()
                    return _to_event(row)
                except IntegrityError as exc:  # 跨进程并发抢到同一 sequence
                    last_error = exc
                    db.rollback()
                    logger.debug('事件 sequence 冲突，重试 run=%s attempt=%s',
                                 run_id, attempt + 1)
                finally:
                    db.close()
        raise RuntimeError(f'分配事件 sequence 失败: {run_id}') from last_error

    def list_after(self, run_id: str, sequence_exclusive: int,
                   limit: int) -> List[AgentRunEvent]:
        db = self._session()
        try:
            rows = db.query(AgentRunEventPO).filter(
                AgentRunEventPO.run_id == run_id,
                AgentRunEventPO.sequence > sequence_exclusive,
            ).order_by(AgentRunEventPO.sequence.asc()).limit(limit).all()
            return [_to_event(r) for r in rows]
        finally:
            db.close()

    def list_by_types(self, run_id: str, event_types: Sequence,
                      limit: int) -> List[AgentRunEvent]:
        """按事件类型定向查询（tool 事件配对校验用，避免扫描整条 run）。"""
        wanted = [_enum_value(item) for item in event_types]
        if not wanted:
            return []
        db = self._session()
        try:
            rows = db.query(AgentRunEventPO).filter(
                AgentRunEventPO.run_id == run_id,
                AgentRunEventPO.type.in_(wanted),
            ).order_by(AgentRunEventPO.sequence.asc()).limit(
                max(1, int(limit))).all()
            return [_to_event(r) for r in rows]
        finally:
            db.close()

    def max_sequence(self, run_id: str) -> int:
        db = self._session()
        try:
            return int(db.query(func.max(AgentRunEventPO.sequence)).filter(
                AgentRunEventPO.run_id == run_id
            ).scalar() or 0)
        finally:
            db.close()

    def has_type(self, run_id: str, event_type) -> bool:
        db = self._session()
        try:
            return db.query(AgentRunEventPO.id).filter(
                AgentRunEventPO.run_id == run_id,
                AgentRunEventPO.type == _enum_value(event_type),
            ).first() is not None
        finally:
            db.close()


# ---------------------------------------------------------------- steps

class SqlStepRepository(_BaseRepo, StepRepository):
    def create(self, run_id: str, index: int,
               plan_snapshot: Optional[Dict[str, Any]] = None) -> AgentStep:
        db = self._session()
        try:
            row = AgentStepPO(
                id=str(uuid.uuid4()), run_id=run_id, index=index,
                plan_snapshot=plan_snapshot, status=StepStatus.RUNNING.value,
                created_at=utcnow(), updated_at=utcnow(),
            )
            db.add(row)
            db.commit()
            return _to_step(row)
        finally:
            db.close()

    def finish(self, step_id: str, status, error: Optional[str] = None) -> None:
        db = self._session()
        try:
            db.query(AgentStepPO).filter(AgentStepPO.id == step_id).update({
                'status': _enum_value(status), 'error': error,
                'updated_at': utcnow(),
            }, synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def next_index(self, run_id: str) -> int:
        db = self._session()
        try:
            current = db.query(func.max(AgentStepPO.index)).filter(
                AgentStepPO.run_id == run_id
            ).scalar()
            return 0 if current is None else int(current) + 1
        finally:
            db.close()

    def fail_running(self, run_id: str, error: str) -> int:
        db = self._session()
        try:
            hit = db.query(AgentStepPO).filter(
                AgentStepPO.run_id == run_id,
                AgentStepPO.status == StepStatus.RUNNING.value,
            ).update({'status': StepStatus.FAILED.value, 'error': error,
                      'updated_at': utcnow()}, synchronize_session=False)
            db.commit()
            return int(hit or 0)
        finally:
            db.close()


# ---------------------------------------------------------------- tool calls

_UPDATABLE_TOOL_CALL_FIELDS = frozenset({
    'status', 'step_id', 'result', 'result_ref', 'latency_ms',
    'permission_decision', 'error', 'idempotency_key',
})


class SqlToolCallRepository(_BaseRepo, ToolCallRepository):
    def find(self, run_id: str, tool_call_id: str) -> Optional[AgentToolCall]:
        db = self._session()
        try:
            row = db.query(AgentToolCallPO).filter(
                AgentToolCallPO.run_id == run_id,
                AgentToolCallPO.tool_call_id == tool_call_id,
            ).one_or_none()
            return _to_tool_call(row) if row else None
        finally:
            db.close()

    def find_by_idempotency_key(self, key: str) -> Optional[AgentToolCall]:
        db = self._session()
        try:
            row = db.query(AgentToolCallPO).filter(
                AgentToolCallPO.idempotency_key == key
            ).one_or_none()
            return _to_tool_call(row) if row else None
        finally:
            db.close()

    def create(self, tool_call: AgentToolCall) -> AgentToolCall:
        db = self._session()
        try:
            row = AgentToolCallPO(
                id=tool_call.id, run_id=tool_call.run_id,
                step_id=tool_call.step_id, tool_call_id=tool_call.tool_call_id,
                tool=tool_call.tool, arguments=tool_call.arguments or {},
                args_hash=tool_call.args_hash, risk=tool_call.risk.value,
                status=tool_call.status.value, result=tool_call.result,
                result_ref=tool_call.result_ref,
                latency_ms=tool_call.latency_ms,
                permission_decision=tool_call.permission_decision,
                error=tool_call.error,
                idempotency_key=tool_call.idempotency_key,
                created_at=tool_call.created_at or utcnow(),
                updated_at=tool_call.updated_at or utcnow(),
            )
            db.add(row)
            db.commit()
            return _to_tool_call(row)
        finally:
            db.close()

    def update(self, tool_call_id: str, run_id: str, **fields) -> None:
        unknown = set(fields) - _UPDATABLE_TOOL_CALL_FIELDS
        if unknown:
            raise ValueError(f'不允许更新的字段: {sorted(unknown)}')
        status = fields.pop('status', None)
        if status is not None:
            fields['status'] = _enum_value(status)
        db = self._session()
        try:
            fields['updated_at'] = utcnow()
            db.query(AgentToolCallPO).filter(
                AgentToolCallPO.run_id == run_id,
                AgentToolCallPO.tool_call_id == tool_call_id,
            ).update(fields, synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def count_for_run(self, run_id: str) -> int:
        db = self._session()
        try:
            return int(db.query(func.count(AgentToolCallPO.id)).filter(
                AgentToolCallPO.run_id == run_id
            ).scalar() or 0)
        finally:
            db.close()

    def recent(self, run_id: str, limit: int) -> List[AgentToolCall]:
        db = self._session()
        try:
            rows = db.query(AgentToolCallPO).filter(
                AgentToolCallPO.run_id == run_id
            ).order_by(AgentToolCallPO.created_at.desc()).limit(limit).all()
            return [_to_tool_call(r) for r in rows]
        finally:
            db.close()

    def list_running(self, run_id: str) -> List[AgentToolCall]:
        db = self._session()
        try:
            rows = db.query(AgentToolCallPO).filter(
                AgentToolCallPO.run_id == run_id,
                AgentToolCallPO.status == ToolCallStatus.RUNNING.value,
            ).order_by(AgentToolCallPO.created_at.asc()).all()
            return [_to_tool_call(r) for r in rows]
        finally:
            db.close()


# ---------------------------------------------------------------- artifacts

class SqlArtifactRepository(_BaseRepo, ArtifactRepository):
    def add(self, artifact: AgentArtifact) -> AgentArtifact:
        db = self._session()
        try:
            row = AgentArtifactPO(
                id=artifact.id, run_id=artifact.run_id, kind=artifact.kind,
                uri=artifact.uri, size=artifact.size or 0,
                artifact_metadata=artifact.metadata or {},
                created_at=artifact.created_at or utcnow(),
            )
            db.add(row)
            db.commit()
            return _to_artifact(row)
        finally:
            db.close()

    def list_by_run(self, run_id: str) -> List[AgentArtifact]:
        db = self._session()
        try:
            rows = db.query(AgentArtifactPO).filter(
                AgentArtifactPO.run_id == run_id
            ).order_by(AgentArtifactPO.created_at.asc()).all()
            return [_to_artifact(r) for r in rows]
        finally:
            db.close()


# ---------------------------------------------------------------- snapshots

class SqlContextSnapshotRepository(_BaseRepo, ContextSnapshotRepository):
    def add(self, snapshot: AgentContextSnapshot) -> AgentContextSnapshot:
        db = self._session()
        try:
            row = AgentContextSnapshotPO(
                id=snapshot.id, run_id=snapshot.run_id,
                version=snapshot.version, token_count=snapshot.token_count,
                dropped_ids=snapshot.dropped_ids or [],
                memo=snapshot.memo or {}, level=snapshot.level.value,
                created_at=snapshot.created_at or utcnow(),
            )
            db.add(row)
            db.commit()
            return _to_snapshot(row)
        finally:
            db.close()

    def list_by_run(self, run_id: str) -> List[AgentContextSnapshot]:
        db = self._session()
        try:
            rows = db.query(AgentContextSnapshotPO).filter(
                AgentContextSnapshotPO.run_id == run_id
            ).order_by(AgentContextSnapshotPO.version.asc()).all()
            return [_to_snapshot(r) for r in rows]
        finally:
            db.close()
