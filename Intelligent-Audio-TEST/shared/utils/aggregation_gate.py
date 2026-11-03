# -*- coding: utf-8 -*-
"""大体量 include_body 聚合的进程级并发护栏（INT-2379 C6）。

背景：带 `api_raw_response` 的维度结果聚合会把整份原始响应映射常驻内存，
真实任务实测单次峰值约 2.78GB（report_service 容器 cgroup peak）。在
「查询（GetCaseAverages）与报告生成」并发、或两个查询并发时，两份映射叠加
会直接把共享 VM 打穿。

INT-2379 C6 的过渡护栏：同一进程内只允许一个大体量 include_body 聚合处于
「拉取 + 行级合并」段，后到的请求排队等待。可重入（按线程计深度），因此
ACL 拉取层与上层聚合入口可以嵌套使用同一把门而不自锁。

超时口径（卡面要求确认）：网关 → report_service 的默认 gRPC deadline 为 60s，
单个大查询实测约 28s。护栏等待上限默认 20s（`REPORT_INCLUDE_BODY_GATE_TIMEOUT`
可调），超时后**不再排队、直接放行**（退化为原并发行为），避免排队本身把请求
推过 deadline；放行会记 WARNING，便于观测。

说明：本护栏只覆盖内存峰值构建段；调用方后续持有合并后映射做指标计算的
时段不在此锁内，彻底解决需等「分块提取压缩」卡落地。护栏不改变请求的
业务语义与响应内容，仅串行化执行。
"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_SEMAPHORE = threading.BoundedSemaphore(1)
_STATE = threading.local()


def _default_timeout() -> float:
    try:
        return max(float(os.getenv('REPORT_INCLUDE_BODY_GATE_TIMEOUT', '20')), 0.0)
    except (TypeError, ValueError):
        return 20.0


@contextmanager
def heavy_include_body_aggregation(timeout=None):
    """进入大体量 include_body 聚合的串行段（线程内可重入）。

    Args:
        timeout: 等待名额的秒数；None 时取 REPORT_INCLUDE_BODY_GATE_TIMEOUT（默认 20s）。
            超时后放行（不加锁），保证不改变既有请求超时口径。
    """
    depth = getattr(_STATE, 'depth', 0)
    acquired = True
    if depth == 0:
        wait = _default_timeout() if timeout is None else max(float(timeout), 0.0)
        acquired = _SEMAPHORE.acquire(timeout=wait) if wait > 0 else _SEMAPHORE.acquire(False)
        if not acquired:
            logger.warning(
                "include_body 聚合护栏等待超过 %.1fs，本次放行（可能并发叠加内存峰值）",
                wait)
    _STATE.depth = depth + 1
    try:
        yield
    finally:
        _STATE.depth -= 1
        if _STATE.depth == 0 and acquired:
            _SEMAPHORE.release()
