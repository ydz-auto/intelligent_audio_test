# -*- coding: utf-8 -*-
"""拒识裁判 is_reject=false 直接跳过评估测试（mock LLM，不发真实请求）。

回归：任务417 中 is_reject=false 的轮次仍被当作拒识轮评估，
顶层结果泄漏 rate/rate_*_count 等拒识指标，平台侧误展示/误统计。
修复后：
  1. 逐轮评估（round_number 有值）目标轮 is_reject=false → 不调 LLM、不产出指标
  2. 整体评估全部轮 is_reject=false → 顶层无拒识指标
  3. 混合轮 → 非拒识轮 per_round 保留跳过占位，拒识轮正常聚合
"""
import json

import pytest

from app.services.calculators.xiaoyi_metrics.env_judge import rejection_judge as rj_mod
from app.services.calculators.xiaoyi_metrics.env_judge.strategy import RejectionJudgeCalculator
from app.services.task_service import TaskService


@pytest.fixture
def fake_llm(monkeypatch):
    """拦截拒识裁判的 LLM 调用：返回固定 behavior=回应，calls 记录调用次数。"""
    monkeypatch.setattr(rj_mod.os.path, 'isfile', lambda path: bool(path))
    monkeypatch.setattr(rj_mod, 'get_llm_config',
                        lambda: {'max_tokens': 100, 'temperature': 0.0})
    monkeypatch.setattr(rj_mod, 'resolve_model', lambda **kw: 'test-model')
    monkeypatch.setattr(rj_mod, 'get_asr_chunks', lambda *a, **k: [])
    monkeypatch.setattr(rj_mod, 'build_interaction_text', lambda *a, **k: '')
    monkeypatch.setattr(rj_mod, 'get_asr_text', lambda *a, **k: '')

    def fake(**kwargs):
        fake.calls += 1
        return {'content': json.dumps(
            getattr(fake, 'content', {'behavior': '回应', 'reason': 'mock'}),
            ensure_ascii=False),
            'tokens_used': 10, 'input_token': 5, 'output_token': 5}

    fake.calls = 0
    monkeypatch.setattr(rj_mod, 'call_llm_api', fake)
    return fake

def _params(rounds, round_number=None):
    p = {'rounds': rounds}
    if round_number is not None:
        p['round_number'] = round_number
    return p


def _rd(is_reject):
    return {'ai_wav': 'ai.wav', 'user_wav': 'user.wav',
            'is_reject': is_reject, 'timing': '回复过程中',
            'is_single_round': False}


def test_per_round_is_reject_false_skips_evaluation(fake_llm):
    """逐轮评估：目标轮 is_reject=false → 不调 LLM、无任何拒识指标。"""
    result = TaskService.calculate(
        'reject_judge', _params([_rd(False)], round_number=0))
    assert result.get('message') == '跳过: 非拒识轮(is_reject=false)'
    assert result.get('rate') is None
    assert 'rate_failure' not in result and 'rate_failure_count' not in result
    assert 'success_silent_recover' not in result
    assert fake_llm.calls == 0


def test_overall_all_skipped_no_metric_leak(fake_llm):
    """整体评估：唯一轮 is_reject=false → 顶层不泄漏拒识指标。"""
    result = TaskService.calculate('reject_judge', _params([_rd(False)]))
    assert result.get('message') == '跳过: 非拒识轮(is_reject=false)'
    assert 'rate_failure' not in result and 'rate_success_count' not in result
    assert result.get('per_round') == [
        {'round_number': 0, 'message': '跳过: 非拒识轮(is_reject=false)'}]
    assert fake_llm.calls == 0


def test_mixed_rounds_skip_and_aggregate(fake_llm):
    """混合轮：轮0=非拒识跳过占位，轮1=拒识正常评估并聚合。"""
    result = TaskService.calculate(
        'reject_judge', _params([_rd(False), _rd(True)]))
    assert result.get('n_reject_rounds') == 1
    assert result.get('n_rate_failure') == 1
    assert result.get('n_failure_reply_respond') == 1
    assert result.get('per_round', [{}])[0] == {
        'round_number': 0, 'message': '跳过: 非拒识轮(is_reject=false)'}
    assert fake_llm.calls >= 1


def test_is_reject_true_still_evaluates(fake_llm):
    """is_reject=true（或缺省默认 true）：正常评估。"""
    result = TaskService.calculate(
        'reject_judge', _params([_rd(True)], round_number=0))
    assert result.get('rate') == '拒识失败'
    assert result.get('n_rate_failure') == 1
    assert fake_llm.calls >= 1

    fake_llm.calls = 0
    result = TaskService.calculate(
        'reject_judge', _params([{'ai_wav': 'ai.wav', 'user_wav': 'user.wav'}],
                                round_number=0))
    assert result.get('rate') == '拒识失败'  # 缺省默认参与评估
    assert fake_llm.calls >= 1


def test_string_false_also_skips(fake_llm):
    """字符串 'false'（multipart 常见形态）同样跳过。"""
    result = TaskService.calculate(
        'reject_judge', _params([_rd('false')], round_number=0))
    assert result.get('message') == '跳过: 非拒识轮(is_reject=false)'
    assert fake_llm.calls == 0


def test_skip_depends_on_is_reject_not_judge_rate(fake_llm, monkeypatch):
    """跳过只取决于 is_reject=false，与 LLM 本会判出的 rate 无关。

    即便 LLM 会判 behavior=静默（timing=静默 → rate=拒识成功），
    只要 is_reject=false 就整体跳过、不调 LLM。
    """
    fake_llm.content = json.dumps({'behavior': '静默', 'reason': 'mock'},
                                   ensure_ascii=False)
    params = _params([{
        'ai_wav': 'ai.wav', 'user_wav': 'user.wav',
        'is_reject': False, 'timing': '静默', 'is_single_round': False,
    }], round_number=0)
    result = TaskService.calculate('reject_judge', params)
    assert result.get('message') == '跳过: 非拒识轮(is_reject=false)'
    assert result.get('rate') is None
    assert fake_llm.calls == 0
