# -*- coding: utf-8 -*-
"""自动合并测试：无 group_key 时，同 endpoint + 同 category + 同 task_type + 同 body_template
的多个 parent 分组自动并入一组只发一次请求（如拒识 3 主维度）；
不同 task_type / category / body 的组保持原分组不合并。"""

import contextlib


def _build_service(dims):
    from backend.services.evaluation.evaluation_service import EvaluationService

    service = EvaluationService.__new__(EvaluationService)
    service._log = lambda **kw: None

    built_groups = []
    service._build_task_data = lambda *a, **kw: built_groups.append(
        [item[0]['id'] for item in a[5]]) or {'groups': built_groups}
    service._get_or_create_worker = lambda endpoint_url, rep: None
    service._submit_to_endpoint_worker = lambda task_data, worker: None

    class _FakeClient:
        def __init__(self):
            self.global_lock = contextlib.nullcontext()

            class _Pool:
                _shutdown = False

                @staticmethod
                def submit(fn, *a):
                    fn(*a)

            self.thread_pool = _Pool()

    service.api_client = _FakeClient()

    service._dispatch_evaluation_tasks(
        dims, {d['id']: d['id'] * 10 for d in dims},
        result_id=1, task_id=1, test_case_id=1, algorithm_result={},
        algorithm_type='voice_llm', test_type='e2e', round_number=None,
        field_mapper=None, ref_texts={})
    return built_groups


def _dim(dim_id, name, dtype, parent_id, tc, cat, settings=None, parent_tc=None):
    d = {
        'id': dim_id, 'name': name, 'dimension_type': dtype,
        'parent_dimension_id': parent_id, 'task_type_code': tc,
        'category_id': cat, 'api_endpoints': [], 'api_url': 'http://eval:8888',
        'api_settings': settings or {},
    }
    if parent_tc:
        d['parent_task_type_code'] = parent_tc
    return d


BODY = {'model': '{{model}}', 'rounds': [{'ai_wav': '{{ai_wav}}'}]}


def test_auto_merge_reject_family_into_one_request():
    """拒识 3 主 + 子（同 category=3、同 task_type=reject_judge、同 body、无 group_key）自动合并一组"""
    settings = {'body_template': BODY}
    dims = [
        _dim(121, '拒识成功数量', 'main', None, 'reject_judge', 3, settings),
        _dim(124, '静默时拒识恢复行为数量', 'sub', 121, 'reject_judge', 3, settings, parent_tc='reject_judge'),
        _dim(122, '拒识询问数量', 'main', None, 'reject_judge', 3, settings),
        _dim(123, '拒识失败数量', 'main', None, 'reject_judge', 3, settings),
        _dim(128, '静默时拒识回应行为数量', 'sub', 123, 'reject_judge', 3, settings, parent_tc='reject_judge'),
    ]
    groups = _build_service(dims)
    assert sorted(map(sorted, groups)) == [[121, 122, 123, 124, 128]]


def test_no_merge_different_task_type_in_family():
    """同 category 但主/子 task_type 不同（如 turn_eval 靠 sub_tasks）→ 保持 parent 分组不跨组合并"""
    settings = {'body_template': BODY}
    dims = [
        _dim(72, '逐轮话轮评估', 'main', None, 'turn_eval', 1, settings),
        _dim(73, '话轮子维度', 'sub', 72, 'turn_evaluation', 1, settings, parent_tc='turn_eval'),
        # 另一个同 category=1、同 body 但 task_type 不同的主维度组 → 不能与 turn_eval 组合并
        _dim(80, '别族主维度', 'main', None, 'turn_other', 1, settings),
    ]
    groups = _build_service(dims)
    assert sorted(map(sorted, groups)) == [[72, 73], [80]]


def test_no_merge_different_category():
    """同 task_type 同 body 但 category 不同 → 不合并"""
    settings = {'body_template': BODY}
    dims = [
        _dim(121, '拒识成功数量', 'main', None, 'reject_judge', 3, settings),
        _dim(122, '同task别的分类', 'main', None, 'reject_judge', 9, settings),
    ]
    groups = _build_service(dims)
    assert sorted(map(sorted, groups)) == [[121], [122]]


def test_no_merge_different_body_template():
    """同 category 同 task_type 但 body_template 不同 → 不合并"""
    dims = [
        _dim(121, '拒识成功数量', 'main', None, 'reject_judge', 3, {'body_template': BODY}),
        _dim(122, '不同body', 'main', None, 'reject_judge', 3, {'body_template': {'a': 1}}),
    ]
    groups = _build_service(dims)
    assert sorted(map(sorted, groups)) == [[121], [122]]
