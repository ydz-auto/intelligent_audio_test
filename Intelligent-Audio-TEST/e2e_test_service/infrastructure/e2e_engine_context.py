# -*- coding: utf-8 -*-
"""E2E 执行引擎上下文 — 基础设施层。

提供 E2EExecutor 所需的运行时基础设施能力：
- device_control_pool: 设备控制线程池
- stop_flags / pause_flags: 任务控制标志位（基于 Redis 分布式标志位）
- update_case_round_progress: 更新轮次进度
- _emit_progress: 推送进度（e2e_test_service 进程内为空实现）

在 e2e_test_service 进程内，控制事件通过 gRPC DeviceService
的 RegisterTaskEvents 与 task_service 同步状态。
"""
import time
import logging
import threading
import concurrent.futures

from shared.utils.config_manager import config_manager
from shared.utils import distributed_coordinator as dc

logger = logging.getLogger(__name__)

# Redis 控制 key 前缀与 TTL
_E2E_STOP_KEY_PREFIX = 'e2e:stop:'
_E2E_PAUSE_KEY_PREFIX = 'e2e:pause:'
# 默认 24 小时兜底 TTL，避免进程崩溃后标志位长期残留
_CONTROL_FLAG_TTL = 86400


class _RedisEvent:
    """threading.Event 语义的 Redis 标志位适配器。

    兼容现有调用点（.is_set() / .set() / .clear() / .wait()），
    将进程内 threading.Event 替换为 Redis 分布式标志位，支持多实例部署。
    Redis 不可用时降级：is_set 返回 False（不阻塞），set/clear 静默忽略（不抛异常）。
    """

    def __init__(self, key, initial_set=False):
        self._key = key
        if initial_set:
            self.set()

    def set(self):
        """置位（标志位存在 = 已设置）"""
        dc.set_flag(self._key, value=1, ttl=_CONTROL_FLAG_TTL)

    def clear(self):
        """复位（标志位不存在 = 未设置）"""
        dc.clear_flag(self._key)

    def is_set(self):
        """判断是否已置位"""
        return dc.is_flag_set(self._key)

    def wait(self, timeout=None):
        """阻塞等待标志位被置位，超时返回 False。

        模拟 threading.Event.wait：轮询 Redis，每 0.5 秒检查一次。
        """
        deadline = None if timeout is None else time.time() + timeout
        while True:
            if self.is_set():
                return True
            if deadline is not None and time.time() >= deadline:
                return False
            time.sleep(0.5)


class E2EEngineContext:
    """E2E 执行上下文：在 e2e_test_service 进程内提供 E2EExecutor 所需的 execution_engine 能力"""

    def __init__(self):
        # 扩容至 12 个线程：全局背景噪声（最多4设备）+ 轮次内 play_round
        # （主讲人/干扰人/噪声，最多4-6设备）需要足够容量避免背景噪声占满线程池导致 play_round 任务排队死锁
        # 并发参数配置化：线程池大小从 config_manager 读取
        self.device_control_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=config_manager.get_value('execution_engine', 'audio_playback_max_workers', 12)
        )
        self.stop_flags = {}
        self.pause_flags = {}
        self._round_progress = {}
        self._lock = threading.Lock()

    def _get_or_create_flags(self, task_id):
        """获取或创建任务的控制标志位（Redis 适配的 _RedisEvent）

        stop 默认未置位，pause 默认置位（即默认不暂停，可执行）。
        """
        with self._lock:
            if task_id not in self.stop_flags:
                self.stop_flags[task_id] = _RedisEvent(
                    f'{_E2E_STOP_KEY_PREFIX}{task_id}', initial_set=False
                )
            if task_id not in self.pause_flags:
                # pause 初始置位 = 未暂停（is_set 为 True 表示可执行）
                self.pause_flags[task_id] = _RedisEvent(
                    f'{_E2E_PAUSE_KEY_PREFIX}{task_id}', initial_set=True
                )
            return self.stop_flags[task_id], self.pause_flags[task_id]

    def update_case_round_progress(self, task_id, tc_rel_id, round_idx, total_rounds):
        with self._lock:
            self._round_progress.setdefault(task_id, {})[tc_rel_id] = {
                'round_idx': round_idx,
                'total_rounds': total_rounds,
            }

    def _emit_progress(self, task_id, force=False):
        # e2e_test_service 进程内不直接推送进度，由 task_service 端通过 gRPC 拉取状态
        pass

    def set_stop(self, task_id):
        stop, pause = self._get_or_create_flags(task_id)
        stop.set()

    def set_pause(self, task_id, paused):
        stop, pause = self._get_or_create_flags(task_id)
        if paused:
            pause.clear()
        else:
            pause.set()

    def get_round_progress(self, task_id):
        with self._lock:
            return dict(self._round_progress.get(task_id, {}))

    def cleanup(self, task_id):
        with self._lock:
            # 清理 Redis 标志位（释放资源）
            stop = self.stop_flags.pop(task_id, None)
            pause = self.pause_flags.pop(task_id, None)
            self._round_progress.pop(task_id, None)
        if stop is not None:
            stop.clear()
        if pause is not None:
            pause.clear()
