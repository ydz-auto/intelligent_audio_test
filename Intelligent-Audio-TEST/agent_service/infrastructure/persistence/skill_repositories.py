# -*- coding: utf-8 -*-
"""自定义 Skill 的 SQLAlchemy 仓储（INT-2549 §4.4 / §10）。

与 ``repositories.py`` 同一口径：每个方法自开自关事务、返回领域实体。
唯一性由数据库局部唯一索引兜底（``(scope=USER, owner_id, name)`` /
``(scope=TENANT, tenant_id, name)``）；冲突转 ``SkillNameConflict``，
不静默覆盖。

INT-2551 追加 ``SqlSkillReviewRepository``（``agent_skill_review`` 审核链，
只追加不更新 / 删除）与 ``transition_if`` 条件状态迁移（并发审批互斥）。
"""
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from agent_service.domain.enums import (
    SkillReviewAction, SkillScope, SkillStatus,
)
from agent_service.domain.exceptions import SkillNameConflict
from agent_service.domain.model.agent_skill import (
    AgentRunSkill, AgentSkill, AgentSkillReview, AgentSkillVersion,
)
from agent_service.domain.repositories import (
    AgentRunSkillRepository, AgentSkillRepository, SkillReviewRepository,
)
from agent_service.infrastructure.persistence.models.agent_models import (
    AgentRunSkill as AgentRunSkillPO,
    AgentSkill as AgentSkillPO,
    AgentSkillReview as AgentSkillReviewPO,
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


def _to_skill_review(row: AgentSkillReviewPO) -> AgentSkillReview:
    return AgentSkillReview(
        id=row.id, skill_id=row.skill_id, version=row.version or '0',
        action=SkillReviewAction(row.action),
        status_from=SkillStatus(row.status_from),
        status_to=SkillStatus(row.status_to),
        reviewer_id=row.reviewer_id, reason=row.reason or '',
        tenant_id=row.tenant_id, created_at=row.created_at,
    )


def _version_po(version: AgentSkillVersion) -> AgentSkillVersionPO:
    """领域版本实体 → ORM 行（``add_version`` / ``apply_edit`` 共用）。"""
    return AgentSkillVersionPO(
        id=str(uuid.uuid4()), skill_id=version.skill_id,
        version=version.version,
        content_hash=version.content_hash or '',
        frontmatter_json=dict(version.frontmatter or {}),
        body=version.body or '',
        resources=dict(version.resources or {}),
        created_by=version.created_by,
        created_at=version.created_at or utcnow(),
    )


def _review_po(review: AgentSkillReview) -> AgentSkillReviewPO:
    """领域审计实体 → ORM 行（审核仓储 / ``apply_edit`` 共用）。"""
    return AgentSkillReviewPO(
        id=review.id or str(uuid.uuid4()),
        skill_id=review.skill_id, version=review.version or '0',
        action=review.action.value,
        status_from=review.status_from.value,
        status_to=review.status_to.value,
        reviewer_id=review.reviewer_id,
        reason=review.reason or '',
        tenant_id=review.tenant_id,
        created_at=review.created_at or utcnow(),
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
            ).order_by(
                # 同名跨 owner / 跨租户是不同 Skill；排序加上归属与作用域，
                # 保证装载顺序确定（合并才是查看者相关的那一步）。
                AgentSkillPO.name.asc(),
                AgentSkillPO.scope.asc(),
                AgentSkillPO.owner_id.asc(),
                AgentSkillPO.tenant_id.asc(),
            ).all()
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

    def transition_if(self, skill_id: str,
                      from_statuses: Iterable[SkillStatus],
                      target: SkillStatus) -> bool:
        """条件状态迁移：``UPDATE ... WHERE id=? AND status IN (...)`。

        并发审核的唯一性交给数据库：两个管理员同时批准同一版本时只有一条
        ``UPDATE`` 命中，另一次返回 ``False``（应用层按状态冲突处理）。
        """
        from_values = [status.value for status in from_statuses]
        if not from_values:
            return False
        db = self._session()
        try:
            hit = db.query(AgentSkillPO).filter(
                AgentSkillPO.id == skill_id,
                AgentSkillPO.status.in_(from_values),
            ).update(
                {'status': target.value, 'updated_at': utcnow()},
                synchronize_session=False)
            db.commit()
            return bool(hit)
        finally:
            db.close()

    def apply_edit(self, skill_id: str, *, from_status: SkillStatus,
                   row_fields: Dict[str, Any],
                   version: AgentSkillVersion,
                   review: AgentSkillReview) -> bool:
        """编辑提交的原子写：条件迁移 + 版本行 + 当前行 + EDIT 审计（INT-2594）。

        条件更新未命中（状态已被并发请求改走）直接回滚返回 ``False``；
        命中后三步一起提交，任一步失败整体回滚 —— 不存在「状态已回 DRAFT
        但版本 / 审计没落库」的中间态，也不会留下孤儿版本号挡住后续保存。
        """
        payload = {key: value for key, value in row_fields.items()
                   if key in self._UPDATABLE}
        if hasattr(payload.get('status'), 'value'):
            payload['status'] = payload['status'].value
        payload.setdefault('updated_at', utcnow())
        db = self._session()
        try:
            try:
                hit = db.query(AgentSkillPO).filter(
                    AgentSkillPO.id == skill_id,
                    AgentSkillPO.status == from_status.value,
                ).update(payload, synchronize_session=False)
            except IntegrityError as exc:
                # 同名唯一索引冲突（与 ``update`` 同一口径）；版本 / 审计
                # 插入的完整性错误走下面的裸异常，不冒充「同名」
                raise SkillNameConflict(
                    '同名 Skill 已存在：{0}'.format(
                        payload.get('name'))) from exc
            if not hit:
                db.rollback()
                return False
            db.add(_version_po(version))
            db.add(_review_po(review))
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def add_version(self, version: AgentSkillVersion) -> AgentSkillVersion:
        db = self._session()
        try:
            row = _version_po(version)
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


class SqlSkillReviewRepository(_BaseRepo, SkillReviewRepository):
    """``agent_skill_review`` 仓储：只追加，不更新、不删除（审计事实）。"""

    def add(self, review: AgentSkillReview) -> AgentSkillReview:
        db = self._session()
        try:
            row = _review_po(review)
            db.add(row)
            db.commit()
            return _to_skill_review(row)
        finally:
            db.close()

    def list_for_skill(self, skill_id: str) -> List[AgentSkillReview]:
        db = self._session()
        try:
            rows = db.query(AgentSkillReviewPO).filter(
                AgentSkillReviewPO.skill_id == skill_id,
            ).order_by(AgentSkillReviewPO.created_at.asc()).all()
            return [_to_skill_review(row) for row in rows]
        finally:
            db.close()

    def list_current(self, status: SkillStatus, *, tenant_id: str,
                     limit: int = 100) -> List[AgentSkillReview]:
        """本租户「当前状态 = ``status``」的 Skill 最近迁移记录（降序）。"""
        db = self._session()
        try:
            rows = db.query(AgentSkillReviewPO).join(
                AgentSkillPO, AgentSkillPO.id == AgentSkillReviewPO.skill_id,
            ).filter(
                AgentSkillPO.scope == SkillScope.TENANT.value,
                AgentSkillPO.tenant_id == tenant_id,
                AgentSkillPO.status == status.value,
                AgentSkillReviewPO.status_to == status.value,
                AgentSkillReviewPO.tenant_id == tenant_id,
            ).order_by(
                AgentSkillReviewPO.created_at.desc(),
            ).limit(limit).all()
            return [_to_skill_review(row) for row in rows]
        finally:
            db.close()


__all__ = [
    'SqlAgentRunSkillRepository', 'SqlAgentSkillRepository',
    'SqlSkillReviewRepository',
]
