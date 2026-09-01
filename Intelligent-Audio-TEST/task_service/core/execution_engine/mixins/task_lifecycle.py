# -*- coding: utf-8 -*-
"""任务生命周期 Mixin（从 _task_runner_mixin.py 拆分，P4-4）。

包含任务启动、API 初始化与主循环编排：
- _run_task：任务执行总编排入口
- _init_task_execution：API 任务初始化
- _process_task_main_loop：主循环（取用例 → 设备检查 → 分发执行）
"""
from datetime import datetime

from task_service.infrastructure.persistence.models import Task, TaskCase
from shared.models.database import get_db_session
from shared.utils.status_constants import TaskStatus
from shared.utils.config_manager import config_manager

import logging

logger = logging.getLogger(__name__)


class TaskLifecycleMixin:
    """任务生命周期编排：启动 / 初始化 / 主循环"""

    def _run_task(self, task_id, stop_event, pause_event):
        """执行测试任务的核心方法

        Args:
            task_id: 任务ID
            stop_event: 停止事件，用于通知任务停止
            pause_event: 暂停事件，用于通知任务暂停/恢复
        """
        try:
            from task_service.infrastructure.persistence.models import Log, TaskCase
            from shared.models.database import remove_db_session

            # 使用本地会话获取任务对象（初始设置）
            local_db_session = get_db_session()
            try:
                # 获取任务对象
                task = local_db_session.get(Task, task_id)
                if not task:
                    self._log(
                        level='ERROR',
                        content=f"任务 {task_id} 不存在，无法执行",
                        task_id=task_id
                    )
                    return

                # 记录任务开始日志
                self._log(
                    level='INFO',
                    content=f"开始执行任务 {task_id}, 类型: {task.type}",
                    task_id=task_id
                )

                # 更新任务状态为运行中，并记录开始时间
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now(self.utc_plus_8)
                local_db_session.commit()
                # 发送进度更新，传递task对象以便触发强制更新逻辑
                self._emit_progress(task)
            finally:
                local_db_session.close()

            try:
                # API任务初始化
                should_continue = self._init_task_execution(task_id)
                if not should_continue:
                    return

                # 主循环：处理测试用例
                self._process_task_main_loop(task_id, stop_event, pause_event)

                # 检查是否所有测试用例都已执行完成，提前更新任务状态
                task = self._update_post_loop_status(task_id)

                # 等待所有测试用例执行完成
                self._wait_for_cases_completion(task_id, task, stop_event)

                # 最终状态更新
                self._finalize_task_status(task_id, task, stop_event)
            except Exception as e:
                # 异常处理
                self._handle_task_exception(task_id, e)
            finally:
                # 清理任务资源
                self._cleanup_task_resources(task_id, stop_event)
        finally:
            # 后台线程结束时清理本线程 DB session，防止连接泄漏
            try:
                from shared.models.database import remove_db_session
                remove_db_session()
            except Exception:
                logger.debug("任务执行结束清理 DB session 失败 task_id=%s", task_id, exc_info=True)

    def _init_task_execution(self, task_id):
        """API任务初始化

        Returns:
            True 表示初始化成功，False 表示任务不存在或初始化失败
        """
        # 使用本地会话确保独立可靠的会话
        local_db_session = get_db_session()
        try:
            # 重新获取任务对象，确保它在有效会话中
            task = local_db_session.get(Task, task_id)
            if not task:
                self._log(
                    level='ERROR',
                    content=f"任务 {task_id} 不存在，无法执行",
                    task_id=task_id
                )
                return False

            # API任务初始化
            if task.type == 'api':
                try:
                    from task_service.infrastructure.persistence.models import TaskAPI
                    # 获取API配置
                    task_api = local_db_session.query(TaskAPI).filter_by(task_id=task.id).first()
                    api_config = None
                    if task_api:
                        # P3 改造：通过 gRPC 调用 api_test_service 获取 API 配置，替代直连 PO
                        try:
                            from shared.clients.grpc_clients import get_api_test_service_stub
                            from shared.proto import api_test_service_pb2 as api_pb
                            from shared.utils.grpc_json import loads as _loads
                            stub = get_api_test_service_stub()
                            resp = stub.GetAPIConfig(api_pb.GetAPIConfigRequest(api_id=task_api.api_id))
                            if resp.success and resp.data:
                                api_config = _loads(resp.data, {})
                        except Exception as grpc_e:
                            self._log(
                                level='WARNING',
                                content=f"通过 gRPC 获取 API 配置失败 (api_id={task_api.api_id}): {str(grpc_e)}",
                                task_id=task_id
                            )

                    # 获取可用的API端点
                    # 注意：gRPC 返回的 dict 中端点字段名为 'endpoints'（对应 _api_to_dict）
                    available_endpoints = []
                    if api_config and api_config.get('endpoints'):
                        available_endpoints = [ep for ep in api_config.get('endpoints') if ep.get('status') == 'online']
                        available_endpoints.sort(key=lambda x: x.get('priority', 0), reverse=True)

                    # 确定最大工作线程数
                    # 并发参数配置化：端点未配置 max_process 时回退到 config_manager 默认值
                    default_max_process = config_manager.get_value('api_executor', 'default_max_process', 5)
                    if available_endpoints:
                        # 计算所有可用端点的最大进程数之和
                        max_workers = sum(ep.get('max_process', default_max_process) for ep in available_endpoints)
                    elif api_config:
                        max_workers = api_config.get('default_max_process') or default_max_process
                    else:
                        max_workers = default_max_process

                    # 保存API配置和可用端点到任务对象
                    task._api_config = api_config
                    task._available_endpoints = available_endpoints

                    # 微服务化后：不再创建本地线程池，API 用例通过 gRPC 调用 api_test_service 执行
                    # api_test_service 内部管理自己的线程池和并发控制
                    self._log(
                        level='INFO',
                        content=f"API任务 {task_id} 初始化成功，执行下沉到 api_test_service",
                        task_id=task_id,
                        api_id=api_config.get('id') if api_config else None
                    )
                except Exception as e:
                    self._log(
                        level='ERROR',
                        content=f"API任务 {task_id} 初始化失败: {str(e)}",
                        task_id=task_id
                    )
                    # API任务初始化失败，将任务标记为失败
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now(self.utc_plus_8)
                    task.error_message = f"API任务初始化失败: {str(e)}"
                    local_db_session.commit()
                    return False
        finally:
            local_db_session.close()

        return True

    def _process_task_main_loop(self, task_id, stop_event, pause_event):
        """主循环：处理测试用例 — 编排入口"""
        while not stop_event.is_set():
            local_db_session = get_db_session()
            try:
                task = local_db_session.get(Task, task_id)
                if not task:
                    self._log(level='ERROR', content=f"任务 {task_id} 不存在，无法执行", task_id=task_id)
                    break

                tc_rel = self._get_next_pending_case(task_id, local_db_session)
                if not tc_rel:
                    if self._handle_no_pending_case(task_id, task, local_db_session):
                        continue
                    break

                if not pause_event.is_set():
                    self._emit_progress(task)
                    pause_event.wait()
                if stop_event.is_set():
                    break

                device_ok, error_msg = self._check_e2e_devices(task_id, task, tc_rel, local_db_session)
                if not device_ok:
                    self._handle_device_check_failed(task_id, task, tc_rel, error_msg, local_db_session)
                    continue

                task = local_db_session.get(Task, task_id)
                if not task:
                    continue
                self._dispatch_case_by_type(task_id, task, tc_rel, local_db_session)
                local_db_session.commit()
                self._emit_progress(task)
            finally:
                local_db_session.close()
