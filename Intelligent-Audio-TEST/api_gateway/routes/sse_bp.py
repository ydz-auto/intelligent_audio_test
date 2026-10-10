"""
SSE 事件流 —— 订阅 EventBus 五通道，实时推送日志/进度/报告事件给前端

事件映射（UC-1001 五通道收敛）：
- TASK_EVENTS / task_log      → event: task_log（payload 为日志信封）
- TASK_EVENTS / task_progress → event: task_progress
- TASK_EVENTS / import_progress → event: import_progress
- REPORT_EVENTS / report_generated、secondary_compare_generated → event: 同名
- REPORT_EVENTS / realtime_frame、realtime_summary → event: realtime_frame / realtime_summary
"""
import json
import logging

import redis as redis_lib
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from api_gateway.application.services.auth.dependencies import require_permission

logger = logging.getLogger(__name__)

router = APIRouter()

# 模块级 Redis 客户端单例：SSE 连接复用同一连接，避免每连接新建导致连接/内存膨胀
_redis_client = None


def _get_redis():
    """惰性创建并复用模块级 Redis 客户端"""
    global _redis_client
    if _redis_client is None:
        from shared.infrastructure.config import BaseConfig
        _redis_client = redis_lib.from_url(BaseConfig.REDIS_URL)
    return _redis_client


def format_sse(data, event=None, event_id=None):
    """格式化 SSE 事件"""
    messages = []
    if event_id:
        messages.append(f"id: {event_id}")
    if event:
        messages.append(f"event: {event}")
    if isinstance(data, (dict, list)):
        messages.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    else:
        messages.append(f"data: {data}")
    messages.append("")
    return "\n".join(messages) + "\n\n"


# EventBus 消息 → (SSE 事件名, 下发数据) 的映射；返回 None 表示不推送给 SSE
def _map_event(channel: str, data: dict):
    from shared.utils.redis_pubsub import EventChannel

    event_type = data.get('event_type', '')
    payload = data.get('payload')
    if not isinstance(payload, dict):
        return None

    if channel == EventChannel.TASK_EVENTS.value:
        if event_type == 'task_log':
            return 'task_log', payload
        if event_type == 'task_progress':
            return 'task_progress', payload.get('data') or {}
        if event_type == 'import_progress':
            return 'import_progress', payload.get('data') or {}
        return None

    if channel == EventChannel.REPORT_EVENTS.value:
        if event_type in ('report_generated', 'secondary_compare_generated'):
            return payload.get('event', event_type), payload.get('data') or {}
        if event_type in ('realtime_frame', 'realtime_summary'):
            return event_type, payload
        return None

    return None


@router.get('/events')
def stream_events(_: None = require_permission('sse:read')):
    """SSE 事件流端点 — 订阅 EventBus 五通道，实时推送日志/进度/报告事件"""
    from shared.utils.redis_pubsub import EventChannel

    def generate():
        r = _get_redis()
        pubsub = r.pubsub()
        pubsub.subscribe([c.value for c in EventChannel])
        try:
            while True:
                message = pubsub.get_message(timeout=1.0)
                if message is None:
                    # 心跳注释，保持连接存活
                    yield ': heartbeat\n\n'
                    continue
                if message.get('type') != 'message':
                    continue
                channel = message['channel']
                if isinstance(channel, bytes):
                    channel = channel.decode('utf-8')
                try:
                    data = json.loads(message['data'])
                except (json.JSONDecodeError, TypeError):
                    continue
                try:
                    mapped = _map_event(channel, data)
                except Exception:
                    logger.debug("SSE 事件映射失败 channel=%s", channel, exc_info=True)
                    continue
                if mapped is None:
                    continue
                event_name, out = mapped
                yield format_sse(out, event=event_name)
        finally:
            try:
                pubsub.close()
            except Exception:
                logger.debug("关闭 Redis pubsub 失败", exc_info=True)

    return StreamingResponse(
        generate(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )
