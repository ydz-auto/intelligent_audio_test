# -*- coding: utf-8 -*-
"""INT-2189 回归：评估收口日志不得因 module 参数重复绑定抛 TypeError。

原缺陷：`_result_status_mixin` 的「维度未全，继续等待」DEBUG 分支调用
`self._log(module='evaluation', ...)`，而 `EvaluationLoggerMixin._log` 已固定
传 `module='Evaluation'` 再把 `**kwargs` 展开给 `log_and_emit` → `module`
重复绑定抛 `TypeError: got multiple values for keyword argument 'module'`，
被 `update_task_case_status` 外层 `except Exception` 吞成一行 ERROR，整段终态
写回被跳过：task_case 永久停在 evaluating、任务主循环忙等到超时才判 failed。

覆盖：
1. `_log` 显式接受 `module=` 覆盖，不再落入 kwargs 重复绑定；
2. 真实 MRO（ResultStatusMixin + EvaluationLoggerMixin）走到「维度未全」分支
   时不抛异常，且照常记出 DEBUG 日志；
3. 外层 `except` 不再静默：带 stack 记录后向上抛，由调用方按失败收口。
"""
import os
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402


def _capture_logs():
    """拦截 EvaluationLoggerMixin 模块内的 log_and_emit，返回 (还原函数, 记录列表)。"""
    from evaluation_service.domain.services import evaluation_logger as mod

    calls = []
    original = mod.log_and_emit
    mod.log_and_emit = lambda **kwargs: calls.append(kwargs)
    return mod, original, calls


class TestLogModuleKwarg:
    def test_log_accepts_module_override(self):
        """调用方传 module= 只覆盖取值，不因重复绑定抛 TypeError。"""
        mod, original, calls = _capture_logs()
        try:
            mixin = mod.EvaluationLoggerMixin()
            mixin._log(level='DEBUG', module='evaluation', category='database',
                       content='int2189 probe')
        finally:
            mod.log_and_emit = original

        assert len(calls) == 1
        assert calls[0]['module'] == 'evaluation'
        assert calls[0]['category'] == 'database'

    def test_log_default_module_unchanged(self):
        """未传 module 时保持既有 'Evaluation' 默认值（零回归）。"""
        mod, original, calls = _capture_logs()
        try:
            mixin = mod.EvaluationLoggerMixin()
            mixin._log(level='INFO', content='int2189 probe')
        finally:
            mod.log_and_emit = original

        assert calls[0]['module'] == 'Evaluation'


class _ProcessorMixin:
    """复刻 EvaluationResultProcessor 的 MRO：日志混入在状态推进混入之前。"""


def _make_processor():
    from evaluation_service.domain.services.evaluation_logger import EvaluationLoggerMixin
    from evaluation_service.infrastructure.persistence._result_status_mixin import (
        ResultStatusMixin,
    )

    class _Proc(EvaluationLoggerMixin, ResultStatusMixin):
        pass

    return _Proc()


class TestDimIncompleteBranch:
    def _run(self, expected_dim_count, dims):
        from evaluation_service.infrastructure.persistence import (
            _result_status_mixin as m,
        )

        mod, original, calls = _capture_logs()
        fake_session = mock.MagicMock()
        fake_session.query.return_value.filter_by.return_value.all.return_value = dims

        try:
            with mock.patch('shared.models.database.get_db_session',
                            return_value=fake_session):
                proc = _make_processor()
                return proc._check_all_results_completed_by_count(
                    task_id=1, test_case_id='case-1', expected_count=1,
                    expected_dim_count=expected_dim_count,
                    all_results=[SimpleNamespace(id=7)],
                ), calls
        finally:
            mod.log_and_emit = original

    def test_dims_incomplete_waits_without_type_error(self):
        """维度未全 → 返回未收敛，且记出「继续等待」DEBUG 日志（曾在此抛 TypeError）。"""
        result, calls = self._run(expected_dim_count=3,
                                  dims=[SimpleNamespace(evaluation_status='completed')])

        case_all_finished, case_any_failed, failed_reasons = result
        assert case_all_finished is False
        assert case_any_failed is False
        assert failed_reasons == []
        assert len(calls) == 1
        assert calls[0]['level'] == 'DEBUG'
        assert '维度未全' in calls[0]['content']


class TestOuterExceptNotSilent:
    def test_update_task_case_status_logs_stack_and_reraises(self):
        """读取链路异常：记录带 stack 的 ERROR 后向上抛，不再静默吞掉。"""
        from evaluation_service.infrastructure.persistence import (
            _result_status_mixin as m,
        )

        mod, original, calls = _capture_logs()
        try:
            with mock.patch.object(m, 'task_acl_repository') as repo:
                repo.get_task_by_id.side_effect = RuntimeError('int2189 boom')
                proc = _make_processor()
                with pytest.raises(RuntimeError, match='int2189 boom'):
                    proc.update_task_case_status(1, True, 2, 'case-1')
        finally:
            mod.log_and_emit = original

        assert len(calls) == 1
        assert calls[0]['level'] == 'ERROR'
        # 带 stack：content 里应含 traceback 的调用栈标记
        assert 'Traceback (most recent call last)' in calls[0]['content']
        assert 'int2189 boom' in calls[0]['content']
