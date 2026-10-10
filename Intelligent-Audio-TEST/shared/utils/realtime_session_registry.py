# -*- coding: utf-8 -*-
"""Realtime 会话实例亲和注册表（INT-61）

api_test_service 双副本部署下，Realtime WS 长连接封闭在接单实例内存中，
同会话（task 粒度）的后续请求必须粘住同一实例。本注册表基于 Redis
session:bind:{task_id} 记录 task → 实例 绑定：

- bind：会话建立时写入绑定（带 TTL，实例崩溃后由 TTL 自然过期）
- resolve：查询绑定。绑定健康实例时原样返回（亲和）；绑定实例已失联
  （不在服务注册存活集合，实例重启场景）或 TTL 已过期时，重绑定到
  当前实例（新会话重路由）
- route_or_bind：派发侧亲和路由（task_service 认领即绑定，§5.2）——
  有健康绑定返回绑定实例；无绑定/绑定失联时选最闲在册实例写入绑定并返回
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
                 redis_client=None, instance_id_provider=None, healthy_provider=None,
                 instances_provider=None):
        self._service_name = service_name
        self._bind_ttl = bind_ttl_seconds
        self._redis = redis_client
        self._instance_id_provider = instance_id_provider or self._default_instance_id
        self._healthy_provider = healthy_provider or self._default_healthy_instances
        self._instances_provider = instances_provider or self._default_instances

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

    def _default_instances(self):
        """注册表中本服务心跳新鲜实例的路由信息表

        Returns:
            dict: {instance_id: {host, grpc_port, running_tasks, ...}}；
            注册表/Redis 不可用时返回 None（与「无在册实例」的空 dict 区分）
        """
        try:
            registry = RedisServiceRegistry()
            alive = registry.get_alive_ids(self._service_name)
            instances = {}
            for info in registry.discover(self._service_name):
                iid = info.get('instance_id')
                if iid in alive:
                    instances[iid] = info
            return instances
        except Exception as e:
            logger.warning(f"查询服务实例路由信息失败: {e}")
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

    def route_or_bind(self, task_id):
        """派发侧亲和路由（task_service 认领即绑定，架构设计 §5.2）

        与 resolve 的「重路由到当前实例」语义不同：派发方自身不是 api_test
        实例，重绑定时须从注册表在册实例中选最闲者写入绑定，并返回其
        host:grpc_port 供调用方直连（绕过服务名负载均衡）。

        Returns:
            dict: {'instance_id', 'host', 'grpc_port', 'bound'}
            bound=True 表示复用既有健康绑定；False 表示新建/重路由绑定
            None  表示 Redis/注册表不可用或无在册实例——调用方回退默认
            负载均衡通道（单实例 / 降级语义）
        """
        client = self._client()
        if client is None:
            return None
        key = self._bind_key(task_id)
        try:
            instances = self._instances_provider()
            if not instances:
                return None
            raw = client.get(key)
            if raw:
                binding = json.loads(raw if isinstance(raw, str) else raw.decode('utf-8'))
                info = instances.get(binding.get('instance_id'))
                if info is not None and info.get('grpc_port'):
                    return {'instance_id': binding['instance_id'], 'host': info['host'],
                            'grpc_port': info.get('grpc_port'), 'bound': True}

            # 无绑定（新任务 / TTL 过期）或绑定实例已失联 → 选最闲在册实例重绑定
            chosen = min(instances.values(), key=lambda i: i.get('running_tasks', 0))
            if not chosen.get('grpc_port'):
                return None
            client.set(
                key,
                json.dumps({'instance_id': chosen['instance_id'], 'bound_at': time.time()}),
                ex=self._bind_ttl,
            )
            return {'instance_id': chosen['instance_id'], 'host': chosen['host'],
                    'grpc_port': chosen.get('grpc_port'), 'bound': False}
        except Exception as e:
            logger.warning(f"派发侧亲和路由 task={task_id} 失败，回退默认通道: {e}")
            return None

    def release(self, task_id):
        """会话结束清除绑定（幂等）"""
        client = self._client()
        if client is None:
            return
        try:
            client.delete(self._bind_key(task_id))
        except Exception as e:
            logger.warning(f"清除 Realtime 会话绑定 task={task_id} 失败: {e}")


def get_instance_target(service_name=SERVICE_NAME, instance_id=None):
    """查询在册实例的直连路由目标（亲和转发/派发路由共用）

    Returns:
        dict: {'instance_id', 'host', 'grpc_port'}；实例不在册、心跳失联
        或未登记 grpc_port 时返回 None（调用方按「不可达」处理）
    """
    if not instance_id:
        return None
    try:
        registry = RedisServiceRegistry()
        if instance_id not in registry.get_alive_ids(service_name):
            return None
        for info in registry.discover(service_name):
            if info.get('instance_id') == instance_id and info.get('grpc_port'):
                return {'instance_id': instance_id, 'host': info['host'],
                        'grpc_port': info.get('grpc_port')}
        return None
    except Exception as e:
        logger.warning(f"查询实例 {instance_id} 路由目标失败: {e}")
        return None
