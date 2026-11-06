# -*- coding: utf-8 -*-
"""INT-1334 专项：编辑标签改到「未分类」保存无效——category_id=null 被网关 exclude_none 丢弃。

现象：标签管理页编辑弹窗把「所属分类」改为「未分类」后保存，标签仍保留原分类
（前端已正确发送 category_id: null，根因全部在后端）。

根因（两处后端缺陷叠加）：
1. 网关 api_gateway TagCommandService.update 用 model_dump(by_alias=False,
   exclude_none=True) 丢弃显式 category_id=None，转发到 task_service 时已无该键；
2. task_service tag_crud_service.update_tag 用
   `if data.get('category_id') is not None:` 判断，键缺失时分支不进入，分类不清空。

修复（对齐批量 PUT /tags/batch-category 口径，批量 batch_update_category
用 `category_id if category_id else None` 支持 null 清空）：
- 网关：model_fields_set 判断保留显式 category_id=None（显式 null → 清空分类）；
- task_service：`if 'category_id' in data:` 显式 null 即执行清空。

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内自行清理，对齐 test_int840 口径。
"""
import os
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.infrastructure.user_context import set_current_user_id
from shared.models.database import (
    Base, init_db, get_engine, get_db_session,
)


# ---------------- 工具（task_service 域） ----------------

_TABLES = None


def _ensure_tables():
    init_db(pool_size=2)
    global _TABLES
    if _TABLES is None:
        from task_service.infrastructure.persistence.models import (
            Tag, TagCategory,
        )
        _TABLES = [t.__table__ for t in (TagCategory, Tag)]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


def _cleanup_tables():
    """清空涉及表（sqlite 无 TRUNCATE，逐表 delete）。"""
    _ensure_tables()
    from task_service.infrastructure.persistence.models import (
        Tag, TagCategory,
    )
    session = get_db_session()
    try:
        for model in (Tag, TagCategory):
            session.query(model).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _tag_db():
    _ensure_tables()
    _cleanup_tables()
    yield
    # 上下文必清理，防止泄漏到后续用例
    set_current_user_id(None)
    _cleanup_tables()


def _tag_service():
    from task_service.application.testcase.tag_crud_service import tag_crud_service
    return tag_crud_service


def _tag_repo():
    """延迟导入 testcase_repository（聚合所有 mixin）。"""
    from task_service.infrastructure.persistence.testcase_repository import testcase_repository
    return testcase_repository


# ---------------- task_service：单条 update_tag 显式 null 清空分类 ----------------

class TestUpdateTagClearsCategory:
    """单条更新传 category_id=None 应移入未分类（与批量口径一致）。"""

    def test_update_tag_category_id_null_moves_to_uncategorized(self):
        from task_service.infrastructure.persistence.models import Tag
        svc = _tag_service()
        repo = _tag_repo()
        set_current_user_id(1)
        cat = repo.create_tag_category({'name': 'int1334-cat'})
        repo.commit()
        tag = repo.create_tag({'name': 'int1334-tag', 'category_id': cat.id})
        repo.commit()
        assert tag.category_id == cat.id

        result = svc.update_tag(tag.id, {'category_id': None})
        assert result['success'] is True
        session = get_db_session()
        try:
            po = session.get(Tag, tag.id)
            assert po.category_id is None
        finally:
            session.close()

    def test_update_tag_absent_key_keeps_category(self):
        """兼容性：未传 category_id 键时分类保持不变（不误清空）。"""
        from task_service.infrastructure.persistence.models import Tag
        svc = _tag_service()
        repo = _tag_repo()
        set_current_user_id(2)
        cat = repo.create_tag_category({'name': 'int1334-cat-keep'})
        repo.commit()
        tag = repo.create_tag({'name': 'int1334-tag-keep', 'category_id': cat.id})
        repo.commit()

        result = svc.update_tag(tag.id, {'description': '只改描述'})
        assert result['success'] is True
        session = get_db_session()
        try:
            po = session.get(Tag, tag.id)
            assert po.category_id == cat.id
        finally:
            session.close()

    def test_update_tag_move_to_other_category(self):
        """仍可正常迁移到其它分类（值校验分支不变）。"""
        from task_service.infrastructure.persistence.models import Tag
        svc = _tag_service()
        repo = _tag_repo()
        set_current_user_id(3)
        cat_a = repo.create_tag_category({'name': 'int1334-catA'})
        cat_b = repo.create_tag_category({'name': 'int1334-catB'})
        repo.commit()
        tag = repo.create_tag({'name': 'int1334-tag-move', 'category_id': cat_a.id})
        repo.commit()

        result = svc.update_tag(tag.id, {'category_id': cat_b.id})
        assert result['success'] is True
        session = get_db_session()
        try:
            po = session.get(Tag, tag.id)
            assert po.category_id == cat_b.id
        finally:
            session.close()

    def test_batch_update_category_null_moves_to_uncategorized(self):
        """批量口径（现有行为）：category_id=None 移入未分类，与单条对齐。"""
        from task_service.infrastructure.persistence.models import Tag
        svc = _tag_service()
        repo = _tag_repo()
        set_current_user_id(4)
        cat = repo.create_tag_category({'name': 'int1334-batch-cat'})
        repo.commit()
        tag = repo.create_tag({'name': 'int1334-batch-tag', 'category_id': cat.id})
        repo.commit()

        result = svc.batch_update_category({'tag_ids': [tag.id], 'category_id': None})
        assert result['success'] is True
        session = get_db_session()
        try:
            po = session.get(Tag, tag.id)
            assert po.category_id is None
        finally:
            session.close()


# ---------------- api_gateway：update 保留显式 category_id=None 转发 ----------------

def _fake_request(user_id=1, permissions=None, json_body=None):
    state = SimpleNamespace(
        user_id=user_id,
        permissions=list(permissions or []),
        username='dev_user',
        role_id=1,
        _json_body=json_body or {},
    )
    return SimpleNamespace(state=state, query_params={})


class TestGatewayUpdateForwardsCategoryIdNull:
    """网关 TagCommandService.update 应把显式 category_id=None 保留在转发载荷中。"""

    def test_update_preserves_explicit_category_id_null(self, monkeypatch):
        from api_gateway.infrastructure.request_adapter import set_current_request
        from api_gateway.application.services.tag import tag_command_service as cmd_mod

        captured = {}

        class _Rec:
            def update_tag(self, tag_id, data):
                captured['data'] = data
                return {
                    'success': True, 'message': 'ok',
                    'data': {'id': tag_id, 'name': 'x', 'category_id': None},
                }

        monkeypatch.setattr(cmd_mod, '_tag_acl', _Rec())
        # 非 admin（无 '*'）：preload_private_state 短路，不会额外调用 _tag_acl.get_tag
        set_current_request(_fake_request(
            user_id=1, permissions=['tag:update'],
            json_body={'name': 'x', 'description': 'd', 'color': '#8b5cf6', 'category_id': None},
        ))

        payload, http_code = cmd_mod.TagCommandService.update(3)
        assert http_code == 200
        assert 'category_id' in captured['data']
        assert captured['data']['category_id'] is None

    def test_update_absent_category_id_not_injected(self, monkeypatch):
        """兼容性：未传 category_id 键时不应凭空补键（改其它字段不受影响）。"""
        from api_gateway.infrastructure.request_adapter import set_current_request
        from api_gateway.application.services.tag import tag_command_service as cmd_mod

        captured = {}

        class _Rec:
            def update_tag(self, tag_id, data):
                captured['data'] = data
                return {
                    'success': True, 'message': 'ok',
                    'data': {'id': tag_id, 'name': 'x'},
                }

        monkeypatch.setattr(cmd_mod, '_tag_acl', _Rec())
        set_current_request(_fake_request(
            user_id=1, permissions=['tag:update'],
            json_body={'name': 'x'},
        ))

        payload, http_code = cmd_mod.TagCommandService.update(3)
        assert http_code == 200
        assert 'category_id' not in captured['data']

    def test_update_preserves_explicit_non_null_category_id(self, monkeypatch):
        """显式传入有效分类 ID 时保持原值转发。"""
        from api_gateway.infrastructure.request_adapter import set_current_request
        from api_gateway.application.services.tag import tag_command_service as cmd_mod

        captured = {}

        class _Rec:
            def update_tag(self, tag_id, data):
                captured['data'] = data
                return {
                    'success': True, 'message': 'ok',
                    'data': {'id': tag_id, 'name': 'x', 'category_id': data.get('category_id')},
                }

        monkeypatch.setattr(cmd_mod, '_tag_acl', _Rec())
        set_current_request(_fake_request(
            user_id=1, permissions=['tag:update'],
            json_body={'name': 'x', 'category_id': 7},
        ))

        payload, http_code = cmd_mod.TagCommandService.update(3)
        assert http_code == 200
        assert captured['data']['category_id'] == 7
