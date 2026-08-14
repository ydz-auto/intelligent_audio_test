"""
Redis 服务注册与发现 - 共享层
基于 Redis Hash + TTL 的轻量级服务注册中心
"""
import redis
import json
import uuid
import time
import threading
import logging

from shared.infrastructure.config import BaseConfig

logger = logging.getLogger(__name__)

class RedisServiceRegistry:
    """Redis 服务注册中心"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, redis_url=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    redis_url = redis_url or BaseConfig.REDIS_URL
                    cls._instance.redis_client = redis.from_url(redis_url)
                    cls._instance.ttl = 15
                    cls._instance._heartbeat_thread = None
                    cls._instance._available = False
                    # 测试连接
                    try:
                        cls._instance.redis_client.ping()
                        cls._instance._available = True
                    except Exception as e:
                        logger.warning(f"Redis 不可用，服务注册降级为本地模式: {e}")
        return cls._instance

    def register(self, service_name, host, port, grpc_port=None, capabilities=None):
        """注册服务实例"""
        instance_id = f"{service_name}:{host}:{port}:{uuid.uuid4().hex[:6]}"
        info = {
            'name': service_name,
            'host': host,
            'port': port,
            'grpc_port': grpc_port,
            'capabilities': capabilities or {},
            'running_tasks': 0,
            'cpu_load': 0.0,
            'registered_at': time.time(),
            'last_heartbeat': time.time()
        }
        self._instance_id = instance_id
        self._info = info
        if self._available:
            try:
                self.redis_client.hset('service:instances', instance_id, json.dumps(info))
                self.redis_client.sadd(f'service:set:{service_name}', instance_id)
                self._start_heartbeat()
            except Exception as e:
                logger.warning(f"服务注册失败，降级为本地模式: {e}")
                self._available = False
        return instance_id

    def deregister(self):
        """注销服务实例"""
        if not self._available:
            return
        if hasattr(self, '_instance_id') and self._instance_id:
            self.redis_client.hdel('service:instances', self._instance_id)
            service_name = self._info.get('name', '')
            if service_name:
                self.redis_client.srem(f'service:set:{service_name}', self._instance_id)

    def discover(self, service_name):
        """发现服务实例（按负载排序）"""
        if not self._available:
            return []
        instance_ids = self.redis_client.smembers(f'service:set:{service_name}')
        result = []
        for iid in instance_ids:
            data = self.redis_client.hget('service:instances', iid)
            if data:
                info = json.loads(data)
                if info.get('running_tasks') is not None:
                    result.append(info)
        return sorted(result, key=lambda x: x.get('running_tasks', 0))
    
    def get_one(self, service_name):
        """获取一个最空闲的实例"""
        instances = self.discover(service_name)
        return instances[0] if instances else None
    
    def update_load(self, running_tasks, cpu_load=0.0):
        """更新本实例负载"""
        if not self._available or not hasattr(self, '_instance_id') or not self._instance_id:
            return
        self._info['running_tasks'] = running_tasks
        self._info['cpu_load'] = cpu_load
        self._info['last_heartbeat'] = time.time()
        self.redis_client.hset('service:instances', self._instance_id, json.dumps(self._info))
    
    def _start_heartbeat(self):
        """心跳续期线程"""
        def beat():
            while True:
                try:
                    self._info['last_heartbeat'] = time.time()
                    self.redis_client.hset('service:instances', self._instance_id, json.dumps(self._info))
                except Exception:
                    logger.debug("心跳续期失败", exc_info=True)
                time.sleep(self.ttl // 3)
        self._heartbeat_thread = threading.Thread(target=beat, daemon=True)
        self._heartbeat_thread.start()
