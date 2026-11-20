# -*- coding: utf-8 -*-
"""INT-2549 自定义 Skill 测试夹具（非测试文件，pytest 不收集）。

复用 INT-2451 的内存库 stack：``build_container`` 已装配 SkillService /
AgentSkill 仓储；这里补齐资源存储替身、golden tasks 替身与草稿构造器。
"""
import os
from typing import Dict, Iterable, List, Sequence

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from agent_service.application.run_worker import InlineRunExecutor
from agent_service.application.skill_service import (
    SkillDraftPayload, SkillSettings,
)
from agent_service.domain.ports.golden_tasks import GoldenTask, GoldenTaskProvider
from agent_service.domain.ports.skill_repository import SkillResourceStore
from agent_service.domain.ports.tool_gateway import ToolDescriptor
from agent_service.domain.enums import SandboxTier, ToolRisk
from tests.unit.int2451_agent_fakes import (
    FakeLlm, FakeToolGateway, build_stack, text_turn,
)

OWNER_ID = 7
TENANT_ID = 't1'
OTHER_USER_ID = 8

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
SKILLS_ROOT = os.path.join(PROJECT_ROOT, 'skills')


class InMemoryResourceStore(SkillResourceStore):
    def __init__(self):
        self.items: Dict[str, bytes] = {}

    def put(self, key: str, data: bytes,
            content_type: str = 'application/octet-stream') -> str:
        self.items[key] = data
        return key

    def get(self, key: str) -> bytes:
        if key not in self.items:
            raise KeyError(key)
        return self.items[key]


class StaticGoldenTasks(GoldenTaskProvider):
    def __init__(self, mapping=None):
        self._mapping = {
            name: [GoldenTask(task_id=f'{name}-{index}', skill=name,
                              query=query)
                   for index, query in enumerate(queries)]
            for name, queries in (mapping or {}).items()
        }

    def tasks_for(self, skill_name: str) -> Sequence[GoldenTask]:
        return tuple(self._mapping.get(skill_name, ()))


def demo_tools() -> List[ToolDescriptor]:
    return [
        ToolDescriptor(name='task_query', description='查询任务',
                       parameters={}, risk=ToolRisk.READ,
                       sandbox_tier=SandboxTier.T0_NONE),
        ToolDescriptor(name='tool_search', description='检索工具',
                       parameters={}, risk=ToolRisk.READ,
                       sandbox_tier=SandboxTier.T0_NONE),
    ]


def build_skill_stack(tmp_path, *, gateway=None, golden=None,
                      settings: SkillSettings = None, llm=None,
                      name='skill.db', **kwargs):
    """返回 (container, resource_store)。"""
    store = InMemoryResourceStore()
    container, engine, session_factory = build_stack(
        tmp_path / name,
        llm or FakeLlm([text_turn('ok')]),
        gateway=gateway or FakeToolGateway(tools=demo_tools()),
        executor_factory=lambda orch: InlineRunExecutor(orch),
        skills_root=SKILLS_ROOT,
        skill_resource_store=store,
        golden_tasks=golden or StaticGoldenTasks(),
        skill_settings=settings,
        **kwargs)
    return container, store


DEMO_BODY = """# demo

演示内容。

## Gotchas

- 无。

## 验收

- 无。
"""


def demo_body(marker: str = '演示内容。', extra: str = '') -> str:
    return f"""# demo

{marker}

## Gotchas

- 无。
{extra}
## 验收

- 无。
"""


def draft_payload(name: str = 'demo-skill', *,
                  description: str = '演示 Skill。触发词：演示、样例',
                  body: str = None,
                  resources: Dict[str, str] = None,
                  permissions: Iterable[str] = None,
                  allowed_tools: Iterable[str] = None,
                  extra_frontmatter: Dict = None) -> SkillDraftPayload:
    frontmatter = {}
    if permissions is not None:
        frontmatter['permissions'] = list(permissions)
    if allowed_tools is not None:
        frontmatter['allowed-tools'] = list(allowed_tools)
    frontmatter.update(extra_frontmatter or {})
    return SkillDraftPayload(
        name=name, description=description, body=body or demo_body(),
        frontmatter=frontmatter, resources=dict(resources or {}))


def create_draft(service, payload=None, *, owner_id=OWNER_ID,
                 tenant_id=TENANT_ID, permissions=('*',)):
    return service.create(payload or draft_payload(), owner_id=owner_id,
                          tenant_id=tenant_id, permissions=list(permissions),
                          created_by=owner_id)


def create_tenant_skill(service, payload=None, *, owner_id=OWNER_ID,
                        tenant_id=TENANT_ID, permissions=('*',),
                        is_admin=True):
    """TENANT 级共享 Skill 草稿（INT-2551；默认用管理员身份创建）。"""
    from agent_service.domain.enums import SkillScope
    return service.create(
        payload or draft_payload(), owner_id=owner_id, tenant_id=tenant_id,
        permissions=list(permissions), created_by=owner_id,
        scope=SkillScope.TENANT, is_admin=is_admin)


# INT-2551：能通过 ≥3 条 golden tasks 门槛的触发词组合
GATE_GOLDEN = {
    'demo-skill': ['演示 一下', '样例 给我', '帮我看样例'],
    'demo-skill-2': ['演示 一下', '样例 给我', '帮我看样例'],
}


def issues_codes(exc) -> List[str]:
    return [issue.code.value for issue in getattr(exc, 'issues', ())]


__all__ = [
    'DEMO_BODY', 'GATE_GOLDEN', 'InMemoryResourceStore', 'OTHER_USER_ID',
    'OWNER_ID', 'PROJECT_ROOT', 'SKILLS_ROOT', 'StaticGoldenTasks',
    'TENANT_ID', 'build_skill_stack', 'create_draft', 'create_tenant_skill',
    'demo_body', 'demo_tools', 'draft_payload', 'issues_codes',
]
