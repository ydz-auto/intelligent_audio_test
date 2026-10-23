# -*- coding: utf-8 -*-
"""INT-1470 测试 run 临时：无前端后端隔离栈（复用 parallel_stack 端口/环境口径）。

用法：python _int1470_stack.py [shift]   （前台监督；本 run 结束前用 stop 收尾）
本文件为临时探针，run 结束时删除。
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SHIFT = int(sys.argv[1]) if len(sys.argv) > 1 else 2600
os.environ['UI_STACK_SHIFT'] = str(SHIFT)
os.environ['AUTH_MODE'] = 'off'
os.environ['UI_GATE_AUTH_MODE'] = 'off'
sys.path.insert(0, os.path.join(HERE, 'tests', 'ui', 'utils'))

import parallel_stack as ps  # noqa: E402

ps.configure(SHIFT, None)

PID_FILE = os.path.join(HERE, 'tests', 'ui', f'_ui_stack_{SHIFT}_backend.pid')


def main():
    ps._ensure_postgres()
    ps._refuse_if_busy()
    os.makedirs(ps.LOG_DIR, exist_ok=True)
    base_env = ps._base_env()
    log = open(os.path.join(ps.LOG_DIR, f'int1470_backend_{SHIFT}.log'), 'ab')
    procs = []
    for name, svc_dir, http_port, grpc_port in ps.SERVICES:
        env = dict(base_env)
        cmd = ps._service_cmd(name, svc_dir,
                              ps._shift(http_port) if http_port else None,
                              ps._shift(grpc_port) if grpc_port else None, env)
        log.write(f'\n[START] {name}: {" ".join(cmd[:6])}\n'.encode())
        log.flush()
        procs.append((name, subprocess.Popen(cmd, cwd=ps.BASE_DIR, env=env,
                                             stdout=log, stderr=subprocess.STDOUT)))
    with open(PID_FILE, 'w', encoding='ascii') as fh:
        fh.write(f'{os.getpid()}\nshift={SHIFT}\n')
    print(f'[INT1470] started {len(procs)} svc, gw :{ps.GATEWAY_HTTP}, db {ps.DB_NAME}', flush=True)
    ps.wait_ready()
    print('[INT1470] supervising', flush=True)
    while True:
        time.sleep(3)
        for name, p in procs:
            if p.poll() is not None:
                print(f'[INT1470] {name} exited {p.returncode}; stopping all', flush=True)
                for _, q in procs:
                    if q.poll() is None:
                        q.terminate()
                return


if __name__ == '__main__':
    main()
