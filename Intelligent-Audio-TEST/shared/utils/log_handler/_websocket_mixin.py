"""DatabaseLogHandler WebSocket 推送相关方法（Mixin）。

从原 log_handler.py 拆分而来。
UC-1001（INT-69）：日志推送统一经 EventBus TASK_EVENTS / task_log 事件发布，
由 api_gateway 订阅五通道后转发前端 Socket.IO —— 各服务进程（含 api_gateway
自身）走同一条总线链路，不再直连 WebSocket、不再使用裸字符串频道。
"""

from datetime import datetime, timezone, timedelta


class _WebSocketMixin:
    """日志 WebSocket 推送（统一 EventBus 链路）。"""

    def _emit_websocket(self, data):
        """
        推送日志到前端（统一经 EventBus 发布）。
        - api_gateway 进程：订阅 TASK_EVENTS 收到 task_log 事件后转发 Socket.IO；
        - task_service / e2e_test_service 等子服务进程：同一条总线，api_gateway 统一转发。
        Redis 不可用时 EventBus.publish 内部降级只打日志，不影响日志入库主流程。
        """
        # 只有成功入库（拿到 id）才推送，避免前端显示不存在的日志
        if data.get('id') is None and data.get('_db_failed'):
            return

        try:
            from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
            utc_plus_8 = timezone(timedelta(hours=8))
            log_time = data.get('_ws_time') or datetime.now(utc_plus_8).strftime('%Y-%m-%d %H:%M:%S')
            log_payload = {
                "id": data.get('id'),
                "time": log_time,
                "level": data['level'],
                "module": data['module'],
                "content": data['content'],
                "mark": "",
                "task_id": data.get('task_id'),
                "test_case_id": data.get('test_case_id'),
                "category": data.get('category'),
                "source": data.get('source'),
            }
            message = {
                'log_payload': log_payload,
                'task_id': data.get('task_id'),
                'test_case_id': data.get('test_case_id'),
            }
            EventBus().publish(EventChannel.TASK_EVENTS, EventType.TASK_LOG, message)
        except Exception as e:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - REDIS PUB ERROR - {str(e)}")
