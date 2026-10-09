# -*- coding: utf-8 -*-
"""比率统计策略（RatioStrategy）回归测试：覆盖 多轮/单轮 × 有整体/无整体 × 按轮次/按用例。"""

from backend.utils.report.aggregation_strategies import RatioStrategy


def _overall_item(value, case_id, round_count):
    """有整体结果时每用例 1 个 item：值为该用例总数，round_count 为该用例有值轮次数。"""
    return {'dimension_value': value, 'api_raw_response': {}, 'test_result_id': case_id, 'round_count': round_count}


def _round_items(values, case_id):
    """无整体结果时每轮 1 个 item：round_count = 该用例有值轮次数。"""
    n = len(values)
    return [{'dimension_value': v, 'api_raw_response': {}, 'test_result_id': case_id, 'round_count': n}
            for v in values]


# ---------- 按轮次（agg_denominator='round'，打断数量类默认） ----------

def test_round_mode_with_overall():
    """有整体结果、按轮次：Σ数量 / Σ各用例有值轮次数。"""
    items = [
        _overall_item(1, case_id=1, round_count=2),
        _overall_item(2, case_id=2, round_count=3),
    ]
    assert RatioStrategy().aggregate(items, denominator_mode='round') == round((1 + 2) / (2 + 3) * 100, 2)  # 60.0


def test_round_mode_without_overall():
    """无整体结果（每轮独立 item）、按轮次：轮次数按用例去重，不重复计数。"""
    items = (
        _round_items([1, 0], case_id=1) +   # 该用例 2 轮
        _round_items([1, 1, 1], case_id=2)  # 该用例 3 轮
    )
    assert RatioStrategy().aggregate(items, denominator_mode='round') == round((1 + 0 + 1 + 1 + 1) / (2 + 3) * 100, 2)  # 80.0


def test_round_mode_null_value_excluded():
    """值为 None 的 item 不计入分子也不计入分母。"""
    items = [
        _overall_item(None, case_id=1, round_count=3),
        _overall_item(1, case_id=2, round_count=2),
    ]
    assert RatioStrategy().aggregate(items, denominator_mode='round') == round(1 / 2 * 100, 2)  # 50.0


def test_round_mode_pure_overall_no_round_records_fallback_to_cases():
    """纯 overall 无轮次记录时，按轮次口径回退为用例数。"""
    items = [
        {'dimension_value': 1, 'api_raw_response': None, 'test_result_id': 1, 'round_count': 0},
        {'dimension_value': 2, 'api_raw_response': None, 'test_result_id': 2, 'round_count': 0},
    ]
    assert RatioStrategy().aggregate(items, denominator_mode='round') == round((1 + 2) / 2 * 100, 2)  # 150.0


# ---------- 按用例（agg_denominator='case'） ----------

def test_case_mode_with_overall():
    """有整体结果、按用例：Σ数量 / 配置该维度的用例数。"""
    items = [
        _overall_item(0, case_id=1, round_count=2),
        _overall_item(2, case_id=2, round_count=3),
    ]
    assert RatioStrategy().aggregate(items, denominator_mode='case') == round((0 + 2) / 2 * 100, 2)  # 100.0


def test_case_mode_without_overall_dedupe_by_case():
    """无整体结果、按用例：用例数按 test_result_id 去重，多轮不重复计。"""
    items = (
        _round_items([1, 0], case_id=1) +
        _round_items([1], case_id=2)
    )
    assert RatioStrategy().aggregate(items, denominator_mode='case') == round((1 + 0 + 1) / 2 * 100, 2)  # 100.0


def test_all_zero_denominator_returns_none():
    """分母为 0（无任何有效 item）返回 None。"""
    assert RatioStrategy().aggregate([], denominator_mode='round') is None
    assert RatioStrategy().aggregate([{'dimension_value': None, 'test_result_id': 1}], denominator_mode='case') is None


def test_default_mode_is_case():
    """未传 denominator_mode 时默认按用例。"""
    items = [_overall_item(1, case_id=1, round_count=2)]
    assert RatioStrategy().aggregate(items) == 100.0


# ---------- 按用例/按轮次 下沉到 pass_rate / average ----------

def test_pass_rate_round_mode():
    """pass_rate 按轮次：达标轮次数 / 有值轮次数。"""
    from backend.utils.report.aggregation_strategies import PassRateStrategy
    items = (
        _round_items([1, 0], case_id=1) +   # 1 轮达标
        _round_items([1, 1], case_id=2)     # 2 轮达标
    )
    # 阈值默认 value>0：3 轮达标 / 4 轮
    assert PassRateStrategy().aggregate(items, denominator_mode='round') == 75.0


def test_pass_rate_case_mode():
    """pass_rate 按用例：达标用例数 / 用例数。"""
    from backend.utils.report.aggregation_strategies import PassRateStrategy
    items = [
        _overall_item(1, case_id=1, round_count=2),
        _overall_item(0, case_id=2, round_count=3),
        _overall_item(1, case_id=3, round_count=2),
    ]
    assert PassRateStrategy().aggregate(items, denominator_mode='case') == round(2 / 3 * 100, 2)  # 66.67


def test_average_round_mode():
    """average 按轮次：Σ轮值 / 轮次数（多轮用例权重更大）。"""
    from backend.utils.report.aggregation_strategies import SimpleAverageStrategy
    items = (
        _round_items([2, 4], case_id=1) +  # 轮均 3
        _round_items([10], case_id=2)      # 单值 10
    )
    # 按轮次：(2+4+10)/3 = 5.333...
    assert SimpleAverageStrategy().aggregate(items, denominator_mode='round') == (2 + 4 + 10) / 3


def test_average_case_mode():
    """average 按用例：Σ用例值 / 用例数（每用例等权）。"""
    from backend.utils.report.aggregation_strategies import SimpleAverageStrategy
    items = [
        _overall_item(2, case_id=1, round_count=2),
        _overall_item(10, case_id=2, round_count=1),
    ]
    assert SimpleAverageStrategy().aggregate(items, denominator_mode='case') == 6.0


# ---------- 排除轮次（exclude_rounds） ----------

class _FakeResult:
    def __init__(self, rid):
        self.id = rid


def test_get_round_values_excludes_rounds():
    """_get_round_values 跳过被排除的轮次；全部排除时回退整体值。"""
    from backend.utils.report.report_utils import ReportUtils
    result = _FakeResult(1)
    dim_results_map = {
        1: [
            {'id': 10, 'value': 1.0, 'round_number': 0},
            {'id': 10, 'value': 2.0, 'round_number': 1},
            {'id': 10, 'value': 3.0, 'round_number': 2},
        ]
    }
    dim_name_to_id = {'X': 10}
    assert ReportUtils._get_round_values(result, 'X', 0.0, dim_results_map, dim_name_to_id, exclude_rounds=[1]) == [1.0, 3.0]
    # 全部排除 → 回退整体值 1 个样本
    assert ReportUtils._get_round_values(result, 'X', 7.0, dim_results_map, dim_name_to_id, exclude_rounds=[0, 1, 2]) == [7.0]
    # 无排除 → 全部轮值
    assert ReportUtils._get_round_values(result, 'X', 0.0, dim_results_map, dim_name_to_id) == [1.0, 2.0, 3.0]


def test_exclude_last_round_minus_one():
    """排除轮次 -1（最后一轮）解析为该用例该维度最大轮次。"""
    from backend.utils.report.report_utils import ReportUtils
    result = _FakeResult(1)
    dim_results_map = {
        1: [
            {'id': 10, 'value': 1.0, 'round_number': 0},
            {'id': 10, 'value': 2.0, 'round_number': 1},
            {'id': 10, 'value': 3.0, 'round_number': 2},
        ]
    }
    dim_name_to_id = {'X': 10}
    # -1 → 最大轮次 2
    assert ReportUtils._get_round_values(result, 'X', 0.0, dim_results_map, dim_name_to_id, exclude_rounds=[-1]) == [1.0, 2.0]
    # -1 与具体轮次并存
    assert ReportUtils._get_round_values(result, 'X', 0.0, dim_results_map, dim_name_to_id, exclude_rounds=[-1, 0]) == [2.0]
    # 无轮次记录时 -1 无效 → 回退整体值
    assert ReportUtils._get_round_values(result, 'X', 9.0, {}, dim_name_to_id, exclude_rounds=[-1]) == [9.0]


# ---------- 实际打断轮数分母（LLM 评估失败剔除） ----------

def test_actual_interruption_rounds_prefers_counts_sum():
    """ratio 分母 = 实际打断轮数：优先 success_count+failure_count+inquiry_count（与分子同源，保证三率和=100%）。"""
    from backend.utils.report.report_utils import _actual_interruption_rounds
    raw = {'interruption': {
        'success_count': 2, 'failure_count': 1, 'inquiry_count': 0,
        'round_details': [{'role': 'interruption', 'behavior': '回复'}] * 5,  # counts 优先于 details
    }}
    assert _actual_interruption_rounds(raw) == 3
    # eval_server 包装格式 {code:0,data:{result:...}} 也识别
    wrapped = {'code': 0, 'data': {'result': {'interruption': {
        'success_count': 1, 'failure_count': 1, 'inquiry_count': 1}}}}
    assert _actual_interruption_rounds(wrapped) == 3
    # counts 全 0（无已判定打断轮）→ 0，整例从分子分母剔除
    assert _actual_interruption_rounds({'interruption': {
        'success_count': 0, 'failure_count': 0, 'inquiry_count': 0}}) == 0


def test_actual_interruption_rounds_details_fallback():
    """counts 缺失（LLM 降级）→ 兜底 round_details 中 role≠resume 且 behavior 非 None 的条数。"""
    from backend.utils.report.report_utils import _actual_interruption_rounds
    raw = {'interruption': {'round_details': [
        {'role': 'interruption', 'behavior': '回复'},
        {'role': 'interruption', 'behavior': None},   # 判定失败 → 不计（分子同样不含它）
        {'role': 'resume', 'behavior': None},          # 恢复轮 → 不计
        {'behavior': '静默'},                          # 旧数据无 role → 视为打断轮
    ]}}
    assert _actual_interruption_rounds(raw) == 2
    # 顶层 round_details 也识别
    assert _actual_interruption_rounds({'round_details': [{'behavior': '回复'}]}) == 1
    # 无法提取 → None，调用方回退配置轮次
    assert _actual_interruption_rounds({'foo': 1}) is None
    assert _actual_interruption_rounds(None) is None
    assert _actual_interruption_rounds('not-json') is None


def test_weighted_sum_ratio_skips_llm_failed_items():
    """LLM 调用失败的用例整例剔出分子分母。"""
    from backend.utils.report.aggregation_strategies import WeightedSumRatioStrategy
    params = [{'agg_role': 'numerator', 'field_path': 'n_rate_success'},
              {'agg_role': 'denominator', 'field_path': 'n_reject_rounds'}]
    items = [
        {'api_raw_response': {'message': 'OK', 'n_rate_success': 1, 'n_reject_rounds': 2}},
        {'api_raw_response': {'message': 'LLM 调用失败: Server disconnected', 'n_rate_success': 0, 'n_reject_rounds': 2}},
    ]
    # 失败例剔除 → 1/2 而不是 1/4
    assert WeightedSumRatioStrategy().aggregate(items, output_params=params) == 50.0


def test_weighted_sum_ratio_takeover_family():
    """接管族三率：Σcount/Σtotal_turns 加权，total_turns=0 用例剔除，三率和=100；
    turn_eval raw 无顶层 message，不被 'LLM 调用失败' 跳过逻辑误伤。"""
    from backend.utils.report.aggregation_strategies import WeightedSumRatioStrategy

    def _params(count_field):
        return [{'agg_role': 'numerator', 'field_path': f'turn_classification.{count_field}'},
                {'agg_role': 'denominator', 'field_path': 'turn_classification.total_turns'}]

    def _item(normal, no, false, total):
        return {'api_raw_response': {'turn_classification': {
            'normal_takeover_count': normal, 'no_takeover_count': no,
            'false_takeover_count': false, 'total_turns': total}}}

    items = [
        _item(2, 1, 0, 3),
        _item(0, 0, 0, 0),   # 零判定轮用例 → den=0 剔除，不稀释占比
        _item(1, 0, 1, 2),
    ]
    strat = WeightedSumRatioStrategy()
    normal = strat.aggregate(items, output_params=_params('normal_takeover_count'))   # 3/5
    no = strat.aggregate(items, output_params=_params('no_takeover_count'))          # 1/5
    false = strat.aggregate(items, output_params=_params('false_takeover_count'))    # 1/5
    assert (normal, no, false) == (60.0, 20.0, 20.0)
    assert normal + no + false == 100.0
