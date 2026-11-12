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

from agent_service.app import create_app
from agent_service.application.run_worker import InlineRunExecutor
from agent_service.infrastructure.wakeup import LocalRunWakeup
from agent_service.wiring import build_container
from tests.unit.int2451_agent_fakes import FakeLlm, make_engine, text_turn

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
        llm_factory=lambda: llm,
        wakeup=LocalRunWakeup(),
        executor_factory=lambda orch: InlineRunExecutor(orch),
        skills_root=str(skills_root),
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
