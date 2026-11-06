# -*- coding: utf-8 -*-
"""报告请求预算（INT-1572 返工二轮）。

一次报告请求（一次 gRPC 调用）有自己的总时限——网关对 report_service 的调用
截止默认 60s。请求内的各个阶段（跨域用例取数 / 结果聚合 / 渲染）共用这一个
预算，任何一段独占预算都会把整次请求顶过截止（INT-1482 复测：ACL 整批截止
40s + 结果段 60s = 100s，直连 gRPC 也超）。故在 interfaces 层把 gRPC 的剩余
时限记进请求上下文，跨域 ACL 按「剩余预算 - 预留」而不是固定值收尾。

不放进 contextvar 的场景（如报告生成线程池里的后台任务）读不到预算，
调用方按配置的固定兜底值处理。
"""
from __future__ import annotations

import contextvars
import time
from typing import Optional

# 截止时刻（time.monotonic 口径）；None 表示本次调用没有可用预算
_deadline_at: contextvars.ContextVar[Optional[float]] = contextvars.ContextVar(
    'report_request_deadline_at', default=None)


class RequestBudget:
    """请求预算上下文：进入时记录截止时刻，退出时恢复。"""

    def __init__(self, seconds: float):
        self._seconds = max(float(seconds), 0.0)
        self._token = None

    def __enter__(self):
        self._token = _deadline_at.set(time.monotonic() + self._seconds)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._token is not None:
            _deadline_at.reset(self._token)
            self._token = None
        return False


def budget_from_grpc_context(context) -> Optional[float]:
    """从 gRPC servicer 的 context 读本次调用的剩余时限（秒）。

    无 context（单测 / 进程内调用）或调用方未设截止时返回 None。
    """
    if context is None:
        return None
    try:
        remaining = context.time_remaining()
    except Exception:  # pragma: no cover - 非 gRPC context 实现
        return None
    if remaining is None:
        return None
    remaining = float(remaining)
    # grpc 用极大值表示「无截止」
    if remaining <= 0 or remaining > 3600:
        return None
    return remaining


def remaining_seconds(reserve: float = 0.0) -> Optional[float]:
    """本次请求还剩多少预算（秒）；没有预算上下文时返回 None。

    Args:
        reserve: 预留给后续阶段的秒数（负数结果归零）。
    """
    deadline_at = _deadline_at.get()
    if deadline_at is None:
        return None
    return max(0.0, deadline_at - time.monotonic() - float(reserve))
