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
    # preserve_resume：__init__ 的 is_last_actual 门控结果不被裁判重派生覆盖
    assert result['resume_first_reply_latency_ms'] == REPLY


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
         'stop_complied': 'no'},
        {'round': 'x', 'behavior': '乱码'},
    ]})
    assert out[0]['round'] == 2 and out[0]['behavior'] == '静默'
    assert out[0]['behavior_reason'] == '无输出'
    assert out[0]['score_overall'] == 4.0
    assert out[0]['stop_complied'] is False
    assert out[1]['round'] is None and out[1]['behavior'] is None
    assert out[1]['score'] is None and out[1]['score_overall'] is None
