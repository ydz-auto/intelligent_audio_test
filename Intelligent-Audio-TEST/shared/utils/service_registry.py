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
        """发现服务实例（按负载排序）

        返回的每个 info 额外携带 instance_id 键（Redis Hash 的 field 名），
        供任务创建方选择归属实例（选 running_tasks 最少者）。
        """
        if not self._available:
            return []
        instance_ids = self.redis_client.smembers(f'service:set:{service_name}')
        result = []
        for iid in instance_ids:
            data = self.redis_client.hget('service:instances', iid)
            if data:
                info = json.loads(data)
                if info.get('running_tasks') is not None:
                    info['instance_id'] = iid.decode() if isinstance(iid, bytes) else iid
                    result.append(info)
        return sorted(result, key=lambda x: x.get('running_tasks', 0))
    
    def get_one(self, service_name):
        """获取一个最空闲的实例"""
        instances = self.discover(service_name)
        return instances[0] if instances else None

    def get_alive_ids(self, service_name, ttl=None):
        """返回心跳新鲜（未过期）的实例 ID 集合。

        多实例归属判定用：已注册但心跳停滞超过 ttl 的实例视为下线，
        其名下任务可被其他实例收养（见 SchedulerMixin._adopt_orphan_tasks）。
        Redis 不可用时返回空集合（降级为单实例语义）。

        Args:
            service_name: 服务名，如 'task_service'
            ttl: 心跳过期阈值（秒），默认取注册表 TTL（15s）
        """
        if not self._available:
            return set()
        ttl = ttl or self.ttl
        instance_ids = self.redis_client.smembers(f'service:set:{service_name}')
        alive = set()
        for iid in instance_ids:
            iid = iid.decode() if isinstance(iid, bytes) else iid
            try:
                data = self.redis_client.hget('service:instances', iid)
                if not data:
                    continue
                info = json.loads(data)
                hb = info.get('last_heartbeat', 0)
                if time.time() - float(hb) <= ttl:
                    alive.add(iid)
            except Exception:
                logger.debug("读取实例心跳失败，忽略: %s", iid, exc_info=True)
                continue
        return alive
    
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
