# -*- coding: utf-8 -*-
"""INT-1572 回归：报告 ACL 按 ID 取用例（GetTestCaseDetail 逐条 + 受限并发 + 缓存）。

缺陷背景：原实现用 ListTestCases(per_page=1000) 全表拉取后按 id 过滤，docker
栈上单次 20~35s 且与所需 id 数无关；报告对比 / case-averages 一次请求内调用
2~4 次，直接撞上网关 60s 截止（INT-1482 复测：compare 60s 超时）。

INT-1572 返工（复测 P1/P2）后本测试锁定：
1. 返回 TestCaseLookupResult：items 为 {str(id): TestCaseDTO}，载荷挂 result_data；
2. 只查缺失的 id（去重），缺失/软删的用例进 missing_ids、不抛错；
3. 单条失败 / 整批截止不拖垮整批，未完成的 id 进 incomplete_ids 且 partial=True
   （调用方据此判定「数据不完整」，不再把部分用例算出的均值当完整数据）；
4. 命中 TTL 缓存不再发 gRPC；未取到的 id 进负缓存，短时间内不重复查询
   （否则同一报告请求的后续 ACL 调用会再吃一个整批截止）。

INT-1572 返工三轮（终审 P2/P3）后追加：
5. 取数 worker 线程带调用方操作人身份（否则出站 GetTestCaseDetail 无 x-user-id，
   task_service 把 PRIVATE 用例按 404 返回，owner 自己也看不到）；
6. 缓存 / 负缓存按可见性与身份分键：shared 载荷跨用户共享，private 只对取到它的
   操作人有效，别人的 404 不会在负缓存期内把 owner 也挡住。
"""
import os
import threading
import time

import pytest

from shared.infrastructure.user_context import (
    get_current_user_id,
    get_current_user_is_admin,
    set_current_user_id,
    set_current_user_is_admin,
)

# 与本目录既有单测一致：BaseConfig 在首次导入即冻结，凭据用假值占位
# （conftest 的 INT-352 守卫已把 OSS_ENDPOINT 指向死端口，不会触达真实存储）
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from report_service.config.config import Config  # noqa: E402
from report_service.infrastructure.acl import testcase_acl_repository as acl_mod  # noqa: E402
from report_service.infrastructure.acl.testcase_acl_repository import (  # noqa: E402
    TestCaseConfigAclRepositoryImpl,
)


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    """每个用例独立缓存；缓存 TTL / 整批截止按用例覆盖；操作人身份复位。"""
    acl_mod.clear_caches()
    monkeypatch.setattr(Config, 'TESTCASE_ACL_CACHE_TTL_SECONDS', 120.0)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_NEGATIVE_CACHE_TTL_SECONDS', 30.0)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_TOTAL_TIMEOUT_SECONDS', 10.0)
    set_current_user_id(None)
    set_current_user_is_admin(False)
    yield
    acl_mod.clear_caches()
    set_current_user_id(None)
    set_current_user_is_admin(False)


def _as_user(user_id, is_admin=False):
    """模拟一次 RPC 线程的操作人上下文。"""
    set_current_user_id(user_id)
    set_current_user_is_admin(is_admin)


def _payload(tc_id, name=None):
    return {'id': tc_id, 'name': name or f'case-{tc_id}', 'config': {'rounds': []}}


def _patch_fetch(monkeypatch, fn):
    """用可计数的假 GetTestCaseDetail 替换逐条取详情。

    真实现签名为 (tc_id, timeout=None)：timeout 由自适应调度器按剩余预算/
    当前负载给出（INT-1572 返工二轮），假实现忽略它。
    """
    calls = []
    lock = threading.Lock()

    def _fetch(tc_id, timeout=None):
        with lock:
            calls.append(tc_id)
        return fn(tc_id)

    monkeypatch.setattr(TestCaseConfigAclRepositoryImpl, '_fetch_detail', staticmethod(_fetch))
    return calls


def test_returns_str_keyed_map_with_payload(monkeypatch):
    calls = _patch_fetch(monkeypatch, lambda tc_id: _payload(tc_id))

    result = TestCaseConfigAclRepositoryImpl().list_testcases_by_ids([101, 102]).items

    assert set(result) == {'101', '102'}
    assert result['101'].id == '101'
    assert result['101'].name == 'case-101'
    # 载荷挂在 result_data，下游 dto_to_dict 依赖该约定
    assert result['101'].result_data == _payload('101')
    assert sorted(calls) == ['101', '102']


def test_dedupes_input_ids(monkeypatch):
    calls = _patch_fetch(monkeypatch, lambda tc_id: _payload(tc_id))

    result = TestCaseConfigAclRepositoryImpl().list_testcases_by_ids(
        ['101', 101, None, '101', 102]).items

    assert set(result) == {'101', '102'}
    assert sorted(calls) == ['101', '102']


def test_missing_cases_are_reported_not_raised(monkeypatch):
    """软删 / 不存在：进 missing_ids，但不算「查询不完整」。"""
    _patch_fetch(monkeypatch, lambda tc_id: _payload(tc_id) if tc_id == '101' else None)

    result = TestCaseConfigAclRepositoryImpl().list_testcases_by_ids([101, 999])

    assert set(result.items) == {'101'}
    assert result.missing_ids == ['999']
    assert result.incomplete_ids == []
    assert result.partial is False


def test_single_failure_marks_result_partial(monkeypatch):
    """单条失败不拖垮整批，但必须标成不完整（不能当缺失用例）。"""
    def fetch(tc_id):
        if tc_id == '102':
            raise RuntimeError('DEADLINE_EXCEEDED')
        return _payload(tc_id)

    _patch_fetch(monkeypatch, fetch)

    result = TestCaseConfigAclRepositoryImpl().list_testcases_by_ids([101, 102, 103])

    assert set(result.items) == {'101', '103'}
    assert result.incomplete_ids == ['102']
    assert '102' in result.missing_ids
    assert result.partial is True


def test_batch_deadline_returns_partial(monkeypatch):
    """整批超时：慢查询被取消，快查询结果照样返回，未完成的标 partial。"""
    tick = threading.Event()

    def fetch(tc_id):
        if tc_id == 'slow':
            tick.wait(5)  # 模拟宿主取数卡住
            return _payload(tc_id)
        return _payload(tc_id)

    _patch_fetch(monkeypatch, fetch)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_TOTAL_TIMEOUT_SECONDS', 0.3)

    t0 = time.time()
    try:
        result = TestCaseConfigAclRepositoryImpl().list_testcases_by_ids(['fast', 'slow'])
    finally:
        tick.set()  # 放行后台线程，避免泄漏到后续用例

    assert 'fast' in result.items
    assert 'slow' not in result.items
    assert result.incomplete_ids == ['slow']
    assert result.partial is True
    assert time.time() - t0 < 3


def test_repeat_call_hits_cache(monkeypatch):
    """同一批 id 第二次取数不再发 gRPC（报告链路一次请求多次取数）。"""
    calls = _patch_fetch(monkeypatch, lambda tc_id: _payload(tc_id))
    repo = TestCaseConfigAclRepositoryImpl()

    first = repo.list_testcases_by_ids([101, 102])
    second = repo.list_testcases_by_ids([101, 102])

    assert set(first.items) == set(second.items) == {'101', '102'}
    assert sorted(calls) == ['101', '102']  # 只查了一轮


def test_missing_ids_are_negative_cached(monkeypatch):
    """未取到的 id 短时间内不重查（否则后续调用再吃一个整批截止）。"""
    calls = _patch_fetch(monkeypatch, lambda tc_id: None)
    repo = TestCaseConfigAclRepositoryImpl()

    first = repo.list_testcases_by_ids([101])
    second = repo.list_testcases_by_ids([101])

    assert first.items == {} and second.items == {}
    assert first.missing_ids == second.missing_ids == ['101']
    assert calls == ['101']  # 第二轮走负缓存

    # 负缓存过期后重新查询（模拟新建 / 恢复的用例）
    acl_mod._neg_cache.clear()
    repo.list_testcases_by_ids([101])
    assert calls == ['101', '101']


def test_negative_cache_can_be_disabled(monkeypatch):
    calls = _patch_fetch(monkeypatch, lambda tc_id: None)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_NEGATIVE_CACHE_TTL_SECONDS', 0)
    repo = TestCaseConfigAclRepositoryImpl()

    repo.list_testcases_by_ids([101])
    repo.list_testcases_by_ids([101])

    assert calls == ['101', '101']


def test_partial_ids_are_negative_cached_so_second_call_is_cheap(monkeypatch):
    """整批截止后，同一请求内的第二次取数不能再付一次整批截止（复测 P1）。"""
    tick = threading.Event()

    def fetch(tc_id):
        if tc_id == 'slow':
            tick.wait(5)
            return _payload(tc_id)
        return _payload(tc_id)

    _patch_fetch(monkeypatch, fetch)
    monkeypatch.setattr(Config, 'TESTCASE_ACL_LOOKUP_TOTAL_TIMEOUT_SECONDS', 0.3)
    repo = TestCaseConfigAclRepositoryImpl()

    try:
        first = repo.list_testcases_by_ids(['fast', 'slow'])
        t0 = time.time()
        second = repo.list_testcases_by_ids(['fast', 'slow'])
        elapsed = time.time() - t0
    finally:
        tick.set()

    assert first.partial is True
    assert 'fast' in second.items and 'slow' not in second.items
    assert elapsed < 1.0
    assert second.incomplete_ids == ['slow']  # 负缓存不吞掉「不完整」口径


def test_cached_payload_isolated_from_caller_mutations(monkeypatch):
    """缓存读写深拷贝：调用方原地改返回的 config 不得污染缓存。"""
    _patch_fetch(monkeypatch, lambda tc_id: _payload(tc_id))
    repo = TestCaseConfigAclRepositoryImpl()

    first = repo.list_testcases_by_ids([101])
    first.items['101'].config['rounds'].append('mutated-by-caller')

    second = repo.list_testcases_by_ids([101])
    assert second.items['101'].config == {'rounds': []}


def test_cache_can_be_disabled(monkeypatch):
    calls = _patch_fetch(monkeypatch, lambda tc_id: _payload(tc_id))
    monkeypatch.setattr(Config, 'TESTCASE_ACL_CACHE_TTL_SECONDS', 0)
    repo = TestCaseConfigAclRepositoryImpl()

    repo.list_testcases_by_ids([101])
    repo.list_testcases_by_ids([101])

    assert calls == ['101', '101']


def test_empty_input_short_circuits(monkeypatch):
    calls = _patch_fetch(monkeypatch, lambda tc_id: _payload(tc_id))

    for empty in ([], None):
        result = TestCaseConfigAclRepositoryImpl().list_testcases_by_ids(empty)
        assert result.items == {}
        assert result.missing_ids == []
        assert result.partial is False
    assert calls == []


# ==================== INT-1572 返工三轮：操作人身份 / 按用户分键缓存 ====================

def test_fetch_worker_runs_with_caller_identity(monkeypatch):
    """取数 worker 必须带着调用方身份：出站 GetTestCaseDetail 靠它带 x-user-id。

    终审 P2 复现：contextvars 不跨线程传播，worker 里 get_current_user_id() 为
    None → 下游把 PRIVATE 用例按 404 返回（owner 自己也看不到）。
    """
    seen = []
    lock = threading.Lock()

    def fetch(tc_id, timeout=None):
        with lock:
            seen.append((tc_id, get_current_user_id(), get_current_user_is_admin()))
        return _payload(tc_id)

    monkeypatch.setattr(TestCaseConfigAclRepositoryImpl, '_fetch_detail', staticmethod(fetch))
    _as_user(101, is_admin=True)

    result = TestCaseConfigAclRepositoryImpl().list_testcases_by_ids([101, 102])

    assert set(result.items) == {'101', '102'}
    assert sorted(seen) == [('101', 101, True), ('102', 101, True)]


def test_fetch_worker_identity_restored_on_pool_thread(monkeypatch):
    """worker 执行完复原身份：共享线程池线程被下一请求复用时不串号。"""
    seen = []
    lock = threading.Lock()

    def fetch(tc_id, timeout=None):
        with lock:
            seen.append(get_current_user_id())
        return _payload(tc_id)

    monkeypatch.setattr(TestCaseConfigAclRepositoryImpl, '_fetch_detail', staticmethod(fetch))
    repo = TestCaseConfigAclRepositoryImpl()

    _as_user(101)
    repo.list_testcases_by_ids([101])
    # 无身份的后台生成线程复用同一批 worker
    set_current_user_id(None)
    acl_mod.clear_caches()
    repo.list_testcases_by_ids([102])

    assert seen == [101, None]


def test_owner_sees_private_case_other_user_does_not(monkeypatch):
    """任务侧按身份过滤（owner 可见 / 非 owner 404）：ACL 如实透传，不得把
    「无权限」记成「查询未完成」，也不得把私有用例跨用户复用。"""
    calls = []

    def fetch(tc_id, timeout=None):
        calls.append((tc_id, get_current_user_id()))
        if get_current_user_id() == 1:
            return {'id': tc_id, 'name': 'private', 'visibility': 'private',
                    'config': {'rounds': []}}
        return None

    monkeypatch.setattr(TestCaseConfigAclRepositoryImpl, '_fetch_detail', staticmethod(fetch))
    repo = TestCaseConfigAclRepositoryImpl()

    _as_user(1)
    owner = repo.list_testcases_by_ids([101])
    assert set(owner.items) == {'101'}
    assert owner.items['101'].name == 'private'
    assert owner.incomplete_ids == [] and owner.partial is False

    _as_user(2)
    other = repo.list_testcases_by_ids([101])
    assert other.items == {}
    assert other.missing_ids == ['101']
    assert other.incomplete_ids == []      # 404 是「不可见」，不是「取数不完整」
    assert other.partial is False
    assert calls == [('101', 1), ('101', 2)]   # 私有载荷没有被跨用户复用


def test_shared_payload_cached_across_users(monkeypatch):
    """shared 载荷对所有查看者一致，缓存可跨用户命中（保住报告链路重复取数的收益）。"""
    calls = _patch_fetch(
        monkeypatch,
        lambda tc_id: {'id': tc_id, 'name': 'shared', 'visibility': 'shared',
                       'config': {'rounds': []}})
    repo = TestCaseConfigAclRepositoryImpl()

    _as_user(1)
    assert set(repo.list_testcases_by_ids([101]).items) == {'101'}
    _as_user(2)
    assert set(repo.list_testcases_by_ids([101]).items) == {'101'}

    assert calls == ['101']


def test_payload_without_visibility_is_not_shared_across_users(monkeypatch):
    """载荷未带 visibility（老版本服务）按私有处理：宁可少命中，不把私有用例供给他人。"""
    calls = _patch_fetch(monkeypatch, lambda tc_id: _payload(tc_id))
    repo = TestCaseConfigAclRepositoryImpl()

    _as_user(1)
    repo.list_testcases_by_ids([101])
    _as_user(2)
    repo.list_testcases_by_ids([101])

    assert calls == ['101', '101']


def test_negative_cache_is_per_identity(monkeypatch):
    """别人查不到（私有无权限）不得在负缓存期内把 owner 也挡住。"""
    calls = _patch_fetch(
        monkeypatch,
        lambda tc_id: _payload(tc_id) if get_current_user_id() == 1 else None)
    repo = TestCaseConfigAclRepositoryImpl()

    _as_user(2)
    other = repo.list_testcases_by_ids([101])
    assert other.items == {} and other.missing_ids == ['101']

    _as_user(1)
    owner = repo.list_testcases_by_ids([101])
    assert set(owner.items) == {'101'}
    assert calls == ['101', '101']


def test_payload_group_contract_feeds_real_case_type_category(monkeypatch):
    """载荷口径变化（终审要求抽验）：GetTestCaseDetail 带 group{id,name}，
    case_type_stats 的分组键由原先恒为 'default_group' 变为真实 group id。

    原 ListTestCases 列表项只有 group_id / group_name（无 group 对象），
    report_utils/metrics_mixin 取不到 group.id 一直回落 'default_group'；
    改按 ID 取详情后分类统计才真正按用例分组——属修正，非回归。
    """
    from report_service.application.services.report_utils import metrics_mixin as mm

    monkeypatch.setattr(
        mm, '_grpc_list_testcases_by_ids',
        lambda ids: {'101': {'id': '101', 'group': {'id': 7, 'name': '接口组'}, 'tags': []}})

    stats = mm.MetricsMixin.calculate_case_type_stats_optimized(
        [{'id': 1, 'test_case_id': '101'}],
        [{'id': 3, 'name': 'SNR'}],
        {1: [{'dimension_id': 3, 'dimension_value': 0.8, 'round_number': None}]},
    )

    assert set(stats) == {7}
    assert stats[7]['SNR'] == pytest.approx(0.8)
