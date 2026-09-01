# -*- coding: utf-8 -*-
"""TaskCaseResultsMixin - 任务用例结果读模型 Mixin。

从 task_read_model.py 按职责拆分，承担：
- 用例列表分页查询（list_cases）
- 网关使用的完整用例详情（get_case_detail）与用例结果（get_case_results）
- gRPC 批量查询辅助：维度评估结果 / 设备名称 / API 名称

由 TaskReadModel 组合复用，不单独实例化。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from shared.models.database import get_db_session
from shared.utils.json_utils import deserialize_algorithm_result  # noqa: F401
from task_service.infrastructure.persistence.models import Task, TaskCase
from shared.models.common_enums import TestType


class TaskCaseResultsMixin:
    """任务用例结果读模型 Mixin：用例列表/详情/结果查询。"""

    def list_cases(self, task_id: int, status: Optional[str] = None,
                   page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """分页查询任务下用例列表。"""
        session = get_db_session()
        try:
            q = session.query(TaskCase).filter(TaskCase.task_id == task_id)
            if status:
                q = q.filter(TaskCase.status == status)
            total = q.count()
            offset = (page - 1) * page_size
            items = (q.order_by(TaskCase.id)
                     .offset(offset)
                     .limit(page_size)
                     .all())

            return {
                'items': [self._case_to_dto(tc) for tc in items],
                'total': total,
                'page': page,
                'page_size': page_size,
            }
        finally:
            session.close()

    def get_case_detail(self, task_id: int, case_id: str) -> Optional[Dict[str, Any]]:
        """网关 get_case_detail 使用的完整用例详情查询。

        P1.7 改造：TestResultDimension / Dimension 是 evaluation_service 自有 PO，
        改为通过 gRPC 调 evaluation_service.EvaluationDataService.GetDimensionResultsByResultIds。
        """
        from task_service.infrastructure.persistence.models import TestCase, TestResult
        from shared.utils.result_data_store import load_full_result_data

        session = get_db_session()
        try:
            tc = session.query(TaskCase).filter_by(
                task_id=task_id, test_case_id=case_id
            ).first()
            if tc is None:
                return None

            case_info = session.get(TestCase, case_id)
            task = session.get(Task, task_id)
            test_type = task.type if task else TestType.API.value

            results = session.query(TestResult).filter_by(
                task_id=task_id, test_case_id=case_id
            ).all()

            # P1.7: 一次性通过 gRPC 获取所有 result 的维度评估结果
            result_ids = [r.id for r in results]
            dim_map = self._fetch_dim_results_grouped(result_ids)

            # P3 改造：收集 device_id / api_id，通过 gRPC 批量查询名称，替代直连 PO
            device_name_map = self._fetch_device_names({r.device_id for r in results if r.device_id})
            api_name_map = self._fetch_api_names({r.api_id for r in results if r.api_id})

            processed_results = []
            for result in results:
                device_name = device_name_map.get(result.device_id) if result.device_id else None
                api_name = api_name_map.get(result.api_id) if result.api_id else None

                dim_data = dim_map.get(result.id, [])

                full_result_data = load_full_result_data(
                    result.result_data, getattr(result, 'result_data_path', None)
                )
                # 兼容历史双重序列化数据：algorithm_result 可能是 str
                algo_result = result.algorithm_result
                algo_result = deserialize_algorithm_result(algo_result)
                processed_results.append({
                    "id": result.id,
                    "device_id": result.device_id,
                    "device_name": device_name,
                    "api_id": result.api_id,
                    "api_name": api_name,
                    "execution_status": result.execution_status,
                    "response_time": result.response_time,
                    "algorithm_result": algo_result,
                    "asr_result": algo_result.get('asr_result'),
                    "translation_result": algo_result.get('translation_result'),
                    "result_data": full_result_data,
                    "error_message": result.error_message,
                    "dimensions": dim_data,
                    "created_at": result.created_at.isoformat()
                })

            return {
                "task_id": task_id,
                "case_id": case_id,
                "case_info": {
                    "id": case_info.id,
                    "name": case_info.name if case_info else "未知用例",
                    "algorithm_type": case_info.algorithm_type if case_info else '',
                    "config": case_info.config if case_info else {},
                } if case_info else None,
                "test_type": test_type,
                "tc": self._case_to_dto(tc),
                "results": processed_results,
            }
        finally:
            session.close()

    def get_case_results(self, task_id: int, case_id: str) -> Optional[Dict[str, Any]]:
        """网关 get_case_results 使用的查询。

        P1.7 改造：TestResultDimension / Dimension 改为 gRPC 调 evaluation_service。
        """
        from task_service.infrastructure.persistence.models import TestCase, TestResult
        from shared.utils.result_data_store import load_full_result_data

        session = get_db_session()
        try:
            tc = session.query(TaskCase).filter_by(
                task_id=task_id, test_case_id=case_id
            ).first()
            if tc is None:
                return None

            case_info = session.get(TestCase, case_id)
            results = session.query(TestResult).filter_by(
                task_id=task_id, test_case_id=case_id
            ).all()

            # P1.7: 一次性通过 gRPC 获取所有 result 的维度评估结果
            result_ids = [r.id for r in results]
            dim_map = self._fetch_dim_results_grouped(result_ids)

            # P3 改造：收集 device_id / api_id，通过 gRPC 批量查询名称，替代直连 PO
            device_name_map = self._fetch_device_names({r.device_id for r in results if r.device_id})
            api_name_map = self._fetch_api_names({r.api_id for r in results if r.api_id})

            processed_results = []
            for result in results:
                device_name = device_name_map.get(result.device_id) if result.device_id else None
                api_name = api_name_map.get(result.api_id) if result.api_id else None

                dim_data = dim_map.get(result.id, [])

                # 兼容历史双重序列化数据：algorithm_result 可能是 str
                algo_result = result.algorithm_result
                algo_result = deserialize_algorithm_result(algo_result)
                processed_results.append({
                    "id": result.id,
                    "device_id": result.device_id,
                    "device_name": device_name,
                    "api_id": result.api_id,
                    "api_name": api_name,
                    "execution_status": result.execution_status,
                    "response_time": result.response_time,
                    "algorithm_result": algo_result,
                    "asr_result": algo_result.get('asr_result'),
                    "translation_result": algo_result.get('translation_result'),
                    "result_data": load_full_result_data(result.result_data, getattr(result, 'result_data_path', None)),
                    "error_message": result.error_message,
                    "dimensions": dim_data,
                    "created_at": result.created_at.isoformat()
                })

            return {
                "task_id": task_id,
                "case_id": case_id,
                "case_name": case_info.name if case_info else "未知用例",
                "results": processed_results,
            }
        finally:
            session.close()

    # ---- gRPC 批量查询辅助 ----

    @staticmethod
    def _fetch_device_names(device_ids):
        """通过 gRPC 批量获取设备名称，返回 {device_id: name} 映射。

        P3 改造：Device 是 e2e_test_service 自有 PO，通过
        DeviceConfigService.GetDeviceStatuses 批量查询，替代直连 DB。
        失败时返回空 dict（仅日志告警）。
        """
        if not device_ids:
            return {}

        from task_service.infrastructure.acl.device_acl_repository import device_acl_repository

        items = device_acl_repository.get_device_statuses(device_ids)
        return {item.get('id'): item.get('name') for item in items if item.get('id') is not None}

    @staticmethod
    def _fetch_api_names(api_ids):
        """通过 gRPC 批量获取 API 名称，返回 {api_id: name} 映射。

        P3 改造：API 是 api_test_service 自有 PO，通过
        APITestService.GetAPIConfig 逐个查询（无批量按 ids 查询接口），
        替代直连 DB。失败时返回空 dict（仅日志告警）。
        """
        if not api_ids:
            return {}

        from task_service.infrastructure.acl.report_acl_repository import api_test_acl_repository

        return api_test_acl_repository.fetch_api_names(api_ids)

    @staticmethod
    def _fetch_dim_results_grouped(result_ids):
        """通过 gRPC 批量获取维度评估结果，按 test_result_id 分组返回。

        P1.7: TestResultDimension / Dimension 是 evaluation_service 自有 PO，
        通过 evaluation_service.EvaluationDataService.GetDimensionResultsByResultIds 获取。
        失败时返回空 dict（不影响主流程，仅日志告警）。
        """
        if not result_ids:
            return {}

        from task_service.infrastructure.acl.evaluation_config_acl_repository import evaluation_config_acl_repository

        return evaluation_config_acl_repository.get_dimension_results_by_result_ids(result_ids)

    @staticmethod
    def _case_to_dto(tc: TaskCase) -> Dict[str, Any]:
        return {
            'id': tc.id,
            'task_id': tc.task_id,
            'test_case_id': tc.test_case_id,
            'status': tc.status,
            'execution_status': tc.execution_status,
            'evaluation_status': tc.evaluation_status,
            'started_at': tc.started_at.isoformat() if tc.started_at else None,
            'completed_at': tc.completed_at.isoformat() if tc.completed_at else None,
            'duration': tc.duration,
            'error_message': tc.error_message,
        }
