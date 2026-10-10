# -*- coding: utf-8 -*-
"""EventBus 五通道事件转发器（UC-1001 / INT-69）

api_gateway 唯一的事件入站口：订阅 EventChannel 五通道（TASK / CASE / DEVICE /
REPORT / CONFIG），把面向前端的实时事件转发给 Socket.IO。业务事件（任务完成、
用例执行完成等）由各服务各自订阅处理，本转发器忽略。

事件 → 前端契约：
- TASK_EVENTS / task_log      → '/ws/logs' task_log（room=task:{task_id} 原生房间）
- TASK_EVENTS / task_progress → '/' task_progress
- TASK_EVENTS / import_progress → '/' import_progress（INT-25）
- TASK_EVENTS / task_alert    → '/' error_alert
- REPORT_EVENTS / report_generated、secondary_compare_generated → '/' 同名事件
- REPORT_EVENTS / realtime_frame、realtime_summary → 仅 SSE（见 routes/sse_bp.py）
"""
import logging
import threading

from shared.utils.redis_pubsub import EventChannel, RedisPubSub

logger = logging.getLogger(__name__)

# (channel.value, event_type.value) → (socket 事件名, payload 提取键)
# payload 提取键 None 表示整个 payload 原样下发
_SOCKET_FORWARD_MAP = {
    (EventChannel.TASK_EVENTS.value, 'task_progress'): ('task_progress', 'data'),
    (EventChannel.TASK_EVENTS.value, 'import_progress'): ('import_progress', 'data'),
    (EventChannel.TASK_EVENTS.value, 'task_alert'): ('error_alert', 'data'),
    (EventChannel.REPORT_EVENTS.value, 'report_generated'): ('report_generated', 'data'),
    (EventChannel.REPORT_EVENTS.value, 'secondary_compare_generated'): ('secondary_compare_generated', 'data'),
}

# 仅转 SSE 的事件（无 Socket.IO 消费方）
_SSE_ONLY_EVENT_TYPES = {'realtime_frame', 'realtime_summary'}


def start_event_forwarder(ws_manager) -> threading.Thread:
    """启动五通道订阅转发线程（daemon），返回线程句柄。"""
    t = threading.Thread(target=_forwarder_loop, args=(ws_manager,),
                         name='EventBusForwarder', daemon=True)
    t.start()
    return t


def _forwarder_loop(ws_manager):
    channels = [c.value for c in EventChannel]
    logger.info("[EventForwarder] subscribing five channels: %s", channels)
    RedisPubSub().subscribe(channels, lambda channel, data: _dispatch(channel, data, ws_manager))


def _dispatch(channel: str, data: dict, ws_manager) -> None:
    """按 (channel, event_type) 分发一条 EventBus 消息到前端 Socket.IO"""
    if not isinstance(data, dict):
        return
    event_type = data.get('event_type', '')
    payload = data.get('payload')

    if channel == EventChannel.TASK_EVENTS.value and event_type == 'task_log':
        # 日志推送：payload 即 {'log_payload': ..., 'task_id': ...} 信封
        if isinstance(payload, dict):
            ws_manager.broadcast_log_sync(payload)
        return

    if event_type in _SSE_ONLY_EVENT_TYPES:
        return

    mapped = _SOCKET_FORWARD_MAP.get((channel, event_type))
    if not mapped:
        return  # 业务事件由各服务订阅处理，前端不消费
    socket_event, extract_key = mapped
    if not isinstance(payload, dict):
        return
    out = payload.get(extract_key) if extract_key else payload
    if out is None:
        out = {}
    ws_manager.emit_sync(socket_event, out)
