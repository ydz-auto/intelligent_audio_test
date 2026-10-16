# -*- coding: utf-8 -*-
"""VEGA-58 独立验收（测试工程师）：turn_eval TOR 话术可区分性。

与 devC 交付的 `test_turn_eval_tor_message_distinguishable.py` **相互独立**：
本文件不复用其夹具/断言，改为从三个独立角度取证，且刻意包含
**源码结构级（AST）** 与 **真实冻结 payload 回放** 两类 devC 未覆盖的角度。

取证角度
--------
A. 源码结构级（AST/文本）——抓「只改了一处调用方、漏了另一处」这类不完整修复：
   A1 `tor.py:73`/`:78` 两条「真·取数空」全局串逐字仍在，且 `compute_tor` 原样返回；
   A2 `turn_eval/strategy.py` 源码中**不再出现**「无 AI 回复」字面量；
   A3 `classify_turn_comprehensive` 的 `if not turn.ai_chunks:` 短路块内
      **不再有** `compute_tor` 调用（改调纯构造函数）。
B. 行为级——三条验收线 + 键数分桶判据 + 未受影响路径的回归：
   B1 误接管轮（`tor=None`）兜底 message 不含「无 AI 回复」且 4 键；
   B2 未接管短路分支 message ≠ 两条全局串，且与 `compute_tor` 空 chunks 早返回**键形一致**；
   B3 真·取数空仍可被单独查出，且与业务判定/兜底话术字符串集合**不相交**；
   B4 接管轮（`tor` 非 None）走原路，兜底改动**不影响**正常结果；
   B5 第三形态（`跳过: …` 1 键项）未被本卡改动波及。
C. 真实冻结数据回放——用 task 420 里**触发闸门的那 6 行**（JG0002）的
   真实 `turn_detail` 形状回放，钉住「输出与事实相反」这一点：
   该轮 `has_ai_reply=True`、`ai_start_s/ai_end_s` 均有值，而兜底曾写「无 AI 回复」。

纯函数，无 LLM / 无 IO / 无网络 / 无 DB。
"""

import ast
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_EVAL_ROOT = os.path.dirname(_HERE)
_TURN_EVAL = os.path.join(_EVAL_ROOT, 'app', 'services', 'calculators',
                          'xiaoyi_metrics', 'turn_eval')
_TOR_PY = os.path.join(_EVAL_ROOT, 'app', 'services', 'calculators',
                       'xiaoyi_metrics', 'turn_taking', 'tor.py')

# tor.py 的两条「真·取数空」全局串（本卡硬约束：逐字不得改）
_TOR_EMPTY_USER_MSG = 'user_chunks 为空，无法计算 TOR'
_TOR_EMPTY_AI_MSG = 'ai_chunks 为空，无法计算 TOR'

_USER_CHUNKS = [
    {'text': '影院的', 'timestamp': [0.0, 0.5]},
    {'text': 'imax', 'timestamp': [0.5, 1.0]},
    {'text': '是什', 'timestamp': [1.0, 1.5]},
]
_AI_CHUNKS = [
    {'text': 'IMAX', 'timestamp': [3.69, 4.0]},
    {'text': '是一种', 'timestamp': [4.0, 4.4]},
]


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _compute_tor(user_chunks=None, ai_chunks=None):
    from app.services.calculators.xiaoyi_metrics.turn_taking.tor import compute_tor
    return compute_tor(_USER_CHUNKS if user_chunks is None else user_chunks,
                       _AI_CHUNKS if ai_chunks is None else ai_chunks)


# ══════════════════════════════════════════════════════════════════
#  A. 源码结构级
# ══════════════════════════════════════════════════════════════════

def test_A1_tor_global_empty_strings_verbatim_in_source_and_runtime():
    """A1：`tor.py:73`/`:78` 两条全局串在**源码**与**运行时**都逐字未变。

    源码级（而非仅行为级）断言，才能证明「真·取数空」这个诊断信号
    不是被顺手改掉、而是被完整保留。
    """
    src = _read(_TOR_PY)
    assert f"result['message'] = '{_TOR_EMPTY_USER_MSG}'" in src, \
        'tor.py 的 user_chunks 空串被改动了（本卡硬约束：不得改）'
    assert f"result['message'] = '{_TOR_EMPTY_AI_MSG}'" in src, \
        'tor.py 的 ai_chunks 空串被改动了（本卡硬约束：不得改）'
    # 运行时逐字
    assert _compute_tor(ai_chunks=[])['message'] == _TOR_EMPTY_AI_MSG
    assert _compute_tor(user_chunks=[])['message'] == _TOR_EMPTY_USER_MSG


def test_A2_no_ai_reply_literal_gone_from_turn_eval_strategy_source():
    """A2：`turn_eval/strategy.py` 源码里不再有「无 AI 回复」字面量。

    兜底字面量若只改了一处（`:585` 或 `:689`），另一处仍会残留该串；
    源码级扫描可一次性覆盖全部兜底点，不依赖测试是否恰好构造到那条分支。
    """
    src = _read(os.path.join(_TURN_EVAL, 'strategy.py'))
    assert '无 AI 回复' not in src, \
        'turn_eval/strategy.py 仍残留「无 AI 回复」字面量（兜底点未改全）'


def test_A3_short_circuit_no_longer_calls_compute_tor_with_empty_ai():
    """A3：`classify_turn_comprehensive` 的「无 ai_chunks」短路块内不再调 `compute_tor`。

    这是缺陷 ② 的病灶：显式传空列表 ⇒ 复用 `tor.py:78` 的全局串。
    用 AST 定位该 if 块（而非按行号），避免行号漂移导致断言失效。
    """
    src = _read(os.path.join(_TURN_EVAL, 'turn_evaluation.py'))
    tree = ast.parse(src)

    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef)
               and n.name == 'classify_turn_comprehensive'), None)
    assert fn is not None, '未找到 classify_turn_comprehensive'

    # 找 `if not turn.ai_chunks:` 的 If 节点
    short_circuits = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        t = node.test
        if (isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not)
                and isinstance(t.operand, ast.Attribute)
                and t.operand.attr == 'ai_chunks'):
            short_circuits.append(node)
    assert short_circuits, '未找到 `if not turn.ai_chunks:` 短路块'

    for sc in short_circuits:
        called = {c.func.attr if isinstance(c.func, ast.Attribute)
                  else getattr(c.func, 'id', None)
                  for c in ast.walk(sc) if isinstance(c, ast.Call)}
        assert 'compute_tor' not in called, \
            '短路块内仍在调 compute_tor（会复用 tor.py 的「真·取数空」串）'
        assert '_build_no_ai_reply_tor' in called, \
            '短路块未改调 _build_no_ai_reply_tor'


# ══════════════════════════════════════════════════════════════════
#  B. 行为级
# ══════════════════════════════════════════════════════════════════

def _calc_with_turns(turn_results):
    """把给定的 turn_results 灌进 TurnEvalCalculator.calculate 的兜底投影。"""
    from app.services.calculators.xiaoyi_metrics.turn_eval.strategy import TurnEvalCalculator
    calc = TurnEvalCalculator()
    calc._eval_one_round = lambda *a, **kw: (
        list(turn_results), 0, 0, 1, list(_USER_CHUNKS), list(_AI_CHUNKS),
    )
    return calc.calculate({'task_params': {'rounds': [{}]}, '_shared_asr': {'_injected': True}})


def _real_jg0002_turn():
    """C 段回放用：task 420 / row 368442-368447（JG0002）的真实 turn_detail 形状。

    该 6 行正是闸门 `LIKE '%无 AI 回复%'` 命中的 `/tor/message` 列，
    其真实 payload 里 `has_ai_reply=true`、`ai_start_s=3.69`、`ai_end_s=23.305`，
    而兜底却写「无 AI 回复」——**输出与事实相反**。
    """
    return {
        'turn_index': 0,
        'round_number': 0,
        'classification': '误接管',
        'false_takeover': {'false_takeover': 1, 'reason': '截取用户中间不完整片段'},
        'tor': None,                      # 误接管轮合法地不传 tor=
        'takeover_judge': None,
        'takeover_latency': None,
        'reply_quality': None,
        'user_start_s': 0.0,
        'user_end_s': 1.5,
        'ai_start_s': 3.69,               # ← AI 确有回复（事实）
        'ai_end_s': 23.305,
        'has_ai_reply': True,             # ← AI 确有回复（事实）
    }


def test_B1_misunderstand_fallback_message_and_arity():
    """B1：误接管轮（tor=None）兜底 —— 不含「无 AI 回复」、4 键、说清分类。"""
    from app.services.calculators.xiaoyi_metrics.turn_eval.strategy import TurnEvalCalculator

    # 顶层兼容字段
    top = _calc_with_turns([_real_jg0002_turn()])['tor']
    assert '无 AI 回复' not in top['message']
    assert top['message'] == '分类为误接管，不计算 TOR'
    assert len(top) == 4 and set(top) == {'tor', 'n_words', 'duration', 'message'}

    # 原生 per_round 投影
    per_round = TurnEvalCalculator._build_per_round(1, [_real_jg0002_turn()])[0]['tor']
    assert '无 AI 回复' not in per_round['message']
    assert per_round['message'] == '分类为误接管，不计算 TOR'
    assert len(per_round) == 4


def test_B2_short_circuit_message_distinct_and_key_shape_matches_compute_tor():
    """B2：未接管短路分支 —— message 与两条全局串都不同，且键形与 compute_tor 早返回一致。"""
    from app.services.calculators.xiaoyi_metrics.turn_eval.turn_evaluation import (
        TurnInfo, classify_turn_comprehensive,
    )

    cls = classify_turn_comprehensive(
        TurnInfo(turn_index=0, user_chunks=_USER_CHUNKS, ai_chunks=[],
                 user_start_s=0.0, user_end_s=1.5)
    )
    assert cls.classification == '未接管'
    msg = cls.tor['message']
    assert msg != _TOR_EMPTY_AI_MSG and msg != _TOR_EMPTY_USER_MSG
    assert '不计算 TOR' in msg

    # 键形一致：与 compute_tor 的空 chunks 早返回同键集、同键序无关但键集相同
    ref = _compute_tor(ai_chunks=[])
    assert set(cls.tor) == set(ref), '短路分支键形与 compute_tor 不一致（键数判据会失真）'
    assert len(cls.tor) == 6
    assert cls.tor['tor'] == 0 and cls.tor['n_words'] == 0 and cls.tor['duration'] == 0.0
    assert cls.tor['hit_words'] == [] and cls.tor['user_last_word_end_s'] is None


def test_B3_true_fetch_empty_still_individually_detectable():
    """B3：真·取数空仍可被单独查出 —— 两条串与任何业务判定串都不相同。"""
    from app.services.calculators.xiaoyi_metrics.turn_eval.turn_evaluation import (
        TurnInfo, classify_turn_comprehensive,
    )
    from app.services.calculators.xiaoyi_metrics.turn_eval.strategy import TurnEvalCalculator

    fetch_empty = {_TOR_EMPTY_AI_MSG, _TOR_EMPTY_USER_MSG}
    business = {
        classify_turn_comprehensive(
            TurnInfo(0, _USER_CHUNKS, [], 0.0, 1.5)
        ).tor['message'],
        TurnEvalCalculator._build_per_round(1, [_real_jg0002_turn()])[0]['tor']['message'],
        _calc_with_turns([_real_jg0002_turn()])['tor']['message'],
    }
    assert fetch_empty & business == set(), '真·取数空与业务判定/兜底话术仍共用字符串'


def test_B4_normal_compute_tor_path_untouched():
    """B4：接管轮走 `last.get('tor')` 真值分支 —— 兜底改动不得影响正常结果。"""
    real_tor = _compute_tor()
    assert real_tor['message'] == 'OK'          # 正常路径未被本卡改动
    turn = dict(_real_jg0002_turn(), classification='接管', tor=real_tor)
    top = _calc_with_turns([turn])['tor']
    assert top == real_tor, '兜底改动污染了正常（接管）轮的 tor'
    from app.services.calculators.xiaoyi_metrics.turn_eval.strategy import TurnEvalCalculator
    assert TurnEvalCalculator._build_per_round(1, [turn])[0]['tor'] == real_tor


def test_B5_skip_item_third_shape_untouched():
    """B5：第三形态（无归属轮 ⇒ 1 键 `跳过: …` 项）未被本卡波及。"""
    from app.services.calculators.xiaoyi_metrics.turn_eval.strategy import TurnEvalCalculator
    item = TurnEvalCalculator._build_per_round(2, [dict(_real_jg0002_turn(), round_number=0)])[1]
    assert item.get('message', '').startswith('跳过')
    assert 'tor' not in item


# ══════════════════════════════════════════════════════════════════
#  C. 真实冻结数据回放（形状取自 task 420 触发闸门的 6 行）
# ══════════════════════════════════════════════════════════════════

def test_C1_replayed_jg0002_row_no_longer_contradicts_fact():
    """C1：回放真实触发行 —— 「有 AI 回复」的误接管轮不再被写成「无 AI 回复」。

    这一条钉住缺陷的**本质**：不是话术不统一，而是**输出与事实相反**。
    """
    turn = _real_jg0002_turn()
    assert turn['has_ai_reply'] is True and turn['ai_start_s'] is not None
    top = _calc_with_turns([turn])['tor']
    assert '无 AI 回复' not in top['message'], '兜底仍把「有 AI 回复的误接管轮」写成「无 AI 回复」'
    assert top['message'] == '分类为误接管，不计算 TOR'


def test_C2_gate_can_bucket_the_two_columns_by_key_count():
    """C2：闸门改用键数分桶后，两列可精确分离（4 键=兜底字面量 / 6 键=compute_tor 返回）。

    真实数据全库分布（只读扫描，16773 个 tor dict）：
      4 键 572 行 —— message 全为「无 AI 回复」（本卡修掉的列）
      6 键 16131 行 —— OK / ai_chunks 为空 / 检测到误接管（抢话）… / user_chunks 为空
      1 键 70 行 —— `跳过: Missing required fields for tor: …`
    """
    from app.services.calculators.xiaoyi_metrics.turn_eval.turn_evaluation import (
        TurnInfo, classify_turn_comprehensive,
    )
    from app.services.calculators.xiaoyi_metrics.turn_eval.strategy import TurnEvalCalculator

    # 兜底字面量列：4 键
    assert len(TurnEvalCalculator._build_per_round(1, [_real_jg0002_turn()])[0]['tor']) == 4
    assert len(_calc_with_turns([_real_jg0002_turn()])['tor']) == 4
    # compute_tor 返回列（含短路分支占位）：6 键
    assert len(_compute_tor(ai_chunks=[])) == 6
    assert len(classify_turn_comprehensive(
        TurnInfo(0, _USER_CHUNKS, [], 0.0, 1.5)).tor) == 6
