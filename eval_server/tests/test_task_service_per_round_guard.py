# -*- coding: utf-8 -*-
"""TaskService per_round 切片守卫：原生 per_round 跳过重跑（省 N 次 ASR/LLM），
无原生 per_round 的计算器（reject_judge 形态）仍走 _calculate_per_round + _agg_result。"""
from app.services.task_service import TaskService


class _FakeNative:
    """打断 v2 / turn_eval 形态：run() 原生返回 per_round"""
    supports_per_round = True
    sliced = 0

    def run(self, task_params):
        return {'score': 1, 'per_round': [{'round_number': 0}, {'round_number': 1}]}

    def _calculate_per_round(self, task_params):
        _FakeNative.sliced += 1
        return [{'round_number': 0}, {'round_number': 1}]


class _FakeSliced:
    """reject_judge 形态：run() 无 per_round，靠切片 + _agg_result 聚合"""
    supports_per_round = True
    sliced = 0
    _agg_result = {'score': 9, 'n_rounds': 2}

    def run(self, task_params):
        return {'score': 0}

    def _calculate_per_round(self, task_params):
        _FakeSliced.sliced += 1
        return [{'round_number': 0}, {'round_number': 1}]


_PARAMS = {'rounds': [{}, {}]}  # 整体评估（无 round_number）、2 轮


def _run(fake):
    TaskService.CALCULATORS['fake'] = fake
    try:
        return TaskService.calculate('fake', dict(_PARAMS))
    finally:
        TaskService.CALCULATORS.pop('fake', None)


def test_native_per_round_skips_reslice():
    _FakeNative.sliced = 0
    result = _run(_FakeNative())
    assert _FakeNative.sliced == 0          # 未重跑切片 → 无额外 LLM/ASR
    assert result['per_round'] == [{'round_number': 0}, {'round_number': 1}]


def test_no_native_per_round_still_slices():
    _FakeSliced.sliced = 0
    result = _run(_FakeSliced())
    assert _FakeSliced.sliced == 1          # reject_judge 聚合路径不受影响
    assert result['score'] == 9             # _agg_result 覆盖顶层
    assert len(result['per_round']) == 2
