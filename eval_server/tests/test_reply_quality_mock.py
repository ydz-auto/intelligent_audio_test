# -*- coding: utf-8 -*-
"""reply_quality.py mock 测试"""
import json
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality import (
    evaluate_reply_quality,
    _build_reply_quality_prompt,
)


def test_build_prompt():
    """测试 prompt 构建"""
    prompt = _build_reply_quality_prompt("今天周几", "今天是周三")
    assert "今天周几" in prompt
    assert "今天是周三" in prompt
    assert '"score": 4' in prompt  # JSON 模板示例
    assert "1-5" in prompt or "5分" in prompt
    print("[PASS] test_build_prompt")


def test_evaluate_success():
    """测试正常评分流程"""
    mock_resp = {
        'content': json.dumps({
            'score': 5,
            'reason': '回答准确完整，直接回应了用户问题',
            'analysis': {
                'accuracy': '准确',
                'completeness': '完整',
                'fluency': '流畅',
            },
        }, ensure_ascii=False),
        'tokens_used': 100,
        'input_token': 50,
        'output_token': 50,
    }
    with patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.call_llm',
        return_value=mock_resp,
    ), patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.get_llm_config',
        return_value={'api_base_url': 'http://mock', 'api_key': 'mock_key', 'max_tokens': 4096, 'temperature': 0.1},
    ), patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.resolve_model',
        return_value='gpt-4o-mini',
    ):
        result = evaluate_reply_quality(
            user_text="今天周几",
            ai_text="今天是周三",
        )
    assert result['message'] == 'OK'
    assert result['score'] == 5
    assert result['reason'] == '回答准确完整，直接回应了用户问题'
    assert result['analysis']['accuracy'] == '准确'
    assert result['user_text'] == '今天周几'
    assert result['ai_text'] == '今天是周三'
    print("[PASS] test_evaluate_success")


def test_evaluate_from_chunks():
    """测试从 chunks 拼接文本"""
    mock_resp = {
        'content': json.dumps({
            'score': 3,
            'reason': '部分回答',
            'analysis': {'accuracy': '一般', 'completeness': '不完整', 'fluency': '流畅'},
        }, ensure_ascii=False),
        'tokens_used': 80,
        'input_token': 40,
        'output_token': 40,
    }
    user_chunks = [
        {'text': '今天', 'timestamp': [0.0, 0.5]},
        {'text': '周几', 'timestamp': [0.6, 1.0]},
    ]
    ai_chunks = [
        {'text': '今天', 'timestamp': [1.5, 2.0]},
        {'text': '天气不错', 'timestamp': [2.1, 2.8]},
    ]
    with patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.call_llm',
        return_value=mock_resp,
    ), patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.get_llm_config',
        return_value={'api_base_url': 'http://mock', 'api_key': 'mock_key', 'max_tokens': 4096, 'temperature': 0.1},
    ), patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.resolve_model',
        return_value='gpt-4o-mini',
    ):
        result = evaluate_reply_quality(
            user_chunks=user_chunks,
            ai_chunks=ai_chunks,
        )
    assert result['message'] == 'OK'
    assert result['score'] == 3
    assert result['user_text'] == '今天周几'
    assert result['ai_text'] == '今天天气不错'
    print("[PASS] test_evaluate_from_chunks")


def test_evaluate_no_llm_config():
    """测试 LLM 未配置"""
    with patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.get_llm_config',
        return_value={'api_base_url': '', 'api_key': ''},
    ):
        result = evaluate_reply_quality(
            user_text="今天周几",
            ai_text="今天是周三",
        )
    assert '未配置' in result['message']
    assert result['score'] is None
    print("[PASS] test_evaluate_no_llm_config")


def test_evaluate_llm_parse_fail():
    """测试 LLM 返回非 JSON"""
    mock_resp = {
        'content': '这不是一个JSON格式的回复',
        'tokens_used': 10,
        'input_token': 5,
        'output_token': 5,
    }
    with patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.call_llm',
        return_value=mock_resp,
    ), patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.get_llm_config',
        return_value={'api_base_url': 'http://mock', 'api_key': 'mock_key', 'max_tokens': 4096, 'temperature': 0.1},
    ), patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.resolve_model',
        return_value='gpt-4o-mini',
    ):
        result = evaluate_reply_quality(
            user_text="今天周几",
            ai_text="今天是周三",
        )
    assert '解析失败' in result['message']
    assert result['score'] is None
    print("[PASS] test_evaluate_llm_parse_fail")


def test_evaluate_llm_exception():
    """测试 LLM 调用异常"""
    with patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.call_llm',
        side_effect=Exception('网络超时'),
    ), patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.get_llm_config',
        return_value={'api_base_url': 'http://mock', 'api_key': 'mock_key', 'max_tokens': 4096, 'temperature': 0.1},
    ), patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.resolve_model',
        return_value='gpt-4o-mini',
    ):
        result = evaluate_reply_quality(
            user_text="今天周几",
            ai_text="今天是周三",
        )
    assert 'LLM 调用失败' in result['message']
    assert result['score'] is None
    print("[PASS] test_evaluate_llm_exception")


def test_output_fields():
    """测试返回字段只包含指定的 6 个 key"""
    mock_resp = {
        'content': json.dumps({
            'score': 4,
            'reason': '良好',
            'analysis': {'accuracy': '准确', 'completeness': '完整', 'fluency': '流畅'},
        }, ensure_ascii=False),
        'tokens_used': 100,
        'input_token': 50,
        'output_token': 50,
    }
    with patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.call_llm',
        return_value=mock_resp,
    ), patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.get_llm_config',
        return_value={'api_base_url': 'http://mock', 'api_key': 'mock_key', 'max_tokens': 4096, 'temperature': 0.1},
    ), patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.reply_quality.resolve_model',
        return_value='gpt-4o-mini',
    ):
        result = evaluate_reply_quality(
            user_text="今天周几",
            ai_text="今天是周三",
        )
    expected_keys = {'score', 'reason', 'analysis', 'user_text', 'ai_text', 'message'}
    assert set(result.keys()) == expected_keys, f"多余字段: {set(result.keys()) - expected_keys}"
    print("[PASS] test_output_fields")


if __name__ == '__main__':
    test_build_prompt()
    test_evaluate_success()
    test_evaluate_from_chunks()
    test_evaluate_no_llm_config()
    test_evaluate_llm_parse_fail()
    test_evaluate_llm_exception()
    test_output_fields()
    print('\n=== 7/7 ALL PASSED ===')
