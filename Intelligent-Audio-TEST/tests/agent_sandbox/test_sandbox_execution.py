# -*- coding: utf-8 -*-
"""T1 沙箱逃逸与资源限制实测（INT-2455）——真实 Docker 容器。

对应可测验收标准：
1. 无网络 / 无宿主挂载 / 无法提权 / 内存·CPU·PID·超时·输出超限被拦截并记录原因；
2. 同一脚本两次执行互不影响（容器用完即毁），产物只从 ``/work`` 回收；
3. 沙箱内看不到任何 DB/OSS/LLM 凭证；
4. 失败 run 明确为 ``FAILED`` / ``BUDGET_EXCEEDED``，不静默成功。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from agent_service.application.sandbox_runner import (
    ContainerLimits,
    SandboxArtifactPolicy,
    SandboxFailureReason,
    SandboxOutcome,
)

pytestmark = pytest.mark.docker_required

DOCKER_FAILED_OUTCOMES = (SandboxOutcome.FAILED, SandboxOutcome.BUDGET_EXCEEDED)


def _parse_stdout(result) -> dict:
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if line.startswith('{') and line.endswith('}'):
            return json.loads(line)
    raise AssertionError(f'脚本未输出 JSON：stdout={result.stdout!r} stderr={result.stderr!r}')


# ── 1. 容器边界：非 root / 只读根 / 无 capability / /tmp 与 /work ──


BOUNDARY_SCRIPT = r'''
import json, os, pathlib
result = {}
result['uid'] = os.getuid()
result['gid'] = os.getgid()
try:
    open('/pwned', 'w').write('x')
    result['root_write'] = 'allowed'
except OSError:
    result['root_write'] = 'denied'
try:
    open('/etc/shadow', 'r').read()
    result['shadow_read'] = 'allowed'
except OSError:
    result['shadow_read'] = 'denied'
with open('/proc/self/status') as fh:
    result['cap_eff'] = [l.split(':')[1].strip() for l in fh if l.startswith('CapEff')][0]
try:
    pathlib.Path('/tmp/tmp_ok').write_text('ok')
    result['tmp_write'] = 'allowed'
except OSError:
    result['tmp_write'] = 'denied'
try:
    pathlib.Path('/work/ok.txt').write_text('ok')
    result['work_write'] = 'allowed'
except OSError:
    result['work_write'] = 'denied'
print(json.dumps(result))
'''


def test_non_root_readonly_root_no_capabilities(make_skill, run_script) -> None:
    skill = make_skill({'main.py': BOUNDARY_SCRIPT})
    result = run_script(skill)
    assert result.outcome is SandboxOutcome.SUCCEEDED, result.detail
    payload = _parse_stdout(result)
    assert payload['uid'] != 0, '沙箱必须以非 root 运行'
    assert payload['root_write'] == 'denied', '容器根文件系统必须只读'
    assert payload['shadow_read'] == 'denied'
    assert payload['cap_eff'] == '0' * 16, '必须 --cap-drop=ALL'
    assert payload['tmp_write'] == 'allowed'
    assert payload['work_write'] == 'allowed'
    assert [a.relative_path for a in result.artifacts] == ['ok.txt']


# ── 2. 无网络 ───────────────────────────────────────────────


NETWORK_SCRIPT = r'''
import json, socket
result = {}
for host, port in [('host.docker.internal', 15000), ('8.8.8.8', 53), ('127.0.0.1', 15000)]:
    key = f'{host}:{port}'
    try:
        sock = socket.create_connection((host, port), timeout=2)
        sock.close()
        result[key] = 'connected'
    except OSError as exc:
        result[key] = type(exc).__name__
print(json.dumps(result))
'''


def test_network_is_fully_blocked(make_skill, run_script) -> None:
    skill = make_skill({'main.py': NETWORK_SCRIPT})
    result = run_script(skill)
    assert result.outcome is SandboxOutcome.SUCCEEDED
    payload = _parse_stdout(result)
    for target, outcome in payload.items():
        assert outcome != 'connected', f'沙箱竟然连上了 {target}'


# ── 3. 宿主文件不可见 ───────────────────────────────────────


HOST_PROBE_SCRIPT = r'''
import json, os
result = {'found': [], 'root_listing': sorted(os.listdir('/'))}
candidates = [
    '/host_secret.txt', '/host_secret', '/work/../host_secret.txt',
    '/skill/../host_secret.txt', '/proc/1/root/host_secret.txt',
    '/proc/1/cwd/host_secret.txt',
]
for path in candidates:
    try:
        if os.path.isfile(path):
            result['found'].append(path)
    except OSError:
        pass
print(json.dumps(result))
'''


def test_host_filesystem_not_visible(make_skill, run_script, tmp_path: Path) -> None:
    secret = tmp_path / 'host_secret.txt'
    secret.write_text('TOP-SECRET', encoding='utf-8')
    skill = make_skill({'main.py': HOST_PROBE_SCRIPT})
    result = run_script(skill)
    assert result.outcome is SandboxOutcome.SUCCEEDED
    payload = _parse_stdout(result)
    assert payload['found'] == [], f'沙箱读到了宿主文件：{payload["found"]}'
    assert all('00_code' not in entry and 'host_secret' not in entry
               for entry in payload['root_listing'])


# ── 4. 沙箱内没有任何凭证 ───────────────────────────────────


CREDENTIAL_PROBE_SCRIPT = r'''
import json, os, pathlib
CRED_MARKERS = ['PASSWORD', 'SECRET', 'TOKEN', 'API_KEY', 'ACCESS_KEY', 'DATABASE_URL',
                'DB_HOST', 'OSS_', 'LLM_', 'OPENAI', 'DEEPSEEK', 'ANTHROPIC', 'REDIS_URL']
env_hits = [k for k in os.environ if any(m in k.upper() for m in CRED_MARKERS)]
content_hits = []
# 片段拼接：避免探针脚本自身被误判为「含凭据」。
content_markers = [b'postgres' + b'ql://', b'mysql' + b'://',
                   b'OSS_ACCESS' + b'_KEY', b'sk' + b'-', b'OPENAI_API' + b'_KEY']
for root in ['/work', '/skill', '/tmp', '/etc']:
    for path in pathlib.Path(root).rglob('*'):
        try:
            if path.is_file() and path.stat().st_size < 200000:
                data = path.read_bytes()
                for marker in content_markers:
                    if marker in data:
                        content_hits.append([str(path), marker.decode()])
        except OSError:
            pass
print(json.dumps({'env_hits': env_hits, 'content_hits': content_hits}))
'''


def test_no_credentials_inside_sandbox(make_skill, run_script) -> None:
    skill = make_skill({'main.py': CREDENTIAL_PROBE_SCRIPT})
    result = run_script(skill)
    assert result.outcome is SandboxOutcome.SUCCEEDED
    payload = _parse_stdout(result)
    assert payload['env_hits'] == [], f'沙箱环境变量含凭据：{payload["env_hits"]}'
    assert payload['content_hits'] == [], f'沙箱文件系统含凭据：{payload["content_hits"]}'


def test_credential_env_never_reaches_container(make_skill, run_script) -> None:
    skill = make_skill({'main.py': 'print("should not run")'})
    result = run_script(skill, env={'DATABASE_URL': 'postgresql://u:p@db/x'})
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.INVALID_INVOCATION


# ── 5. 超时 ────────────────────────────────────────────────


def test_timeout_terminates_container(make_skill, run_script) -> None:
    skill = make_skill({'main.py': 'import time\ntime.sleep(120)\nprint("never")\n'})
    started = time.monotonic()
    result = run_script(skill, limits=ContainerLimits(timeout_seconds=3))
    elapsed = time.monotonic() - started
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.TIMEOUT
    assert result.timed_out is True
    assert elapsed < 40, f'超时容器未及时终止：{elapsed:.1f}s'


# ── 6. CPU 上限（跑满 CPU 的脚本由超时兜底终止） ─────────────


CPU_SCRIPT = r'''
import time
end = time.time() + 120
while time.time() < end:
    pass
print('never')
'''


def test_cpu_burn_is_terminated(make_skill, run_script) -> None:
    skill = make_skill({'main.py': CPU_SCRIPT})
    started = time.monotonic()
    result = run_script(skill, limits=ContainerLimits(timeout_seconds=3, cpus=1.0))
    elapsed = time.monotonic() - started
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.TIMEOUT
    assert elapsed < 40


# ── 7. 输出上限 ────────────────────────────────────────────


OUTPUT_FLOOD_SCRIPT = r'''
import sys
chunk = 'x' * 65536
for _ in range(64):  # 4MB，远超 1MB 上限
    sys.stdout.write(chunk)
    sys.stdout.flush()
print('never')
'''


def test_output_flood_is_killed_and_recorded(make_skill, run_script) -> None:
    skill = make_skill({'main.py': OUTPUT_FLOOD_SCRIPT})
    limit = 64 * 1024
    result = run_script(
        skill, limits=ContainerLimits(timeout_seconds=30, output_limit_bytes=limit)
    )
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.OUTPUT_LIMIT_EXCEEDED
    assert result.output_truncated is True
    assert len(result.stdout.encode('utf-8')) <= limit


# ── 8. 内存上限 ────────────────────────────────────────────


MEMORY_HOG_SCRIPT = r'''
chunks = []
try:
    while True:
        chunks.append(bytearray(32 * 1024 * 1024))
except MemoryError:
    print('memoryerror')
'''


def test_memory_limit_contains_allocation(make_skill, run_script) -> None:
    skill = make_skill({'main.py': MEMORY_HOG_SCRIPT})
    result = run_script(
        skill,
        limits=ContainerLimits(
            timeout_seconds=30, memory='128m', memory_swap='128m'
        ),
    )
    assert result.outcome in DOCKER_FAILED_OUTCOMES, '内存超限必须判失败'
    assert result.reason in {
        SandboxFailureReason.MEMORY_LIMIT_EXCEEDED,
        SandboxFailureReason.EXIT_CODE_NONZERO,
        SandboxFailureReason.RESOURCE_LIMIT_EXCEEDED,
    }


# ── 9. PID 上限（fork 炸弹被围栏，宿主不受影响） ──────────────


FORK_BOMB_SCRIPT = r'''
import json, os
forks = 0
errno_hit = None
for _ in range(300):
    try:
        pid = os.fork()
    except OSError as exc:
        errno_hit = exc.errno
        break
    if pid == 0:
        os._exit(0)
    forks += 1
print(json.dumps({'forks': forks, 'errno': errno_hit}))
raise SystemExit(9 if errno_hit else 0)
'''


def test_pid_limit_contains_fork_bomb(make_skill, run_script) -> None:
    skill = make_skill({'main.py': FORK_BOMB_SCRIPT})
    result = run_script(skill, limits=ContainerLimits(timeout_seconds=30, pids_limit=32))
    assert result.outcome in DOCKER_FAILED_OUTCOMES, 'fork 炸弹不得表现为成功'
    payload = _parse_stdout(result)
    assert payload['errno'] in (11, 12), f'未命中 PID/内存上限：{payload}'
    assert payload['forks'] < 300, 'fork 未被 pids-limit 拦住'


# ── 10. 两次执行互不影响 / 容器用完即毁 ──────────────────────


ISOLATION_SCRIPT = r'''
import json, pathlib, sys
mode = sys.argv[1]
work = pathlib.Path('/work')
tmp = pathlib.Path('/tmp')
result = {'work_before': sorted(p.name for p in work.iterdir()),
          'tmp_before': sorted(p.name for p in tmp.iterdir())}
if mode == 'first':
    (work / 'a.txt').write_text('a', encoding='utf-8')
else:
    (work / 'b.txt').write_text('b', encoding='utf-8')
print(json.dumps(result))
'''


def test_two_runs_are_isolated(make_skill, run_script) -> None:
    skill = make_skill({'main.py': ISOLATION_SCRIPT})
    first = run_script(skill, args=('first',))
    second = run_script(skill, args=('second',))

    assert first.outcome is SandboxOutcome.SUCCEEDED
    assert second.outcome is SandboxOutcome.SUCCEEDED
    assert [a.relative_path for a in first.artifacts] == ['a.txt']
    assert [a.relative_path for a in second.artifacts] == ['b.txt']

    assert _parse_stdout(second)['work_before'] == [], '第二次执行看到了上一次的产物'
    assert _parse_stdout(second)['tmp_before'] == [], '/tmp 未随容器销毁'
    assert first.container_id and second.container_id
    assert first.container_id != second.container_id, '两次执行必须使用不同容器'


def test_same_script_twice_is_deterministic(make_skill, run_script) -> None:
    skill = make_skill({'main.py': 'import pathlib\npathlib.Path("/work/o.txt").write_text("same")\n'})
    first = run_script(skill)
    second = run_script(skill)
    assert first.outcome is second.outcome is SandboxOutcome.SUCCEEDED
    assert first.artifacts[0].sha256 == second.artifacts[0].sha256


# ── 11. 产物只从 /work 回收 ─────────────────────────────────


ARTIFACT_SCOPE_SCRIPT = r'''
import pathlib
pathlib.Path('/work/good.txt').write_text('good', encoding='utf-8')
pathlib.Path('/tmp/scratch.txt').write_text('scratch', encoding='utf-8')
try:
    pathlib.Path('/skill/leak.txt').write_text('leak', encoding='utf-8')
except OSError:
    print('skill readonly')
'''


def test_artifacts_only_from_work(make_skill, run_script) -> None:
    skill = make_skill({'main.py': ARTIFACT_SCOPE_SCRIPT})
    result = run_script(skill)
    assert result.outcome is SandboxOutcome.SUCCEEDED
    assert [a.relative_path for a in result.artifacts] == ['good.txt']
    assert not (skill / 'leak.txt').exists(), 'Skill 只读挂载被写穿'


def test_symlink_artifact_rejected(make_skill, run_script) -> None:
    script = (
        'import os, pathlib\n'
        'pathlib.Path("/work/real.txt").write_text("x")\n'
        'os.symlink("/etc/passwd", "/work/link.txt")\n'
    )
    skill = make_skill({'main.py': script})
    result = run_script(skill)
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.ARTIFACT_INVALID


def test_oversized_artifact_rejected(make_skill, run_script) -> None:
    script = 'import pathlib\npathlib.Path("/work/big.bin").write_bytes(b"0" * (2 * 1024 * 1024))\n'
    skill = make_skill({'main.py': script})
    result = run_script(skill, policy=SandboxArtifactPolicy(max_artifact_bytes=1024 * 1024))
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.ARTIFACT_TOO_LARGE


# ── 12. 失败不静默 + stdout/stderr 采集 ─────────────────────


def test_nonzero_exit_is_failed(make_skill, run_script) -> None:
    script = 'import sys\nprint("out")\nprint("err", file=sys.stderr)\nsys.exit(3)\n'
    skill = make_skill({'main.py': script})
    result = run_script(skill)
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.EXIT_CODE_NONZERO
    assert result.exit_code == 3
    assert 'out' in result.stdout and 'err' in result.stderr
