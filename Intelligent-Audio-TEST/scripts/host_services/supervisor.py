# -*- coding: utf-8 -*-
"""宿主服务守护壳：子进程退出 5s 后拉起，看到停止标记就退出（原 run_forever.ps1）。

为什么用 pythonw 而不是 PowerShell：进程由 control.py 经 WMI 拉起（WmiPrvSE 做父级，
避免被 agent run 的 job 对象整树回收），WMI 进程没有可继承的控制台，PowerShell 会新
分配一个 conhost；Windows Terminal 下 `-WindowStyle Hidden` 不生效，于是每起一个服务
桌面就多一个空白黑窗。pythonw 是 GUI 子系统，天生没有控制台窗口。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOG_ROTATE_BYTES = 5 * 1024 * 1024
RESTART_DELAY = 5.0


def _log(path: Path, tag: str, message: str) -> None:
    line = f'{datetime.now():%Y-%m-%d %H:%M:%S} [{tag}] {message}\n'
    with open(path, 'a', encoding='utf-8') as handle:
        handle.write(line)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', required=True)
    parser.add_argument('--python', required=True)
    parser.add_argument('--entry', required=True)
    parser.add_argument('--mode', required=True)
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--log', required=True)
    parser.add_argument('--stop-flag', required=True)
    parser.add_argument('--pid-file', required=True)
    args = parser.parse_args()

    log = Path(args.log)
    stop_flag = Path(args.stop_flag)
    pid_file = Path(args.pid_file)
    pid_file.write_text(str(os.getpid()), encoding='ascii')
    _log(log, args.tag, f'supervisor started pid={os.getpid()}')

    while True:
        if stop_flag.exists():
            _log(log, args.tag, 'stop flag present, exit')
            break
        if log.exists() and log.stat().st_size > LOG_ROTATE_BYTES:
            log.replace(log.with_name(log.name + '.1'))
        _log(log, args.tag,
             f'starting: {args.python} {args.entry} --service {args.tag} --mode {args.mode}')
        code = subprocess.call(
            [args.python, args.entry, '--service', args.tag, '--mode', args.mode,
             '--env-file', args.env_file],
            cwd=str(REPO), creationflags=0x08000000 if os.name == 'nt' else 0)
        if stop_flag.exists():
            _log(log, args.tag, f'exited rc={code} (stop requested), exit')
            break
        _log(log, args.tag, f'exited rc={code}, restart in {RESTART_DELAY:.0f}s')
        time.sleep(RESTART_DELAY)

    pid_file.unlink(missing_ok=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
