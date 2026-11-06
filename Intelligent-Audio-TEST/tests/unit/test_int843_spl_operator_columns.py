# -*- coding: utf-8 -*-
"""INT-843 专项：声压级映射（SPL）CRUD 写侧操作人 user_id。

覆盖：
- create_spl_mapping → created_by_user_id = 当前上下文 user_id
- update_spl_mapping → updated_by_user_id = 当前上下文 user_id
- create_calibration_history → created_by_user_id = 当前上下文 user_id
- delete_spl_mapping → 软删（deleted=True / deleted_at 有值），表无
  deleted_by_user_id 列，保持现状（按卡说明）
- 无上下文（AUTH_MODE=off 等价）→ 两列保持 NULL，不硬编码 0/None 充当真实用户

DB：进程级 SQLite（tests/conftest.py 注入），仅建 spl_mappings /
calibration_history 两表，用例内自行清理，对齐 test_int141 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.infrastructure.user_context import (
    set_current_user_id, get_current_user_id,
)
from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)

_TABLES = None


def _ensure_tables():
    init_db(pool_size=2)
    global _TABLES
    if _TABLES is None:
        from device_service.infrastructure.persistence.models import (
            SPLMapping, CalibrationHistory,
        )
        _TABLES = [SPLMapping.__table__, CalibrationHistory.__table__]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


def _cleanup():
    session = get_db_session()
    try:
        for table in _TABLES:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


def session_get(model, pk):
    session = get_db_session()
    try:
        return session.get(model, pk)
    finally:
        remove_db_session()


class TestSplOperatorColumns:
    def setup_method(self):
        _ensure_tables()

    def teardown_method(self):
        _cleanup()

    def _create_mapping(self, user_id):
        from device_service.infrastructure.persistence._spl_repository_impl import (
            SPLRepository,
        )
        set_current_user_id(user_id)
        try:
            repo = SPLRepository()
            entity = repo.create_spl_mapping({
                'name': 'INT843_SPL_MAP',
                'description': '操作人测试',
                'distance': 1.0,
                'target_spl': 80.0,
                'digital_gain': -20.0,
                'test_frequency': 1000,
            })
            # create 只 flush，服务层负责 commit；测试侧按生产语义落库
            repo.commit()
            return entity.id
        finally:
            set_current_user_id(None)

    def test_create_fills_created_by_user_id(self):
        from device_service.infrastructure.persistence.models import SPLMapping
        mid = self._create_mapping(7)
        po = session_get(SPLMapping, mid)
        assert po.created_by_user_id == 7
        # 读侧不受影响：实体转换正常
        from device_service.infrastructure.persistence._spl_repository_impl import (
            SPLRepository,
        )
        ent = SPLRepository().get_spl_mapping(mid)
        assert ent is not None and ent.name == 'INT843_SPL_MAP'

    def test_create_without_context_leaves_null(self):
        """AUTH_MODE=off 等价：无上下文 → NULL，不硬编码。"""
        from device_service.infrastructure.persistence.models import SPLMapping
        from device_service.infrastructure.persistence._spl_repository_impl import (
            SPLRepository,
        )
        set_current_user_id(None)
        try:
            repo = SPLRepository()
            entity = repo.create_spl_mapping({
                'name': 'INT843_OFF', 'distance': 1.0,
            })
            repo.commit()
            mid = entity.id
        finally:
            set_current_user_id(None)
        po = session_get(SPLMapping, mid)
        assert po.created_by_user_id is None
        assert get_current_user_id() is None

    def test_update_fills_updated_by_user_id(self):
        from device_service.infrastructure.persistence.models import SPLMapping
        from device_service.infrastructure.persistence._spl_repository_impl import (
            SPLRepository,
        )
        mid = self._create_mapping(7)
        # 换用户更新
        set_current_user_id(8)
        try:
            ent = SPLRepository().update_spl_mapping(mid, {'name': 'INT843_更新后'})
            assert ent.name == 'INT843_更新后'
        finally:
            set_current_user_id(None)
        po = session_get(SPLMapping, mid)
        assert po.updated_by_user_id == 8
        assert po.created_by_user_id == 7  # 创建人不变

    def test_update_without_context_keeps_null(self):
        from device_service.infrastructure.persistence.models import SPLMapping
        from device_service.infrastructure.persistence._spl_repository_impl import (
            SPLRepository,
        )
        mid = self._create_mapping(7)
        set_current_user_id(None)
        try:
            SPLRepository().update_spl_mapping(mid, {'name': 'INT843_OFF_UP'})
        finally:
            set_current_user_id(None)
        po = session_get(SPLMapping, mid)
        assert po.updated_by_user_id is None

    def test_create_calibration_history_fills_created_by(self):
        from device_service.infrastructure.persistence.models import CalibrationHistory
        from device_service.infrastructure.persistence._spl_repository_impl import (
            SPLRepository,
        )
        mid = self._create_mapping(7)
        set_current_user_id(9)
        try:
            repo = SPLRepository()
            hist = repo.create_calibration_history(
                mid, {'points': [{'freq': 1000, 'spl': 80.0}]}, 1.0, 1000,
            )
            repo.commit()
            hid = hist.id
        finally:
            set_current_user_id(None)
        po = session_get(CalibrationHistory, hid)
        assert po.created_by_user_id == 9
        assert po.mapping_id == mid

    def test_calibration_history_without_context_leaves_null(self):
        from device_service.infrastructure.persistence.models import CalibrationHistory
        from device_service.infrastructure.persistence._spl_repository_impl import (
            SPLRepository,
        )
        mid = self._create_mapping(7)
        set_current_user_id(None)
        try:
            repo = SPLRepository()
            hist = repo.create_calibration_history(mid, {'p': 1}, 1.0, 1000)
            repo.commit()
            hid = hist.id
        finally:
            set_current_user_id(None)
        po = session_get(CalibrationHistory, hid)
        assert po.created_by_user_id is None

    def test_delete_soft_and_idempotent(self):
        """软删：deleted=True / deleted_at 有值；表无 deleted_by_user_id 列按现状。"""
        from device_service.infrastructure.persistence.models import SPLMapping
        from device_service.infrastructure.persistence._spl_repository_impl import (
            SPLRepository,
        )
        mid = self._create_mapping(7)
        repo = SPLRepository()
        assert repo.delete_spl_mapping(mid) is True
        po = session_get(SPLMapping, mid)
        assert po.deleted is True
        assert po.deleted_at is not None
        # 幂等：再删返回 False
        assert repo.delete_spl_mapping(mid) is False
        # 读侧过滤语义不改（get_spl_mapping 按现状不过滤软删行，列表层过滤）：
        # 软删行实体仍可取，deleted 标志为 True
        ent = repo.get_spl_mapping(mid)
        assert ent is not None and ent.deleted is True

    def test_model_has_no_deleted_by_user_id_column(self):
        """锁定表现状：无 deleted_by_user_id 列，删除操作人不落库（按卡说明）。"""
        from device_service.infrastructure.persistence.models import SPLMapping
        assert not hasattr(SPLMapping, 'deleted_by_user_id')
