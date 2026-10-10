# -*- coding: utf-8 -*-
"""INT-116 测试工程师独立验收补充：DB 会话作用域收窄 + 终态写库入口接线守卫。

开发侧 tests/unit/test_int116_evaluation_terminal_state.py 已覆盖：
清理器不重建 engine、仓储内联重试、延迟队列补写/去重/超窗、
mark_case_failed_if_active 兜底。本文件补齐其余两个守卫面
（修复①的编排层与修复②的 INT-107 终态入口）：

A. 会话收窄（连接池耗尽修复的编排层守卫）：
   1. process_group_dimension_results —— gRPC 读取 TestResult 发生在
      get_db_session() 之前；_build_and_store_algorithm_results（多次
      gRPC+文件 IO）与 TaskCase 状态推进发生在会话 close 之后；
      open→close 窗口内禁止任何跨服务调用（事故形态：持连接做 30s 级
      gRPC，pool 3+5 被同步占满）。
   2. aggregate_round_results —— aggregated 的 gRPC 写回在会话释放后执行。
   3. update_all_dimensions_in_group_failed —— 本地 commit 失败（连接池
      耗尽场景）不得阻断 TaskCase failed 终态推进；gRPC 在会话释放后。
B. 接线（INT-107 终态口径入口）：
   4. update_task_case_status_in_db —— 持续失败返回 0 且转延迟队列
      （evaluation_status/error_message 随行）；成功返回 1 且不入队。
   5. update_task_status_with_retry —— 任务级终态失败同样转延迟队列。
"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int116_t_') + '/guard.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from evaluation_service.infrastructure.acl import task_acl_repository
import evaluation_service.infrastructure.acl.task_case_status_retry as retry_mod
from evaluation_service.infrastructure.acl.task_case_status_retry import (
    TaskStatusRetryQueue,
)
from evaluation_service.infrastructure import evaluation_mixin as em
from evaluation_service.infrastructure.persistence import _result_group_mixin as group_mod
from evaluation_service.infrastructure.persistence import _result_dimension_mixin as dim_mod
from evaluation_service.infrastructure.persistence import round_aggregator as agg_mod
from evaluation_service.infrastructure.persistence._result_group_mixin import GroupResultMixin
from evaluation_service.infrastructure.persistence._result_dimension_mixin import DimensionResultMixin
from evaluation_service.infrastructure.persistence.round_aggregator import RoundAggregator


# ==================== 测试夹具 ====================

class _EventLog(list):
    def add(self, label):
        self.append(label)


class _FakeQuery:
    def filter(self, *a, **k):
        return self

    def all(self):
        return []

    def first(self):
        return None


class _FakeSession:
    """只记录生命周期事件的假会话，供窗口断言使用。"""

    def __init__(self, events, commit_error=None):
        self._events = events
        self._commit_error = commit_error

    def query(self, *a, **k):
        return _FakeQuery()

    def get(self, *a, **k):
        return None

    def add(self, *a, **k):
        pass

    def commit(self):
        if self._commit_error is not None:
            raise self._commit_error
        self._events.add('session_commit')

    def rollback(self):
        self._events.add('session_rollback')

    def close(self):
        self._events.add('session_close')


class _TestResultDTO:
    def __init__(self):
        self.api_id = 77
        self.device_id = 'dev-1'
        self.test_case_id = 'C-9'


def _bare(mixin_cls):
    return object.__new__(mixin_cls)


def _patch_session_factory(monkeypatch, module, events, commit_error=None):
    def _factory():
        events.add('session_open')
        return _FakeSession(events, commit_error=commit_error)
    monkeypatch.setattr(module, 'get_db_session', _factory)


def _assert_no_cross_service_in_session_window(events):
    window = _window_between(events, 'session_open', 'session_close')
    leaked = [e for e in window if e.startswith('grpc') or e.startswith('build_and_store')]
    assert not leaked, f'持连接窗口内出现跨服务调用/长IO: {leaked}'


def _window_between(events, start, end):
    return events[events.index(start) + 1:events.index(end)]


@pytest.fixture()
def silent_queue(monkeypatch):
    """独立队列实例：关掉后台线程，只检查入队内容。"""
    monkeypatch.setattr(TaskStatusRetryQueue, '_ensure_worker_locked',
                        lambda self: None)
    queue = TaskStatusRetryQueue()
    monkeypatch.setattr(retry_mod, 'task_status_retry_queue', queue)
    return queue


def _patch_inline_sleep(monkeypatch):
    # 内联重试退避 0.5s/1.0s 在单测里跳过；monkeypatch 会自动还原全局 time.sleep
    monkeypatch.setattr(retry_mod.time, 'sleep', lambda s: None)


# ==================== A1. process_group_dimension_results 会话收窄 ====================

def test_group_dimension_results_no_cross_service_in_session_window(monkeypatch):
    events = _EventLog()
    _patch_session_factory(monkeypatch, group_mod, events)
    monkeypatch.setattr(
        task_acl_repository, 'get_test_result_by_id',
        lambda result_id: (events.add('grpc_get_test_result'), _TestResultDTO())[1])

    obj = _bare(GroupResultMixin)
    obj.parse_dimension_result = lambda resp, dim: ('raw', 3.5)
    obj._log = lambda *a, **k: None
    obj.update_dimension_result_completed = lambda *a, **k: events.add('dim_update')
    obj._build_and_store_algorithm_results = \
        lambda *a, **k: events.add('build_and_store_grpc_io')
    obj.check_all_dimensions_completed = \
        lambda *a, **k: (events.add('grpc_check_completed'), True)[1]
    obj.is_multi_round_result = lambda *a, **k: False
    obj.update_task_case_status = \
        lambda *a, **k: events.add('grpc_case_status_update')

    obj.process_group_dimension_results(
        resp_data={'name': 'x'}, group_items=[({'id': 1, 'name': 'a'}, 11)],
        task_id=9, test_case_id='C-9', result_id=5, api_request_body={},
        test_type='api')

    assert events == [
        'grpc_get_test_result',   # 会话外
        'session_open', 'dim_update', 'session_commit', 'session_close',
        'build_and_store_grpc_io',   # 会话外
        'grpc_check_completed',      # 会话外
        'grpc_case_status_update',   # 会话外
    ]
    _assert_no_cross_service_in_session_window(events)


# ==================== A2. aggregate_round_results gRPC 写回移出会话 ====================

def test_aggregate_round_results_grpc_writeback_after_session_close(monkeypatch):
    events = _EventLog()
    _patch_session_factory(monkeypatch, agg_mod, events)

    obj = _bare(RoundAggregator)
    obj._log = lambda *a, **k: None
    obj._update_algorithm_result_aggregated = \
        lambda *a, **k: events.add('grpc_writeback_aggregated')

    result = obj.aggregate_round_results(result_id=5, task_id=9, test_case_id='C-9')

    assert result == {'round_count': 0, 'completed_rounds': 0}
    assert events == ['session_open', 'session_commit', 'session_close',
                      'grpc_writeback_aggregated']
    _assert_no_cross_service_in_session_window(events)


# ==================== A3. update_all_dimensions_in_group_failed 容错与收窄 ====================

def test_group_case_failed_not_blocked_by_local_commit_failure(monkeypatch):
    """本地 TRD 落库失败（连接池耗尽）不得跳过 TaskCase failed 终态推进。

    事故形态：原实现 commit 抛异常直接冒泡，_mark_group_case_failed 被跳过，
    用例永久停留 evaluating。
    """
    events = _EventLog()
    _patch_session_factory(monkeypatch, dim_mod, events,
                           commit_error=RuntimeError('QueuePool exhausted'))

    obj = _bare(DimensionResultMixin)
    obj._log = lambda *a, **k: None
    obj.update_dimension_result_failed = lambda *a, **k: events.add('trd_fail_write')
    obj._mark_group_case_failed = lambda *a, **k: events.add('grpc_case_failed')

    obj.update_all_dimensions_in_group_failed(
        group_items=[({'id': 1, 'name': 'a'}, 11)],
        error_message='endpoint unreachable', task_id=9, test_case_id='C-9',
        api_raw_response={}, api_request_body={})

    assert 'grpc_case_failed' in events
    assert _window_between(events, 'session_open', 'session_close') == ['trd_fail_write']
    assert events.index('session_close') < events.index('grpc_case_failed')


def test_group_case_failed_after_clean_commit(monkeypatch):
    events = _EventLog()
    _patch_session_factory(monkeypatch, dim_mod, events)

    obj = _bare(DimensionResultMixin)
    obj._log = lambda *a, **k: None
    obj.update_dimension_result_failed = lambda *a, **k: events.add('trd_fail_write')
    obj._mark_group_case_failed = lambda *a, **k: events.add('grpc_case_failed')

    obj.update_all_dimensions_in_group_failed(
        group_items=[({'id': 1, 'name': 'a'}, 11)],
        error_message='endpoint unreachable', task_id=9, test_case_id='C-9')

    assert events == ['session_open', 'trd_fail_write', 'session_commit',
                      'session_close', 'grpc_case_failed']


# ==================== B4. update_task_case_status_in_db 终态入口接线 ====================

def test_update_task_case_status_in_db_persistent_failure_enqueues(silent_queue, monkeypatch):
    """INT-107 终态写入口：内联重试耗尽 → 返回 0 且转延迟队列补写。"""
    _patch_inline_sleep(monkeypatch)
    calls = {'n': 0}

    def _update(**kwargs):
        calls['n'] += 1
        raise RuntimeError('task_service down')

    # 说明：此处 stub 直接替换仓储方法，异常一次即冒泡（仓储内的 3 次内联
    # 重试已由开发侧 test_repo_update_task_case_status_persistent_failure
    # 以 gRPC stub 层覆盖）；本测试守卫的是"仍失败 → 转延迟队列"的接线。
    monkeypatch.setattr(task_acl_repository, 'update_task_case_status', _update)

    ret = em.update_task_case_status_in_db(
        None, task_id=9, test_case_id='C-9', status='failed',
        evaluation_status='failed', error_message='endpoint unreachable')

    assert ret == 0
    assert calls['n'] == 1
    key = (9, 'C-9')
    assert key in silent_queue._pending_case
    item = silent_queue._pending_case[key]
    assert item.status  # 推导终态非空
    assert item.evaluation_status == 'failed'
    assert item.error_message == 'endpoint unreachable'


def test_update_task_case_status_in_db_success_no_enqueue(silent_queue, monkeypatch):
    calls = {'n': 0}

    def _update(**kwargs):
        calls['n'] += 1
        return True

    monkeypatch.setattr(task_acl_repository, 'update_task_case_status', _update)

    ret = em.update_task_case_status_in_db(
        None, task_id=9, test_case_id='C-9', status='completed',
        evaluation_status='completed')

    assert ret == 1
    assert calls['n'] == 1
    assert not silent_queue._pending_case


# ==================== B5. 任务级终态包装接线 ====================

def test_update_task_status_with_retry_failure_enqueues(silent_queue, monkeypatch):
    _patch_inline_sleep(monkeypatch)
    monkeypatch.setattr(task_acl_repository, 'update_task_status',
                        lambda *a, **k: False)

    ok = em.update_task_status_with_retry(9, 'failed')

    assert ok is False
    assert 9 in silent_queue._pending_task
    assert silent_queue._pending_task[9].status == 'failed'


def test_update_task_status_with_retry_success_no_enqueue(silent_queue, monkeypatch):
    monkeypatch.setattr(task_acl_repository, 'update_task_status',
                        lambda *a, **k: True)

    ok = em.update_task_status_with_retry(9, 'completed')

    assert ok is True
    assert not silent_queue._pending_task
