"""
Redis Pub/Sub 与 KV 封装 - 共享层
用于服务间 WebSocket 推送解耦，以及跨服务状态共享（如异步任务进度）。

各子服务（task_service / e2e_test_service / api_test_service）无 SocketIO 实例，
通过 Redis PubSub 发布日志/进度，由 api_gateway 订阅后转发给前端 WebSocket。
"""
import redis
import json

from shared.infrastructure.config import BaseConfig


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
        pubsub = self.redis_client.pubsub()
        pubsub.subscribe(channels)
        for message in pubsub.listen():
            if message['type'] == 'message':
                channel = message['channel']
                if isinstance(channel, bytes):
                    channel = channel.decode('utf-8')
                data = json.loads(message['data'])
                callback(channel, data)


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

