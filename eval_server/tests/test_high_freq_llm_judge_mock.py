# -*- coding: utf-8 -*-
"""测试 high_freq_llm_judge 新模式（user_case + ASR 分轮）

运行方式:
    cd eval_server && python tests/test_high_freq_llm_judge_mock.py
"""
import os
import sys
import json
from unittest.mock import patch

# 确保 eval_server 在 sys.path
os.environ.setdefault('PYTHONPATH', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────── mock 数据 ───────────

# 模拟 ai_wav 的 ASR 词级 chunks：3 轮模型回复，轮间间隔 > 2.0s
MOCK_AI_CHUNKS = [
    # 第1轮回复：0~4s
    {'text': '好的', 'timestamp': [0.5, 0.8]},
    {'text': '，', 'timestamp': [0.8, 0.9]},   # 标点（应被过滤）
    {'text': '春风又绿', 'timestamp': [1.0, 1.5]},
    {'text': '江南岸', 'timestamp': [1.6, 2.0]},
    # 间隔 2.5s → 第2轮
    {'text': '明月几时有', 'timestamp': [4.5, 5.0]},
    {'text': '把酒问青天', 'timestamp': [5.1, 5.5]},
    # 间隔 3.0s → 第3轮
    {'text': '不知细叶谁裁出', 'timestamp': [8.5, 9.0]},
    {'text': '二月春风似剪刀', 'timestamp': [9.1, 9.5]},
]

# 用户用例（3轮，按行分隔的字符串）
MOCK_USER_CASE = "用花字作飞花令\n用月字作飞花令\n用柳字作飞花令"

# mock LLM 返回
MOCK_LLM_RESPONSE = {
    'content': json.dumps({
        'rounds': [
            {'round': 1, 'pass': True, 'reason': '春风又绿江南岸，包含"花"字且为有效诗句'},
            {'round': 2, 'pass': True, 'reason': '明月几时有，包含"月"字且为有效词句'},
            {'round': 3, 'pass': False, 'reason': '回复未包含"柳"字'},
        ],
        'overall_pass_rate': 0.667,
    }, ensure_ascii=False),
    'tokens_used': 500,
    'input_token': 300,
    'output_token': 200,
}


def test_parse_user_case():
    """1. 测试 _parse_user_case"""
    from app.services.calculators.xiaoyi_metrics.turn_taking.high_freq_llm_judge import _parse_user_case

    # str 按行分割
    result = _parse_user_case(MOCK_USER_CASE)
    assert len(result) == 3, f"期望 3 轮，实际 {len(result)}"
    assert result[0] == '用花字作飞花令'
    assert result[1] == '用月字作飞花令'
    assert result[2] == '用柳字作飞花令'

    # list 直接使用
    result_list = _parse_user_case(['第一轮', '第二轮'])
    assert len(result_list) == 2

    # 空值
    assert _parse_user_case(None) == []
    assert _parse_user_case('') == []

    print("[PASS] _parse_user_case: str 按行分割 / list / 空值")
    return True


def test_parse_user_case_json():
    """1b. 测试 _parse_user_case 读取 JSON 文件"""
    import tempfile
    from app.services.calculators.xiaoyi_metrics.turn_taking.high_freq_llm_judge import _parse_user_case

    # 构造与实际格式一致的 JSON
    mock_json = {
        "rounds": [
            {
                "round_number": 1,
                "segments": [{
                    "audio": "test01.wav",
                    "query": "用户1：今天周几？",
                    "input_text": "今天周几？"
                }]
            },
            {
                "round_number": 2,
                "segments": [{
                    "audio": "test02.wav",
                    "query": "用户2：明天呢？",
                    "input_text": "明天呢？"
                }]
            },
            {
                "round_number": 3,
                "segments": [{
                    "audio": "test03.wav",
                    "query": "用户3：后天呢？",
                    "input_text": "后天呢？"
                }]
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(mock_json, f, ensure_ascii=False)
        json_path = f.name

    try:
        result = _parse_user_case(json_path)
        assert len(result) == 3, f"期望 3 轮，实际 {len(result)}"
        assert result[0] == '今天周几？', f"第1轮: {result[0]}"
        assert result[1] == '明天呢？', f"第2轮: {result[1]}"
        assert result[2] == '后天呢？', f"第3轮: {result[2]}"
    finally:
        os.unlink(json_path)

    print(f"[PASS] _parse_user_case: JSON 文件路径解析正确")
    print(f"  用例: {result}")
    return True


def test_segment_asr_rounds():
    """2. 测试 _segment_asr_rounds"""
    from app.services.calculators.xiaoyi_metrics.turn_taking.high_freq_llm_judge import _segment_asr_rounds

    rounds = _segment_asr_rounds(MOCK_AI_CHUNKS, seg_gap_s=0.7, round_gap_s=2.0)

    assert len(rounds) == 3, f"期望 3 轮，实际 {len(rounds)}"

    # 第1轮
    r1 = rounds[0]
    assert '春风又绿' in r1['text'], f"第1轮文本: {r1['text']}"
    assert r1['start_s'] == 0.5, f"第1轮起始: {r1['start_s']}"
    assert r1['end_s'] == 2.0, f"第1轮结束: {r1['end_s']}"

    # 第2轮
    r2 = rounds[1]
    assert '明月几时有' in r2['text'], f"第2轮文本: {r2['text']}"
    assert r2['start_s'] == 4.5, f"第2轮起始: {r2['start_s']}"

    # 第3轮
    r3 = rounds[2]
    assert '二月春风似剪刀' in r3['text'], f"第3轮文本: {r3['text']}"
    assert r3['start_s'] == 8.5, f"第3轮起始: {r3['start_s']}"

    # 空输入
    assert _segment_asr_rounds([]) == []

    print(f"[PASS] _segment_asr_rounds: 3轮分轮正确")
    print(f"  第1轮: [{r1['start_s']:.1f}-{r1['end_s']:.1f}] {r1['text']}")
    print(f"  第2轮: [{r2['start_s']:.1f}-{r2['end_s']:.1f}] {r2['text']}")
    print(f"  第3轮: [{r3['start_s']:.1f}-{r3['end_s']:.1f}] {r3['text']}")
    return True


def test_build_prompt_with_asr():
    """3. 测试 _build_prompt_with_asr"""
    from app.services.calculators.xiaoyi_metrics.turn_taking.high_freq_llm_judge import (
        _parse_user_case, _segment_asr_rounds, _build_prompt_with_asr,
    )

    user_cases = _parse_user_case(MOCK_USER_CASE)
    asr_rounds = _segment_asr_rounds(MOCK_AI_CHUNKS, seg_gap_s=0.7, round_gap_s=2.0)

    prompt = _build_prompt_with_asr(user_cases, asr_rounds, scenario_type='飞花令')

    # 验证 prompt 包含关键信息
    assert '飞花令' in prompt, "prompt 应包含场景类型"
    assert '用花字作飞花令' in prompt, "prompt 应包含第1轮用户用例"
    assert '用月字作飞花令' in prompt, "prompt 应包含第2轮用户用例"
    assert '用柳字作飞花令' in prompt, "prompt 应包含第3轮用户用例"
    assert '春风又绿江南岸' in prompt, "prompt 应包含第1轮 ASR 转写"
    assert '明月几时有' in prompt, "prompt 应包含第2轮 ASR 转写"
    assert '二月春风似剪刀' in prompt, "prompt 应包含第3轮 ASR 转写"
    assert 'overall_pass_rate' in prompt, "prompt 应包含 JSON 输出模板"

    print(f"[PASS] _build_prompt_with_asr: prompt 包含全部用例和 ASR 转写")
    return True


def test_evaluate_new_mode():
    """4. 测试新模式：user_case + ASR，mock call_llm"""
    from app.services.calculators.xiaoyi_metrics.turn_taking.high_freq_llm_judge import evaluate_high_freq_llm

    with patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.high_freq_llm_judge.call_llm',
        return_value=MOCK_LLM_RESPONSE,
    ):
        result = evaluate_high_freq_llm(
            ai_wav='/tmp/fake_ai.wav',
            user_case=MOCK_USER_CASE,
            ai_chunks=MOCK_AI_CHUNKS,  # 注入 ASR，不实际调用
            scenario_type='飞花令',
            model='qwen-plus',
        )

    # 基本结构
    assert result['enabled'] is True
    assert result['message'] == 'OK'
    assert result['model'] == 'qwen-plus'
    assert result['scenario_type'] == '飞花令'

    # 新模式独有字段
    assert 'asr_rounds' in result, "应包含 asr_rounds"
    assert 'user_cases' in result, "应包含 user_cases"
    assert len(result['asr_rounds']) == 3, f"asr_rounds 应 3 轮"
    assert len(result['user_cases']) == 3, f"user_cases 应 3 条"

    # per_round
    assert len(result['per_round']) == 3
    assert result['per_round'][0]['pass'] is True
    assert result['per_round'][2]['pass'] is False
    assert result['n_passed'] == 2
    assert result['n_failed'] == 1

    # token
    assert result['tokens_used'] == 500
    assert result['input_token'] == 300
    assert result['output_token'] == 200

    print(f"[PASS] evaluate_high_freq_llm 新模式: 3轮评判正确")
    print(f"  通过率: {result['overall_pass_rate']} ({result['n_passed']}/{len(result['per_round'])})")
    print(f"  tokens: {result['tokens_used']} (in={result['input_token']}, out={result['output_token']})")
    for rd in result['per_round']:
        status = 'PASS' if rd['pass'] else 'FAIL'
        print(f"  轮{rd['round']} [{status}] {rd['reason']}")
    return True


def test_evaluate_round_mismatch():
    """5. 测试 user_case 与 ASR 轮次不对齐"""
    from app.services.calculators.xiaoyi_metrics.turn_taking.high_freq_llm_judge import evaluate_high_freq_llm

    # user_case 2 轮，ASR 3 轮 → 应取 max=3 轮
    mock_resp = {
        'content': json.dumps({
            'rounds': [
                {'round': 1, 'pass': True, 'reason': 'OK'},
                {'round': 2, 'pass': True, 'reason': 'OK'},
                {'round': 3, 'pass': False, 'reason': '未提供用户用例'},
            ],
            'overall_pass_rate': 0.667,
        }, ensure_ascii=False),
        'tokens_used': 100, 'input_token': 60, 'output_token': 40,
    }

    with patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.high_freq_llm_judge.call_llm',
        return_value=mock_resp,
    ):
        result = evaluate_high_freq_llm(
            ai_wav='/tmp/fake.wav',
            user_case="第一轮\n第二轮",  # 只有2轮
            ai_chunks=MOCK_AI_CHUNKS,     # ASR 有3轮
            scenario_type='自定义',
            scenario_rules='测试规则',
        )

    assert result['n_rounds'] == 3, f"期望 3 轮(max)，实际 {result['n_rounds']}"
    assert len(result['per_round']) == 3

    print(f"[PASS] 轮次不对齐: user_case=2, asr=3, 取 max=3")
    return True


def test_evaluate_llm_parse_fail():
    """6. 测试 LLM 输出解析失败"""
    from app.services.calculators.xiaoyi_metrics.turn_taking.high_freq_llm_judge import evaluate_high_freq_llm

    with patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.high_freq_llm_judge.call_llm',
        return_value={'content': 'not a json', 'tokens_used': 10, 'input_token': 5, 'output_token': 5},
    ):
        result = evaluate_high_freq_llm(
            ai_wav='/tmp/fake.wav',
            user_case="测试",
            ai_chunks=MOCK_AI_CHUNKS,
        )

    assert result['message'] == 'LLM 输出解析失败'
    assert result['per_round'] == []

    print(f"[PASS] LLM 解析失败: message={result['message']}")
    return True


def test_calculator_integration():
    """7. 测试 HighFreqLlmJudgeCalculator 集成"""
    from app.services.calculators.xiaoyi_metrics.turn_taking.strategy import HighFreqLlmJudgeCalculator

    task_params = {
        'ai_wav': '/tmp/fake_ai.wav',
        'user_case': MOCK_USER_CASE,
        'scenario_type': '飞花令',
        'round_number': 0,
    }

    calc = HighFreqLlmJudgeCalculator()

    # validate
    ok, err = calc.validate(task_params)
    assert ok, f"validate 失败: {err}"

    # prepare_params
    params = calc.prepare_params(task_params)
    assert params['user_case'] == MOCK_USER_CASE
    assert params['ai_wav'] == '/tmp/fake_ai.wav'
    assert params['scenario_type'] == '飞花令'

    # calculate with mock
    params['_shared_asr'] = {'ai_word_chunks': MOCK_AI_CHUNKS}

    with patch(
        'app.services.calculators.xiaoyi_metrics.turn_taking.high_freq_llm_judge.call_llm',
        return_value=MOCK_LLM_RESPONSE,
    ):
        result = calc.calculate(params)

    assert result['message'] == 'OK'
    assert result['n_rounds'] == 3
    assert result['n_passed'] == 2
    assert result['n_failed'] == 1

    print(f"[PASS] HighFreqLlmJudgeCalculator 集成: validate → prepare → calculate")
    return True


if __name__ == '__main__':
    print("=" * 70)
    print("测试 high_freq_llm_judge 新模式（user_case + ASR）")
    print("=" * 70)

    tests = [
        test_parse_user_case,
        test_parse_user_case_json,
        test_segment_asr_rounds,
        test_build_prompt_with_asr,
        test_evaluate_new_mode,
        test_evaluate_round_mismatch,
        test_evaluate_llm_parse_fail,
        test_calculator_integration,
    ]

    results = []
    for test_fn in tests:
        print(f"\n── {test_fn.__name__} ──")
        try:
            ok = test_fn()
            results.append((test_fn.__name__, ok))
        except Exception as e:
            import traceback
            traceback.print_exc()
            results.append((test_fn.__name__, False))
            print(f"[FAIL] {e}")

    print("\n" + "=" * 70)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n  {passed}/{total} 通过")
    print("=" * 70)
    sys.exit(0 if passed == total else 1)
