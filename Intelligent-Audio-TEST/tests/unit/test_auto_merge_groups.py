# -*- coding: utf-8 -*-
"""INT-175 守卫：维度组间自动合并——无显式分组键的多个 parent 分组，
同 endpoint + 同 category_id + 组内全部维度 (task_type_code, body_template) 完全一致时
并入一组只发一次请求、一次判定（如拒识族 3 主维度 → 三率同源一致，和=100%）；
task_type 异（主子异构族）/ body 异 / endpoint 异 / category 异 不合并。

纯单测：TaskDispatcherMixin 最小宿主 + 真实 _group_dimensions_by_endpoint +
真实合并逻辑，不触 DB/gRPC/线程池。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import contextlib

from evaluation_service.infrastructure.evaluation_api.task_dispatcher import (
    TaskDispatcherMixin,
)


BODY = {'model': '{{model}}', 'rounds': [{'ai_wav': '{{ai_wav}}'}]}
BODY_ALT = {'model': '{{model}}', 'rounds': [{'ai_wav': '{{ai_wav}}', 'x': 1}]}


def _dim(dim_id, name, dtype, parent_id, tc, cat, body=BODY, api_url='http://eval:8888',
         parent_tc=None):
    d = {
        'id': dim_id, 'name': name, 'dimension_type': dtype,
        'parent_dimension_id': parent_id, 'task_type_code': tc,
        'category_id': cat, 'api_endpoints': [], 'api_url': api_url,
        'api_settings': {'method': 'POST', 'headers': {}, 'body_template': body, 'timeout': 30000},
    }
    if parent_tc:
        d['parent_task_type_code'] = parent_tc
    return d


class _Host(TaskDispatcherMixin):
    """最小宿主：真实分组/合并/提交链，能力分流打桩为直通。"""

    def __init__(self):
        self.captured_groups = None

    def _log(self, **kwargs):
        pass

    def _split_by_eval_capability(self, dimension_data_list, task_id, test_case_id):
        return list(dimension_data_list), []


def _dispatch(dims):
    host = _Host()
    host._submit_to_workers = lambda endpoint_groups, *a, **kw: setattr(
        host, 'captured_groups',
        [[item[0]['id'] for item in items] for items in endpoint_groups.values()])
    host._dispatch_evaluation_tasks(
        dims, {d['id']: d['id'] * 10 for d in dims},
        result_id=1, task_id=1, test_case_id=1, algorithm_result={},
        algorithm_type='voice_llm', device_type='physical', round_number=None,
        field_mapper=None, ref_texts={})
    return host.captured_groups


def test_auto_merge_reject_family_into_one_request():
    """拒识族 3 主 + 子（同 category、同 task_type、同 body、同 endpoint）合并一组一次请求"""
    dims = [
        _dim(121, '拒识成功数量', 'main', None, 'reject_judge', 3),
        _dim(124, '静默时拒识恢复行为数量', 'sub', 121, 'reject_judge', 3, parent_tc='reject_judge'),
        _dim(122, '拒识询问数量', 'main', None, 'reject_judge', 3),
        _dim(123, '拒识失败数量', 'main', None, 'reject_judge', 3),
        _dim(128, '静默时拒识回应行为数量', 'sub', 123, 'reject_judge', 3, parent_tc='reject_judge'),
    ]
    groups = _dispatch(dims)
    assert sorted(map(sorted, groups)) == [[121, 122, 123, 124, 128]]


def test_no_merge_different_task_type_in_family():
    """同 category 但主/子 task_type 异构（turn_eval 靠 sub_tasks）→ 保持 parent 分组不跨组合并"""
    dims = [
        _dim(72, '逐轮话轮评估', 'main', None, 'turn_eval', 1),
        _dim(73, '话轮子维度', 'sub', 72, 'turn_evaluation', 1, parent_tc='turn_eval'),
        # 同 category=1、同 body 但 task_type 不同的另一个主维度组 → 不能与 turn_eval 组合并
        _dim(80, '别族主维度', 'main', None, 'turn_other', 1),
    ]
    groups = _dispatch(dims)
    assert sorted(map(sorted, groups)) == [[72, 73], [80]]


def test_no_merge_different_category():
    """同 task_type 同 body 但 category 不同 → 不合并"""
    dims = [
        _dim(121, '拒识成功数量', 'main', None, 'reject_judge', 3),
        _dim(122, '同task别的分类', 'main', None, 'reject_judge', 9),
    ]
    groups = _dispatch(dims)
    assert sorted(map(sorted, groups)) == [[121], [122]]


def test_no_merge_different_body_template():
    """同 category 同 task_type 但 body_template 不同 → 不合并"""
    dims = [
        _dim(121, '拒识成功数量', 'main', None, 'reject_judge', 3),
        _dim(122, '不同body', 'main', None, 'reject_judge', 3, body=BODY_ALT),
    ]
    groups = _dispatch(dims)
    assert sorted(map(sorted, groups)) == [[121], [122]]


def test_no_merge_different_endpoint():
    """同 category 同 task_type 同 body 但 endpoint 不同 → 不合并"""
    dims = [
        _dim(121, '拒识成功数量', 'main', None, 'reject_judge', 3,
             api_url='http://eval-a:8888'),
        _dim(122, '拒识询问数量', 'main', None, 'reject_judge', 3,
             api_url='http://eval-b:8888'),
    ]
    groups = _dispatch(dims)
    assert sorted(map(sorted, groups)) == [[121], [122]]


def test_merge_preserves_dimension_result_pairing():
    """合并组内各维度携带各自的 dimension_result_id（结果按 field_path 从同一份响应提取的前提）"""
    dims = [
        _dim(121, '拒识成功数量', 'main', None, 'reject_judge', 3),
        _dim(122, '拒识询问数量', 'main', None, 'reject_judge', 3),
    ]
    host = _Host()
    captured_items = []
    host._submit_to_workers = lambda endpoint_groups, *a, **kw: captured_items.extend(
        next(iter(endpoint_groups.values())))
    host._dispatch_evaluation_tasks(
        dims, {121: 1210, 122: 1220},
        result_id=1, task_id=1, test_case_id=1, algorithm_result={},
        algorithm_type='voice_llm', device_type='physical', round_number=None,
        field_mapper=None, ref_texts={})
    assert [(d['id'], rid) for d, rid in captured_items] == [(121, 1210), (122, 1220)]


class _SyncPool:
    _shutdown = False

    def submit(self, fn, *a):
        fn(*a)


class _FakeApiClient:
    """同步线程池替身：提交即执行，捕获最终任务数据。"""

    def __init__(self):
        self.global_lock = contextlib.nullcontext()
        self.thread_pool = _SyncPool()
        self.submitted = []

    def init_thread_pool(self):
        pass


def test_real_submit_chain_accepts_merged_group_key():
    """真实 _submit_to_workers 接受合并后三元组键（回归守卫：
    endpoint_url, _ = group_key 解包二元组会在合并组上崩溃），
    合并组构建一次任务数据、提交一次。"""
    dims = [
        _dim(121, '拒识成功数量', 'main', None, 'reject_judge', 3),
        _dim(124, '静默时拒识恢复行为数量', 'sub', 121, 'reject_judge', 3, parent_tc='reject_judge'),
        _dim(122, '拒识询问数量', 'main', None, 'reject_judge', 3),
    ]
    host = _Host()
    host.api_client = _FakeApiClient()
    host._get_or_create_worker = lambda endpoint_url, rep: type('W', (), {
        'put_task': staticmethod(lambda td: host.api_client.submitted.append(td))})()

    built = []
    host._build_task_data = lambda *a, **kw: built.append(a[5]) or {}

    host._dispatch_evaluation_tasks(
        dims, {d['id']: d['id'] * 10 for d in dims},
        result_id=1, task_id=1, test_case_id=1, algorithm_result={},
        algorithm_type='voice_llm', device_type='physical', round_number=None,
        field_mapper=None, ref_texts={})

    # 3 个 parent 组合并为 1 组 → 只构建/提交一次任务，组内 3 个维度
    assert len(built) == 1
    assert [item[0]['id'] for item in built[0]] == [121, 124, 122]
    assert len(host.api_client.submitted) == 1
