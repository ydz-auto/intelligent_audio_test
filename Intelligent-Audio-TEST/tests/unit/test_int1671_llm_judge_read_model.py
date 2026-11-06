# -*- coding: utf-8 -*-
"""INT-1671 A1：维度读模型派生 llm_judge 标识（替身注入、不连库）。

口径（INT-1671 评审裁定）：LLM Judge 是「评估方法」不是「结果值类型」，
故不改 result_type 语义，由 task_type_code / dimension_type 经 shared 谓词派生。
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from evaluation_service.application.queries.evaluation_query_service import (
    EvaluationQueryService,
)


def _fake_dim(**overrides):
    """维度替身（覆盖 `_serialize_dimension` 读取的全部字段）。"""
    base = dict(
        id=1,
        name='dim',
        description=None,
        keywords=None,
        dimension_type='main',
        parent_dimension_id=None,
        task_type_code=None,
        category_id=None,
        api_url=None,
        api_endpoints=None,
        api_settings=None,
        api_status=None,
        score_unit=None,
        type='auto',
        result_type=1,
        result_min=0,
        result_max=100,
        decimal_places=2,
        weight=5,
        sort_order=0,
        estimated_exec_time=5,
        rule=None,
        statistic_method='average',
        agg_denominator='case',
        exclude_rounds=None,
        status=True,
        visibility='shared',
        created_by_user_id=None,
        created_at=None,
        updated_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _StubDimensionRepo:
    """options 查询替身：只提供 `get_dimension_options` 用到的两个方法。"""

    def __init__(self, dims):
        self._dims = dims

    def list_dimension_options(self, algorithm_type=''):
        return list(self._dims)

    def find_audio_dimension_ids(self, dim_ids):
        return set()


@pytest.mark.parametrize('overrides', [
    # 种子里已软删的 id=1 形态
    {'task_type_code': 'llm_judge', 'dimension_type': 'main'},
    # 真库唯一活体 LLM 裁判维度 id=164 形态（dimension_type 不是 llm_judge）
    {'task_type_code': 'high_freq_llm_judge', 'dimension_type': 'main'},
    # 仅 dimension_type 携带标记
    {'task_type_code': 'turn_taking', 'dimension_type': 'llm_judge'},
])
def test_serialize_dimension_marks_llm_judge(overrides):
    out = EvaluationQueryService._serialize_dimension(_fake_dim(**overrides))
    assert out['llm_judge'] is True


@pytest.mark.parametrize('overrides', [
    {'task_type_code': 'algorithm_type', 'dimension_type': 'main'},
    {'task_type_code': 'turn_taking', 'dimension_type': 'main'},
    {'task_type_code': None, 'dimension_type': None},
    {'task_type_code': '', 'dimension_type': ''},
])
def test_serialize_dimension_marks_non_llm_judge(overrides):
    out = EvaluationQueryService._serialize_dimension(_fake_dim(**overrides))
    assert out['llm_judge'] is False


@pytest.mark.parametrize('result_type', [0, 1, 2, 3])
def test_result_type_kept_as_is(result_type):
    """LLM Judge 维度也保持 result_type 原值（0/1/2/3 不扩字符串、不派生）。"""
    out = EvaluationQueryService._serialize_dimension(
        _fake_dim(task_type_code='llm_judge', result_type=result_type))
    assert out['result_type'] == result_type
    assert out['llm_judge'] is True


def test_dimension_options_items_carry_llm_judge():
    """options 项与列表/详情同源派生。"""
    repo = _StubDimensionRepo([
        _fake_dim(id=1, name='llm', task_type_code='llm_judge'),
        _fake_dim(id=2, name='freq', task_type_code='high_freq_llm_judge'),
        _fake_dim(id=3, name='algo', task_type_code='algorithm_type'),
    ])
    result = EvaluationQueryService(repo=repo).get_dimension_options()

    assert result['success'] is True
    items = result['data']['dimensions']
    assert [item['llm_judge'] for item in items] == [True, True, False]
    # options 项不引入第二套结果类型口径
    assert all('result_type' not in item for item in items)
