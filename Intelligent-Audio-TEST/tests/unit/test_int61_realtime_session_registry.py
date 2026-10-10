# -*- coding: utf-8 -*-
"""INT-61 Realtime 会话亲和注册表单测 — 内存 Redis 桩模拟双副本

覆盖：
- bind：会话建立写绑定（task → 实例），带 TTL
- resolve：同会话重复解析粘同实例（亲和）
- resolve：绑定实例失联（实例重启，心跳集合不再包含）→ 重路由到当前实例
- resolve：无绑定（新会话 / TTL 过期）→ 绑定当前实例
- resolve：绑定健康远端实例 → is_local=False 且不重绑定
- release：清除绑定（幂等）
- Redis 不可用：降级单实例语义（degraded=True，不阻塞）
"""
import json
import os

# BaseConfig 在 import 时校验环境变量（测试环境无 .env），先补齐必需项
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.utils.realtime_session_registry import (
    DEFAULT_BIND_TTL_SECONDS,
    RealtimeSessionRegistry,
)

SERVICE = 'api_test_service'
TASK = 1001


class _MemRedis:
    """最小 Redis 语义桩：get / set(key, value, ex=) / delete，记录 TTL"""

    def __init__(self):
        self._data = {}
        self.ttls = {}

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value, ex=None):
        self._data[key] = value
        self.ttls[key] = ex
        return True

    def delete(self, key):
        return 1 if self._data.pop(key, None) is not None else 0


class _BrokenRedis:
    """不可用 Redis：所有命令抛 ConnectionError"""

    def get(self, *_a, **_k):
        raise ConnectionError('redis down')

    def set(self, *_a, **_k):
        raise ConnectionError('redis down')

    def delete(self, *_a, **_k):
        raise ConnectionError('redis down')


def _make_registry(store, healthy=None, local_instance='inst-A'):
    """构造注入依赖的注册表：内存桩存储 + 可控存活集合"""
    healthy = healthy if healthy is not None else {'inst-A'}
    return RealtimeSessionRegistry(
        service_name=SERVICE,
        redis_client=store,
        instance_id_provider=lambda: local_instance,
        healthy_provider=lambda: healthy,
    )


class TestBind:
    def test_bind_writes_binding(self):
        store = _MemRedis()
        reg = _make_registry(store)
        instance_id, bound = reg.bind(TASK)
        assert bound is True
        assert instance_id == 'inst-A'
        binding = json.loads(store.get(f'session:bind:{TASK}'))
        assert binding['instance_id'] == 'inst-A'

    def test_bind_has_ttl(self):
        store = _MemRedis()
        reg = _make_registry(store)
        reg.bind(TASK)
        ttl = store.ttls[f'session:bind:{TASK}']
        assert 0 < ttl <= DEFAULT_BIND_TTL_SECONDS


class TestResolve:
    def test_same_session_sticks_to_same_instance(self):
        """双副本亲和：同会话重复解析粘同实例"""
        store = _MemRedis()
        reg = _make_registry(store, healthy={'inst-A', 'inst-B'})
        reg.bind(TASK)
        for _ in range(3):
            result = reg.resolve(TASK, local_instance_id='inst-B')
            assert result['instance_id'] == 'inst-A'
            assert result['is_local'] is False
            assert result['rerouted'] is False

    def test_resolve_local_binding(self):
        store = _MemRedis()
        reg = _make_registry(store, healthy={'inst-A', 'inst-B'})
        reg.bind(TASK)
        result = reg.resolve(TASK, local_instance_id='inst-A')
        assert result['is_local'] is True
        assert result['rerouted'] is False

    def test_reroute_when_bound_instance_restarted(self):
        """实例重启后新会话重路由：绑定实例失联 → 重绑定当前实例"""
        store = _MemRedis()
        reg = _make_registry(store, healthy={'inst-A'})
        reg.bind(TASK)
        # inst-A 重启：心跳集合中 inst-A 消失（模拟），当前请求来自 inst-B
        reg._healthy_provider = lambda: {'inst-B'}
        result = reg.resolve(TASK, local_instance_id='inst-B')
        assert result['rerouted'] is True
        assert result['is_local'] is True
        assert result['instance_id'] == 'inst-B'
        binding = json.loads(store.get(f'session:bind:{TASK}'))
        assert binding['instance_id'] == 'inst-B'

    def test_new_session_binds_local(self):
        """无绑定（新会话 / TTL 过期）→ 绑定当前实例"""
        store = _MemRedis()
        reg = _make_registry(store, healthy={'inst-A', 'inst-B'})
        result = reg.resolve(TASK, local_instance_id='inst-A')
        assert result['rerouted'] is True
        assert result['is_local'] is True

    def test_expired_ttl_reroutes(self):
        store = _MemRedis()
        reg = _make_registry(store, healthy={'inst-A', 'inst-B'})
        reg.bind(TASK)
        store.delete(f'session:bind:{TASK}')  # 模拟 TTL 过期
        result = reg.resolve(TASK, local_instance_id='inst-A')
        assert result['rerouted'] is True


class TestRelease:
    def test_release_clears_binding(self):
        store = _MemRedis()
        reg = _make_registry(store)
        reg.bind(TASK)
        reg.release(TASK)
        assert store.get(f'session:bind:{TASK}') is None

    def test_release_idempotent(self):
        store = _MemRedis()
        reg = _make_registry(store)
        reg.release(TASK)
        reg.release(TASK)


class TestDegraded:
    def test_redis_unavailable_degrades_to_local(self):
        """Redis 不可用：降级单实例语义，不阻塞业务"""
        reg = _make_registry(_BrokenRedis())
        instance_id, bound = reg.bind(TASK)
        assert bound is False
        result = reg.resolve(TASK, local_instance_id='inst-A')
        assert result['degraded'] is True
        assert result['is_local'] is True
