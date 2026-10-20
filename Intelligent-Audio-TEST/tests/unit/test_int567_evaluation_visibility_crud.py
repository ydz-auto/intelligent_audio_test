# -*- coding: utf-8 -*-
"""INT-567 专项：新建评估维度/分类 visibility 透传落库（INT-423 P0-4 打回修复）。

背景：集成验收发现 `POST /api/v1/evaluation/dimensions` 载荷 `{visibility:'private'}`
→ 201，落库却为 `'shared'`。

根因链路（P0-4 排查结论）：
- 网关 `api_gateway/schemas/evaluation.py` 的 `DimensionCreateInput` /
  `CategoryCreateInput` / `CategoryUpdateInput` 无 `visibility` 字段，而 APIModel
  `extra="ignore"` 静默丢弃未知字段 → 网关转发到 evaluation_service 的数据里
  没有 visibility → 服务端回落 `'shared'`。
- 服务端 `create_dimension` / `create_category` / `update_dimension` 已支持
  visibility（INT-465/466），`update_category` 缺同口径处理。

修复：
1. 网关 schema 补 visibility（`DimensionInput` + `CategoryCreateInput/UpdateInput`）
2. `evaluation_service` `update_category` 透传 visibility（对齐 update_dimension）

回归断言：
1. 网关 schema model_validate → model_dump 保留 visibility（dimension/category create+update）
2. 网关 EvaluationCommandService.create / create_category 转发数据含 visibility
3. 服务端 update_dimension / update_category 显式携带 visibility 落库生效
4. 共享默认不变（create 不传 visibility → shared）
"""
import os
import tempfile
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import create_engine

import shared.models.database as database
from shared.infrastructure.user_context import (
    set_current_user_id,
    set_current_user_is_admin,
)

USER_A = 1001
USER_B = 1002


# ==================== 网关层：schema 透传 + 命令服务转发 ====================

def _fake_request(user_id=100, json_body=None):
    """镜像 test_int466_gateway_visibility 的请求桩（state._json_body 供 get_json）。"""
    state = SimpleNamespace(
        user_id=user_id,
        permissions=['evaluation:dim_manage'],
        username='dev_user',
        role_id=1,
        _json_body=json_body or {},
    )
    return SimpleNamespace(state=state, query_params={})


@pytest.fixture(autouse=True)
def _reset_request():
    yield
    from api_gateway.infrastructure.request_adapter import set_current_request
    set_current_request(None)


class TestGatewaySchemaKeepsVisibility:
    """网关 Pydantic schema 不得再吞掉 visibility（extra=ignore 是根因）。"""

    def test_dimension_create_and_update_input_keep_visibility(self):
        from api_gateway.schemas.evaluation import (
            DimensionCreateInput,
            DimensionUpdateInput,
        )
        for cls in (DimensionCreateInput, DimensionUpdateInput):
            m = cls.model_validate({'name': '维度', 'visibility': 'private'})
            dumped = m.model_dump(by_alias=False, exclude_none=True)
            assert dumped['visibility'] == 'private'

    def test_category_create_and_update_input_keep_visibility(self):
        from api_gateway.schemas.evaluation import (
            CategoryCreateInput,
            CategoryUpdateInput,
        )
        for cls in (CategoryCreateInput, CategoryUpdateInput):
            m = cls.model_validate({'name': '分类', 'visibility': 'private'})
            dumped = m.model_dump(by_alias=False, exclude_none=True)
            assert dumped['visibility'] == 'private'

    def test_without_visibility_defaults_absent(self):
        """不传 visibility 时 model_dump 不产出该键 → 服务端回落 shared。"""
        from api_gateway.schemas.evaluation import DimensionCreateInput
        m = DimensionCreateInput.model_validate({'name': '维度'})
        dumped = m.model_dump(by_alias=False, exclude_none=True)
        assert 'visibility' not in dumped


class TestGatewayCommandServiceForwardsVisibility:
    """网关命令服务转发到 evaluation_service 的数据必须含 visibility。"""

    def test_create_dimension_forwards_visibility(self, monkeypatch):
        from api_gateway.infrastructure.request_adapter import set_current_request
        from api_gateway.application.services.evaluation import (
            evaluation_command_service as eva_cmd_mod,
        )
        calls = []

        def fake_create_dimension(data):
            calls.append(data)
            return {'success': True, 'message': '评分维度创建成功',
                    'data': {'id': 1}, 'code': 201}

        monkeypatch.setattr(eva_cmd_mod._evaluation_acl, 'create_dimension',
                            fake_create_dimension)
        set_current_request(_fake_request(
            json_body={'name': '新建私有维度', 'type': 'auto',
                       'result_type': 1, 'visibility': 'private'}))

        payload, http_code = eva_cmd_mod.EvaluationCommandService.create()
        assert http_code == 201
        assert calls[0]['visibility'] == 'private'

    def test_update_dimension_forwards_visibility(self, monkeypatch):
        from api_gateway.infrastructure.request_adapter import set_current_request
        from api_gateway.application.services.evaluation import (
            evaluation_command_service as eva_cmd_mod,
        )
        calls = []

        def fake_update_dimension(dim_id, data):
            calls.append(data)
            return {'success': True, 'message': '评分维度更新成功', 'data': None}

        monkeypatch.setattr(eva_cmd_mod._evaluation_acl, 'update_dimension',
                            fake_update_dimension)
        monkeypatch.setattr(eva_cmd_mod._evaluation_acl, 'get_dimension',
                            lambda dim_id: {'success': True, 'data': {}})
        set_current_request(_fake_request(json_body={'visibility': 'private'}))

        payload, http_code = eva_cmd_mod.EvaluationCommandService.update(5)
        assert http_code == 200
        assert calls[0]['visibility'] == 'private'

    def test_create_category_forwards_visibility(self, monkeypatch):
        from api_gateway.infrastructure.request_adapter import set_current_request
        from api_gateway.application.services.evaluation import (
            evaluation_command_service as eva_cmd_mod,
        )
        calls = []

        def fake_create_category(data):
            calls.append(data)
            return {'success': True, 'message': '分类创建成功',
                    'data': {'id': 1}, 'code': 201}

        monkeypatch.setattr(eva_cmd_mod._evaluation_acl, 'create_category',
                            fake_create_category)
        set_current_request(_fake_request(
            json_body={'name': '新建私有分类', 'visibility': 'private'}))

        payload, http_code = eva_cmd_mod.EvaluationCommandService.create_category()
        assert http_code == 201
        assert calls[0]['visibility'] == 'private'

    def test_update_category_forwards_visibility(self, monkeypatch):
        from api_gateway.infrastructure.request_adapter import set_current_request
        from api_gateway.application.services.evaluation import (
            evaluation_command_service as eva_cmd_mod,
        )
        calls = []

        def fake_update_category(cat_id, data):
            calls.append(data)
            return {'success': True, 'message': '分类更新成功', 'data': None}

        monkeypatch.setattr(eva_cmd_mod._evaluation_acl, 'update_category',
                            fake_update_category)
        monkeypatch.setattr(eva_cmd_mod._evaluation_acl, 'list_categories',
                            lambda: {'success': True, 'data': {'items': []}})
        set_current_request(_fake_request(json_body={'visibility': 'private'}))

        payload, http_code = eva_cmd_mod.EvaluationCommandService.update_category(5)
        assert http_code == 200
        assert calls[0]['visibility'] == 'private'


# ==================== 服务端：update 透传落库 + 共享默认 ====================

def _create_tables(engine):
    """建齐 evaluation_service 涉及的表（Category / Dimension）。"""
    from evaluation_service.infrastructure.persistence.orm_models import (
        Category,
        Dimension,
    )
    database.Base.metadata.create_all(engine, tables=[
        Category.__table__, Dimension.__table__,
    ])


@pytest.fixture()
def db():
    """SQLite 临时文件库：engine 直装全局 scoped_session（对齐 test_int465）。"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(f'sqlite:///{path}',
                           connect_args={'check_same_thread': False})
    database.remove_db_session()
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    _create_tables(engine)
    yield database
    database.remove_db_session()
    set_current_user_id(None)
    set_current_user_is_admin(False)
    engine.dispose()
    try:
        os.remove(path)
    except PermissionError:
        pass


@pytest.fixture(autouse=True)
def _clean_context():
    """每个用例开始前清空 user context（防跨用例残留）。"""
    set_current_user_id(None)
    set_current_user_is_admin(False)
    yield
    set_current_user_id(None)
    set_current_user_is_admin(False)


class TestEvaluationServiceUpdateVisibilityPassthrough:
    """命令侧 update 路径显式携带 visibility 必须落库（含 update_category 补齐）。"""

    def _create_dimension(self, name='私有维度', visibility='private'):
        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )
        return evaluation_command_service.create_dimension(
            {'name': name, 'type': 'auto', 'result_type': 1,
             'visibility': visibility})

    def _create_category(self, name='私有分类', visibility='private'):
        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )
        return evaluation_command_service.create_category(
            {'name': name, 'icon': 'icon', 'visibility': visibility})

    def test_create_dimension_private_persists(self, db):
        """P0-4 复现场景：新建 dimension 载荷 visibility=private 落库即 private。"""
        set_current_user_id(USER_A)
        ok = self._create_dimension()
        assert ok['success'] is True
        dim_id = ok['data']['id']

        from evaluation_service.infrastructure.persistence.orm_models import Dimension
        po = database.get_db_session().get(Dimension, dim_id)
        assert po.visibility == 'private'

    def test_create_category_private_persists(self, db):
        set_current_user_id(USER_A)
        ok = self._create_category()
        assert ok['success'] is True
        cat_id = ok['data']['id']

        from evaluation_service.infrastructure.persistence.orm_models import Category
        po = database.get_db_session().get(Category, cat_id)
        assert po.visibility == 'private'

    def test_create_defaults_to_shared(self, db):
        """共享默认不变：create 不传 visibility → shared。"""
        set_current_user_id(USER_A)
        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )
        ok = evaluation_command_service.create_dimension(
            {'name': '默认共享维度', 'type': 'auto', 'result_type': 1})
        dim_id = ok['data']['id']

        from evaluation_service.infrastructure.persistence.orm_models import Dimension
        po = database.get_db_session().get(Dimension, dim_id)
        assert po.visibility == 'shared'

    def test_update_dimension_visibility_persists(self, db):
        set_current_user_id(USER_A)
        dim_id = self._create_dimension()['data']['id']

        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )
        ok = evaluation_command_service.update_dimension(
            dim_id, {'visibility': 'shared'})
        assert ok['success'] is True

        from evaluation_service.infrastructure.persistence.orm_models import Dimension
        po = database.get_db_session().get(Dimension, dim_id)
        assert po.visibility == 'shared'

    def test_update_category_visibility_persists(self, db):
        """INT-567 补齐点：update_category 载荷携带 visibility 必须落库。"""
        set_current_user_id(USER_A)
        cat_id = self._create_category()['data']['id']

        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )
        ok = evaluation_command_service.update_category(
            cat_id, {'visibility': 'shared'})
        assert ok['success'] is True

        from evaluation_service.infrastructure.persistence.orm_models import Category
        po = database.get_db_session().get(Category, cat_id)
        assert po.visibility == 'shared'

    def test_update_category_invalid_visibility_400(self, db):
        """非法值 400：对齐 create 路径校验。"""
        set_current_user_id(USER_A)
        cat_id = self._create_category()['data']['id']

        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )
        ok = evaluation_command_service.update_category(
            cat_id, {'visibility': 'team'})
        assert ok['success'] is False and ok.get('code') == 400

    def test_update_dimension_invalid_visibility_400(self, db):
        set_current_user_id(USER_A)
        dim_id = self._create_dimension()['data']['id']

        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )
        ok = evaluation_command_service.update_dimension(
            dim_id, {'visibility': 'team'})
        assert ok['success'] is False and ok.get('code') == 400

    def test_non_owner_update_private_dimension_403(self, db):
        """既有已通过项不回归：私有维度非 owner 更新 403。"""
        set_current_user_id(USER_A)
        dim_id = self._create_dimension()['data']['id']

        set_current_user_id(USER_B)
        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )
        ok = evaluation_command_service.update_dimension(
            dim_id, {'name': '别人改'})
        assert ok['success'] is False and ok.get('code') == 403

    def test_non_owner_update_private_category_403(self, db):
        set_current_user_id(USER_A)
        cat_id = self._create_category()['data']['id']

        set_current_user_id(USER_B)
        from evaluation_service.application.commands.evaluation_command_service import (
            evaluation_command_service,
        )
        ok = evaluation_command_service.update_category(
            cat_id, {'name': '别人改'})
        assert ok['success'] is False and ok.get('code') == 403
