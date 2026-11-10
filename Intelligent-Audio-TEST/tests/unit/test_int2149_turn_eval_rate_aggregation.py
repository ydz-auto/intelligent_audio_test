# -*- coding: utf-8 -*-
"""INT-2149：turn_eval 三率占比（接管率/未接管率/误接管率）聚合口径回归。

背景：V9.7.31 移植 turn_eval 维度种子时，三个率占比子维度被配成 `statistic_method='ratio'`，
V9.7.10 金标（commit `3d27e8028^`）是 `weighted_sum_ratio`。两者口径不同：

- `ratio`：分子 = Σ用例级 dimension_value（这里是 0~1 的**比率**，不是计数），
  分母 = Σ有值轮次数（round_count）。用例只有整体结果、没有逐轮行时 round_count=0，
  分子照样计入 → 分母偏小，占比可超过 100%（任务 402 报告口径实测接管率 138.98%）。
- `weighted_sum_ratio`：从每条结果的 `api_raw_response` 取
  `turn_classification.<count>` / `turn_classification.total_turns`，Σ分子/Σ分母。

本文件钉死两件事（不连库）：
1. 种子配置：三个率占比子维度必须 `weighted_sum_ratio` + `agg_denominator='round'`，
   main/numerator/denominator 三种 agg_role 指向 turn_classification 对应字段；
2. 口径行为：同一批「用例级比率 + 部分用例有轮次、部分没有」的 item，
   ratio 会算出 >100% 的非物理值，weighted_sum_ratio 恒为 Σ分子/Σ分母。
"""
import importlib.util
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 种子脚本 import 期会读取配置（不触网），与其它种子单测同口径先序兜底。
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')
os.environ.setdefault('DATABASE_URI', 'postgresql://u:p@localhost:1/unused')

SEED_PATH = os.path.join(
    PROJECT_ROOT, 'scripts', 'migrations', '202610', 'seed_turn_eval.py')

RATE_DIMS = {
    '接管率占比': ('normal_takeover_count', 'turn_classification.normal_takeover_count'),
    '未接管率占比': ('no_takeover_count', 'turn_classification.no_takeover_count'),
    '误接管率占比': ('false_takeover_count', 'turn_classification.false_takeover_count'),
}


def _load_seed():
    spec = importlib.util.spec_from_file_location('int2149_seed_turn_eval', SEED_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sub_dim(name):
    for sub in _load_seed().SUB_DIMENSIONS:
        if sub['name'] == name:
            return sub
    raise AssertionError(f'子维度不存在: {name}')


def test_rate_dims_use_weighted_sum_ratio():
    """三个率占比子维度必须按金标走 weighted_sum_ratio + 按轮次分母。"""
    for name in RATE_DIMS:
        sub = _sub_dim(name)
        assert sub['statistic_method'] == 'weighted_sum_ratio', name
        assert sub['agg_denominator'] == 'round', name


def test_rate_dims_agg_roles_map_to_turn_classification():
    """main/numerator/denominator 三种 agg_role 指向 turn_classification 的对应字段。"""
    for name, (count_code, count_path) in RATE_DIMS.items():
        params = {p[0]: p for p in _sub_dim(name)['params']}
        by_role = {p[6]: p for p in params.values() if p[6] in ('main', 'numerator', 'denominator')}

        assert set(by_role) == {'main', 'numerator', 'denominator'}, name
        main = by_role['main']
        assert main[5].startswith('turn_classification.'), name
        assert main[5].endswith('_rate'), name

        numerator = by_role['numerator']
        assert numerator[0] == count_code, name
        assert numerator[5] == count_path, name

        denominator = by_role['denominator']
        assert denominator[0] == 'total_turns', name
        assert denominator[5] == 'turn_classification.total_turns', name


def test_rate_dim_help_text_no_longer_claims_ratio():
    """分子/分母参数的 help_text 必须与新口径一致，不再写 'ratio 分子/分母'。"""
    for name in RATE_DIMS:
        for param in _sub_dim(name)['params']:
            if param[6] in ('numerator', 'denominator'):
                assert 'weighted_sum_ratio' in param[11], (name, param[0])
                assert not param[11].startswith('ratio'), (name, param[0])


def test_ratio_overcounts_case_rate_without_round_rows():
    """用例级比率 + 部分用例无逐轮行时，ratio 分母漏计 → 占比 >100%；weighted 恒为 Σ分子/Σ分母。"""
    from report_service.domain.services.aggregation_strategies import (
        RatioStrategy, WeightedSumRatioStrategy,
    )

    def item(case_id, rate, num, den, round_count):
        return {
            'dimension_value': rate,
            # INT-2381：聚合 item 只携带块内提取的标量，不再带整份 api_raw_response
            'raw_fields': {'present': True, 'values': {
                'turn_classification.normal_takeover_count': num,
                'turn_classification.total_turns': den,
            }},
            'test_result_id': case_id,
            'round_count': round_count,
        }

    # 3 个用例：仅 case 1 有逐轮行（round_count=2）；case 2/3 只有整体结果。
    items = [
        item(1, 1.0, 2, 2, round_count=2),
        item(2, 1.0, 2, 2, round_count=0),
        item(3, 0.5, 1, 2, round_count=0),
    ]
    output_params = [
        {'param_code': 'normal_takeover_count', 'agg_role': 'numerator',
         'field_path': 'turn_classification.normal_takeover_count'},
        {'param_code': 'total_turns', 'agg_role': 'denominator',
         'field_path': 'turn_classification.total_turns'},
    ]

    # ratio：(1.0 + 1.0 + 0.5) / 2 × 100 = 125%（分子含 3 个用例，分母只有 case 1 的 2 轮）
    assert RatioStrategy().aggregate(items, output_params, 'round') == 125.0

    # weighted_sum_ratio：(2 + 2 + 1) / (2 + 2 + 2) × 100 = 83.3333%
    assert WeightedSumRatioStrategy().aggregate(items, output_params, 'round') == round(5 / 6 * 100, 4)
