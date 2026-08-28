"""
Redis Pub/Sub 与 KV 封装 - 共享层
用于服务间 WebSocket 推送解耦，以及跨服务状态共享（如异步任务进度）。

各子服务（task_service / e2e_test_service / api_test_service）无 SocketIO 实例，
通过 Redis PubSub 发布日志/进度，由 api_gateway 订阅后转发给前端 WebSocket。
"""
import redis
import json
import logging
import threading
from enum import Enum

from shared.infrastructure.config import BaseConfig

logger = logging.getLogger(__name__)


# ========== 事件总线枚举 ==========

class EventChannel(str, Enum):
    """Redis 事件总线频道枚举 — 禁止裸字符串"""
    TASK_EVENTS = 'task_events'          # 任务级事件（创建/完成/停止）
    CASE_EVENTS = 'case_events'         # 用例级事件（执行完成/评估完成）
    DEVICE_EVENTS = 'device_events'     # 设备状态变更事件
    REPORT_EVENTS = 'report_events'    # 报告生成事件
    CONFIG_EVENTS = 'config_events'     # 配置变更事件（维度 CRUD 等）


class EventType(str, Enum):
    """事件类型枚举 — 各服务发布事件时必须使用此枚举"""
    # 任务级
    TASK_CREATED = 'task_created'
    TASK_COMPLETED = 'task_completed'
    TASK_FAILED = 'task_failed'
    TASK_STOPPED = 'task_stopped'
    # 用例级
    CASE_EXECUTION_COMPLETED = 'case_execution_completed'
    CASE_EVALUATION_COMPLETED = 'case_evaluation_completed'
    CASE_FAILED = 'case_failed'
    # 设备级
    DEVICE_STATUS_CHANGED = 'device_status_changed'
    # 报告级
    REPORT_GENERATED = 'report_generated'
    # 配置级
    DIMENSION_CONFIG_CHANGED = 'dimension_config_changed'


# ========== Redis Pub/Sub 封装 ==========

class RedisPubSub:
    _instance = None

    def __new__(cls, redis_url=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            redis_url = redis_url or BaseConfig.REDIS_URL
            cls._instance.redis_client = redis.from_url(redis_url)
        return cls._instance

    def publish(self, channel, message):
        self.redis_client.publish(channel, json.dumps(message, ensure_ascii=False))

    def publish_progress(self, task_id, progress_data):
        self.publish('task_progress', {'task_id': task_id, **progress_data})

    def publish_log(self, task_id, log_data):
        self.publish('task_logs', {'task_id': task_id, **log_data})

    def publish_device_status(self, device_id, status_data):
        self.publish('device_status', {'device_id': device_id, **status_data})

    def subscribe(self, channels, callback):
        """订阅 Redis 频道，监听消息并回调。带自动重连。

        阻塞方法，应在后台线程中调用。Redis 断开后等待 3 秒重连。
        """
        import time
        while True:
            try:
                pubsub = self.redis_client.pubsub()
                pubsub.subscribe(channels)
                for message in pubsub.listen():
                    if message['type'] == 'message':
                        channel = message['channel']
                        if isinstance(channel, bytes):
                            channel = channel.decode('utf-8')
                        data = json.loads(message['data'])
                        callback(channel, data)
            except Exception as e:
                print(f"[RedisPubSub] connection lost: {e}, retrying in 3s...", flush=True)
                time.sleep(3)


# ========== 事件总线 ==========

class EventBus:
    """跨服务事件总线（基于 Redis Pub/Sub）

    各服务完成操作后发布事件，消费方订阅处理，实现服务间解耦。
    替代 gRPC 同步回传，支持故障降级（Redis 不可用时只打日志不阻塞业务）。

    用法:
        # 发布事件
        EventBus().publish(EventChannel.CASE_EVENTS, EventType.CASE_EVALUATION_COMPLETED, {
            'task_id': 123, 'test_case_id': 'abc', 'result_id': 456, 'success': True
        })

        # 订阅事件（在后台线程中调用）
        EventBus().subscribe_events(
            EventChannel.CASE_EVENTS,
            {EventType.CASE_EVALUATION_COMPLETED: on_case_evaluated},
        )
    """

    def __init__(self, redis_url=None):
        self._pubsub = RedisPubSub(redis_url)

    @property
    def _client(self):
        """获取 Redis 客户端（复用 RedisPubSub 单例连接）"""
        return self._pubsub.redis_client

    def publish(self, channel: EventChannel, event_type: EventType, payload: dict) -> None:
        """发布领域事件到指定频道

        Args:
            channel: 事件频道（EventChannel 枚举）
            event_type: 事件类型（EventType 枚举）
            payload: 事件数据 dict
        """
        message = {
            'event_type': event_type.value,
            'payload': payload,
        }
        try:
            self._pubsub.publish(channel.value, message)
        except Exception as e:
            logger.warning(f"[EventBus] 发布事件 {event_type.value} 到 {channel.value} 失败: {e}")

    def subscribe_events(self, channel: EventChannel, handlers: dict) -> None:
        """订阅指定频道的事件，按 event_type 分发到不同 handler

        阻塞方法，应在后台线程中调用。

        Args:
            channel: 事件频道（EventChannel 枚举）
            handlers: {EventType: callback(payload_dict)} 映射
        """
        import time
        handler_map = {et.value: cb for et, cb in handlers.items()}
        while True:
            try:
                pubsub = self._client.pubsub()
                pubsub.subscribe(channel.value)
                for message in pubsub.listen():
                    if message['type'] != 'message':
                        continue
                    try:
                        data = json.loads(message['data'])
                        event_type = data.get('event_type', '')
                        payload = data.get('payload', {})
                        handler = handler_map.get(event_type)
                        if handler:
                            handler(payload)
                    except Exception as e:
                        logger.error(f"[EventBus] 处理 {channel.value} 事件异常: {e}")
            except Exception as e:
                logger.warning(f"[EventBus] {channel.value} 连接断开: {e}，3秒后重连")
                time.sleep(3)

    def start_subscriber(self, channel: EventChannel, handlers: dict, name: str = None) -> threading.Thread:
        """在后台线程中启动事件订阅

        Args:
            channel: 事件频道
            handlers: {EventType: callback(payload_dict)} 映射
            name: 线程名

        Returns:
            启动的后台线程
        """
        thread = threading.Thread(
            target=self.subscribe_events,
            args=(channel, handlers),
            name=name or f'EventSub-{channel.value}',
            daemon=True,
        )
        thread.start()
        return thread


class RedisStore:
    """跨服务共享的 Redis KV 存储（替代进程内 dict）。

    用于异步任务状态等需要跨进程读取的临时数据。
    每条记录用 HASH 存储，字段对应任务进度字段。
    自带 TTL，避免内存泄漏。
    """
    _instance = None

    def __new__(cls, redis_url=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            redis_url = redis_url or BaseConfig.REDIS_URL
            cls._instance.redis_client = redis.from_url(redis_url)
        return cls._instance

    def save_task(self, key: str, fields: dict, ttl_seconds: int = 86400) -> None:
        """保存任务进度字段（HASH）。ttl_seconds=0 表示不过期。"""
        if not fields:
            return
        pipe = self.redis_client.pipeline()
        pipe.hset(key, mapping={k: json.dumps(v, ensure_ascii=False) for k, v in fields.items()})
        if ttl_seconds > 0:
            pipe.expire(key, ttl_seconds)
        pipe.execute()

    def load_task(self, key: str) -> dict:
        """读取任务进度字段，自动反 JSON。key 不存在返回空 dict。"""
        raw = self.redis_client.hgetall(key)
        if not raw:
            return {}
        result = {}
        for k, v in raw.items():
            if isinstance(k, bytes):
                k = k.decode('utf-8')
            if isinstance(v, bytes):
                v = v.decode('utf-8')
            try:
                result[k] = json.loads(v)
            except Exception:
                result[k] = v
        return result

    def delete_task(self, key: str) -> None:
        self.redis_client.delete(key)

