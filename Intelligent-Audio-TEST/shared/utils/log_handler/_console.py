"""控制台安全输出（INT-102）。

stdout/stderr 可能是坏管道（启动器转发线程死亡后 PIPE 无人消化、
管道断裂）或受限编码（中文 Windows GBK 重定向文件遇 U+FFFD 等
GBK 外字符）。日志的控制台直打一旦抛异常会沿调用链炸进业务路径
（已证实：audio_service 用例自动创建被 sys.stdout.flush() 的
OSError: [Errno 22] Invalid argument 炸成 merge 400）。
日志出口必须自防御：写失败静默丢弃，绝不向调用方传播。
"""

import sys


def safe_console_print(text, file=None):
    """print 到指定流（默认 stdout）并 flush；任何失败静默丢弃。"""
    try:
        print(text, file=file if file is not None else sys.stdout, flush=True)
    except Exception:
        pass
