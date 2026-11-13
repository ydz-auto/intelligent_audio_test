# -*- coding: utf-8 -*-
"""自定义 Skill 的 SQLAlchemy 仓储（INT-2549 §4.4 / §10）。

与 ``repositories.py`` 同一口径：每个方法自开自关事务、返回领域实体。
唯一性由数据库局部唯一索引兜底（``(scope=USER, owner_id, name)`` /
``(scope=TENANT, tenant_id, name)``）；冲突转 ``SkillNameConflict``，
不静默覆盖。
"""
import uuid
from typing import List, Optional, Sequence

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from agent_service.domain.enums import SkillScope, SkillStatus
from agent_service.domain.exceptions import SkillNameConflict
from agent_service.domain.model.agent_skill import (
    AgentRunSkill, AgentSkill, AgentSkillVersion,
)
from agent_service.domain.repositories import (
    AgentRunSkillRepository, AgentSkillRepository,
)
from agent_service.infrastructure.persistence.models.agent_models import (
    AgentRunSkill as AgentRunSkillPO,
    AgentSkill as AgentSkillPO,
    AgentSkillVersion as AgentSkillVersionPO,
)
from shared.utils.time_utils import utcnow


class _BaseRepo:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def _session(self):
        return self._session_factory()


def _to_agent_skill(row: AgentSkillPO) -> AgentSkill:
    return AgentSkill(
        id=row.id, scope=SkillScope(row.scope),
        tenant_id=row.tenant_id, owner_id=row.owner_id,
        name=row.name or '', description=row.description or '',
        version=row.version or '0', status=SkillStatus(row.status),
        content_hash=row.content_hash or '',
        frontmatter=dict(row.frontmatter_json or {}),
        resources=dict(row.resources or {}),
        created_by=row.created_by,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _to_skill_version(row: AgentSkillVersionPO) -> AgentSkillVersion:
    return AgentSkillVersion(
        skill_id=row.skill_id, version=row.version or '0',
        content_hash=row.content_hash or '', body=row.body or '',
        frontmatter=dict(row.frontmatter_json or {}),
        resources=dict(row.resources or {}),
        created_by=row.created_by, created_at=row.created_at,
    )


def _to_run_skill(row: AgentRunSkillPO) -> AgentRunSkill:
    return AgentRunSkill(
        run_id=row.run_id, skill_id=row.skill_id,
        version=row.version or '0', content_hash=row.content_hash or '',
        activated_at=row.activated_at,
    )


class SqlAgentSkillRepository(_BaseRepo, AgentSkillRepository):
    """自定义 Skill 仓储：当前行 + 版本快照（正文只在版本表）。"""

    _UPDATABLE = frozenset({
        'name', 'description', 'version', 'status', 'content_hash',
        'frontmatter_json', 'resources', 'updated_at',
    })

    def add(self, skill: AgentSkill) -> AgentSkill:
        db = self._session()
        try:
            row = AgentSkillPO(
                id=skill.id, scope=skill.scope.value,
                tenant_id=skill.tenant_id, owner_id=skill.owner_id,
                name=skill.name, description=skill.description or '',
                version=skill.version or '0', status=skill.status.value,
                content_hash=skill.content_hash or '',
                frontmatter_json=dict(skill.frontmatter or {}),
                resources=dict(skill.resources or {}),
                created_by=skill.created_by,
                created_at=skill.created_at or utcnow(),
                updated_at=skill.updated_at or utcnow(),
            )
            db.add(row)
            db.commit()
            return _to_agent_skill(row)
        except IntegrityError as exc:
            db.rollback()
            raise SkillNameConflict(
                '同名 Skill 已存在：{0}'.format(skill.name)) from exc
        finally:
            db.close()

    def get(self, skill_id: str) -> Optional[AgentSkill]:
        db = self._session()
        try:
            row = db.get(AgentSkillPO, skill_id)
            return _to_agent_skill(row) if row else None
        finally:
            db.close()

    def find_by_name(self, scope: SkillScope, name: str, *,
                     owner_id: Optional[int] = None,
                     tenant_id: Optional[str] = None
                     ) -> Optional[AgentSkill]:
        db = self._session()
        try:
            query = db.query(AgentSkillPO).filter(
                AgentSkillPO.scope == scope.value,
                AgentSkillPO.name == name)
            if scope is SkillScope.USER:
                query = query.filter(AgentSkillPO.owner_id == owner_id)
            elif scope is SkillScope.TENANT:
                query = query.filter(AgentSkillPO.tenant_id == tenant_id)
            row = query.first()
            return _to_agent_skill(row) if row else None
        finally:
            db.close()

    def list_visible(self, *, tenant_id: str, owner_id: int,
                     scopes: Optional[Sequence[SkillScope]] = None,
                     statuses: Optional[Sequence[SkillStatus]] = None
                     ) -> List[AgentSkill]:
        db = self._session()
        try:
            query = db.query(AgentSkillPO).filter(
                or_(
                    and_(AgentSkillPO.scope == SkillScope.USER.value,
                         AgentSkillPO.owner_id == owner_id),
                    and_(AgentSkillPO.scope == SkillScope.TENANT.value,
                         AgentSkillPO.tenant_id == tenant_id),
                ))
            if scopes:
                query = query.filter(
                    AgentSkillPO.scope.in_([s.value for s in scopes]))
            if statuses:
                query = query.filter(
                    AgentSkillPO.status.in_([s.value for s in statuses]))
            rows = query.order_by(AgentSkillPO.name.asc()).all()
            return [_to_agent_skill(row) for row in rows]
        finally:
            db.close()

    def list_active(self) -> List[AgentSkill]:
        db = self._session()
        try:
            rows = db.query(AgentSkillPO).filter(
                AgentSkillPO.status == SkillStatus.ACTIVE.value,
                AgentSkillPO.scope.in_(
                    [SkillScope.USER.value, SkillScope.TENANT.value]),
            ).order_by(AgentSkillPO.name.asc()).all()
            return [_to_agent_skill(row) for row in rows]
        finally:
            db.close()

    def update(self, skill_id: str, **fields) -> bool:
        payload = {key: value for key, value in fields.items()
                   if key in self._UPDATABLE}
        if not payload:
            return False
        if hasattr(payload.get('status'), 'value'):
            payload['status'] = payload['status'].value
        payload.setdefault('updated_at', utcnow())
        db = self._session()
        try:
            hit = db.query(AgentSkillPO).filter(
                AgentSkillPO.id == skill_id,
            ).update(payload, synchronize_session=False)
            db.commit()
            return bool(hit)
        except IntegrityError as exc:
            db.rollback()
            raise SkillNameConflict(
                '同名 Skill 已存在：{0}'.format(payload.get('name'))) from exc
        finally:
            db.close()

    def delete(self, skill_id: str) -> bool:
        """删除当前行；版本行保留（历史 run 回放仍可读到旧内容）。"""
        db = self._session()
        try:
            hit = db.query(AgentSkillPO).filter(
                AgentSkillPO.id == skill_id,
            ).delete(synchronize_session=False)
            db.commit()
            return bool(hit)
        finally:
            db.close()

    def add_version(self, version: AgentSkillVersion) -> AgentSkillVersion:
        db = self._session()
        try:
            row = AgentSkillVersionPO(
                id=str(uuid.uuid4()), skill_id=version.skill_id,
                version=version.version,
                content_hash=version.content_hash or '',
                frontmatter_json=dict(version.frontmatter or {}),
                body=version.body or '',
                resources=dict(version.resources or {}),
                created_by=version.created_by,
                created_at=version.created_at or utcnow(),
            )
            db.add(row)
            db.commit()
            return _to_skill_version(row)
        finally:
            db.close()

    def list_versions(self, skill_id: str) -> List[AgentSkillVersion]:
        db = self._session()
        try:
            rows = db.query(AgentSkillVersionPO).filter(
                AgentSkillVersionPO.skill_id == skill_id,
            ).order_by(AgentSkillVersionPO.created_at.asc()).all()
            return [_to_skill_version(row) for row in rows]
        finally:
            db.close()

    def get_version(self, skill_id: str,
                    version: str) -> Optional[AgentSkillVersion]:
        db = self._session()
        try:
            row = db.query(AgentSkillVersionPO).filter(
                AgentSkillVersionPO.skill_id == skill_id,
                AgentSkillVersionPO.version == str(version),
            ).one_or_none()
            return _to_skill_version(row) if row else None
        finally:
            db.close()


class SqlAgentRunSkillRepository(_BaseRepo, AgentRunSkillRepository):
    """run 激活快照仓储：只追加，不覆盖（回放以历史快照为准）。"""

    def add(self, snapshot: AgentRunSkill) -> AgentRunSkill:
        db = self._session()
        try:
            row = AgentRunSkillPO(
                id=str(uuid.uuid4()), run_id=snapshot.run_id,
                skill_id=snapshot.skill_id, version=snapshot.version or '0',
                content_hash=snapshot.content_hash or '',
                activated_at=snapshot.activated_at or utcnow(),
            )
            db.add(row)
            db.commit()
            return _to_run_skill(row)
        finally:
            db.close()

    def list_by_run(self, run_id: str) -> List[AgentRunSkill]:
        db = self._session()
        try:
            rows = db.query(AgentRunSkillPO).filter(
                AgentRunSkillPO.run_id == run_id,
            ).order_by(AgentRunSkillPO.activated_at.asc()).all()
            return [_to_run_skill(row) for row in rows]
        finally:
            db.close()


__all__ = ['SqlAgentRunSkillRepository', 'SqlAgentSkillRepository']
