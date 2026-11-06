# -*- coding: utf-8 -*-
"""INT-622 专用并行隔离栈（端口整体 +1200，前端 6374）——复用标准启动器，仅改端口。

背景：标准并行栈前端端口 6273 被其它在途 run 占用（`_refuse_if_busy` 拒绝启动），
本卡（INT-622 P1 修复回归）需要一套独立隔离栈验证修改后的前端代码，故整体换偏移
端口复用 parallel_stack 的起栈/监督/停止逻辑，互不干扰。

端口表（shift=+1200）：网关 6200，HTTP 服务 6201-6210，gRPC 51251-51301，
前端 vite 6374（VITE_API_TARGET=http://127.0.0.1:6200）。

用法（本卡专用，WMI 脱离进程树启动；清理用同文件 stop）：
    python tests/ui/utils/parallel_stack_622.py start
    python tests/ui/utils/parallel_stack_622.py stop
    python tests/ui/utils/parallel_stack_622.py status
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(BASE_DIR, 'tests', 'ui', 'utils'))

import parallel_stack as ps  # noqa: E402

# 换偏移端口，避开被占用的标准并行栈端口（6000-6010/6273）
ps.SHIFT = 1200
ps.GATEWAY_HTTP = 5000 + ps.SHIFT          # 6200
ps.FRONTEND_PORT = 6374
ps.PID_FILE = os.path.join(ps.BASE_DIR, 'tests', 'ui', '_ui_stack_622.pid')
ps.LOG_DIR = os.path.join(ps.BASE_DIR, 'logs', 'ui_stack_622')

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='INT-622 UI 专用并行隔离栈（端口+1200，前端 6374）')
    parser.add_argument('cmd', choices=['start', 'stop', 'status'])
    args = parser.parse_args()
    if args.cmd == 'start':
        ps.start()
    elif args.cmd == 'stop':
        ps.stop()
    else:
        ps.status()
