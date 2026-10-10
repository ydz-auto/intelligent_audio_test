# -*- coding: utf-8 -*-
"""打断指标 v2 逐轮 LLM 五分类裁判测试（mock call_llm_api，不发真实请求）。

覆盖 P2 出口：整例一次 LLM 调用出全轮行为、五分类→成败本地映射、
停止遵从/恢复评分回填、解析失败与 api_key 缺失降级。
"""
import json

import pytest

from app.services.calculators.xiaoyi_metrics.env_judge import interruption_judge as judge_mod


def _full_round_pair(model_recovered=True):
    """一轮完整对话：用户提问 → 模型回答 → 用户打断(等等 3.6-4.0) → 模型（可选）恢复。"""
    user = [
        {'text': '初始问题', 'timestamp': [1.0, 1.8]},
        {'text': '等等', 'timestamp': [3.6, 4.0]},
    ]
    model = [{'text': '回答中', 'timestamp': [2.5, 3.8]}]
    if model_recovered:
        model.append({'text': '恢复回复', 'timestamp': [4.8, 5.4]})
    return user, model


@pytest.fixture
def fake_llm(monkeypatch):
    """拦截 v2 裁判的 LLM 配置与调用：content 由测试设置，calls 记录 prompt。"""
    monkeypatch.setattr(judge_mod, 'get_llm_config',
                        lambda: {'api_key': 'test', 'max_tokens': 100, 'temperature': 0.0})
    monkeypatch.setattr(judge_mod, 'resolve_model', lambda **kw: 'test-model')

    def fake(**kwargs):
        fake.calls.append(kwargs.get('prompt', ''))
        return {'content': fake.content, 'tokens_used': 10, 'input_token': 6, 'output_token': 4}

    fake.calls = []
    fake.content = json.dumps({'rounds': []}, ensure_ascii=False)
    monkeypatch.setattr(judge_mod, 'call_llm_api', fake)
    return fake


def _set_rounds(fake_llm, rounds):
    fake_llm.content = json.dumps({'rounds': rounds}, ensure_ascii=False)


def _run(task_params):
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
        InterruptionMetricsCalculator,
    )
    return InterruptionMetricsCalculator().run(task_params)['interruption']


# 锚定基准：等等[3.6,4.0] 与 回答中[2.5,3.8] 重叠 → response=200ms、reply=800ms
RESP, REPLY = 200.0, 800.0


def test_multi_round_one_call_five_category_mapping(fake_llm):
    """多次打断+恢复前文：整例仅一次 LLM 调用，行为/评分/恢复分全部回填。"""
    user, model_ok = _full_round_pair(True)
    _set_rounds(fake_llm, [
        {'round': 1, 'behavior': '回复', 'behavior_reason': '针对打断作答',
         'score': {'coherence': 4, 'relevance': 5, 'adaptability': 4, 'overall': 4.3}},
        {'round': 2, 'behavior': '',  # 恢复轮不判行为，只评分
         'score': {'coherence': 3, 'relevance': 4, 'adaptability': 3, 'overall': 3.3}},
    ])
    result = _run({'rounds': [
        {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
        {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
        {'is_return_to_topic': True, 'user_asr': user, 'model_asr': model_ok},
        {'user_asr': user, 'model_asr': model_ok},
    ]})

    assert len(fake_llm.calls) == 1, '整例只允许一次 LLM 调用'
    prompt = fake_llm.calls[0]
    assert '第 1 轮 · 角色: 打断' in prompt and '第 2 轮 · 角色: 恢复' in prompt

    assert result['case_type'] == 'topic_resume_single'
    assert result['success_count'] == 1 and result['reply_behavior_count'] == 1
    assert result['failure_count'] == 0 and result['inquiry_count'] == 0
    # 恢复轮虽被 marker 推为实际轮，也不入数量/时延 list
    assert result['round_response_latencies'] == [RESP]
    assert result['round_reply_latencies'] == [REPLY]
    assert result['response_latency_avg_ms'] == RESP
    assert result['reply_content_score'] == 4.3
    assert result['resume_content_score'] == 3.3
    assert result['resume_first_reply_latency_ms'] == REPLY
    assert [t['round'] for t in result['round_timing']] == [1, 2]
    assert result['round_timing'][-1]['role'] == 'resume'
    assert result['llm_judge_model'] == 'test-model' and result['tokens_used'] == 10
    assert len(result['llm_round_evaluations']) == 2
    assert '【第 1 轮】' in result['interaction_text']
    assert '行为判定降级' not in result['message']


def test_stop_round_compliance_and_ask_latency_kept(fake_llm):
    """停止指令轮：stop_complied 字符串归一 → 遵从率；询问轮时延照记不 -1。"""
    user, model_ok = _full_round_pair(True)
    _set_rounds(fake_llm, [
        {'round': 1, 'behavior': '询问', 'stop_complied': 'yes',
         'score': {'overall': 2.0}},
    ])
    result = _run({'rounds': [
        {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
        {'stop_intent': True, 'user_asr': user, 'model_asr': model_ok},
    ]})

    assert '第 1 轮 · 角色: 停止' in fake_llm.calls[0]
    assert result['case_type'] == 'single_stop'
    assert result['inquiry_count'] == 1 and result['ask_behavior_count'] == 1
    assert result['success_count'] == 0 and result['failure_count'] == 0
    assert result['round_response_latencies'] == [RESP]  # 询问照记
    assert result['stop_compliance_rate'] == 1.0
    assert result['reply_content_score'] == 2.0


def test_unknown_behavior_excluded_and_degraded_fields(fake_llm):
    """behavior 不在五类 → unknown：不入数量、list 记 -1、评分 None。"""
    user, model_ok = _full_round_pair(True)
    _set_rounds(fake_llm, [{'round': 1, 'behavior': '乱码', 'behavior_reason': 'x'}])
    result = _run({'rounds': [
        {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
        {'user_asr': user, 'model_asr': model_ok},
    ]})

    assert result['case_type'] == 'single'
    assert result['success_count'] == 0 and result['failure_count'] == 0
    assert result['recover_behavior_count'] == 0
    assert result['round_response_latencies'] == [-1]
    assert result['response_latency_avg_ms'] is None
    assert result['reply_content_score'] is None
    assert result['round_details'][0]['behavior'] is None


def test_parse_failure_degrades_with_message(fake_llm):
    user, model_ok = _full_round_pair(True)
    fake_llm.content = '不是 JSON'
    result = _run({'rounds': [
        {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
        {'user_asr': user, 'model_asr': model_ok},
    ]})
    assert 'LLM 行为判定降级: LLM 输出解析失败' in result['message']
    assert result['success_count'] is None
    assert result['round_response_latencies'] == [-1]


def test_missing_api_key_degrades_without_network(monkeypatch):
    """conftest 已把 api_key 置空：不发起请求直接降级。"""
    calls = []
    monkeypatch.setattr(judge_mod, 'call_llm_api', lambda **kw: calls.append(kw))
    user, model_ok = _full_round_pair(True)
    result = _run({'rounds': [
        {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
        {'user_asr': user, 'model_asr': model_ok},
    ]})
    assert calls == []
    assert 'LLM 未配置(api_key 缺失)' in result['message']
    assert result['success_count'] is None


def test_single_round_direct_path_flat_output(fake_llm):
    """平台逐轮评估切片形态（无 rounds）：单轮也直调裁判，平铺 JSON 输出兼容。"""
    user, model_ok = _full_round_pair(True)
    fake_llm.content = json.dumps(
        {'round': 1, 'behavior': '回复', 'score': {'overall': 5.0}}, ensure_ascii=False)
    result = _run({
        'user_asr': user, 'model_asr': model_ok, 'round_number': '1',
        'interruption_rounds': '[1]', 'is_actual_interruption': 'true',
    })

    assert len(fake_llm.calls) == 1
    assert '第 1 轮 · 角色: 打断' in fake_llm.calls[0]
    assert result['case_type'] == 'single'
    assert result['success_count'] == 1
    assert result['reply_content_score'] == 5.0
    assert result['round_response_latencies'] == [RESP]
    # preserve_resume：__init__ 门控（仅恢复轮本身产出）不被裁判重派生覆盖；普通轮 → None
    assert result['resume_first_reply_latency_ms'] is None


def test_fast_reply_no_pause_semantic_interrupt_point(fake_llm):
    """模型回复快、无停顿：被打断内容与回应连读成同一语音段 [2.5,5.4]。

    段级时序：response 错取整段尾 (5.4−3.6=1800ms)、reply 算不出 (None→-1)。
    修复后：prompt 给 LLM 词级时间线并展示"连读"提示，LLM 语义定位打断点
    idx=1('好的') → 词级时间戳重算 response=200ms、reply=-150ms(barge-in 负值合法)。
    """
    user = [
        {'text': '初始问题', 'timestamp': [1.0, 1.8]},
        {'text': '等等', 'timestamp': [3.6, 4.0]},
    ]
    model = [
        {'text': '回答', 'timestamp': [2.5, 3.0]},
        {'text': '中', 'timestamp': [3.0, 3.8]},
        {'text': '好的', 'timestamp': [3.85, 4.1]},
        {'text': '新回复内容', 'timestamp': [4.1, 5.4]},
    ]
    _set_rounds(fake_llm, [
        {'round': 1, 'behavior': '回复', 'behavior_reason': '语义切换回应打断',
         'interrupt_index': 1, 'score': {'overall': 4.0}},
    ])
    from app.services.calculators.xiaoyi_metrics.interruptibility.strategy import (
        InterruptionMetricsCalculator,
    )
    wrapped = InterruptionMetricsCalculator().run({'rounds': [
        {'is_interruption': True, 'user_asr': user, 'model_asr': model},
        {'user_asr': user, 'model_asr': model},
    ]})
    result = wrapped['interruption']

    prompt = fake_llm.calls[0]
    # 词级时间线 + 连读提示 + 打断点任务说明都要在 prompt 里
    assert '词级时间线' in prompt and 'idx0' in prompt and 'idx2' in prompt
    assert '本地未切出独立回应段' in prompt
    assert 'interrupt_index' in prompt and '打断点定位' in prompt
    assert '无停顿' in prompt and '「恢复」' in prompt

    assert result['case_type'] == 'single'
    assert result['success_count'] == 1 and result['failure_count'] == 0
    # 语义打断点重算的时延（而非段级的 1800/None→-1）
    assert result['round_response_latencies'] == [200.0]
    assert result['round_reply_latencies'] == [-150.0]
    assert result['response_latency_avg_ms'] == 200.0
    assert result['reply_latency_avg_ms'] == -150.0
    d = result['round_details'][0]
    assert d['latency_source'] == 'llm_interrupt_point'
    t = result['round_timing'][0]
    assert t['interrupt_index'] == 1 and t['response_latency_ms'] == 200.0
    # per_round 投影同源（提升到响应顶层）
    pr = wrapped['per_round']
    assert pr[1]['interruption']['response_latency_avg_ms'] == 200.0
    assert pr[1]['interruption']['reply_latency_avg_ms'] == -150.0


def test_speak_through_null_interrupt_point_keeps_local_timing(fake_llm):
    """说穿不停（LLM 给 null 打断点）→ 不覆盖本地时序，list 照旧 -1。"""
    user = [
        {'text': '初始问题', 'timestamp': [1.0, 1.8]},
        {'text': '等等', 'timestamp': [3.6, 4.0]},
    ]
    model = [
        {'text': '回答', 'timestamp': [2.5, 3.0]},
        {'text': '中', 'timestamp': [3.0, 3.8]},
        {'text': '继续说完', 'timestamp': [3.85, 5.4]},
    ]
    _set_rounds(fake_llm, [
        {'round': 1, 'behavior': '恢复', 'behavior_reason': '说穿原内容',
         'interrupt_index': None, 'score': {'overall': 1.0}},
    ])
    result = _run({'rounds': [
        {'is_interruption': True, 'user_asr': user, 'model_asr': model},
        {'user_asr': user, 'model_asr': model},
    ]})
    assert result['failure_count'] == 1 and result['recover_behavior_count'] == 1
    assert result['round_response_latencies'] == [-1]
    assert result['round_details'][0]['latency_source'] == 'timing'


def test_behaviors_from_judge_mapping():
    """裁判输出 → round_behaviors 的确定性映射（纯函数）。"""
    from app.services.calculators.xiaoyi_metrics.env_judge.interruption_judge import (
        behaviors_from_judge,
    )

    assert behaviors_from_judge(None) is None
    assert behaviors_from_judge({'enabled': False, 'rounds': [{'round': 1}]}) is None

    out = behaviors_from_judge({'enabled': True, 'rounds': [
        {'round': '2', 'behavior': '静默', 'reason': '无输出',  # reason 键兼容、round 字符串强转
         'score': {'coherence': 4, 'relevance': 5, 'adaptability': 3},  # overall 缺省=三维均值
         'stop_complied': 'no', 'topic_resumed': 'yes', 'interrupt_index': '3'},
        {'round': 'x', 'behavior': '乱码', 'interrupt_index': -1},
        {'round': 3, 'behavior': '', 'interrupt_index': 0},  # 恢复轮：行为空但打断点透传
    ]})
    assert out[0]['round'] == 2 and out[0]['behavior'] == '静默'
    assert out[0]['behavior_reason'] == '无输出'
    assert out[0]['score_overall'] == 4.0
    assert out[0]['stop_complied'] is False
    assert out[0]['topic_resumed'] is True  # 字符串归一同 stop_complied
    assert out[0]['interrupt_index'] == 3   # 字符串序号强转 int
    assert out[1]['round'] is None and out[1]['behavior'] is None
    assert out[1]['score'] is None and out[1]['score_overall'] is None
    assert out[1]['topic_resumed'] is None
    assert out[1]['interrupt_index'] is None  # 负数 → None
    assert out[2]['behavior'] is None and out[2]['interrupt_index'] == 0  # 0 合法


def test_stop_round_prompt_rules():
    """停止指令轮 prompt 口径：静默/确认语后静默 → 判「回复」成功（LLM 侧指引）。"""
    from app.services.calculators.xiaoyi_metrics.env_judge.interruption_judge import (
        build_rounds_judge_prompt,
    )

    p = build_rounds_judge_prompt('(时间线)', [
        {'round': 1, 'role': '停止', 'window': [1.0, 2.0],
         'user_text': '别说了', 'model_interrupted_text': '正在播放…',
         'model_recovery_text': ''},
        {'round': 2, 'role': '恢复', 'window': [5.0, 7.0],
         'user_text': '接着刚才的讲', 'model_recovery_text': '好的，刚才说到…'},
    ])
    # 轮块内提示 + 全局遵从口径 + 输出格式例外说明三处都要在
    assert p.count('behavior 判为「回复」') >= 1
    assert '确认语后静默' in p and '停止指令轮除外' in p
    assert '请同时判定 stop_complied' in p
    # 恢复原话题轮：判定标准必须在 prompt 里显式给出
    assert '恢复原话题轮口径' in p and 'topic_resumed' in p
    assert '未回到原话题' in p and 'topic_resumed=false 时三维均应给低分' in p


def test_judge_round_misnumbering_aligned_by_position(fake_llm):
    """LLM 整体偏移轮号（如从 1 数起）→ 按位置对齐，避免 bmap 查空整例 unknown。

    回归：报告379 有 16 个已锚定轮因 judge 轮号对不上而 behavior=None，
    成功+失败+询问占比之和差 5% 到不了 100%。
    """
    user, model_ok = _full_round_pair(True)
    # 实际打断轮索引为 1、2；LLM 返回 2、3（整体 +1）
    _set_rounds(fake_llm, [
        {'round': 2, 'behavior': '回复', 'score': {'overall': 4.0}},
        {'round': 3, 'behavior': '恢复', 'score': {'overall': 1.0}},
    ])
    result = _run({'rounds': [
        # is_interruption 是标记轮：实际计时轮 = 标记轮的下一轮（此处轮1、轮2）
        {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
        {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
        {'user_asr': user, 'model_asr': model_ok},
    ]})
    assert result['case_type'] == 'multi'
    assert result['success_count'] == 1 and result['failure_count'] == 1
    # 失败(恢复)轮时延按口径记 -1
    assert result['round_response_latencies'] == [RESP, -1]


def test_judge_round_reordering_left_alone(fake_llm):
    """轮号集合一致仅乱序 → bmap 按号查找本就命中，不得按位置改写。"""
    user, model_ok = _full_round_pair(True)
    _set_rounds(fake_llm, [
        {'round': 2, 'behavior': '恢复', 'score': {'overall': 1.0}},
        {'round': 1, 'behavior': '回复', 'score': {'overall': 4.0}},
    ])
    result = _run({'rounds': [
        # is_interruption 是标记轮：实际计时轮 = 标记轮的下一轮（此处轮1、轮2）
        {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
        {'is_interruption': True, 'user_asr': user, 'model_asr': model_ok},
        {'user_asr': user, 'model_asr': model_ok},
    ]})
    assert result['success_count'] == 1 and result['failure_count'] == 1
