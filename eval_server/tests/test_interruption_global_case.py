# -*- coding: utf-8 -*-
"""整体评估全局路径单测：case 模式完整 pcm 单次评估（禁止逐轮单独评估）。

用户口径：整体评估用最后一轮采集的完整 pcm（含前面全部轮）评一次，
数据按 每轮(per_round) + 整体 返回。

时间线（合并阈值 user 1.5s / model 0.7s，间距 ≥3.8s 不会误合并）：
    user : 初始问题[1.0,1.8]  打断'等等'[5.6,5.9]  回话题[10.0,10.5]
    model: 回答中[2.5,5.8]                好嘞加上了[11.0,12.0]
    round1 窗口(5.6,5.9): resp=200ms, reply=None —— u_next=10.0 挡住 11.0 的模型段（本轮静默）
    round2 窗口(10.0,10.5): resp=None, reply=500ms
"""

USER_CHUNKS = [
    {'text': '初始问题', 'timestamp': [1.0, 1.8]},
    {'text': '等等', 'timestamp': [5.6, 5.9]},
    {'text': '哦对了还要加上下午去银行办卡', 'timestamp': [10.0, 10.5]},
]
MODEL_CHUNKS = [
    {'text': '回答中', 'timestamp': [2.5, 5.8]},
    {'text': '好嘞加上了', 'timestamp': [11.0, 12.0]},
]
# FFT 锚定桩：rd 级 played_audios → 全局时间线上的用户窗口
WINDOWS = {'clean_r1.wav': (5.6, 5.9), 'clean_r2.wav': (10.0, 10.5)}


def _patch_fft(monkeypatch):
    from app.services.calculators.xiaoyi_metrics.interruptibility import round_metrics as rm

    def fake_locate(played_audios, user_wav):
        if not played_audios:
            return None
        key = played_audios[0] if isinstance(played_audios, list) else played_audios
        w = WINDOWS.get(key)
        return (w[0], w[1], 0.99) if w else None

    monkeypatch.setattr(rm, 'locate_fft_window', fake_locate)


def _patch_judge(monkeypatch, rounds_items):
    """假 LLM 裁判：捕获 blocks/interaction，返回 behaviors_from_judge 可解析的形状。"""
    from app.services.calculators.xiaoyi_metrics.interruptibility import interruption_judge as ij

    captured = {'calls': 0}

    def fake_judge(blocks, interaction_text='', **kw):
        captured['calls'] += 1
        captured['blocks'] = blocks
        captured['interaction'] = interaction_text
        return {'enabled': True, 'model': 'fake', 'tokens_used': 0,
                'rounds': rounds_items, 'message': 'OK'}

    monkeypatch.setattr(ij, 'judge_interruption_rounds', fake_judge)
    return captured


def _patch_asr(monkeypatch):
    """记录远程 ASR 调用的 wav 路径；按路径回固定 chunks。"""
    from app.utils import asr_adapter

    calls = []

    def fake_call(path):
        calls.append(path)
        return path

    monkeypatch.setattr(asr_adapter, 'call_modelscope_asr_word', fake_call)
    monkeypatch.setattr(
        asr_adapter, 'parse_result',
        lambda raw: {'chunks': USER_CHUNKS if 'user' in str(raw) else MODEL_CHUNKS})
    return calls


def test_global_case_single_eval_and_per_round_slicing(monkeypatch):
    """顶层内联 ASR（完整 pcm 已 ASR）→ 全局单次评估 + 逐轮窗口切片 + 整轮=Σ逐轮。"""
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
        InterruptionMetricsCalculator,
    )

    _patch_fft(monkeypatch)
    asr_calls = _patch_asr(monkeypatch)
    captured = _patch_judge(monkeypatch, [
        {'round': 1, 'behavior': '恢复', 'behavior_reason': '模型继续原话题',
         'score': {'overall': 2.0}},
        {'round': 2, 'behavior': '回复', 'behavior_reason': '正常回应',
         'score': {'overall': 4.5}},
    ])
    task_params = {
        'user_asr': list(USER_CHUNKS), 'model_asr': list(MODEL_CHUNKS),
        'interruption_rounds': [1, 2],
        'rounds': [
            {'is_interruption': True, 'query': '初始问题'},
            {'is_interruption': True, 'played_audios': ['clean_r1.wav']},
            {'played_audios': ['clean_r2.wav']},
        ],
    }
    wrapped = InterruptionMetricsCalculator().run(task_params)
    result = wrapped['interruption']

    # 内联 ASR → 0 次远程 ASR；LLM 裁判整例恰好一次
    assert asr_calls == []
    assert captured['calls'] == 1

    # 全局单时间线：真打断事件只有 round1 一个（round2 用户段是 recovery_only）
    assert result['case_type'] == 'multi'
    assert result['interruption_success_rate'] == 1 and result['n_events'] == 1

    # 逐轮时延：round1 静默不取到 round2 的模型段（u_next 边界生效，否则误得 5100.0）
    timing = {t['round']: t for t in result['round_timing']}
    assert timing[1]['anchor_method'] == 'fft'
    assert timing[1]['response_latency_ms'] == 200.0
    assert timing[1]['reply_latency_ms'] is None
    assert timing[2]['response_latency_ms'] is None
    assert timing[2]['reply_latency_ms'] == 500.0

    # LLM 标注块：round1 不得泄漏 round2 的模型文本（同源 u_next 口径）
    b1, b2 = captured['blocks']
    assert b1['model_interrupted_text'] == '回答中' and b1['model_recovery_text'] == ''
    assert b2['model_interrupted_text'] == '' and b2['model_recovery_text'] == '好嘞加上了'
    assert '等等' in captured['interaction']

    # 行为 × 时序 → v2 spec（round1 恢复=失败记 -1，round2 回复照记）
    assert result['success_count'] == 1 and result['failure_count'] == 1
    assert result['round_response_latencies'] == [-1, -1]
    assert result['round_reply_latencies'] == [-1, 500.0]
    assert result['reply_latency_avg_ms'] == 500.0

    # legacy 逐轮字段：全局 per_event 按窗口 [u_s, u_next) 切片
    rl = result['round_latencies']
    assert [e['round'] for e in rl] == [1, 2]
    assert rl[0]['stop_latency_s'] == 200.0 and rl[0]['recovery_latency_s'] == 5100.0
    assert rl[0]['target_recovery_latency_s'] == 5100.0
    assert rl[0]['first_recovery_latency_s'] is None  # round2 无 interruption 事件 → 末轮也是 None
    assert rl[1]['stop_latency_s'] is None and rl[1]['target_stop_latency_s'] is None
    assert result['first_recovery_latency_s'] is None

    # per_round 提升到响应顶层；整轮 = Σ 逐轮
    per_round = wrapped['per_round']
    assert 'per_round' not in result
    assert [p['round_number'] for p in per_round] == [0, 1, 2]
    for key in ('success_count', 'failure_count', 'inquiry_count'):
        assert result[key] == sum(
            p.get('interruption', {}).get(key, 0) for p in per_round), key


def test_global_case_asr_runs_once_on_full_pcm_only(monkeypatch):
    """wav-only payload：远程 ASR 只对顶层完整 pcm 各一次，绝不碰 rd 级累积录音。"""
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
        InterruptionMetricsCalculator,
    )

    _patch_fft(monkeypatch)
    asr_calls = _patch_asr(monkeypatch)
    _patch_judge(monkeypatch, [])  # rounds 空 → behaviors None → 降级 spec（本测试不关心行为）
    task_params = {
        'user_wav': '/fake/full_user.wav', 'ai_wav': '/fake/full_ai.wav',
        'interruption_rounds': [1, 2],
        'rounds': [
            {'is_interruption': True, 'query': '初始问题'},
            {'is_interruption': True, 'played_audios': ['clean_r1.wav'],
             'user_wav': '/fake/cum_r1_user.wav', 'ai_wav': '/fake/cum_r1_ai.wav'},
            {'played_audios': ['clean_r2.wav'],
             'user_wav': '/fake/cum_r2_user.wav', 'ai_wav': '/fake/cum_r2_ai.wav'},
        ],
    }
    result = InterruptionMetricsCalculator().run(task_params)['interruption']

    # "不需要也不能使用每轮的数据进行单独的评估"的硬校验：
    # 只有顶层完整 pcm 被 ASR，rd 级累积录音一次都不碰
    assert asr_calls == ['/fake/full_user.wav', '/fake/full_ai.wav']
    assert not any('cum_' in p for p in asr_calls)
    # 全局评估结果与内联 ASR 路径一致
    assert result['n_events'] == 1 and result['interruption_success_rate'] == 1
    assert [t['round'] for t in result['round_timing']] == [1, 2]


def test_gate_off_legacy_per_round_path_unchanged(monkeypatch):
    """无顶层音频（轮次内联 ASR 旧形态）→ 不进全局路径，旧逐轮行为不变。"""
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
        InterruptionMetricsCalculator,
    )

    calls = []
    monkeypatch.setattr(InterruptionMetricsCalculator, '_calculate_overall_global',
                        lambda *a, **k: calls.append(1))
    user = [
        {'text': '初始问题', 'timestamp': [1.0, 1.8]},
        {'text': '等等', 'timestamp': [3.6, 4.0]},
    ]
    model = [
        {'text': '回答中', 'timestamp': [2.5, 3.8]},
        {'text': '恢复回复', 'timestamp': [4.8, 5.4]},
    ]
    task_params = {
        'rounds': [
            {'is_interruption': True, 'user_asr': user, 'model_asr': model},
            {'is_interruption': True, 'user_asr': user, 'model_asr': model},
            {'user_asr': user, 'model_asr': model},
        ],
    }
    result = InterruptionMetricsCalculator().run(task_params)['interruption']
    assert not calls
    assert result['case_type'] == 'multi'
    assert result['interruption_success_rate'] == 1


def test_global_stop_resume_case(monkeypatch):
    """停止指令 + 恢复前文：全局路径出 stop_resume_single，恢复轮独立锚定回复时延。"""
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
        InterruptionMetricsCalculator,
    )

    _patch_fft(monkeypatch)
    captured = _patch_judge(monkeypatch, [
        {'round': 1, 'behavior': '回复', 'behavior_reason': '停下并回应',
         'score': {'overall': 4.0}, 'stop_complied': True},
    ])
    task_params = {
        'user_asr': list(USER_CHUNKS), 'model_asr': list(MODEL_CHUNKS),
        'interruption_rounds': [1],
        'rounds': [
            {'query': '初始问题'},
            {'is_actual_interruption': True, 'stop_intent': True,
             'played_audios': ['clean_r1.wav']},
            {'is_return_to_topic': True, 'played_audios': ['clean_r2.wav']},
        ],
    }
    wrapped = InterruptionMetricsCalculator().run(task_params)
    result = wrapped['interruption']

    assert result['case_type'] == 'stop_resume_single'
    # 恢复轮（round2）在全局时间线上独立锚定：回复时延 = 11.0 − 10.5
    resume = [t for t in result['round_timing'] if t.get('role') == 'resume']
    assert len(resume) == 1 and resume[0]['round'] == 2
    assert result['resume_first_reply_latency_ms'] == 500.0
    # 停止遵从来自 LLM 判定
    assert result['stop_compliance_rate'] == 1.0
    assert result['success_count'] == 1 and result['failure_count'] == 0
    # 标注块角色：停止轮 + 恢复轮
    roles = [b['role'] for b in captured['blocks']]
    assert roles == ['停止', '恢复']

    per_round = wrapped['per_round']
    assert per_round[1]['interruption']['response_latency_avg_ms'] == 200.0
    assert per_round[1]['interruption']['stop_compliance_rate'] == 1.0
    assert per_round[2]['interruption'] == {'resume_first_reply_latency_ms': 500.0}
