# -*- coding: utf-8 -*-
"""T1 沙箱的 runner/sidecar HTTP 通道（INT-2455）——真实 Docker。

验证负责人红线：``agent_service`` 侧**不接触 Docker**，只把容器规格 POST 给
独立 runner；两条通道行为一致（同一份加固参数、同样的产物回收）。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from agent_service.application.sandbox_runner import (
    ContainerLimits,
    SandboxArtifactPolicy,
    SandboxFailureReason,
    SandboxOutcome,
    SandboxRequest,
    SandboxRunner,
    SandboxConfigurationError,
)
from agent_service.infrastructure.sandbox.docker_runner import (
    DockerRunnerConfig,
    DockerRunnerMode,
    HttpRunnerDockerExecutor,
    build_sandbox_executor,
)
from agent_service.infrastructure.sandbox.runner_service import (
    RUNNER_HEALTH_PATH,
    RUNNER_TOKEN_ENV,
    SandboxRunnerServer,
)

from tests.agent_sandbox._sandbox_support import RecordingDockerExecutor

pytestmark = pytest.mark.docker_required

TEST_TOKEN = 'it-token-' + uuid.uuid4().hex[:12]

HELLO_SCRIPT = r'''
import json, os, pathlib, sys
pathlib.Path('/work/out.txt').write_text('via-runner', encoding='utf-8')
print(json.dumps({'uid': os.getuid(), 'argv': sys.argv[1:]}))
'''


@pytest.fixture
def runner_server(recorded_executor: RecordingDockerExecutor):
    server = SandboxRunnerServer(
        executor=recorded_executor,
        token=TEST_TOKEN,
        bind_host='127.0.0.1',
        port=0,
    ).start_background()
    yield server
    server.stop()


def _runner(server: SandboxRunnerServer, token: str = TEST_TOKEN) -> SandboxRunner:
    executor = HttpRunnerDockerExecutor(
        server.url, limits=ContainerLimits(timeout_seconds=30), runner_token=token
    )
    return SandboxRunner(executor, artifact_policy=SandboxArtifactPolicy())


def test_runner_service_refuses_to_start_without_token() -> None:
    with pytest.raises(SandboxConfigurationError):
        SandboxRunnerServer(
            executor=RecordingDockerExecutor(), token='', bind_host='127.0.0.1', port=0
        )


def test_health_endpoint(runner_server: SandboxRunnerServer) -> None:
    from urllib import request as urlrequest

    with urlrequest.urlopen(runner_server.url + RUNNER_HEALTH_PATH, timeout=10) as response:
        payload = json.loads(response.read().decode('utf-8'))
    assert payload['status'] == 'ok'


def test_sandbox_runs_through_sidecar(runner_server, make_skill) -> None:
    skill = make_skill({'main.py': HELLO_SCRIPT})
    result = _runner(runner_server).run_trusted_script(
        SandboxRequest(skill_name='demo', skill_root=skill, script='scripts/main.py', args=('a', 'b'))
    )
    assert result.outcome is SandboxOutcome.SUCCEEDED, result.detail
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload['uid'] != 0
    assert payload['argv'] == ['a', 'b']
    assert [a.relative_path for a in result.artifacts] == ['out.txt']
    assert result.artifacts[0].size_bytes == len('via-runner')


def test_wrong_token_is_rejected(runner_server, make_skill) -> None:
    skill = make_skill({'main.py': HELLO_SCRIPT})
    result = _runner(runner_server, token='wrong').run_trusted_script(
        SandboxRequest(skill_name='demo', skill_root=skill, script='scripts/main.py')
    )
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.RUNNER_ERROR
    assert '401' in result.detail


def test_sidecar_rejects_credential_env(runner_server, make_skill) -> None:
    """即使调用方绕过应用层校验，sidecar 也必须拒绝带凭据的容器规格。"""
    from urllib import error as urlerror
    from urllib import request as urlrequest

    from agent_service.infrastructure.sandbox.docker_runner import RUNNER_API_PATH

    skill = make_skill({'main.py': 'print("never")'})
    work = skill.parent / 'workdir'
    work.mkdir()
    payload = json.dumps({
        'protocol_version': 1,
        'invocation': {
            'name': 'agent-sandbox-t1-credential',
            'skill_root': str(skill),
            'work_dir': str(work),
            'script_relative_path': 'scripts/main.py',
            'args': [],
            'env': {'DATABASE_URL': 'postgresql://u:p@db/x'},
        },
    }).encode('utf-8')
    request = urlrequest.Request(
        runner_server.url + RUNNER_API_PATH,
        data=payload,
        headers={'Content-Type': 'application/json', 'X-Sandbox-Runner-Token': TEST_TOKEN},
        method='POST',
    )
    with pytest.raises(urlerror.HTTPError) as raised:
        urlrequest.urlopen(request, timeout=10)
    assert raised.value.code == 400


def test_sidecar_unreachable_fails_closed(tmp_path: Path) -> None:
    from agent_service.application.sandbox_runner import ContainerInvocation

    skill = tmp_path / 'skill'
    work = tmp_path / 'work'
    skill.mkdir()
    work.mkdir()
    executor = HttpRunnerDockerExecutor('http://127.0.0.1:9', runner_token=TEST_TOKEN)
    execution = executor.run(
        ContainerInvocation(
            name='agent-sandbox-t1-unreachable',
            skill_root=str(skill),
            work_dir=str(work),
            script_relative_path='scripts/x.py',
        )
    )
    assert execution.engine_failed
    assert 'runner 不可达' in execution.error


def test_runner_http_is_production_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('AGENT_SANDBOX_EXECUTOR_MODE', 'runner_http')
    monkeypatch.setenv('AGENT_SANDBOX_RUNNER_URL', 'http://sandbox-runner:51110')
    monkeypatch.setenv(RUNNER_TOKEN_ENV, TEST_TOKEN)
    config = DockerRunnerConfig.from_env()
    assert config.mode is DockerRunnerMode.RUNNER_HTTP
    executor = build_sandbox_executor(config)
    assert isinstance(executor, HttpRunnerDockerExecutor)
    # agent_service 侧配置里没有 docker 访问面：只可能出站 HTTP
    assert executor.limits.image == config.limits.image
