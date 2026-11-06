# -*- coding: utf-8 -*-
"""日志上下文（INT-81）：轮次/评估ID 的线程级上下文。

跨层传递轮次上下文用：E2E 轮次循环、评估端点 Worker 在进入单轮处理前
set_current_round()，该线程内后续所有业务日志自动落到对应轮次目录，
无需逐个调用点显式传 round。
"""
import threading
from contextlib import contextmanager

_ctx = threading.local()


def set_current_round(round_value) -> None:
    """设置当前线程的轮次上下文（None 清除）。"""
    _ctx.current_round = round_value


def get_current_round():
    """读取当前线程的轮次上下文，未设置返回 None。"""
    return getattr(_ctx, 'current_round', None)


def set_current_evaluation_id(evaluation_id) -> None:
    """设置当前线程的评估ID上下文（None 清除）。"""
    _ctx.current_evaluation_id = evaluation_id


def get_current_evaluation_id():
    """读取当前线程的评估ID上下文，未设置返回 None。"""
    return getattr(_ctx, 'current_evaluation_id', None)


@contextmanager
def log_round(round_value):
    """上下文管理器：范围内业务日志归属指定轮次，退出自动清除。"""
    set_current_round(round_value)
    try:
        yield
    finally:
        set_current_round(None)
