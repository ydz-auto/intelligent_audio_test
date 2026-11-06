# -*- coding: utf-8 -*-
"""INT-1423 回归：报告对比 GenerateCompareReport 显式超时。

INT-1406 第一部分修复丢失后补交付：compare() 的 gRPC 调用显式传
Config.GRPC_REPORT_COMPARE_TIMEOUT_SECONDS（默认 600s），替代客户端默认
deadline 60s —— 跨任务大结果集同步聚合实测 >60s → DEADLINE_EXCEEDED → 网关 400。

覆盖：
- 默认配置值 = 600s
- compare() 调用 GenerateCompareReport 时显式传 timeout=配置值（记录型桩断言）
- 配置被覆盖时透传新值（证明取配置、非硬编码）
- 参数缺失 taskIds 仍走 400（不回归）
"""
import json
import os
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402

import api_gateway.application.services.report.report_command_sevice as report_cmd_mod  # noqa: E402
from api_gateway.config.config import Config  # noqa: E402
from api_gateway.infrastructure.request_adapter import set_current_request  # noqa: E402


class _CompareStub:
    """report_config_service 桩：记录 GenerateCompareReport 的 timeout。"""

    def __init__(self):
        self.timeouts = []
        self.requests = []

    @property
    def stub(self):
        return self

    def GenerateCompareReport(self, req, timeout=None):
        self.timeouts.append(timeout)
        self.requests.append(json.loads(req.data) if hasattr(req, 'data') else req)
        return SimpleNamespace(
            success=True, message='ok',
            data=json.dumps({'report_id': 42, 'status': 'generating'},
                            ensure_ascii=False))


def _fake_request(json_body=None):
    state = SimpleNamespace(_json_body=json_body or {})
    return SimpleNamespace(state=state, query_params={})


class TestConfigDefault:
    def test_default_timeout_is_600(self):
        assert Config.GRPC_REPORT_COMPARE_TIMEOUT_SECONDS == 600, \
            'INT-1406 默认应为 600s，实际 %s' % Config.GRPC_REPORT_COMPARE_TIMEOUT_SECONDS


class TestCompareExplicitTimeout:
    def test_compare_passes_configured_timeout(self, monkeypatch):
        stub = _CompareStub()
        monkeypatch.setattr(report_cmd_mod, 'report_config_service', stub)
        set_current_request(_fake_request(
            json_body={'task_ids': [1, 2], 'name': '对比', 'description': ''}))
        try:
            payload, http_code = report_cmd_mod.ReportCommandService.compare()
        finally:
            set_current_request(None)

        assert http_code == 200
        assert stub.timeouts == [Config.GRPC_REPORT_COMPARE_TIMEOUT_SECONDS], \
            'GenerateCompareReport 应显式传配置超时，实际 %s' % stub.timeouts
        assert stub.requests[0]['task_ids'] == [1, 2]

    def test_compare_honors_config_override(self, monkeypatch):
        monkeypatch.setattr(Config, 'GRPC_REPORT_COMPARE_TIMEOUT_SECONDS', 1200)
        stub = _CompareStub()
        monkeypatch.setattr(report_cmd_mod, 'report_config_service', stub)
        set_current_request(_fake_request(
            json_body={'task_ids': [1, 2], 'name': '对比', 'description': ''}))
        try:
            payload, http_code = report_cmd_mod.ReportCommandService.compare()
        finally:
            set_current_request(None)

        assert http_code == 200
        assert stub.timeouts == [1200], \
            '配置覆盖后应透传新值，实际 %s' % stub.timeouts

    def test_compare_missing_task_ids_returns_400(self, monkeypatch):
        stub = _CompareStub()
        monkeypatch.setattr(report_cmd_mod, 'report_config_service', stub)
        set_current_request(_fake_request(json_body={'name': '对比'}))
        try:
            payload, http_code = report_cmd_mod.ReportCommandService.compare()
        finally:
            set_current_request(None)

        assert http_code == 400
        assert stub.timeouts == [], '参数校验失败不得触达 gRPC 调用'
