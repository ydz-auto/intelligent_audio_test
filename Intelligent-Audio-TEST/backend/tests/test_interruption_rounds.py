# -*- coding: utf-8 -*-
"""打断轮次元数据与二值成功率回归测试。"""


def test_actual_interruption_rounds_follow_marker():
    from backend.services.execution.e2e_aggregator import E2EAggregator

    metadata = E2EAggregator.build_interruption_round_metadata([
        {'is_interruption': True},
        {'is_interruption': False},
        {'is_interruption': True},
        {'is_interruption': False},
    ])
    assert metadata['interruption_rounds'] == [1, 3]
    assert metadata['dangling_interruption_rounds'] == []


def test_final_interruption_marker_is_dangling():
    from backend.services.execution.e2e_aggregator import E2EAggregator

    metadata = E2EAggregator.build_interruption_round_metadata([
        {'is_interruption': False},
        {'isInterruption': True},
    ])
    assert metadata['interruption_rounds'] == []
    assert metadata['dangling_interruption_rounds'] == [1]


def test_round_metadata_is_added_to_algorithm_result(monkeypatch):
    from backend.services.execution.e2e_aggregator import E2EAggregator
    import backend.utils.algorithm.field_mapper as fm_mod

    class _Mapper:
        def get_mapped_device_output_fields(self, algorithm_type):
            return []

    monkeypatch.setattr(fm_mod, 'get_field_mapper', lambda: _Mapper())

    class _Executor:
        @staticmethod
        def _log(**kwargs):
            pass

    result = E2EAggregator(_Executor()).build_algorithm_result(
        'task',
        [{'round_number': 0}, {'round_number': 1}],
        {'rounds': [
            {'is_interruption': True},
            {'is_interruption': False},
        ]},
        'voice_llm',
    )
    assert result['interruption_rounds'] == [1]
    assert result['rounds'][0]['is_actual_interruption'] is False


def test_evaluation_service_derives_missing_round_metadata():
    from backend.services.evaluation.evaluation_service import EvaluationService

    service = EvaluationService.__new__(EvaluationService)
    metadata = service._derive_interruption_metadata(
        {'rounds': [{'round': 0}, {'round': 1}]},
        {'rounds': [{'is_interruption': True}, {'is_interruption': False}, {'is_interruption': True}]},
    )
    assert metadata['interruption_rounds'] == [1]
    assert metadata['dangling_interruption_rounds'] == [2]


def test_evaluation_service_keeps_existing_round_metadata():
    from backend.services.evaluation.evaluation_service import EvaluationService

    service = EvaluationService.__new__(EvaluationService)
    metadata = service._derive_interruption_metadata(
        {'rounds': [{'round': 0, 'is_actual_interruption': True}]},
        {'rounds': [{'is_interruption': False}]},
    )
    assert metadata is None


def test_derive_metadata_reads_algorithm_params_col():
    """is_interruption/stop_intent 配置在 TestCase.algorithm_params 独立列时兜底也能读到。"""
    from backend.services.evaluation.evaluation_service import EvaluationService

    service = EvaluationService.__new__(EvaluationService)
    algo_col = [
        {'round_number': 1, 'params': [{'field_code': 'is_interruption', 'field_value': True}]},
        {'round_number': 2, 'params': [{'field_code': 'stop_intent', 'field_value': True}]},
    ]
    metadata = service._derive_interruption_metadata(
        {'rounds': [{'round': 0}, {'round': 1}]},
        {'rounds': [{}, {}]},
        algo_col,
    )
    assert metadata['interruption_rounds'] == [1]
    assert metadata['stop_intent'] == [False, True]
    assert metadata['stop_instruction_rounds'] == [1]


def test_group_key_merges_interruption_family_into_one_request():
    """P3 出口：api_settings.group_key 相同的打断族维度（跨主维度+子维度）合并为一组只发一次请求；
    无 group_key 的维度不受影响，仍按 parent_dimension_id 各自分组。"""
    from backend.services.evaluation.evaluation_service import EvaluationService

    service = EvaluationService.__new__(EvaluationService)
    service._log = lambda **kw: None

    family_settings = {'group_key': 'interruption_v2', 'body_template': {}}
    url = 'http://eval:8888'
    dims = [
        {'id': 57, 'name': '打断成功数量', 'dimension_type': 'main', 'parent_dimension_id': None,
         'task_type_code': 'interruption_metrics', 'api_endpoints': [], 'api_url': url,
         'api_settings': family_settings},
        {'id': 66, 'name': '停止指令遵循', 'dimension_type': 'main', 'parent_dimension_id': None,
         'task_type_code': 'interruption_metrics', 'api_endpoints': [], 'api_url': url,
         'api_settings': family_settings},
        {'id': 69, 'name': '响应时延', 'dimension_type': 'sub', 'parent_dimension_id': 68,
         'task_type_code': 'interruption_metrics', 'parent_task_type_code': 'interruption_metrics',
         'api_endpoints': [], 'api_url': url, 'api_settings': family_settings},
        {'id': 100, 'name': '其他维度', 'dimension_type': 'main', 'parent_dimension_id': None,
         'task_type_code': 'other', 'api_endpoints': [], 'api_url': url, 'api_settings': {}},
    ]

    built_groups = []
    service._build_task_data = lambda *a, **kw: built_groups.append(
        [item[0]['id'] for item in a[5]]) or {'groups': built_groups}
    service._get_or_create_worker = lambda endpoint_url, rep: None
    service._submit_to_endpoint_worker = lambda task_data, worker: None

    import contextlib

    class _FakeClient:
        def __init__(self):
            self.global_lock = contextlib.nullcontext()  # with 直接作用于实例

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

    assert sorted(map(sorted, built_groups)) == [[57, 66, 69], [100]]
