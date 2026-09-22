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


def test_barge_in_reply_negative_latency():
    """barge-in：模型在用户话未说完（u_e 前）已开始回应，旧口径 start>u_e 会漏判为静默。

    取自实测误判案例：窗口 (27.378, 28.968)，模型段 {28.57, 45.135} 在窗口内起播，
    回复时延应为负（-398ms），且 build_round_block 能取到回应文本。
    """
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        round_latency_from_window, build_round_block,
    )

    segs = [{'start': 28.57, 'end': 45.135, 'text': '好嘞同比就是拿今年同时间段的数据和去年比较'}]
    resp, reply = round_latency_from_window(27.378, 28.968, segs)
    assert resp is None
    assert reply == round((28.57 - 28.968) * 1000, 1)  # -398.0

    # 被打断的活跃段本身不算回应（说穿不停 → 回复时延 None）
    resp, reply = round_latency_from_window(2.0, 2.5, [{'start': 1.0, 'end': 3.0}])
    assert resp == 1000.0 and reply is None

    t = {'round': 2, 'u_s': 27.378, 'u_e': 28.968, 'stop_intent': False}
    block = build_round_block(t, {'model_segments': segs, 'user_segments': []}, {})
    assert block['model_recovery_text'] == segs[0]['text']  # LLM 不再看到 "(无语音输出)"
    assert block['model_interrupted_text'] == ''


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


def test_stop_round_silence_counts_as_reply_success():
    """停止指令轮口径(2026-09-22)：直接静默=遵从 → 按「回复」成功计，不再判失败。"""
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        build_per_round,
        derive_round_metrics,
    )

    timing = [_t(1, 300.0, None, stop=True), _t(2, 250.0, 700.0)]
    behaviors = [
        # LLM 旧口径产物：静默 + score 0 + 甚至 stop_complied=False → 派生层确定性重映射
        {'round': 1, 'behavior': '静默', 'score_overall': 0.0, 'stop_complied': False},
        {'round': 2, 'behavior': '回复', 'score_overall': 4.0},
    ]
    m = derive_round_metrics(timing, behaviors, {'is_stop_type': True})
    assert m['success_count'] == 2 and m['failure_count'] == 0
    assert m['silence_behavior_count'] == 0 and m['reply_behavior_count'] == 2
    # 成功轮时延照记（本轮无回复 → reply 记 -1）
    assert m['round_response_latencies'] == [300.0, 250.0]
    assert m['round_reply_latencies'] == [-1, 700.0]
    # 静默遵从无内容可评 → score 不入内容均分
    assert m['reply_content_score'] == 4.0
    # 遵从率取重映射后的 True（LLM 给的 False 被确定性口径覆盖）
    assert m['stop_compliance_rate'] == 1.0
    d1 = m['round_details'][0]
    assert d1['behavior'] == '回复' and d1['stop_complied'] is True
    assert d1['score_overall'] is None
    # per_round 投影同步
    pr = build_per_round(3, m['round_details'])
    assert pr[1]['interruption']['success_count'] == 1
    assert pr[1]['interruption']['response_latency_avg_ms'] == 300.0
    assert pr[1]['interruption']['stop_compliance_rate'] == 1.0


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


# ─────────── per_round 逐轮投影（整体评估返回逐轮结果方案 §4.2） ───────────

def test_build_per_round():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        build_per_round,
    )

    details = [
        # 成功轮：0/1 计数 + 时延 + 评分
        {'round': 1, 'role': 'interruption', 'behavior': '回复',
         'response_latency_ms': 300.0, 'reply_latency_ms': 800.0, 'score_overall': 4.5},
        # 失败轮：计数投，时延不投（与 list -1 口径一致）
        {'round': 2, 'role': 'interruption', 'behavior': '恢复',
         'response_latency_ms': 100.0, 'reply_latency_ms': 200.0, 'score_overall': 2.0},
        # 停止轮：遵从率投 0/1
        {'round': 3, 'role': 'interruption', 'behavior': '回复', 'stop_intent': True,
         'response_latency_ms': 150.0, 'reply_latency_ms': 500.0,
         'score_overall': 4.0, 'stop_complied': True},
        # 恢复轮：只投恢复首轮内容时延
        {'round': 4, 'role': 'resume', 'behavior': None,
         'response_latency_ms': None, 'reply_latency_ms': 1200.0, 'score_overall': None},
        # unknown 轮（LLM 降级/解析失败）：无可投影 → 跳过项
        {'round': 5, 'role': 'interruption', 'behavior': None,
         'response_latency_ms': 90.0, 'reply_latency_ms': 90.0, 'score_overall': None},
    ]
    pr = build_per_round(7, details)
    assert [p['round_number'] for p in pr] == list(range(7))
    # 轮0 无时序 → 跳过项
    assert 'interruption' not in pr[0] and 'message' in pr[0]
    # 轮1 成功
    assert pr[1]['interruption'] == {'success_count': 1, 'failure_count': 0, 'inquiry_count': 0,
                                     'response_latency_avg_ms': 300.0, 'reply_latency_avg_ms': 800.0,
                                     'reply_content_score': 4.5}
    # 轮2 失败：无时延
    assert pr[2]['interruption'] == {'success_count': 0, 'failure_count': 1, 'inquiry_count': 0,
                                     'reply_content_score': 2.0}
    # 轮3 停止遵从
    assert pr[3]['interruption']['stop_compliance_rate'] == 1.0
    # 轮4 恢复轮：只有 resume_first_reply_latency_ms
    assert pr[4]['interruption'] == {'resume_first_reply_latency_ms': 1200.0}
    # 轮5 unknown：跳过
    assert 'interruption' not in pr[5]
    # 轮6 超出 details：跳过
    assert 'message' in pr[6]
