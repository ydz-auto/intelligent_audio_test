# -*- coding: utf-8 -*-
"""report_service / api_test_service 防腐层仓储 — gRPC ACL 适配层。

封装 task_service 对 report_service / api_test_service 的跨域 gRPC 调用，
消除 infrastructure/read_models 层对 shared.clients.grpc_clients 的直接依赖。

相关 stub：
- shared.clients.grpc_clients.get_report_config_service_stub
- shared.clients.grpc_clients.get_api_test_service_stub

proto：shared/proto/report_service_pb2 / api_test_service_pb2
"""
import logging
from typing import List

from shared.utils.grpc_json import loads as _loads

_logger = logging.getLogger(__name__)

# 列表页每个任务回填的报告摘要上限（沿用历史 ListReports per_page=100 口径）
REPORT_BRIEF_PER_TASK_LIMIT = 100


class ReportAclRepository:
    """report_service 防腐层仓储（gRPC ACL 适配层）。"""

    def list_reports(self, task_id=None, page: int = 1, per_page: int = 100) -> dict:
        """查询报告列表（可按 task_id 过滤）。

        封装 report_service.ReportConfigService.ListReports RPC，
        返回 {'total': N, 'items': [...]}；失败返回空 dict。
        """
        from shared.clients.grpc_clients import get_report_config_service_stub
        from shared.proto import report_service_pb2 as report_pb
        try:
            stub = get_report_config_service_stub()
            resp = stub.ListReports(report_pb.ListReportsRequest(
                page=page, per_page=per_page,
                task_id=int(task_id) if task_id else 0,
            ))
            if not resp.success:
                return {}
            return _loads(resp.data, {}) or {}
        except Exception as e:
            _logger.warning("ListReports gRPC 异常: %s", e)
            return {}

    def list_reports_by_task_ids(self, task_ids) -> dict:
        """页级批量查询整页任务的报告摘要（INT-1462）。

        封装 report_service.ReportConfigService.ListReportsByTaskIds RPC——
        列表页组装任务时一次往返取回整页报告，取代逐任务 ListReports 的 N+1。

        Returns:
            {task_id(int): [{id,name,status,type,created_at}, ...]}；失败返回空 dict。
        """
        if not task_ids:
            return {}
        from shared.clients.grpc_clients import get_report_config_service_stub
        from shared.proto import report_service_pb2 as report_pb
        try:
            stub = get_report_config_service_stub()
            resp = stub.ListReportsByTaskIds(report_pb.ListReportsByTaskIdsRequest(
                task_ids=[int(t) for t in task_ids],
                per_task_limit=REPORT_BRIEF_PER_TASK_LIMIT,
            ))
            if not resp.success:
                _logger.warning("ListReportsByTaskIds 返回失败: %s", resp.message)
                return {}
            payload = _loads(resp.data, {}) or {}
            raw = payload.get('items_by_task') or {}
            return {int(tid): rows for tid, rows in raw.items()}
        except Exception as e:
            _logger.warning("ListReportsByTaskIds gRPC 异常: %s", e)
            return {}

    def list_reports_count(self) -> int:
        """查询报告总数。失败返回 0。"""
        payload = self.list_reports(page=1, per_page=1)
        return int(payload.get('total', 0) or 0) if payload else 0

    def get_report_config_stub(self):
        """获取 ReportConfigService gRPC stub。

        封装 shared.clients.grpc_clients.get_report_config_service_stub，
        供需要直接调用 stub 的场景使用。
        """
        from shared.clients.grpc_clients import get_report_config_service_stub
        return get_report_config_service_stub()

    def get_report_cases_raw_payload(self, report_id: int) -> list:
        """按 report_id 取报告用例**原始九字段 payload**（INT-1996：发布冻结 M1 前置）。

        封装 report_service.ReportConfigService.GetReportCasesRawPayload RPC——
        不经响应装配层（build_case_item 的 null/[] 归一与 algorithmResults /
        referenceParams 展开），直接由 report_case_snapshots 解引用出口返回
        原始列值，供 freeze_report_snapshot 改造前后逐字节一致。

        Raises:
            RuntimeError: gRPC 失败 / 快照指针悬空 / sha 不符时显式抛错——
            禁止返回空 cases 静默产出缺内容的发布快照（对齐档4 §8.4 失败语义）。
        """
        from shared.clients.grpc_clients import get_report_config_service_stub
        from shared.proto import report_service_pb2 as report_pb
        try:
            stub = get_report_config_service_stub()
            resp = stub.GetReportCasesRawPayload(report_pb.GetReportCasesRequest(
                report_id=int(report_id),
                data='',
            ))
            if not resp.success:
                raise RuntimeError(
                    f'report_service 取报告用例原始 payload 失败 (report_id={report_id}): '
                    f'{resp.message}')
            payload = _loads(resp.data, {}) or {}
            return payload.get('cases') or []
        except RuntimeError:
            raise
        except Exception as e:
            _logger.warning("GetReportCasesRawPayload gRPC 异常 report_id=%s: %s", report_id, e)
            raise RuntimeError(
                f'report_service 取报告用例原始 payload 异常 (report_id={report_id}): {e}') from e

    def recalculate_task_report(self, task_id: int) -> bool:
        """触发任务报告重算（INT-305：终态任务删除用例后重建报告）。

        封装 report_service.ReportConfigService.GenerateTaskReport：
        - 报告不存在 → report_service 幂等成功（status=exists / no-op）；
        - 报告存在 → report_service 内部去重锁承载排队语义（生成中返回
          generating，不重复提交）。
        失败返回 False 由调用方降级（报告可手动重新生成，不阻塞删除主链）。
        """
        from shared.clients.grpc_clients import get_report_config_service_stub
        from shared.proto import report_service_pb2 as report_pb
        try:
            stub = get_report_config_service_stub()
            resp = stub.GenerateTaskReport(report_pb.GenerateTaskReportRequest(
                task_id=int(task_id),
                name='',
                description='',
            ))
            if not resp.success:
                _logger.warning("GenerateTaskReport 返回失败 task_id=%s: %s", task_id, resp.message)
                return False
            return True
        except Exception as e:
            _logger.warning("GenerateTaskReport gRPC 异常 task_id=%s: %s", task_id, e)
            return False


# 模块级单例
report_acl_repository = ReportAclRepository()


class ApiTestAclRepository:
    """api_test_service 防腐层仓储（gRPC ACL 适配层）。"""

    def list_apis_count(self) -> int:
        """查询 API 总数。失败返回 0。"""
        from shared.clients.grpc_clients import get_api_test_service_stub
        from shared.proto import api_test_service_pb2 as api_pb
        try:
            stub = get_api_test_service_stub()
            resp = stub.ListAPIConfigs(api_pb.ListAPIConfigsRequest(
                page=1, per_page=1,
            ))
            if not resp.success:
                return 0
            payload = _loads(resp.data, {}) or {}
            return int(payload.get('total', 0) or 0)
        except Exception as e:
            _logger.warning("ListAPIConfigs gRPC 异常: %s", e)
            return 0

    def get_api_config(self, api_id) -> dict:
        """按 ID 查询单个 API 配置，返回 dict 或 None。"""
        from shared.clients.grpc_clients import get_api_test_service_stub
        from shared.proto import api_test_service_pb2 as api_pb
        try:
            stub = get_api_test_service_stub()
            resp = stub.GetAPIConfig(api_pb.GetAPIConfigRequest(api_id=api_id))
            if resp.success and resp.data:
                return _loads(resp.data, {}) or {}
        except Exception as e:
            _logger.warning("GetAPIConfig gRPC 异常 (api_id=%s): %s", api_id, e)
        return None

    def fetch_api_list(self, api_ids: List) -> list:
        """批量获取 API 列表（含 id/name/status）。

        封装 api_test_service.APITestService.GetAPIConfig 逐个查询，
        失败时返回空列表。
        """
        if not api_ids:
            return []
        result = []
        for api_id in api_ids:
            api_data = self.get_api_config(api_id)
            if isinstance(api_data, dict):
                result.append({
                    'id': api_data.get('id'),
                    'name': api_data.get('name'),
                    'status': api_data.get('status'),
                })
        return result

    def fetch_api_summaries(self, api_ids: List, session=None) -> dict:
        """批量获取 API 摘要 {api_id: {id, name, status}}。

        INT-1500：api_test_service 没有按 ID 集合的批量查询接口，原实现逐个
        调 `GetAPIConfig`（`fetch_api_list` / `fetch_api_names`），一页任务或
        一页候选就是几十次下游调用（`/apis` 列表 400 时前端只能显示 ID 亦同源）。
        改共享库窄字段只读投影（口径同 `GetAPIConfig`：`apis.deleted = FALSE`；
        先例见 `_read_projection`）。

        失败返回空 dict（仅日志告警），调用方按「无 API」降级。
        """
        ids = [int(a) for a in (api_ids or []) if a is not None]
        if not ids:
            return {}
        from shared.models.database import get_db_session
        from task_service.infrastructure.acl._read_projection import fetch_rows
        session = session or get_db_session()
        rows = fetch_rows(
            session,
            'SELECT id, name, status FROM apis WHERE id IN :ids AND deleted = FALSE',
            ids,
        )
        return {int(r[0]): {'id': int(r[0]), 'name': r[1], 'status': r[2]} for r in rows}

    def fetch_api_names(self, api_ids: List) -> dict:
        """批量获取 API 名称，返回 {api_id: name} 映射。失败时返回空 dict。"""
        if not api_ids:
            return {}
        summaries = self.fetch_api_summaries(api_ids)
        return {api_id: summaries[int(api_id)]['name'] for api_id in api_ids
                if int(api_id) in summaries}

    def get_api_test_stub(self):
        """获取 APITestService gRPC stub。

        封装 shared.clients.grpc_clients.get_api_test_service_stub，
        供需要直接调用 stub 的场景使用。
        """
        from shared.clients.grpc_clients import get_api_test_service_stub
        return get_api_test_service_stub()

    # ==================== 用例执行分发（INT-71：执行域 P0 契约贯通） ====================

    @staticmethod
    def _resolve_stub(dispatch_target=None):
        """按会话亲和路由目标取 stub：指定实例直连，否则走默认负载均衡通道。"""
        if dispatch_target and dispatch_target.get('grpc_port'):
            from shared.clients.grpc_instance_client import (
                get_api_test_service_stub_for_instance,
            )
            return get_api_test_service_stub_for_instance(
                dispatch_target['host'], dispatch_target['grpc_port'])
        from shared.clients.grpc_clients import get_api_test_service_stub
        return get_api_test_service_stub()

    def create_api_test(self, task_id, case_ids, dispatch_target=None) -> dict:
        """分发 API 用例执行（CreateAPITest 通道，HTTP 非实时路径）。

        封装 api_test_service.APITestService.CreateAPITest，test_config
        携带精确 case_ids；执行失败抛 RuntimeError 由分发侧失败兜底收敛。
        """
        from shared.proto import api_test_service_pb2 as api_pb
        from shared.utils.grpc_json import dumps as _dumps
        try:
            stub = self._resolve_stub(dispatch_target)
            resp = stub.CreateAPITest(api_pb.CreateAPITestRequest(
                task_id=str(task_id),
                test_config=_dumps({'case_ids': [str(c) for c in case_ids]}),
            ))
            if not resp.success:
                raise RuntimeError(f"api_test_service 执行失败: {resp.message}")
            return _loads(getattr(resp, 'data', '') or '', {}) or {}
        except RuntimeError:
            raise
        except Exception as e:
            _logger.warning("CreateAPITest gRPC 异常 (task_id=%s): %s", task_id, e)
            raise

    def start_api_test(self, task_id, case_ids, device_type='', device_id='',
                       dispatch_target=None) -> dict:
        """分发 API 用例执行（StartAPITest 通道，执行域 P0 契约贯通）。

        封装 api_test_service.APITestService.StartAPITest：case_ids 精确
        用例分发，device_type/device_id 为调度侧路由决策随请求传递；
        websocket_api 会话亲和场景经 dispatch_target 直连绑定实例。
        执行失败抛 RuntimeError 由分发侧失败兜底收敛。
        """
        from shared.proto import api_test_service_pb2 as api_pb
        try:
            stub = self._resolve_stub(dispatch_target)
            resp = stub.StartAPITest(api_pb.StartAPITestRequest(
                task_id=str(task_id),
                device_type=device_type or '',
                device_id=str(device_id) if device_id else '',
                case_ids=[int(c) for c in case_ids],
            ))
            if not resp.success:
                raise RuntimeError(f"api_test_service 执行失败: {resp.message}")
            return _loads(getattr(resp, 'data', '') or '', {}) or {}
        except RuntimeError:
            raise
        except Exception as e:
            _logger.warning("StartAPITest gRPC 异常 (task_id=%s): %s", task_id, e)
            raise


# 模块级单例
api_test_acl_repository = ApiTestAclRepository()
