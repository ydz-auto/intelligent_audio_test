# -*- coding: utf-8 -*-
"""打断裁判一次调用产出全部 LLM 维度的测试（不调真实 LLM/ASR）。"""
import json

import pytest

from app.services.calculators.xiaoyi_metrics.interruptibility import interruption_judge as judge_mod

USER_CHUNKS = [
    {'text': '初始问题', 'timestamp': [1.0, 1.8]},
    {'text': '等等', 'timestamp': [3.6, 4.0]},
]
MODEL_CHUNKS = [
    {'text': '回答中', 'timestamp': [2.5, 3.8]},
    {'text': '恢复回复', 'timestamp': [4.8, 5.4]},
]

SCORE_JSON = {
    'behavior': '回应',
    'reason': '模型针对打断内容作了回答',
    'is_real_interruption': True,
    'interruption_reason': '用户在模型说话期间插入打断，模型让出',
    'success': True,
    'success_reason': '模型停下当前输出',
    'recovery_score': {
        'coherence': 4, 'relevance': 5, 'adaptability': 4, 'overall': 4.3,
        'coherence_reason': 'c', 'relevance_reason': 'r', 'adaptability_reason': 'a',
    },
    'stop_complied': True,
    'stop_compliance_reason': '只回复了确认语',
}


@pytest.fixture
def calls(monkeypatch):
    """拦截 LLM 与 ASR，返回记录到的 prompt 列表。"""
    prompts = []
    monkeypatch.setattr(judge_mod.os.path, 'isfile', lambda path: bool(path))
    monkeypatch.setattr(
        judge_mod, 'get_asr_chunks',
        lambda wav: USER_CHUNKS if 'user' in str(wav) else MODEL_CHUNKS,
    )

    def fake_call_llm(**kwargs):
        prompts.append(kwargs.get('prompt', ''))
        return {'content': json.dumps(SCORE_JSON, ensure_ascii=False),
                'tokens_used': 10, 'input_token': 6, 'output_token': 4}

    monkeypatch.setattr(judge_mod, 'call_llm_api', fake_call_llm)
    return prompts


def _run(**kwargs):
    params = {'ai_wav': 'ai.wav', 'user_wav': 'user.wav', 'model': 'test-model'}
    params.update(kwargs)
    return judge_mod.evaluate_interruption_judge(**params)


def test_single_call_covers_behavior_and_content_score(calls):
    result = _run(sub_tasks=['interruption_judge', 'interruption_coherence',
                             'interruption_relevance', 'interruption_adaptability',
                             'interruption_reply_content'],
                  rounds=[{'is_actual_interruption': True}],
                  round_number=0, interruption_rounds=[0])

    assert len(calls) == 1, '只允许一次 LLM 调用'
    assert '事件语义判定任务' in calls[0]
    # 内容评分块(三维)随 need_score 拼接
    assert 'coherence(连贯性)' in calls[0]
    # is_real/success 始终判定，与三维评分同块产出
    assert result['llm_is_real_interruption'] is True
    assert result['interruption_real_rate'] == 1.0
    assert result['llm_success'] is True
    assert result['llm_success_rate'] == 1.0
    assert result['behavior_respond'] == 1
    assert result['interruption_inquiry_rate'] == 0.0
    assert result['recovery_coherence'] == 4.0
    # 单实际轮：两个内容评分维度都拿到同一目标轮评分
    assert result['interruption_reply_overall'] == 4.3
    assert result['first_recovery_overall'] == 4.3
    # 未勾选停止指令遵从率 → 不拼接、不返回
    assert '停止指令遵从判定任务' not in calls[0]
    assert result['stop_instruction_compliance_rate'] is None


def test_behavior_only_request_has_no_scoring_block(calls):
    result = _run(sub_tasks=['interruption_judge'],
                  rounds=[{'is_actual_interruption': True}],
                  round_number=0, interruption_rounds=[0])

    assert len(calls) == 1
    # 行为-only：事件语义块(is_real/success)仍在，但三维评分不拼
    assert '事件语义判定任务' in calls[0]
    assert 'coherence(连贯性)' not in calls[0]
    assert result['llm_success'] is True  # is_real/success 始终判定
    assert result['recovery_coherence'] is None
    assert result['interruption_reply_overall'] is None
    assert result['first_recovery_overall'] is None
    assert result['interruption_inquiry_rate'] == 0.0


def test_multi_round_scores_last_actual_round_only(calls):
    common = dict(sub_tasks=['interruption_first_recovery_content'],
                  rounds=[{'is_actual_interruption': False},
                          {'is_actual_interruption': True},
                          {'is_actual_interruption': True}],
                  interruption_rounds=[1, 2])

    earlier = _run(round_number=1, **common)
    assert earlier['first_recovery_overall'] is None
    assert earlier['interruption_reply_overall'] is None

    last = _run(round_number=2, **common)
    assert last['first_recovery_overall'] == 4.3
    assert last['interruption_reply_overall'] == 4.3


def test_stop_instruction_compliance_only_for_stop_rounds(calls):
    stop = _run(sub_tasks=['interruption_stop_instruction_compliance'],
                rounds=[{'is_actual_interruption': True, 'stop_intent': True}],
                round_number=0, interruption_rounds=[0], stop_intent=True)
    assert '停止指令遵从判定任务' in calls[-1]
    assert stop['stop_complied'] is True
    assert stop['stop_instruction_compliance_rate'] == 1.0

    normal = _run(sub_tasks=['interruption_stop_instruction_compliance'],
                  rounds=[{'is_actual_interruption': True}],
                  round_number=0, interruption_rounds=[0])
    assert '停止指令遵从判定任务' not in calls[-1]
    assert normal['stop_instruction_compliance_rate'] is None


def test_multipart_string_metadata_is_coerced(calls):
    """create_task_upload 后所有标量都是字符串，不能因此崩溃或误判轮次。"""
    result = _run(sub_tasks='["interruption_first_recovery_content", "interruption_coherence"]',
                  rounds=[{'is_actual_interruption': True}],
                  round_number='0', interruption_rounds='[0]')

    assert len(calls) == 1
    assert '事件语义判定任务' in calls[0]
    # 字符串 sub_tasks（multipart 传参）同样能解析并勾选评分块
    assert result['interruption_reply_overall'] == 4.3
    assert result['first_recovery_overall'] == 4.3
    assert result['recovery_coherence'] == 4.0


def test_inquiry_rate_and_parse_failure(monkeypatch):
    monkeypatch.setattr(judge_mod.os.path, 'isfile', lambda path: bool(path))
    monkeypatch.setattr(
        judge_mod, 'get_asr_chunks',
        lambda wav: USER_CHUNKS if 'user' in str(wav) else MODEL_CHUNKS,
    )

    def uncertain(**kwargs):
        return {'content': json.dumps({'behavior': '不确定询问', 'reason': '没听清'},
                                      ensure_ascii=False),
                'tokens_used': 1, 'input_token': 1, 'output_token': 0}

    monkeypatch.setattr(judge_mod, 'call_llm_api', uncertain)
    result = _run(sub_tasks=['interruption_inquiry_rate'])
    assert result['behavior_uncertain'] == 1
    assert result['interruption_inquiry_rate'] == 1.0

    monkeypatch.setattr(judge_mod, 'call_llm_api',
                        lambda **kwargs: {'content': '不是 JSON', 'tokens_used': 0,
                                          'input_token': 0, 'output_token': 0})
    broken = _run(sub_tasks=['interruption_inquiry_rate'])
    assert broken['message'] == 'LLM 输出解析失败'
    assert broken['interruption_inquiry_rate'] is None
