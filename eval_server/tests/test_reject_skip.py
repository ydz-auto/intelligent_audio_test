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
    """拦截拒识裁判的 LLM/ASR 调用：返回固定判定，calls 记录调用次数。

    ASR 按文件名返回假词级 chunks（user.wav=意图段+1 个干扰段，ai.wav=模型段），
    使文本整体评估的轮次切分（参考打断）能产出 1 个拒识轮。
    LLM 返回 round_details（timing+behavior+reason，新文本模态契约）。
    """
    monkeypatch.setattr(rj_mod.os.path, 'isfile', lambda path: bool(path))
    monkeypatch.setattr(rj_mod, 'get_llm_config',
                        lambda: {'max_tokens': 100, 'temperature': 0.0})
    monkeypatch.setattr(rj_mod, 'resolve_model', lambda **kw: 'test-model')

    def _chunks(path):
        name = str(path or '')
        if 'ai' in name:
            return [{'text': '好的', 'timestamp': [2.0, 4.0]},
                    {'text': '没问题', 'timestamp': [6.0, 8.0]}]
        return [{'text': '你好', 'timestamp': [0.0, 1.0]},
                {'text': '嗯', 'timestamp': [5.0, 5.5]}]

    monkeypatch.setattr(rj_mod, 'get_asr_chunks', _chunks)
    monkeypatch.setattr(rj_mod, 'build_interaction_text', lambda *a, **k: '')
    monkeypatch.setattr(rj_mod, 'get_asr_text', lambda *a, **k: '')

    def fake(**kwargs):
        fake.calls += 1
        return {'content': json.dumps(
            getattr(fake, 'content', {'behavior': '回应', 'reason': 'mock',
                                      'round_details': [
                                          {'round': 1, 'timing': '回复过程中',
                                           'behavior': '回应', 'reason': 'mock'}]}),
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


def test_mixed_rounds_reject_first_not_skipped(fake_llm):
    """混合轮且拒识轮在前、意图轮在最后：整体评估不得整例跳过。

    回归：run() 用 _is_reject_round(task_params)（多轮时按目标轮=最后一轮取数）
    判断是否跳过，最后一轮 is_reject=false 时把整例误判为跳过，而逐轮切片照常评估
    前面的拒识轮 → 整体 TRD 为空、逐轮 TRD 有值，报告主/子维度口径错乱。
    """
    result = TaskService.calculate(
        'reject_judge', _params([_rd(True), _rd(False)]))
    assert result.get('message') != '跳过: 非拒识轮(is_reject=false)'
    assert result.get('n_reject_rounds') == 1
    assert result.get('n_rate_failure') == 1
    assert result.get('n_failure_reply_respond') == 1
    assert result.get('per_round', [{}])[0].get('round_number') == 0
    assert result.get('per_round', [{}])[1] == {
        'round_number': 1, 'message': '跳过: 非拒识轮(is_reject=false)'}
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


def test_per_round_labels_request_round_number(fake_llm):
    """逐轮评估（round_number 有值、rounds 被平台切成单轮）：
    per_round 的 round_number 必须用请求级 round_number（用例级索引），
    不能用切片本地下标 0——否则该轮结果被标成 0，平台 _overwrite_round_results
    落库到 round_number=0 的 TRD，导致 is_reject=false 的第一轮误显示拒识数据。

    rounds 里没有 'round' 字段（multipart 渲染模板不含该键），
    rd.get('round') 取不到时必须回退请求级 round_number。
    """
    result = TaskService.calculate(
        'reject_judge', _params([_rd(True)], round_number=1))
    assert result.get('per_round', [{}])[0].get('round_number') == 1
    assert result.get('n_reject_rounds') == 1
    assert fake_llm.calls >= 1


def test_per_round_skipped_labels_request_round_number(fake_llm):
    """逐轮评估且该轮 is_reject=false：跳过占位项的 round_number 同样用请求级轮号。"""
    result = TaskService.calculate(
        'reject_judge', _params([_rd(False)], round_number=1))
    assert result.get('per_round', [{}])[0] == {
        'round_number': 1, 'message': '跳过: 非拒识轮(is_reject=false)'}
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
