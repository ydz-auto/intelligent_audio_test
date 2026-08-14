# -*- coding: utf-8 -*-
"""TaskCrudService — 任务 CRUD 应用服务（写操作 + 委托入口）。

将网关 TaskCommandService / TaskQueryService / TaskLifecycleService 的
业务逻辑下沉到 task_service，通过 gRPC TaskConfigService 暴露。

职责拆分：
- 写操作（create/update/delete/update_cases/batch_action/merge）：保留在本类
- 读操作（list/get_detail/progress/stats/case_detail/case_results）：
  委托 ``task_query_service``
- 生命周期操作（start/retry/control/stop/rextract）：
  委托 ``task_lifecycle_service``

约定：
- 所有方法返回 dict: {success, message, data, code?}
- 复杂参数通过 JSON dict 传递
- 通过 task_repository 访问 DB，不直接持有 session
"""
from __future__ import annotations

import logging

from shared.utils.status_constants import TaskStatus

from task_service.infrastructure.persistence.task_repository import task_repository

logger = logging.getLogger(__name__)


class TaskCrudService:
    """任务 CRUD 应用服务（写操作）。读/生命周期方法委托给对应服务。"""

    def __init__(self):
        self._lifecycle = None
        self._query = None

    @property
    def lifecycle(self):
        """延迟加载生命周期服务，避免循环依赖。"""
        if self._lifecycle is None:
            from task_service.application.task.task_lifecycle_service import task_lifecycle_service
            self._lifecycle = task_lifecycle_service
        return self._lifecycle

    @property
    def query(self):
        """延迟加载查询服务。"""
        if self._query is None:
            from task_service.application.task.task_query_service import task_query_service
            self._query = task_query_service
        return self._query

    # ==================== 写操作 ====================

    def create(self, data: dict) -> dict:
        """创建任务。"""
        try:
            from api_gateway.application.services.stats_cache import refresh_stats_cache

            task_id = task_repository.create_task_with_relations(
                name=data.get('name'),
                task_type=data.get('type'),
                description=data.get('description'),
                config=data.get('config'),
                algorithm_type=data.get('algorithm_type'),
                algorithm_params=data.get('algorithm_params'),
                case_ids=data.get('case_ids', []),
                device_ids=data.get('device_ids', []),
                api_ids=data.get('api_ids', []),
                created_by=data.get('created_by'),
            )
            if task_id is None:
                return {'success': False, 'message': '创建任务失败', 'data': None, 'code': 500}

            try:
                refresh_stats_cache()
            except Exception:
                logger.warning("创建任务后刷新统计缓存失败", exc_info=True)

            return {'success': True, 'message': '任务创建成功', 'data': {'id': task_id}, 'code': 201}
        except Exception as e:
            logger.error(f"创建任务失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def update(self, task_id: int, data: dict) -> dict:
        """更新任务名称/描述。"""
        try:
            updated = task_repository.update_task(
                task_id, name=data.get('name'), description=data.get('description')
            )
            if not updated:
                return {'success': False, 'message': '未找到任务', 'data': None, 'code': 404}
            return {'success': True, 'message': '任务已更新', 'data': {'id': task_id, 'name': data.get('name')}}
        except Exception as e:
            logger.error(f"更新任务失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def delete(self, task_id: int) -> dict:
        """软删除任务。"""
        try:
            from api_gateway.application.services.stats_cache import refresh_stats_cache

            # 先停止运行中的任务
            task = self.query.get_task_detail(task_id)
            if not task.get('success'):
                return task

            status = (task.get('data') or {}).get('status')
            if status in [TaskStatus.RUNNING, TaskStatus.PAUSED]:
                try:
                    from task_service.core.execution_engine import execution_engine
                    execution_engine.control_task(None, task_id, 'stop')
                except Exception:
                    logger.warning("删除任务时停止运行中任务失败 task_id=%s", task_id, exc_info=True)
                try:
                    from task_service.core.execution_engine import execution_engine
                    execution_engine.remove_from_queue(task_id)
                except Exception:
                    logger.warning("删除任务时从队列移除任务失败 task_id=%s", task_id, exc_info=True)

            ok = task_repository.soft_delete(task_id)
            if not ok:
                return {'success': False, 'message': '未找到任务', 'data': None, 'code': 404}

            try:
                refresh_stats_cache()
            except Exception:
                logger.debug("删除任务后刷新统计缓存失败 task_id=%s", task_id, exc_info=True)

            return {'success': True, 'message': '任务已删除', 'data': None}
        except Exception as e:
            logger.error(f"删除任务失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def update_cases(self, task_id: int, data: dict) -> dict:
        """动态添加/移除用例。"""
        try:
            action = data.get('action')
            case_ids = data.get('case_ids', [])

            result = task_repository.update_cases(task_id, action, case_ids)
            if result is None:
                return {'success': False, 'message': '任务 ID 不存在', 'data': None, 'code': 404}
            if 'error' in result:
                return {'success': False, 'message': result['error'], 'data': None, 'code': result.get('code', 400)}

            return {
                'success': True,
                'message': 'Cases updated successfully',
                'data': {'task_id': str(result['task_id']), 'total_count': result['total_count']},
            }
        except Exception as e:
            logger.error(f"更新用例失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def batch_action(self, data: dict, query_args: dict = None) -> dict:
        """批量操作（delete/export）。"""
        try:
            action = data.get('action')
            task_ids = data.get('task_ids', [])

            if action == 'delete':
                # 先停止运行中的任务：通过读模型查询状态，停止副作用由执行引擎处理
                for tid in task_ids:
                    task = self.query.get_task_detail(tid)
                    if task.get('success') and (task.get('data') or {}).get('status') in [TaskStatus.RUNNING, TaskStatus.PAUSED]:
                        try:
                            from task_service.core.execution_engine import execution_engine
                            execution_engine.control_task(None, tid, 'stop')
                        except Exception:
                            logger.debug("批量删除时停止运行中任务失败 task_id=%s", tid, exc_info=True)
                        try:
                            from task_service.core.execution_engine import execution_engine
                            execution_engine.remove_from_queue(tid)
                        except Exception:
                            logger.debug("批量删除时从队列移除任务失败 task_id=%s", tid, exc_info=True)

                deleted_count = task_repository.batch_stop_and_soft_delete(task_ids)

                return {'success': True, 'message': f'成功删除 {deleted_count} 个任务', 'data': None}

            elif action == 'export':
                format_ = (query_args or {}).get('format', 'json')
                tasks_data = task_repository.get_tasks_for_export(task_ids)

                if not tasks_data:
                    return {'success': False, 'message': '没有可导出的数据', 'data': None, 'code': 404}

                if format_ in ['excel', 'pdf']:
                    # 导出文件生成由网关处理（需要 FileResponse）
                    return {'success': True, 'message': '数据准备就绪', 'data': {'tasks': tasks_data, 'format': format_}}

                return {'success': True, 'message': '数据准备就绪', 'data': tasks_data}

            return {'success': False, 'message': f'未知操作: {action}', 'data': None, 'code': 400}
        except Exception as e:
            logger.error(f"批量操作失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def merge(self, data: dict) -> dict:
        """合并多个已完成任务。"""
        try:
            task_ids = data.get('task_ids', [])
            if not task_ids or len(task_ids) < 2:
                return {'success': False, 'message': '合并需要至少两个任务', 'data': None, 'code': 400}

            from datetime import datetime, timezone, timedelta
            _utc8 = timezone(timedelta(hours=8))

            merged_task_id, total_results = task_repository.merge_tasks(
                source_task_ids=task_ids,
                merged_task_name=data.get('merged_task_name') or f"合并任务_{datetime.now(_utc8).strftime('%Y%m%d%H%M%S')}",
                merged_task_type=data.get('merged_task_type') or data.get('type') or 'api',
                description=data.get('description') or '',
                created_by=data.get('created_by'),
                now=datetime.now(_utc8),
            )

            return {
                'success': True,
                'message': f"成功合并 {len(task_ids)} 个任务",
                'data': {
                    'merged_task_id': merged_task_id,
                    'source_task_ids': task_ids,
                    'total_results': total_results,
                },
                'code': 201,
            }
        except Exception as e:
            logger.error(f"合并任务失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    # ==================== 读操作（委托 task_query_service） ====================

    def list_tasks(self, page=1, per_page=10, status=None, task_type=None,
                   algorithm_type=None, search=None, start_date=None, end_date=None) -> dict:
        """获取任务列表。"""
        return self.query.list_tasks(
            page=page, per_page=per_page, status=status, task_type=task_type,
            algorithm_type=algorithm_type, search=search, start_date=start_date, end_date=end_date,
        )

    def get_task_detail(self, task_id: int) -> dict:
        """获取单个任务详情。"""
        return self.query.get_task_detail(task_id)

    def get_task_progress(self, task_id: int) -> dict:
        """获取任务实时进度。"""
        return self.query.get_task_progress(task_id)

    def get_task_stats(self, task_id: int) -> dict:
        """获取任务统计信息。"""
        return self.query.get_task_stats(task_id)

    def get_case_detail(self, task_id: int, case_id) -> dict:
        """获取单个用例的执行详情。"""
        return self.query.get_case_detail(task_id, case_id)

    def get_case_results(self, task_id: int, case_id) -> dict:
        """获取单个用例的执行结果。"""
        return self.query.get_case_results(task_id, case_id)

    # ==================== 生命周期操作（委托 task_lifecycle_service） ====================

    def start(self, task_id: int) -> dict:
        """启动任务。"""
        return self.lifecycle.start(task_id)

    def retry(self, task_id: int) -> dict:
        """重新执行失败或未完成的用例。"""
        return self.lifecycle.retry(task_id)

    def control(self, task_id: int, data: dict) -> dict:
        """任务运行时控制。"""
        return self.lifecycle.control(task_id, data)

    def stop(self, task_id: int) -> dict:
        """停止任务。"""
        return self.lifecycle.stop(task_id)

    def rextract(self, task_id: int, data: dict) -> dict:
        """重新提取设备输出。"""
        return self.lifecycle.reextract(task_id, data)


# 模块级单例
task_crud_service = TaskCrudService()
