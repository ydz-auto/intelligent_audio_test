# -*- coding: utf-8 -*-
"""E2E 异步派发 Mixin（spec group-execution §9 阶段 B）。

不同实验室之间并行：主循环认领路由行后，把「按 SN 抢锁 → StartE2ETask →
逐行收敛」提交到任务级线程池，立即返回继续派发下一行。并发度由
`TASK_E2E_DISPATCH_WORKERS` 控制，串行语义仍由 SN 物理锁保证：

- 不同实验室（不同 SN）→ 各自拿到锁，真正并行；
- 同实验室同 SN → 同一把 SN 锁，后到者排队（线程内阻塞），仍串行；
- 串行目标（mode=serial）/ 未绑定实验室的行 → 不进入异步派发，保持就地
  同步执行（语义与阶段 A 完全一致）。

线程内使用独立 Session（不跨线程复用主循环会话），执行异常在内部收口为
行失败，绝不向派发线程外抛出（避免用例被认领后永挂）。
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.exc import InvalidRequestError

from task_service.infrastructure.persistence.models import Task, TaskCase

import logging

logger = logging.getLogger(__name__)


class E2EAsyncDispatchMixin:
    """E2E 异步派发：线程池、在途计数、执行阶段与逐行收敛"""

    # 在途容量轮询间隔（秒）：主循环等空位时的探测间隔（非执行路径，代价可忽略）
    E2E_DISPATCH_POLL_SECONDS = 0.2

    # ---- 开关与容量 ----

    @staticmethod
    def _e2e_async_enabled():
        """异步派发总开关（配置化，默认开启；关闭回退同步派发）"""
        from shared.infrastructure.config import BaseConfig
        return bool(getattr(BaseConfig, 'TASK_E2E_ASYNC_DISPATCH', True))

    @staticmethod
    def _e2e_dispatch_worker_count():
        """单任务并发派发上限（同时在途的 E2E 执行数）"""
        from shared.infrastructure.config import BaseConfig
        return max(1, int(getattr(BaseConfig, 'TASK_E2E_DISPATCH_WORKERS', 4)))

    def _is_async_dispatch_row(self, task_id, session, tc_rel):
        """该路由行是否允许异步派发（并发执行）。

        不允许的情况保持同步就地执行：
        - 非物理行（API 道有自己的异步链路）；
        - 未解析到设备 / 设备未绑定实验室（无法确认实验室物理隔离）；
        - 所属目标 mode=serial（串行语义 = 逐台依次执行、各播一遍）。
        """
        from shared.models.common_enums import DeviceType, ExecutionMode

        if (getattr(tc_rel, 'device_type', None)
                or DeviceType.PHYSICAL.value) != DeviceType.PHYSICAL.value:
            return False
        if not tc_rel.device_id:
            return False
        target_key = self._row_target_key(tc_rel)
        if (target_key is not None
                and self._target_mode(task_id, session, target_key) == ExecutionMode.SERIAL.value):
            return False
        lab_id = self._device_fingerprint(tc_rel.device_id).get('lab_id')
        return lab_id is not None and lab_id != ''

    # ---- 在途计数与线程池 ----

    def _e2e_dispatch_inflight_count(self, task_id):
        with self.e2e_dispatch_lock:
            return int(self.e2e_dispatch_inflight.get(task_id, 0))

    def _bump_e2e_dispatch_inflight(self, task_id, delta):
        with self.e2e_dispatch_lock:
            current = int(self.e2e_dispatch_inflight.get(task_id, 0))
            value = current + delta
            if value > 0:
                self.e2e_dispatch_inflight[task_id] = value
            else:
                self.e2e_dispatch_inflight.pop(task_id, None)

    def _get_e2e_dispatch_pool(self, task_id):
        """取（或按需创建）任务级派发线程池。"""
        with self.e2e_dispatch_lock:
            pool = self.e2e_dispatch_pools.get(task_id)
            if pool is None:
                pool = ThreadPoolExecutor(
                    max_workers=self._e2e_dispatch_worker_count(),
                    thread_name_prefix=f'e2e-dispatch-{task_id}',
                )
                self.e2e_dispatch_pools[task_id] = pool
            return pool

    def _await_e2e_dispatch_capacity(self, task_id, stop_event=None):
        """等待派发空位（在途 < 并发上限）；任务被停止返回 False。

        主循环在容量满时等待而非把行提前认领后堆在池队列里：排队中的行保持
        PENDING，不会被评估挂起仲裁误判（INT-120）。
        """
        limit = self._e2e_dispatch_worker_count()
        while self._e2e_dispatch_inflight_count(task_id) >= limit:
            if stop_event is not None and stop_event.is_set():
                return False
            time.sleep(self.E2E_DISPATCH_POLL_SECONDS)
        return True

    # ---- 提交与线程入口 ----

    def _submit_e2e_execution(self, task_id, row_ids, device_ids):
        """把执行阶段提交到任务级线程池（认领已在主线程完成）。

        提交失败（线程池不可用）回退就地同步执行：行已被认领，不能丢。
        """
        from shared.infrastructure.user_context import get_current_user_id

        row_ids = [int(row_id) for row_id in row_ids]
        device_ids = [int(device_id) for device_id in device_ids if device_id]
        with self.e2e_dispatch_lock:
            self.e2e_dispatch_user_ids[task_id] = get_current_user_id()
        try:
            pool = self._get_e2e_dispatch_pool(task_id)
        except Exception as e:
            self._log(level='ERROR',
                      content=f"E2E 派发线程池不可用，回退同步执行: {e}",
                      task_id=task_id)
            self._run_e2e_execution(task_id, row_ids, device_ids)
            return

        self._bump_e2e_dispatch_inflight(task_id, 1)
        try:
            pool.submit(self._e2e_execution_entry, task_id, row_ids, device_ids)
        except Exception as e:
            self._bump_e2e_dispatch_inflight(task_id, -1)
            self._log(level='ERROR',
                      content=f"E2E 异步派发提交失败，回退同步执行: {e}",
                      task_id=task_id)
            self._run_e2e_execution(task_id, row_ids, device_ids)

    def _e2e_execution_entry(self, task_id, row_ids, device_ids):
        """派发线程入口：绑定执行上下文后运行执行阶段，结束归还空位。"""
        from shared.infrastructure.worker_context import set_worker_instance_id
        from shared.infrastructure.user_context import set_current_user_id
        from shared.models.database import remove_db_session

        set_worker_instance_id(getattr(self, 'instance_id', None))
        with self.e2e_dispatch_lock:
            user_id = self.e2e_dispatch_user_ids.get(task_id)
        set_current_user_id(user_id)
        try:
            self._run_e2e_execution(task_id, row_ids, device_ids)
        except Exception as e:
            # _run_e2e_execution 内部已收口；此处兜底防线程静默死亡不留痕
            self._log(level='ERROR',
                      content=f"E2E 异步派发线程异常: {e}",
                      task_id=task_id)
        finally:
            self._bump_e2e_dispatch_inflight(task_id, -1)
            try:
                remove_db_session()
            except Exception:
                logger.debug("异步派发线程清理 DB session 失败 task_id=%s",
                             task_id, exc_info=True)

    # ---- 执行阶段（可在派发线程内运行） ----

    def _run_e2e_execution(self, task_id, row_ids, device_ids, session=None):
        """按 SN 抢锁 → 一次 StartE2ETask → 逐行收敛。

        锁按 SN 排序后逐把获取，全成或全退（一次播放缺一台设备无法补播）；
        任一锁被占用则组内/该行按「物理设备被占用」收敛失败。

        session 为 None 时使用独立 Session（异步派发线程不可复用主循环会话）；
        同步（就地）路径传入主循环会话，与阶段 A 行为一致。
        """
        from shared.models.database import create_db_session

        row_ids = [int(row_id) for row_id in row_ids]
        device_ids = [int(device_id) for device_id in device_ids if device_id]
        db_session = session if session is not None else create_db_session()
        lock_keys = sorted({
            lock_key
            for lock_key in (self._resolve_physical_lock_key(task_id, device_id)
                             for device_id in device_ids)
            if lock_key
        })

        locks = []
        try:
            for lock_key in lock_keys:
                lock = self._acquire_physical_lock_by_sn(lock_key)
                if lock is None:
                    self._release_e2e_locks(locks, task_id, device_ids)
                    locks = []
                    for row_id in row_ids:
                        row = db_session.get(TaskCase, row_id)
                        if row is not None:
                            self._handle_physical_lock_busy(task_id, row)
                    return False
                locks.append(lock)

            self._log(level='INFO',
                      content=self._e2e_dispatch_log_text(row_ids, device_ids),
                      task_id=task_id)
            error = None
            try:
                success = self._execute_e2e_rows(task_id, row_ids, device_ids)
            except Exception as e:
                # 执行异常不能留下未收敛的 running 行（否则主循环等到挂起仲裁）
                self._log(level='ERROR',
                          content=f"E2E 用例执行异常: {e}",
                          task_id=task_id)
                success, error = False, e
            self._converge_e2e_rows(task_id, row_ids, success, db_session, error=error)
            return success
        finally:
            self._release_e2e_locks(locks, task_id, device_ids)
            if session is None:
                db_session.close()

    @staticmethod
    def _e2e_dispatch_log_text(row_ids, device_ids):
        if len(device_ids) > 1:
            return (f"组执行派发: 路由行 {row_ids} 设备 {device_ids}"
                    f"（一次播放驱动组内全部设备）")
        return f"用例派发: 路由行 {row_ids} 设备 {device_ids}"

    def _execute_e2e_rows(self, task_id, row_ids, device_ids):
        """一次 StartE2ETask 驱动组内全部设备（单设备走 device_id 兼容路径）"""
        if len(device_ids) > 1:
            return self._execute_e2e_case(task_id, row_ids[0], device_ids=device_ids)
        return self._execute_e2e_case(
            task_id, row_ids[0],
            device_id=device_ids[0] if device_ids else None)

    def _converge_e2e_rows(self, task_id, row_ids, success, session, error=None):
        """逐行收敛执行状态（以落库值为准，执行器写入的终态不被覆盖）。"""
        try:
            for row_id in row_ids:
                row = session.get(TaskCase, row_id)
                if row is None:
                    continue
                try:
                    session.refresh(row)
                except InvalidRequestError:
                    if session.query(TaskCase.id).filter(
                            TaskCase.id == row_id).first() is None:
                        self._log(level='INFO',
                                  content=f"用例 {row_id} 执行期间已被删除，跳过终态收敛",
                                  task_id=task_id)
                        continue
                    raise
                if not success:
                    if error is not None and not (row.error_message or '').strip():
                        row.error_message = f'E2E执行异常: {error}'
                    self._handle_e2e_failure(task_id, row)
            session.commit()
        except Exception as converge_err:
            session.rollback()
            self._log(level='ERROR',
                      content=f"E2E 执行结果收敛失败: {converge_err}",
                      task_id=task_id)
            return

        try:
            self.refresh_task_counts_atomic(task_id)
            task = session.get(Task, task_id)
            if task is not None:
                session.expire(task)
                self._emit_progress(task)
        except Exception as progress_err:
            logger.warning("异步派发后刷新任务统计/进度失败 task_id=%s: %s",
                           task_id, progress_err, exc_info=True)

    def _release_e2e_locks(self, locks, task_id, device_ids):
        for lock in locks:
            try:
                lock.release()
            except Exception as e:
                self._log(level='WARNING',
                          content=f"释放物理设备互斥锁失败 (devices={device_ids}): {e}",
                          task_id=task_id)

    # ---- 任务收尾 ----

    def _drain_e2e_dispatch(self, task_id):
        """等待在途派发结束（有界）并回收线程池。

        必须在释放任务单飞槽位之前调用：否则仍在执行的设备/音频会与下一个
        任务并发占用同一物理资源。
        """
        from shared.infrastructure.config import BaseConfig

        deadline = time.time() + int(
            getattr(BaseConfig, 'GRPC_E2E_SYNC_TIMEOUT_SECONDS', 600)) + 60
        while self._e2e_dispatch_inflight_count(task_id) > 0 and time.time() < deadline:
            time.sleep(self.E2E_DISPATCH_POLL_SECONDS)

        with self.e2e_dispatch_lock:
            pool = self.e2e_dispatch_pools.pop(task_id, None)
            remaining = self.e2e_dispatch_inflight.pop(task_id, 0)
            self.e2e_dispatch_user_ids.pop(task_id, None)
        if remaining:
            self._log(level='ERROR',
                      content=f"任务结束时仍有 {remaining} 个异步派发在执行，已强制回收线程池",
                      task_id=task_id)
        if pool is not None:
            pool.shutdown(wait=False)
