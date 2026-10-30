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
    ('audio', 'real'): 'audio_service.log',
    ('audio', 'shim'): 'audio_service_shim.log',
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
    os.dup2(handle.fileno(), 1)
    os.dup2(handle.fileno(), 2)


def main() -> None:
    parser = argparse.ArgumentParser(description='宿主服务进程入口（WMI 拉起）')
    parser.add_argument('--service', choices=('audio', 'device'), required=True)
    parser.add_argument('--mode', choices=('real', 'shim'), default='real')
    parser.add_argument('--env-file', required=True)
    args = parser.parse_args()

    os.chdir(REPO)
    _load_env(args.env_file)
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))

    _redirect_log(LOG_NAMES[(args.service, args.mode)])

    if args.service == 'device':
        runpy.run_module('device_service.interfaces.grpc.server',
                         run_name='__main__', alter_sys=True)
        return

    if args.mode == 'shim':
        sys.path.insert(0, str(SHIM_DIR))
    os.environ.setdefault('SERVICE_NAME', 'audio_service')
    os.environ.setdefault('GRPC_PORT', '50052')
    runpy.run_module('audio_service.interfaces.grpc.server',
                     run_name='__main__', alter_sys=True)


if __name__ == '__main__':
    main()
