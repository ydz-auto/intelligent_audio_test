# -*- coding: utf-8 -*-
"""Benchmark 排行事件订阅（D1：事件订阅 REPORT_EVENTS）

监听 REPORT_EVENTS 频道的 REPORT_GENERATED 事件，报告生成完成后自动触发
Benchmark 排行重算（幂等，ReadModel 整体刷新）。订阅失败降级为仅手动触发，
不影响主服务启动；Redis 不可用时由 EventBus 自动重连。
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_subscriber_started = threading.Event()


def _on_report_generated(payload: dict) -> None:
    """REPORT_GENERATED 事件回调：后台触发排行重算（失败仅告警）。"""
    def _compute():
        try:
            from report_service.application.commands.benchmark_commands import (
                ComputeBenchmarkRankingCommand,
            )
            from report_service.application.services.benchmark_ranking_service import (
                BenchmarkRankingService,
            )
            result = BenchmarkRankingService().compute_ranking(ComputeBenchmarkRankingCommand())
            logger.info(
                "[benchmark_ranking][event] 报告事件触发排行重算: %s",
                result.get('message'),
            )
        except Exception:
            logger.warning("[benchmark_ranking][event] 排行重算失败", exc_info=True)

    threading.Thread(target=_compute, name='BenchmarkRankingRecompute', daemon=True).start()


def start_benchmark_ranking_subscriber():
    """启动 REPORT_EVENTS 订阅线程（幂等：重复调用仅启动一次）。"""
    if _subscriber_started.is_set():
        return None
    from shared.utils.redis_pubsub import EventBus, EventChannel, EventType

    event_bus = EventBus()
    thread = event_bus.start_subscriber(
        EventChannel.REPORT_EVENTS,
        {EventType.REPORT_GENERATED: _on_report_generated},
        name='BenchmarkRankingEventSub',
    )
    _subscriber_started.set()
    return thread
