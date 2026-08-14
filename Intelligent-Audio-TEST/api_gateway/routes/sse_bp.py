"""
SSE 事件流 —— 通过 Redis PubSub 订阅实时事件并推送给前端

频道映射：
- task_logs      → event: task_log
- task_progress  → event: task_progress
- sse_events     → event: 由消息体 event 字段决定（如 report_generated）
"""
import json
import logging

import redis as redis_lib
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from api_gateway.application.services.auth.dependencies import require_permission

logger = logging.getLogger(__name__)

router = APIRouter()


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


@router.get('/events')
def stream_events(_: None = require_permission('sse:read')):
    """SSE 事件流端点 — 订阅 Redis PubSub 频道，实时推送日志/进度/报告事件"""
    def generate():
        from shared.infrastructure.config import BaseConfig
        r = redis_lib.from_url(BaseConfig.REDIS_URL)
        pubsub = r.pubsub()
        pubsub.subscribe(['task_logs', 'task_progress', 'sse_events'])
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
                if channel == 'task_logs':
                    yield format_sse(data, event='task_log')
                elif channel == 'task_progress':
                    yield format_sse(data, event='task_progress')
                elif channel == 'sse_events':
                    event_name = data.pop('event', 'report') if isinstance(data, dict) else 'report'
                    yield format_sse(data.get('data', data) if isinstance(data, dict) else data, event=event_name)
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
