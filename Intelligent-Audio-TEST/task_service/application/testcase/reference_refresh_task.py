# -*- coding: utf-8 -*-
"""
用例参考参数异步刷新任务

职责：
- 提供异步批量刷新用例 reference_params 的能力
- 支持查询任务进度
- 进程重启后接管孤儿任务（INT-76）：任务记录含输入 case_ids 与归属实例，
  启动时按归属实例存活判定收养重放，同 task_id 重新入队执行

任务状态存于 Redis（key 前缀 reference_refresh:task:{task_id}），
api_gateway 可直接读 Redis 查询进度，无需跨服务 Python 直导。
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from task_service.config.config import Config
from task_service.infrastructure.persistence.testcase_repository import testcase_repository

logger = logging.getLogger(__name__)

# Redis 任务状态 key 前缀
_TASK_KEY_PREFIX = 'reference_refresh:task:'
# 孤儿任务认领锁 TTL（秒）：多实例同时启动恢复时仅一个实例接管同一任务，
# 锁到期自然失效，不影响后续正常恢复
_ADOPT_LOCK_TTL_SECONDS = 60

_CST = timezone(timedelta(hours=8))


def _task_key(task_id: str) -> str:
    return f'{_TASK_KEY_PREFIX}{task_id}'


def _task_ttl() -> int:
    return Config.REFERENCE_REFRESH_TASK_TTL_SECONDS


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
        # 提交实例归属与恢复次数（INT-76）：进程重启后按归属存活判定收养重放
        self.instance_id = None
        self.recovered_count = 0

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
            'instance_id': self.instance_id,
            'recovered_count': self.recovered_count,
        }
        _store().save_task(_task_key(self.task_id), fields, ttl_seconds=_task_ttl())
        # 推送进度到 WebSocket 通道（降级：Redis 不可用时只打日志，不影响刷新主流程）
        try:
            from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
            progress = 0
            if total and isinstance(total, int) and total > 0:
                progress = int((self.updated_count + self.failed_count) / total * 100)
            EventBus().publish(EventChannel.TASK_EVENTS, EventType.TASK_PROGRESS, {
                'event': 'task_progress',
                'task_id': self.task_id,
                'data': {
                    'task_id': self.task_id,
                    'status': self.status,
                    'total': total,
                    'updated': self.updated_count,
                    'failed': self.failed_count,
                    'progress': progress,
                },
            })
        except Exception as e:
            logger.warning(f"[ReferenceRefreshTask-{self.task_id}] 推送进度失败，降级忽略: {e}")

    def _publish_completion_event(self):
        """任务终态补发 CASE_EVENTS / case_batch_action_completed 领域事件（INT-75）。

        提交时 batch_action 调度器已发布 status='submitted' 事件；此处补发
        completed/failed 终态。降级：Redis 不可用时只打日志，不影响任务状态。
        """
        try:
            from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
            from task_service.domain.events.testcase_events import TestCaseBatchAction
            event = TestCaseBatchAction(
                action='refresh_reference',
                case_ids=list(self.case_ids),
                success_count=self.updated_count,
                message=f"异步刷新任务终态: 成功 {self.updated_count}, 失败 {self.failed_count}",
                status=self.status,
                async_task_id=self.task_id,
            )
            EventBus().publish(EventChannel.CASE_EVENTS, EventType.CASE_BATCH_ACTION_COMPLETED, event.to_dict())
        except Exception as e:
            logger.warning(f"[ReferenceRefreshTask-{self.task_id}] 发布终态事件失败，降级忽略: {e}")

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
            self._publish_completion_event()

            logger.info(f"[ReferenceRefreshTask-{self.task_id}] 完成! 成功: {self.updated_count}, 失败: {self.failed_count}")

        except Exception as e:
            self.status = 'failed'
            self.completed_at = datetime.now(_CST)
            self._persist()
            self._publish_completion_event()
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
            'recovered_count': data.get('recovered_count', 0),
            'error_message': data.get('error_message'),
        }


def submit_reference_refresh_task(case_ids: list, executor=None, refresher=None,
                                  task_id=None, recovered_count=0) -> str:
    """
    提交用例参考刷新任务

    Args:
        case_ids: 用例ID列表
        executor: 执行器对象，需提供 _reference_refresh_pool.submit 方法（如 execution_engine 实例）。
                    如果未提供，将尝试延迟导入 execution_engine。
        refresher: 可调用对象，签名为 refresher(test_case)，用于刷新单个用例的参考参数。
                    必须由调用方提供。
        task_id: 复用既有任务 ID（孤儿恢复重放时保持前端轮询 ID 不变），缺省新生成
        recovered_count: 已恢复次数（孤儿恢复重放时累加，供追溯）

    Returns:
        task_id: 任务ID，用于查询进度
    """
    task_id = task_id or str(uuid.uuid4())

    if executor is None:
        try:
            from task_service.core.execution_engine import execution_engine as executor
        except ImportError:
            raise RuntimeError("executor 未提供且 execution_engine 不可用")

    task = ReferenceRefreshTask(case_ids)
    task.task_id = task_id
    task.recovered_count = recovered_count
    task.instance_id = getattr(executor, 'instance_id', None)
    # 预写入 pending 状态，便于调用方立即查询
    task._persist()
    # 任务输入 case_ids 仅首次写入（INT-76）：后续 _persist 为 HASH 字段合并不覆盖，
    # 进程重启后据此判定孤儿并重放
    _store().save_task(_task_key(task_id), {'case_ids': list(case_ids)}, ttl_seconds=_task_ttl())

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
        'recovered_count': data.get('recovered_count', 0),
        'error_message': data.get('error_message'),
    }


def _claim_adoption(task_id: str) -> bool:
    """认领孤儿任务：SETNX 锁保证多实例同时恢复时仅一个实例接管同一任务。

    Redis 锁不可用时放行（降级为单实例语义，重放本身幂等，重复执行无害）。
    """
    try:
        acquired = _store().redis_client.set(
            f'reference_refresh:adopt:{task_id}', '1', nx=True, ex=_ADOPT_LOCK_TTL_SECONDS)
        return bool(acquired)
    except Exception as e:
        logger.warning("[ReferenceRefresh] 认领锁不可用，放行恢复 task_id=%s: %s", task_id, e)
        return True


def _default_refresher():
    """默认刷新器：与批量入口共用同一参考参数生成实现（延迟导入避免循环依赖）。"""
    from task_service.application.testcase.testcase_batch_reference_mixin import (
        _apply_reference_params_to_config,
    )
    return _apply_reference_params_to_config


def _mark_unrecoverable(store, key: str, task_id: str, reason: str) -> None:
    """无法重放的历史遗留任务记录标记为 failed 终态，避免前端轮询到永久 running。"""
    store.save_task(key, {
        'status': 'failed',
        'completed_at': datetime.now(_CST).isoformat(),
        'error_message': reason,
    }, ttl_seconds=_task_ttl())
    logger.warning("[ReferenceRefresh] 任务无法恢复，已标记失败: task_id=%s, 原因: %s", task_id, reason)


def recover_orphan_reference_refresh_tasks(instance_id: str = None) -> int:
    """启动恢复（INT-76）：接管归属实例已下线的孤儿刷新任务，同 task_id 重新入队。

    多实例语义与主任务调度器孤儿收养一致（SchedulerMixin._adopt_orphan_tasks）：
    - 归属实例心跳仍在（存活）的 pending/running 任务不动，由其继续推进；
    - 归属实例已下线、或历史遗留未归属（无 instance_id）的任务收养重放；
    - 刷新本身幂等（重新生成参考参数覆盖写入），整任务重跑安全。

    需在 lifespan 启动阶段、本实例注册之后调用。

    Args:
        instance_id: 本实例标识（收养后写入任务记录作为新归属），仅用于日志追溯。

    Returns:
        收养（重新入队）的任务数
    """
    from shared.utils.service_registry import RedisServiceRegistry

    store = _store()
    try:
        alive_ids = RedisServiceRegistry().get_alive_ids('task_service')
    except Exception as e:
        logger.warning("[ReferenceRefresh] 读取存活实例列表失败，跳过孤儿刷新任务恢复: %s", e)
        return 0

    adopted = 0
    for key in store.scan_keys(f'{_TASK_KEY_PREFIX}*'):
        task_id = key[len(_TASK_KEY_PREFIX):]
        data = store.load_task(key)
        if not data:
            continue
        if data.get('status') not in ('pending', 'running'):
            continue

        owner = data.get('instance_id')
        if owner and owner in alive_ids:
            # 归属实例仍存活，由其继续推进，本实例不接管
            continue

        case_ids = data.get('case_ids')
        if not isinstance(case_ids, list) or not case_ids:
            _mark_unrecoverable(store, key, task_id, '任务记录缺少 case_ids，进程重启后无法重放')
            continue

        if not _claim_adoption(task_id):
            logger.info("[ReferenceRefresh] 任务已被其他实例认领，跳过: task_id=%s", task_id)
            continue

        recovered_count = int(data.get('recovered_count') or 0) + 1
        submit_reference_refresh_task(
            case_ids,
            task_id=task_id,
            recovered_count=recovered_count,
            refresher=_default_refresher(),
        )
        adopted += 1
        logger.info("[ReferenceRefresh] 孤儿任务已恢复重放: task_id=%s, 用例数=%s, 第 %s 次恢复, 原归属=%s",
                    task_id, len(case_ids), recovered_count, owner or '未归属')

    return adopted


def cleanup_finished_tasks(max_age_hours: int = 24):
    """
    清理已完成的旧任务（Redis TTL 已自动过期，本函数为兼容保留，空操作）

    Args:
        max_age_hours: 任务保留时间（小时）
    """
    # Redis 自带 TTL，无需显式清理
    pass
