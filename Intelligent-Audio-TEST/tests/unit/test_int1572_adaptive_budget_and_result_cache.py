# -*- coding: utf-8 -*-
"""INT-1572 返工二轮：自适应并发 / 请求预算 / 结果文件缺失负缓存。

复测（INT-1482 二次）失败清单的对应关系：
- P2「50 用例在宿主 audio 排队窗口整批 60s 超时」→ 固定 8 路并发是放大器：
  宿主 audio 串行取数，8 路会把单条拖过 10s 超时线，整批打成 0。改为 AIMD
  并发 + 单条超时放大 + 超时重试。
- P1「138 用例仍不可用」→ 整批截止按本次请求剩余预算分配，ACL 不吃光 60s；
  结果文件缺失判定按路径缓存，同一请求内不再每条用例重复付一次 OSS 探测。
"""
import os
import time

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from report_service.config.config import Config  # noqa: E402
from report_service.domain.request_budget import RequestBudget  # noqa: E402
from report_service.infrastructure.acl import testcase_acl_repository as acl_mod  # noqa: E402
from report_service.infrastructure.acl.testcase_acl_repository import (  # noqa: E402
    TestCaseConfigAclRepositoryImpl,
)
from report_service.application.services.report_utils import result_data_loader  # noqa: E402


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    acl_mod.clear_caches()
    result_data_loader.clear_missing_cache()
    monkeypatch.setattr(Config, 'TESTCASE_ACL_CACHE_TTL_SECONDS', 120.0)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_NEGATIVE_CACHE_TTL_SECONDS', 30.0)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_TOTAL_TIMEOUT_SECONDS', 10.0)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_TIMEOUT_SECONDS', 0.2)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_INITIAL_WORKERS', 2)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_MIN_WORKERS', 1)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_MAX_WORKERS', 8)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_MAX_ATTEMPTS', 2)
    monkeypatch.setattr(Config, 'REPORT_RESULT_FILE_NEGATIVE_CACHE_TTL_SECONDS', 60.0)
    yield
    acl_mod.clear_caches()
    result_data_loader.clear_missing_cache()


def _payload(tc_id):
    return {'id': tc_id, 'name': f'case-{tc_id}', 'config': {}}


def _patch_fetch(monkeypatch, fn):
    calls = []

    def _fetch(tc_id, timeout=None):
        calls.append(tc_id)
        return fn(tc_id, timeout)

    monkeypatch.setattr(TestCaseConfigAclRepositoryImpl, '_fetch_detail', staticmethod(_fetch))
    return calls


# ----------------------------------------------------------------------
# 自适应并发 + 超时重试
# ----------------------------------------------------------------------

def test_timed_out_item_is_retried_and_eventually_succeeds(monkeypatch):
    """单条首次超时不再直接判「没取到」：排到队尾重试，第二次成功即取到。"""
    attempts = {}

    def _fetch(tc_id, timeout):
        attempts[tc_id] = attempts.get(tc_id, 0) + 1
        if tc_id == '101' and attempts[tc_id] == 1:
            raise TimeoutError('GetTestCaseDetail 超时')
        return _payload(tc_id)

    calls = _patch_fetch(monkeypatch, _fetch)

    result = TestCaseConfigAclRepositoryImpl().list_testcases_by_ids(['101', '102'])

    assert set(result.items) == {'101', '102'}
    assert result.incomplete_ids == []
    assert calls.count('101') == 2


def test_governor_backs_off_on_timeout_and_recovers_on_success():
    """超时减半并发并放大单条超时；连续成功后再往回收。"""
    governor = acl_mod._AdaptiveConcurrency(initial=8, minimum=1, maximum=8)

    governor.on_timeout()
    assert governor.permits == 4
    assert governor.timeout_scale > 1.0
    governor.on_timeout()
    assert governor.permits == 2
    governor.on_timeout()
    assert governor.permits == 1
    # 下限不被击穿
    governor.on_timeout()
    assert governor.permits == 1

    scale_after_backoff = governor.timeout_scale
    for _ in range(10):
        governor.on_success()
    assert governor.timeout_scale < scale_after_backoff
    # 连续成功后并发回升（回升步长受当前档位约束，不要求精确到某一档）
    assert 2 <= governor.permits <= 8


def test_repeated_timeouts_end_up_in_incomplete_not_missing(monkeypatch):
    """一直超时的 id 计入 incomplete（数据不完整），不当成「用例不存在」。"""
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_MAX_ATTEMPTS', 2)

    def _fetch(tc_id, timeout):
        raise TimeoutError('down')

    calls = _patch_fetch(monkeypatch, _fetch)

    result = TestCaseConfigAclRepositoryImpl().list_testcases_by_ids(['101'])

    assert result.items == {}
    assert result.incomplete_ids == ['101']
    assert calls.count('101') == 2


# ----------------------------------------------------------------------
# 请求预算
# ----------------------------------------------------------------------

def test_lookup_budget_follows_request_budget_minus_reserve(monkeypatch):
    """ACL 取数预算 = 本次请求剩余 - 后续阶段预留，且不超过配置上限。"""
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_REQUEST_RESERVE_SECONDS', 5.0)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_TOTAL_TIMEOUT_SECONDS', 40.0)

    with RequestBudget(20.0):
        budget = TestCaseConfigAclRepositoryImpl._lookup_budget_seconds()
        assert 14.0 <= budget <= 15.5

    with RequestBudget(120.0):
        # 剩余再多也不超过配置上限
        assert TestCaseConfigAclRepositoryImpl._lookup_budget_seconds() == 40.0

    # 无请求预算上下文（生成线程池 / 单测）用固定兜底
    assert TestCaseConfigAclRepositoryImpl._lookup_budget_seconds() == 40.0


def test_slow_backend_stops_at_budget(monkeypatch):
    """预算用尽即收尾：不能等到每一条都跑满，未取到的标 incomplete。"""
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_TIMEOUT_SECONDS', 5.0)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_MIN_WORKERS', 1)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_INITIAL_WORKERS', 1)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_MAX_ATTEMPTS', 1)

    def _fetch(tc_id, timeout):
        time.sleep(0.4)
        return _payload(tc_id)

    _patch_fetch(monkeypatch, _fetch)

    repo = TestCaseConfigAclRepositoryImpl()
    t0 = time.monotonic()
    with RequestBudget(1.0):  # 预留 18s → 预算被夹到 0，立即收尾
        result = repo.list_testcases_by_ids([str(i) for i in range(20)])
    elapsed = time.monotonic() - t0

    assert elapsed < 3.0
    assert result.items == {}
    assert len(result.incomplete_ids) == 20


# ----------------------------------------------------------------------
# 结果文件缺失负缓存
# ----------------------------------------------------------------------

def test_missing_result_file_probed_once_per_request(monkeypatch):
    """同一路径的「对象不存在」只探测一次，之后直接用 DB 轻量载荷。"""
    probes = []

    def _fake_read(path):
        probes.append(path)
        return {}

    monkeypatch.setattr(result_data_loader, 'read_result_data_file', _fake_read)

    db_payload = {'result_type': 'recording'}
    path = 'case_result/418/tc1/dev/result_data.json'
    for _ in range(5):
        assert result_data_loader.load_full_result_data_cached(db_payload, path) == db_payload

    assert probes == [path]


def test_existing_result_file_is_read_every_time_and_not_negatively_cached(monkeypatch):
    """文件存在时正常返回文件内容，不做负缓存（结果文件可能被补写）。"""
    payload = {'result_type': 'recording', 'raw_results': [1]}

    monkeypatch.setattr(result_data_loader, 'read_result_data_file', lambda p: payload)

    for _ in range(3):
        assert result_data_loader.load_full_result_data_cached({}, 'case_result/x') == payload


def test_missing_cache_can_be_disabled(monkeypatch):
    monkeypatch.setattr(Config, 'REPORT_RESULT_FILE_NEGATIVE_CACHE_TTL_SECONDS', 0.0)
    probes = []
    monkeypatch.setattr(result_data_loader, 'read_result_data_file',
                        lambda p: probes.append(p) or {})

    for _ in range(3):
        result_data_loader.load_full_result_data_cached({'a': 1}, 'case_result/y')

    assert len(probes) == 3


def test_missing_cache_falls_back_to_db_payload_only_when_dict(monkeypatch):
    monkeypatch.setattr(result_data_loader, 'read_result_data_file', lambda p: {})

    assert result_data_loader.load_full_result_data_cached(None, 'case_result/z') == {}
    assert result_data_loader.load_full_result_data_cached({'k': 'v'}, 'case_result/z') == {'k': 'v'}


# ----------------------------------------------------------------------
# servicer 预算注入
# ----------------------------------------------------------------------

class _FakeContext:
    def __init__(self, remaining):
        self._remaining = remaining

    def time_remaining(self):
        return self._remaining


def test_get_case_averages_servicer_injects_request_budget(monkeypatch):
    """GetCaseAverages 处理期间，ACL 能看到「网关剩余时限」口径的预算。"""
    from report_service.domain import request_budget as rb
    from report_service.interfaces.grpc.servicers import ReportServicer

    seen = {}

    class _Handler:
        def handle_get_case_averages(self, params):
            seen['remaining'] = rb.remaining_seconds()
            return {'total_cases': 0}

    servicer = ReportServicer()
    monkeypatch.setattr(type(servicer), 'query_handler', property(lambda self: _Handler()))

    resp = servicer.GetCaseAverages(
        type('Req', (), {'data': '{"task_id": 418}'})(), _FakeContext(52.0))

    assert resp.success is True
    assert seen['remaining'] is not None and 50.0 <= seen['remaining'] <= 52.0
    # 退出后预算上下文复位（同进程的其它调用不受影响）
    assert rb.remaining_seconds() is None


def test_get_case_averages_servicer_without_deadline_uses_no_budget(monkeypatch):
    """无截止（单测 / 进程内调用）时不注入预算，ACL 回落配置固定值。"""
    from report_service.domain import request_budget as rb
    from report_service.interfaces.grpc.servicers import ReportServicer

    seen = {}

    class _Handler:
        def handle_get_case_averages(self, params):
            seen['remaining'] = rb.remaining_seconds()
            return {'total_cases': 0}

    servicer = ReportServicer()
    monkeypatch.setattr(type(servicer), 'query_handler', property(lambda self: _Handler()))

    servicer.GetCaseAverages(type('Req', (), {'data': '{"task_id": 418}'})(), None)

    assert seen['remaining'] is None
