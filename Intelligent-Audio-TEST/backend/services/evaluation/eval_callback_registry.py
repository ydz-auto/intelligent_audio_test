# -*- coding: utf-8 -*-
"""
评估任务回调注册表 + 兜底结算线程（事件化评估）

背景：
  原先后端提交异步评估任务后，由 endpoint_worker 阻塞轮询（wait_for_task_completion，
  5s 一次、600s 上限）。单个评估任务超过 600s 时会把维度直接判失败，进而把用例判为
  评估失败——即使 eval_server 稍后其实能算完。

事件化方案：
  提交评估任务时带上 callback_url，eval_server 算完后主动 POST 回调结果；
  后端把"待完成任务的上下文"注册到这里，回调到达后取出上下文并写维度结果。
  若回调丢失（网络抖动/服务重启），由兜底结算线程周期查询 get_final_result 补写，
  避免任务卡死；同时不再有 600s 硬超时误判。

上下文 ctx 字段：
  eval_task_id   评估任务ID（eval_server 生成）
  endpoint_url   提交到的评估端点（兜底结算时轮询该端点）
  on_complete    回调成功处理器（写维度结果 + 更新用例状态）
  on_failed      回调失败处理器（标记维度/用例失败）
  submitted_at   提交时间戳（兜底结算判断依据）
"""

import threading
import time
import logging

logger = logging.getLogger('eval_callback_registry')


class EvalCallbackRegistry:
    """线程安全的评估任务回调注册表（eval_task_id -> ctx）"""

    _lock = threading.Lock()
    _entries = {}

    @classmethod
    def register(cls, eval_task_id, ctx):
        ctx['submitted_at'] = time.time()
        with cls._lock:
            cls._entries[eval_task_id] = ctx
        ensure_fallback_thread()
        return eval_task_id

    @classmethod
    def pop(cls, eval_task_id):
        with cls._lock:
            return cls._entries.pop(eval_task_id, None)

    @classmethod
    def get(cls, eval_task_id):
        with cls._lock:
            return cls._entries.get(eval_task_id)

    @classmethod
    def all(cls):
        with cls._lock:
            return dict(cls._entries)

    @classmethod
    def count(cls):
        with cls._lock:
            return len(cls._entries)


eval_callback_registry = EvalCallbackRegistry()

# ---------------------------------------------------------------------------
# 兜底结算线程：回调丢失时周期补查 get_final_result，避免任务卡死
# ---------------------------------------------------------------------------

FALLBACK_SCAN_INTERVAL = 60     # 扫描间隔（秒）
FALLBACK_FIRST_CHECK = 1200     # 提交后超过该秒数仍未回调，主动查询一次结果
FALLBACK_HARD_TIMEOUT = 7200    # 提交后超过该秒数仍未回调，判失败收尾

_fallback_thread = None
_fallback_thread_lock = threading.Lock()


def ensure_fallback_thread():
    """确保兜底结算线程已启动（注册首个任务时触发）"""
    global _fallback_thread
    with _fallback_thread_lock:
        if _fallback_thread is None or not _fallback_thread.is_alive():
            _fallback_thread = threading.Thread(
                target=_fallback_loop, daemon=True, name='EvalCallbackFallback'
            )
            _fallback_thread.start()


def _safe_call(fn, *args, **kwargs):
    """安全调用处理器，异常只记录不抛出（避免兜底线程因单个任务崩溃）"""
    if not fn:
        return
    try:
        fn(*args, **kwargs)
    except Exception as e:
        logger.warning(f'评估结果处理器执行异常: {e}', exc_info=True)


def _fallback_loop():
    while True:
        time.sleep(FALLBACK_SCAN_INTERVAL)
        now = time.time()
        entries = eval_callback_registry.all()
        for eval_task_id, ctx in entries.items():
            elapsed = now - ctx.get('submitted_at', now)
            if elapsed < FALLBACK_FIRST_CHECK:
                continue

            on_complete = ctx.get('on_complete')
            on_failed = ctx.get('on_failed')
            endpoint_url = ctx.get('endpoint_url')

            # 超硬时限仍未回调：判失败收尾，避免任务永久卡死
            if elapsed >= FALLBACK_HARD_TIMEOUT:
                logger.warning(
                    f'评估任务 {eval_task_id} 回调超时({int(elapsed)}s)，按失败收尾'
                )
                eval_callback_registry.pop(eval_task_id)
                _safe_call(on_failed, f'评估任务回调超时({int(elapsed)}s)')
                continue

            # 主动补查一次结果
            try:
                import requests as _requests
                result_url = f"{endpoint_url.rstrip('/')}/api/get_final_result/{eval_task_id}"
                resp = _requests.get(result_url, timeout=30)
                data = resp.json() if resp.status_code == 200 else {}
                if isinstance(data, dict) and data.get('code') == 0:
                    result = data.get('data', {}).get('result', {})
                    eval_callback_registry.pop(eval_task_id)
                    logger.info(f'兜底补写评估结果: {eval_task_id}, 等待={int(elapsed)}s')
                    _safe_call(on_complete, result)
                elif isinstance(data, dict) and data.get('__error__'):
                    # 202（仍在处理）或 404/500：暂不处理，留待下轮扫描或硬超时收尾
                    pass
            except Exception as e:
                logger.warning(f'兜底查询评估任务失败: eval_task_id={eval_task_id}, err={e}')
