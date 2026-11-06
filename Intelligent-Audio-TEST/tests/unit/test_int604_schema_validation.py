# -*- coding: utf-8 -*-
"""INT-604/INT-1115 网关 schema 校验：TaskCreateRequest 的逐目标 target_modes。

覆盖验收标准 1（单测）：
- target_modes 顶层可选：target_type ∈ {device, api}（TargetType）、
  mode ∈ {parallel, serial}（ExecutionMode）、target_id 命中 device_ids/api_ids；
- target_modes 出现时必须恰好覆盖全部选中目标一次（不漏/不多/不重复）→ 422 报错；
- 缺省/空数组 = 全目标并行（零回归）；
- 旧全局字段 execution_mode/serial_first（含 camelCase）一律拒绝并指明改用 target_modes；
- POST /api/v1/tasks 端到端：旧字段 / target_modes 违规 → 422；合法载荷透传 ACL。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from pydantic import ValidationError


def _make(**kwargs):
    from api_gateway.schemas.task import TaskCreateRequest
    base = {'name': 'INT-1115 schema 校验任务'}
    base.update(kwargs)
    return TaskCreateRequest(**base)


def _tm(target_type, target_id, mode='parallel'):
    return {'target_type': target_type, 'target_id': target_id, 'mode': mode}


class TestTargetModesValidation:
    def test_default_is_all_parallel(self):
        """不传 target_modes：缺省全目标并行（现行为，零回归）。"""
        req = _make(device_ids=[1], api_ids=[2])
        assert req.target_modes is None

    def test_empty_list_is_all_parallel(self):
        req = _make(device_ids=[1], target_modes=[])
        assert req.target_modes == []

    def test_valid_target_modes_accepted(self):
        """设备+API 混排合法：恰好覆盖全部选中目标一次，保序可读。"""
        req = _make(device_ids=[1, 2], api_ids=[10], target_modes=[
            _tm('device', 1, 'serial'),
            _tm('device', 2, 'parallel'),
            _tm('api', 10, 'serial'),
        ])
        assert [(i.target_type, i.target_id, i.mode) for i in req.target_modes] == [
            ('device', 1, 'serial'),
            ('device', 2, 'parallel'),
            ('api', 10, 'serial'),
        ]

    def test_invalid_target_type_rejected(self):
        with pytest.raises(ValidationError):
            _make(device_ids=[1], target_modes=[_tm('unknown', 1)])

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValidationError):
            _make(device_ids=[1], target_modes=[_tm('device', 1, 'mixed')])

    def test_missing_target_rejected(self):
        """未命中 device_ids/api_ids 的目标（多余）→ 422 校验错误。"""
        with pytest.raises(ValidationError):
            _make(device_ids=[1], target_modes=[_tm('device', 2)])

    def test_coverage_missing_selected_target_rejected(self):
        """选中目标未被 target_modes 覆盖（缺失）→ 422。"""
        with pytest.raises(ValidationError):
            _make(device_ids=[1, 2], target_modes=[_tm('device', 1)])

    def test_coverage_duplicate_rejected(self):
        """同一目标重复出现 → 422。"""
        with pytest.raises(ValidationError):
            _make(device_ids=[1], target_modes=[
                _tm('device', 1), _tm('device', 1, 'serial')])

    def test_cross_type_mismatch_rejected(self):
        """target_type=api 的 target_id 未命中 api_ids → 422。"""
        with pytest.raises(ValidationError):
            _make(device_ids=[1], target_modes=[
                _tm('device', 1), _tm('api', 10)])

    def test_camel_case_target_modes_accepted(self):
        """camelCase 请求体（targetType/targetId）与 snake_case 同口径。"""
        req = _make(deviceIds=[1], apiIds=[10], targetModes=[
            {'targetType': 'device', 'targetId': 1, 'mode': 'serial'},
            {'targetType': 'api', 'targetId': 10, 'mode': 'parallel'},
        ])
        assert [(i.target_type, i.target_id, i.mode) for i in req.target_modes] == [
            ('device', 1, 'serial'),
            ('api', 10, 'parallel'),
        ]


class TestDeprecatedExecutionFieldsRejected:
    """旧全局字段 execution_mode/serial_first 一律拒绝并指明改用 target_modes。"""

    def test_execution_mode_rejected(self):
        with pytest.raises(ValidationError) as exc:
            _make(execution_mode='serial')
        assert 'target_modes' in str(exc.value)

    def test_serial_first_rejected(self):
        with pytest.raises(ValidationError) as exc:
            _make(serial_first='device')
        assert 'target_modes' in str(exc.value)

    def test_camel_case_variants_rejected(self):
        """camelCase 旧字段（executionMode/serialFirst）同口径拒绝。"""
        with pytest.raises(ValidationError) as exc:
            _make(executionMode='serial', serialFirst='api')
        assert 'target_modes' in str(exc.value)


class TestTaskCreateRouteTargetModes:
    """POST /api/v1/tasks 端到端：旧字段/target_modes 违规 → 422；合法载荷透传 ACL。

    app/TestClient 模块级共用（任务路由链首次导入较重），避免每测试重建。
    """

    @classmethod
    def _build_client(cls):
        if not hasattr(cls, '_client'):
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from api_gateway.middleware import RequestAdapterMiddleware
            from api_gateway.routes.task_bp import router as task_router
            from api_gateway.utils.error_handlers import register_error_handlers

            app = FastAPI()
            app.add_middleware(RequestAdapterMiddleware)

            @app.middleware('http')
            async def _fake_auth(request, call_next):
                request.state.permissions = ['*']
                return await call_next(request)

            register_error_handlers(app)
            app.include_router(task_router, prefix='/api/v1/tasks', tags=['tasks'])
            cls._client = TestClient(app)
        return cls._client

    def test_old_field_execution_mode_returns_422(self):
        client = self._build_client()
        resp = client.post('/api/v1/tasks', json={
            'name': '接线测试_旧字段', 'execution_mode': 'serial'})
        assert resp.status_code == 422
        assert 'target_modes' in resp.json()['message']

    def test_old_field_camel_case_returns_422(self):
        client = self._build_client()
        resp = client.post('/api/v1/tasks', json={
            'name': '接线测试_旧字段camel', 'serialFirst': 'device'})
        assert resp.status_code == 422
        assert 'target_modes' in resp.json()['message']

    def test_coverage_missing_returns_422(self):
        client = self._build_client()
        resp = client.post('/api/v1/tasks', json={
            'name': '接线测试_缺覆盖', 'device_ids': [1, 2],
            'target_modes': [{'target_type': 'device', 'target_id': 1, 'mode': 'serial'}]})
        assert resp.status_code == 422
        assert 'target_modes' in resp.json()['message']

    def test_valid_target_modes_passed_to_acl(self, monkeypatch):
        from api_gateway.application.services.task import task_command_service

        captured = {}

        class _FakeAcl:
            def create(self, data):
                captured['data'] = data
                return {'success': True, 'data': {'id': 123}}

        monkeypatch.setattr(task_command_service, '_task_acl', _FakeAcl())
        client = self._build_client()
        resp = client.post('/api/v1/tasks', json={
            'name': '接线测试_合法target_modes', 'device_ids': [1], 'api_ids': [10],
            'target_modes': [
                {'target_type': 'device', 'target_id': 1, 'mode': 'serial'},
                {'target_type': 'api', 'target_id': 10, 'mode': 'parallel'},
            ]})
        assert resp.status_code == 201, resp.text
        assert captured['data']['target_modes'] == [
            {'target_type': 'device', 'target_id': 1, 'mode': 'serial'},
            {'target_type': 'api', 'target_id': 10, 'mode': 'parallel'},
        ]
