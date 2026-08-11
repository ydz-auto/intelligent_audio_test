"""api_gateway 基础设施层 —— 读模型

CQRS 读模型：优化复杂查询，避免走 ORM 关系加载。

对于简单 CRUD 查询直接用 application/queries/handlers.py 中的 ORM 查询。
对于复杂列表、统计、聚合查询，使用 read_models 直接 SQL 查询优化。

改造说明（P4）：
- 删除对 task_service / evaluation_service / e2e_test_service / api_test_service /
  report_service PO 的直连 import，改为 gRPC 调用对应服务的 config/data 服务。
- ORM 属性访问改为 dict 访问（gRPC 返回 JSON 反序列化后的字典）。
- gRPC 调用采用延迟 import + try/except 容错。

TODO(DB穿透): 本文件仍通过 get_db_session() 执行原生 SQL 查询（跨服务聚合读）。
应通过各后端服务（task_service / report_service 等）的 gRPC 聚合统计 RPC 获取，
待对应 RPC 就绪后迁移。当前保留代码，DB 调用失败时回退为空结果。
"""
from sqlalchemy import text
from shared.models.database import get_db_session
from shared.models.common_enums import TaskStatus
from typing import Optional, Dict, Any, List
from shared.utils.grpc_json import loads as _loads


class TestCaseReadModel:
    """测试用例读模型 —— 优化列表查询"""

    @staticmethod
    def list_with_stats(page: int = 1, page_size: int = 20,
                        group_id: Optional[str] = None,
                        keyword: Optional[str] = None) -> dict:
        """列表 + 统计信息

        改造后：通过 gRPC 调用 task_service.TestCaseConfigService.ListTestCases
        获取用例列表，统计字段（result_count/task_count）原通过 SQL 子查询
        获取，gRPC 无对应接口，暂置为 0 并加 TODO。
        """
        try:
            from shared.clients.grpc_clients import get_testcase_config_service_stub
            from shared.proto import task_service_pb2 as task_pb

            stub = get_testcase_config_service_stub()
            req = task_pb.ListTestCasesRequest(
                page=page,
                per_page=page_size,
                keyword=keyword or '',
                group_id=group_id or '',
                include_deleted=False,
            )
            resp = stub.ListTestCases(req)
            if not resp.success:
                return {'total': 0, 'page': page, 'page_size': page_size, 'items': []}
            payload = _loads(resp.data, {}) or {}
            total = payload.get('total', 0) or len(payload.get('items', []) or [])
            items = []
            for it in payload.get('items', []) or []:
                items.append({
                    'id': it.get('id'),
                    'name': it.get('name', ''),
                    'description': it.get('description', '') or '',
                    'algorithm_type': it.get('algorithm_type'),
                    'group': it.get('group'),
                    # TODO(P4): result_count/task_count 原 SQL 子查询统计，
                    # gRPC 无对应接口，暂置 0
                    'result_count': 0,
                    'task_count': 0,
                    'created_at': it.get('created_at'),
                })

            return {'total': total, 'page': page, 'page_size': page_size, 'items': items}
        except Exception:
            return {'total': 0, 'page': page, 'page_size': page_size, 'items': []}


class TaskReadModel:
    """任务读模型 —— 优化任务列表 + 进度查询"""

    @staticmethod
    def list_with_progress(page: int = 1, page_size: int = 20,
                           status: Optional[str] = None,
                           task_type: Optional[str] = None) -> dict:
        """任务列表 + 进度

        改造后：通过 gRPC 调用 task_service.TaskConfigService.ListTasks
        获取任务列表，进度由 total_cases/completed_cases 计算。
        """
        try:
            from shared.clients.grpc_clients import get_task_config_service_stub
            from shared.proto import task_service_pb2 as task_pb

            stub = get_task_config_service_stub()
            req = task_pb.ListTasksRequest(
                page=page,
                per_page=page_size,
                status=status or '',
                type=task_type or '',
            )
            resp = stub.ListTasks(req)
            if not resp.success:
                return {'total': 0, 'page': page, 'page_size': page_size, 'items': []}
            payload = _loads(resp.data, {}) or {}
            total = payload.get('total', 0) or len(payload.get('items', []) or [])
            items = []
            for t in payload.get('items', []) or []:
                total_cases = t.get('total_cases') or 0
                completed_cases = t.get('completed_cases') or 0
                failed_cases = t.get('failed_cases') or 0
                progress = 0
                if total_cases and total_cases > 0:
                    progress = round(completed_cases / total_cases * 100, 2)
                items.append({
                    'id': t.get('id'),
                    'name': t.get('name', ''),
                    'status': t.get('status'),
                    'type': t.get('type'),
                    'total_cases': total_cases,
                    'completed_cases': completed_cases,
                    'failed_cases': failed_cases,
                    'progress': progress,
                    'created_at': t.get('created_at'),
                })

            return {'total': total, 'page': page, 'page_size': page_size, 'items': items}
        except Exception:
            return {'total': 0, 'page': page, 'page_size': page_size, 'items': []}


class ReportReadModel:
    """报告读模型 —— 优化报告列表 + 详情"""

    @staticmethod
    def list_with_task_info(page: int = 1, page_size: int = 20,
                            task_id: Optional[str] = None) -> dict:
        """报告列表 + 关联任务信息

        改造后：通过 gRPC 调用 report_service.ReportConfigService.ListReports
        获取报告列表，task_name 通过 gRPC 调用 task_service.TaskDataService.GetTaskById 获取。
        """
        try:
            from shared.clients.grpc_clients import get_report_config_service_stub
            from shared.proto import report_service_pb2 as report_pb

            stub = get_report_config_service_stub()
            req = report_pb.ListReportsRequest(
                page=page,
                per_page=page_size,
                task_id=int(task_id) if task_id else 0,
            )
            resp = stub.ListReports(req)
            if not resp.success:
                return {'total': 0, 'page': page, 'page_size': page_size, 'items': []}
            payload = _loads(resp.data, {}) or {}
        except Exception:
            return {'total': 0, 'page': page, 'page_size': page_size, 'items': []}

        items = []
        for r in payload.get('items', []) or []:
            task_name = None
            r_task_id = r.get('task_id')
            if r_task_id:
                try:
                    from shared.clients.grpc_clients import get_task_data_service_stub
                    from shared.proto import task_service_pb2 as task_pb

                    stub = get_task_data_service_stub()
                    req = task_pb.GetTaskByIdRequest(task_id=int(r_task_id))
                    resp = stub.GetTaskById(req)
                    if resp.success:
                        task_data = _loads(resp.data, {}) or {}
                        task_name = task_data.get('name')
                except Exception:
                    task_name = None
            items.append({
                'id': r.get('id'),
                'task_id': r.get('task_id'),
                'task_name': task_name,
                'name': r.get('name'),
                'type': r.get('type'),
                'status': r.get('status'),
                'created_at': r.get('created_at'),
            })

        total = payload.get('total', len(items))
        return {'total': total, 'page': page, 'page_size': page_size, 'items': items}


class HomeStatsReadModel:
    """首页统计读模型 —— 聚合统计"""

    @staticmethod
    def _count_cases() -> int:
        """用例总数（未删除）"""
        try:
            from shared.clients.grpc_clients import get_testcase_config_service_stub
            from shared.proto import task_service_pb2 as task_pb

            stub = get_testcase_config_service_stub()
            # ListTestCases 不带参数取 total
            resp = stub.ListTestCases(task_pb.ListTestCasesRequest(
                page=1, per_page=1, include_deleted=False))
            if not resp.success:
                return 0
            payload = _loads(resp.data, {}) or {}
            return int(payload.get('total', 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _count_tasks() -> int:
        """任务总数（未删除）"""
        try:
            from shared.clients.grpc_clients import get_task_config_service_stub
            from shared.proto import task_service_pb2 as task_pb

            stub = get_task_config_service_stub()
            resp = stub.ListTasks(task_pb.ListTasksRequest(page=1, per_page=1))
            if not resp.success:
                return 0
            payload = _loads(resp.data, {}) or {}
            return int(payload.get('total', 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _count_audios() -> int:
        """音频总数"""
        try:
            from shared.clients.grpc_clients import get_audio_config_service_stub
            from shared.proto import audio_service_pb2 as e2e_pb

            stub = get_audio_config_service_stub()
            # ListAudios 接收 JSON 查询参数，per_page=1 取 total
            import json as _json
            req = e2e_pb.ListAudiosRequest(data=_json.dumps({
                'page': 1, 'per_page': 1,
            }, ensure_ascii=False, default=str))
            resp = stub.ListAudios(req)
            if not resp.success:
                return 0
            payload = _loads(resp.data, {}) or {}
            return int(payload.get('total', 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _count_devices() -> int:
        """设备总数（未删除）"""
        try:
            from shared.clients.grpc_clients import get_device_config_service_stub
            from shared.proto import device_service_pb2 as e2e_pb

            stub = get_device_config_service_stub()
            resp = stub.ListDevices(e2e_pb.ListDevicesRequest(
                page=1, per_page=1))
            if not resp.success:
                return 0
            payload = _loads(resp.data, {}) or {}
            return int(payload.get('total', 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _count_apis() -> int:
        """API 总数（未删除）"""
        try:
            from shared.clients.grpc_clients import get_api_test_service_stub
            from shared.proto import api_test_service_pb2 as api_pb

            stub = get_api_test_service_stub()
            resp = stub.ListAPIConfigs(api_pb.ListAPIConfigsRequest(
                page=1, per_page=1))
            if not resp.success:
                return 0
            payload = _loads(resp.data, {}) or {}
            return int(payload.get('total', 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _count_groups() -> int:
        """用例分组总数

        gRPC 无直接的 group count 接口，使用 ListTestCases（view=tag）兜底，
        无可靠来源时返回 0。
        """
        # TODO(P4): task_service 未提供 TestCaseGroup 计数 gRPC 接口
        return 0

    @staticmethod
    def _count_dimensions() -> int:
        """评估维度总数（启用 + 未删除）"""
        try:
            from shared.clients.grpc_clients import get_evaluation_config_service_stub
            from shared.proto import evaluation_service_pb2 as eval_pb

            stub = get_evaluation_config_service_stub()
            # ListDimensions 不带过滤，per_page=1 取 total
            resp = stub.ListDimensions(eval_pb.ListDimensionsRequest(
                page=1, per_page=1))
            if not resp.success:
                return 0
            payload = _loads(resp.data, {}) or {}
            return int(payload.get('total', 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _count_running_tasks() -> int:
        """运行中任务数（pending/running）"""
        try:
            from shared.clients.grpc_clients import get_task_config_service_stub
            from shared.proto import task_service_pb2 as task_pb

            stub = get_task_config_service_stub()
            # 逐状态查询累加（gRPC ListTasks 单次只支持单 status 过滤）
            running = 0
            for st in (TaskStatus.PENDING.value, TaskStatus.RUNNING.value):
                resp = stub.ListTasks(task_pb.ListTasksRequest(
                    page=1, per_page=1, status=st))
                if resp.success:
                    payload = _loads(resp.data, {}) or {}
                    running += int(payload.get('total', 0) or 0)
            return running
        except Exception:
            return 0

    @staticmethod
    def _count_completed_tasks() -> int:
        """已完成任务数"""
        try:
            from shared.clients.grpc_clients import get_task_config_service_stub
            from shared.proto import task_service_pb2 as task_pb

            stub = get_task_config_service_stub()
            resp = stub.ListTasks(task_pb.ListTasksRequest(
                page=1, per_page=1, status=TaskStatus.COMPLETED.value))
            if not resp.success:
                return 0
            payload = _loads(resp.data, {}) or {}
            return int(payload.get('total', 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _count_failed_tasks() -> int:
        """失败任务数"""
        try:
            from shared.clients.grpc_clients import get_task_config_service_stub
            from shared.proto import task_service_pb2 as task_pb

            stub = get_task_config_service_stub()
            resp = stub.ListTasks(task_pb.ListTasksRequest(
                page=1, per_page=1, status=TaskStatus.FAILED.value))
            if not resp.success:
                return 0
            payload = _loads(resp.data, {}) or {}
            return int(payload.get('total', 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _count_reports() -> int:
        """报告总数"""
        try:
            from shared.clients.grpc_clients import get_report_config_service_stub
            from shared.proto import report_service_pb2 as report_pb

            stub = get_report_config_service_stub()
            resp = stub.ListReports(report_pb.ListReportsRequest(
                page=1, per_page=1))
            if not resp.success:
                return 0
            payload = _loads(resp.data, {}) or {}
            return int(payload.get('total', 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def get_dashboard_stats() -> dict:
        """获取首页仪表盘统计"""
        case_count = HomeStatsReadModel._count_cases()
        task_count = HomeStatsReadModel._count_tasks()
        report_count = HomeStatsReadModel._count_reports()
        audio_count = HomeStatsReadModel._count_audios()
        device_count = HomeStatsReadModel._count_devices()
        api_count = HomeStatsReadModel._count_apis()
        group_count = HomeStatsReadModel._count_groups()
        dimension_count = HomeStatsReadModel._count_dimensions()

        running_tasks = HomeStatsReadModel._count_running_tasks()
        completed_tasks = HomeStatsReadModel._count_completed_tasks()
        failed_tasks = HomeStatsReadModel._count_failed_tasks()

        return {
            'cases': case_count,
            'tasks': task_count,
            'running_tasks': running_tasks,
            'completed_tasks': completed_tasks,
            'failed_tasks': failed_tasks,
            'reports': report_count,
            'audios': audio_count,
            'devices': device_count,
            'apis': api_count,
            'groups': group_count,
            'dimensions': dimension_count,
        }
