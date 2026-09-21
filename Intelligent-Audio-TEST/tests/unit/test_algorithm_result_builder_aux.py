# -*- coding: utf-8 -*-
"""共享构建器 algorithm_result_builder 逐轮 aux 提取测试（迁移自 V9.7.10 6927d07e 修复）。

契约：
- 多轮场景每轮独立取值：aux_values 按 (param_code, round_number) 分组，输出 @round:N / @overall 后缀条目
- api_raw_response 主路径（整体行 round=None、轮次行 round=i）
- evaluation_data 仅兜底（某参数在 api_raw_response 中完全未取到时）
"""
from shared.domain.algorithm_result_builder import build_algorithm_results_for_result


def _aux_params_map():
    """{dimension_id: [{param, dimension_name}]}，同一维度两个 aux 参数（逐轮独立取值）。"""
    return {
        1: [
            {'param': {'param_code': 'interruption_count', 'field_path': 'data.result.count',
                       'field_type': 'number'}, 'dimension_name': '打断成功数量'},
            {'param': {'param_code': 'scene', 'field_path': 'data.result.scene',
                       'field_type': 'text'}, 'dimension_name': '场景'},
        ],
    }


def _row(dim_id, round_number, count, scene):
    """TRD 行：api_raw_response 为 {code:0, data:{result:{count, scene}}}。"""
    return {
        'dimension_id': dim_id,
        'round_number': round_number,
        'dimension_value': count,
        'api_raw_response': {'code': 0, 'data': {'result': {'count': count, 'scene': scene}}},
    }


def _build(result_data=None, rows=None):
    """调用共享构建器，返回 param_code 列表与 (code -> item) 映射。

    result_data 保持非空（{'evaluation_data': {}}），避免构建器第 77 行
    `if not (algo_res or result_data)` 提前返回（空 dict 为 falsy）。
    """
    algorithm_results = build_algorithm_results_for_result(
        result=None, resource='dev_01', algo_res={}, result_data=result_data or {'evaluation_data': {}},
        aux_params_map=_aux_params_map(), dim_result_rows=rows or [],
        output_fields=[], algorithm_type='translation',
    )
    by_code = {r['param_code']: r for r in algorithm_results}
    codes = [r['param_code'] for r in algorithm_results]
    return codes, by_code


# ---------- 多轮场景：每轮独立取值 ----------

def test_multi_round_each_round_independent():
    """多轮（整体行 + 2 个轮次行）：输出 @overall + @round:1 + @round:2 三组条目，各自取对应轮的值。"""
    rows = [
        _row(1, None, 3, '整体场景'),   # 整体行 round=None
        _row(1, 0, 1, '轮一'),           # round 0
        _row(1, 1, 2, '轮二'),           # round 1
    ]
    codes, by_code = _build(rows=rows)

    # 打断成功数量：整体 + 每轮
    assert 'interruption_count@overall' in codes
    assert 'interruption_count@round:1' in codes
    assert 'interruption_count@round:2' in codes
    assert by_code['interruption_count@overall']['value'] == 3
    assert by_code['interruption_count@round:1']['value'] == 1
    assert by_code['interruption_count@round:2']['value'] == 2
    assert by_code['interruption_count@round:1']['round_number'] == 1
    assert by_code['interruption_count@overall']['round_number'] is None

    # 场景：每轮独立（修复前 first-wins 会丢后续轮次）
    assert by_code['scene@round:1']['value'] == '轮一'
    assert by_code['scene@round:2']['value'] == '轮二'
    assert by_code['scene@overall']['value'] == '整体场景'


def test_single_round_no_suffix():
    """非多轮（无任何 round_number 行）：无 @ 后缀，code 原样输出。"""
    rows = [_row(1, None, 5, 's')]
    codes, by_code = _build(rows=rows)
    assert 'interruption_count' in codes
    assert 'interruption_count@overall' not in codes
    assert by_code['interruption_count']['value'] == 5


def test_multi_round_row_with_null_value_skipped():
    """某轮行 api_raw_response 缺失（或值为 None）时该轮不输出，不影响其它轮。"""
    rows = [
        _row(1, None, 3, '整体'),
        _row(1, 0, 1, '轮一'),
        {'dimension_id': 1, 'round_number': 1, 'dimension_value': 2, 'api_raw_response': None},
    ]
    codes, by_code = _build(rows=rows)
    assert 'interruption_count@round:2' not in codes  # 轮二无响应，不产出
    assert by_code['interruption_count@round:1']['value'] == 1
    assert by_code['interruption_count@overall']['value'] == 3


# ---------- evaluation_data 兜底 ----------

def test_evaluation_data_fallback_only_when_api_raw_response_missing():
    """api_raw_response 完全取不到某参数时，用 evaluation_data 兜底并沿用轮次标注。"""
    rows = [
        {'dimension_id': 1, 'round_number': 1, 'dimension_value': 1.0, 'api_raw_response': None},
    ]
    codes, by_code = _build(
        result_data={'evaluation_data': {'interruption_count': 7}},
        rows=rows,
    )
    assert 'interruption_count@round:2' in codes
    assert by_code['interruption_count@round:2']['value'] == 7
