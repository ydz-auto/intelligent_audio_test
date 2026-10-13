# -*- coding: utf-8 -*-
"""UI 集成门禁入口（INT-260）：一键起并行隔离栈 + 跑 UI 用例。

门禁语义：UI 用例不过 → 不推送。栈未隔离/未就绪 → FAIL（不静默跳过）。

并行隔离栈（端口 +1000：网关 6000 / 前端 6273）与共享栈并行互不干扰，
因此门禁可在共享栈被其它工作占用时照常执行。栈常驻复用（首次启动约
1-2 分钟，后续直接跑用例）；显式清理用 parallel_stack.py stop。

用法（仓库根）：
    python tests/ui/run_gate.py                 # 全量 UI 用例
    python tests/ui/run_gate.py -k login        # 透传 pytest 参数（-- 之后）
    python tests/ui/run_gate.py -- --maxfail=1
"""
import os
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

GATEWAY = 'http://127.0.0.1:6000'
FRONTEND = 'http://127.0.0.1:6273'

import httpx  # noqa: E402

from shared.constants.database import ISOLATED_TEST_DB_NAME  # noqa: E402

_LAUNCHER = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'utils', 'parallel_stack.py')


def _gw_health(timeout=2):
    try:
        r = httpx.get(f'{GATEWAY}/health', timeout=timeout, trust_env=False)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def ensure_stack() -> dict:
    """栈已隔离 → 复用；未起 → WMI 脱离进程树启动（INT-125 同因）并等就绪。"""
    body = _gw_health()
    if body:
        if body.get('database') != ISOLATED_TEST_DB_NAME:
            raise SystemExit(
                f"[GATE] :6000 已被非隔离库栈占用（database={body.get('database')}），"
                '拒绝误连。请排查端口占用。')
        print(f'[GATE] 复用已就绪的并行隔离栈（{GATEWAY}，database=隔离库）')
        return body
    print('[GATE] 并行隔离栈未起，经 WMI 脱离进程树启动（首次约 1-2 分钟）...')
    ps = (
        "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{"
        f"CommandLine = 'cmd.exe /c \"\"{sys.executable}\"\" \"{_LAUNCHER}\" start\"';"
        f"CurrentDirectory = '{PROJECT_ROOT}'"
        "}; $r.ReturnValue"
    )
    r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0 or not r.stdout.strip().endswith(('0',)):
        raise SystemExit(f'[GATE] WMI 启动失败: {r.stdout} {r.stderr}')
    deadline = time.time() + 180
    while time.time() < deadline:
        body = _gw_health()
        if body and body.get('database') == ISOLATED_TEST_DB_NAME:
            print(f'[GATE] 并行隔离栈就绪（database={body["database"]}）')
            return body
        time.sleep(3)
    raise SystemExit('[GATE] 栈就绪探测超时（3 分钟）；日志: logs/ui_stack/ui_stack.log')


def main():
    ensure_stack()
    env = dict(os.environ)
    env['RUN_LIVE_STACK'] = '1'
    env['UI_API_BASE'] = GATEWAY
    env['UI_FRONTEND_BASE'] = FRONTEND
    env['PYTHONUTF8'] = '1'
    pytest_args = sys.argv[1:]
    if pytest_args and pytest_args[0] == '--':
        pytest_args = pytest_args[1:]
    cmd = [sys.executable, '-m', 'pytest', os.path.join('tests', 'ui'), '-v'] + pytest_args
    print(f'[GATE] 运行: {" ".join(cmd)}')
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env)
    print(f'\n[GATE] UI 门禁结果: {"PASS" if proc.returncode == 0 else "FAIL"}'
          '（UI 用例不过不推送）')
    return proc.returncode


if __name__ == '__main__':
    raise SystemExit(main())
