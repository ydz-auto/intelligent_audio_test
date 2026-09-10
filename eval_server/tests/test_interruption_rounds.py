# -*- coding: utf-8 -*-
"""打断时序二值成功率测试。"""


def _asr_pair():
    return (
        [
            {'text': '等等', 'timestamp': [1.0, 1.4]},
            {'text': '继续问题', 'timestamp': [3.2, 3.6]},
        ],
        [
            {'text': '回答一', 'timestamp': [1.0, 1.8]},
            {'text': '恢复一', 'timestamp': [2.2, 2.8]},
            {'text': '回答二', 'timestamp': [3.0, 3.4]},
            {'text': '恢复二', 'timestamp': [4.0, 4.5]},
        ],
    )


def test_actual_interruption_round_is_binary_not_event_ratio():
    from app.services.calculators.xiaoyi_metrics.interruptibility.interruption import (
        compute_interruption_metrics,
    )

    user_asr, model_asr = _asr_pair()
    result = compute_interruption_metrics(
        user_asr, model_asr, actual_interruption=True,
    )
    assert result['n_events'] == 2
    assert result['interruption_success_rate'] in (0, 1)
    assert len(result['per_event']) == 2


def test_non_actual_round_does_not_count_as_success():
    from app.services.calculators.xiaoyi_metrics.interruptibility.interruption import (
        compute_interruption_metrics,
    )

    user_asr, model_asr = _asr_pair()
    result = compute_interruption_metrics(
        user_asr, model_asr, actual_interruption=False,
    )
    assert result['interruption_success_rate'] == 0


def test_failure_rate_is_binary_for_single_round_events():
    from app.services.calculators.xiaoyi_metrics.interruptibility.interruption import (
        compute_interruption_metrics,
    )

    result = compute_interruption_metrics(
        [{'text': '等', 'timestamp': [1.0, 1.4]}],
        [{'text': '回答', 'timestamp': [1.0, 2.0]}],
        actual_interruption=True,
    )
    assert result['interruption_success_rate'] == 0
    assert result['interruption_failure_rate'] == 1.0


def test_stop_intent_is_not_inferred_from_interruption():
    from app.services.calculators.xiaoyi_metrics.interruptibility.interruption import (
        compute_interruption_metrics,
    )

    result = compute_interruption_metrics(*_asr_pair(), actual_interruption=True)
    assert result['stop_instruction_compliance_rate'] is None
    assert all(not event['stop_intent'] for event in result['per_event'])
