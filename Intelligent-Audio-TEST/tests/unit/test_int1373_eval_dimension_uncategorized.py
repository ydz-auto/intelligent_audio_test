# -*- coding: utf-8 -*-
"""INT-1373 专项：编辑评估维度设「未分类」清空不落库——网关保留显式 category_id=None。

现象：评估维度管理页编辑维度把「所属分类」改为「未分类」（前端 Select 空值项，
发送 category_id: null）保存后，UI 回显「未分类」，但 GET 详情仍返回原分类。

根因：网关 api_gateway EvaluationCommandService.update 用
`model_dump(by_alias=False, exclude_none=True)` 丢弃请求中显式 category_id=None
→ 转发到 evaluation_service 时已无该键 → `_extract_model_fields` 不改该字段
→ 分类保持原值。老 Vue 表单无「未分类」项未暴露此路径；React 表单提供空值项故触发。

修复（镜像 INT-1334 标签同款修复）：
`model_fields_set` 判断保留显式 category_id=None，透传 evaluation_service 清空分类。
evaluation_service 已具备清空能力：`_extract_model_fields` 对 category_id == '' or None
归一 None，`update_dimension → _apply_dimension_fields` 会落 null。

断言：
1. 显式 category_id=null → 转发载荷保留该键且为 None（→ 服务端清空分类）
2. 未传 category_id 键 → 不凭空补键（改其它字段不受影响）
3. 显式非 null 分类 ID → 原值转发
"""
import os
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from api_gateway.infrastructure.request_adapter import set_current_request


def _fake_request(user_id=1, permissions=None, json_body=None):
    """镜像 test_int1334 / test_int567 的请求桩（state._json_body 供 get_json）。"""
    state = SimpleNamespace(
        user_id=user_id,
        permissions=list(permissions or []),
        username='dev_user',
        role_id=1,
        _json_body=json_body or {},
    )
    return SimpleNamespace(state=state, query_params={})


@pytest.fixture(autouse=True)
def _reset_request():
    yield
    set_current_request(None)


class TestGatewayUpdateForwardsCategoryIdNull:
    """网关 EvaluationCommandService.update 应把显式 category_id=None 保留在转发载荷中。"""

    def test_update_preserves_explicit_category_id_null(self, monkeypatch):
        from api_gateway.application.services.evaluation import (
            evaluation_command_service as cmd_mod,
        )
        captured = {}

        class _Rec:
            def update_dimension(self, dim_id, data):
                captured['data'] = data
                return {
                    'success': True, 'message': '评分维度更新成功',
                    'data': {'id': dim_id, 'name': 'x', 'category_id': None},
                }

        monkeypatch.setattr(cmd_mod, '_evaluation_acl', _Rec())
        # 非 admin（无 '*'）：preload_private_state 短路，不会额外调用 get_dimension
        set_current_request(_fake_request(
            user_id=1, permissions=['evaluation:dim_manage'],
            json_body={'name': 'x', 'description': 'd', 'category_id': None},
        ))

        payload, http_code = cmd_mod.EvaluationCommandService.update(3)
        assert http_code == 200
        assert 'category_id' in captured['data']
        assert captured['data']['category_id'] is None

    def test_update_absent_category_id_not_injected(self, monkeypatch):
        """兼容性：未传 category_id 键时不应凭空补键（改其它字段不受影响）。"""
        from api_gateway.application.services.evaluation import (
            evaluation_command_service as cmd_mod,
        )
        captured = {}

        class _Rec:
            def update_dimension(self, dim_id, data):
                captured['data'] = data
                return {
                    'success': True, 'message': '评分维度更新成功',
                    'data': {'id': dim_id, 'name': 'x'},
                }

        monkeypatch.setattr(cmd_mod, '_evaluation_acl', _Rec())
        set_current_request(_fake_request(
            user_id=1, permissions=['evaluation:dim_manage'],
            json_body={'name': 'x'},
        ))

        payload, http_code = cmd_mod.EvaluationCommandService.update(3)
        assert http_code == 200
        assert 'category_id' not in captured['data']

    def test_update_preserves_explicit_non_null_category_id(self, monkeypatch):
        """显式传入有效分类 ID 时保持原值转发。"""
        from api_gateway.application.services.evaluation import (
            evaluation_command_service as cmd_mod,
        )
        captured = {}

        class _Rec:
            def update_dimension(self, dim_id, data):
                captured['data'] = data
                return {
                    'success': True, 'message': '评分维度更新成功',
                    'data': {'id': dim_id, 'name': 'x', 'category_id': data.get('category_id')},
                }

        monkeypatch.setattr(cmd_mod, '_evaluation_acl', _Rec())
        set_current_request(_fake_request(
            user_id=1, permissions=['evaluation:dim_manage'],
            json_body={'name': 'x', 'category_id': 7},
        ))

        payload, http_code = cmd_mod.EvaluationCommandService.update(3)
        assert http_code == 200
        assert captured['data']['category_id'] == 7
