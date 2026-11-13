# -*- coding: utf-8 -*-
"""tests/agent_sandbox 共用小工具（非测试用例，pytest 不收集）。"""

from __future__ import annotations

import subprocess

from agent_service.application.sandbox_runner import (
    ContainerExecution,
    ContainerInvocation,
    T2ContainerInvocation,
)
from agent_service.infrastructure.sandbox.docker_runner import HostCliDockerExecutor
from agent_service.infrastructure.sandbox.t2_runner import T2DockerExecutor


def docker_cli(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['docker', *args], capture_output=True, text=True, timeout=timeout
    )


class RecordingDockerExecutor(HostCliDockerExecutor):
    """记录每次容器名的执行器：用例结束后逐个确认容器已销毁。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.container_names: list[str] = []

    def run(self, invocation: ContainerInvocation) -> ContainerExecution:
        self.container_names.append(invocation.name)
        return super().run(invocation)


class RecordingT2Executor(T2DockerExecutor):
    """T2 执行器 + 容器名记录（用例结束后确认无遗留容器）。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.container_names: list[str] = []

    def run(self, invocation: T2ContainerInvocation) -> ContainerExecution:
        self.container_names.append(invocation.name)
        return super().run(invocation)

