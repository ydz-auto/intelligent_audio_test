# -*- coding: utf-8 -*-
"""INT-201 专项：任务合并成功响应携带新任务名 + 全链路 snake_case 契约。

根因：task_crud_service.merge 响应缺 merged_task_name，网关 merge 手写
camelCase 键（mergedTaskId/mergedTaskName），前端读 snake_case 键恒落空 →
成功提示恒为兜底「合并任务」。

覆盖：
- task_crud_service.merge：响应 data 携带 merged_task_name（自动生成 /
  显式传入均回传），repository 收到同名
- 网关 TaskLifecycleService.merge：data 键为 snake_case（merged_task_id /
  merged_task_name），与「后端统一返回 snake_case」序列化基线一致
仓储/ACL 以 fake 替身注入（不依赖 DB/跨服务）。
"""
import importlib
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

# 包 __init__ 将 task_crud_service 名绑定为单例实例，遮蔽同名子模块；
# importlib 直取 sys.modules 中的真实模块用于打桩
crud_mod = importlib.import_module('task_service.application.task.task_crud_service')
from task_service.application.task.task_crud_service import TaskCrudService


# ---------- task_service 应用层 ----------

class FakeMergeRepo:
    """task_repository 替身：仅捕获 merge_tasks 调用。"""

    def __init__(self, merged_task_id=999, total_results=42):
        self.calls = []
        self._merged_task_id = merged_task_id
        self._total_results = total_results

    def merge_tasks(self, source_task_ids, merged_task_name, description, created_by, now):
        self.calls.append({
            'source_task_ids': list(source_task_ids),
            'merged_task_name': merged_task_name,
        })
        return self._merged_task_id, self._total_results


class TestTaskMergeResponseName:
    """task_crud_service.merge 响应契约。"""

    def test_auto_generated_name_returned(self, monkeypatch):
        fake_repo = FakeMergeRepo()
        monkeypatch.setattr(crud_mod, 'task_repository', fake_repo)
        svc = TaskCrudService()

        result = svc.merge({'task_ids': [1, 2]})

        assert result['success'] is True
        assert result['data']['merged_task_id'] == 999
        assert result['data']['merged_task_name'] == fake_repo.calls[0]['merged_task_name']
        assert result['data']['merged_task_name'].startswith('合并任务_')
        assert result['data']['total_results'] == 42

    def test_explicit_name_passed_through(self, monkeypatch):
        fake_repo = FakeMergeRepo()
        monkeypatch.setattr(crud_mod, 'task_repository', fake_repo)
        svc = TaskCrudService()

        result = svc.merge({'task_ids': [1, 2], 'merged_task_name': '我的合并任务'})

        assert result['data']['merged_task_name'] == '我的合并任务'
        assert fake_repo.calls[0]['merged_task_name'] == '我的合并任务'

    def test_merge_requires_two_tasks(self, monkeypatch):
        fake_repo = FakeMergeRepo()
        monkeypatch.setattr(crud_mod, 'task_repository', fake_repo)
        svc = TaskCrudService()

        result = svc.merge({'task_ids': [1]})

        assert result['success'] is False
        assert result['code'] == 400
        assert fake_repo.calls == []


# ---------- 网关响应契约 ----------

class FakeMergeAcl:
    """网关 TaskConfigAclRepositoryImpl.merge 替身（模拟 task_service 返回）。"""

    def merge(self, data):
        return {
            'success': True,
            'message': '成功合并 2 个任务',
            'data': {
                'merged_task_id': 999,
                'merged_task_name': '合并任务_20261013',
                'source_task_ids': [1, 2],
                'total_results': 42,
            },
            'code': 201,
        }


class TestGatewayMergeSnakeContract:

    def test_response_data_keys_snake_case(self, monkeypatch):
        from types import SimpleNamespace

        from api_gateway.application.services.task import task_lifecycle_service as gw_mod
        from api_gateway.infrastructure import request_adapter

        monkeypatch.setattr(gw_mod, '_task_acl', FakeMergeAcl())

        request_adapter.set_current_request(
            SimpleNamespace(state=SimpleNamespace(_json_body={'task_ids': [1, 2]})))
        try:
            payload, http_code = gw_mod.TaskLifecycleService.merge()
        finally:
            request_adapter.set_current_request(None)

        assert http_code == 201
        data = payload['data']
        assert 'mergedTaskId' not in data
        assert 'mergedTaskName' not in data
        assert data['merged_task_id'] == 999
        assert data['merged_task_name'] == '合并任务_20261013'
