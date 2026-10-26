# -*- coding: utf-8 -*-
"""关联用例参考参数刷新的后台调度（INT-2042）。

背景：批量更新标注（POST /audios/batch/annotations）与「同步刷新关联测试用例
的参考参数」原本在同一次 gRPC 调用里串行完成。刷新路径要分页扫描全部用例
（573 条实测 3.5~4.2s/100 条）再逐个用例重算，实测总耗时 >60s，必然先撞上
网关 gRPC 客户端的默认 deadline（GRPC_CLIENT_DEADLINE_SECONDS=60s）：标注
其实已写库，客户端却收到 400 DEADLINE_EXCEEDED，用户只看到失败、数据落库
状态不可知，重试还可能重复提交。

因此把刷新从批量标注命令里解耦：命令只负责标注落库并提交，刷新入队后由本
调度器在后台线程串行执行，接口随标注提交立即返回。

- 单飞：同一时刻只有一个刷新任务在跑，避免并发提交反复全表扫描；
- 合并：运行期间新入队的 audio_id 合并进同一队列项（按 算法类型 + 操作人
  身份 归并），既不丢刷新，也不重复扫描；
- 身份：contextvars 不跨线程传播，入队时 capture_identity() 捕获操作人，
  工作线程用 run_with_identity() 恢复——出站 gRPC 才带 x-user-id，
  task_service 侧私有用例的可见性判定才不会按未认证降级（同 INT-1572）。
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, List, Optional, Set, Tuple

from shared.infrastructure.user_context import capture_identity, run_with_identity

logger = logging.getLogger(__name__)


class TestCaseRefreshScheduler:
    """关联用例参考参数刷新的单飞 + 合并队列（每个进程一个实例）。"""

    # 名字以 Test 开头，避免被 pytest 当成测试类收集
    __test__ = False

    def __init__(self, refresh_fn: Callable[[List[int], Optional[str]], List[str]]):
        # refresh_fn(audio_ids, algorithm_type) -> 被刷新的用例 ID 列表
        self._refresh_fn = refresh_fn
        self._lock = threading.Lock()
        # 队列项：{'key': (algorithm_type, identity), 'audio_ids': set[int]}
        self._queue: List[dict] = []
        self._worker: Optional[threading.Thread] = None

    def enqueue(self, audio_ids, algorithm_type=None, identity=None) -> bool:
        """把一批 audio_id 的刷新请求入队，立即返回是否已入队（不阻塞调用方）。"""
        ids: Set[int] = set()
        for audio_id in audio_ids or []:
            try:
                ids.add(int(audio_id))
            except (TypeError, ValueError):
                continue
        if not ids:
            return False

        key = (algorithm_type or None, identity)
        with self._lock:
            for job in self._queue:
                if job['key'] == key:
                    job['audio_ids'].update(ids)
                    break
            else:
                self._queue.append({'key': key, 'audio_ids': set(ids)})

            if self._worker is not None and self._worker.is_alive():
                return True
            self._worker = threading.Thread(
                target=self._drain, daemon=True, name='audio-testcase-refresh')
            self._worker.start()
        return True

    def pending_batches(self) -> int:
        """待执行的刷新批次数（观测/测试用）。"""
        with self._lock:
            return len(self._queue)

    def wait_idle(self, timeout: Optional[float] = None) -> bool:
        """阻塞到队列清空且工作线程退出，返回是否在超时前空闲（测试/收尾用）。"""
        with self._lock:
            worker = self._worker
        if worker is not None:
            worker.join(timeout)
        return worker is None or not worker.is_alive()

    # ---------- 内部 ----------

    def _drain(self):
        """串行消费队列，直到没有待执行批次才退出线程。"""
        while True:
            with self._lock:
                if not self._queue:
                    self._worker = None
                    return
                job = self._queue.pop(0)
            try:
                self._run_batch(job)
            except Exception:
                logger.exception("关联用例参考参数刷新批次异常退出")
            finally:
                self._reset_session()

    def _run_batch(self, job: dict):
        algorithm_type, identity = job['key']
        audio_ids = sorted(job['audio_ids'])
        try:
            refreshed = run_with_identity(
                identity, self._refresh_fn, audio_ids, algorithm_type)
            logger.info(
                "关联用例参考参数刷新完成: audio=%s 用例=%s",
                len(audio_ids), len(refreshed or []))
        except Exception as e:
            # 刷新失败不回滚标注（标注已提交），只记录便于排查与人工重试
            logger.warning(
                "关联用例参考参数刷新失败: audio_ids=%s err=%s",
                audio_ids, e, exc_info=True)

    @staticmethod
    def _reset_session():
        """后台线程结束前释放线程级 DB session（gRPC 拦截器不会覆盖到本线程）。"""
        try:
            from shared.models.database import remove_db_session
            remove_db_session()
        except Exception:
            logger.debug("后台刷新线程释放 DB session 失败", exc_info=True)


_scheduler: Optional[TestCaseRefreshScheduler] = None
_scheduler_lock = threading.Lock()


def get_testcase_refresh_scheduler() -> TestCaseRefreshScheduler:
    """获取进程内唯一的刷新调度器（首次使用时绑定应用服务实例）。"""
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                from audio_service.application.services.audio_testcase_creation_service import (
                    audio_testcase_creation_service,
                )
                _scheduler = TestCaseRefreshScheduler(
                    audio_testcase_creation_service.refresh_test_cases_for_audios)
    return _scheduler
