# -*- coding: utf-8 -*-
"""宿主服务进程入口（由 stack.py 经 WMI 脱离 run 树拉起）。

为什么要单独这个入口：agent 平台在 run 结束时会回收整棵进程树，直接 Popen
拉起的服务会随之消失。WMI ``Win32_Process.Create`` 拉起的进程父级是
WmiPrvSE（系统服务），不在任何 run 的 job 对象里。

WMI 拉起的进程不继承调用方环境（继承的是 WmiPrvSE 的），所以调用方把完整
环境写成 JSON 传进来，本入口在 import 业务模块前注入。
"""
import argparse
import json
import os
import runpy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

LOG_NAMES = {
    ('e2e', 'real'): 'e2e_test_service.log',
    # 宿主进程只承担执行机硬件面，见 docs/audio服务拆分方案.md §6
    ('audio', 'real'): 'audio_agent.log',
    ('audio', 'shim'): 'audio_agent_shim.log',
    ('device', 'real'): 'device_service.log',
}
SHIM_DIR = REPO / 'tests' / 'fixtures' / 'pyaudio_shim'
LOG_DIR = REPO / 'logs' / 'host_services'


def _load_env(path: str) -> None:
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    for key, value in data.items():
        if value is not None:
            os.environ[key] = str(value)


def _redirect_log(name: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handle = open(LOG_DIR / name, 'a', encoding='utf-8', errors='replace')
    # pythonw 启动时 sys.stdout/sys.stderr 为 None：dup2 只改 OS fd，
    # 还要把 Python 侧流对象指到同一文件，否则 logging/uvicorn 日志会丢
    sys.stdout = handle
    sys.stderr = handle
    os.dup2(handle.fileno(), 1)
    os.dup2(handle.fileno(), 2)


def _patch_subprocess_no_window() -> None:
    """Windows：宿主服务子进程统一禁开控制台窗口。

    pythonw 没有可继承的控制台，device_service 拉起 adb/hdc 等控制台程序时
    会各自弹一个黑色窗口；这里在服务模块 import 前替换 subprocess.Popen，
    默认叠加 CREATE_NO_WINDOW（adb track-devices、hdc、ffmpeg 都覆盖）。
    """
    if sys.platform != 'win32':
        return
    import subprocess

    if getattr(subprocess, '_iat_no_window_patched', False):
        return
    create_no_window = 0x08000000
    original_popen = subprocess.Popen

    class _NoWindowPopen(original_popen):
        def __init__(self, *args, **kwargs):
            kwargs['creationflags'] = kwargs.get('creationflags', 0) | create_no_window
            super().__init__(*args, **kwargs)

    subprocess.Popen = _NoWindowPopen
    subprocess._iat_no_window_patched = True


def main() -> None:
    parser = argparse.ArgumentParser(description='宿主服务进程入口（WMI 拉起）')
    parser.add_argument('--service', choices=('e2e', 'audio', 'device'), required=True)
    parser.add_argument('--mode', choices=('real', 'shim'), default='real')
    parser.add_argument('--env-file', required=True)
    args = parser.parse_args()

    os.chdir(REPO)
    _load_env(args.env_file)
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))

    _redirect_log(LOG_NAMES[(args.service, args.mode)])
    _patch_subprocess_no_window()

    if args.service == 'e2e':
        # e2e_test_service.app 的 __main__ 分支自起 uvicorn + gRPC（PORT/GRPC_PORT 由 env 注入）
        runpy.run_module('e2e_test_service.app', run_name='__main__', alter_sys=True)
        return

    if args.service == 'device':
        runpy.run_module('device_service.interfaces.grpc.server',
                         run_name='__main__', alter_sys=True)
        return

    if args.mode == 'shim':
        sys.path.insert(0, str(SHIM_DIR))
    os.environ.setdefault('SERVICE_NAME', 'audio_service')
    os.environ.setdefault('GRPC_PORT', '50052')
    # 宿主进程只承担硬件面（播放/试听/SPL），见 docs/audio服务拆分方案.md §6
    os.environ.setdefault('AUDIO_ROLE', 'agent')
    runpy.run_module('audio_service.interfaces.grpc.server',
                     run_name='__main__', alter_sys=True)


if __name__ == '__main__':
    main()
