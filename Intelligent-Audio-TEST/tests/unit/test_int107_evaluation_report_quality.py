# -*- coding: utf-8 -*-
"""INT-107 守卫：评估/报告数据质量一组缺陷。

覆盖三组修复（均纯单测，不触真实 DB/gRPC/Redis）：

缺陷① 评估整例静默失败：
  任一维度失败 → 整例 evaluation_status=failed 时 task_case_relations.error_message
  为空串，失败原因只在维度行里。修复后 update_task_case_status_in_db /
  _mark_group_case_failed / _apply_final_status 聚合链全程携带失败原因摘要。

缺陷② 维度评分全外呼无兜底：
  维度评估端点不可达（连接级失败）时所有维度直接 failed，评估链无降级路径。
  修复后连接级失败（__error_kind__=connection）按配置 eval_fallback_urls /
  EVAL_FALLBACK_URLS 依次尝试兜底评估端点；业务级失败不切换（避免重复计分）。

缺陷③ 报告负数统计：
  task.completed_cases 口径为 status=completed 的用例数（与 failed_cases 不相交），
  报告侧曾再做 completed-failed 扣减 → 全失败任务出现 completed_cases=-1、
  pass_rate=-100。修复后三处聚合口径与 task_service 一致。

洪泛一条（task_service GetTaskStats / 执行引擎忙等）不在本服务域，
由 INT-79（in_review）与 INT-103（in_progress）承责，见 INT-107 提测评论。
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.common_enums import EvalErrorKind
from shared.utils.status_constants import EvaluationStatus
from evaluation_service.domain.services.evaluation_utils import (
    CASE_ERROR_MESSAGE_MAX_LEN,
    compose_case_error_message,
)


# ============================================================
# 缺陷①：用例级失败原因聚合
# ============================================================

class TestComposeCaseErrorMessage:
    def test_empty_reasons_returns_empty_string(self):
        assert compose_case_error_message([]) == ''
        assert compose_case_error_message([None, '', '  ']) == ''

    def test_joins_reasons(self):
        msg = compose_case_error_message(['端点A超时', '端点B 500'])
        assert msg == '维度评估失败: 端点A超时; 端点B 500'

    def test_dedups_identical_reasons(self):
        """同端点不可达时多维度同报 ConnectTimeout，摘要只保留一条。"""
        reasons = ['HTTPConnectionPool: ConnectTimeout'] * 6
        msg = compose_case_error_message(reasons)
        assert msg == '维度评估失败: HTTPConnectionPool: ConnectTimeout'
        assert msg.count('ConnectTimeout') == 1

    def test_truncates_overlong_summary(self):
        msg = compose_case_error_message(['x' * 1500, 'y' * 1500])
        assert len(msg) <= CASE_ERROR_MESSAGE_MAX_LEN + len('...(截断，完整原因见各维度错误信息)')
        assert msg.endswith('...(截断，完整原因见各维度错误信息)')


class TestUpdateTaskCaseStatusInDbErrorPropagation:
    """update_task_case_status_in_db 必须把 error_message 传给 task_service ACL。"""

    def _run(self, **kwargs):
        from evaluation_service.infrastructure.acl.task_acl_repository import (
            TaskAclRepository,
        )
        from evaluation_service.infrastructure.evaluation_mixin import (
            update_task_case_status_in_db,
        )

        captured = {}
        original = TaskAclRepository.update_task_case_status

        def _capture(self, **call_kwargs):
            captured.update(call_kwargs)
            return True
        TaskAclRepository.update_task_case_status = _capture
        try:
            rc = update_task_case_status_in_db(
                None, 1, 'case-1', 'failed', EvaluationStatus.FAILED, **kwargs)
        finally:
            TaskAclRepository.update_task_case_status = original
        return rc, captured

    def test_error_message_reaches_acl(self):
        rc, captured = self._run(error_message='维度评估失败: ConnectTimeout')
        assert rc == 1
        assert captured['error_message'] == '维度评估失败: ConnectTimeout'

    def test_no_error_message_defaults_to_empty(self):
        """成功路径不携带 error_message（服务端仅非空时写入）。"""
        rc, captured = self._run()
        assert rc == 1
        assert captured.get('error_message', '') == ''


class TestMarkGroupCaseFailedErrorPropagation:
    """组内维度全失败 → TaskCase 置 failed 时必须携带失败原因。"""

    def _run(self, error_message):
        from evaluation_service.infrastructure.persistence._result_dimension_mixin import (
            DimensionResultMixin,
        )
        import evaluation_service.infrastructure.evaluation_mixin as eval_mixin_mod

        captured = {}

        def _fake_update(session, task_id, test_case_id, status, evaluation_status,
                         **kwargs):
            captured['task_id'] = task_id
            captured['test_case_id'] = test_case_id
            captured['status'] = status
            captured['evaluation_status'] = evaluation_status
            captured.update(kwargs)
            return 1

        original = eval_mixin_mod.update_task_case_status_in_db
        eval_mixin_mod.update_task_case_status_in_db = _fake_update
        try:
            proc = DimensionResultMixin()
            proc._log = lambda *a, **k: None
            proc._mark_group_case_failed(1, 'case-1', error_message)
        finally:
            eval_mixin_mod.update_task_case_status_in_db = original
        return captured

    def test_group_failure_carries_error_message(self):
        captured = self._run('HTTPConnectionPool: ConnectTimeout')
        assert captured['status'] == 'failed'
        assert captured['evaluation_status'] == EvaluationStatus.FAILED
        assert 'ConnectTimeout' in captured['error_message']

    def test_group_failure_without_message_stays_empty(self):
        captured = self._run('')
        assert captured['error_message'] == ''


class TestApplyFinalStatusErrorPropagation:
    """聚合收口路径（case_any_failed）→ 用例级 error_message 携带维度失败摘要。"""

    def _run(self, new_evaluation_status, failed_reasons):
        from evaluation_service.infrastructure.persistence._result_status_mixin import (
            ResultStatusMixin,
        )
        import evaluation_service.infrastructure.evaluation_mixin as eval_mixin_mod

        captured = {}

        def _fake_update(session, task_id, test_case_id, status, evaluation_status,
                         **kwargs):
            captured.update(kwargs)
            captured['evaluation_status'] = evaluation_status
            return 1

        original = eval_mixin_mod.update_task_case_status_in_db
        eval_mixin_mod.update_task_case_status_in_db = _fake_update
        try:
            proc = ResultStatusMixin()
            proc._log = lambda *a, **k: None
            proc._apply_final_status(
                1, 'case-1', 'failed', new_evaluation_status, None,
                failed_reasons=failed_reasons)
        finally:
            eval_mixin_mod.update_task_case_status_in_db = original
        return captured

    def test_failed_case_carries_composed_reasons(self):
        captured = self._run(
            EvaluationStatus.FAILED, ['ConnectTimeout', 'HTTP 500'])
        assert 'ConnectTimeout' in captured['error_message']
        assert 'HTTP 500' in captured['error_message']

    def test_completed_case_has_no_error_message(self):
        captured = self._run(EvaluationStatus.COMPLETED, ['whatever'])
        assert captured['error_message'] == ''


# ============================================================
# 缺陷②：连接级失败 → 兜底评估端点降级
# ============================================================

class _ClientLogger:
    """把 _log 调用收进列表，避免单测写日志/DB。"""

    def _log(self, level, content, *args, **kwargs):
        self.logs.append((level, content))


def _make_client():
    from evaluation_service.infrastructure.evaluation_api.evaluation_api_client import (
        evaluationApiClient,
    )

    client = evaluationApiClient()
    client.logs = []
    client._log = _ClientLogger._log.__get__(client)
    return client


class TestIsConnectionError:
    def test_connection_kind_detected(self):
        client = _make_client()
        assert client._is_connection_error(
            {'__error__': 'boom', '__error_kind__': EvalErrorKind.CONNECTION.value}) is True

    def test_business_error_not_connection(self):
        client = _make_client()
        assert client._is_connection_error({'__error__': 'HTTP 400'}) is False

    def test_none_and_non_dict_not_connection(self):
        client = _make_client()
        assert client._is_connection_error(None) is False
        assert client._is_connection_error('error text') is False


class TestGetFallbackUrls:
    def test_env_var_takes_priority(self, monkeypatch):
        monkeypatch.setenv('EVAL_FALLBACK_URLS', 'http://fb1:1, http://fb2:2')
        client = _make_client()
        assert client._get_fallback_urls() == ['http://fb1:1', 'http://fb2:2']

    def test_config_list_used_when_env_absent(self, monkeypatch):
        monkeypatch.delenv('EVAL_FALLBACK_URLS', raising=False)
        from shared.utils.config_manager import config_manager
        monkeypatch.setitem(config_manager.config['evaluation_service'],
                            'eval_fallback_urls', ['http://cfg:1'])
        client = _make_client()
        assert client._get_fallback_urls() == ['http://cfg:1']

    def test_primary_url_excluded(self, monkeypatch):
        monkeypatch.setenv('EVAL_FALLBACK_URLS', 'http://primary:1,http://fb:1')
        client = _make_client()
        assert client._get_fallback_urls(exclude_url='http://primary:1') == ['http://fb:1']

    def test_empty_config_means_no_fallback(self, monkeypatch):
        monkeypatch.delenv('EVAL_FALLBACK_URLS', raising=False)
        client = _make_client()
        assert client._get_fallback_urls() == []


class TestMakeApiRequestWithFallback:
    """主端点连接级失败 → 尝试配置兜底端点；业务级失败不切换。"""

    PRIMARY = 'http://primary:8888'
    FALLBACK = 'http://fallback:18888'

    def _patch_urls(self, client, urls):
        client._get_fallback_urls = lambda exclude_url=None: [
            u for u in urls if u != exclude_url]

    def test_connection_error_triggers_fallback_success(self):
        client = _make_client()
        primary_error = {'__error__': 'ConnectTimeout',
                         '__error_kind__': EvalErrorKind.CONNECTION.value}
        fallback_result = {'code': 0, 'data': {'result': {'score': 88}}}

        calls = []

        def _fake_acquire(selected_url, *args, **kwargs):
            calls.append(selected_url)
            return primary_error
        client._acquire_and_execute = _fake_acquire

        def _fake_single(fallback_url, *args, **kwargs):
            calls.append(fallback_url)
            return True, fallback_url, fallback_result
        client._try_single_fallback = _fake_single
        self._patch_urls(client, [self.FALLBACK])

        selected_url, resp = client.make_api_request_with_fallback(
            endpoints=[], method='POST', headers={}, payload={},
            task_id=1, dim_names=['d1'], api_url=self.PRIMARY)

        assert selected_url == self.FALLBACK
        assert resp is fallback_result
        assert calls == [self.PRIMARY, self.FALLBACK]

    def test_connection_error_all_fallbacks_fail_returns_primary_error(self):
        client = _make_client()
        primary_error = {'__error__': 'ConnectTimeout',
                         '__error_kind__': EvalErrorKind.CONNECTION.value}

        client._acquire_and_execute = lambda *a, **k: primary_error

        def _fake_single(fallback_url, *args, **kwargs):
            return False, None, {'__error__': 'ConnectTimeout',
                                 '__error_kind__': EvalErrorKind.CONNECTION.value}
        client._try_single_fallback = _fake_single
        self._patch_urls(client, [self.FALLBACK])

        selected_url, resp = client.make_api_request_with_fallback(
            endpoints=[], method='POST', headers={}, payload={},
            task_id=1, dim_names=['d1'], api_url=self.PRIMARY)

        assert selected_url == self.PRIMARY
        assert resp is primary_error

    def test_no_fallback_configured_keeps_original_error(self):
        client = _make_client()
        primary_error = {'__error__': 'ConnectTimeout',
                         '__error_kind__': EvalErrorKind.CONNECTION.value}
        client._acquire_and_execute = lambda *a, **k: primary_error
        self._patch_urls(client, [])

        def _unexpected(*a, **k):
            raise AssertionError('未配置兜底端点时不应触发兜底尝试')
        client._try_single_fallback = _unexpected

        selected_url, resp = client.make_api_request_with_fallback(
            endpoints=[], method='POST', headers={}, payload={},
            task_id=1, dim_names=['d1'], api_url=self.PRIMARY)

        assert resp is primary_error

    def test_business_error_does_not_switch_endpoint(self):
        client = _make_client()
        business_error = {'__error__': 'HTTP 400'}

        def _unexpected(*a, **k):
            raise AssertionError('业务级失败不应尝试兜底端点')
        client._try_single_fallback = _unexpected
        client._acquire_and_execute = lambda *a, **k: business_error
        self._patch_urls(client, [self.FALLBACK])

        selected_url, resp = client.make_api_request_with_fallback(
            endpoints=[], method='POST', headers={}, payload={},
            task_id=1, dim_names=['d1'], api_url=self.PRIMARY)

        assert selected_url == self.PRIMARY
        assert resp is business_error

    def test_async_error_kind_propagated_from_create_response(self):
        """创建任务失败时 __error_kind__ 必须透传到最终 resp_data。"""
        client = _make_client()
        conn_resp = {'__error__': 'ConnectTimeout',
                     '__error_kind__': EvalErrorKind.CONNECTION.value}
        client.create_task = lambda *a, **k: conn_resp
        resp = client._process_async_result(
            conn_resp, self.PRIMARY, task_id=1, test_case_id='c1', api_id=None)
        assert resp.get('__error_kind__') == EvalErrorKind.CONNECTION.value

        business_resp = {'__error__': 'HTTP 500'}
        resp = client._process_async_result(
            business_resp, self.PRIMARY, task_id=1, test_case_id='c1', api_id=None)
        assert '__error_kind__' not in resp


class TestApiRequestHandlerConnectionMarker:
    """连接级异常必须带 __error_kind__=connection 标记。"""

    def _handler(self):
        from evaluation_service.infrastructure.evaluation_api.api_request_handler import (
            ApiRequestHandler,
        )

        h = ApiRequestHandler()
        h._log = lambda *a, **k: None
        return h

    def test_make_api_request_marks_connection_error(self, monkeypatch):
        import requests
        import evaluation_service.infrastructure.evaluation_api.api_request_handler as mod

        def _raise(*args, **kwargs):
            raise requests.exceptions.ConnectTimeout('connection timed out')
        monkeypatch.setattr(mod.requests, 'post', _raise)

        resp = self._handler().make_api_request('http://x', 'POST', {}, {})
        assert resp['__error_kind__'] == EvalErrorKind.CONNECTION.value

    def test_make_api_request_business_error_unmarked(self, monkeypatch):
        import evaluation_service.infrastructure.evaluation_api.api_request_handler as mod

        class _Resp:
            status_code = 500
            text = 'server error'

            def json(self):
                return {'msg': 'server error'}
        monkeypatch.setattr(mod.requests, 'post', lambda **kwargs: _Resp())

        resp = self._handler().make_api_request('http://x', 'POST', {}, {})
        assert '__error__' in resp
        assert resp.get('__error_kind__') is None

    def test_create_task_upload_marks_connection_error(self, monkeypatch):
        import requests
        import evaluation_service.infrastructure.evaluation_api.api_request_handler as mod

        def _raise(*args, **kwargs):
            raise requests.exceptions.ConnectionError('refused')
        monkeypatch.setattr(mod.requests, 'post', _raise)

        resp = self._handler().create_task_upload('http://x', {}, {})
        assert resp['__error_kind__'] == EvalErrorKind.CONNECTION.value


# ============================================================
# 缺陷③：报告聚合口径（completed_cases 与 failed_cases 不相交）
# ============================================================

def _task(total, completed, failed):
    return {'total_cases': total, 'completed_cases': completed, 'failed_cases': failed}


class TestTaskReportStatsNoNegative:
    """_prepare_report_data 聚合口径：全失败任务不得出现 completed=-1 / pass_rate=-100。"""

    def _run_prepare(self, task):
        import report_service.application.services.report_task_generator as mod

        stubs = {
            '_get_source_task_ids': lambda t: [],
            '_get_dimension_results_batch': lambda ids: ({'d1': []}, [{'id': 'd1'}]),
            '_calculate_summary_dimensions': lambda stats: [],
            '_get_task_test_cases': lambda ids: ([], []),
            '_get_task_resources': lambda ids: (
                [{'name': 'dev'}], [{'name': 'api'}], [1], [1]),
            '_get_resource_result_types_batch': lambda *a, **k: ({}, {}),
            '_build_resources_list': lambda *a, **k: [],
            '_build_all_metrics': lambda dims: [{'id': 1, 'name': 'm'}],
            '_build_case_data': lambda *a, **k: [],
        }
        originals = {}
        try:
            for name, fn in stubs.items():
                originals[name] = getattr(mod.ReportDataBuilder, name)
                setattr(mod.ReportDataBuilder, name, staticmethod(fn))

            saved = {}
            for name in ('_grpc_list_dimensions_all', '_grpc_get_devices_by_ids',
                         '_grpc_get_apis_by_ids'):
                saved[name] = getattr(mod, name)
            setattr(mod, '_grpc_list_dimensions_all', lambda: [])
            setattr(mod, '_grpc_get_devices_by_ids', lambda ids: {})
            setattr(mod, '_grpc_get_apis_by_ids', lambda ids: {})

            for name, fn in {
                '_collect_field_mappings_snapshot': lambda *a, **k: {},
            }.items():
                originals[name] = getattr(mod.ReportTaskGenerator, name)
                setattr(mod.ReportTaskGenerator, name, staticmethod(fn))

            import report_service.application.services.report_utils as utils_mod
            saved_utils = {}
            for name, fn in {
                'calculate_core_metrics': lambda **k: {
                    'metric_data': [], 'tag_metric_data': [], 'raw_data': [],
                    'case_type_stats': [], 'resources': []},
                'build_resource_headers': lambda **k: [],
                'calculate_device_api_stats': lambda **k: ([], []),
            }.items():
                saved_utils[name] = getattr(utils_mod.ReportUtils, name)
                setattr(utils_mod.ReportUtils, name, staticmethod(fn))

            saved_extract = mod.ReportQueryBuilder.extract_case_categories_and_tags
            mod.ReportQueryBuilder.extract_case_categories_and_tags = staticmethod(
                lambda tc: ([], []))
            try:
                return mod.ReportTaskGenerator._prepare_report_data(task, 1, [SimpleNamespace(id=1)])
            finally:
                mod.ReportQueryBuilder.extract_case_categories_and_tags = saved_extract
                for name, fn in saved_utils.items():
                    setattr(utils_mod.ReportUtils, name, fn)
        finally:
            for name, fn in originals.items():
                if name.startswith('_grpc'):
                    continue
                owner = (mod.ReportDataBuilder if name in stubs
                         else mod.ReportTaskGenerator)
                setattr(owner, name, fn)
            for name, fn in saved.items():
                setattr(mod, name, fn)

    def test_all_failed_task_has_zero_completed_and_zero_rate(self):
        """INT-95 实测场景：total=1、failed=1、completed=0 → 不得再减出 -1/-100。"""
        data = self._run_prepare(_task(total=1, completed=0, failed=1))
        assert data['completed_cases'] == 0
        assert data['failed_cases'] == 1
        assert data['success_rate'] == 0

    def test_mixed_task_stats_consistent(self):
        """completed 与 failed 各自独立计数，互不扣减。"""
        data = self._run_prepare(_task(total=3, completed=2, failed=1))
        assert data['completed_cases'] == 2
        assert data['success_rate'] == pytest.approx(2 / 3 * 100)


class TestCompareReportStatsNoNegative:
    def test_secondary_records_no_double_subtraction(self):
        from report_service.application.services.report_compare_generator_persist_mixin import (
            ReportComparePersistMixin,
        )
        import report_service.application.services.report_compare_generator_persist_mixin as mod

        repo = MagicMock()
        repo.add.return_value = 99
        original = mod.report_repository
        mod.report_repository = repo
        try:
            tasks = [_task(total=1, completed=0, failed=1),
                     _task(total=2, completed=1, failed=1)]
            ReportComparePersistMixin._create_secondary_report_records(
                99, [1, 2], tasks, *([[]] * 16))
        finally:
            mod.report_repository = original

        summary_data = repo.add_summary.call_args[0][1]
        # completed: 0 + 1 = 1（原实现会算出 0-1-1 = -2）
        assert summary_data['completed_cases'] == 1
        assert summary_data['failed_cases'] == 2
        assert summary_data['total_cases'] == 3
        assert summary_data['pass_rate'] == pytest.approx(1 / 3 * 100, abs=0.01)

    def test_persist_compare_report_uses_summary_counts(self):
        from report_service.application.services.report_compare_generator_persist_mixin import (
            ReportComparePersistMixin,
        )
        import report_service.application.services.report_compare_generator_persist_mixin as mod

        repo = MagicMock()
        repo.add.return_value = 7
        original = mod.report_repository
        original_aggregate = mod.ReportAggregate
        mod.report_repository = repo
        mod.ReportAggregate = MagicMock()
        try:
            summary = {'total_cases': 3, 'completed_cases': 2, 'failed_cases': 1,
                       'overall_success_rate': 66.67}
            ReportComparePersistMixin._persist_compare_report(
                'n', 'd', summary, [], {})
        finally:
            mod.report_repository = original
            mod.ReportAggregate = original_aggregate

        summary_data = repo.add_summary.call_args[0][1]
        assert summary_data['completed_cases'] == 2
        assert summary_data['failed_cases'] == 1


class TestCompareSummaryCarriesCaseCounts:
    def test_build_compare_summary_includes_completed_and_failed(self):
        from report_service.application.services.report_compare_generator_data_mixin import (
            ReportCompareDataMixin,
        )

        data_dict = {'report_task_type': 'api', 'task_weighted_values': {},
                     'total_cases': 3, 'completed_cases': 2, 'failed_cases': 1,
                     'success_rate': 66.67, 'case_categories_list': [],
                     'case_tags_list': [], 'device_list': [], 'api_list': [],
                     'resources': [], 'all_metrics': [], 'metric_data': [],
                     'tag_metric_data': [], 'raw_data': [], 'case_type_stats': [],
                     'device_stats': [], 'api_stats': [], 'source_cases': [],
                     'resource_headers': [], 'comparison_data': {}}
        summary = ReportCompareDataMixin._build_compare_summary(
            [], [1], [], data_dict)
        assert summary['completed_cases'] == 2
        assert summary['failed_cases'] == 1
        assert summary['overall_success_rate'] == 66.67
