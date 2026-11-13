# -*- coding: utf-8 -*-
"""T2 沙箱逃逸 / 联网 / 资源限制实测（INT-2489）——真实 gVisor ``runsc``。

对应卡面可测验收标准 1–5、7：

1. 逃逸用例 100% 拦截：宿主 ``/etc/passwd``、挂载宿主目录、``ptrace``、
   ``unshare``、``mount``、提权、写宿主路径；
2. 联网用例 100% 拦截：``curl``/DNS/直连 IP；出口白名单在契约层单测覆盖
   （真实代理 sidecar 由 INT-2456 部署）；
3. 资源用例生效：pids / CPU / 内存 / 时长 / 产物体积分别命中停止原因，且无
   遗留容器；
4. 凭证不可见：无 ``AGENT_CREDENTIAL_MASTER_KEY`` / DB / OSS / 设备凭证；
5. 失败不得静默成功：编译失败 ``FAILED``、超时 ``BUDGET_EXCEEDED``，事件带
   ``sandbox_failed`` 原因；
6. 运行时缺失时 ``T2_RUNTIME_UNAVAILABLE`` 由 ``test_t2_contract.py`` 单测覆盖。

无 ``runsc`` 的环境（如 Windows 开发机 Docker Desktop）会 skip 并给出手工执行
命令（``tests/agent_sandbox/README.md`` / 卡面要求，不许静默跳过）；门禁脚本
``scripts/sandbox_gate.py --tier t2`` 把 skip 判为失败。
"""

from __future__ import annotations

import json
import time

import pytest

from agent_service.application.sandbox_runner import (
    ContainerLimits,
    SandboxArtifactPolicy,
    SandboxFailureReason,
    SandboxOutcome,
    T2Phase,
)
from tests.agent_sandbox._sandbox_support import docker_cli

pytestmark = pytest.mark.t2_required

DOCKER_FAILED_OUTCOMES = (SandboxOutcome.FAILED, SandboxOutcome.BUDGET_EXCEEDED)


def _parse_stdout(result) -> dict:
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if line.startswith('{') and line.endswith('}'):
            return json.loads(line)
    raise AssertionError(f'脚本未输出 JSON：stdout={result.stdout!r} stderr={result.stderr!r}')


def _phase(name: str = 'probe', timeout: int = 30) -> T2Phase:
    return T2Phase(name, ('python3', f'/input/{name}.py'), timeout_seconds=timeout)


def _files(script: str, name: str = 'probe') -> dict[str, str]:
    return {f'{name}.py': script}


# ── 1. 容器边界：非 root / 只读根 / 无 capability / 卷边界 ─────


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
    lines = {l.split(':')[0]: l.split(':', 1)[1].strip() for l in fh if ':' in l}
result['cap_eff'] = lines.get('CapEff', '?')
result['no_new_privs'] = lines.get('NoNewPrivs', '?')
result['home'] = os.environ.get('HOME')
try:
    pathlib.Path('/input/leak.txt').write_text('x')
    result['input_write'] = 'allowed'
except OSError:
    result['input_write'] = 'denied'
try:
    pathlib.Path('/work/ok.txt').write_text('ok')
    result['work_write'] = 'allowed'
except OSError:
    result['work_write'] = 'denied'
print(json.dumps(result))
'''


def test_non_root_readonly_root_no_capabilities(run_t2) -> None:
    result = run_t2(_files(BOUNDARY_SCRIPT), (_phase(),))
    assert result.outcome is SandboxOutcome.SUCCEEDED, result.detail
    payload = _parse_stdout(result)
    assert payload['uid'] != 0, 'T2 必须以非 root 运行'
    assert payload['root_write'] == 'denied', '根文件系统必须只读'
    assert payload['shadow_read'] == 'denied'
    assert payload['cap_eff'] == '0' * 16, '必须 --cap-drop=ALL'
    assert payload['no_new_privs'] == '1', '必须 no-new-privileges'
    assert payload['home'] == '/tmp', '宿主 home 不可见'
    assert payload['input_write'] == 'denied', '输入卷必须只读'
    assert payload['work_write'] == 'allowed'
    assert [a.relative_path for a in result.artifacts] == ['ok.txt']
    assert result.artifacts[0].phase == 'probe'
    assert result.runtime == 'gvisor'


# ── 2. 逃逸尝试全部拦截 ────────────────────────────────────────


ESCAPE_SCRIPT = r'''
import ctypes, json, os

libc = ctypes.CDLL('libc.so.6', use_errno=True)
result = {}


def _rc(name, *args):
    func = getattr(libc, name)
    rc = func(*args)
    err = ctypes.get_errno()
    return rc, err


rc, err = _rc('mount', b'/etc', b'/work/host_etc', b'', 0, None)
result['mount'] = 'allowed' if rc == 0 else f'denied:{err}'

rc, err = _rc('unshare', 0x10000000)  # CLONE_NEWUSER
result['unshare_user_ns'] = 'allowed' if rc == 0 else f'denied:{err}'

rc, err = _rc('ptrace', 16, 1, None, None)  # PTRACE_ATTACH -> pid 1
result['ptrace'] = 'allowed' if rc == 0 else f'denied:{err}'

rc, err = _rc('setuid', 0)
result['setuid_0'] = 'allowed' if rc == 0 else f'denied:{err}'

rc, err = _rc('chroot', b'/')
result['chroot'] = 'allowed' if rc == 0 else f'denied:{err}'

try:
    os.unlink('/etc/shadow')
    result['delete_etc_shadow'] = 'allowed'
except OSError:
    result['delete_etc_shadow'] = 'denied'

print(json.dumps(result))
'''


def test_escape_attempts_are_blocked(run_t2) -> None:
    result = run_t2(_files(ESCAPE_SCRIPT), (_phase(),))
    assert result.outcome is SandboxOutcome.SUCCEEDED, result.detail
    payload = _parse_stdout(result)
    for key, value in payload.items():
        assert value != 'allowed', f'T2 沙箱逃逸未被拦截：{key}'


HOST_PROBE_SCRIPT = r'''
import json, os
result = {'found': [], 'root_listing': sorted(os.listdir('/'))}
candidates = [
    '/host_secret.txt', '/host_secret', '/work/../host_secret.txt',
    '/input/../host_secret.txt', '/proc/1/root/host_secret.txt',
    '/proc/1/cwd/host_secret.txt', '/proc/1/environ',
]
for path in candidates:
    try:
        if os.path.isfile(path):
            with open(path, 'rb') as fh:
                result['found'].append([path, fh.read(32).decode('utf-8', 'replace')])
    except OSError:
        pass
print(json.dumps(result))
'''


def test_host_filesystem_not_visible(run_t2) -> None:
    result = run_t2(_files(HOST_PROBE_SCRIPT), (_phase(),))
    assert result.outcome is SandboxOutcome.SUCCEEDED
    payload = _parse_stdout(result)
    found = [entry[0] for entry in payload['found']]
    assert found == [], f'T2 沙箱读到了宿主文件：{payload["found"]}'
    assert all('00_code' not in entry and 'host_secret' not in entry
               for entry in payload['root_listing'])


# ── 3. 联网全部拦截 ────────────────────────────────────────────


NETWORK_SCRIPT = r'''
import json, socket, urllib.request
result = {}
for host, port in [('host.docker.internal', 15000), ('8.8.8.8', 53),
                   ('1.1.1.1', 443), ('127.0.0.1', 15000)]:
    key = f'{host}:{port}'
    try:
        sock = socket.create_connection((host, port), timeout=2)
        sock.close()
        result[key] = 'connected'
    except OSError as exc:
        result[key] = type(exc).__name__
try:
    result['dns'] = socket.gethostbyname('example.com')
except OSError as exc:
    result['dns'] = type(exc).__name__
try:
    urllib.request.urlopen('http://example.com', timeout=2)
    result['http'] = 'connected'
except Exception as exc:
    result['http'] = type(exc).__name__
print(json.dumps(result))
'''


def test_network_is_fully_blocked(run_t2) -> None:
    result = run_t2(_files(NETWORK_SCRIPT), (_phase(),))
    assert result.outcome is SandboxOutcome.SUCCEEDED
    payload = _parse_stdout(result)
    for target, outcome in payload.items():
        assert outcome != 'connected', f'T2 沙箱竟然连上了 {target}'


# ── 4. 凭证不可见 ──────────────────────────────────────────────


CREDENTIAL_PROBE_SCRIPT = r'''
import json, os, pathlib
CRED_MARKERS = ['PASSWORD', 'SECRET', 'TOKEN', 'API_KEY', 'ACCESS_KEY',
                'DATABASE_URL', 'DB_HOST', 'OSS_', 'LLM_', 'OPENAI',
                'DEEPSEEK', 'ANTHROPIC', 'REDIS_URL', 'CREDENTIAL', 'MASTER_KEY']
env_hits = [k for k in os.environ if any(m in k.upper() for m in CRED_MARKERS)]
master_key_visible = 'AGENT_CREDENTIAL_MASTER_KEY' in os.environ
content_hits = []
content_markers = [b'postgres' + b'ql://', b'mysql' + b'://',
                   b'OSS_ACCESS' + b'_KEY', b'sk' + '-', b'OPENAI_API' + b'_KEY']
for root in ['/input', '/work', '/tmp', '/etc']:
    for path in pathlib.Path(root).rglob('*'):
        try:
            if path.is_file() and path.stat().st_size < 200000:
                data = path.read_bytes()
                for marker in content_markers:
                    if marker in data:
                        content_hits.append([str(path), marker.decode()])
        except OSError:
            pass
root_readable = True
try:
    pathlib.Path('/root/.bashrc').read_text()
except OSError:
    root_readable = False
print(json.dumps({'env_hits': env_hits,
                  'master_key_visible': master_key_visible,
                  'content_hits': content_hits,
                  'root_home_readable': root_readable,
                  'home': os.environ.get('HOME')}))
'''


def test_no_credentials_inside_sandbox(run_t2) -> None:
    result = run_t2(_files(CREDENTIAL_PROBE_SCRIPT), (_phase(),))
    assert result.outcome is SandboxOutcome.SUCCEEDED
    payload = _parse_stdout(result)
    assert payload['env_hits'] == [], f'沙箱环境变量含凭据：{payload["env_hits"]}'
    assert payload['master_key_visible'] is False
    assert payload['content_hits'] == [], f'沙箱文件系统含凭据：{payload["content_hits"]}'
    assert payload['root_home_readable'] is False
    assert payload['home'] == '/tmp'


# ── 5. 资源限制 ────────────────────────────────────────────────


def test_timeout_terminates_container(run_t2) -> None:
    result = run_t2(
        _files('import time\ntime.sleep(300)\nprint("never")\n'),
        (_phase(timeout=5),),
    )
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.TIMEOUT
    assert result.timed_out is True


CPU_SCRIPT = r'''
import time
end = time.time() + 300
while time.time() < end:
    pass
print('never')
'''


def test_cpu_burn_is_terminated_by_timeout(run_t2) -> None:
    # CPU 超额由 cgroup 节流（不会杀进程），最终由时长硬限兜底终止：
    # 与 T1 口径一致，停止原因是 TIMEOUT。
    started = time.monotonic()
    result = run_t2(_files(CPU_SCRIPT), (_phase(timeout=5),))
    elapsed = time.monotonic() - started
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.TIMEOUT
    assert elapsed < 60, f'CPU 打满的容器未及时终止：{elapsed:.1f}s'


OUTPUT_FLOOD_SCRIPT = r'''
import sys
chunk = 'x' * 65536
for _ in range(64):  # 4MB，远超 1MB 上限
    sys.stdout.write(chunk)
    sys.stdout.flush()
print('never')
'''


def test_output_flood_is_killed_and_recorded(run_t2) -> None:
    result = run_t2(_files(OUTPUT_FLOOD_SCRIPT), (_phase(),))
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.OUTPUT_LIMIT_EXCEEDED
    assert result.output_truncated is True


MEMORY_HOG_SCRIPT = r'''
chunks = []
try:
    while True:
        chunks.append(bytearray(32 * 1024 * 1024))
except MemoryError:
    print('memoryerror')
'''


def test_memory_limit_contains_allocation(run_t2, make_t2_executor) -> None:
    executor = make_t2_executor(ContainerLimits(timeout_seconds=30, memory='128m',
                                                memory_swap='128m'))
    result = run_t2(_files(MEMORY_HOG_SCRIPT), (_phase(),), executor=executor)
    assert result.outcome in DOCKER_FAILED_OUTCOMES, '内存超限必须判失败'
    assert result.reason in {
        SandboxFailureReason.MEMORY_LIMIT_EXCEEDED,
        SandboxFailureReason.EXIT_CODE_NONZERO,
        SandboxFailureReason.RESOURCE_LIMIT_EXCEEDED,
    }


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


def test_pid_limit_contains_fork_bomb(run_t2, make_t2_executor) -> None:
    executor = make_t2_executor(ContainerLimits(timeout_seconds=30, pids_limit=32))
    result = run_t2(_files(FORK_BOMB_SCRIPT), (_phase(),), executor=executor)
    assert result.outcome in DOCKER_FAILED_OUTCOMES, 'fork 炸弹不得表现为成功'
    payload = _parse_stdout(result)
    assert payload['errno'] in (11, 12), f'未命中 PID/内存上限：{payload}'
    assert payload['forks'] < 300, 'fork 未被 pids-limit 拦住'


def test_oversized_artifact_is_budget_exceeded(run_t2) -> None:
    script = 'import pathlib\npathlib.Path("/work/big.bin").write_bytes(b"0" * (2 * 1024 * 1024))\n'
    result = run_t2(
        _files(script),
        (_phase(),),
        artifact_policy=SandboxArtifactPolicy(max_artifact_bytes=1024 * 1024),
    )
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.ARTIFACT_TOO_LARGE


# ── 6. 失败不得静默成功 ────────────────────────────────────────


def test_compile_failure_is_failed(run_t2) -> None:
    result = run_t2(
        {'bad.py': 'def broken(:\n    pass\n'},
        (T2Phase('import_compile', ('python3', '-m', 'compileall', '-q', '/input')),),
    )
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.EXIT_CODE_NONZERO
    assert 'import_compile' in result.detail
    event = result.to_sandbox_event()
    assert event['event'] == 'sandbox_failed'
    assert event['reason'] == SandboxFailureReason.EXIT_CODE_NONZERO.value


def test_timeout_result_has_sandbox_failed_event(run_t2) -> None:
    result = run_t2(
        _files('import time\ntime.sleep(300)\n'),
        (_phase(timeout=5),),
    )
    event = result.to_sandbox_event()
    assert event['event'] == 'sandbox_failed'
    assert event['reason'] == SandboxFailureReason.TIMEOUT.value
    assert event['code_sha256']


def test_phases_are_isolated_and_artifacts_are_attributed(run_t2) -> None:
    script = (
        'import json, pathlib\n'
        'work = pathlib.Path("/work")\n'
        'print(json.dumps(sorted(p.name for p in work.iterdir())))\n'
        'work.joinpath("out.txt").write_text("x")\n'
    )
    result = run_t2(
        _files(script),
        (T2Phase('phase_a', ('python3', '/input/probe.py')),
         T2Phase('phase_b', ('python3', '/input/probe.py'))),
    )
    assert result.outcome is SandboxOutcome.SUCCEEDED, result.detail
    assert [p.name for p in result.phases] == ['phase_a', 'phase_b']
    assert all(p.succeeded for p in result.phases)
    assert sorted(a.phase for a in result.artifacts) == ['phase_a', 'phase_b']
    for chunk in result.stdout.splitlines():
        assert chunk.strip().startswith('[')
        assert '[]' in chunk, '后一阶段不应看到前一阶段的 /work 产物'


# ── 7. 容器用完即毁（及时清理，无需 --rm 兜底） ────────────────


def test_no_leftover_t2_containers(run_t2) -> None:
    result = run_t2(_files('print("ok")\n'), (_phase(),))
    assert result.outcome is SandboxOutcome.SUCCEEDED
    listing = docker_cli(
        'ps', '--all', '--filter', 'label=agent-sandbox=t2', '--format', '{{.Names}}'
    )
    assert listing.returncode == 0
    assert not [name for name in listing.stdout.split() if name], '存在遗留 T2 容器'
