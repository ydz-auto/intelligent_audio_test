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
from task_service.infrastructure.persistence.models import Task, TaskCase


class TaskDetailReadModelMixin:
    """任务详情读模型 Mixin：详情 DTO 组装 + 设备/API 列表查询。"""

    def find_by_id_with_relations(self, task_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 查询单个任务，含关联用例/设备/API/标签详情。"""
        session = get_db_session()
        try:
            task = session.query(Task).filter(
                Task.id == task_id, Task.deleted == False  # noqa: E712
            ).first()
            if task is None:
                return None
            return self._to_detail_dto(task, session)
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
        from task_service.infrastructure.persistence.models import TestCase, TaskDevice, TaskAPI
        from task_service.infrastructure.persistence.models.testcase_models import TestCaseGroup

        cases = []
        task_cases = session.query(TaskCase).filter_by(task_id=task.id).all()
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

        return {
            'id': task.id,
            'name': task.name,
            'description': task.description,
            'status': task.status,
            'type': task.type,
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
            'tags': tag_names,
            'cases': cases,
            'devices': devices,
            'apis': apis,
            'created_at': task.created_at.isoformat() if task.created_at else None,
            'updated_at': task.updated_at.isoformat() if task.updated_at else None,
        }
