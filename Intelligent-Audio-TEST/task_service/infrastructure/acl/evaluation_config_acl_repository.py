# -*- coding: utf-8 -*-
"""evaluation_service 防腐层仓储 — gRPC ACL 适配层。

封装 task_service 对 evaluation_service 的跨域 gRPC 调用，
消除 infrastructure/persistence / read_models 层对
shared.clients.grpc_clients 的直接依赖。

相关 stub：
- shared.clients.grpc_clients.get_evaluation_config_service_stub
- shared.clients.grpc_clients.get_evaluation_data_service_stub

proto：shared/proto/evaluation_service_pb2
"""
import json
import logging
from typing import List

from shared.utils.grpc_json import loads as _loads

_logger = logging.getLogger(__name__)


class EvaluationConfigAclRepository:
    """evaluation_service 防腐层仓储（gRPC ACL 适配层）。"""

    def list_dimensions_by_ids(self, dim_ids) -> list:
        """按 ID 列表批量查询评价维度基础信息。

        封装 evaluation_service.EvaluationConfigService.GetDimensionByIds RPC。
        返回 [{'id', 'name', 'type', 'description'}, ...]；失败返回空列表。
        """
        if not dim_ids:
            return []
        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        try:
            stub = get_evaluation_config_service_stub()
            resp = stub.GetDimensionByIds(eval_pb.GetDimensionByIdsRequest(
                dim_ids=json.dumps(list(dim_ids)),
            ))
            if not resp.success:
                _logger.warning("GetDimensionByIds gRPC 失败: %s", resp.message)
                return []
            payload = json.loads(resp.data) if resp.data else {}
        except Exception as e:
            _logger.warning("GetDimensionByIds gRPC 异常: %s", e)
            return []

        if not isinstance(payload, dict):
            return []
        return payload.get('items', [])

    def list_dimensions(self, page: int = 1, per_page: int = 1) -> dict:
        """查询维度列表（分页）。

        封装 evaluation_service.EvaluationConfigService.ListDimensions RPC，
        返回 {'total': N, 'items': [...]}；失败返回空 dict。
        """
        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        try:
            stub = get_evaluation_config_service_stub()
            resp = stub.ListDimensions(eval_pb.ListDimensionsRequest(
                page=page, per_page=per_page,
            ))
            if not resp.success:
                return {}
            return _loads(resp.data, {}) or {}
        except Exception as e:
            _logger.warning("ListDimensions gRPC 异常: %s", e)
            return {}

    def get_evaluation_config_stub(self):
        """获取 EvaluationConfigService gRPC stub。

        封装 shared.clients.grpc_clients.get_evaluation_config_service_stub，
        供需要直接调用 stub 的场景使用。
        """
        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        return get_evaluation_config_service_stub()

    def get_evaluated_result_ids(self, result_ids, session=None) -> set:
        """按结果 ID 集合批量取「已评估」结果 ID 集合。

        INT-1625：候选行 `evaluated` 标记与 `evaluation_status` 筛选原经 gRPC
        `GetDimensionResultsByResultIds` 取回全部维度行（真实库候选首页 200 个
        结果 ID 对应 5592 行、宿主实测 5~22s，其中多数行只为判「有无」），候选页
        只需「是否存在维度行」的布尔集合。改共享库窄字段只读投影（口径同 RPC 的
        仓储查询：`test_result_dimensions` 有无该 `test_result_id` 的行，不过滤
        软删；先例见 `_read_projection`）。

        失败返回空集合（仅日志告警，等价原「按未评估降级」）。
        """
        ids = [int(r) for r in (result_ids or []) if r is not None]
        if not ids:
            return set()
        from shared.models.database import get_db_session
        from task_service.infrastructure.acl._read_projection import fetch_rows
        session = session or get_db_session()
        rows = fetch_rows(
            session,
            'SELECT DISTINCT test_result_id FROM test_result_dimensions '
            'WHERE test_result_id IN :ids',
            ids,
        )
        return {int(r[0]) for r in rows if r[0] is not None}

    def get_dimension_results_by_result_ids(self, result_ids) -> dict:
        """批量获取维度评估结果，按 test_result_id 分组返回。

        封装 evaluation_service.EvaluationDataService.GetDimensionResultsByResultIds RPC。
        失败时返回空 dict。
        """
        if not result_ids:
            return {}
        from shared.clients.grpc_clients import get_evaluation_data_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        try:
            stub = get_evaluation_data_service_stub()
            resp = stub.GetDimensionResultsByResultIds(
                eval_pb.GetDimensionResultsByResultIdsRequest(
                    result_ids=json.dumps(list(result_ids)),
                ))
            if not resp.success:
                _logger.warning(
                    "GetDimensionResultsByResultIds gRPC 失败: %s", resp.message)
                return {}
            payload = json.loads(resp.data) if resp.data else {}
        except Exception as e:
            _logger.warning(
                "GetDimensionResultsByResultIds gRPC 异常: %s", e)
            return {}

        items = payload.get('items', []) if isinstance(payload, dict) else []
        grouped = {}
        for item in items:
            rid = item.get('test_result_id')
            if rid is None:
                continue
            grouped.setdefault(rid, []).append({
                "id": item.get('id'),
                "dimension_id": item.get('dimension_id'),
                "name": item.get('dimension_name'),
                "value": item.get('dimension_value'),
                "score": item.get('score'),
                "status": item.get('status'),
                "evaluation_status": item.get('evaluation_status'),
                "error_message": item.get('error_message'),
                "round_number": item.get('round_number'),
            })
        return grouped

    def get_evaluation_data_stub(self):
        """获取 EvaluationDataService gRPC stub。

        封装 shared.clients.grpc_clients.get_evaluation_data_service_stub，
        供需要直接调用 stub 的场景使用。
        """
        from shared.clients.grpc_clients import get_evaluation_data_service_stub
        return get_evaluation_data_service_stub()

    # INT-823 将新增 evaluation_service EvaluationDataService.AiReviewCheck RPC
    # （LLM 复检：聚合 ASR/参考文本/维度分/LLM 评语 → verdict/confidence/reasoning）。
    # 本卡（#2）异步执行骨架经此调用；方法未落地时优雅失败（发起记录置 failed）。
    AI_REVIEW_RECHECK_RPC = 'AiReviewCheck'
    AI_REVIEW_RECHECK_REQUEST = 'AiReviewCheckRequest'

    def run_ai_review_check(self, result_id, dimension_id=None,
                            task_id=None, test_case_id=None) -> dict:
        """调用 evaluation_service LLM 复检 gRPC（INT-823 契约，本卡先留骨架）。

        Returns:
            {'success': bool, 'message': str, 'data': {'verdict','confidence','reasoning'}|None}
        """
        from shared.clients.grpc_clients import get_evaluation_data_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        try:
            stub = get_evaluation_data_service_stub()
            method = getattr(stub, self.AI_REVIEW_RECHECK_RPC, None)
            req_cls = getattr(eval_pb, self.AI_REVIEW_RECHECK_REQUEST, None)
            if method is None or req_cls is None:
                return {'success': False,
                        'message': f'evaluation_service LLM 复检 gRPC 未就绪'
                                   f'（{self.AI_REVIEW_RECHECK_RPC} 待 INT-823）',
                        'data': None}
            resp = method(req_cls(
                result_id=int(result_id),
                dimension_id=int(dimension_id) if dimension_id is not None else 0,
                task_id=int(task_id) if task_id is not None else 0,
                test_case_id=test_case_id or '',
            ))
            data = json.loads(resp.data) if resp.data else {}
            return {'success': resp.success, 'message': resp.message,
                    'data': data if isinstance(data, dict) else None}
        except Exception as e:
            _logger.warning("run_ai_review_check gRPC 异常: %s", e)
            return {'success': False, 'message': str(e), 'data': None}

    def list_llm_judge_dimension_ids(self) -> list:
        """查询全部 LLM 判分维度 ID（task_type_code/dimension_type 含 'llm_judge'）。

        经 evaluation_service.ListDimensions 拉全量过滤（维度量级小，单页够）；
        失败返回空列表。INT-822 发起缺省维度口径：结果现有已完成评估的 LLM 判分维度。
        """
        try:
            payload = self.list_dimensions(page=1, per_page=1000)
            items = payload.get('items', []) if isinstance(payload, dict) else []
        except Exception as e:
            _logger.warning("查询 LLM 判分维度失败: %s", e)
            return []
        out = []
        for d in items:
            if not isinstance(d, dict):
                continue
            ttc = d.get('task_type_code') or ''
            dt = d.get('dimension_type') or ''
            if 'llm_judge' in ttc or dt == 'llm_judge':
                if d.get('id') is not None:
                    out.append(int(d['id']))
        return out

    def set_dimension_review_status(self, result_ids, evaluation_status, status) -> dict:
        """人工复核改判 TRD 评估状态（INT-340）。

        封装 evaluation_service.EvaluationDataService.SetDimensionReviewStatusByResultIds RPC。
        Returns:
            {'success': bool, 'message': str, 'data': dict|None}
        """
        if not result_ids:
            return {'success': True, 'message': 'no-op', 'data': {'updated': 0}}
        from shared.clients.grpc_clients import get_evaluation_data_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        try:
            stub = get_evaluation_data_service_stub()
            resp = stub.SetDimensionReviewStatusByResultIds(
                eval_pb.SetDimensionReviewStatusByResultIdsRequest(
                    result_ids=json.dumps(list(result_ids)),
                    evaluation_status=evaluation_status or '',
                    status=status or '',
                ))
            return {'success': resp.success, 'message': resp.message,
                    'data': json.loads(resp.data) if resp.data else {}}
        except Exception as e:
            _logger.warning("SetDimensionReviewStatusByResultIds gRPC 异常: %s", e)
            return {'success': False, 'message': str(e), 'data': None}


# 模块级单例
evaluation_config_acl_repository = EvaluationConfigAclRepository()
