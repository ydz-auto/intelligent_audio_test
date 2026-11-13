# -*- coding: utf-8 -*-
"""T1 沙箱门禁（INT-2455）：逃逸/资源限制用例可重复运行，供 CI 与 M3 门禁复用。

做什么
------
1. 预检：docker CLI 可用、daemon 在跑、沙箱镜像（默认 ``python:3.11-slim``）在
   本地；镜像缺失时按 ``--pull`` 决定拉取或直接失败（门禁不静默降级）。
2. 运行 ``pytest tests/agent_sandbox``（真实一次性容器，含逃逸/资源/隔离/凭证
   用例）。任一条失败 / 跳过 docker 用例 → 门禁不通过。
3. 门禁结束后终检：无遗留 ``agent-sandbox=t1`` 标签容器。

用法（仓库根、项目环境 python）：
    python scripts/sandbox_gate.py             # 门禁
    python scripts/sandbox_gate.py --pull      # 镜像缺失时先 docker pull
    python scripts/sandbox_gate.py --json      # 机器可读结果（CI 留证）

退出码：0 全通过；1 用例失败/跳过；2 预检失败。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SANDBOX_TEST_DIR = PROJECT_ROOT / 'tests' / 'agent_sandbox'
DEFAULT_IMAGE = 'python:3.11-slim'
CONTAINER_LABEL = 'agent-sandbox=t1'


def _run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, **kwargs)


def _preflight(image: str, pull: bool) -> tuple[bool, str]:
    if shutil.which('docker') is None:
        return False, 'docker CLI 不可用（需要 Docker Desktop / Docker Engine）'
    # 探活用 `docker version`：部分开发机 `docker info` 会卡到分钟级（已知环境问题）。
    info = _run(['docker', 'version', '--format', '{{.Server.Version}}'], timeout=120)
    if info.returncode != 0:
        return False, f'docker daemon 不可用：{info.stderr.strip()[:300]}'
    inspect = _run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image], timeout=60)
    if inspect.returncode == 0:
        return True, f'镜像就绪：{image}'
    if not pull:
        return False, f'镜像 {image} 不在本地；先执行 docker pull {image} 或加 --pull'
    pull_result = _run(['docker', 'pull', image], timeout=600)
    if pull_result.returncode != 0:
        return False, f'docker pull {image} 失败：{pull_result.stderr.strip()[:300]}'
    return True, f'已拉取镜像：{image}'


def _leftover_containers() -> list[str]:
    listing = _run(
        ['docker', 'ps', '--all', '--filter', f'label={CONTAINER_LABEL}',
         '--format', '{{.Names}}'],
        timeout=60,
    )
    if listing.returncode != 0:
        return ['<docker ps 失败>']
    return [name for name in listing.stdout.split() if name]


def _skipped_count(output: str) -> int:
    """从 pytest -q 摘要里取 skip 数（门禁不允许 docker 用例被跳过）。"""
    matches = re.findall(r'(\d+) skipped', output)
    return sum(int(value) for value in matches)


def main() -> int:
    parser = argparse.ArgumentParser(description='T1 沙箱逃逸/资源限制门禁（INT-2455）')
    parser.add_argument('--pull', action='store_true', help='镜像缺失时先 docker pull')
    parser.add_argument('--json', action='store_true', help='输出机器可读结果')
    parser.add_argument('--image', default=DEFAULT_IMAGE, help='沙箱镜像（默认 python:3.11-slim）')
    args = parser.parse_args()

    ok, detail = _preflight(args.image, args.pull)
    if not ok:
        print(f'[FAIL] 预检：{detail}')
        if args.json:
            print(json.dumps({'gate': 'INT-2455', 'pass': False, 'stage': 'preflight',
                              'detail': detail}, ensure_ascii=False, indent=2))
        return 2

    env_ready = {'AGENT_SANDBOX_IMAGE': args.image}
    pytest_cmd = [
        sys.executable, '-m', 'pytest', str(SANDBOX_TEST_DIR), '-q', '-p', 'no:cacheprovider',
    ]
    result = subprocess.run(
        pytest_cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        timeout=1800, env={**_clean_env(), **env_ready},
    )
    output = (result.stdout or '') + (result.stderr or '')
    print(output.strip()[-8000:])

    skipped = _skipped_count(output) > 0
    leftover = _leftover_containers()
    passed = result.returncode == 0 and not skipped and not leftover

    if args.json:
        print(json.dumps({
            'gate': 'INT-2455', 'pass': passed,
            'pytest_exit': result.returncode,
            'skipped_any': skipped,
            'leftover_containers': leftover,
            'image': args.image,
        }, ensure_ascii=False, indent=2))
    print('==== T1 沙箱门禁: ' + ('PASS' if passed else 'FAIL') + ' ====')
    if not passed:
        if skipped:
            print('[FAIL] 存在被 skip 的用例（门禁要求 docker 用例全部真实执行）')
        if leftover:
            print(f'[FAIL] 沙箱容器未销毁：{leftover}')
    return 0 if passed else 1


def _clean_env() -> dict:
    """不带宿主 AGENT_SANDBOX_* 变量，门禁结果只取决于本脚本显式配置。"""
    import os

    return {k: v for k, v in os.environ.items() if not k.startswith('AGENT_SANDBOX_')}


if __name__ == '__main__':
    sys.exit(main())
