"""
分布式协调器 - 共享层

基于 Redis 的分布式锁 / 信号量 / 控制标志位，用于多实例部署场景。
单实例部署时可通过环境变量 DISTRIBUTED_COORDINATOR_ENABLED=false 关闭，退化为纯内存模式。

设计原则：
- 所有方法在 Redis 不可用时返回安全默认值（不阻塞业务），并打印降级日志
- 锁带 TTL 防止持有者崩溃后死锁
- 信号量用 INCR/DECR 原子实现，带 TTL 兜底；Redis 不可用/异常时降级为进程内
  BoundedSemaphore 兜底，保证独占实例场景下并发限制不失效
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


# 进程内信号量兜底注册表：Redis 不可用/异常时保持并发限制不失效（对齐 V9.7.10）
# key -> threading.BoundedSemaphore；按 key 复用，跨实例共享，数量有限无需清理
_LOCAL_SEMAPHORES = {}
_LOCAL_SEM_LOCK = threading.Lock()


def _get_local_semaphore(key, max_count):
    """获取（或创建）key 对应的进程内兜底信号量"""
    with _LOCAL_SEM_LOCK:
        sem = _LOCAL_SEMAPHORES.get(key)
        if sem is None:
            sem = threading.BoundedSemaphore(max_count)
            _LOCAL_SEMAPHORES[key] = sem
        return sem


class DistributedSemaphore:
    """分布式信号量（基于 Lua 原子 INCR/DECR + 兜底 TTL key）

    用于限制同一资源的全局并发数（如同一 API 的并发请求数）。
    用 Lua 脚本保证 INCR+判超限+回退+EXPIRE 是原子的，多进程并发安全。

    降级策略（对齐 V9.7.10 的进程内 threading.Semaphore 行为）：
    - Redis 不可用/异常时，acquire 降级为进程内 BoundedSemaphore 兜底，
      并发限制不失效；release 与 acquire 路径对称降级，保证配对释放。
    - ttl 为持有者崩溃后的名额泄漏兜底，必须大于最长持有时长
      （如单条 API 用例的最长执行时间），否则计数 key 提前过期会导致并发控制失效。
    """

    def __init__(self, key, max_count, ttl=3600):
        self.key = key
        self.max_count = max_count
        self.ttl = ttl

    def acquire(self, timeout=300):
        """获取一个名额，成功返回 True，超时返回 False

        Redis 可用：Lua 原子 INCR 抢名额，抢不到则轮询直至成功或超时；
        无论 timeout 多小都至少尝试一次（timeout=0 即非阻塞尝试）。
        Redis 不可用/异常：降级为进程内 BoundedSemaphore 兜底。
        """
        if self.max_count <= 0:
            return True  # 配置 0 表示不限制，直接放行

        client = _client() if _enabled() else None
        if client is not None:
            start = time.time()
            while True:
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
                    logger.warning(
                        f"获取分布式信号量 {self.key} 失败，降级为进程内信号量: {e}"
                    )
                    break
                if time.time() - start >= timeout:
                    return False
                time.sleep(0.1)

        # 进程内兜底（分布式关闭 / Redis 不可用 / Redis 异常）
        local_sem = _get_local_semaphore(self.key, self.max_count)
        return local_sem.acquire(timeout=timeout)

    def release(self):
        """释放一个名额

        与 acquire 路径对称：Redis 可用则 DECR；
        Redis 不可用/异常则释放进程内兜底信号量（与降级获取配对）。
        """
        client = _client() if _enabled() else None
        if client is not None:
            try:
                current = client.decr(self.key)
                if current < 0:
                    # 防御性：计数不能为负
                    client.set(self.key, 0, ex=self.ttl)
                return
            except Exception as e:
                logger.warning(
                    f"释放分布式信号量 {self.key} 失败，回退进程内信号量: {e}"
                )
        local_sem = _get_local_semaphore(self.key, self.max_count)
        try:
            local_sem.release()
        except ValueError:
            # 防过度释放（对齐 V9.7.10 release 捕获 ValueError 的处理）
            pass


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


# === 任务控制信号（stop / pause）统一 Redis Key ===
# 多实例下，task_service / e2e_test_service / device_service 三方统一读写同一组 key：
#   task:stop:{task_id}   存在 = 已停止
#   task:pause:{task_id}  存在 = 已暂停
# 冷启动后由各服务启动时调用 cleanup_orphan_task_control_flags 清理孤儿标志。

TASK_STOP_KEY_PREFIX = 'task:stop:'
TASK_PAUSE_KEY_PREFIX = 'task:pause:'


def task_stop_key(task_id):
    """构造任务停止信号 key"""
    return f'{TASK_STOP_KEY_PREFIX}{task_id}'


def task_pause_key(task_id):
    """构造任务暂停信号 key"""
    return f'{TASK_PAUSE_KEY_PREFIX}{task_id}'


def set_task_stop(task_id, ttl=86400):
    """置位任务停止信号（多实例可见）"""
    set_flag(task_stop_key(task_id), value=1, ttl=ttl)


def clear_task_stop(task_id):
    """清除任务停止信号"""
    clear_flag(task_stop_key(task_id))


def is_task_stopped(task_id):
    """判断任务停止信号是否已置位（Redis 不可用时返回 False，不阻塞）"""
    return is_flag_set(task_stop_key(task_id))


def set_task_pause(task_id, ttl=86400):
    """置位任务暂停信号（多实例可见）"""
    set_flag(task_pause_key(task_id), value=1, ttl=ttl)


def clear_task_pause(task_id):
    """清除任务暂停信号"""
    clear_flag(task_pause_key(task_id))


def is_task_paused(task_id):
    """判断任务暂停信号是否已置位（Redis 不可用时返回 False，不阻塞）"""
    return is_flag_set(task_pause_key(task_id))


def _scan_keys(pattern):
    """使用 SCAN 迭代匹配 key，避免 KEYS 阻塞 Redis；Redis 不可用返回空列表"""
    if not _enabled():
        return []
    client = _client()
    if client is None:
        return []
    keys = []
    try:
        for k in client.scan_iter(match=pattern, count=500):
            if isinstance(k, bytes):
                k = k.decode('utf-8', errors='ignore')
            keys.append(k)
    except Exception as e:
        logger.warning(f"SCAN {pattern} 失败: {e}")
    return keys


def cleanup_orphan_task_control_flags(active_task_ids):
    """清理孤儿任务控制标志（冷启动恢复用）。

    多实例场景下，若 task_id 仍处于 active_task_ids（本实例或其它实例正在运行/暂停），
    则保留其 stop/pause 标志；否则删除，防止残留信号影响后续同名任务。

    Args:
        active_task_ids: 集合/可迭代，当前仍处于运行态（running/paused）的任务 ID 集合。
    """
    if not _enabled():
        return 0
    active = {str(t) for t in (active_task_ids or [])}
    cleaned = 0
    for prefix in (TASK_STOP_KEY_PREFIX, TASK_PAUSE_KEY_PREFIX):
        for key in _scan_keys(f'{prefix}*'):
            task_id = key[len(prefix):]
            if task_id in active:
                continue
            try:
                _client().delete(key)
                cleaned += 1
                logger.info("清理孤儿任务控制标志: %s", key)
            except Exception as e:
                logger.warning(f"清理孤儿任务控制标志 {key} 失败: {e}")
    return cleaned
