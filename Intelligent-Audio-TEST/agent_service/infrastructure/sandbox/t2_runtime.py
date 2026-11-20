# -*- coding: utf-8 -*-
"""T2 可信运行时可见性探测（INT-2456 / 方案 07 §7 拍板#2）。

``T2_UNTRUSTED_CODE``（模型生成代码 / 驱动代码 / 任意分析脚本）需要 gVisor
（``runsc``）或 Firecracker 提供的强隔离运行时。首期不实现 T2 执行
（INT-2455 只交付 T1），但「运行时到底在不在」必须有明确结论：

- 运行时缺失 → T2 请求报 ``T2_RUNTIME_UNAVAILABLE``，**绝不静默降级 T1**；
- ``/health`` 回显探测结果，部署验收不必进容器手工查命令。

探测只读可执行文件与 ``<runtime> --version``：agent_service 不持有
docker.sock（方案 §7 红线），无法经 ``docker info`` 查已注册 runtimes；
运行时装在运行时所在主机（宿主或镜像）上，安装与启用方式见
``docker/README.md`` 的「T2 运行时」一节。
"""
import shutil
import subprocess
from dataclasses import dataclass

#: /health 的取值（与 SandboxFailureReason 的失败码区分：这是可见性状态）。
T2_RUNTIME_AVAILABLE = 'available'
T2_RUNTIME_UNAVAILABLE = 'unavailable'

#: 缺省运行时名（配置项 AGENT_T2_RUNTIME 的同名缺省；本模块不 import 业务配置，
#: 与 docker_runner 同口径：独立 runner 进程不需要 DB/OSS 配置也能启动）。
DEFAULT_T2_RUNTIME = 'runsc'

_PROBE_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class T2RuntimeStatus:
    runtime: str
    available: bool
    binary_path: str = ''
    detail: str = ''

    def as_health(self) -> dict:
        return {
            'runtime': self.runtime,
            'status': T2_RUNTIME_AVAILABLE if self.available
            else T2_RUNTIME_UNAVAILABLE,
            'binary': self.binary_path,
            'detail': self.detail,
        }


def probe_t2_runtime(runtime: str = '') -> T2RuntimeStatus:
    """探测 T2 运行时是否可用；``runtime`` 缺省为 runsc。"""
    name = (runtime or DEFAULT_T2_RUNTIME).strip() or DEFAULT_T2_RUNTIME
    path = shutil.which(name)
    if not path:
        return T2RuntimeStatus(
            runtime=name, available=False,
            detail=f'未在 PATH 找到 {name}：T2_UNTRUSTED_CODE 不可执行'
                   f'（安装/启用方式见 docker/README.md「T2 运行时」）',
        )
    try:
        result = subprocess.run(
            [path, '--version'], capture_output=True,
            timeout=_PROBE_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return T2RuntimeStatus(
            runtime=name, available=False, binary_path=path,
            detail=f'{name} 无法执行：{exc}')
    if result.returncode != 0:
        return T2RuntimeStatus(
            runtime=name, available=False, binary_path=path,
            detail=f'{name} --version 退出码 {result.returncode}：'
                   f'{_first_line(result.stderr)}',
        )
    return T2RuntimeStatus(
        runtime=name, available=True, binary_path=path,
        detail=_first_line(result.stdout) or f'{name} 可用',
    )


def _first_line(raw: bytes) -> str:
    text = (raw or b'').decode('utf-8', 'replace').strip()
    return text.splitlines()[0] if text else ''
