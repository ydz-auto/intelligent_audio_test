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
    assert result['rounds'][1]['is_actual_interruption'] is True
