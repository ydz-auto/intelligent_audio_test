# -*- coding: utf-8 -*-
"""交互文字（interaction_text）在话轮接管与拒识裁判中的返回测试。"""
import json

import pytest

from app.services.calculators.xiaoyi_metrics.env_judge import rejection_judge as rj_mod
from app.services.calculators.xiaoyi_metrics.turn_taking.strategy import TurnTakingCalculator

USER_CHUNKS = [{'text': '今天天气', 'timestamp': [1.0, 2.0]}]
AI_CHUNKS = [{'text': '明天小雨', 'timestamp': [3.0, 4.5]}]


def test_turn_taking_returns_interaction_text():
    params = {
        'mode': 'single', 'user_wav': 'u.wav', 'ai_wav': 'a.wav',
        'sub_tasks': ['__none__'],  # 跳过全部子维度，只验证顶层字段
        '_shared_asr': {
            'user_chunks': USER_CHUNKS, 'ai_chunks': AI_CHUNKS,
            'ai_word_chunks': AI_CHUNKS, 'pause_intervals': [],
        },
    }
    result = TurnTakingCalculator().calculate(params)
    text = result['interaction_text']
    assert text.startswith('query [0:01; 0:02]今天天气\n')
    assert text.endswith('answer [0:03; 0:04]明天小雨\n')


def test_rejection_judge_returns_interaction_text(monkeypatch):
    monkeypatch.setattr(rj_mod.os.path, 'isfile', lambda path: bool(path))
    monkeypatch.setattr(
        rj_mod, 'get_asr_chunks',
        lambda wav: USER_CHUNKS if 'user' in str(wav) else AI_CHUNKS,
    )
    monkeypatch.setattr(rj_mod, 'get_asr_text', lambda wav: '文本')
    monkeypatch.setattr(
        rj_mod, 'call_llm_api',
        lambda **kwargs: {'content': json.dumps({'behavior': '静默', 'reason': '未回应'},
                                                ensure_ascii=False),
                          'tokens_used': 1, 'input_token': 1, 'output_token': 0},
    )

    result = rj_mod.evaluate_rejection_judge(ai_wav='ai.wav', user_wav='user.wav',
                                             model='test-model')
    assert result['message'] == 'OK'
    assert result['behavior_silent'] == 1
    assert result['interaction_text'] == (
        'query [0:01; 0:02]今天天气\nanswer [0:03; 0:04]明天小雨\n'
    )
