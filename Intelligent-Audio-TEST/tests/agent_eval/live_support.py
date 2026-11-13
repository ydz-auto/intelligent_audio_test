# -*- coding: utf-8 -*-
"""实测网关共用夹具（INT-2467；只在显式设置 ``AGENT_LIVE_GATEWAY`` 时运行）。

与 ``tests/agent_eval/domains/*/test_*_live_contract.py`` 同一登录口径：
GET 公钥 → RSA-OAEP 加密密码 → form 登录，拿 Bearer token 交给
``SharedToolGateway`` 的 ``RestToolClient``（与生产执行路径一致）。
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

GATEWAY = os.environ.get('AGENT_LIVE_GATEWAY', '').strip().rstrip('/')
GATEWAY_USER = os.environ.get('UI_TEST_USERNAME', 'dev_user')
GATEWAY_PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')

#: 实测数据前缀（卡面执行约定：真实库栈只用「接线测试_」前缀，并在 run 结束前清理）
LIVE_PREFIX = '接线测试_'


def available() -> bool:
    return bool(GATEWAY)


def login() -> str:
    """按 INT-147 契约登录，返回 access_token。"""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    with urllib.request.urlopen(
            f'{GATEWAY}/api/v1/auth/encryption-key', timeout=20) as resp:
        key = json.loads(resp.read().decode('utf-8'))
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
    with urllib.request.urlopen(request, timeout=20) as resp:
        payload = json.loads(resp.read().decode('utf-8'))
    token = payload.get('access_token')
    assert token, f'登录失败：{str(payload)[:200]}'
    return token


def raw(method: str, path: str, token: str, body=None):
    """直接调网关 REST（用于取证 / 清理）；返回 (status, json|None)。"""
    data = None
    headers = {'Authorization': f'Bearer {token}'}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(
        f'{GATEWAY}{path}', data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode('utf-8', 'replace')
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, None


def gateway_client(token: str):
    """生产同款 ToolGateway（共享注册表 + 真实 REST 客户端）。"""
    from agent_service.application.tool_gateway import SharedToolGateway
    from agent_service.infrastructure.tools.registry_bridge import (
        RestToolClient, RunCredentialRegistry, SharedToolRegistryBridge,
    )

    credentials = RunCredentialRegistry()
    credentials.put('live-run', f'Bearer {token}')
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=RestToolClient(GATEWAY),
        credentials=credentials)


def approved_ctx(*, permissions, idempotency_key='live-k'):
    """「审批已通过」的执行上下文（与 Loop 执行写操作的上下文同形）。"""
    from agent_service.domain.enums import ToolRisk
    from agent_service.domain.ports.tool_gateway import (
        ToolApproval, ToolInvocationContext,
    )

    return ToolInvocationContext(
        run_id='live-run', session_id='live', owner_id=1, tenant_id='default',
        step_id='step', permissions=tuple(permissions),
        idempotency_key=idempotency_key,
        approval=ToolApproval(
            approval_id='live-approval', risk=ToolRisk.DESTRUCTIVE,
            proposal={'tool': 'live'}),
    )


__all__ = ['GATEWAY', 'LIVE_PREFIX', 'approved_ctx', 'available', 'gateway_client',
           'login', 'raw']
