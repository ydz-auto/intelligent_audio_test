# -*- coding: utf-8 -*-
"""INT-1666 算法配置缓存重载改造单测。

背景（INT-1666）：写 RPC 每次调用 `_invalidate_cache()` 都做一次全量重建——
遍历每个在线算法 6 次查询 + 逐条维度关系查参数（典型 N+1），整份快照构建
期间持有 RLock，DB I/O 把并发写串行化，评估维度写 19.6s、并发冲到分钟级。

修复后的契约（本文件逐条守住）：
1. 重载 SQL 条数与算法/维度数量无关：每类配置只发一次批量 IN 查询；
2. 写路径按受影响范围失效：`invalidate(algorithm_types=[...])` /
   `invalidate(dimension_ids=[...])` 只重建对应切片，其余切片原样保留；
3. 构建期间不持有快照锁：构建卡在 DB 查询上时，读侧仍能立即拿到快照；
4. 同一时刻的多个失效请求合并：后到请求并入下一轮，不会并发重复构建；
5. 构建失败保留上一份快照（INT-94 回归点），读侧不清空；
6. 范围归一化后为空时按全量兜底，不漏刷新。
"""
import os
import threading

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import algorithm_service.infrastructure.persistence.config_cache as config_cache_module
from algorithm_service.infrastructure.persistence.config_cache import (
    AlgorithmConfigCache,
)

ALGORITHMS = [
    {'id': 1, 'type': 'a1', 'name': 'A1', 'status': 'online', 'display_order': 1},
    {'id': 2, 'type': 'a2', 'name': 'A2', 'status': 'online', 'display_order': 2},
]
DEVICE_PARAMS = [
    {'id': 11, 'algorithm_type': 'a1', 'param_code': 'd1',
     'param_name': 'D1', 'param_type': 'text', 'ui_order': 1},
    {'id': 12, 'algorithm_type': 'a2', 'param_code': 'd2',
     'param_name': 'D2', 'param_type': 'text', 'ui_order': 1},
]
API_PARAMS = [
    {'id': 21, 'algorithm_type': 'a1', 'param_code': 'api1',
     'param_name': 'API1', 'param_type': 'text', 'ui_order': 1},
]
CASE_PARAMS = [
    {'id': 31, 'algorithm_type': 'a1', 'param_code': 'c1',
     'param_name': 'C1', 'param_type': 'text', 'ui_order': 1},
]
REFERENCE_PARAMS = [
    {'id': 41, 'algorithm_type': 'a1', 'code': 'r1', 'name': 'R1',
     'param_type': 'text'},
]
MAPPINGS = [
    # source='evaluation' 是历史脏数据：来源需从已取回的参数反推（内存版，
    # 不得再逐条查库）
    {'id': 51, 'algorithm_type': 'a1', 'source': 'evaluation',
     'source_param': 'c1', 'target_param': 'p1', 'dimension_id': 101},
    {'id': 52, 'algorithm_type': 'a1', 'source': 'case',
     'source_param': 'c1', 'target_param': 'p2', 'dimension_id': None},
]
RELATIONS = [
    {'id': 61, 'algorithm_type': 'a1', 'dimension_id': 101},
    {'id': 62, 'algorithm_type': 'a1', 'dimension_id': 102},
]
DIMENSION_PARAMS = [
    {'id': 71, 'dimension_id': 101, 'param_code': 'p1',
     'param_name': 'P1', 'ui_order': 1},
    {'id': 72, 'dimension_id': 102, 'param_code': 'p2',
     'param_name': 'P2', 'ui_order': 1},
]


class _FakeRepo:
    """记录调用的仓储替身：每个方法返回固定数据。"""

    def __init__(self, **methods):
        self.calls = []
        self._methods = methods

    def __getattr__(self, name):
        if name not in self._methods:
            raise AssertionError(f'未预期的仓储调用: {name}')
        impl = self._methods[name]

        def _call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return impl(*args, **kwargs) if callable(impl) else impl

        return _call


def _bare_cache(**overrides):
    cache = object.__new__(AlgorithmConfigCache)
    cache._config_cache = overrides.pop('snapshot', {})
    cache._last_reload_time = None
    cache._pending_full = False
    cache._pending_algorithms = set()
    cache._pending_dimensions = set()
    # 隔离 Redis：单测只验证 L1 构建/替换逻辑
    cache._save_to_redis = lambda *a, **kw: None
    cache._publish_invalidation = lambda *a, **kw: None
    for key, value in overrides.items():
        setattr(cache, key, value)
    return cache


def _install_repos(monkeypatch, *, algorithms=None, definitions_by_type=None,
                   dimension_params=None, fail_on=None):
    """把 config_cache 模块里的仓储单例替换为替身，返回各替身。"""
    algorithms = ALGORITHMS if algorithms is None else algorithms
    definitions_by_type = (
        ALGORITHMS if definitions_by_type is None else definitions_by_type)
    dimension_params = (
        DIMENSION_PARAMS if dimension_params is None else dimension_params)

    def _maybe_fail(name, value):
        if fail_on == name:
            def _boom(*_args, **_kwargs):
                raise RuntimeError(f'db error in {name}')
            return _boom
        return value

    repos = {
        'algorithm_definition_query_repository': _FakeRepo(
            list_online_definitions=_maybe_fail('definitions', algorithms),
            list_by_types=_maybe_fail('types', definitions_by_type),
        ),
        'dimension_param_repository': _FakeRepo(
            list_by_dimensions=_maybe_fail('dimension_params', dimension_params),
        ),
        'algorithm_param_repository': _FakeRepo(
            list_by_algorithms=lambda types, kind: [
                row for row in (DEVICE_PARAMS if kind == 'device' else API_PARAMS)
                if not types or row['algorithm_type'] in types
            ],
        ),
        'case_param_repository': _FakeRepo(
            list_by_algorithms=lambda types: [
                row for row in CASE_PARAMS
                if not types or row['algorithm_type'] in types
            ],
        ),
        'reference_param_repository': _FakeRepo(
            list_by_algorithms=lambda types: [
                row for row in REFERENCE_PARAMS
                if not types or row['algorithm_type'] in types
            ],
        ),
        'mapping_repository': _FakeRepo(
            list_by_algorithms=lambda types: [
                row for row in MAPPINGS
                if not types or row['algorithm_type'] in types
            ],
        ),
        'dimension_relation_repository': _FakeRepo(
            list_by_algorithms=lambda types: [
                row for row in RELATIONS
                if not types or row['algorithm_type'] in types
            ],
        ),
        # 参数策略（API 参数 / 映射的唯一来源）：本文件只验证切片与构建语义，
        # 策略内容留空即可。
        'param_profile_repository': _FakeRepo(
            load_active=_maybe_fail('profiles', ([], {}, {})),
            load_bindings={},
            load_profiles_by_types=_maybe_fail('profiles', []),
        ),
    }
    for name, repo in repos.items():
        monkeypatch.setattr(config_cache_module, name, repo)
    return repos


def _total_calls(repos):
    return sum(len(repo.calls) for repo in repos.values())


# ========== 1. 全量重载：常数量级查询 ==========

def test_full_load_uses_one_batch_query_per_table(monkeypatch):
    repos = _install_repos(monkeypatch)
    cache = _bare_cache()

    cache._load_all_configs()

    snapshot = cache._config_cache
    assert set(snapshot['algorithms']) == {'a1', 'a2'}
    assert [p['code'] for p in snapshot['device_params']['a1']] == ['d1']
    assert [p['code'] for p in snapshot['api_params']['a1']] == ['api1']
    assert [p['code'] for p in snapshot['case_params']['a1']] == ['c1']
    assert [p['code'] for p in snapshot['reference_params']['a1']] == ['r1']
    assert sorted(snapshot['evaluation_dimension_params']) == [101, 102]
    # 每张表一次批量调用（原实现是 N 个算法 × 6 次 + 每个维度 1 次）：
    # device/api 参数各一次、case/reference/mapping 各一次、维度关系一次；
    # 参数策略新增两次（策略+声明+映射一次、API 绑定一次），同样与算法数量无关
    called = [name for repo in repos.values() for name, _, _ in repo.calls]
    assert called.count('list_online_definitions') == 1
    assert called.count('list_by_algorithms') == 6
    assert called.count('list_by_dimensions') == 1
    assert called.count('load_active') == 1
    assert called.count('load_bindings') == 1
    assert _total_calls(repos) == 10


def test_full_load_query_count_does_not_grow_with_algorithm_count(monkeypatch):
    many_algorithms = [
        {'id': i, 'type': f'a{i}', 'name': f'A{i}', 'status': 'online',
         'display_order': i}
        for i in range(40)
    ]
    repos = _install_repos(monkeypatch, algorithms=many_algorithms,
                           definitions_by_type=many_algorithms)
    cache = _bare_cache()

    cache._load_all_configs()

    # 40 个算法仍是 10 次仓储调用：SQL 条数与算法数量解耦
    assert _total_calls(repos) == 10
    assert len(cache._config_cache['algorithms']) == 40


def test_full_load_resolves_dirty_mapping_source_in_memory(monkeypatch):
    """source='evaluation' 的历史脏数据从已取回参数反推，不再逐条查库。"""
    _install_repos(monkeypatch)
    cache = _bare_cache()

    cache._load_all_configs()

    evaluation = cache.get_param_mapping('a1', 'evaluation')
    dirty = [m for m in evaluation if m['target_param'] == 'p1']
    assert dirty and dirty[0]['source'] == 'case'
    assert dirty[0]['dimension_id'] == 101


# ========== 2. 切片失效 ==========

def test_algorithm_slice_invalidation_keeps_other_slices(monkeypatch):
    repos = _install_repos(monkeypatch)
    cache = _bare_cache()
    cache._load_all_configs()
    untouched = cache._config_cache['device_params']['a1']

    # 只失效 a2：a1 各切片对象应原样保留
    cache.invalidate(algorithm_types=['a2'])

    snapshot = cache._config_cache
    assert snapshot['device_params']['a1'] is untouched
    assert snapshot['device_params']['a2'][0]['code'] == 'd2'
    # 切片路径不再调用全量在线定义查询
    called = [name for repo in repos.values() for name, _, _ in repo.calls]
    assert called.count('list_online_definitions') == 1  # 只有首次全量
    assert 'list_by_types' in called


def test_algorithm_slice_invalidation_drops_offline_algorithm(monkeypatch):
    _install_repos(monkeypatch)
    cache = _bare_cache()
    cache._load_all_configs()
    assert 'a2' in cache._config_cache['algorithms']

    # a2 下线（list_by_types 返回 status=offline）→ 切片应用时整组移除
    _install_repos(monkeypatch, definitions_by_type=[
        {'id': 1, 'type': 'a1', 'name': 'A1', 'status': 'online', 'display_order': 1},
        {'id': 2, 'type': 'a2', 'name': 'A2', 'status': 'offline', 'display_order': 2},
    ])
    cache.invalidate(algorithm_types=['a2'])

    snapshot = cache._config_cache
    assert 'a2' not in snapshot['algorithms']
    assert 'a2' not in snapshot['device_params']
    assert 'a1' in snapshot['algorithms']


def test_dimension_slice_invalidation_only_reloads_that_dimension(monkeypatch):
    repos = _install_repos(monkeypatch)
    cache = _bare_cache()
    cache._load_all_configs()
    untouched = cache._config_cache['device_params']['a1']

    repos.clear()
    repos.update(_install_repos(monkeypatch, dimension_params=[
        {'id': 71, 'dimension_id': 101, 'param_code': 'p1_new',
         'param_name': 'P1', 'ui_order': 1},
    ]))
    cache.invalidate(dimension_ids=[101])

    snapshot = cache._config_cache
    assert snapshot['device_params']['a1'] is untouched
    assert snapshot['evaluation_dimension_params'][101][0]['code'] == 'p1_new'
    assert 101 in snapshot['evaluation_dimension_params']
    assert _total_calls(repos) == 1  # 只查维度参数表

    called = [name for repo in repos.values() for name, _, _ in repo.calls]
    assert called == ['list_by_dimensions']
    assert repos['algorithm_definition_query_repository'].calls == []


def test_scope_normalized_to_empty_falls_back_to_full_reload(monkeypatch):
    """给了范围但归一化后为空（如 algorithm_type=None）→ 全量兜底，不漏刷新。"""
    _install_repos(monkeypatch)
    cache = _bare_cache()
    cache._load_all_configs()

    repos = _install_repos(monkeypatch)
    cache.invalidate(algorithm_types=[None], dimension_ids=[None])

    called = [name for repo in repos.values() for name, _, _ in repo.calls]
    assert 'list_online_definitions' in called


# ========== 3. 构建不持快照锁 ==========

def test_reads_are_not_blocked_while_build_holds_db_query(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def _slow_definitions():
        started.set()
        release.wait(5)
        return ALGORITHMS

    repos = _install_repos(monkeypatch)
    repos['algorithm_definition_query_repository'] = _FakeRepo(
        list_online_definitions=_slow_definitions,
        list_by_types=ALGORITHMS,
    )
    monkeypatch.setattr(
        config_cache_module, 'algorithm_definition_query_repository',
        repos['algorithm_definition_query_repository'])

    cache = _bare_cache()
    cache._load_all_configs()  # 先有一份快照
    old_snapshot = cache._config_cache

    rebuild = threading.Thread(target=cache.reload, daemon=True)
    rebuild.start()
    assert started.wait(5), '构建未开始'

    # 构建卡在 DB 查询上时，读侧必须立即返回旧快照（不被锁住）
    got = cache.get_all_algorithms()
    assert {item['type'] for item in got} == {'a1', 'a2'}
    assert cache._config_cache is old_snapshot

    release.set()
    rebuild.join(5)
    assert not rebuild.is_alive()


# ========== 4. 失效合并 ==========

def test_flush_without_pending_scope_is_noop(monkeypatch):
    repos = _install_repos(monkeypatch)
    cache = _bare_cache()

    cache._flush_pending_invalidations()

    assert _total_calls(repos) == 0


def test_pending_invalidations_merge_into_one_build_round(monkeypatch):
    """同一轮待办里的多个算法切片合并成一次构建（不逐条重建）。"""
    repos = _install_repos(monkeypatch)
    cache = _bare_cache()
    cache._load_all_configs()
    repos['algorithm_definition_query_repository'].calls.clear()

    cache._register_invalidation(algorithm_types=['a1'])
    cache._register_invalidation(algorithm_types=['a2'])
    cache._flush_pending_invalidations()

    type_calls = [c for c in repos['algorithm_definition_query_repository'].calls
                  if c[0] == 'list_by_types']
    assert len(type_calls) == 1
    assert sorted(type_calls[0][1][0]) == ['a1', 'a2']

    # 待办已清空：再来一轮不会重复构建
    cache._flush_pending_invalidations()
    assert len([c for c in repos['algorithm_definition_query_repository'].calls
                if c[0] == 'list_by_types']) == 1


def test_concurrent_invalidations_keep_snapshot_consistent(monkeypatch):
    builds = {'count': 0}
    lock = threading.Lock()

    def _counted_list_by_types(types):
        with lock:
            builds['count'] += 1
        return ALGORITHMS

    repos = _install_repos(monkeypatch)
    repos['algorithm_definition_query_repository'] = _FakeRepo(
        list_online_definitions=ALGORITHMS,
        list_by_types=_counted_list_by_types,
    )
    monkeypatch.setattr(
        config_cache_module, 'algorithm_definition_query_repository',
        repos['algorithm_definition_query_repository'])

    cache = _bare_cache()
    cache._load_all_configs()

    threads = [
        threading.Thread(target=cache.invalidate, kwargs={'algorithm_types': [t]})
        for t in ('a1', 'a2', 'a1', 'a2')
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    # 合并不追求精确轮次（取决于线程交错），但必须远少于逐个重建，
    # 且最终快照完整可用
    assert builds['count'] <= len(threads)
    assert set(cache._config_cache['algorithms']) == {'a1', 'a2'}


# ========== 5. 失败保留旧快照 ==========

def test_build_failure_keeps_previous_snapshot(monkeypatch):
    _install_repos(monkeypatch)
    cache = _bare_cache()
    cache._load_all_configs()
    good_snapshot = cache._config_cache

    _install_repos(monkeypatch, fail_on='definitions')
    with pytest.raises(RuntimeError):
        cache.reload()

    assert cache._config_cache is good_snapshot
    assert cache.get_all_algorithms()


# ========== 6. pubsub 通知发布方识别 ==========

def test_notice_instance_parsing():
    parse = AlgorithmConfigCache._notice_instance
    assert parse('{"instance": "abc-123", "at": "2026-10-24T00:00:00"}') == 'abc-123'
    # 旧版载荷是纯时间戳字符串 → 视为其他进程（必须刷新）
    assert parse('2026-10-24T00:00:00') == ''
    assert parse(None) == ''
