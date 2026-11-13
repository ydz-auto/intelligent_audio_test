# -*- coding: utf-8 -*-
"""INT-2452 Skill 的 REST 契约与 Loop 注入。

验收锚点（卡面可测标准 2、3）：
2. GET /api/v1/agent/skills 对低权限用户不返回 permissions 不满足的 Skill；
3. 会话激活 platform-reference 后模型上下文包含其正文；未激活时不包含。
另验证：未知 / 无权 Skill 激活被拒；切换 Skill 落库并只注入对应 L2。
"""
import os
import shutil

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi.testclient import TestClient

import agent_service.app as agent_app
from agent_service.app import create_app
from agent_service.application.run_worker import InlineRunExecutor
from agent_service.infrastructure.wakeup import LocalRunWakeup
from agent_service.wiring import build_container
from tests.unit.int2451_agent_fakes import (
    FakeLlm, FakeProviderResolver, TEST_MASTER_KEY, make_engine, text_turn,
)
from agent_service.infrastructure.llm.credential_store import CredentialStore

PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
SKILLS_ROOT = os.path.join(PROJECT_ROOT, 'skills')

OWNER = {'X-User-Id': '7', 'X-Tenant-Id': 't1'}
LOW_PERM = dict(OWNER, **{'X-User-Permissions': 'task:read'})
ADMIN = dict(OWNER, **{'X-User-Permissions': '*'})

# platform-reference 正文里的独占字符串（L1 只有 description，不含这些）
BODY_MARKER = '`/agent/skill` 与 `/agent/skills` 不是一回事'

_RESTRICTED = """---
name: restricted-demo
description: 仅 report:read 用户可见的测试 Skill
version: 1.0.0
owner: test-team
allowed-tools: []
permissions:
  - report:read
budgets:
  maxToolCalls: 5
  maxTokens: 1000
---

# restricted-demo

RESTRICTED_BODY_MARKER

## Gotchas

- 无。

## 验收

- 无。
"""


@pytest.fixture()
def skills_root(tmp_path):
    """真实 platform-reference + 一个受限 Skill。"""
    root = tmp_path / 'skills'
    root.mkdir()
    shutil.copytree(os.path.join(SKILLS_ROOT, 'platform-reference'),
                    root / 'platform-reference')
    restricted = root / 'restricted-demo'
    restricted.mkdir()
    (restricted / 'SKILL.md').write_text(_RESTRICTED, encoding='utf-8')
    return root


class _Stack:
    def __init__(self, client, container, llm):
        self.client = client
        self.container = container
        self.llm = llm

    @property
    def system(self) -> str:
        """最近一次模型调用的 system 内容。"""
        return self.llm.requests[-1].messages[0].content


def _stack(tmp_path, skills_root) -> _Stack:
    engine, session_factory = make_engine(tmp_path / 'api.db')
    llm = FakeLlm([text_turn('好的', '收到')])
    container = build_container(
        session_factory,
        provider_resolver=FakeProviderResolver(llm),
        wakeup=LocalRunWakeup(),
        executor_factory=lambda orch: InlineRunExecutor(orch),
        skills_root=str(skills_root),
        credential_store=CredentialStore.from_secret(TEST_MASTER_KEY),
    )
    return _Stack(TestClient(create_app(container=container)), container, llm)


def _session(client, headers=OWNER, **payload):
    return client.post('/api/v1/agent/sessions',
                       json={'title': 't', **payload}, headers=headers)


def _run(client, session_id, headers=OWNER, **payload):
    return client.post(f'/api/v1/agent/sessions/{session_id}/runs',
                       json={'message': '你好', **payload}, headers=headers)


# ---------------------------------------------------------------- GET /skills

def test_skills_endpoint_returns_open_skill_to_everyone(tmp_path, skills_root):
    stack = _stack(tmp_path, skills_root)
    with stack.client as client:
        resp = client.get('/api/v1/agent/skills', headers=OWNER)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        names = [item['name'] for item in body['items']]
        assert 'platform-reference' in names

        item = next(i for i in body['items'] if i['name'] == 'platform-reference')
        assert item['version'] and item['owner']
        assert item['allowed_tools'] == ['platform_contract', 'tool_search']
        assert body['l1_tokens'] > 0
        assert body['l1_tokens'] <= body['l1_budget_tokens']


def test_low_permission_user_does_not_see_restricted_skill(tmp_path,
                                                          skills_root):
    stack = _stack(tmp_path, skills_root)
    with stack.client as client:
        low = client.get('/api/v1/agent/skills', headers=LOW_PERM)
        assert low.status_code == 200
        assert 'restricted-demo' not in [i['name'] for i in low.json()['items']]

        admin = client.get('/api/v1/agent/skills', headers=ADMIN)
        names = [i['name'] for i in admin.json()['items']]
        assert 'restricted-demo' in names and 'platform-reference' in names
        assert low.json()['l1_tokens'] < admin.json()['l1_tokens']


def test_skills_endpoint_exposes_load_summary(tmp_path, skills_root):
    """INT-2506：/skills 带装载总数与问题摘要，正常态问题数为 0。"""
    stack = _stack(tmp_path, skills_root)
    with stack.client as client:
        body = client.get('/api/v1/agent/skills', headers=OWNER).json()
        assert body['skills_count'] >= 2
        assert body['issues_count'] == 0
        assert body['issues'] == []
        assert body['l1_tokens'] > 0


def test_skills_root_missing_fails_startup_with_reason_code(tmp_path):
    """INT-2506 + INT-2529：根目录不存在时带原因码启动失败，不再 200 全绿。

    合并契约（INT-2529）：零 Skill 是部署级故障，装配阶段直接抛
    ``SkillValidationError``，进程不进入可服务状态 —— 因此 /skills 与
    /health 在这个场景下本来就不该有响应可查。
    """
    from agent_service.domain.exceptions import SkillValidationError

    with pytest.raises(SkillValidationError) as exc:
        _stack(tmp_path, tmp_path / 'missing-skills')
    assert [i.code.value for i in exc.value.issues] == [
        'SKILLS_ROOT_MISSING', 'EMPTY_SKILLS_ROOT']


def test_skills_endpoint_surfaces_directory_level_issue(tmp_path):
    """INT-2506：有 Skill 能装载时，/skills 仍能看出目录级原因码（不被 200 抹平）。"""
    root = tmp_path / 'skills'
    root.mkdir()
    shutil.copytree(os.path.join(SKILLS_ROOT, 'platform-reference'),
                    root / 'platform-reference')
    os.makedirs(str(root / 'no-skill-md'))
    stack = _stack(tmp_path, root)
    with stack.client as client:
        body = client.get('/api/v1/agent/skills', headers=OWNER).json()
        assert body['skills_count'] == 1
        assert body['issues_count'] == 1
        issue = body['issues'][0]
        assert issue['code'] == 'SKILL_FILE_MISSING'
        assert issue['severity'] == 'ERROR'
        assert issue['skill'] == '' and issue['path']


def test_health_reports_skill_load_summary(tmp_path, skills_root, monkeypatch):
    """INT-2506：/health 能看到装载了几个 Skill、几个问题、问题码。

    INT-2456 起 /health 改为真实探测 DB / Redis（DB 不可用 → 503 +
    status=error）。本用例栈用 ``make_engine`` 建临时 sqlite，
    ``shared.models.database.get_engine()`` 未初始化，真实探测必然失败；
    这里按合并后的契约把两个探测桩为可用，断言 HTTP 状态与
    ``checks.database`` 结论一致，再核对装载摘要。
    """
    monkeypatch.setattr(agent_app, '_probe_database', lambda: (True, ''))
    monkeypatch.setattr(agent_app, '_probe_redis', lambda: (True, ''))
    stack = _stack(tmp_path, skills_root)
    with stack.client as client:
        resp = client.get('/health')
        assert resp.status_code == 200
        health = resp.json()
        assert health['status'] == 'ok'
        assert health['checks']['database']['status'] == 'ok'
        assert health['skills']['loaded'] >= 2
        assert health['skills']['issues'] == 0
        assert health['skills']['issue_codes'] == []


def test_health_surfaces_per_skill_issue_codes(tmp_path):
    """INT-2506：可装载 Skill 之外仍有目录级问题时，/health 仍与正常态有差别。"""
    work = tmp_path / 'degraded'
    work.mkdir()
    skills = work / 'skills'
    skills.mkdir()
    shutil.copytree(os.path.join(SKILLS_ROOT, 'platform-reference'),
                    skills / 'platform-reference')
    os.makedirs(str(skills / 'no-skill-md'))
    stack = _stack(work, skills)
    with stack.client as client:
        health = client.get('/health').json()
        assert health['skills']['loaded'] == 1
        assert health['skills']['issues'] == 1
        assert health['skills']['issue_codes'] == ['SKILL_FILE_MISSING']


# ---------------------------------------------------------------- activation

def test_unknown_skill_activation_is_rejected(tmp_path, skills_root):
    stack = _stack(tmp_path, skills_root)
    with stack.client as client:
        assert _session(client, active_skill='no-such-skill').status_code == 400


def test_activation_of_restricted_skill_requires_permission(tmp_path,
                                                            skills_root):
    stack = _stack(tmp_path, skills_root)
    with stack.client as client:
        assert _session(client, headers=LOW_PERM,
                        active_skill='restricted-demo').status_code == 400
        assert _session(client, headers=ADMIN,
                        active_skill='restricted-demo').status_code == 201


def test_active_skill_body_injected_only_when_active(tmp_path, skills_root):
    stack = _stack(tmp_path, skills_root)
    with stack.client as client:
        plain = _session(client)
        assert plain.status_code == 201
        assert _run(client, plain.json()['id']).status_code == 201
        system = stack.system
        assert 'platform-reference' in system      # L1 常驻
        assert BODY_MARKER not in system           # 未激活 → 无 L2

        active = _session(client, active_skill='platform-reference')
        assert active.status_code == 201
        assert active.json()['active_skill'] == 'platform-reference'
        assert _run(client, active.json()['id']).status_code == 201
        system = stack.system
        assert 'platform-reference' in system
        assert BODY_MARKER in system               # 激活 → 注入 L2


def test_switching_skill_persists_and_injects_that_body(tmp_path, skills_root):
    stack = _stack(tmp_path, skills_root)
    with stack.client as client:
        session_id = _session(client).json()['id']
        assert _run(client, session_id,
                    active_skill='platform-reference').status_code == 201

        detail = client.get(f'/api/v1/agent/sessions/{session_id}',
                            headers=OWNER).json()
        assert detail['session']['active_skill'] == 'platform-reference'
        assert BODY_MARKER in stack.system

        # 后续 run 未显式切换：沿用会话激活值
        assert _run(client, session_id).status_code == 201
        assert BODY_MARKER in stack.system


def test_permissions_revoked_mid_session_drops_l2(tmp_path, skills_root):
    """会话记录里残留的激活 Skill 在权限收紧后不再注入正文。"""
    stack = _stack(tmp_path, skills_root)
    with stack.client as client:
        session_id = _session(client, headers=ADMIN,
                              active_skill='restricted-demo').json()['id']
        assert _run(client, session_id, headers=LOW_PERM).status_code == 201
        system = stack.system
        assert 'RESTRICTED_BODY_MARKER' not in system
        assert 'restricted-demo' not in system
