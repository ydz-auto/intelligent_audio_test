# -*- coding: utf-8 -*-
"""Realtime 会话实例亲和注册表（INT-61）

api_test_service 双副本部署下，Realtime WS 长连接封闭在接单实例内存中，
同会话（task 粒度）的后续请求必须粘住同一实例。本注册表基于 Redis
session:bind:{task_id} 记录 task → 实例 绑定：

- bind：会话建立时写入绑定（带 TTL，实例崩溃后由 TTL 自然过期）
- resolve：查询绑定。绑定健康实例时原样返回（亲和）；绑定实例已失联
  （不在服务注册存活集合，实例重启场景）或 TTL 已过期时，重绑定到
  当前实例（新会话重路由）
- release：会话结束主动清除

Redis 不可用时降级为「视当前实例为绑定方」（单实例语义），不阻塞业务。
"""
import json
import logging
import time

from shared.models.common_enums import RedisKeyPrefix
from shared.utils.service_registry import RedisServiceRegistry

logger = logging.getLogger(__name__)

# 绑定 TTL 缺省值（秒）：覆盖 Realtime 会话最长执行时长；
# 实例崩溃后绑定至多存活该时长，期间新请求重路由到存活实例
DEFAULT_BIND_TTL_SECONDS = 3600

SERVICE_NAME = 'api_test_service'


class RealtimeSessionRegistry:
    """Realtime 会话实例亲和注册表（Redis 实现，不可用降级本地）"""

    def __init__(self, service_name=SERVICE_NAME, bind_ttl_seconds=DEFAULT_BIND_TTL_SECONDS,
                 redis_client=None, instance_id_provider=None, healthy_provider=None):
        self._service_name = service_name
        self._bind_ttl = bind_ttl_seconds
        self._redis = redis_client
        self._instance_id_provider = instance_id_provider or self._default_instance_id
        self._healthy_provider = healthy_provider or self._default_healthy_instances

    def _client(self):
        if self._redis is not None:
            return self._redis
        try:
            from shared.utils.redis_pubsub import RedisPubSub
            return RedisPubSub().redis_client
        except Exception as e:
            logger.warning(f"Realtime 会话注册表：Redis 不可用，降级本地模式: {e}")
            return None

    @staticmethod
    def _bind_key(task_id):
        return f"{RedisKeyPrefix.SESSION_BIND.value}:{task_id}"

    def _default_instance_id(self):
        """当前实例标识：取服务注册表登记的实例 ID，未注册时返回 None（视为本实例）。"""
        try:
            registry = RedisServiceRegistry()
            return registry.get_instance_id()
        except Exception as e:
            logger.warning(f"获取本实例 ID 失败: {e}")
            return None

    def _default_healthy_instances(self):
        """服务注册表中本服务心跳新鲜的实例 ID 集合（实例重启后心跳停滞即出局）"""
        try:
            registry = RedisServiceRegistry()
            return registry.get_alive_ids(self._service_name)
        except Exception as e:
            logger.warning(f"查询服务存活实例失败: {e}")
            return None

    def bind(self, task_id):
        """会话建立：绑定 task → 当前实例（覆盖写，TTL 兜底）

        Returns:
            (instance_id, bound: bool)——bound=False 表示 Redis 不可用降级
        """
        client = self._client()
        instance_id = self._instance_id_provider()
        if client is None:
            return instance_id, False
        try:
            client.set(
                self._bind_key(task_id),
                json.dumps({'instance_id': instance_id, 'bound_at': time.time()}),
                ex=self._bind_ttl,
            )
            return instance_id, True
        except Exception as e:
            logger.warning(f"绑定 Realtime 会话 task={task_id} 失败: {e}")
            return instance_id, False

    def resolve(self, task_id, local_instance_id=None):
        """解析会话绑定：同会话粘同实例，绑定实例失联则重路由到当前实例

        Args:
            task_id: 任务（会话）ID
            local_instance_id: 当前实例 ID，缺省取服务注册表本实例

        Returns:
            dict: {
                'instance_id': 绑定/重绑定的实例 ID,
                'is_local': bool,   # 绑定是否落在当前实例
                'rerouted': bool,   # 是否发生重路由（原绑定实例失联/键过期）
                'degraded': bool,   # Redis 不可用降级（单实例语义）
            }
        """
        client = self._client()
        if local_instance_id is None:
            local_instance_id = self._instance_id_provider()
        if client is None:
            return {'instance_id': local_instance_id, 'is_local': True,
                    'rerouted': False, 'degraded': True}

        key = self._bind_key(task_id)
        try:
            raw = client.get(key)
            if raw:
                binding = json.loads(raw if isinstance(raw, str) else raw.decode('utf-8'))
                bound_id = binding.get('instance_id')
                healthy = self._healthy_provider()
                if bound_id == local_instance_id or (healthy is not None and bound_id in healthy):
                    return {'instance_id': bound_id, 'is_local': bound_id == local_instance_id,
                            'rerouted': False, 'degraded': False}

            # 无绑定（新会话 / TTL 过期）或绑定实例已失联（实例重启）→ 重绑定当前实例
            client.set(
                key,
                json.dumps({'instance_id': local_instance_id, 'bound_at': time.time()}),
                ex=self._bind_ttl,
            )
            return {'instance_id': local_instance_id, 'is_local': True,
                    'rerouted': True, 'degraded': False}
        except Exception as e:
            logger.warning(f"解析 Realtime 会话绑定 task={task_id} 失败，降级本地: {e}")
            return {'instance_id': local_instance_id, 'is_local': True,
                    'rerouted': False, 'degraded': True}

    def release(self, task_id):
        """会话结束清除绑定（幂等）"""
        client = self._client()
        if client is None:
            return
        try:
            client.delete(self._bind_key(task_id))
        except Exception as e:
            logger.warning(f"清除 Realtime 会话绑定 task={task_id} 失败: {e}")
