# -*- coding: utf-8 -*-
"""turn_eval TOR 话术可区分性（VEGA-58，纯函数，无 LLM/无 IO/无网络）。

缺陷本体：`tor.py:78` 的「真·取数空」诊断串（`ai_chunks 为空，无法计算 TOR`）
被两处**业务判定/兜底**路径复用，导致两种语义共用一句话术、无法分桶：

① `strategy.py` 兜底字面量凭空造「无 AI 回复」（该轮 `误接管` ⇒ `tor=None` 是合法的）；
② `turn_evaluation.py` 的「无 AI 回复 ⇒ 判为未接管」短路分支显式传空列表调 `compute_tor`。

本文件锁死三条验收线：
- 兜底/业务判定产出的 message 不再出现「无 AI 回复」，且不复用 tor.py 的诊断串；
- `tor.py` 的两条「真·取数空」全局串**逐字未变**（真·取数空仍可被单独查出）；
- 两列判据仍可分桶：`真·取数空` 与 `业务判定或兜底话术` 字符串集合**不相交**，
  且键数判据（4 键=兜底字面量 / 6 键=compute_tor 真实返回）仍成立。
"""


_USER_CHUNKS = [
    {'text': '今天', 'timestamp': [0.0, 0.5]},
    {'text': '天气', 'timestamp': [0.5, 1.0]},
]

# tor.py 的两条「真·取数空」全局串（VEGA-58 明确要求不得改动）
_TOR_EMPTY_AI_MSG = 'ai_chunks 为空，无法计算 TOR'
_TOR_EMPTY_USER_MSG = 'user_chunks 为空，无法计算 TOR'


def _tor(user_chunks=None, ai_chunks=None):
    from app.services.calculators.xiaoyi_metrics.turn_taking.tor import compute_tor
    return compute_tor(_USER_CHUNKS if user_chunks is None else user_chunks,
                       _USER_CHUNKS if ai_chunks is None else ai_chunks)


def _misunderstand_turn():
    """「误接管」轮：tor=None 是合法的（该轮本就不算 TOR）"""
    return {
        'round_number': 0,
        'turn_index': 0,
        'classification': '误接管',
        'false_takeover': {'false_takeover': 1, 'reason': '截取用户中间不完整片段'},
        'tor': None,
        'takeover_judge': None,
    }


# ─────────── ① tor.py 全局串逐字未变 ───────────

def test_tor_global_empty_messages_unchanged():
    assert _tor(ai_chunks=[])['message'] == _TOR_EMPTY_AI_MSG
    assert _tor(user_chunks=[])['message'] == _TOR_EMPTY_USER_MSG


def test_compute_tor_real_return_has_six_keys():
    """键数判据：compute_tor 真实返回 6 键（含 hit_words / user_last_word_end_s）"""
    empty_ai = _tor(ai_chunks=[])
    assert len(empty_ai) == 6
    assert 'hit_words' in empty_ai and 'user_last_word_end_s' in empty_ai


# ─────────── ② 短路分支（turn_evaluation）不再复用「取数空」串 ───────────

def test_no_ai_reply_shortcut_tor_message_distinct():
    """`未接管` 轮短路分支：message 说清「为什么没算」，且与真·取数空串不同"""
    from app.services.calculators.xiaoyi_metrics.turn_eval.turn_evaluation import (
        TurnInfo, classify_turn_comprehensive,
    )

    turn = TurnInfo(turn_index=0, user_chunks=_USER_CHUNKS, ai_chunks=[],
                    user_start_s=0.0, user_end_s=1.0)
    cls = classify_turn_comprehensive(turn)  # 无 ai_chunks ⇒ 短路，不触发 LLM

    assert cls.classification == '未接管'
    tor = cls.tor
    assert tor['message'] != _TOR_EMPTY_AI_MSG
    assert tor['message'] != _TOR_EMPTY_USER_MSG
    assert '不计算 TOR' in tor['message']
    # 键形与 compute_tor 的空 chunks 早返回一致（6 键，仍是「真实返回」列）
    assert len(tor) == 6
    assert tor['tor'] == 0 and tor['n_words'] == 0 and tor['duration'] == 0.0


# ─────────── ③ strategy 兜底字面量不再凭空造「无 AI 回复」 ───────────

def test_top_level_tor_fallback_message(monkeypatch):
    """顶层兼容字段 `results['tor']` 兜底：说清分类，不再写「无 AI 回复」"""
    from app.services.calculators.xiaoyi_metrics.turn_eval.strategy import TurnEvalCalculator

    calc = TurnEvalCalculator()
    monkeypatch.setattr(
        calc, '_eval_one_round',
        lambda *a, **kw: ([_misunderstand_turn()], 0, 0, 1, list(_USER_CHUNKS), []),
    )
    result = calc.calculate({'task_params': {'rounds': [{}]}, '_shared_asr': {'_injected': True}})

    tor = result['tor']
    assert '无 AI 回复' not in tor['message']
    assert tor['message'] == '分类为误接管，不计算 TOR'
    # 兜底字面量仍是 4 键（键数判据不变）
    assert len(tor) == 4
    assert set(tor) == {'tor', 'n_words', 'duration', 'message'}


def test_per_round_tor_fallback_message():
    """原生 per_round 投影的 `tor` 兜底：同款措辞"""
    from app.services.calculators.xiaoyi_metrics.turn_eval.strategy import TurnEvalCalculator

    per_round = TurnEvalCalculator._build_per_round(1, [_misunderstand_turn()])
    tor = per_round[0]['tor']
    assert '无 AI 回复' not in tor['message']
    assert tor['message'] == '分类为误接管，不计算 TOR'
    assert len(tor) == 4


# ─────────── ④ 两列判据可分桶 ───────────

def test_two_buckets_share_no_string():
    """`真·取数空` 与 `业务判定或兜底话术` 不再共用字符串"""
    from app.services.calculators.xiaoyi_metrics.turn_eval.strategy import TurnEvalCalculator
    from app.services.calculators.xiaoyi_metrics.turn_eval.turn_evaluation import (
        TurnInfo, classify_turn_comprehensive,
    )

    fetch_empty = {
        _tor(ai_chunks=[])['message'],
        _tor(user_chunks=[])['message'],
    }
    business = {
        classify_turn_comprehensive(
            TurnInfo(0, _USER_CHUNKS, [], 0.0, 1.0)
        ).tor['message'],
        TurnEvalCalculator._build_per_round(1, [_misunderstand_turn()])[0]['tor']['message'],
    }
    assert fetch_empty & business == set()
    # 兜底字面量（误接管轮 tor=None）里的「无 AI 回复」与事实相反，必须消失；
    # 短路分支（未接管轮）里「无 AI 回复」是**事实**，保留（同 payload 的
    # false_takeover.reason / takeover_judge.reason 亦如此表述）。
    fallback = TurnEvalCalculator._build_per_round(1, [_misunderstand_turn()])[0]['tor']['message']
    assert '无 AI 回复' not in fallback
