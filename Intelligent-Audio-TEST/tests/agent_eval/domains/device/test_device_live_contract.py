# -*- coding: utf-8 -*-
"""INT-2459 设备 / SPL 域实测：真实 docker 网关上的 10 条任务与契约核对。

默认跳过；显式给出网关地址时运行（实测命令）：

    AGENT_LIVE_GATEWAY=http://localhost:15000 python -m pytest \
        tests/agent_eval/domains/device/test_device_live_contract.py -s

前置：docker 栈已起（网关 15000），栈上存在 dev_user / dev_password 账号，
device_service 跑宿主机 gRPC 50053（环境铁律）。
"""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.tool_gateway import (
    PERMISSION_DENIED, SharedToolGateway,
)
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import ToolInvocationContext
from agent_service.infrastructure.tools.registry_bridge import (
    RestToolClient, RunCredentialRegistry, SharedToolRegistryBridge,
)
from tests.agent_eval.domains.device import fixtures

GATEWAY = os.environ.get('AGENT_LIVE_GATEWAY', '').strip().rstrip('/')
GATEWAY_USER = os.environ.get('UI_TEST_USERNAME', 'dev_user')
GATEWAY_PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')

ALL_PERMISSIONS = ('device:read', 'spl:read', 'digital_spl:read')

pytestmark = pytest.mark.skipif(
    not GATEWAY, reason='未设置 AGENT_LIVE_GATEWAY，跳过真实网关实测')


def _get_json(url):
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _login():
    """按 INT-147 契约登录：GET 公钥 → RSA-OAEP 加密密码 → form 提交。"""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    key = _get_json(f'{GATEWAY}/api/v1/auth/encryption-key')
    assert key.get('enabled') is True, '网关未开启密码加密，无法按契约登录'
    public_key = serialization.load_pem_public_key(
        key['public_key'].encode('utf-8'))
    ciphertext = base64.b64encode(public_key.encrypt(
        GATEWAY_PASSWORD.encode('utf-8'),
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                     algorithm=hashes.SHA256(),
                     label=None))).decode('ascii')
    body = urllib.parse.urlencode({
        'username': GATEWAY_USER,
        'password_encrypted': ciphertext,
        'encryption_key_id': key['kid'],
    }).encode('utf-8')
    request = urllib.request.Request(
        f'{GATEWAY}/api/v1/auth/login', data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(request, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))


@pytest.fixture(scope='module')
def live():
    try:
        login = _login()
    except (urllib.error.URLError, OSError) as exc:  # pragma: no cover
        pytest.skip(f'网关不可用：{exc}')
    if 'access_token' not in login:  # pragma: no cover
        pytest.skip(f'网关登录失败：{str(login)[:200]}')
    token = login['access_token']
    credentials = RunCredentialRegistry()
    credentials.put('live-run', f'Bearer {token}')
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=RestToolClient(GATEWAY),
        credentials=credentials)
    return gateway, token


def _ctx(permissions=ALL_PERMISSIONS):
    return ToolInvocationContext(
        run_id='live-run', session_id='live', owner_id=1, tenant_id='default',
        step_id='step', permissions=tuple(permissions), idempotency_key='k')


def _execute(gateway, arguments, permissions=ALL_PERMISSIONS):
    return gateway.execute(
        ToolCallRequest(tool_call_id='live', name='device_query',
                        arguments=arguments), _ctx(permissions))


def _raw(path, token):
    request = urllib.request.Request(
        f'{GATEWAY}{path}', headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        return exc.code, None


def test_live_device_query_10_domain_tasks(live):
    """卡面可测标准 1：设备 6 条 + SPL 4 条任务在真实网关上全部走通。"""
    gateway, token = live
    status, devices = _raw('/api/v1/test-devices?page=1&per_page=10', token)
    assert status == 200 and devices['success'] is True
    device_items = devices['data']['items']
    if not device_items:  # pragma: no cover
        pytest.skip('库里没有设备，无法跑详情类任务')
    device_id = device_items[0]['id']

    status, mappings = _raw('/api/v1/spl?page=1&per_page=10', token)
    assert status == 200 and mappings['success'] is True
    mapping_items = mappings['data']['items']
    if not mapping_items:  # pragma: no cover
        pytest.skip('库里没有 SPL 映射，无法跑 SPL 任务')
    mapping_id = mapping_items[0]['id']

    passed = []
    for task in fixtures.DOMAIN_TASKS:
        arguments = dict(task['arguments'])
        action = arguments['action']
        if action == 'detail':
            arguments['device_id'] = device_id
        if action == 'status':
            arguments['ids'] = [device_id]
        if action == 'status_history':
            arguments['device_id'] = device_id
        if action in ('spl_mapping', 'spl_history', 'spl_calibration_data'):
            arguments['mapping_id'] = mapping_id
        result = _execute(gateway, arguments)
        assert result.ok, f"{task['name']} 失败：{result.error_code} {result.content}"
        payload = json.loads(result.content)
        assert payload['success'] is True, task['name']
        data = payload['data']
        if action == 'spl_calibration_data':
            # 未做过校准的映射 calibration_data 为 null，也是真实返回
            assert data is None or 'points' in data, data
        else:
            for field in task['checks']:
                assert field in data, f"{task['name']} 缺少 {field}"
        passed.append(task['name'])
    assert len(passed) == 10
    print('\n10 条设备 / SPL 域任务全部通过：', '、'.join(passed))


def test_live_device_fields_match_gateway_schema(live):
    """卡面可测标准 2：设备状态 / 告警字段与真实接口一致。"""
    from api_gateway.schemas.device import DeviceItem, DeviceStatusItem

    gateway, token = live
    status, listed = _raw('/api/v1/test-devices?page=1&per_page=5', token)
    assert status == 200
    allowed = set(DeviceItem.model_fields)
    for item in listed['data']['items']:
        assert set(item) <= allowed, sorted(set(item) - allowed)

    status, statuses = _raw('/api/v1/test-devices/status', token)
    assert status == 200 and statuses['success'] is True
    allowed_status = set(DeviceStatusItem.model_fields)
    for item in statuses['data']['items']:
        assert set(item) <= allowed_status, sorted(set(item) - allowed_status)

    status, alarms = _raw('/api/v1/test-devices/alarms?page=1&per_page=5', token)
    assert status == 200 and alarms['success'] is True
    assert {'items', 'total', 'page', 'per_page', 'pages'} <= set(
        alarms['data'])
    for item in alarms['data']['items']:
        for field in ('id', 'device_id', 'severity', 'status', 'metric_type',
                      'triggered_at'):
            assert field in item, field


def test_live_spl_mapping_and_history_trace_to_source(live):
    """卡面可测标准 2：SPL 映射 / 历史可追溯到真实来源（播放设备 + 映射 ID）。"""
    gateway, token = live
    status, mappings = _raw('/api/v1/spl?page=1&per_page=5', token)
    assert status == 200
    items = mappings['data']['items']
    if not items:  # pragma: no cover
        pytest.skip('库里没有 SPL 映射')
    mapping = items[0]
    mapping_id = mapping['id']

    result = _execute(gateway, {'action': 'spl_mapping',
                                'mapping_id': mapping_id})
    assert result.ok, result.content
    detail = json.loads(result.content)['data']
    assert detail['id'] == mapping_id
    assert detail['device_id'] == mapping['device_id']
    for field in ('target_spl', 'calibration_status', 'test_frequency'):
        assert field in detail, field

    # 按播放设备反查必须命中同一条映射（来源可追溯）
    playback_device_id = mapping['device_id']
    if playback_device_id is None:  # pragma: no cover - 未绑定播放设备的映射
        pytest.skip('首条映射未绑定播放设备，无法核对按设备反查')
    result = _execute(gateway, {'action': 'spl_by_device',
                                'device_id': playback_device_id})
    assert result.ok, result.content
    by_device = json.loads(result.content)['data']
    assert mapping_id in {item['id'] for item in by_device['items']}

    result = _execute(gateway, {'action': 'spl_history',
                                'mapping_id': mapping_id})
    assert result.ok, result.content
    history = json.loads(result.content)['data']
    assert 'items' in history and 'total' in history

    calibration = detail.get('calibration_data')
    if calibration:
        for point in calibration.get('points', []):
            for field in ('spl', 'gainOffset', 'baseLevel', 'finalLevel'):
                assert field in point, field


def test_live_digital_spl_fields(live):
    gateway, token = live
    status, listed = _raw('/api/v1/digital-spl?page=1&per_page=5', token)
    assert status == 200 and listed['success'] is True
    for item in listed['data']['items']:
        for field in ('id', 'api_id', 'reference_spl', 'calibration_status',
                      'calibration_points'):
            assert field in item, field


def test_live_permission_narrowing_without_rest(live):
    """动作级权限：device:read 不能读 SPL，spl:read 不能读设备。"""
    gateway, _ = live
    result = _execute(gateway, {'action': 'spl_history', 'mapping_id': 1},
                      permissions=('device:read',))
    assert result.error_code == PERMISSION_DENIED

    result = _execute(gateway, {'action': 'list'},
                      permissions=('spl:read',))
    assert result.error_code == PERMISSION_DENIED

    result = _execute(gateway,
                      {'action': 'digital_spl_mapping', 'mapping_id': 1},
                      permissions=('spl:read',))
    assert result.error_code == PERMISSION_DENIED


def test_live_filters_take_effect(live):
    """参数名 / 序列化口径与真实网关一致：过滤条件必须真的收窄结果。"""
    gateway, token = live
    status, listed = _raw('/api/v1/test-devices?page=1&per_page=50', token)
    assert status == 200
    items = listed['data']['items']
    if not items:  # pragma: no cover
        pytest.skip('库里没有设备')

    # device_type 过滤：返回行必须都是该类型，且数量不超过全量
    device_type = items[0].get('type')
    if device_type:
        result = _execute(gateway, {'action': 'list', 'device_type': device_type,
                                    'page': 1, 'per_page': 50})
        assert result.ok, result.content
        filtered = json.loads(result.content)['data']
        assert filtered['total'] <= listed['data']['total']
        assert all(item['type'] == device_type
                   for item in filtered['items'])

    # status 的 ids 数组按逗号串下发，返回行必须落在这组 id 内
    ids = [item['id'] for item in items[:2]]
    result = _execute(gateway, {'action': 'status', 'ids': ids})
    assert result.ok, result.content
    statuses = json.loads(result.content)['data']
    assert {item['id'] for item in statuses['items']} <= set(ids)

    # alarms 的状态枚举过滤
    result = _execute(gateway, {'action': 'alarms', 'status': 'active',
                                'page': 1, 'per_page': 10})
    assert result.ok, result.content

    # SPL 校准状态过滤
    status, mappings = _raw('/api/v1/spl?page=1&per_page=10', token)
    assert status == 200
    mapping_items = mappings['data']['items']
    if mapping_items:  # pragma: no cover - 空库环境
        calibration_status = mapping_items[0]['calibration_status']
        result = _execute(gateway, {'action': 'spl_mappings',
                                    'calibration_status': calibration_status,
                                    'page': 1, 'per_page': 10})
        assert result.ok, result.content
        filtered = json.loads(result.content)['data']
        assert all(item['calibration_status'] == calibration_status
                   for item in filtered['items'])


def test_live_missing_mapping_semantics(live):
    gateway, _ = live
    result = _execute(gateway,
                      {'action': 'digital_spl_mapping', 'mapping_id': 2000000000},
                      permissions=('digital_spl:read',))
    assert not result.ok
    assert result.error_code == 'NOT_FOUND'
    assert '不存在或无权访问' in result.content
