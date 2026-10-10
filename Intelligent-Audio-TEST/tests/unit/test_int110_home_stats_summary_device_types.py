# -*- coding: utf-8 -*-
"""INT-110 网关 /home/stats/summary 兼容 task.type 废弃（device_types 口径）单测

INT-79（db8db540）废弃 Task.type 存储语义后，task_service 读模型 list_tasks
items 不再携带 type（口径改为用例级被测设备类型集合 device_types）。网关
RecentTaskItem.type 必填 + home_service 传 task['type']（恒 None）导致库内存在
新语义任务时 GET /home/stats/summary 恒 400。

本测试以 TestClient 装配真实 home 路由 + 桩 ACL 锁定该路径（此前仅有 tests/api
在线栈用例覆盖，canonical 全量回归对该路径是盲区）：
1. list_tasks 仅返回 device_types（无 type 键）时 summary 返回 200，
   recent_tasks 携带 device_types 且无 type 残留；
2. 既有调用方负载（name/status/algorithm_type/total_cases/...）不回归；
3. device_status 聚合不回归。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_gateway.application.services.home_service as home_service_module
from api_gateway.routes.home_bp import router as home_router


def _task_item(**overrides):
    """模拟 INT-79 后 task_service list_tasks 读模型 item（无 type 键）。"""
    item = {
        'id': 1,
        'name': '新语义任务',
        'status': 'completed',
        'device_types': ['phone', 'speaker'],
        'algorithm_type': None,
        'total_cases': 3,
        'completed_cases': 2,
        'created_at': '2026-10-10T00:00:00',
    }
    item.update(overrides)
    return item


class _StubTaskAcl:
    """替代 TaskConfigAclRepositoryImpl：list_tasks 返回无 type 的读模型口径。"""

    @staticmethod
    def list_tasks(**kwargs):
        return {
            'success': True,
            'message': '',
            'data': {'items': [_task_item()], 'total': 1, 'page': 1, 'per_page': 5},
        }


class _StubDeviceAcl:

    @staticmethod
    def get_all(**kwargs):
        return {
            'success': True,
            'message': '',
            'data': {'items': [{'status': 'online'}, {'status': 'offline'}, {'status': 'online'}]},
        }


class _StubTaskDataService:
    """替代 grpc_proxies.task_data_service：空分组聚合（top_groups 路径不在此测）。"""

    @staticmethod
    def list_testcase_groups():
        return {'items': []}

    @staticmethod
    def get_testcase_stats(group_by=None):
        return {'items': []}


def _make_client(monkeypatch) -> TestClient:
    monkeypatch.setattr(home_service_module, '_task_acl', _StubTaskAcl())
    monkeypatch.setattr(home_service_module, '_device_acl', _StubDeviceAcl())
    monkeypatch.setattr(home_service_module, 'task_data_service', _StubTaskDataService())

    app = FastAPI()
    app.include_router(home_router, prefix='/api/v1/home')

    @app.middleware('http')
    async def _grant_admin_permissions(request, call_next):
        # 与生产 AuthMiddleware AUTH_MODE=off 注入口径一致：admin 通配放行
        request.state.permissions = ['*']
        return await call_next(request)

    return TestClient(app)


class TestHomeStatsSummaryDeviceTypes:

    def test_summary_200_with_device_types(self, monkeypatch):
        """新语义任务（仅 device_types）时 summary 200，recent_tasks 携带 device_types。"""
        client = _make_client(monkeypatch)
        resp = client.get('/api/v1/home/stats/summary')
        assert resp.status_code == 200
        body = resp.json()
        assert body.get('success') is True, body
        recent = (body.get('data') or {}).get('recent_tasks') or []
        assert len(recent) == 1
        assert recent[0]['device_types'] == ['phone', 'speaker']

    def test_summary_no_type_residual(self, monkeypatch):
        """recent_tasks 输出不得残留 type 字段。"""
        client = _make_client(monkeypatch)
        resp = client.get('/api/v1/home/stats/summary')
        body = resp.json()
        recent = (body.get('data') or {}).get('recent_tasks') or []
        assert recent and all('type' not in item for item in recent)

    def test_summary_existing_fields_not_regressed(self, monkeypatch):
        """既有输出字段（name/status/algorithm_type/计数/created_at）不回归。"""
        client = _make_client(monkeypatch)
        resp = client.get('/api/v1/home/stats/summary')
        body = resp.json()
        item = ((body.get('data') or {}).get('recent_tasks') or [])[0]
        assert item['id'] == 1
        assert item['name'] == '新语义任务'
        assert item['status'] == 'completed'
        assert item['total_cases'] == 3
        assert item['completed_cases'] == 2
        assert item['created_at'] == '2026-10-10T00:00:00'

    def test_summary_device_status_aggregation(self, monkeypatch):
        """device_status 在线/离线聚合不回归。"""
        client = _make_client(monkeypatch)
        resp = client.get('/api/v1/home/stats/summary')
        body = resp.json()
        status = (body.get('data') or {}).get('device_status') or {}
        assert status.get('online') == 2
        assert status.get('offline') == 1
