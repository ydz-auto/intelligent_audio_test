# -*- coding: utf-8 -*-
"""tests/unit 测试隔离夹具（INT-81 验收补充）。

真实日志链（ReevaluationExecutor._log、审计写入等）会经 get_db_handler()
惰性创建进程级全局 DatabaseLogHandler，其后台 worker 与队列条目会跨测试
文件存活：后续测试运行期间继续发 TASK_LOG 事件 / 调用（可能已被替换的）
batch_create_logs，污染 INT-65 restore 事件计数断言与 audit emit captured
断言（全量回归中同类失败在两个用例间游走的根因）。

本夹具在每个测试结束后清空积压并停掉 worker，重置全局引用；后续测试
经 get_db_handler() 惰性重建干净实例。
"""
import queue

import pytest


@pytest.fixture(autouse=True)
def _quiesce_global_log_worker():
    yield

    import shared.utils.log_handler._state as lh_state

    prev = lh_state._global_db_handler
    if prev is not None:
        try:
            # 先清空积压条目再发退出哨兵：worker 对 DB 路径批写失败有 1s 退避，
            # 依赖 worker 自行清空会超时遗留活线程
            while True:
                try:
                    prev.queue.get_nowait()
                except queue.Empty:
                    break
            prev.queue.put(None)
            worker = getattr(prev, 'worker_thread', None)
            if worker is not None:
                worker.join(timeout=1.0)
        except Exception:
            pass
        lh_state._global_db_handler = None
