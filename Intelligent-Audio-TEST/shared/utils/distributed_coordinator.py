"""
分布式协调器 - 共享层

基于 Redis 的分布式锁 / 信号量 / 控制标志位，用于多实例部署场景。
单实例部署时可通过环境变量 DISTRIBUTED_COORDINATOR_ENABLED=false 关闭，退化为纯内存模式。

设计原则：
- 所有方法在 Redis 不可用时返回安全默认值（不阻塞业务），并打印降级日志
- 锁带 TTL 防止持有者崩溃后死锁
- 信号量用 INCR/DECR 原子实现，带 TTL 兜底
- 控制标志位用 SET/GET，多实例可读
"""
import logging
import time
import uuid
import threading

from shared.infrastructure.config import BaseConfig

logger = logging.getLogger(__name__)


def _get_redis_client():
    """获取 Redis 客户端单例（复用 RedisPubSub 的连接）"""
    try:
        from shared.utils.redis_pubsub import RedisPubSub
        return RedisPubSub().redis_client
    except Exception:
        try:
            import redis
            return redis.from_url(BaseConfig.REDIS_URL)
        except Exception as e:
            logger.warning(f"分布式协调器：Redis 不可用，降级为本地模式: {e}")
            return None


_REDIS_CLIENT = None
_REDIS_LOCK = threading.Lock()


def _client():
    global _REDIS_CLIENT
    if _REDIS_CLIENT is None:
        with _REDIS_LOCK:
            if _REDIS_CLIENT is None:
                _REDIS_CLIENT = _get_redis_client()
    return _REDIS_CLIENT


def _enabled():
    """是否启用分布式协调（默认关闭，单实例无需开启）"""
    import os
    return os.environ.get('DISTRIBUTED_COORDINATOR_ENABLED', 'true').lower() in ('true', '1', 'yes')


# Lua 脚本：CAS 式释放锁（只有持有者才能删）
_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


class DistributedLock:
    """分布式可重入锁（基于 SET NX EX + token）"""

    def __init__(self, key, ttl=30, retry_interval=0.1, retry_timeout=30):
        self.key = key
        self.ttl = ttl
        self.retry_interval = retry_interval
        self.retry_timeout = retry_timeout
        self._token = None

    def acquire(self, blocking=True):
        """获取锁，成功返回 True；非阻塞模式下获取不到立即返回 False

        Redis 不可达时降级放行（返回 True），不阻塞业务，与文件头承诺一致。
        """
        if not _enabled():
            return True  # 单实例模式：直接放行
        client = _client()
        if client is None:
            return True  # Redis 不可用：降级放行，不阻塞业务

        self._token = uuid.uuid4().hex
        try:
            if not blocking:
                return bool(client.set(self.key, self._token, nx=True, ex=self.ttl))
            start = time.time()
            while time.time() - start < self.retry_timeout:
                if client.set(self.key, self._token, nx=True, ex=self.ttl):
                    return True
                time.sleep(self.retry_interval)
            return False
        except Exception as e:
            logger.warning(f"获取分布式锁 {self.key} 时 Redis 不可达，降级放行: {e}")
            return True

    def release(self):
        """释放锁"""
        if not _enabled() or self._token is None:
            return
        client = _client()
        if client is None:
            return
        try:
            client.eval(_RELEASE_LOCK_SCRIPT, 1, self.key, self._token)
        except Exception as e:
            logger.warning(f"释放分布式锁 {self.key} 失败: {e}")
        finally:
            self._token = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


# Lua 脚本：原子信号量获取（INCR + 判超限回退 + EXPIRE 一次完成）
_ACQUIRE_SEM_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current <= tonumber(ARGV[1]) then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
    return current
else
    redis.call('DECR', KEYS[1])
    return -1
end
"""


class DistributedSemaphore:
    """分布式信号量（基于 Lua 原子 INCR/DECR + 兜底 TTL key）

    用于限制同一资源的全局并发数（如同一 API 的并发请求数）。
    用 Lua 脚本保证 INCR+判超限+回退+EXPIRE 是原子的，多进程并发安全。
    """

    def __init__(self, key, max_count, ttl=30):
        self.key = key
        self.max_count = max_count
        self.ttl = ttl

    def acquire(self, timeout=300):
        """获取一个名额，成功返回 True，超时返回 False"""
        if not _enabled():
            return True
        client = _client()
        if client is None:
            return True
        if self.max_count <= 0:
            return True  # 无限制，直接放行（用于 release 的占位实例）

        start = time.time()
        while time.time() - start < timeout:
            try:
                result = client.eval(
                    _ACQUIRE_SEM_SCRIPT, 1, self.key, self.max_count, self.ttl
                )
                # 兼容 redis-py 不同版本返回 int 或 bytes
                if isinstance(result, bytes):
                    result = int(result)
                if result != -1:
                    return True
            except Exception as e:
                logger.warning(f"获取分布式信号量 {self.key} 失败: {e}")
                return True  # Redis 异常降级放行
            time.sleep(0.1)
        return False

    def release(self):
        """释放一个名额"""
        if not _enabled():
            return
        client = _client()
        if client is None:
            return
        try:
            current = client.decr(self.key)
            if current < 0:
                # 防御性：计数不能为负
                client.set(self.key, 0, ex=self.ttl)
        except Exception as e:
            logger.warning(f"释放分布式信号量 {self.key} 失败: {e}")


def set_flag(key, value=1, ttl=86400):
    """设置控制标志位（如 stop/pause）"""
    if not _enabled():
        return
    client = _client()
    if client is None:
        return
    try:
        client.set(key, str(value), ex=ttl)
    except Exception as e:
        logger.warning(f"设置标志位 {key} 失败: {e}")


def clear_flag(key):
    """清除控制标志位"""
    if not _enabled():
        return
    client = _client()
    if client is None:
        return
    try:
        client.delete(key)
    except Exception as e:
        logger.warning(f"清除标志位 {key} 失败: {e}")


def get_flag(key):
    """读取控制标志位"""
    if not _enabled():
        return None
    client = _client()
    if client is None:
        return None
    try:
        return client.get(key)
    except Exception as e:
        logger.warning(f"读取标志位 {key} 失败: {e}")
        return None


def is_flag_set(key):
    """判断控制标志位是否被设置"""
    if not _enabled():
        return False
    client = _client()
    if client is None:
        return False
    try:
        return client.exists(key) > 0
    except Exception as e:
        logger.warning(f"检查标志位 {key} 失败: {e}")
        return False


# === 任务抢占 CAS（推荐用法）===
# 不用 Redis 锁，直接用 DB 条件 UPDATE 更可靠，这里提供 Redis 层的辅助函数供特殊场景使用
def try_claim_task(task_id, holder_id=None, ttl=600):
    """尝试抢占任务（用于多实例调度器同时拉到同一 pending 任务时去重）

    Returns:
        True 抢占成功，False 已被其它实例抢占
    """
    if not _enabled():
        return True
    client = _client()
    if client is None:
        return True
    token = holder_id or uuid.uuid4().hex
    try:
        return bool(client.set(f'task:claim:{task_id}', token, nx=True, ex=ttl))
    except Exception as e:
        logger.warning(f"抢占任务 {task_id} 失败: {e}")
        return True  # Redis 异常时降级放行，由 DB CAS 兜底


def release_task_claim(task_id):
    """释放任务抢占"""
    if not _enabled():
        return
    client = _client()
    if client is None:
        return
    try:
        client.delete(f'task:claim:{task_id}')
    except Exception as e:
        logger.warning(f"释放任务抢占 {task_id} 失败: {e}")
