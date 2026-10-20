# -*- coding: utf-8 -*-
"""INT-840 专项：标签/标签分类/用例分组 CUD 操作人列补齐。

背景（INT-840 审计）：tags / tag_categories / test_case_groups 三表已有
created_by_user_id / updated_by_user_id 列，但写路径从不赋值；本卡把
task_service 域标签/分组 CRUD 写侧操作人补齐：
- 创建：create_tag_category / create_tag / get_or_create_tag(新建) /
        create_group / create_group_and_commit → created_by_user_id
- 更新：update_tag_name(重命名) / batch_update_tag_category /
        update_category / update_tag / update_group_and_commit → updated_by_user_id
- 软删：soft_delete_tag_category / soft_delete_tag / delete_group_and_commit
        → deleted_by_user_id（INT-840 补列，三表新增 deleted_by_user_id）
- 无上下文（AUTH_MODE=off 等价）：操作人列保持 NULL，不硬编码 0 充当真实用户

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内自行清理，对齐 test_int299 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.infrastructure.user_context import set_current_user_id, get_current_user_id
from shared.models.database import (
    Base, init_db, get_engine, get_db_session,
)


# ---------------- 工具 ----------------

_TABLES = None


def _ensure_tables():
    init_db(pool_size=2)
    global _TABLES
    if _TABLES is None:
        from task_service.infrastructure.persistence.models import (
            Tag, TagCategory, TestCaseGroup, TestCase,
        )
        _TABLES = [t.__table__ for t in (
            TagCategory, Tag, TestCaseGroup, TestCase,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


def _cleanup_tables():
    """清空涉及表（sqlite 无 TRUNCATE，逐表 delete）。"""
    _ensure_tables()
    from task_service.infrastructure.persistence.models import (
        Tag, TagCategory, TestCaseGroup, TestCase,
    )
    session = get_db_session()
    try:
        for model in (TestCase, Tag, TagCategory, TestCaseGroup):
            session.query(model).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _operator_db():
    _ensure_tables()
    _cleanup_tables()
    yield
    # 上下文必清理，防止泄漏到后续用例
    set_current_user_id(None)
    _cleanup_tables()


def _tag_repo():
    """延迟导入 testcase_repository（聚合所有 mixin）。"""
    from task_service.infrastructure.persistence.testcase_repository import testcase_repository
    return testcase_repository


def _tag_service():
    from task_service.application.testcase.tag_crud_service import tag_crud_service
    return tag_crud_service


# ---------------- TagCategory 域 ----------------

class TestTagCategoryOperatorColumns:
    """标签分类 CUD 操作人（INT-840）。"""

    def test_create_category_sets_created_by(self):
        from task_service.infrastructure.persistence.models import TagCategory
        repo = _tag_repo()
        set_current_user_id(101)
        cat = repo.create_tag_category({'name': 'int840-cat', 'description': 'd'})
        session = get_db_session()
        try:
            po = session.get(TagCategory, cat.id)
            assert po.created_by_user_id == 101
            assert po.updated_by_user_id is None  # create 不写 updated_by
            assert po.deleted_by_user_id is None
        finally:
            session.close()

    def test_update_category_sets_updated_by(self):
        from task_service.infrastructure.persistence.models import TagCategory
        svc = _tag_service()
        repo = _tag_repo()
        set_current_user_id(102)
        cat = repo.create_tag_category({'name': 'int840-cat-upd'})
        repo.commit()
        set_current_user_id(103)
        result = svc.update_category(cat.id, {'description': 'updated'})
        assert result['success'] is True
        session = get_db_session()
        try:
            po = session.get(TagCategory, cat.id)
            assert po.updated_by_user_id == 103
            assert po.created_by_user_id == 102  # 同上下文创建
        finally:
            session.close()

    def test_soft_delete_category_sets_deleted_by(self):
        from task_service.infrastructure.persistence.models import TagCategory
        repo = _tag_repo()
        set_current_user_id(104)
        cat = repo.create_tag_category({'name': 'int840-cat-del'})
        repo.commit()
        set_current_user_id(105)
        repo.soft_delete_tag_category(cat)
        repo.commit()
        session = get_db_session()
        try:
            po = session.get(TagCategory, cat.id)
            assert po.deleted is True
            assert po.deleted_by_user_id == 105
            assert po.deleted_at is not None
        finally:
            session.close()

    def test_delete_category_via_service_sets_deleted_by(self):
        from task_service.infrastructure.persistence.models import TagCategory
        svc = _tag_service()
        repo = _tag_repo()
        set_current_user_id(106)
        cat = repo.create_tag_category({'name': 'int840-cat-svcdel'})
        repo.commit()
        set_current_user_id(107)
        result = svc.delete_category(cat.id)
        assert result['success'] is True
        session = get_db_session()
        try:
            po = session.get(TagCategory, cat.id)
            assert po.deleted is True
            assert po.deleted_by_user_id == 107
        finally:
            session.close()


# ---------------- Tag 域 ----------------

class TestTagOperatorColumns:
    """标签 CUD 操作人（INT-840）。"""

    def test_create_tag_sets_created_by(self):
        from task_service.infrastructure.persistence.models import Tag
        repo = _tag_repo()
        set_current_user_id(201)
        tag = repo.create_tag({'name': 'int840-tag'})
        session = get_db_session()
        try:
            po = session.get(Tag, tag.id)
            assert po.created_by_user_id == 201
            assert po.updated_by_user_id is None
            assert po.deleted_by_user_id is None
        finally:
            session.close()

    def test_get_or_create_new_sets_created_by(self):
        from task_service.infrastructure.persistence.models import Tag
        repo = _tag_repo()
        set_current_user_id(202)
        tag = repo.get_or_create_tag('int840-auto')
        session = get_db_session()
        try:
            po = session.get(Tag, tag.id)
            assert po.created_by_user_id == 202
        finally:
            session.close()

    def test_get_or_create_existing_keeps_created_by(self):
        from task_service.infrastructure.persistence.models import Tag
        repo = _tag_repo()
        set_current_user_id(203)
        tag = repo.get_or_create_tag('int840-exists')
        repo.commit()
        set_current_user_id(204)
        same = repo.get_or_create_tag('int840-exists')
        assert same.id == tag.id
        session = get_db_session()
        try:
            po = session.get(Tag, tag.id)
            assert po.created_by_user_id == 203  # 已存在不覆盖
        finally:
            session.close()

    def test_update_tag_name_sets_updated_by(self):
        from task_service.infrastructure.persistence.models import Tag
        repo = _tag_repo()
        set_current_user_id(205)
        tag = repo.create_tag({'name': 'int840-rename'})
        repo.commit()
        set_current_user_id(206)
        repo.update_tag_name(tag, 'int840-renamed')
        repo.commit()
        session = get_db_session()
        try:
            po = session.get(Tag, tag.id)
            assert po.name == 'int840-renamed'
            assert po.updated_by_user_id == 206
        finally:
            session.close()

    def test_update_tag_via_service_sets_updated_by(self):
        from task_service.infrastructure.persistence.models import Tag
        svc = _tag_service()
        repo = _tag_repo()
        set_current_user_id(207)
        tag = repo.create_tag({'name': 'int840-tagupd'})
        repo.commit()
        set_current_user_id(208)
        result = svc.update_tag(tag.id, {'description': 'updated'})
        assert result['success'] is True
        session = get_db_session()
        try:
            po = session.get(Tag, tag.id)
            assert po.updated_by_user_id == 208
        finally:
            session.close()

    def test_soft_delete_tag_sets_deleted_by(self):
        from task_service.infrastructure.persistence.models import Tag
        repo = _tag_repo()
        set_current_user_id(209)
        tag = repo.create_tag({'name': 'int840-tagdel'})
        repo.commit()
        set_current_user_id(210)
        repo.soft_delete_tag(tag)
        repo.commit()
        session = get_db_session()
        try:
            po = session.get(Tag, tag.id)
            assert po.deleted is True
            assert po.deleted_by_user_id == 210
            assert po.deleted_at is not None
        finally:
            session.close()

    def test_batch_update_tag_category_sets_updated_by(self):
        from task_service.infrastructure.persistence.models import Tag, TagCategory
        repo = _tag_repo()
        set_current_user_id(211)
        cat = repo.create_tag_category({'name': 'int840-batchcat'})
        cat_id = cat.id
        repo.commit()
        tags = [repo.create_tag({'name': f'int840-batch{i}'}) for i in range(2)]
        tag_ids = [t.id for t in tags]
        repo.commit()
        set_current_user_id(212)
        count = repo.batch_update_tag_category(tag_ids, cat_id)
        assert count == 2
        session = get_db_session()
        try:
            for po in session.query(Tag).filter(
                Tag.id.in_(tag_ids)
            ).populate_existing().all():
                assert po.updated_by_user_id == 212
                assert po.category_id == cat_id
        finally:
            session.close()


# ---------------- TestCaseGroup 域 ----------------

class TestCaseGroupOperatorColumns:
    """用例分组 CUD 操作人（INT-840）。"""

    def test_create_group_sets_created_by(self):
        from task_service.infrastructure.persistence.models import TestCaseGroup
        repo = _tag_repo()
        set_current_user_id(301)
        grp = repo.create_group('g-int840-1', 'int840-group')
        session = get_db_session()
        try:
            po = session.get(TestCaseGroup, 'g-int840-1')
            assert po.created_by_user_id == 301
        finally:
            session.close()

    def test_create_group_and_commit_sets_created_by(self):
        from task_service.infrastructure.persistence.models import TestCaseGroup
        repo = _tag_repo()
        set_current_user_id(302)
        item = repo.create_group_and_commit('g-int840-2', 'int840-group2')
        assert item['id'] == 'g-int840-2'
        session = get_db_session()
        try:
            po = session.get(TestCaseGroup, 'g-int840-2')
            assert po.created_by_user_id == 302
        finally:
            session.close()

    def test_update_group_sets_updated_by(self):
        from task_service.infrastructure.persistence.models import TestCaseGroup
        repo = _tag_repo()
        set_current_user_id(303)
        repo.create_group_and_commit('g-int840-3', 'int840-group3')
        set_current_user_id(304)
        repo.update_group_and_commit('g-int840-3', name='int840-group3b')
        session = get_db_session()
        try:
            po = session.get(TestCaseGroup, 'g-int840-3')
            assert po.updated_by_user_id == 304
            assert po.created_by_user_id == 303
        finally:
            session.close()

    def test_delete_group_sets_deleted_by(self):
        from task_service.infrastructure.persistence.models import TestCaseGroup
        repo = _tag_repo()
        set_current_user_id(305)
        repo.create_group_and_commit('g-int840-4', 'int840-group4')
        set_current_user_id(306)
        repo.delete_group_and_commit('g-int840-4')
        session = get_db_session()
        try:
            po = session.get(TestCaseGroup, 'g-int840-4')
            assert po.deleted is True
            assert po.deleted_by_user_id == 306
        finally:
            session.close()

    def test_create_group_via_testcase_crud_service(self):
        """自动建分组路径走同一 create_group，一并覆盖（INT-840）。

        testcase_crud_service 单例与 testcase_repository 共用同一仓储实例，
        自动建分组（create_case 中 group 不存在时）即调用 repo.create_group。
        此处经该单例的 repo 路径验证 created_by_user_id 落库。
        """
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        from task_service.infrastructure.persistence.models import TestCaseGroup
        set_current_user_id(307)
        repo = testcase_crud_service.repo  # 同一 testcase_repository 实例
        repo.create_group('g-int840-auto', 'int840-auto-group', '自动创建')
        session = get_db_session()
        try:
            po = session.get(TestCaseGroup, 'g-int840-auto')
            assert po.created_by_user_id == 307
        finally:
            session.close()


# ---------------- 无上下文（AUTH_MODE=off 等价） ----------------

class TestNoContextNullColumns:
    """无认证上下文（AUTH_MODE=off 等价）：操作人列 NULL，不硬编码 0。"""

    def test_create_soft_delete_null(self):
        from task_service.infrastructure.persistence.models import (
            Tag, TagCategory, TestCaseGroup,
        )
        repo = _tag_repo()
        set_current_user_id(None)
        cat = repo.create_tag_category({'name': 'int840-null-cat'})
        cat_id = cat.id
        tag = repo.create_tag({'name': 'int840-null-tag'})
        tag_id = tag.id
        repo.commit()
        repo.soft_delete_tag_category(cat)
        repo.soft_delete_tag(tag)
        repo.create_group_and_commit('g-int840-null', 'int840-null-group')
        repo.delete_group_and_commit('g-int840-null')
        session = get_db_session()
        try:
            cat_po = session.get(TagCategory, cat_id)
            tag_po = session.get(Tag, tag_id)
            grp_po = session.get(TestCaseGroup, 'g-int840-null')
            assert cat_po.created_by_user_id is None
            assert cat_po.deleted_by_user_id is None
            assert tag_po.created_by_user_id is None
            assert tag_po.deleted_by_user_id is None
            assert grp_po.created_by_user_id is None
            assert grp_po.deleted_by_user_id is None
        finally:
            session.close()
