# -*- coding: utf-8 -*-
"""INT-644 测试用并行隔离栈启动器（复用主仓库 V9.7.31 的 parallel_stack，端口整体 +3500）。

端口表（shift=+3500）：网关 8500，HTTP 8501-8510，gRPC 53551-54601，前端 vite 6273。
用 AUTH_MODE=off（UI_GATE_AUTH_MODE=off）免认证，隔离库 intelligent_audio_test_test。
不修改主仓库任何文件；PID/日志由主仓库 parallel_stack 原生管理，stop 走其 stop()。
"""
import os
import sys

MAIN_REPO = r'D:\00_code\V9.7.31\Intelligent-Audio-TEST'
if MAIN_REPO not in sys.path:
    sys.path.insert(0, MAIN_REPO)

import tests.ui.utils.parallel_stack as ps  # noqa: E402

ps.SHIFT = 3500  # 避开 6000(int-423)/7500(旧栈)/53051-53053(Docker WSL) 占用段
ps.FRONTEND_PORT = 6273  # 原值不变（vite 前端非本卡目标，仅喂 _verify_auth_mode）


if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else 'start'
    if action == 'start':
        ps.start()
    elif action == 'stop':
        ps.stop()
    else:
        ps.status()
