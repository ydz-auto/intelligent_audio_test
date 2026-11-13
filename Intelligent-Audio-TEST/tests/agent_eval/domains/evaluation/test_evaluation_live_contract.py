# -*- coding: utf-8 -*-
"""INT-2462 评估域实测：真实 docker 网关上的 10 条任务与逐字段契约。

默认跳过；显式给出网关地址时运行（实测命令）：

    AGENT_LIVE_GATEWAY=http://localhost:15000 python -m pytest \
        tests/agent_eval/domains/evaluation/test_evaluation_live_contract.py -s

前置：docker 栈已起（网关 15000），栈上存在 dev_user / dev_password 账号。
agent_service 尚未进 docker（INT-2456 部署接线），因此这里直接组合
``SharedToolGateway`` + ``RestToolClient`` 打真实网关，验证工具层到 REST 的链路。
"""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import pytest

from agent_service.application.tool_gateway import (
    PERMISSION_DENIED, RESOURCE_NOT_FOUND, SharedToolGateway,
)
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import ToolInvocationContext
from agent_service.infrastructure.tools.registry_bridge import (
    RestToolClient, RunCredentialRegistry, SharedToolRegistryBridge,
)
from tests.agent_eval.domains.evaluation import fixtures

GATEWAY = os.environ.get('AGENT_LIVE_GATEWAY', '').strip().rstrip('/')
GATEWAY_USER = os.environ.get('UI_TEST_USERNAME', 'dev_user')
GATEWAY_PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')

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
                     algorithm=hashes.SHA256(), label=None))).decode('ascii')
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


def _ctx(permissions=('evaluation:read',)):
    return ToolInvocationContext(
        run_id='live-run', session_id='live', owner_id=1, tenant_id='default',
        step_id='step', permissions=tuple(permissions), idempotency_key='k')


def _execute(gateway, arguments, permissions=('evaluation:read',)):
    return gateway.execute(
        ToolCallRequest(tool_call_id='live', name='evaluation_query',
                        arguments=arguments), _ctx(permissions))


def _raw(path, token):
    request = urllib.request.Request(
        f'{GATEWAY}{path}', headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        return exc.code, None


def test_live_evaluation_query_10_domain_tasks(live):
    """卡面可测标准 1：该域 10 条任务在真实网关上全部走通。"""
    gateway, token = live
    status, listed = _raw('/api/v1/evaluation/dimensions?page=1&per_page=10',
                          token)
    assert status == 200 and listed['success'] is True
    items = listed['data']['items']
    if not items:  # pragma: no cover - 空库环境仍校验信封
        pytest.skip('库里没有维度，无法跑详情类任务')
    dim_id = items[0]['id']

    passed = []
    for task in fixtures.DOMAIN_TASKS:
        arguments = dict(task['arguments'])
        if arguments.get('action') == 'dimension':
            arguments['dim_id'] = dim_id
        result = _execute(gateway, arguments)
        assert result.ok, f"{task['name']} 失败：{result.error_code} {result.content}"
        payload = json.loads(result.content)
        assert payload['success'] is True, task['name']
        data = payload['data']
        for field in task['checks']:
            assert field in data, f"{task['name']} 缺少 {field}"
        passed.append(task['name'])
    assert len(passed) == 10
    print('\n10 条评估域任务全部通过：', '、'.join(passed))


def test_live_dimension_fields_match_gateway_schema(live):
    """卡面可测标准 2：维度字段与真实接口逐字段一致。"""
    from api_gateway.schemas.evaluation import DimensionItem

    gateway, token = live
    status, listed = _raw('/api/v1/evaluation/dimensions?page=1&per_page=5',
                          token)
    assert status == 200
    allowed = set(DimensionItem.model_fields)
    items = listed['data']['items']
    assert items
    for item in items:
        assert set(item) <= allowed, sorted(set(item) - allowed)
    # 评分口径核心字段在真实列表里必须能看到（None 字段会被 exclude_none 省略）
    first = items[0]
    for field in ('id', 'name', 'dimension_type', 'score_unit', 'result_type',
                  'weight', 'statistic_method', 'visibility'):
        assert field in first, field


def test_live_category_fields_match_gateway_schema(live):
    from api_gateway.schemas.evaluation import CategoryItem

    gateway, token = live
    status, listed = _raw('/api/v1/evaluation/categories', token)
    assert status == 200 and listed['success'] is True
    allowed = set(CategoryItem.model_fields)
    items = listed['data']['items']
    assert items
    for item in items:
        assert set(item) <= allowed, sorted(set(item) - allowed)


def test_live_dimension_list_params_are_search_and_category(live):
    """列表过滤参数：search / category_id 生效；旧的 keyword 不被识别。"""
    gateway, token = live
    status, all_items = _raw(
        '/api/v1/evaluation/dimensions?page=1&per_page=50', token)
    assert status == 200
    items = all_items['data']['items']
    if not items:  # pragma: no cover
        pytest.skip('库里没有维度')
    keyword = (items[0].get('keywords') or items[0]['name']).split(',')[0]
    if not keyword:
        pytest.skip('首个维度没有可用关键词')

    status, searched = _raw(
        f'/api/v1/evaluation/dimensions?search={urllib.parse.quote(keyword)}'
        '&page=1&per_page=50', token)
    assert status == 200
    assert searched['data']['total'] <= all_items['data']['total']
    for item in searched['data']['items']:
        haystack = ' '.join(str(item.get(k) or '') for k in
                            ('name', 'description', 'keywords'))
        assert keyword in haystack, (keyword, item['id'])

    status, old = _raw(
        f'/api/v1/evaluation/dimensions?keyword={urllib.parse.quote(keyword)}'
        '&page=1&per_page=50', token)
    assert status == 200
    # keyword 不是真实参数：网关忽略它，返回全量（与 total 一致）
    assert old['data']['total'] == all_items['data']['total']


def test_live_category_filter_narrows_result(live):
    gateway, token = live
    status, listed = _raw('/api/v1/evaluation/categories', token)
    assert status == 200
    categories = listed['data']['items']
    if not categories:  # pragma: no cover
        pytest.skip('库里没有分类')
    category_id = categories[0]['id']
    result = _execute(gateway, {'action': 'dimensions',
                                'category_id': category_id,
                                'page': 1, 'per_page': 50})
    assert result.ok, result.content
    data = json.loads(result.content)['data']
    for item in data['items']:
        assert item['category_id'] == category_id


def test_live_missing_dimension_is_plain_not_found(live):
    gateway, _ = live
    result = _execute(gateway, {'action': 'dimension', 'dim_id': 2000000000})
    assert not result.ok
    assert result.error_code == RESOURCE_NOT_FOUND
    assert '不存在或无权访问' in result.content


def test_live_permission_denied_without_rest(live):
    gateway, _ = live
    result = _execute(gateway, {'action': 'dimensions'},
                      permissions=('task:read',))
    assert result.error_code == PERMISSION_DENIED
