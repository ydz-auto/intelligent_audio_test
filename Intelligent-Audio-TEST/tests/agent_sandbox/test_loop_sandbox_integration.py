# -*- coding: utf-8 -*-
"""INT-2495 真实 Docker 端到端：唯一 Loop 触发 T1 脚本。

覆盖卡面验收标准 1 与 2 的真实容器路径：

1. 正常脚本 → run ``SUCCEEDED``，``/work`` 产物清单回灌 ``tool_result``；
2. 超时脚本 → run ``BUDGET_EXCEEDED``（原因码 ``TIMEOUT``）；
3. 非零退出脚本 → run ``FAILED``（原因码 ``EXIT_CODE_NONZERO``）。

无 Docker / 缺沙箱镜像时整文件 skip（原因由 ``docker_available`` 给出）。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from pathlib import Path

import pytest

from agent_service.application.run_worker import InlineRunExecutor
from agent_service.application.sandbox_dispatch import (
    SandboxScriptDispatcher, SkillScripts,
)
from agent_service.application.sandbox_runner import (
    ContainerLimits, SandboxArtifactPolicy, SandboxRunner,
)
from agent_service.domain.enums import RunStatus, SandboxTier, ToolRisk
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import ToolDescriptor
from agent_service.infrastructure.llm.credential_store import CredentialStore
from agent_service.infrastructure.wakeup import LocalRunWakeup
from agent_service.wiring import build_container
from tests.agent_sandbox._sandbox_support import (
    RecordingDockerExecutor, docker_cli,
)
from tests.unit.int2451_agent_fakes import (
    TEST_MASTER_KEY, FakeLlm, FakeProviderResolver, FakeToolGateway, events_of,
    make_engine, new_session, text_turn, tool_turn,
)

pytestmark = pytest.mark.docker_required

TIMEOUT_SECONDS = 3
SCRIPT_TOOL = 'script_tool'
SCRIPT_PATH = 'scripts/main.py'


def _container(tmp_path: Path, llm, dispatcher):
    engine, session_factory = make_engine(tmp_path / 'int2495_e2e.db')
    container = build_container(
        session_factory,
        provider_resolver=FakeProviderResolver(llm),
        tool_gateway=FakeToolGateway(tools=[ToolDescriptor(
            name=SCRIPT_TOOL, description='T1 脚本', parameters={},
            risk=ToolRisk.READ, sandbox_tier=SandboxTier.T1_TRUSTED_SCRIPT)]),
        wakeup=LocalRunWakeup(),
        executor_factory=InlineRunExecutor,
        credential_store=CredentialStore.from_secret(TEST_MASTER_KEY),
        sandbox=dispatcher,
    )
    return container


def _dispatcher(skill_root: Path, executor) -> SandboxScriptDispatcher:
    runner = SandboxRunner(
        executor, SandboxArtifactPolicy(),
        work_root=skill_root.parent / 'workroot')
    locate = lambda name: SkillScripts(  # noqa: E731
        skill_name='demo', root=skill_root, scripts=(SCRIPT_PATH,))
    return SandboxScriptDispatcher(runner, locate)


def _run(container, message='执行脚本'):
    session = new_session(container)
    run, created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message=message)
    assert created
    container.executor.submit(run.id)
    return run


def _finished(container, run_id) -> dict:
    rows = [e for e in events_of(container, run_id)
            if e.type.value == 'run_finished']
    assert len(rows) == 1
    return rows[0].payload


def _tool_message(llm) -> dict:
    message = [m for m in llm.requests[-1].messages if m.role == 'tool'][0]
    return json.loads(message.content)


def test_loop_runs_t1_script_in_real_container(make_skill, docker_available):
    skill_root = make_skill({SCRIPT_PATH.split('/')[-1]: (
        'import json, pathlib\n'
        'pathlib.Path("/work/result.json").write_text(json.dumps({"ok": 1}))\n'
        'print(json.dumps({"hello": "sandbox"}))\n')})
    executor = RecordingDockerExecutor(limits=ContainerLimits(
        timeout_seconds=TIMEOUT_SECONDS))
    call = ToolCallRequest('call_e2e', SCRIPT_TOOL,
                           {'skill': 'demo', 'script': SCRIPT_PATH})
    llm = FakeLlm([tool_turn([call]), text_turn('完成')])
    container = _container(skill_root.parent.parent, llm,
                           _dispatcher(skill_root, executor))
    try:
        run = _run(container)
        stored = container.repositories['runs'].get(run.id)
        assert stored.status is RunStatus.SUCCEEDED
        payload = _tool_message(llm)
        assert payload['outcome'] == 'SUCCEEDED'
        assert payload['skill'] == 'demo'
        assert [item['path'] for item in payload['artifacts']] == ['result.json']
        assert json.loads(payload['stdout']) == {'hello': 'sandbox'}
    finally:
        container.shutdown()
    # 容器用完即毁
    for name in executor.container_names:
        assert docker_cli('container', 'inspect', name).returncode != 0


def test_timeout_script_finishes_run_as_budget_exceeded(make_skill, docker_available):
    skill_root = make_skill({SCRIPT_PATH.split('/')[-1]: (
        'import time\ntime.sleep(60)\n')})
    executor = RecordingDockerExecutor(limits=ContainerLimits(
        timeout_seconds=TIMEOUT_SECONDS))
    call = ToolCallRequest('call_timeout', SCRIPT_TOOL,
                           {'skill': 'demo', 'script': SCRIPT_PATH})
    llm = FakeLlm([tool_turn([call]), text_turn('不应到达')])
    container = _container(skill_root.parent.parent, llm,
                           _dispatcher(skill_root, executor))
    try:
        run = _run(container)
        stored = container.repositories['runs'].get(run.id)
        assert stored.status is RunStatus.BUDGET_EXCEEDED
        finished = _finished(container, run.id)
        assert finished['reason'] == 'TIMEOUT'
        assert finished['reason_code'] == 'TIMEOUT'
        codes = [e.payload.get('code') for e in events_of(container, run.id)
                 if e.type.value == 'error']
        assert 'TIMEOUT' in codes
        assert len(llm.requests) == 1
    finally:
        container.shutdown()
    for name in executor.container_names:
        assert docker_cli('container', 'inspect', name).returncode != 0


def test_nonzero_script_finishes_run_as_failed(make_skill, docker_available):
    skill_root = make_skill({SCRIPT_PATH.split('/')[-1]: (
        'import sys\nsys.exit(3)\n')})
    executor = RecordingDockerExecutor(limits=ContainerLimits(
        timeout_seconds=TIMEOUT_SECONDS))
    call = ToolCallRequest('call_fail', SCRIPT_TOOL,
                           {'skill': 'demo', 'script': SCRIPT_PATH})
    llm = FakeLlm([tool_turn([call]), text_turn('不应到达')])
    container = _container(skill_root.parent.parent, llm,
                           _dispatcher(skill_root, executor))
    try:
        run = _run(container)
        stored = container.repositories['runs'].get(run.id)
        assert stored.status is RunStatus.FAILED
        finished = _finished(container, run.id)
        assert finished['reason'] == 'EXIT_CODE_NONZERO'
        call_row = container.repositories['tool_calls'].find(run.id, 'call_fail')
        assert call_row.result_code == 'EXIT_CODE_NONZERO'
        assert len(llm.requests) == 1
    finally:
        container.shutdown()
    for name in executor.container_names:
        assert docker_cli('container', 'inspect', name).returncode != 0
