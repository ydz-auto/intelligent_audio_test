# -*- coding: utf-8 -*-
"""沙箱门禁：T1（INT-2455）+ T2（INT-2489）逃逸/资源限制用例，供 CI 与 M3 门禁复用。

做什么
------
1. 预检：docker CLI / daemon / 沙箱镜像在本地（``--pull`` 决定拉取或失败）。
   跑 T2 时额外要求 docker 已注册 gVisor ``runsc`` runtime；缺失即门禁失败并
   输出 ``T2_RUNTIME_UNAVAILABLE``（不静默降级到 runc/T1）。
2. 运行对应层级的 pytest 用例（真实一次性容器）。任一条失败 / 跳过即不通过。
3. 门禁结束后终检：无遗留 ``agent-sandbox=t1`` / ``agent-sandbox=t2`` 容器。

用法（仓库根、项目环境 python）：
    python scripts/sandbox_gate.py                 # T1 门禁（默认）
    python scripts/sandbox_gate.py --tier t2       # T2 门禁（需 runsc）
    python scripts/sandbox_gate.py --tier all --pull
    python scripts/sandbox_gate.py --tier t2 --json
    python scripts/sandbox_gate.py --json-out ./out/sandbox.json   # 五层门禁聚合

退出码：0 全通过；1 用例失败/跳过；2 预检失败。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SANDBOX_TEST_DIR = PROJECT_ROOT / 'tests' / 'agent_sandbox'
DEFAULT_IMAGE = 'python:3.11-slim'
T1_CONTAINER_LABEL = 'agent-sandbox=t1'
T2_CONTAINER_LABEL = 'agent-sandbox=t2'

T1_TESTS = [
    'test_sandbox_contract.py',
    'test_sandbox_spec_validation.py',
    'test_sandbox_execution.py',
    'test_sandbox_runner_transport.py',
    'test_sandbox_lifecycle.py',
]
T2_TESTS = [
    'test_t2_contract.py',
    'test_t2_escape.py',
    'test_t2_boundary_p1.py',
]


def _run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, **kwargs)


def _preflight_docker() -> tuple[bool, str]:
    if shutil.which('docker') is None:
        return False, 'docker CLI 不可用（需要 Docker Desktop / Docker Engine）'
    # 探活用 `docker version`：部分开发机 `docker info` 会卡到分钟级（已知环境问题）。
    info = _run(['docker', 'version', '--format', '{{.Server.Version}}'], timeout=120)
    if info.returncode != 0:
        return False, f'docker daemon 不可用：{info.stderr.strip()[:300]}'
    return True, info.stdout.strip()


def _preflight_image(image: str, pull: bool) -> tuple[bool, str]:
    inspect = _run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image], timeout=60)
    if inspect.returncode == 0:
        return True, f'镜像就绪：{image}'
    if not pull:
        return False, f'镜像 {image} 不在本地；先执行 docker pull {image} 或加 --pull'
    pull_result = _run(['docker', 'pull', image], timeout=600)
    if pull_result.returncode != 0:
        return False, f'docker pull {image} 失败：{pull_result.stderr.strip()[:300]}'
    return True, f'已拉取镜像：{image}'


def _preflight_runsc() -> tuple[bool, str]:
    """T2 预检：docker runtime 列表必须有 runsc（gVisor）。

    本机已知问题：``docker info`` 偶发分钟级卡顿；超时按预检失败处理（退出码 2），
    不让门禁抛异常——预检失败与「无 runsc」同样是 exit 2，日志给出具体原因。
    """
    try:
        info = _run(['docker', 'info', '--format', '{{json .Runtimes}}'], timeout=120)
    except subprocess.TimeoutExpired:
        return False, 'docker info 超时（本机偶发卡顿，已知环境问题）：无法确认 runsc'
    if info.returncode != 0:
        return False, f'docker info 失败：{info.stderr.strip()[:300]}'
    try:
        runtimes = json.loads(info.stdout or '{}')
    except ValueError:
        return False, f'docker info 输出非法：{info.stdout.strip()[:300]}'
    if 'runsc' not in (runtimes or {}):
        return False, (
            'T2_RUNTIME_UNAVAILABLE: docker 未注册 runtime runsc（现有：'
            f'{sorted((runtimes or {}).keys())}）；需在宿主安装 gVisor 并注册 runsc，'
            '或使用预置 gVisor 的 CI（docker-in-docker）'
        )
    return True, f'gVisor runtime 就绪：{runtimes["runsc"]}'


def _leftover_containers(label: str) -> list[str]:
    listing = _run(
        ['docker', 'ps', '--all', '--filter', f'label={label}', '--format', '{{.Names}}'],
        timeout=60,
    )
    if listing.returncode != 0:
        return ['<docker ps 失败>']
    return [name for name in listing.stdout.split() if name]


def _skipped_count(output: str) -> int:
    """从 pytest -q 摘要里取 skip 数（门禁不允许 docker 用例被跳过）。"""
    matches = re.findall(r'(\d+) skipped', output)
    return sum(int(value) for value in matches)


def _summary_counts(output: str) -> dict:
    """解析 pytest 摘要里的 passed / failed / skipped / error 数（报告口径）。"""
    counts = {}
    for name in ('passed', 'failed', 'skipped', 'error', 'errors'):
        matches = re.findall(r'(\d+) ' + name + r'\b', output)
        if matches:
            counts['error' if name == 'errors' else name] = sum(
                int(value) for value in matches)
    return counts


def _write_json_out(args, payload: dict) -> None:
    """把机器可读结果另存一份（INT-2475 五层门禁聚合用）。"""
    if not getattr(args, 'json_out', ''):
        return
    path = os.path.abspath(args.json_out)
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def _clean_env() -> dict:
    """不带宿主 AGENT_SANDBOX_* 变量，门禁结果只取决于本脚本显式配置。"""
    return {k: v for k, v in os.environ.items() if not k.startswith('AGENT_SANDBOX_')}


def main() -> int:
    parser = argparse.ArgumentParser(description='沙箱逃逸/资源限制门禁（T1/T2）')
    parser.add_argument('--tier', choices=('t1', 't2', 'all'), default='t1',
                        help='门禁层级：t1（默认）/ t2（需 runsc）/ all')
    parser.add_argument('--pull', action='store_true', help='镜像缺失时先 docker pull')
    parser.add_argument('--json', action='store_true', help='输出机器可读结果')
    parser.add_argument('--json-out', default='',
                        help='把机器可读结果另存为文件（供五层评测聚合）')
    parser.add_argument('--image', default=DEFAULT_IMAGE, help='沙箱镜像（默认 python:3.11-slim）')
    parser.add_argument('--t2-image', default=os.environ.get('AGENT_SANDBOX_T2_IMAGE', DEFAULT_IMAGE),
                        help='T2 沙箱镜像（默认 python:3.11-slim）')
    args = parser.parse_args()

    ok, detail = _preflight_docker()
    if not ok:
        return _fail(args, 'preflight', detail)
    ok, detail = _preflight_image(args.image, args.pull)
    if not ok:
        return _fail(args, 'preflight', detail)
    if args.tier in ('t2', 'all'):
        ok, detail = _preflight_image(args.t2_image, args.pull)
        if not ok:
            return _fail(args, 'preflight', detail)
        ok, detail = _preflight_runsc()
        if not ok:
            return _fail(args, 'preflight', detail)

    targets: list[str] = []
    labels: list[str] = []
    if args.tier in ('t1', 'all'):
        targets += [str(SANDBOX_TEST_DIR / name) for name in T1_TESTS]
        labels.append(T1_CONTAINER_LABEL)
    if args.tier in ('t2', 'all'):
        targets += [str(SANDBOX_TEST_DIR / name) for name in T2_TESTS]
        labels.append(T2_CONTAINER_LABEL)

    pytest_cmd = [
        sys.executable, '-m', 'pytest', *targets, '-q', '-p', 'no:cacheprovider',
    ]
    result = subprocess.run(
        pytest_cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        timeout=3600, env={**_clean_env(), 'AGENT_SANDBOX_IMAGE': args.image,
                           'AGENT_SANDBOX_T2_IMAGE': args.t2_image},
    )
    output = (result.stdout or '') + (result.stderr or '')
    print(output.strip()[-8000:])

    skipped = _skipped_count(output) > 0
    leftover = [name for label in labels for name in _leftover_containers(label)]
    passed = result.returncode == 0 and not skipped and not leftover

    payload = {
        'gate': f'INT-2455/INT-2489:{args.tier}',
        'pass': passed,
        'pytest_exit': result.returncode,
        'skipped_any': skipped,
        'leftover_containers': leftover,
        'image': args.image,
        'tier': args.tier,
        'counts': _summary_counts(output),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    _write_json_out(args, payload)
    print(f'==== {args.tier.upper()} 沙箱门禁: ' + ('PASS' if passed else 'FAIL') + ' ====')
    if not passed:
        if skipped:
            print('[FAIL] 存在被 skip 的用例（门禁要求沙箱用例全部真实执行）')
        if leftover:
            print(f'[FAIL] 沙箱容器未销毁：{leftover}')
    return 0 if passed else 1


def _fail(args, stage: str, detail: str) -> int:
    print(f'[FAIL] {stage}：{detail}')
    payload = {
        'gate': f'INT-2455/INT-2489:{args.tier}',
        'pass': False,
        'stage': stage,
        'detail': detail,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    _write_json_out(args, payload)
    return 2


if __name__ == '__main__':
    sys.exit(main())
