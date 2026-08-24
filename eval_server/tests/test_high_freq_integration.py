# -*- coding: utf-8 -*-
"""测试 high_freq_turn_taking 和 high_freq_llm_judge 是否正确集成到 calculate_xiaoyi_metrics

运行方式:
    cd eval_server && python tests/test_high_freq_integration.py
"""
import os
import sys
import json
from unittest.mock import patch

# 确保 eval_server 在 sys.path
os.environ.setdefault('PYTHONPATH', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_import():
    """1. 验证模块导入正常"""
    from app.services.calculators.xiaoyi_metrics.turn_taking import (
        calculate_xiaoyi_metrics,
        calculate_high_freq_turn_taking_metrics,
        calculate_high_freq_llm_judge,
        compute_high_freq_turn_taking,
    )
    print("[PASS] 导入成功: calculate_xiaoyi_metrics, calculate_high_freq_turn_taking_metrics, calculate_high_freq_llm_judge, compute_high_freq_turn_taking")
    return True


def test_compute_high_freq_turn_taking():
    """2. 验证 compute_high_freq_turn_taking 核心逻辑"""

    # 构造 mock ASR chunks：3 轮用户提问 + 3 轮 AI 回复（共享时间轴）
    user_chunks = [
        {'text': '你好', 'timestamp': [1.0, 1.5]},
        {'text': '飞花令', 'timestamp': [2.0, 2.5]},
        {'text': '春风', 'timestamp': [10.0, 10.5]},
        {'text': '花的', 'timestamp': [11.0, 11.3]},
        {'text': '秋月', 'timestamp': [20.0, 20.5]},
        {'text': '月色', 'timestamp': [21.0, 21.3]},
    ]
    ai_chunks = [
        {'text': '欢迎', 'timestamp': [0.0, 0.8]},        # 开场白（不应被消费）
        {'text': '好的', 'timestamp': [3.0, 3.5]},         # 第1轮回复
        {'text': '春风又绿', 'timestamp': [12.0, 12.5]},   # 第2轮回复
        {'text': '月色如水', 'timestamp': [22.0, 22.5]},   # 第3轮回复
    ]

    from app.services.calculators.xiaoyi_metrics.turn_taking import compute_high_freq_turn_taking

    result = compute_high_freq_turn_taking(user_chunks, ai_chunks)

    assert result['n_user_segments'] == 3, f"期望 3 个用户段，实际 {result['n_user_segments']}"
    assert result['n_ai_segments'] == 4, f"期望 4 个 AI 段，实际 {result['n_ai_segments']}"
    assert result['n_matched_rounds'] == 3, f"期望 3 轮匹配，实际 {result['n_matched_rounds']}"
    assert result['n_missed_rounds'] == 0, f"期望 0 轮未匹配，实际 {result['n_missed_rounds']}"
    assert result['n_unmatched_ai_segments'] == 1, f"期望 1 个未消费 AI 段（开场白），实际 {result['n_unmatched_ai_segments']}"
    assert result['avg_response_latency_s'] is not None, "avg_response_latency_s 不应为 None"

    # 第1轮：用户段 [1.0, 2.5] → AI [3.0, 3.5]，时延 = 3.0 - 2.5 = 0.5s
    r1 = result['per_round'][0]
    assert r1['response_latency_s'] == 0.5, f"第1轮时延期望 0.5s，实际 {r1['response_latency_s']}s"

    # 第2轮：用户段 [10.0, 11.3] → AI [12.0, 12.5]，时延 = 12.0 - 11.3 = 0.7s
    r2 = result['per_round'][1]
    assert r2['response_latency_s'] == 0.7, f"第2轮时延期望 0.7s，实际 {r2['response_latency_s']}s"

    # 第3轮：用户段 [20.0, 21.3] → AI [22.0, 22.5]，时延 = 22.0 - 21.3 = 0.7s
    r3 = result['per_round'][2]
    assert r3['response_latency_s'] == 0.7, f"第3轮时延期望 0.7s，实际 {r3['response_latency_s']}s"

    print(f"[PASS] compute_high_freq_turn_taking 核心逻辑验证通过")
    print(f"  轮数={result['n_rounds']} 匹配={result['n_matched_rounds']} "
          f"未匹配={result['n_missed_rounds']} 未消费AI={result['n_unmatched_ai_segments']}")
    print(f"  平均时延={result['avg_response_latency_ms']:.0f}ms "
          f"最小={result['min_response_latency_s']}s 最大={result['max_response_latency_s']}s")
    return True


def test_calculate_xiaoyi_metrics_integration():
    """3. 验证 calculate_xiaoyi_metrics 返回结果包含 high_freq_turn_taking 和 high_freq_llm_judge 键"""

    # mock ASR 调用，避免真实网络请求
    mock_user_chunks = [
        {'text': '你好', 'timestamp': [1.0, 1.5]},
        {'text': '飞花令', 'timestamp': [2.0, 2.5]},
        {'text': '春风', 'timestamp': [10.0, 10.5]},
        {'text': '花的', 'timestamp': [11.0, 11.3]},
    ]
    mock_ai_chunks = [
        {'text': '欢迎', 'timestamp': [0.0, 0.8]},
        {'text': '好的', 'timestamp': [3.0, 3.5]},
        {'text': '春风又绿', 'timestamp': [12.0, 12.5]},
    ]
    mock_main_chunks = [
        {'text': '测试', 'timestamp': [0.5, 1.0]},
    ]

    import app.services.calculators.xiaoyi_metrics.turn_taking as tt_module
    from app.services.calculators.xiaoyi_metrics.turn_taking import calculate_xiaoyi_metrics

    task_params = {
        'record_file': '/tmp/fake.wav',
        'user_wav': '/tmp/fake_user.wav',
        'ai_wav': '/tmp/fake_ai.wav',
        'rounds': [{'query': '你好', 'answer': '好的'}],
        'offset_ms': 40,
    }

    with patch.object(tt_module, '_get_asr_chunks', side_effect=lambda w: mock_user_chunks if 'user' in w else mock_ai_chunks), \
         patch.object(tt_module, '_get_asr_word_chunks', return_value=[]), \
         patch('app.utils.asr_adapator.call_modelscope_asr_word', return_value={'text': '', 'chunks': mock_main_chunks}), \
         patch('app.utils.asr_adapator.parse_result', return_value={'text': '', 'chunks': mock_main_chunks}), \
         patch.object(tt_module, 'calculate_high_freq_llm_judge',
               side_effect=lambda tp: {'enabled': False, 'message': 'mocked', 'n_rounds': 0, 'per_round': []}):

        result = calculate_xiaoyi_metrics(task_params)

    assert 'high_freq_turn_taking' in result, "结果中缺少 high_freq_turn_taking 键"
    assert 'high_freq_llm_judge' in result, "结果中缺少 high_freq_llm_judge 键"

    hf = result['high_freq_turn_taking']
    assert isinstance(hf, dict), "high_freq_turn_taking 应为 dict"
    assert 'n_rounds' in hf, "high_freq_turn_taking 应包含 n_rounds"
    assert 'per_round' in hf, "high_freq_turn_taking 应包含 per_round"

    hl = result['high_freq_llm_judge']
    assert isinstance(hl, dict), "high_freq_llm_judge 应为 dict"
    assert hl.get('message') == 'mocked', f"high_freq_llm_judge message 期望 'mocked'，实际 {hl.get('message')}"

    print(f"[PASS] calculate_xiaoyi_metrics 集成验证通过")
    print(f"  结果键: {list(result.keys())}")
    print(f"  high_freq_turn_taking: n_rounds={hf.get('n_rounds')} "
          f"matched={hf.get('n_matched_rounds')} "
          f"avg_latency={hf.get('avg_response_latency_s')}s")
    print(f"  high_freq_llm_judge: enabled={hl.get('enabled')} msg={hl.get('message')}")
    return True


def test_task_service_no_high_freq_branch():
    """4. 验证 task_service.py 中不再有独立的 high_freq_turn_taking / high_freq_llm_judge elif 分支"""
    import inspect
    from app.services.task_service import TaskService

    source = inspect.getsource(TaskService.calculate)
    assert "'high_freq_turn_taking'" not in source, "task_service 仍包含 high_freq_turn_taking 分支"
    assert "'high_freq_llm_judge'" not in source, "task_service 仍包含 high_freq_llm_judge 分支"
    assert "CALCULATORS" in source, "task_service 应使用 CALCULATORS 注册表"

    print("[PASS] task_service.py 已移除独立 high_freq 分支，统一由 CALCULATORS 注册表处理")
    return True


if __name__ == '__main__':
    print("=" * 70)
    print("测试 high_freq_turn_taking 和 high_freq_llm_judge 集成到 calculate_xiaoyi_metrics")
    print("=" * 70)

    results = []
    for test_fn in [
        test_import,
        test_compute_high_freq_turn_taking,
        test_calculate_xiaoyi_metrics_integration,
        test_task_service_no_high_freq_branch,
    ]:
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
