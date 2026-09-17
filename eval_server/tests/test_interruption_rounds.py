# -*- coding: utf-8 -*-
"""打断本地时序指标测试（interruption_metrics 不再调用 LLM）。"""


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


def _full_round_pair(model_recovered=True):
    """一轮完整对话：用户提问 → 模型回答 → 用户打断 → 模型（可选）恢复。"""
    user = [
        {'text': '初始问题', 'timestamp': [1.0, 1.8]},
        {'text': '等等', 'timestamp': [3.6, 4.0]},
    ]
    model = [{'text': '回答中', 'timestamp': [2.5, 3.8]}]
    if model_recovered:
        model.append({'text': '恢复回复', 'timestamp': [4.8, 5.4]})
    return user, model


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
    assert result['timing_success_rate'] == 0


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
    assert result['stop_intent'] is False
    assert all(not event['stop_intent'] for event in result['per_event'])


def test_metrics_result_carries_no_llm_or_behavior_keys():
    from app.services.calculators.xiaoyi_metrics.interruptibility import (
        calculate_interruption_metrics,
    )

    user_asr, model_asr = _full_round_pair(True)
    result = calculate_interruption_metrics({
        'user_asr': user_asr,
        'model_asr': model_asr,
        'is_actual_interruption': True,
        'interruption_rounds': [0],
        'round_number': 0,
    })
    for key in (
        'llm_eval', 'llm_success_rate', 'llm_recovery_per_round', 'behavior_judge',
        'behavior_uncertain', 'interaction_text', 'evaluations',
        'interruption_inquiry_rate', 'first_recovery_overall',
        'stop_instruction_compliance_rate',
    ):
        assert key not in result
    assert result['round_latencies'][0]['round'] == 0
    assert result['first_recovery_latency_s'] is not None


def test_marker_rounds_derive_next_round_as_actual():
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
        InterruptionMetricsCalculator,
    )

    user, model_ok = _full_round_pair(True)
    _, model_fail = _full_round_pair(False)
    task_params = {
        'rounds': [
            {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
            {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
            {'user_asr': user, 'model_asr': model_fail},
        ],
    }
    result = InterruptionMetricsCalculator().run(task_params)['interruption']
    assert result['interruption_rounds'] == [1, 2]
    assert result['is_actual_interruption'] is True
    # 多轮：任一轮失败即整例失败，失败率与成功率二值互补
    assert result['interruption_success_rate'] == 0
    assert result['interruption_failure_rate'] == 1.0


def test_dangling_marker_is_not_actual_round():
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
        InterruptionMetricsCalculator,
    )

    user, model_ok = _full_round_pair(True)
    task_params = {
        'rounds': [
            {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
            {'user_asr': user, 'model_asr': model_ok},
            {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
        ],
    }
    result = InterruptionMetricsCalculator().run(task_params)['interruption']
    assert result['interruption_rounds'] == [1]
    assert result['dangling_interruption_rounds'] == [2]
    assert result['interruption_success_rate'] == 1
    assert result['interruption_failure_rate'] == 0.0
    # 成功率与失败率恒互补
    assert result['interruption_success_rate'] + result['interruption_failure_rate'] == 1.0


def test_round_latencies_are_returned_per_round():
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
        InterruptionMetricsCalculator,
    )

    user, model_ok = _full_round_pair(True)
    task_params = {
        'rounds': [
            {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
            {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
            {'user_asr': user, 'model_asr': model_ok},
        ],
    }
    result = InterruptionMetricsCalculator().run(task_params)['interruption']
    assert [item['round'] for item in result['round_latencies']] == [1, 2]
    assert all(item['recovery_latency_s'] is not None for item in result['round_latencies'])
    assert result['avg_recovery_latency_s'] is not None
    # 恢复首轮时延只取最后一个有效实际打断轮
    assert result['round_latencies'][0]['first_recovery_latency_s'] is None
    assert result['round_latencies'][1]['first_recovery_latency_s'] is not None
    assert result['first_recovery_latency_s'] == result['round_latencies'][1]['first_recovery_latency_s']


def test_single_round_request_only_scores_last_actual_round():
    from app.services.calculators.xiaoyi_metrics.interruptibility import (
        calculate_interruption_metrics,
    )

    user, model_ok = _full_round_pair(True)
    base = {
        'user_asr': user,
        'model_asr': model_ok,
        'is_actual_interruption': True,
        'interruption_rounds': [1, 3],
    }
    earlier = calculate_interruption_metrics(dict(base, round_number=1))
    assert earlier['first_recovery_latency_s'] is None
    assert earlier['round_latencies'][0]['round'] == 1

    last = calculate_interruption_metrics(dict(base, round_number=3))
    assert last['first_recovery_latency_s'] is not None
    assert last['round_latencies'][0]['round'] == 3


def test_platform_sliced_round_payload_keeps_actual_round_semantics():
    """平台逐轮评估的真实形态：rounds 被切成一片、round_number/interruption_rounds
    是用例级索引，且经 multipart 上传后都是字符串。"""
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
        InterruptionMetricsCalculator,
    )

    user, model_ok = _full_round_pair(True)
    task_params = {
        'user_asr': user,
        'model_asr': model_ok,
        'round_number': '1',
        'interruption_rounds': '[1]',
        'rounds': [{
            'user_asr': '', 'model_asr': '',
            'is_interruption': False, 'is_actual_interruption': True,
            'stop_intent': False,
        }],
    }
    result = InterruptionMetricsCalculator().run(task_params)['interruption']
    assert result['is_actual_interruption'] is True
    assert result['interruption_success_rate'] == 1
    assert result['interruption_failure_rate'] == 0.0
    assert result['round_latencies'][0]['round'] == 1
    assert result['first_recovery_latency_s'] is not None


def test_target_event_is_max_overlap_not_first_event():
    """短插话（反馈词）重叠小，不应成为本轮代表事件；均值仍覆盖全部事件。"""
    from app.services.calculators.xiaoyi_metrics.interruptibility import (
        calculate_interruption_metrics,
    )

    user_asr = [
        {'text': '帮我列一下明天的代办事项', 'timestamp': [4.76, 6.96]},   # 首轮提问（开场白过滤基准）
        {'text': '你们', 'timestamp': [11.03, 11.46]},                 # 重叠 430ms
        {'text': '哦对了还要加上下午去银行办卡', 'timestamp': [16.73, 21.0]},  # 重叠 1840ms
    ]
    model_asr = [
        {'text': '明天青浦是小雨天气', 'timestamp': [11.02, 18.57]},
        {'text': '那可以这样安排', 'timestamp': [23.17, 41.44]},
    ]
    result = calculate_interruption_metrics({
        'user_asr': user_asr,
        'model_asr': model_asr,
        'is_actual_interruption': True,
        'interruption_rounds': [0],
        'round_number': 0,
    })

    assert result['n_events'] == 2
    # 目标事件 = 重叠最大的真正打断
    assert result['target_stop_latency_s'] == 1840.0
    assert result['target_recovery_latency_s'] == 2170.0
    assert result['first_recovery_latency_s'] == 2170.0
    # 维度值仍是全部事件的平均
    assert result['avg_stop_latency_s'] == 4690.0
    assert result['avg_recovery_latency_s'] == 6940.0
    entry = result['round_latencies'][0]
    assert entry['target_recovery_latency_s'] == 2170.0
    assert entry['recovery_latency_s'] == 6940.0


def test_multipart_string_metadata_is_coerced():
    """create_task_upload 后标量全是字符串：round_number='1'、interruption_rounds='[1]'。"""
    from app.services.calculators.xiaoyi_metrics.interruptibility import (
        calculate_interruption_metrics,
    )

    user, model_ok = _full_round_pair(True)
    result = calculate_interruption_metrics({
        'user_asr': user,
        'model_asr': model_ok,
        'is_actual_interruption': 'true',
        'round_number': '1',
        'interruption_rounds': '[1]',
        'stop_intent': 'false',
    })
    assert result['interruption_success_rate'] == 1
    assert result['round_latencies'][0]['round'] == 1
    assert result['first_recovery_latency_s'] is not None


def test_multi_round_payload_carries_v2_spec_fields():
    """v2 spec 字段：用例类型推导 + 逐轮时序锚定 + 行为未合流时的降级路径。"""
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
        InterruptionMetricsCalculator,
    )

    user, model_ok = _full_round_pair(True)
    task_params = {
        'rounds': [
            {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
            {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
            {'user_asr': user, 'model_asr': model_ok},
        ],
    }
    result = InterruptionMetricsCalculator().run(task_params)['interruption']
    assert result['case_type'] == 'multi'
    assert result['case_type_label'] == '多次打断'
    assert [t['round'] for t in result['round_timing']] == [1, 2]
    assert all(t['response_latency_ms'] is not None for t in result['round_timing'])
    # 行为未合流（LLM 逐轮判定 P2 接入）→ 降级：数量/评分 None、list 全 -1、avg None
    assert result['success_count'] is None and result['failure_count'] is None
    assert result['round_response_latencies'] == [-1, -1]
    assert result['response_latency_avg_ms'] is None
    # 恢复首轮内容时延回退 = 末个实际打断轮的回复时延
    assert result['resume_first_reply_latency_ms'] == result['round_timing'][-1]['reply_latency_ms']
    # 旧字段保持不变
    assert result['interruption_success_rate'] == 1
    assert result['first_recovery_latency_s'] is not None


def test_case_type_stop_resume_single():
    """停止指令 + 恢复前文轮 → stop_resume_single；恢复轮独立锚定回复时延。"""
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
        InterruptionMetricsCalculator,
    )

    user, model_ok = _full_round_pair(True)
    task_params = {
        'rounds': [
            {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
            {'stop_intent': True, 'user_asr': user, 'model_asr': model_ok},
            {'is_return_to_topic': True, 'user_asr': user, 'model_asr': model_ok},
        ],
    }
    result = InterruptionMetricsCalculator().run(task_params)['interruption']
    assert result['case_type'] == 'stop_resume_single'
    assert result['case_type_label'] == '停止指令后恢复前文-一次打断一次恢复'
    # 行为未合流 → 停止遵从 None（P2 由 LLM 逐停止轮判定）
    assert result['stop_compliance_rate'] is None
    # 恢复轮（round 2）独立锚定出 reply 时延
    resume = [t for t in result['round_timing'] if t.get('role') == 'resume']
    assert len(resume) == 1 and resume[0]['round'] == 2
    assert result['resume_first_reply_latency_ms'] == resume[0]['reply_latency_ms']
