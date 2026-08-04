"""DatabaseLogHandler WebSocket 推送相关方法（Mixin）。

从原 log_handler.py 拆分而来，保持行为不变。
"""

from datetime import datetime, timezone, timedelta

from . import _state


class _WebSocketMixin:
    """日志 WebSocket 推送（直连回调 / Redis PubSub 转发）。"""

    def _emit_websocket(self, data):
        """
        推送日志到前端。
        - api_gateway 进程：有 _ws_broadcast_callback（Socket.IO），直接调用推送。
        - task_service / e2e_test_service 等子服务进程：无 callback，
          通过 Redis PubSub 发布到 task_logs 频道，由 api_gateway 订阅后转发给前端。
        """
        # 只有成功入库（拿到 id）才推送，避免前端显示不存在的日志
        if data.get('id') is None and data.get('_db_failed'):
            return

        # 1) api_gateway 进程：有 WebSocket 广播回调，直接推送
        if _state._ws_broadcast_callback is not None:
            try:
                _state._ws_broadcast_callback(data)
                return
            except Exception as ws_error:
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - WS CALLBACK ERROR - {str(ws_error)}")

        # 2) 子服务进程：无 callback，通过 Redis PubSub 发布给 api_gateway 转发
        self._publish_via_redis(data)

    def _publish_via_redis(self, data):
        """当前进程无 WebSocket 时，通过 Redis PubSub 发布日志给 api_gateway 转发"""
        try:
            if self._redis_pubsub is None:
                from shared.utils.redis_pubsub import RedisPubSub
                self._redis_pubsub = RedisPubSub()
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
            }
            self._redis_pubsub.publish('task_logs', message)
        except Exception as e:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - REDIS PUB ERROR - {str(e)}")
