# -*- coding: utf-8 -*-
"""INT-2470 算法写意图工具实测：真实 docker 网关上的提案 → 审批 → 执行闭环。

默认跳过；显式给出网关地址时运行（实测命令）：

    AGENT_LIVE_GATEWAY=http://localhost:15000 python -m pytest \
        tests/agent_eval/domains/algorithm/test_algorithm_manage_live.py -s

纪律（devloop §4.3 / 卡面可测标准 4）：真实库栈只写本 run 自建的
``接线测试_`` 前缀记录（算法类型 ``jxtest_int2470_<ts>``），结束时按依赖倒序
软删清理；平台既有算法（如 ``voice_llm``）只读，不改不删。

覆盖：定义创建 / 更新 / 读回 → 设备参数创建 / 更新 / 读回 → 参考参数创建 /
更新 → 映射创建 / 更新 → 热重载（连续两次，可重复执行且不改数据）→ 逐项软删 →
读回确认消失；并与「人工操作」（直接打网关 REST 的同形请求）逐字段对账。
"""
import json
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
from tests.ui.utils.api_client import ApiClient

GATEWAY = os.environ.get('AGENT_LIVE_GATEWAY', '').strip().rstrip('/')
GATEWAY_USER = os.environ.get('UI_TEST_USERNAME', 'dev_user')
GATEWAY_PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')

pytestmark = pytest.mark.skipif(
    not GATEWAY, reason='未设置 AGENT_LIVE_GATEWAY，跳过真实网关实测')

PREFIX = '接线测试_INT2470_'
WRITE_PERMISSIONS = ('*',)


def _ctx(permissions=WRITE_PERMISSIONS):
    return ToolInvocationContext(
        run_id='live-run', session_id='live', owner_id=1,
        tenant_id='default', step_id='live', permissions=tuple(permissions),
        idempotency_key='live', approval=ToolApproval(
            approval_id='live-approval', risk=ToolRisk.WRITE, proposal={}))


def _read_ctx():
    return ToolInvocationContext(
        run_id='live-run', session_id='live', owner_id=1,
        tenant_id='default', step_id='live',
        permissions=('algorithm:read',), idempotency_key='live')


@pytest.fixture(scope='module')
def live():
    client = ApiClient(GATEWAY)
    try:
        client.login(GATEWAY_USER, GATEWAY_PASSWORD)
    except (urllib.error.URLError, OSError, RuntimeError) as exc:  # pragma: no cover
        pytest.skip(f'网关不可用或登录失败：{exc}')
    credentials = RunCredentialRegistry()
    credentials.put('live-run', f'Bearer {client.token}')
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=RestToolClient(GATEWAY), credentials=credentials)
    return gateway, client, client.token


def _run(gateway, action, permissions=WRITE_PERMISSIONS, **arguments):
    return gateway.execute(
        ToolCallRequest(tool_call_id=f'live-{action}',
                        name='algorithm_manage',
                        arguments={'action': action, **arguments}),
        _ctx(permissions))


def _query(gateway, action, **arguments):
    result = gateway.execute(
        ToolCallRequest(tool_call_id=f'live-q-{action}',
                        name='algorithm_query',
                        arguments={'action': action, **arguments}),
        _read_ctx())
    assert result.ok, result.content
    return json.loads(result.content).get('data')


def _data(result):
    assert result.ok, result.content
    return json.loads(result.content).get('data')


def _items(payload):
    """列表接口两种形态（分页信封 / 裸数组）统一取行。"""
    if isinstance(payload, dict):
        return payload.get('items') or []
    return payload or []


def _delete_all(gateway, mapping_id, reference_id, param_id, algo_type):
    """兜底清理：按依赖倒序软删；对已删记录再删是幂等 404，不影响结论。"""
    if mapping_id is not None:
        _run(gateway, 'mapping_delete', mapping_id=mapping_id)
    if reference_id is not None:
        _run(gateway, 'reference_param_delete', param_id=reference_id)
    if param_id is not None:
        _run(gateway, 'param_delete', param_id=param_id)
    if algo_type is not None:
        _run(gateway, 'definition_delete', algo_type=algo_type)


def test_algorithm_write_crud_live(live):
    gateway, client, _token = live
    suffix = str(int(time.time()))
    algo_type = f'jxtest_int2470_{suffix}'
    algo_name = f'{PREFIX}定义_{suffix}'
    param_code = f'jxtest_int2470_param_{suffix}'
    ref_code = f'jxtest_int2470_ref_{suffix}'
    param_id = reference_id = mapping_id = None
    manual_param_id = None
    try:
        # ---- 定义：创建 + 读回（字段与人工新建一致）----
        created = _data(_run(gateway, 'definition_create', body={
            'type': algo_type,
            'name': algo_name,
            'description': f'{PREFIX}初始描述',
            'status': 'offline'}))
        assert created['type'] == algo_type
        detail = _query(gateway, 'definition', algo_type=algo_type)
        assert detail['type'] == algo_type
        assert detail['name'] == algo_name
        assert detail['status'] == 'offline'

        # ---- 定义：更新 + 读回 ----
        _data(_run(gateway, 'definition_update', algo_type=algo_type,
                   body={'description': f'{PREFIX}已更新描述'}))
        detail = _query(gateway, 'definition', algo_type=algo_type)
        assert detail['description'] == f'{PREFIX}已更新描述'
        assert detail['name'] == algo_name

        # ---- 参数：创建（算法级设备参数）+ 读回 ----
        param_body = {
            'algorithm_type': algo_type,
            'param_code': param_code,
            'param_name': '接线测试_参数',
            'param_type': 'text',
            'direction': 'input',
        }
        param = _data(_run(gateway, 'param_create', body=dict(param_body)))
        param_id = param['id']
        rows = _items(_query(gateway, 'params', algorithm_type=algo_type))
        row = [item for item in rows if item['param_code'] == param_code]
        assert row and row[0]['param_name'] == '接线测试_参数'
        assert row[0]['param_type'] == 'text'

        # ---- 人工操作对账：同形请求直接打网关，读回字段与工具路径一致 ----
        manual_code = f'{param_code}_manual'
        manual = client.request('POST', '/algorithm/params', {
            **param_body, 'param_code': manual_code,
            'param_type_source': 'device'})
        manual_param_id = (manual.get('data') or {})['id']
        rows = _items(_query(gateway, 'params', algorithm_type=algo_type))
        tool_row = [r for r in rows if r['param_code'] == param_code][0]
        manual_row = [r for r in rows if r['param_code'] == manual_code][0]
        for field in ('param_name', 'param_type', 'direction', 'required',
                      'hidden', 'ui_order'):
            assert tool_row.get(field) == manual_row.get(field), field

        # ---- 参数：更新 + 读回 ----
        _data(_run(gateway, 'param_update', param_id=param_id,
                   body={'param_name': '接线测试_参数_已改名'}))
        updated = _query(gateway, 'param', param_id=param_id)
        assert updated['param_name'] == '接线测试_参数_已改名'
        assert updated['param_code'] == param_code

        # ---- 参考参数：创建 / 更新 + 读回 ----
        ref = _data(_run(gateway, 'reference_param_create', body={
            'algorithm_type': algo_type, 'code': ref_code,
            'name': '接线测试_参考参数', 'type': 'text'}))
        reference_id = ref['id']
        refs = _items(_query(gateway, 'reference_params',
                             algorithm_type=algo_type))
        assert [item for item in refs if item['code'] == ref_code]
        _data(_run(gateway, 'reference_param_update', param_id=reference_id,
                   body={'name': '接线测试_参考参数_已改名'}))
        assert _query(gateway, 'reference_param',
                      param_id=reference_id)['name'] == '接线测试_参考参数_已改名'

        # ---- 映射：创建 / 更新 + 读回 ----
        mapping = _data(_run(gateway, 'mapping_create', body={
            'algorithm_type': algo_type, 'source_type': 'device',
            'source_param': param_code, 'source_direction': 'output',
            'target_param': '接线测试_目标参数'}))
        mapping_id = mapping['id']
        mappings = _items(_query(gateway, 'mappings', algorithm_type=algo_type))
        found = [item for item in mappings if item['id'] == mapping_id]
        assert found and found[0]['target_param'] == '接线测试_目标参数'
        _data(_run(gateway, 'mapping_update', mapping_id=mapping_id,
                   body={'target_param': '接线测试_目标参数2'}))
        mappings = _items(_query(gateway, 'mappings', algorithm_type=algo_type))
        found = [item for item in mappings if item['id'] == mapping_id]
        assert found and found[0]['target_param'] == '接线测试_目标参数2'

        # ---- 热重载：连续两次都成功，且不改配置数据 ----
        first = _data(_run(gateway, 'reload'))
        second = _data(_run(gateway, 'reload'))
        assert first.get('success') is True
        assert second.get('success') is True
        assert first.get('reload_time') and second.get('reload_time')
        detail = _query(gateway, 'definition', algo_type=algo_type)
        assert detail['description'] == f'{PREFIX}已更新描述'
        mappings = _items(_query(gateway, 'mappings', algorithm_type=algo_type))
        assert [item for item in mappings if item['id'] == mapping_id][0][
            'target_param'] == '接线测试_目标参数2'

        # ---- 软删：逐项消失；再次删除是业务失败而非静默成功 ----
        _data(_run(gateway, 'mapping_delete', mapping_id=mapping_id))
        mappings = _items(_query(gateway, 'mappings', algorithm_type=algo_type))
        assert not [item for item in mappings if item['id'] == mapping_id]
        again = _run(gateway, 'mapping_delete', mapping_id=mapping_id)
        assert not again.ok
        assert again.error_code in ('NOT_FOUND', 'UPSTREAM_ERROR')

        _data(_run(gateway, 'reference_param_delete', param_id=reference_id))
        gone = gateway.execute(
            ToolCallRequest(tool_call_id='live-ref-gone',
                            name='algorithm_query',
                            arguments={'action': 'reference_param',
                                       'param_id': reference_id}),
            _read_ctx())
        assert not gone.ok

        _data(_run(gateway, 'param_delete', param_id=param_id))
        rows = _items(_query(gateway, 'params', algorithm_type=algo_type))
        assert not [item for item in rows if item['id'] == param_id]

        _data(_run(gateway, 'definition_delete', algo_type=algo_type))
        failure = gateway.execute(
            ToolCallRequest(tool_call_id='live-def-gone',
                            name='algorithm_query',
                            arguments={'action': 'definition',
                                       'algo_type': algo_type}),
            _read_ctx())
        assert not failure.ok
    finally:
        _delete_all(gateway, mapping_id, reference_id, param_id, algo_type)
        if manual_param_id is not None:
            _run(gateway, 'param_delete', param_id=manual_param_id)


def test_import_is_additive_and_reports_imported_types_live(live):
    """导入只增不改：已存在的 type 不会被更新（如实返回 imported 列表）。"""
    gateway, _client, _token = live
    suffix = str(int(time.time()))
    algo_type = f'jxtest_int2470_imp_{suffix}'
    algo_name = f'{PREFIX}导入_{suffix}'
    try:
        payload = _data(_run(gateway, 'import', body={'algorithms': [{
            'type': algo_type, 'name': algo_name, 'description': '接线测试_导入'}]}))
        assert algo_type in (payload.get('imported') or [])
        detail = _query(gateway, 'definition', algo_type=algo_type)
        assert detail['name'] == algo_name
        # 再次导入同 type：不更新名称，但仍报告已处理
        first_name = detail['name']
        payload = _data(_run(gateway, 'import', body={'algorithms': [{
            'type': algo_type, 'name': f'{algo_name}_覆盖'}]}))
        assert algo_type in (payload.get('imported') or [])
        assert _query(gateway, 'definition',
                      algo_type=algo_type)['name'] == first_name
    finally:
        _run(gateway, 'definition_delete', algo_type=algo_type)


def test_write_permission_is_narrowed_live(live):
    """只有定义权限的用户不能删参数（动作级权限收窄）。"""
    gateway, _client, _token = live
    result = _run(gateway, 'param_delete',
                  permissions=('algorithm:definition_manage',),
                  param_id=2147483000)
    assert not result.ok
    assert result.error_code == 'PERMISSION_DENIED'


def test_full_chain_proposal_approval_execute_live(tmp_path, live):
    """真实网关上跑一遍完整链路：提案（零副作用）→ 审批 → 执行 → 读回。

    与上面直接用审批凭据执行的区别：这里走 INT-2466 的 ``agent_approval``，
    证明「提案 → 审批 → 执行」在真实栈上闭环，且审批前不产生任何数据。
    """
    from tests.agent_write.helpers import (
        FakeLlm, OWNER_ID, TENANT_ID, decide, make_container,
        pending_approval, text_turn, tool_turn,
    )

    _gateway, _client, token = live
    suffix = str(int(time.time()))
    algo_type = f'jxtest_int2470_chain_{suffix}'
    algo_name = f'{PREFIX}链路_{suffix}'
    credentials = RunCredentialRegistry()
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=RestToolClient(GATEWAY), credentials=credentials)

    llm = FakeLlm([
        tool_turn([ToolCallRequest('c1', 'algorithm_manage', {
            'action': 'definition_create',
            'body': {'type': algo_type, 'name': algo_name,
                     'status': 'offline'}})]),
        text_turn('已提交审批'),
    ])
    container, _engine, _sf = make_container(
        tmp_path, llm, gateway=gateway, name='live_chain.db')
    session = container.run_service.create_session(
        owner_id=OWNER_ID, tenant_id=TENANT_ID, title='算法写链路',
        permissions=['*'])
    run, created = container.run_service.create_run(
        session.id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
        message='新建算法定义', permissions=['*'])
    assert created
    credentials.put(run.id, f'Bearer {token}')
    try:
        container.executor.submit(run.id)
        # 提案阶段：审批单存在，网关里还没有这条定义
        approval = pending_approval(container, run.id)
        assert approval.diff['kind'] == 'algorithm_config'
        missing = _gateway.execute(
            ToolCallRequest(tool_call_id='chain-before',
                            name='algorithm_query',
                            arguments={'action': 'definition',
                                       'algo_type': algo_type}),
            _read_ctx())
        assert not missing.ok

        decide(container, approval.id, 'APPROVE', permissions=['*'])
        container.executor.submit(run.id)
        detail = _query(_gateway, 'definition', algo_type=algo_type)
        assert detail['name'] == algo_name
        assert detail['status'] == 'offline'
    finally:
        _run(_gateway, 'definition_delete', algo_type=algo_type)
