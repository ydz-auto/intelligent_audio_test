# -*- coding: utf-8 -*-
"""Realtime 流式双通道推送发布器（INT-61）— 基础设施层

frame（逐帧）/ summary（会话汇总）双通道：
- 领域事件经 EventBus REPORT_EVENTS 频道（事件类型枚举化）；
- 前端 SSE 经既有 sse_events 桥（api_gateway sse_bp 转发，event 名 = 通道名），
  网关零改动，前端按 realtime_frame / realtime_summary 订阅渲染。

Redis 不可用时静默降级（不阻塞会话执行），与 EventBus 发布降级语义一致。
"""
from __future__ import annotations

import logging

from shared.models.common_enums import RealtimeChannel
from shared.utils.redis_pubsub import (
    EventBus,
    EventChannel,
    EventType,
    RedisPubSub,
)

logger = logging.getLogger(__name__)


class RealtimeStreamPublisher:
    """Realtime 双通道事件发布"""

    def __init__(self, event_bus: EventBus = None):
        self._event_bus = event_bus or EventBus()

    def publish_frame(self, task_id, test_case_id, session_id, round_number,
                      seq: int, frame: dict) -> None:
        """推送单帧到 frame 通道（载荷轻量：归一化类型 + 摘要，不含原始音频）"""
        payload = {
            'task_id': str(task_id),
            'test_case_id': str(test_case_id),
            'session_id': session_id,
            'round_number': round_number,
            'seq': seq,
            'channel': RealtimeChannel.FRAME.value,
            'type': frame.get('type'),
            'payload': frame.get('payload'),
            'ts': frame.get('ts'),
        }
        self._emit(RealtimeChannel.FRAME, payload)

    def publish_summary(self, task_id, test_case_id, session_id, summary: dict) -> None:
        """推送会话汇总到 summary 通道"""
        payload = {
            'task_id': str(task_id),
            'test_case_id': str(test_case_id),
            'session_id': session_id,
            'channel': RealtimeChannel.SUMMARY.value,
            **summary,
        }
        self._emit(RealtimeChannel.SUMMARY, payload)

    def _emit(self, channel: RealtimeChannel, payload: dict) -> None:
        event_type = (
            EventType.REALTIME_FRAME if channel == RealtimeChannel.FRAME
            else EventType.REALTIME_SUMMARY
        )
        try:
            self._event_bus.publish(EventChannel.REPORT_EVENTS, event_type, payload)
        except Exception as e:
            logger.warning(f"发布 Realtime 领域事件 {channel.value} 失败: {e}")
        try:
            RedisPubSub().publish('sse_events', {'event': channel.value, 'data': payload})
        except Exception as e:
            logger.warning(f"发布 Realtime SSE 事件 {channel.value} 失败: {e}")
