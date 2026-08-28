# -*- coding: utf-8 -*-
"""
用例参考参数异步刷新任务

职责：
- 提供异步批量刷新用例 reference_params 的能力
- 支持查询任务进度

任务状态存于 Redis（key 前缀 reference_refresh:task:{task_id}），
api_gateway 可直接读 Redis 查询进度，无需跨服务 Python 直导。
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from task_service.infrastructure.persistence.testcase_repository import testcase_repository

logger = logging.getLogger(__name__)

# Redis 任务状态 key 前缀
_TASK_KEY_PREFIX = 'reference_refresh:task:'
# 任务状态 TTL（秒），24 小时后自动过期
_TASK_TTL_SECONDS = 24 * 60 * 60

_CST = timezone(timedelta(hours=8))


def _task_key(task_id: str) -> str:
    return f'{_TASK_KEY_PREFIX}{task_id}'


def _store():
    from shared.utils.redis_pubsub import RedisStore
    return RedisStore()


class ReferenceRefreshTask:
    """
    用例参考参数刷新任务

    用法：
        task = ReferenceRefreshTask(case_ids)
        thread = threading.Thread(target=task.run, daemon=True)
        thread.start()
        # 或直接调用 task.run() 同步执行
    """

    def __init__(self, case_ids: list):
        self.case_ids = case_ids
        self.task_id = str(uuid.uuid4())
        self.updated_count = 0
        self.failed_count = 0
        self.failed_cases = []
        self.status = 'pending'
        self.started_at = None
        self.completed_at = None

    def _persist(self):
        """把当前进度写入 Redis（HASH），同时通过 PubSub 推送进度，前端 WebSocket 可实时感知。"""
        total = len(self.case_ids)
        fields = {
            'task_id': self.task_id,
            'status': self.status,
            'total': total,
            'updated': self.updated_count,
            'failed': self.failed_count,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'failed_cases': self.failed_cases[:10],
        }
        _store().save_task(_task_key(self.task_id), fields, ttl_seconds=_TASK_TTL_SECONDS)
        # 推送进度到 WebSocket 通道（降级：Redis 不可用时只打日志，不影响刷新主流程）
        try:
            from shared.utils.redis_pubsub import RedisPubSub
            progress = 0
            if total and isinstance(total, int) and total > 0:
                progress = int((self.updated_count + self.failed_count) / total * 100)
            RedisPubSub().publish_progress(self.task_id, {
                'status': self.status,
                'total': total,
                'updated': self.updated_count,
                'failed': self.failed_count,
                'progress': progress,
            })
        except Exception as e:
            logger.warning(f"[ReferenceRefreshTask-{self.task_id}] 推送进度失败，降级忽略: {e}")

    def run(self, refresher=None):
        """在新线程中执行刷新任务

        Args:
            refresher: 可调用对象，签名为 refresher(test_case)，用于刷新单个用例的参考参数。
                        必须由调用方提供（task_service 不应反向依赖 api_gateway）。
        """
        self.status = 'running'
        self.started_at = datetime.now(_CST)
        self._persist()

        try:
            if refresher is None:
                raise RuntimeError(
                    "refresher 未提供；task_service 不应反向依赖 api_gateway，"
                    "调用方须显式注入 refresher"
                )

            test_cases = testcase_repository.list_testcases_by_ids(self.case_ids)

            logger.info(f"[ReferenceRefreshTask-{self.task_id}] 开始刷新 {len(test_cases)} 个用例")

            for tc in test_cases:
                try:
                    refresher(tc)
                    tc.updated_at = datetime.now(_CST)
                    testcase_repository.flush()
                    self.updated_count += 1

                    if self.updated_count % 10 == 0:
                        testcase_repository.commit()
                        self._persist()
                        logger.info(f"[ReferenceRefreshTask-{self.task_id}] 已刷新 {self.updated_count} 个用例")
                except Exception as e:
                    self.failed_count += 1
                    self.failed_cases.append({
                        'case_id': tc.id,
                        'error': str(e)
                    })
                    logger.error(f"[ReferenceRefreshTask-{self.task_id}] 刷新用例 {tc.id} 失败: {e}")

            testcase_repository.commit()
            self.status = 'completed'
            self.completed_at = datetime.now(_CST)
            self._persist()

            logger.info(f"[ReferenceRefreshTask-{self.task_id}] 完成! 成功: {self.updated_count}, 失败: {self.failed_count}")

        except Exception as e:
            self.status = 'failed'
            self.completed_at = datetime.now(_CST)
            self._persist()
            logger.error(f"[ReferenceRefreshTask-{self.task_id}] 任务执行失败: {e}")

    def get_progress(self) -> dict:
        """获取任务进度（从 Redis 读取）。"""
        data = _store().load_task(_task_key(self.task_id))
        if not data:
            return {
                'task_id': self.task_id,
                'status': 'not_found',
                'message': f'任务 {self.task_id} 不存在或已过期'
            }
        total = data.get('total', len(self.case_ids))
        updated = data.get('updated', 0)
        failed = data.get('failed', 0)
        progress = 0
        if total and isinstance(total, int) and total > 0:
            progress = int((updated + failed) / total * 100)
        return {
            'task_id': data.get('task_id', self.task_id),
            'status': data.get('status', 'unknown'),
            'total': total,
            'updated': updated,
            'failed': failed,
            'progress': progress,
            'started_at': data.get('started_at'),
            'completed_at': data.get('completed_at'),
            'failed_cases': data.get('failed_cases', [])[:10],
        }


def submit_reference_refresh_task(case_ids: list, executor=None, refresher=None) -> str:
    """
    提交用例参考刷新任务

    Args:
        case_ids: 用例ID列表
        executor: 执行器对象，需提供 _reference_refresh_pool.submit 方法（如 execution_engine 实例）。
                    如果未提供，将尝试延迟导入 execution_engine。
        refresher: 可调用对象，签名为 refresher(test_case)，用于刷新单个用例的参考参数。
                    必须由调用方提供。

    Returns:
        task_id: 任务ID，用于查询进度
    """
    task_id = str(uuid.uuid4())

    task = ReferenceRefreshTask(case_ids)
    task.task_id = task_id
    # 预写入 pending 状态，便于调用方立即查询
    task._persist()

    if executor is None:
        try:
            from task_service.core.execution_engine import execution_engine as executor
        except ImportError:
            raise RuntimeError("executor 未提供且 execution_engine 不可用")

    executor._reference_refresh_pool.submit(lambda: task.run(refresher=refresher))

    logger.info(f"[submit_reference_refresh_task] 任务已提交: {task_id}, 用例数: {len(case_ids)}")

    return task_id


def get_reference_refresh_task_status(task_id: str) -> dict:
    """
    获取刷新任务状态（从 Redis 读取）

    Args:
        task_id: 任务ID

    Returns:
        任务状态字典
    """
    data = _store().load_task(_task_key(task_id))
    if not data:
        return {
            'task_id': task_id,
            'status': 'not_found',
            'message': f'任务 {task_id} 不存在或已过期'
        }
    total = data.get('total', 0)
    updated = data.get('updated', 0)
    failed = data.get('failed', 0)
    progress = 0
    if isinstance(total, int) and total > 0:
        progress = int((updated + failed) / total * 100)
    return {
        'task_id': data.get('task_id', task_id),
        'status': data.get('status', 'unknown'),
        'total': total,
        'updated': updated,
        'failed': failed,
        'progress': progress,
        'started_at': data.get('started_at'),
        'completed_at': data.get('completed_at'),
        'failed_cases': data.get('failed_cases', [])[:10],
    }


def cleanup_finished_tasks(max_age_hours: int = 24):
    """
    清理已完成的旧任务（Redis TTL 已自动过期，本函数为兼容保留，空操作）

    Args:
        max_age_hours: 任务保留时间（小时）
    """
    # Redis 自带 TTL，无需显式清理
    pass
