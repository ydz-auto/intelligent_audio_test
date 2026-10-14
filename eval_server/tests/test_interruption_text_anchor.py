# -*- coding: utf-8 -*-
"""文本匹配锚定回退单测（VEGA-8：多轮打断"回复"被误判"静默"）。

根因：整体评估全局路径只靠 FFT(played_audios)→驱动窗口锚定轮窗口；两者都失败时
anchor='none' → build_round_block 出空块（用户'(未识别到)'/回应'(无语音输出)'）→
LLM 按「模型无任何语音输出时 behavior=静默」规则被迫判静默——即使全局 ASR 时间线
里该轮用户话语和模型回应都在。

修复：strategy._anchor 增加第三级回退 locate_text_window（轮脚本台词 ↔ ASR 用户段
模糊匹配，含说话人前缀剥离/连续段拼接/单调时间约束），anchor_method='text_match'。

本文件覆盖：
  1. locate_text_window 纯函数（前缀剥离/切段拼接/单调约束/串音不命中）
  2. 全局路径集成：FFT/驱动窗口失败 → text_match 锚定，块含用户话语与模型回应，
     行为可按证据判定（假裁判判「回复」→ success_count 计入）
  3. 串音回归：台词不在 ASR（录音内容为其他用例对话）→ 保持 anchor='none' 降级，
     不做虚假锚定
"""

# ─────────── 1. locate_text_window 纯函数 ───────────

def _seg(s, e, t):
    return {'start': s, 'end': e, 'text': t}


def test_text_window_basic_and_prefix():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        locate_text_window,
    )
    segs = [_seg(4.92, 8.78, '我最近晚上有点失眠有什么解决办法吗'),
            _seg(15.47, 18.21, '先帮我定个倒计时五分钟')]
    # 带说话人前缀+标点（真实请求体 query 形态："用户1：……，……？"）
    win = locate_text_window('用户1：我最近，晚上有点失眠，有什么解决办法吗？', segs)
    assert win is not None
    assert win[0] == 4.92 and win[1] == 8.78 and win[2] >= 0.5
    # 串音台词（录音里没有）→ 不命中
    assert locate_text_window('看中了一件吊带裙现在买合适吗', segs) is None


def test_text_window_multi_segment_concat():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        locate_text_window,
    )
    # ASR 把一句台词切成两段（间隔>合并阈值时不会并段）
    segs = [_seg(2.0, 4.0, '刚恢复运动快走三十分钟更合适'),
            _seg(5.8, 9.0, '还是快走二十分钟加慢跑十分钟'),
            _seg(20.0, 22.0, '无关话语')]
    win = locate_text_window('刚恢复运动快走三十分钟更合适还是快走二十分钟加慢跑十分钟', segs)
    assert win is not None
    assert win[0] == 2.0 and win[1] == 9.0  # 窗口=首段start~末段end


def test_text_window_monotonic_after():
    from app.services.calculators.xiaoyi_metrics.interruptibility.round_metrics import (
        locate_text_window,
    )
    # 相同台词出现两次（如恢复轮重复前文）：after 下界防止错锚到更早一次
    segs = [_seg(3.0, 5.0, '等一下你刚才说什么'), _seg(30.0, 32.0, '等一下你刚才说什么')]
    w1 = locate_text_window('等一下你刚才说什么', segs)
    assert w1[0] == 3.0
    w2 = locate_text_window('等一下你刚才说什么', segs, after=5.0)
    assert w2 is not None and w2[0] == 30.0


# ─────────── 2/3. 全局路径集成（复刻 test_interruption_global_case 桩件） ───────────

USER_CHUNKS = [
    {'text': '帮我推荐一部电影', 'timestamp': [1.0, 1.8]},
    {'text': '等等我忘了说', 'timestamp': [5.6, 6.4]},
    {'text': '哦对了还要加上下午去银行办卡', 'timestamp': [10.0, 10.8]},
]
MODEL_CHUNKS = [
    {'text': '回答中', 'timestamp': [2.5, 5.8]},
    {'text': '好的您说', 'timestamp': [7.0, 8.0]},
    {'text': '好嘞加上了', 'timestamp': [11.5, 12.5]},
]


def _patch_asr(monkeypatch):
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


def _patch_judge(monkeypatch, rounds_items):
    from app.services.calculators.xiaoyi_metrics.env_judge import interruption_judge as ij

    captured = {'calls': 0}

    def fake_judge(blocks, interaction_text='', **kw):
        captured['calls'] += 1
        captured['blocks'] = blocks
        return {'enabled': True, 'model': 'fake', 'tokens_used': 0,
                'rounds': rounds_items, 'message': 'OK'}

    monkeypatch.setattr(ij, 'judge_interruption_rounds', fake_judge)
    return captured


def _task_params(rounds):
    return {
        'user_asr': list(USER_CHUNKS), 'model_asr': list(MODEL_CHUNKS),
        'interruption_rounds': [1, 2],
        'rounds': rounds,
    }


def test_global_text_anchor_when_fft_and_driver_fail(monkeypatch):
    """无 played_audios/驱动窗口 → 文本匹配锚定：窗口/时延/标注块全部恢复。"""
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
        InterruptionMetricsCalculator,
    )

    _patch_asr(monkeypatch)
    captured = _patch_judge(monkeypatch, [
        {'round': 1, 'behavior': '回复', 'behavior_reason': '模型回应了打断',
         'score': {'overall': 4.0}},
        {'round': 2, 'behavior': '回复', 'behavior_reason': '正常回应',
         'score': {'overall': 4.5}},
    ])
    result = InterruptionMetricsCalculator().run(_task_params([
        {'is_interruption': True, 'query': '帮我推荐一部电影'},
        # 真实请求体形态：query 为 {'text': '用户N：……'} 且带标点
        {'is_interruption': True, 'query': {'text': '用户1：等等，我忘了说'}},
        {'query': {'text': '用户1：哦对了，还要加上下午去银行办卡'}},
    ]))['interruption']

    timing = {t['round']: t for t in result['round_timing']}
    assert timing[1]['anchor_method'] == 'text_match'
    assert timing[1]['u_s'] == 5.6 and timing[1]['u_e'] == 6.4
    # 时延恢复：响应=被打断段止于5.8(200ms)，回复=下一模型段7.0起(600ms)
    assert timing[1]['response_latency_ms'] == 200.0
    assert timing[1]['reply_latency_ms'] == 600.0
    assert timing[2]['anchor_method'] == 'text_match'
    assert timing[2]['u_s'] == 10.0 and timing[2]['u_e'] == 10.8

    # 标注块非空：LLM 能看到用户话语与模型回应，不再被「无语音输出=静默」规则绑架
    b1, b2 = captured['blocks']
    assert b1['user_text'] == '等等我忘了说'
    assert b1['model_interrupted_text'] == '回答中'
    assert b1['model_recovery_text'] == '好的您说'
    assert b2['model_recovery_text'] == '好嘞加上了'

    # 行为×时序 → 有回应轮按「回复」计成功（原缺陷下这两轮会被迫判静默）
    assert result['success_count'] == 2
    assert result['silence_behavior_count'] == 0
    assert result['round_reply_latencies'] == [600.0, 700.0]
    assert '锚定降级' not in result['message']


def test_global_crosstalk_round_stays_degraded(monkeypatch):
    """串音回归：录音内容为其他用例对话（台词不在 ASR）→ 保持 none 降级，不虚假锚定。"""
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
        InterruptionMetricsCalculator,
    )

    _patch_asr(monkeypatch)
    captured = _patch_judge(monkeypatch, [
        {'round': 1, 'behavior': '静默', 'behavior_reason': '模型无任何语音输出',
         'score': {'overall': 0}},
        {'round': 2, 'behavior': '静默', 'behavior_reason': '模型无任何语音输出',
         'score': {'overall': 0}},
    ])
    result = InterruptionMetricsCalculator().run(_task_params([
        {'is_interruption': True, 'query': '帮我推荐一部电影'},
        # VEGA-8 C类形态：脚本是吊带裙，录音里却是失眠对话（时间线桩件即"别人的对话"）
        {'is_interruption': True, 'query': {'text': '用户1：看中了一件吊带裙，现在买合适吗'}},
        {'query': {'text': '用户1：你是怎么判断的'}},
    ]))['interruption']

    timing = {t['round']: t for t in result['round_timing']}
    assert timing[1]['anchor_method'] == 'none'
    assert timing[1]['u_s'] is None and timing[1]['response_latency_ms'] is None
    # 空块保持：串音轮不做虚假锚定（数据侧问题须由采集层修，评估层不猜）
    b1 = captured['blocks'][0]
    assert b1['user_text'] == '' and b1['model_recovery_text'] == ''
    assert '锚定降级' in result['message']
