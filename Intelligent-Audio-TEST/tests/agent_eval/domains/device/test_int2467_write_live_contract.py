# -*- coding: utf-8 -*-
"""INT-2467 设备 / SPL 写工具实测（真实 docker 网关）。

默认跳过；显式给出网关地址时运行：

    AGENT_LIVE_GATEWAY=http://localhost:15000 python -m pytest \
        tests/agent_eval/domains/device/test_int2467_write_live_contract.py -s

验收口径（卡面 1 / 5）：
- 写工具在「审批已通过」的执行上下文下按真实 REST 接口产生副作用，
  且读回来与人工操作一致；
- 只用「接线测试_」前缀数据，并在用例结束前清理；
- 破坏性动作只实测无副作用的 ``scan``；重启 / 关机 / 安装 / 卸载在共享栈上
  会中断他人任务或改设备版本，**不执行**（由单测覆盖审批与二次确认）。
"""
import os

import pytest

from tests.agent_eval import live_support

pytestmark = pytest.mark.skipif(
    not live_support.available(),
    reason='未设置 AGENT_LIVE_GATEWAY，跳过真实网关实测')

SPL_PERMISSIONS = ('spl:read', 'spl:create', 'spl:update', 'spl:delete',
                   'spl:test_tone')
DIGITAL_PERMISSIONS = ('digital_spl:read', 'digital_spl:create',
                       'digital_spl:update', 'digital_spl:delete')
DEVICE_PERMISSIONS = ('device:read', 'device:control')


@pytest.fixture(scope='module')
def live():
    token = live_support.login()
    return live_support.gateway_client(token), token


def _execute(gateway, name, arguments, permissions):
    from agent_service.domain.model.entities import ToolCallRequest

    result = gateway.execute(
        ToolCallRequest(tool_call_id=f'live-{name}', name=name,
                        arguments=arguments),
        live_support.approved_ctx(permissions=permissions))
    return result


def test_live_spl_mapping_create_update_delete(live):
    """物理域：创建 → 改 → 删，全部为真实副作用且可清理。"""
    import json

    gateway, token = live
    name = f'{live_support.LIVE_PREFIX}INT2467_物理映射'
    created_id = None
    try:
        result = _execute(gateway, 'spl_calibrate', {
            'action': 'mapping_create', 'name': name,
            'device_type': 'dry', 'distance': 1.2, 'target_spl': 65,
            'test_frequency': 1000,
        }, SPL_PERMISSIONS)
        assert result.ok, f'{result.error_code} {result.content[:300]}'
        payload = json.loads(result.content)
        assert payload['success'] is True, payload
        created_id = payload['data']['id']
        assert created_id

        # 读侧核对（device_query 的 spl_mapping 动作 = GET /api/v1/spl/{id}）
        read = _execute(gateway, 'device_query',
                        {'action': 'spl_mapping', 'mapping_id': created_id},
                        SPL_PERMISSIONS)
        assert read.ok, read.content[:300]
        detail = json.loads(read.content)['data']
        assert detail['name'] == name
        assert detail['distance'] == pytest.approx(1.2)

        # 修改
        update = _execute(gateway, 'spl_calibrate', {
            'action': 'mapping_update', 'mapping_id': created_id,
            'target_spl': 66, 'description': f'{live_support.LIVE_PREFIX}改',
        }, SPL_PERMISSIONS)
        assert update.ok, f'{update.error_code} {update.content[:300]}'
        read = _execute(gateway, 'device_query',
                        {'action': 'spl_mapping', 'mapping_id': created_id},
                        SPL_PERMISSIONS)
        detail = json.loads(read.content)['data']
        assert detail['target_spl'] == pytest.approx(66)
    finally:
        if created_id:
            deleted = _execute(gateway, 'spl_calibrate', {
                'action': 'mapping_delete', 'mapping_id': created_id,
            }, SPL_PERMISSIONS)
            assert deleted.ok, f'清理失败 {deleted.content[:300]}'
    # 删除后读不到（网关对不存在映射返回 400 + 文案）
    status, _body = live_support.raw(
        'GET', f'/api/v1/spl/{created_id}', token)
    assert status == 400


def test_live_digital_spl_mapping_create_update_delete(live):
    """数字域：创建 → 改 → 删（依赖一个真实被测 API）。"""
    import json

    gateway, token = live
    status, apis = live_support.raw('GET', '/api/v1/apis?page=1&per_page=1', token)
    assert status == 200 and apis['success'] is True
    items = apis['data']['items']
    if not items:  # pragma: no cover
        pytest.skip('库里没有被测 API，无法创建数字域映射')
    api_id = items[0]['id']

    name = f'{live_support.LIVE_PREFIX}INT2467_数字映射'
    created_id = None
    try:
        result = _execute(gateway, 'spl_calibrate', {
            'action': 'digital_mapping_create', 'api_id': api_id,
            'name': name, 'reference_spl': 65,
            'calibration_data': {'points': [
                {'target_spl': 65, 'rms_dbfs': -20}]},
        }, DIGITAL_PERMISSIONS)
        assert result.ok, f'{result.error_code} {result.content[:300]}'
        payload = json.loads(result.content)
        assert payload['success'] is True, payload
        created_id = payload['data']['id']

        update = _execute(gateway, 'spl_calibrate', {
            'action': 'digital_mapping_update', 'mapping_id': created_id,
            'description': f'{live_support.LIVE_PREFIX}改',
        }, DIGITAL_PERMISSIONS)
        assert update.ok, f'{update.error_code} {update.content[:300]}'
    finally:
        if created_id:
            deleted = _execute(gateway, 'spl_calibrate', {
                'action': 'digital_mapping_delete', 'mapping_id': created_id,
            }, DIGITAL_PERMISSIONS)
            assert deleted.ok, f'清理失败 {deleted.content[:300]}'
    status, _body = live_support.raw(
        'GET', f'/api/v1/digital-spl/{created_id}', token)
    assert status == 404


def test_live_device_control_scan_is_real(live):
    """设备扫描：真实驱动层扫描（不改状态、不加设备），只验动作接线。

    重启 / 关机 / 安装 / 卸载在共享栈上会中断他人任务或改设备版本，
    本用例不执行；审批与二次确认由单测覆盖。
    """
    import json

    gateway, _token = live
    result = _execute(gateway, 'device_control', {'action': 'scan'},
                      DEVICE_PERMISSIONS)
    assert result.ok, f'{result.error_code} {result.content[:300]}'
    payload = json.loads(result.content)
    assert payload['success'] is True, payload
    assert isinstance(payload['data'], list)


def test_live_write_targets_are_registered_gateway_routes():
    """写工具目标路径必须是网关真实注册的路由（静态核对，不需要登录）。"""
    import api_gateway.app as gateway_app
    from shared.agent_tools import device_tools, mcp_registry

    paths = set(gateway_app.app.openapi()['paths'])

    def concrete(path):
        import re
        return re.sub(r'\{[^}]+\}', '{param}', path)

    registered = {concrete(path) for path in paths}
    targets = list(device_tools.SPL_CALIBRATE_TARGETS.values())
    for action, mcp_name in device_tools.DEVICE_CONTROL_ACTIONS.items():
        targets.append(mcp_registry.get_tool(mcp_name))
    for target in targets:
        assert target is not None
        assert concrete(target['path']) in registered, (
            target['name'], target['path'])
