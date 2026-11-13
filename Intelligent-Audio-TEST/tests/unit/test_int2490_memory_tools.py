# -*- coding: utf-8 -*-
"""INT-2490 记忆工具：网关分派 / 审批占位 / 审计不落正文 / 会话注入。

验收锚点（卡面可测标准 1、3、4、5、6、8）：
- memory_search 走本地记忆服务（rg），tenant/owner 来自 run 身份；
- memory_write 生成待审批提案，审批前不落盘；Loop 侧审计参数脱敏；
- 会话开始注入偏好 + 项目规则摘要，细节靠 memory_search。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.memory_service import (
    MemoryService, MemoryServiceSettings,
)
from agent_service.application.run_worker import InlineRunExecutor
from agent_service.application.tool_gateway import (
    APPROVAL_REQUIRED, INVALID_ARGUMENTS, SharedToolGateway, TOOL_NOT_ENABLED,
)
from agent_service.domain.enums import MemorySection, ToolCallStatus
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import ToolInvocationContext
from agent_service.infrastructure.memory import (
    FileMemoryStore, MemoryStoreSettings, load_sensitive_rules,
)
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from agent_service.wiring import build_container
from tests.unit.int2451_agent_fakes import (
    FakeLlm, build_stack, text_turn, tool_turn,
)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_RULES_PATH = os.path.join(_REPO_ROOT, 'agent_service', 'config',
                           'memory_sensitive_rules.json')


class FakeRestClient:
    """记忆工具不回源 REST；这里只兜底其它工具。"""

    def __init__(self):
        self.calls = []

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': arguments, **kwargs})
        return RestResult(status=200, payload={'ok': True}, text='{"ok": true}')


def make_memory(tmp_path, *, inject_max_tokens=600):
    return MemoryService(
        FileMemoryStore(MemoryStoreSettings(
            root=str(tmp_path / 'memory'),
            sensitive_rules=load_sensitive_rules(_RULES_PATH))),
        settings=MemoryServiceSettings(inject_max_tokens=inject_max_tokens),
        audit_path=str(tmp_path / 'memory' / '.audit'))


def make_gateway(memory=None):
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=FakeRestClient(),
        credentials=RunCredentialRegistry(), memory=memory)


def ctx(owner_id=7, tenant='t1'):
    return ToolInvocationContext(
        run_id='run-1', session_id='s1', owner_id=owner_id,
        tenant_id=tenant, step_id='step1', permissions=('*',),
        idempotency_key='k')


def call(name, arguments):
    return ToolCallRequest(tool_call_id='call-1', name=name,
                          arguments=arguments)


def _seed(memory, *, owner_id=7, tenant='t1'):
    proposal = memory._store.create_proposal(  # noqa: SLF001 - 测试种子
        tenant_id=tenant, owner_id=owner_id,
        section=MemorySection.USER_PROFILE, content='偏好中文回答')
    memory._store.approve(  # noqa: SLF001
        tenant_id=tenant, owner_id=owner_id,
        approval_id=proposal.approval_id)
    rule = memory._store.create_proposal(  # noqa: SLF001
        tenant_id=tenant, owner_id=owner_id,
        section=MemorySection.PROJECT_MEMORY, content='项目规则：报告先核对任务 ID',
        project_id='alpha')
    memory._store.approve(  # noqa: SLF001
        tenant_id=tenant, owner_id=owner_id, approval_id=rule.approval_id)


def _stack(tmp_path, llm, memory):
    gateway = make_gateway(memory)
    return build_stack(
        tmp_path / 'agent.db', llm, gateway=gateway,
        executor_factory=lambda orch: InlineRunExecutor(orch),
        memory_service=memory)[0]


def _run(container, *, owner_id=7, tenant='t1', active_skill=None):
    session = container.run_service.create_session(
        owner_id=owner_id, tenant_id=tenant, title='t',
        active_skill=active_skill)
    run, created = container.run_service.create_run(
        session.id, owner_id=owner_id, tenant_id=tenant, message='你好',
        permissions=['*'], active_skill=active_skill)
    assert created
    container.executor.submit(run.id)
    return container.repositories['runs'].get(run.id)


def _tool_events(container, run_id):
    return [event for event in container.repositories['events'].list_after(
        run_id, 0, 10000) if event.type.value == 'tool_call']


# ---------------------------------------------------------------- 网关分派

def test_memory_search_returns_only_callers_hits(tmp_path):
    memory = make_memory(tmp_path)
    _seed(memory)
    gateway = make_gateway(memory)
    result = gateway.execute(
        call('memory_search', {'query': '偏好', 'scope': 'USER'}), ctx())
    assert result.ok and result.error_code == 'OK'
    payload = json.loads(result.content)
    assert payload['count'] == 1
    assert payload['items'][0]['path'] == 'user_profile.md'

    # 另一个用户 identity 查同一个服务：空结果，无「存在但无权」
    other = gateway.execute(
        call('memory_search', {'query': '偏好', 'scope': 'USER'}),
        ctx(owner_id=8))
    assert json.loads(other.content)['count'] == 0


def test_memory_write_creates_proposal_but_no_file(tmp_path):
    memory = make_memory(tmp_path)
    gateway = make_gateway(memory)
    result = gateway.execute(call('memory_write', {
        'section': 'USER_PROFILE', 'content': '记住：导出报告用 PDF',
        'reason': '用户显式要求'}), ctx())
    assert result.ok is False
    assert result.error_code == APPROVAL_REQUIRED
    payload = json.loads(result.content)
    assert payload['approval_id']
    assert payload['artifact_ref'] == (
        f"memory://proposals/{payload['approval_id']}")
    assert payload['status'] == 'PENDING'
    assert payload['path'] == 'user_profile.md'
    assert 'preview' not in payload
    target = (tmp_path / 'memory' / 'tenants' / 't1' / 'users' / '7'
              / 'user_profile.md')
    assert '导出报告用 PDF' not in target.read_text(encoding='utf-8')


def test_memory_write_rejects_sensitive_content(tmp_path):
    memory = make_memory(tmp_path)
    gateway = make_gateway(memory)
    result = gateway.execute(call('memory_write', {
        'section': 'USER_PROFILE', 'content': 'api_key: sk-abcdefghijklmnopqrst'}),
        ctx())
    assert result.ok is False
    assert result.error_code == INVALID_ARGUMENTS
    assert 'sk-abcdefghijklmnopqrst' not in result.content


def test_memory_tools_not_enabled_without_memory_service():
    gateway = make_gateway(None)
    for name, args in (
            ('memory_search', {'query': 'x', 'scope': 'USER'}),
            ('memory_write', {'section': 'USER_PROFILE', 'content': 'x'})):
        result = gateway.execute(call(name, args), ctx())
        assert result.error_code == TOOL_NOT_ENABLED, name
    assert gateway.proposal_capable('memory_write') is False


def test_proposal_capable_is_memory_write_only(tmp_path):
    gateway = make_gateway(make_memory(tmp_path))
    assert gateway.proposal_capable('memory_write') is True
    assert gateway.proposal_capable('task_run') is False
    assert gateway.proposal_capable('memory_search') is False


# ---------------------------------------------------------------- Loop 审计

def test_memory_write_in_loop_is_audited_without_body(tmp_path):
    memory = make_memory(tmp_path)
    llm = FakeLlm([
        tool_turn([ToolCallRequest('c1', 'memory_write', {
            'section': 'USER_PROFILE', 'content': '用户偏好：回答要简短'})]),
        text_turn('已生成待审批提案'),
    ])
    container = _stack(tmp_path, llm, memory)
    run = _run(container)
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.DENIED
    assert record.permission_decision == 'approval_required'
    assert record.result_code == APPROVAL_REQUIRED
    assert record.risk.value == 'WRITE'
    # 审计参数：content 脱敏，只剩 sha256 + 长度
    stored = record.arguments or {}
    assert stored['content']['redacted'] is True
    assert len(stored['content']['sha256']) == 64
    assert '回答要简短' not in json.dumps(stored, ensure_ascii=False)
    assert record.args_hash
    # 事件流同样不落正文
    for event in _tool_events(container, run.id):
        assert '回答要简短' not in json.dumps(event.payload, ensure_ascii=False)
    # 审批前无文件副作用
    profile = (tmp_path / 'memory' / 'tenants' / 't1' / 'users' / '7'
               / 'user_profile.md')
    assert '回答要简短' not in profile.read_text(encoding='utf-8')
    # 提案已生成，可在 REST 审批
    assert memory.list_proposals(tenant_id='t1', owner_id=7)


def test_memory_search_in_loop_hits_own_memory(tmp_path):
    memory = make_memory(tmp_path)
    _seed(memory)
    llm = FakeLlm([
        tool_turn([ToolCallRequest('c1', 'memory_search', {
            'query': '偏好', 'scope': 'USER'})]),
        text_turn('偏好中文回答'),
    ])
    container = _stack(tmp_path, llm, memory)
    run = _run(container)
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.COMPLETED
    assert record.result_code == 'OK'
    assert 'user_profile.md' in json.dumps(record.result, ensure_ascii=False)


# ---------------------------------------------------------------- 会话注入

def test_session_start_injects_preferences_and_project_rules(tmp_path):
    memory = make_memory(tmp_path)
    _seed(memory)
    llm = FakeLlm([text_turn('好的')])
    container = _stack(tmp_path, llm, memory)
    _run(container)
    system = llm.requests[0].messages[0]
    assert system.role == 'system'
    assert '长期记忆摘要' in system.content
    assert '偏好中文回答' in system.content
    assert '项目规则：报告先核对任务 ID' in system.content


def test_session_inject_skips_other_users_memory(tmp_path):
    memory = make_memory(tmp_path)
    _seed(memory, owner_id=99)
    llm = FakeLlm([text_turn('好的')])
    container = _stack(tmp_path, llm, memory)
    _run(container)
    system = llm.requests[0].messages[0]
    assert '偏好中文回答' not in (system.content or '')


def test_injection_does_not_exceed_configured_limit(tmp_path):
    memory = make_memory(tmp_path, inject_max_tokens=40)
    for index in range(60):
        _seed(memory, owner_id=7)
    llm = FakeLlm([text_turn('好的')])
    container = _stack(tmp_path, llm, memory)
    _run(container)
    from agent_service.domain.services.token_estimator import estimate_tokens
    content = llm.requests[0].messages[0].content or ''
    blocks = [part for part in content.split('\n\n')
              if part.startswith('## 长期记忆摘要')]
    assert blocks, content
    assert estimate_tokens(blocks[0]) <= 40


# ---------------------------------------------------------------- REST：审批占位

def test_memory_rest_approval_flow(tmp_path):
    from fastapi.testclient import TestClient

    from agent_service.app import create_app
    memory = make_memory(tmp_path)
    llm = FakeLlm([text_turn('x')])
    container = _stack(tmp_path, llm, memory)
    headers = {'X-User-Id': '7', 'X-Tenant-Id': 't1',
               'X-User-Permissions': '*'}
    proposal = memory.propose_write(
        tenant_id='t1', owner_id=7, section='USER_PROFILE',
        content='偏好中文回答')
    with TestClient(create_app(container=container)) as client:
        listing = client.get('/api/v1/agent/memory/proposals', headers=headers)
        assert listing.status_code == 200, listing.text
        assert proposal['approval_id'] in {
            item['approval_id'] for item in listing.json()['items']}

        approved = client.post(
            f"/api/v1/agent/memory/proposals/{proposal['approval_id']}/approve",
            headers=headers)
        assert approved.status_code == 200, approved.text
        assert approved.json()['status'] == 'APPROVED'

        meta = client.get('/api/v1/agent/memory/metadata', headers=headers)
        assert meta.status_code == 200, meta.text
        assert meta.json()['user_profile_count'] == 1

        # 归属校验：别人看不到 / 批不了
        other = dict(headers, **{'X-User-Id': '8'})
        assert client.get('/api/v1/agent/memory/proposals',
                          headers=other).json()['items'] == []
        not_found = client.post(
            f"/api/v1/agent/memory/proposals/{proposal['approval_id']}/approve",
            headers=other)
        assert not_found.status_code == 404

        # break-glass：无专用权限 → 403（fail-closed）
        denied = client.get('/api/v1/agent/memory/break-glass',
                            params={'path': 'user_profile.md', 'owner_id': 7},
                            headers={'X-User-Id': '9', 'X-Tenant-Id': 't1',
                                     'X-User-Permissions': 'task:read'})
        assert denied.status_code == 403

        allowed = client.get('/api/v1/agent/memory/break-glass',
                             params={'path': 'user_profile.md', 'owner_id': 7},
                             headers=headers)
        assert allowed.status_code == 200, allowed.text
        assert '偏好中文回答' in allowed.json()['content']



def test_memory_tools_survive_skill_narrowing(tmp_path):
    """Harness 级常驻：激活业务 Skill 时记忆工具仍要装配（否则用不了记忆）。"""
    memory = make_memory(tmp_path)
    llm = FakeLlm([text_turn('好的')])
    container = _stack(tmp_path, llm, memory)
    _run(container, active_skill='platform-reference')
    names = [tool['function']['name'] for tool in llm.requests[0].tools]
    assert 'memory_search' in names and 'memory_write' in names
    assert 'platform_contract' in names
