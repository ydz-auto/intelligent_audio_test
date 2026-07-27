"""
Redis Pub/Sub 封装 - 共享层
用于服务间 WebSocket 推送解耦
"""
import redis
import json
import os

class RedisPubSub:
    _instance = None
    
    def __new__(cls, redis_url=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            redis_url = redis_url or os.environ.get('REDIS_URL', 'redis://localhost:6379')
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
