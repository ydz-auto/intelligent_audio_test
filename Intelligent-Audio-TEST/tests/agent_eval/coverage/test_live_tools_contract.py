# -*- coding: utf-8 -*-
"""INT-2465 真实 docker 网关实测：tools/list 逐项一致 + 长尾读取可调用。

默认跳过；显式给网关地址时运行（实测命令）：

    AGENT_LIVE_GATEWAY=http://localhost:15000 python -m pytest \
        tests/agent_eval/coverage/test_live_tools_contract.py -s

前置：docker 栈已起（网关 15000），栈上存在 dev_user / dev_password。
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

from shared.agent_tools import mcp_registry

GATEWAY = os.environ.get('AGENT_LIVE_GATEWAY', '').strip().rstrip('/')
GATEWAY_USER = os.environ.get('UI_TEST_USERNAME', 'dev_user')
GATEWAY_PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')

pytestmark = pytest.mark.skipif(
    not GATEWAY, reason='未设置 AGENT_LIVE_GATEWAY，跳过真实网关实测')


def _get_json(url):
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _login():
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    key = _get_json(f'{GATEWAY}/api/v1/auth/encryption-key')
    assert key.get('enabled') is True
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


def _rpc(token, method, params=None, rpc_id=1):
    body = json.dumps({
        'jsonrpc': '2.0', 'id': rpc_id, 'method': method,
        'params': params or {},
    }, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(
        f'{GATEWAY}/api/v1/mcp', data=body,
        headers={'Content-Type': 'application/json',
                 'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(request, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


@pytest.fixture(scope='module')
def token():
    try:
        payload = _login()
    except (urllib.error.URLError, OSError) as exc:  # pragma: no cover
        pytest.skip(f'网关登录失败：{exc}')
    return payload.get('access_token') or payload.get('token')


def test_live_tools_list_matches_shared_registry(token):
    result = _rpc(token, 'tools/list')
    listed = result['result']['tools']
    assert len(listed) == 207
    assert listed == mcp_registry.list_tools(), '真实网关 tools/list 与共享注册表不一致'


@pytest.mark.parametrize('tool,args', [
    ('task_list', {'page': 1, 'per_page': 1}),
    ('device_list', {'page': 1, 'per_page': 1}),
    ('algorithm_form_schema', {'algo_type': 'voice_llm'}),
])
def test_long_tail_read_tools_are_callable(token, tool, args):
    result = _rpc(token, 'tools/call', {'name': tool, 'arguments': args})
    content = result['result']['content'][0]
    payload = json.loads(content['text'])
    assert result['result'].get('isError') is not True, payload
    assert isinstance(payload, (dict, list))
    tool_def = mcp_registry.get_tool(tool)
    assert tool_def['method'] == 'GET'
