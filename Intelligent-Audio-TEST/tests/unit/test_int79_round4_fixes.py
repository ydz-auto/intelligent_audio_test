# -*- coding: utf-8 -*-
"""INT-79 四轮验收回归：三轮打回修复（commit 1a45aeac）行为验证。

覆盖第四轮验收聚焦点：
- 缺陷6  report 合并容器任务「用例平均值统计」按 TaskMergeRelation 展开源任务集合
         （原 task.get('type')=='merged' 死读，读模型 DTO 已无 type 键）
- 缺陷7  api_test_service API 用例 config 无 `api` 段时顶层参数兜底恢复
         （device_type 口径）+ 失败文案标签与兜底同源
- 自查1  _progress gRPC 进度路径 device_types 含 API 类被测设备才收集 api_resources
         （原 task_type != 'api' 门禁恒真 → 运行中任务 API 资源状态恒空）
- 自查2  对比报告 report_task_type 由配置形态派生；tasks_info 不再输出恒 None type 键
- 顺手项 CreateTask 占位端点不再回显 type 键
"""
import json
import os
import tempfile
from types import SimpleNamespace

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int79_r4_') + '/r4.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')


# ==================== 缺陷6：合并任务平均值统计展开 ====================

class TestMergedAveragesExpansion:
    """_query_cases_for_averages：合并容器任务由 TaskMergeRelation 存在性判定。"""

    def _make_mixin(self, monkeypatch, merge_relations):
        from report_service.application.handlers._report_stats_query_mixin import (
            ReportStatsQueryMixin,
        )
        import report_service.infrastructure.clients.grpc_clients as grpc_clients

        monkeypatch.setattr(
            grpc_clients, '_grpc_get_tasks_by_ids',
            lambda ids: [{'id': ids[0], 'name': 't', 'device_types': ['physical']}])

        monkeypatch.setattr(
            grpc_clients, '_grpc_get_task_merge_relations',
            lambda task_id: merge_relations)

        captured = {}

        def _fake_query(task_id_filter, result_task_filter, *a, **k):
            captured['task_id_filter'] = task_id_filter
            captured['result_task_filter'] = result_task_filter
            return ['c-1'], []

        m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)
        monkeypatch.setattr(m, '_query_test_cases_and_results', _fake_query)
        return m, captured

    def test_merged_container_expands_source_task_ids(self, monkeypatch):
        m, captured = self._make_mixin(
            monkeypatch,
            [{'source_task_id': 7}, {'source_task_id': 8}])
        m._query_cases_for_averages(5, None, None, None, True)
        assert captured['task_id_filter'] == [7, 8]
        assert captured['result_task_filter'] == [7, 8]

    def test_plain_task_keeps_own_id(self, monkeypatch):
        m, captured = self._make_mixin(monkeypatch, [])
        m._query_cases_for_averages(5, None, None, None, True)
        assert captured['task_id_filter'] == 5
        assert captured['result_task_filter'] == 5

    def test_merge_query_failure_falls_back_to_container(self, monkeypatch):
        from report_service.application.handlers._report_stats_query_mixin import (
            ReportStatsQueryMixin,
        )
        import report_service.infrastructure.clients.grpc_clients as grpc_clients

        monkeypatch.setattr(
            grpc_clients, '_grpc_get_tasks_by_ids',
            lambda ids: [{'id': 5, 'name': 't', 'device_types': []}])

        def _boom(task_id):
            raise RuntimeError('grpc down')

        monkeypatch.setattr(grpc_clients, '_grpc_get_task_merge_relations', _boom)

        captured = {}

        def _fake_query(task_id_filter, result_task_filter, *a, **k):
            captured['task_id_filter'] = task_id_filter
            return [], []

        m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)
        monkeypatch.setattr(m, '_query_test_cases_and_results', _fake_query)
        m._query_cases_for_averages(5, None, None, None, True)
        assert captured['task_id_filter'] == 5


# ==================== 缺陷7：API 兜底恢复与文案标签同源 ====================

class _FakeTaskDataAcl:
    def __init__(self, tc_row):
        self._tc_row = tc_row

    def get_task_case_by_ids(self, task_id, case_ids=None):
        return [SimpleNamespace(result_data=dict(self._tc_row))]

    def update_task_case_status(self, **k):
        return True

    def get_task_by_id(self, task_id):
        # 读模型 DTO 已无 type 键（差异#2 收尾）——形状对齐真实数据
        return SimpleNamespace(result_data={'id': task_id, 'name': 'task'})


class TestApiCaseConfigFallback:
    """config 无 `api` 段时顶层 vendor/case_config 等恢复被拾取（device_type 口径）。"""

    def _run(self, monkeypatch, case_config, device_type):
        from api_test_service.core import api_executor as executor_mod

        tc_row = {'id': 401, 'test_case_id': 'c-1', 'task_id': 31,
                  'execution_status': 'queued', 'device_type': 'http_api',
                  'device_id': '5'}

        monkeypatch.setattr(executor_mod, '_task_data_acl', _FakeTaskDataAcl(tc_row))

        class _FakeTestcaseAcl:
            def get_test_case_detail(self, case_id):
                return SimpleNamespace(result_data={
                    'id': 'c-1', 'name': 'case', 'config': case_config})

        monkeypatch.setattr(executor_mod, '_testcase_acl', _FakeTestcaseAcl())
        monkeypatch.setattr(executor_mod, 'dto_to_dict',
                            lambda d: getattr(d, 'result_data', d))

        executor = executor_mod.APIExecutor.__new__(executor_mod.APIExecutor)
        executor._thread_ctx = SimpleNamespace(current_test_case_id=None)
        monkeypatch.setattr(executor, '_log', lambda *a, **k: None)
        monkeypatch.setattr(executor, '_handle_control', lambda task_id: None)

        class _FakeApiConfig:
            id = 1
            api_url = 'http://api'
            api_endpoints = []
            default_max_process = 1
            meta = {}
            max_timeout = 30
            vendor = None

        monkeypatch.setattr(executor, '_get_api_configs',
                            lambda task_id: [_FakeApiConfig()])
        monkeypatch.setattr(executor, '_get_audio_data',
                            lambda *a, **k: (b'', 0, ''))

        ok, data = executor._validate_and_get_data(
            31, 401, device_type=device_type, device_id='5')
        return ok, data

    def test_http_api_case_without_api_section_falls_back_to_full_config(self, monkeypatch):
        config = {'vendor': 'x', 'case_config': {'k': 'v'}, 'rounds': []}
        ok, data = self._run(monkeypatch, config, 'http_api')
        assert ok is True
        assert data['api_specific_config'] == config

    def test_websocket_api_case_without_api_section_falls_back_to_full_config(self, monkeypatch):
        config = {'vendor': 'x', 'translation_direction': 'zh->en', 'rounds': []}
        ok, data = self._run(monkeypatch, config, 'websocket_api')
        assert ok is True
        assert data['api_specific_config'] == config

    def test_api_section_wins_when_present(self, monkeypatch):
        api_section = {'api_url': 'http://x'}
        config = {'api': api_section, 'vendor': 'top', 'rounds': []}
        ok, data = self._run(monkeypatch, config, 'http_api')
        assert ok is True
        assert data['api_specific_config'] == api_section

    def test_physical_case_does_not_fallback(self, monkeypatch):
        config = {'vendor': 'x', 'rounds': []}
        ok, data = self._run(monkeypatch, config, 'physical')
        assert ok is True
        assert data['api_specific_config'] == {}


class TestAudioFailureLabel:
    """_get_audio_data 失败文案标签由同一 case_device_type 派生（兜底与文案同源）。"""

    def _run(self, monkeypatch, device_type):
        from api_test_service.core import api_executor as executor_mod

        class _FakeTestcaseAcl:
            def get_test_case_detail(self, case_id):
                return SimpleNamespace(result_data={
                    'id': 'c-1', 'name': 'case',
                    'config': {'rounds': [{'audios': []}]}})

        monkeypatch.setattr(executor_mod, '_testcase_acl', _FakeTestcaseAcl())
        monkeypatch.setattr(executor_mod, 'dto_to_dict',
                            lambda d: getattr(d, 'result_data', d))

        executor = executor_mod.APIExecutor.__new__(executor_mod.APIExecutor)
        monkeypatch.setattr(executor, '_log', lambda *a, **k: None)
        monkeypatch.setattr(executor, '_fail_tc_rel', lambda *a, **k: None)

        audio, duration, error = executor._get_audio_data(
            'c-1', device_type, 'case', 31, 401)
        return error

    def test_http_api_case_labelled_api(self, monkeypatch):
        assert 'API' in self._run(monkeypatch, 'http_api')

    def test_websocket_api_case_labelled_api(self, monkeypatch):
        assert 'API' in self._run(monkeypatch, 'websocket_api')

    def test_physical_case_labelled_e2e(self, monkeypatch):
        assert 'E2E' in self._run(monkeypatch, 'physical')


# ==================== 自查1：进度事件 api_resources 门禁 ====================

class TestProgressApiResourcesGate:
    """_build_api_resources_from_grpc：device_types 含 API 类被测设备才收集。"""

    def _make_mixin(self, monkeypatch, concurrent=3):
        from shared.utils.event_manager import _progress as progress_mod
        from shared.utils.event_manager._progress import ProgressMixin

        monkeypatch.setattr(progress_mod, '_current_concurrent_from_load_balancer',
                            lambda engine: concurrent)
        m = ProgressMixin.__new__(ProgressMixin)
        m.execution_engine = SimpleNamespace()
        return m

    def test_http_api_task_collects_resources(self, monkeypatch):
        m = self._make_mixin(monkeypatch)
        raw = [{'id': 'a1', 'name': 'api-1', 'pending_cases': 2,
                'avg_response_time': 120, 'default_max_process': 8}]
        out = m._build_api_resources_from_grpc(['http_api'], raw)
        assert len(out) == 1
        assert out[0].id == 'a1'
        assert out[0].queue_length == 2
        assert out[0].current_concurrent == 3

    def test_websocket_api_task_collects_resources(self, monkeypatch):
        m = self._make_mixin(monkeypatch)
        out = m._build_api_resources_from_grpc(
            ['websocket_api'], [{'id': 'a2', 'name': 'api-2'}])
        assert len(out) == 1

    def test_physical_task_returns_empty(self, monkeypatch):
        m = self._make_mixin(monkeypatch)
        out = m._build_api_resources_from_grpc(
            ['physical'], [{'id': 'a1', 'name': 'api-1'}])
        assert out == []

    def test_empty_device_types_returns_empty(self, monkeypatch):
        m = self._make_mixin(monkeypatch)
        assert m._build_api_resources_from_grpc([], [{'id': 'a1'}]) == []
        assert m._build_api_resources_from_grpc(None, [{'id': 'a1'}]) == []

    def test_mixed_device_types_collect_resources(self, monkeypatch):
        m = self._make_mixin(monkeypatch)
        out = m._build_api_resources_from_grpc(
            ['physical', 'http_api'], [{'id': 'a1', 'name': 'api-1'}])
        assert len(out) == 1


# ==================== 自查2：对比报告口径派生与占位键清理 ====================

class TestCompareSummaryDerivation:
    """report_task_type 由配置形态派生；tasks_info 不再含恒 None type 键。"""

    def test_get_task_type_by_config_shape(self):
        from report_service.application.services.report_compare_helpers import (
            ReportCompareHelpers,
        )

        api_task = {'id': 1, 'config': {'api': {}}}
        e2e_task = {'id': 2, 'config': {'audios': [{'audio_id': 'a',
                                                    'playback_device_id': 'd1'}]}}
        assert ReportCompareHelpers._get_task_type([api_task]) == 'api'
        assert ReportCompareHelpers._get_task_type([e2e_task]) == 'e2e'
        assert ReportCompareHelpers._get_task_type([api_task, e2e_task]) == 'all'

    def test_tasks_info_has_no_type_key(self):
        from report_service.application.services.report_compare_generator_data_mixin import (
            ReportCompareDataMixin,
        )

        tasks = [{'id': 1, 'name': 't1', 'status': 'completed'}]
        data_dict = {
            'report_task_type': 'api',
            'total_cases': 10,
            'completed_cases': 8,
            'failed_cases': 1,
            'success_rate': 80.0,
            'task_weighted_values': {1: 90.0},
            'case_categories_list': [],
            'case_tags_list': [],
            'device_list': [],
            'api_list': [],
            'resources': [],
            'resource_headers': [],
            'all_metrics': [],
            'metric_data': {},
            'tag_metric_data': {},
            'raw_data': [],
            'device_stats': {},
            'api_stats': {},
            'case_type_stats': {},
            'source_cases': [],
        }
        summary = ReportCompareDataMixin._build_compare_summary(
            tasks, [1], [], data_dict)
        assert summary['task_type'] == 'api'
        for info in summary['tasks_info']:
            assert 'type' not in info
            assert info['weighted_value'] == 90.0


# ==================== 顺手项：CreateTask 占位端点不再回显 type ====================

class TestCreateTaskPlaceholder:
    def test_result_has_no_type_echo(self):
        from shared.proto import task_service_pb2 as task_pb
        from task_service.interfaces.grpc.execution import ExecutionServiceServicer

        resp = ExecutionServiceServicer().CreateTask(
            task_pb.CreateTaskRequest(task_id='5'))
        assert resp.success is True
        payload = json.loads(resp.data)
        assert payload == {'task_id': '5', 'created': True}


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
