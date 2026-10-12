# -*- coding: utf-8 -*-
"""收藏仓储（INT-141，task_service 分治域：task|testcase）

per-user 语义：user_id 来自 JWT（x-user-id metadata）；
(entity_id, entity_type, user_id) 唯一约束幂等。
"""
from sqlalchemy.exc import IntegrityError

from shared.models.common_enums import EntityType
from shared.models.database import get_db_session
from shared.utils.db_session import with_session
from task_service.infrastructure.persistence.models import Favorite, Task, TestCase

# 本服务分治域内允许的实体类型（report 归 report_service）
_ALLOWED_ENTITY_TYPES = frozenset({EntityType.TASK.value, EntityType.TESTCASE.value})


class FavoriteRepository:
    """favorites 表读写（本服务管辖 task|testcase 两类实体）"""

    @staticmethod
    def _validate_type(entity_type: str):
        if entity_type not in _ALLOWED_ENTITY_TYPES:
            raise ValueError(
                f"非法实体类型: {entity_type}，task_service 仅支持 {_ALLOWED_ENTITY_TYPES}")

    def _validate(self, entity_type: str, entity_id: str):
        self._validate_type(entity_type)
        if not entity_id:
            raise ValueError("entity_id 不能为空")

    def _entity_exists(self, session, entity_type: str, entity_id: str) -> bool:
        if entity_type == EntityType.TASK.value:
            try:
                tid = int(entity_id)
            except (TypeError, ValueError):
                return False
            return session.query(Task.id).filter(
                Task.id == tid, Task.deleted == False).first() is not None  # noqa: E712
        return session.query(TestCase.id).filter(
            TestCase.id == entity_id, TestCase.deleted == False).first() is not None  # noqa: E712

    @with_session(auto_commit=True)
    def add(self, user_id, entity_type: str, entity_id: str) -> dict:
        """收藏（幂等：已收藏返回 already=True；实体不存在返回 exists=False）"""
        self._validate(entity_type, entity_id)
        if not user_id:
            raise ValueError("未认证用户禁止收藏（user_id 缺失）")
        session = get_db_session()
        if not self._entity_exists(session, entity_type, entity_id):
            return {'success': False, 'message': '实体不存在或已删除', 'code': 404}
        existing = session.query(Favorite.id).filter(
            Favorite.user_id == user_id,
            Favorite.entity_type == entity_type,
            Favorite.entity_id == entity_id,
        ).first()
        if existing:
            return {'success': True, 'already_favorited': True, 'message': '已收藏'}
        try:
            session.add(Favorite(
                user_id=user_id, entity_type=entity_type, entity_id=entity_id))
            session.flush()
        except IntegrityError:
            session.rollback()
            return {'success': True, 'already_favorited': True, 'message': '已收藏'}
        return {'success': True, 'already_favorited': False, 'message': '收藏成功'}

    @with_session(auto_commit=True)
    def remove(self, user_id, entity_type: str, entity_id: str) -> dict:
        """取消收藏（幂等：未收藏同样返回成功）"""
        self._validate(entity_type, entity_id)
        session = get_db_session()
        deleted = session.query(Favorite).filter(
            Favorite.user_id == user_id,
            Favorite.entity_type == entity_type,
            Favorite.entity_id == entity_id,
        ).delete(synchronize_session=False)
        return {'success': True, 'removed': int(deleted or 0), 'message': '取消收藏成功'}

    @with_session(auto_commit=False)
    def list_ids(self, user_id, entity_type: str | None = None) -> list:
        """当前用户收藏的实体 ID 列表（字符串化原样返回）"""
        session = get_db_session()
        q = session.query(Favorite.entity_id).filter(Favorite.user_id == user_id)
        if entity_type:
            self._validate_type(entity_type)
            q = q.filter(Favorite.entity_type == entity_type)
        return [r[0] for r in q.all()]

    @with_session(auto_commit=False)
    def filter_existing_entity_ids(self, entity_type: str, entity_ids) -> list:
        """过滤出仍活跃存在的实体 ID（收藏列表联查实体时避免悬挂项）"""
        session = get_db_session()
        if entity_type == EntityType.TASK.value:
            ids = []
            for eid in entity_ids:
                try:
                    ids.append(int(eid))
                except (TypeError, ValueError):
                    continue
            rows = session.query(Task.id).filter(
                Task.id.in_(ids), Task.deleted == False).all() if ids else []  # noqa: E712
            return [r[0] for r in rows]
        rows = session.query(TestCase.id).filter(
            TestCase.id.in_(list(entity_ids)), TestCase.deleted == False
        ).all() if entity_ids else []  # noqa: E712
        return [r[0] for r in rows]


# 单例
favorite_repository = FavoriteRepository()
