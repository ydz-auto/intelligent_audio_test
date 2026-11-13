# -*- coding: utf-8 -*-
"""INT-2469 评估写意图工具实测：真实 docker 网关上的维度 / 分类 CRUD 闭环。

默认跳过；显式给出网关地址时运行（实测命令）：

    AGENT_LIVE_GATEWAY=http://localhost:15000 python -m pytest \
        tests/agent_eval/domains/evaluation/test_evaluation_manage_live.py -s

纪律（devloop §4.3 / 卡面可测标准 4）：真实库栈只写本 run 自建的
``接线测试_`` 前缀记录，结束时软删清理；真实维度 / 分类只读，不改不删。

覆盖：创建分类 → 创建维度 → 读回逐字段核对 → 修改维度 / 分类 → 读回核对 →
可见性 private ⇄ shared → 软删分类 / 维度（列表消失、重复删除 404）→
重评估对不存在任务的安全拒绝（不触碰真实任务状态）。
"""
import os
import time
import urllib.error

import pytest

from agent_service.application.tool_gateway import SharedToolGateway
from agent_service.domain.enums import ToolRisk
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import (
    ToolApproval, ToolInvocationContext,
)
from agent_service.infrastructure.tools.registry_bridge import (
    RestToolClient, RunCredentialRegistry, SharedToolRegistryBridge,
)
from tests.agent_eval.domains.evaluation.test_evaluation_live_contract import (
    GATEWAY, GATEWAY_PASSWORD, GATEWAY_USER, _login,
)

pytestmark = pytest.mark.skipif(
    not GATEWAY, reason='未设置 AGENT_LIVE_GATEWAY，跳过真实网关实测')

PREFIX = '接线测试_INT2469_'
WRITE_PERMISSIONS = ('*',)


def _ctx(permissions=WRITE_PERMISSIONS):
    return ToolInvocationContext(
        run_id='live-run', session_id='live', owner_id=1,
        tenant_id='default', step_id='live', permissions=tuple(permissions),
        idempotency_key='live', approval=ToolApproval(
            approval_id='live-approval', risk=ToolRisk.WRITE, proposal={}))


@pytest.fixture(scope='module')
def live():
    try:
        login = _login()
    except (urllib.error.URLError, OSError) as exc:  # pragma: no cover
        pytest.skip(f'网关不可用：{exc}')
    if 'access_token' not in login:  # pragma: no cover
        pytest.skip(f'网关登录失败：{str(login)[:200]}')
    credentials = RunCredentialRegistry()
    credentials.put('live-run', f"Bearer {login['access_token']}")
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=RestToolClient(GATEWAY), credentials=credentials)


def _run(gateway, action, permissions=WRITE_PERMISSIONS, **arguments):
    result = gateway.execute(
        ToolCallRequest(tool_call_id=f'live-{action}',
                        name='evaluation_manage',
                        arguments={'action': action, **arguments}),
        _ctx(permissions))
    return result


def _query(gateway, action, **arguments):
    result = gateway.execute(
        ToolCallRequest(tool_call_id=f'live-q-{action}',
                        name='evaluation_query',
                        arguments={'action': action, **arguments}),
        ToolInvocationContext(
            run_id='live-run', session_id='live', owner_id=1,
            tenant_id='default', step_id='live',
            permissions=('evaluation:read',), idempotency_key='live'))
    assert result.ok, result.content
    import json
    return json.loads(result.content)


def _categories(gateway):
    payload = _query(gateway, 'categories')
    data = payload.get('data') or {}
    return data.get('items') or []


def _dimension(gateway, dim_id):
    result = _detail_result(gateway, dim_id)
    assert result.ok, result.content
    import json
    payload = json.loads(result.content)
    return payload.get('data') or {}


def _data(result):
    import json
    assert result.ok, result.content
    payload = json.loads(result.content)
    return payload.get('data') or {}


def _detail_result(gateway, dim_id):
    """读维度详情并返回原始结果（软删后是 404，不能按成功断言）。"""
    return gateway.execute(
        ToolCallRequest(tool_call_id='live-detail', name='evaluation_query',
                        arguments={'action': 'dimension', 'dim_id': dim_id}),
        ToolInvocationContext(
            run_id='live-run', session_id='live', owner_id=1,
            tenant_id='default', step_id='live',
            permissions=('evaluation:read',), idempotency_key='live'))


def test_dimension_and_category_crud_live(live):
    suffix = f'{int(time.time())}'
    cat_name = f'{PREFIX}分类_{suffix}'
    dim_name = f'{PREFIX}维度_{suffix}'
    cat_id = dim_id = None
    try:
        # ---- 分类：创建 ----
        cat = _data(_run(live, 'category_create', body={
            'name': cat_name,
            'description': '接线测试_分类初始描述',
            'visibility': 'private'}))
        cat_id = cat['id']
        found = [item for item in _categories(live) if item['id'] == cat_id]
        assert found and found[0]['name'] == cat_name
        assert found[0]['description'] == '接线测试_分类初始描述'

        # ---- 分类：修改 + 读回 ----
        _data(_run(live, 'category_update', cat_id=cat_id, body={
            'description': '接线测试_分类已更新'}))
        found = [item for item in _categories(live) if item['id'] == cat_id]
        assert found and found[0]['description'] == '接线测试_分类已更新'
        assert found[0]['name'] == cat_name

        # ---- 维度：创建（字段与人工新建一致）----
        dim = _data(_run(live, 'dimension_create', body={
            'name': dim_name,
            'description': '接线测试_维度初始描述',
            'category_id': cat_id,
            'dimension_type': 'main',
            'type': 'auto',
            'statistic_method': 'average',
            'score_unit': '%',
            'result_min': 0,
            'result_max': 100,
            'decimal_places': 2,
            'weight': 7,
            'status': True,
            'visibility': 'private'}))
        dim_id = dim['id']
        detail = _dimension(live, dim_id)
        for field, expected in (
                ('name', dim_name), ('description', '接线测试_维度初始描述'),
                ('category_id', cat_id), ('weight', 7),
                ('statistic_method', 'average'), ('score_unit', '%'),
                ('result_min', 0), ('result_max', 100),
                ('decimal_places', 2), ('visibility', 'private')):
            assert detail.get(field) == expected, (field, detail.get(field))

        # ---- 维度：修改 + 读回 ----
        _data(_run(live, 'dimension_update', dim_id=dim_id, body={
            'description': '接线测试_维度已更新', 'weight': 9}))
        detail = _dimension(live, dim_id)
        assert detail.get('description') == '接线测试_维度已更新'
        assert detail.get('weight') == 9
        assert detail.get('name') == dim_name

        # ---- 可见性：private → shared → private ----
        assert _dimension(live, dim_id).get('visibility') == 'private'
        _data(_run(live, 'dimension_visibility', dim_id=dim_id,
                   visibility='shared'))
        assert _dimension(live, dim_id).get('visibility') == 'shared'
        _data(_run(live, 'dimension_visibility', dim_id=dim_id,
                   visibility='private'))
        assert _dimension(live, dim_id).get('visibility') == 'private'

        # ---- 删除：软删 + 详情消失 + 重复删除无二次副作用 ----
        _data(_run(live, 'dimension_delete', dim_id=dim_id))
        gone = _detail_result(live, dim_id)
        assert not gone.ok and gone.error_code == 'NOT_FOUND'
        # 评估服务对已软删维度再删是幂等成功（不物理删、不报错）；分类则 404。
        # 两者的共同判据是「详情仍是 404、不产生第二次删除」。
        again = _run(live, 'dimension_delete', dim_id=dim_id)
        assert again.ok or again.error_code == 'NOT_FOUND'
        assert _detail_result(live, dim_id).error_code == 'NOT_FOUND'

        _data(_run(live, 'category_delete', cat_id=cat_id))
        assert not [c for c in _categories(live) if c['id'] == cat_id]
        # 分类重复删除：网关以 400 + code 404「未找到分类」表达已删（无二次副作用）
        again = _run(live, 'category_delete', cat_id=cat_id)
        assert not again.ok
        assert again.error_code in ('NOT_FOUND', 'UPSTREAM_ERROR')
        assert '未找到' in again.content
    finally:
        # 兜底清理：只做软删，删除已删记录是幂等的 404，不影响结论
        if dim_id is not None:
            _run(live, 'dimension_delete', dim_id=dim_id)
        if cat_id is not None:
            _run(live, 'category_delete', cat_id=cat_id)


def test_reevaluate_rejects_missing_task_without_side_effect(live):
    """不存在的任务：网关 404 拒绝，不改任何真实任务状态。"""
    result = _run(live, 'reevaluate', body={'task_id': 2147483000})
    assert not result.ok
    assert result.error_code in ('NOT_FOUND', 'UPSTREAM_ERROR')


def test_write_permission_is_narrowed_live(live):
    """只有执行权限的用户不能删除维度（动作级权限收窄）。"""
    result = _run(live, 'dimension_delete', permissions=('evaluation:execute',),
                  dim_id=2147483000)
    assert not result.ok
    assert result.error_code == 'PERMISSION_DENIED'
