# -*- coding: utf-8 -*-
"""TaskDetailReadModelMixin - 任务详情读模型 Mixin。

从 task_read_model.py 按职责拆分，承担：
- 任务详情 DTO 组装（含关联用例/分组/标签）
- 设备/API 列表的 gRPC 批量查询（P3 改造，替代 task.devices / task.apis 关系）

由 TaskReadModel 组合复用，不单独实例化。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from shared.models.database import get_db_session
from shared.utils.status_utils import task_case_not_removed
from task_service.infrastructure.persistence.models import Task, TaskCase


class TaskDetailReadModelMixin:
    """任务详情读模型 Mixin：详情 DTO 组装 + 设备/API 列表查询。"""

    @staticmethod
    def extract_case_evaluation_dimensions(config) -> list:
        """从用例 config 提取评估维度去重列表（INT-302/F3）。

        覆盖整体口径（config.dimensions）与逐轮口径（config.rounds[n].
        evaluation.dimensions），维度条目形如 {id, name, weight, threshold}；
        只保留 id/name（重评估维度勾选的展示与过滤所需），按首次出现去重。

        Returns:
            list[dict]: [{'id': int, 'name': str}]，无维度配置返回空列表
        """
        if not isinstance(config, dict):
            return []
        seen: dict = {}

        def _collect(entries):
            for d in entries or []:
                if isinstance(d, dict) and d.get('id') is not None:
                    dim_id = d['id']
                    if dim_id not in seen:
                        seen[dim_id] = {'id': dim_id, 'name': d.get('name') or str(dim_id)}

        _collect(config.get('dimensions'))
        for rnd in (config.get('rounds') or []):
            if isinstance(rnd, dict):
                ev = rnd.get('evaluation')
                if isinstance(ev, dict):
                    _collect(ev.get('dimensions'))
        return list(seen.values())

    def find_by_id_with_relations(self, task_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 查询单个任务，含关联用例/设备/API/标签详情。

        INT-423：私有任务对非 owner 视为不存在（返回 None → 网关 404）。
        """
        from shared.infrastructure.visibility_filter import VisibilityDenied, check_visible
        from task_service.infrastructure.visibility_context import visibility_identity
        from task_service.infrastructure.read_models.task_dual_status_expr import (
            EXECUTION_STATUS_EXPR, EVALUATION_STATUS_EXPR,
        )
        session = get_db_session()
        try:
            row = session.query(Task, EXECUTION_STATUS_EXPR, EVALUATION_STATUS_EXPR).filter(
                Task.id == task_id, Task.deleted == False  # noqa: E712
            ).first()
            if row is None:
                return None
            task, execution_status, evaluation_status = row
            uid, is_admin = visibility_identity()
            try:
                check_visible(task.created_by_user_id, task.visibility, uid, is_admin)
            except VisibilityDenied:
                return None
            dto = self._to_detail_dto(task, session)
            # INT-301：SQL 派生的任务级执行/评估双状态（与列表同口径）
            dto['execution_status'] = execution_status
            dto['evaluation_status'] = evaluation_status
            return dto
        finally:
            session.close()

    @staticmethod
    def _fetch_device_list(device_ids):
        """通过 gRPC 批量获取设备列表（含 id/name/status），替代 task.devices 关系。

        P3 改造：Device 是 e2e_test_service 自有 PO，通过
        DeviceConfigService.GetDeviceStatuses 批量查询。
        注：GetDeviceStatuses 不返回 model 字段，列表视图可接受缺失。
        失败时返回空列表（仅日志告警）。
        """
        if not device_ids:
            return []

        from task_service.infrastructure.acl.device_acl_repository import device_acl_repository

        items = device_acl_repository.get_device_statuses(device_ids)
        return [
            {
                'id': item.get('id'),
                'name': item.get('name'),
                'status': item.get('status'),
                'model': None,  # GetDeviceStatuses 不返回 model
            }
            for item in items
        ]

    @staticmethod
    def _fetch_api_list(api_ids):
        """通过 gRPC 批量获取 API 列表（含 id/name/status），替代 task.apis 关系。

        P3 改造：API 是 api_test_service 自有 PO，通过
        APITestService.GetAPIConfig 逐个查询（无批量按 ids 查询接口）。
        失败时返回空列表（仅日志告警）。
        """
        if not api_ids:
            return []

        from task_service.infrastructure.acl.report_acl_repository import api_test_acl_repository

        return api_test_acl_repository.fetch_api_list(api_ids)

    def _to_detail_dto(self, task: Task, session) -> Dict[str, Any]:
        """含关联的详情 DTO。"""
        from task_service.infrastructure.persistence.models import TestCase, TaskDevice, TaskAPI, TestResult
        from task_service.infrastructure.persistence.models.testcase_models import TestCaseGroup
        from task_service.infrastructure.persistence.review_repository import review_repository

        # INT-340：人工复核标注（任务级复核计数 + 用例级是否含复核结果，覆盖提醒/标记展示用）
        reviewed_ids = review_repository.reviewed_result_ids(task.id, session)
        review_count = len(reviewed_ids)
        case_reviewed: Dict[str, bool] = {}
        if reviewed_ids:
            for (_rid, cid) in session.query(TestResult.id, TestResult.test_case_id).filter(
                    TestResult.task_id == task.id,
                    TestResult.id.in_(list(reviewed_ids)),
            ).all():
                case_reviewed[cid] = True

        cases = []
        # INT-305：移除留痕行（error_message = '用例已被移除'）从详情剔除
        task_cases = session.query(TaskCase).filter(
            TaskCase.task_id == task.id,
            task_case_not_removed(TaskCase),
        ).all()
        # 预取分组名映射，避免逐条查询
        group_ids = {tc.test_case_id for tc in task_cases}
        case_infos = {c.id: c for c in session.query(TestCase).filter(TestCase.id.in_(list(group_ids))).all()} if group_ids else {}
        group_name_map = {}
        for ci in case_infos.values():
            if ci.group_id and ci.group_id not in group_name_map:
                g = session.get(TestCaseGroup, ci.group_id)
                group_name_map[ci.group_id] = g.name if g else None
        for tc in task_cases:
            case_info = case_infos.get(tc.test_case_id)
            cases.append({
                'case_id': tc.test_case_id,
                'name': case_info.name if case_info else "未知用例",
                'status': tc.status,
                'execution_status': tc.execution_status,
                'evaluation_status': tc.evaluation_status,
                'started_at': tc.started_at.isoformat() if tc.started_at else None,
                'completed_at': tc.completed_at.isoformat() if tc.completed_at else None,
                'duration': tc.duration,
                'error_message': tc.error_message,
                'group_name': group_name_map.get(case_info.group_id) if case_info else None,
                'tags': [t.name for t in case_info.tags] if case_info and case_info.tags else [],
                # INT-302/F3：本任务用例聚合的评估维度（重评估维度勾选候选集）
                'evaluation_dimensions': self.extract_case_evaluation_dimensions(
                    case_info.config if case_info else None),
                # INT-340：该用例下是否存在人工复核结果（任务详情「人工复核」标记）
                'reviewed': bool(case_reviewed.get(tc.test_case_id)),
            })

        # P3 改造：task.devices / task.apis 关系已移除，
        # 通过 TaskDevice/TaskAPI 关联表 + gRPC 查询设备/API 信息
        task_device_ids = [td.device_id for td in
                           session.query(TaskDevice).filter_by(task_id=task.id).all()]
        task_api_ids = [ta.api_id for ta in
                        session.query(TaskAPI).filter_by(task_id=task.id).all()]
        devices = self._fetch_device_list(task_device_ids)
        apis = self._fetch_api_list(task_api_ids)
        tag_names = [tag.name for tag in task.tags]

        # 用例级被测设备类型集合（差异#2 收尾：取代 task.type 输出）
        device_types = [dt for (dt,) in session.query(TaskCase.device_type)
                        .filter(TaskCase.task_id == task.id, TaskCase.device_type.isnot(None))
                        .distinct().all()]

        # 实验室扩展（INT-540）：任务关联实验室 [{id, code, name}]（多实验室 N:M）
        labs = self._fetch_labs_map(session, [task.id]).get(task.id, [])

        return {
            'id': task.id,
            'name': task.name,
            'description': task.description,
            'status': task.status,
            'device_types': device_types,
            'config': task.config or {},
            'algorithm_type': task.algorithm_type,
            'algorithm_params': task.algorithm_params,
            'started_at': task.started_at.isoformat() if task.started_at else None,
            'completed_at': task.completed_at.isoformat() if task.completed_at else None,
            'total_cases': task.total_cases,
            'case_count': task.total_cases,
            'device_count': len(devices),
            'completed_cases': task.completed_cases,
            'failed_cases': task.failed_cases,
            'review_count': review_count,
            'tags': tag_names,
            'cases': cases,
            'devices': devices,
            'apis': apis,
            'labs': labs,
            'created_at': task.created_at.isoformat() if task.created_at else None,
            'updated_at': task.updated_at.isoformat() if task.updated_at else None,
        }
