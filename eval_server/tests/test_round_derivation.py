# -*- coding: utf-8 -*-
"""打断指标 v2 派生层测试：7 类用例类型推导 + spec 字段派生（纯函数，无 LLM/无 IO）。"""


def _t(r, resp, reply, stop=False, role='interruption'):
    return {'round': r, 'role': role, 'u_s': 1.0, 'u_e': 2.0, 'anchor_method': 'fft',
            'response_latency_ms': resp, 'reply_latency_ms': reply, 'stop_intent': stop}


# ─────────── §3.1 用例类型推导（7 类） ───────────

def test_seven_case_types():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        derive_case_type,
    )

    cases = [
        # (rounds, actual, dangling, stop兜底, 期望类型)
        ([{}, {'is_actual_interruption': True}, {}], [1], [], None, 'single'),
        ([{}, {'is_actual_interruption': True, 'stop_intent': 'true'}, {}], [1], [], None, 'single_stop'),
        ([{}, {'is_actual_interruption': True}, {}, {'is_actual_interruption': True}, {}],
         [1, 3], [], None, 'multi'),
        ([{}, {'is_actual_interruption': True, 'stop_intent': True}, {'is_return_to_topic': True}],
         [1], [], None, 'stop_resume_single'),
        ([{}, {'is_actual_interruption': True, 'stop_intent': True},
          {'is_actual_interruption': True}, {'is_return_to_topic': True}],
         [1, 2], [], None, 'stop_resume_multi'),
        ([{}, {'is_actual_interruption': True}, {'is_return_to_topic': True}],
         [1], [], None, 'topic_resume_single'),
        ([{}, {'is_actual_interruption': True}, {'is_actual_interruption': True},
          {'is_return_to_topic': True}],
         [1, 2], [], None, 'topic_resume_multi'),
    ]
    for rounds, actual, dangling, stop_fb, expected in cases:
        info = derive_case_type(rounds, actual, dangling, stop_intent=stop_fb)
        assert info['case_type'] == expected, f"{expected} != {info}"
        assert info['case_type_label']
    # 停止类 gate
    assert derive_case_type([{}, {'stop_intent': True}], [1], [])['is_stop_type'] is True
    assert derive_case_type([{}, {}], [1], [])['is_stop_type'] is False


def test_dangling_and_resume_rounds_excluded_from_n():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        derive_case_type,
    )

    # dangling 末轮标记不计入 n
    info = derive_case_type(
        [{}, {'is_actual_interruption': True}, {}, {'is_interruption': True}],
        [1], [3])
    assert info['case_type'] == 'single' and info['n_actual'] == 1
    # 恢复轮即使误标为实际打断轮也不入 n
    info = derive_case_type(
        [{}, {'is_actual_interruption': True}, {'is_actual_interruption': True, 'is_return_to_topic': True}],
        [1, 2], [])
    assert info['case_type'] == 'topic_resume_single' and info['n_actual'] == 1
    # 无有效实际轮 → 类型未知
    info = derive_case_type([{'is_interruption': True}], [], [0])
    assert info['case_type'] is None


def test_stop_intent_list_fallback():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        derive_case_type,
    )

    # 轮内无标记时用用例级 stop_intent 列表兜底（按轮索引取值）
    info = derive_case_type([{}, {}, {}], [1], [], stop_intent=[False, 'true', False])
    assert info['case_type'] == 'single_stop'
    info = derive_case_type([{}, {}, {}], [1], [], stop_intent='false')
    assert info['case_type'] == 'single'


# ─────────── §3.2 时序锚定 ───────────

def test_latency_window_no_stopped_gating():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        round_latency_from_window,
    )

    segs = [{'start': 1.0, 'end': 3.0}, {'start': 4.0, 'end': 5.0}]
    resp, reply = round_latency_from_window(2.0, 2.5, segs)
    assert resp == 1000.0 and reply == 1500.0  # m_e−u_s=3.0−2.0；mn_s−u_e=4.0−2.5
    # u_s 时刻无活跃模型段 → 响应时延 None（旧口径会 gate，v2 不做）
    resp, reply = round_latency_from_window(3.5, 3.8, segs)
    assert resp is None and reply == 200.0


def test_extract_prefers_fft_window():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        extract_round_timing,
    )

    rr = {'client_out_start_ms': 2000.0, 'client_out_end_ms': 2500.0,
          'model_segments': [{'start': 1.0, 'end': 3.0}, {'start': 4.0, 'end': 5.0}],
          'user_segments': [{'start': 1.9, 'end': 2.6}], 'stop_intent': True}
    t = extract_round_timing(rr, {}, 1)
    assert t['anchor_method'] == 'fft'
    assert (t['u_s'], t['u_e']) == (2.0, 2.5)
    assert t['response_latency_ms'] == 1000.0 and t['reply_latency_ms'] == 1500.0
    assert t['stop_intent'] is True


def test_extract_driver_window_then_heuristic():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        extract_round_timing,
    )

    rr = {'user_segments': [{'start': 5.0, 'end': 6.0}, {'start': 20.0, 'end': 21.0}],
          'model_segments': [{'start': 4.0, 'end': 5.5}, {'start': 8.0, 'end': 9.0}],
          'per_event': []}
    t = extract_round_timing(rr, {'start_ms': '4500', 'end_ms': '7000'}, 2)
    assert t['anchor_method'] == 'driver_window'
    assert (t['u_s'], t['u_e']) == (5.0, 6.0)
    assert t['response_latency_ms'] == 500.0 and t['reply_latency_ms'] == 2000.0

    rr2 = {'user_segments': [], 'model_segments': [], 'per_event': [
        {'event_type': 'interruption', 'overlap_s': 900.0, 'user_segment': [1.0, 2.0]}]}
    t2 = extract_round_timing(rr2, {}, 0)
    assert t2['anchor_method'] == 'overlap_heuristic'
    assert (t2['u_s'], t2['u_e']) == (1.0, 2.0)
    assert t2['response_latency_ms'] is None

    # 恢复轮无事件时取首个用户段
    rr3 = {'user_segments': [{'start': 0.5, 'end': 1.5}],
           'model_segments': [{'start': 2.0, 'end': 3.0}], 'per_event': []}
    t3 = extract_round_timing(rr3, {}, 4, role='resume')
    assert t3['anchor_method'] == 'first_user_segment'
    assert t3['reply_latency_ms'] == 500.0


# ─────────── §3.4 spec 字段派生 ───────────

def test_counts_lists_and_scores():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        derive_round_metrics,
    )

    timing = [_t(1, 300.0, 800.0), _t(2, 250.0, 700.0), _t(3, 400.0, 900.0, stop=True)]
    behaviors = [
        {'round': 1, 'behavior': '回复', 'score_overall': 4.5},
        {'round': 2, 'behavior': '静默'},                       # 失败 → list 记 -1
        {'round': 3, 'behavior': '询问', 'stop_complied': True},  # 询问轮时延照记不 -1
    ]
    m = derive_round_metrics(timing, behaviors, {'is_stop_type': True})
    assert m['success_count'] == 1 and m['reply_behavior_count'] == 1
    assert m['failure_count'] == 1 and m['silence_behavior_count'] == 1
    assert m['recover_behavior_count'] == 0 and m['irrelevant_behavior_count'] == 0
    assert m['inquiry_count'] == 1 and m['ask_behavior_count'] == 1
    assert m['round_response_latencies'] == [300.0, -1, 400.0]
    assert m['round_reply_latencies'] == [800.0, -1, 900.0]
    assert m['response_latency_avg_ms'] == 350.0
    assert m['response_latency_min_ms'] == 300.0 and m['response_latency_max_ms'] == 400.0
    assert m['reply_latency_avg_ms'] == 850.0  # avg/min/max 排除 -1
    assert m['reply_content_score'] == 4.5
    assert m['stop_compliance_rate'] == 1.0
    assert len(m['round_details']) == 3


def test_unknown_behavior_excluded_from_counts():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        derive_round_metrics,
    )

    m = derive_round_metrics(
        [_t(1, 300.0, 800.0), _t(2, 200.0, 600.0)],
        [{'round': 1, 'behavior': '回复'}, {'round': 2, 'behavior': None}],  # 解析失败 → unknown
        {'is_stop_type': False})
    assert m['success_count'] == 1 and m['failure_count'] == 0
    assert m['round_response_latencies'] == [300.0, -1]


def test_degraded_path_without_behaviors():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        derive_round_metrics,
    )

    m = derive_round_metrics([_t(1, 300.0, 800.0)], None, {'is_stop_type': True})
    assert m['success_count'] is None and m['failure_count'] is None
    assert m['inquiry_count'] is None and m['reply_content_score'] is None
    assert m['round_response_latencies'] == [-1] and m['round_reply_latencies'] == [-1]
    assert m['response_latency_avg_ms'] is None  # 全 -1 → null 不给 0
    assert m['stop_compliance_rate'] is None


def test_stop_compliance_only_for_stop_case_types():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        derive_round_metrics,
    )

    behaviors = [{'round': 1, 'behavior': '回复', 'stop_complied': False}]
    m = derive_round_metrics([_t(1, 1.0, 2.0, stop=True)], behaviors, {'is_stop_type': False})
    assert m['stop_compliance_rate'] is None
    m = derive_round_metrics([_t(1, 1.0, 2.0, stop=True)], behaviors, {'is_stop_type': True})
    assert m['stop_compliance_rate'] == 0.0


def test_resume_latency_fallback_and_explicit():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        derive_round_metrics,
    )

    timing = [_t(1, 300.0, 800.0)]
    # 无恢复轮锚定 → 回退末个实际打断轮回复时延（spec"最后一轮模型的回复时延"）
    m = derive_round_metrics(timing, [], {'is_stop_type': False})
    assert m['resume_first_reply_latency_ms'] == 800.0
    # 恢复轮锚定优先
    rt = _t(2, None, 1200.0, role='resume')
    m2 = derive_round_metrics(timing, [], {'is_stop_type': False}, rt)
    assert m2['resume_first_reply_latency_ms'] == 1200.0
    # 恢复轮不入数量分母/list
    assert m2['round_response_latencies'] == [-1]
    assert len(m2['round_details']) == 2 and m2['round_details'][-1]['role'] == 'resume'
