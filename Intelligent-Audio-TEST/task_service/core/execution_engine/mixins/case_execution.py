from datetime import datetime
from task_service.infrastructure.persistence.models import Task, TaskCase
from task_service.infrastructure.acl.report_acl_repository import api_test_acl_repository
from shared.models.database import create_db_session
from shared.utils.status_constants import TaskCaseStatus

# gRPC 调用封装函数（模块级）
from task_service.core.execution_engine.mixins.grpc_helpers import (
    _execute_e2e_case_via_grpc,
)


class CaseExecutionMixin:
    """测试用例执行相关的方法：API/E2E 用例执行、入口健康状态"""

    def _update_endpoint_health(self, endpoint_url, available):
        """更新API入口(Master)的可用性状态
        
        Args:
            endpoint_url: 入口URL
            available: 是否可用
        """
        with self.api_entry_lock:
            if endpoint_url not in self.api_entry_status:
                self.api_entry_status[endpoint_url] = {'available': True, 'fail_count': 0}
            
            old_status = self.api_entry_status[endpoint_url]['available']
            self.api_entry_status[endpoint_url]['available'] = available
            
            if not available:
                self.api_entry_status[endpoint_url]['fail_count'] += 1
            else:
                self.api_entry_status[endpoint_url]['fail_count'] = 0
                
            if old_status != available:
                status_str = "可用" if available else "不可用"
                self._log(level='WARNING' if not available else 'INFO', 
                         content=f"API入口状态变更: {endpoint_url} -> {status_str}")

    def _execute_api_case(self, task_id, tc_rel_id, dispatch_target=None,
                          device_type=None, device_id=None):
        """执行API测试用例

        微服务化迁移后，不再直接调用本地 self.api_executor，
        经 ACL 仓储跨服务分发到 api_test_service（INT-71：core 层
        不直触 gRPC stub；device_type/device_id 路由决策随请求贯通）。

        路由决策表（05_路由与废弃.md 2.1）：
        - websocket_api → StartAPITest（携带 device_type/device_id，
          会话亲和场景经 dispatch_target 直连绑定实例）
        - 其余（http_api）→ StartAPITest 同通道分发（02_架构设计.md：
          调度侧随契约演进收敛到 StartAPITest），device_type 随请求传递

        Args:
            task_id: 任务ID
            tc_rel_id: 任务用例关联ID
            dispatch_target: 会话亲和路由目标（websocket_api 用例经
                route_or_bind 解析）；None 走默认负载均衡通道
            device_type: 用例级被测设备类型（TaskCase.device_type）
            device_id: 被测设备 ID（API 类=api.id）

        Returns:
            执行结果
        """
        try:
            # 逐用例精确分发：StartAPITestRequest 携带 case_ids +
            # device_type/device_id（调度层路由决策随请求传递）
            api_test_acl_repository.start_api_test(
                task_id=task_id,
                case_ids=[tc_rel_id],
                device_type=device_type or '',
                device_id=device_id or '',
                dispatch_target=dispatch_target,
            )

            # 更新任务统计信息（基于 api_test_service 已写入数据库的 TaskCase 状态）
            # INT-40：嵌套链路必须用独立 Session——此处处于主循环的调用栈内，
            # 主循环仍持有 scoped session 上的 Task ORM 对象；若取线程共享的
            # scoped session 并 close，会把外层对象 expunge，后续
            # _emit_progress(task) 访问已过期属性即抛 DetachedInstanceError
            local_db_session = create_db_session()
            try:
                tc_rel = local_db_session.get(TaskCase, tc_rel_id)
                if tc_rel:
                    # 若 api_test_service 未设置 started_at，在此兜底
                    if not tc_rel.started_at:
                        tc_rel.started_at = datetime.now(self.utc_plus_8)
                        local_db_session.commit()
            finally:
                local_db_session.close()

            return True
        except Exception as e:
            # 捕获所有异常，确保测试用例状态被正确更新
            import traceback
            error_trace = traceback.format_exc()
            error_msg = f"API 执行异常: {str(e)}"

            self._log(
                level='ERROR',
                content=f"API 用例执行失败: {error_msg}\n{error_trace}",
                task_id=task_id
            )

            # 更新测试用例状态为失败（INT-40：独立 Session，理由同上）
            local_db_session = create_db_session()
            try:
                tc_rel = local_db_session.get(TaskCase, tc_rel_id)
                if tc_rel:
                    self._finalize_dispatch_failure(tc_rel)
                    # 如果started_at字段为空，设置它
                    if not tc_rel.started_at:
                        tc_rel.started_at = datetime.now(self.utc_plus_8)
                    tc_rel.completed_at = datetime.now(self.utc_plus_8)
                    # 计算测试用例执行时长，确保时区一致
                    started_at = tc_rel.started_at
                    if started_at.tzinfo is None:
                        started_at = started_at.replace(tzinfo=self.utc_plus_8)
                    tc_rel.duration = int((tc_rel.completed_at - started_at).total_seconds())
                    tc_rel.error_message = error_msg
                    local_db_session.commit()

                    # 更新任务统计信息
                    task = local_db_session.get(Task, task_id)
                    if task:
                        task.completed_cases = local_db_session.query(TaskCase).filter(
                            TaskCase.task_id == task_id,
                            TaskCase.status == TaskCaseStatus.COMPLETED
                        ).count()
                        task.failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status=TaskCaseStatus.FAILED).count()
                        local_db_session.commit()
                        self._emit_progress(task)
            finally:
                local_db_session.close()
            return False

    def _execute_e2e_case(self, task_id, tc_rel_id):
        """执行端到端测试用例

        通过 gRPC 调用 e2e_test_service 的 ExecutionService.StartE2ETask，
        E2E 业务逻辑已下沉到 e2e_test_service 进程。

        Args:
            task_id: 任务ID
            tc_rel_id: 任务用例关联ID

        Returns:
            执行结果（成功返回True，失败返回False）
        """
        return _execute_e2e_case_via_grpc(task_id, tc_rel_id)
