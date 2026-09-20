# -*- coding: utf-8 -*-
"""平台 per_round 逐轮 TRD 覆盖测试（_extract_per_round + _overwrite_round_results）。

契约来源: doc/功能设计文档/04_评估/整体评估返回逐轮结果方案.md
per_round 投影取 eval_server build_per_round 的真实输出（同 monorepo 兄弟目录，
round_metrics.py 自包含可直接按文件加载），跨仓契约一起验。
"""
import importlib.util
import os

import pytest

from backend.models.database import db
from backend.models.models import Dimension, TestResult, TestResultDimension
from backend.services.evaluation.evaluation_result_processor import EvaluationResultProcessor

_ROUND_METRICS_PY = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'eval_server',
    'app', 'services', 'calculators', 'xiaoyi_metrics',
    'interruptibility', 'round_metrics.py'))


def _load_build_per_round():
    spec = importlib.util.spec_from_file_location('_ir_round_metrics', _ROUND_METRICS_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_per_round


def _real_per_round():
    """eval_server 真实投影：3 轮请求，轮1 成功、轮2 失败(恢复)、轮0 无时序。"""
    build_per_round = _load_build_per_round()
    details = [
        {'round': 1, 'role': 'interruption', 'behavior': '回复',
         'response_latency_ms': 300.0, 'reply_latency_ms': 800.0, 'score_overall': 4.5},
        {'round': 2, 'role': 'interruption', 'behavior': '恢复',
         'response_latency_ms': 100.0, 'reply_latency_ms': 200.0, 'score_overall': 2.0},
    ]
    return build_per_round(3, details)


def _dim_data(dim, field_path):
    return {
        'id': dim.id, 'name': dim.name, 'rule': {'type': 'direct'}, 'api_settings': {},
        'output_params': [{'param_code': 'main', 'field_path': field_path,
                           'output_role': 'main', 'visible_in_report': True}],
    }


@pytest.fixture
def env(app):
    """result + 3 维度(成功数量/响应时延/用例类型文本) + 整体 TRD + 一条 pending 逐轮 TRD。"""
    dims = {}
    for key, name in [('success', '打断成功数量'), ('latency', '响应时延'),
                      ('case_type', '用例类型')]:
        d = Dimension(name=f'{name}_pr_test', type='auto', result_type=0, weight=1)
        db.session.add(d)
        db.session.flush()
        dims[key] = d
    result = TestResult(algorithm_type='voice_llm', result_data={})
    db.session.add(result)
    db.session.flush()
    overall = {}
    for key, d in dims.items():
        trd = TestResultDimension(test_result_id=result.id, dimension_id=d.id,
                                  algorithm_type='voice_llm', round_number=None,
                                  evaluation_status='completed')
        db.session.add(trd)
        db.session.flush()
        overall[key] = trd
    # 模拟逐轮评估先建的 pending 行（应被覆盖而非新建）
    pending = TestResultDimension(test_result_id=result.id, dimension_id=dims['success'].id,
                                  algorithm_type='voice_llm', round_number=1,
                                  evaluation_status='pending')
    db.session.add(pending)
    db.session.flush()
    paths = {'success': 'interruption.success_count',
             'latency': 'interruption.response_latency_avg_ms',
             'case_type': 'interruption.case_type'}
    group_items = [(_dim_data(dims[k], paths[k]), overall[k].id) for k in dims]
    return result, dims, pending, group_items


def test_extract_per_round_shapes(app):
    proc = EvaluationResultProcessor()
    # 真实包装：code/data → result → 维度包内嵌套 per_round
    resp = {'code': 0, 'msg': 'success',
            'data': {'task_id': 't1', 'status': 'completed',
                     'result': {'interruption': {'success_count': 1,
                                                 'per_round': [{'round_number': 0}]}}}}
    assert proc._extract_per_round(resp) == [{'round_number': 0}]
    # 顶层 per_round（文档 §4.2 形态）
    assert proc._extract_per_round({'per_round': [{'round_number': 1}]}) == [{'round_number': 1}]
    # 无 per_round / 非 dict → 空列表（旧评估服务兼容）
    assert proc._extract_per_round({'code': 0, 'data': {'result': {}}}) == []
    assert proc._extract_per_round(None) == []


def test_overwrite_round_results(app, env):
    result, dims, pending, group_items = env
    proc = EvaluationResultProcessor()
    per_round = _real_per_round()
    # 跳过项形态核对（跨仓契约）
    assert per_round[0] == {'round_number': 0, 'message': '跳过: 非计时轮(无打断时序)'}

    n = proc._overwrite_round_results(result.id, per_round, group_items, db.session)
    db.session.flush()

    def _rows(round_idx):
        return {r.dimension_id: r for r in db.session.query(TestResultDimension).filter(
            TestResultDimension.test_result_id == result.id,
            TestResultDimension.round_number == round_idx).all()}

    # 轮1：pending 行被原地覆盖（不新建）；时延行新建且 algorithm_type 复制整体行
    rows1 = _rows(1)
    assert rows1[dims['success'].id].id == pending.id
    assert rows1[dims['success'].id].dimension_value == 1.0
    assert rows1[dims['success'].id].score == 1.0
    assert rows1[dims['success'].id].evaluation_status == 'completed'
    assert rows1[dims['latency'].id].dimension_value == 300.0
    assert rows1[dims['latency'].id].algorithm_type == 'voice_llm'
    # 文本维度(case_type)不投影 → 无逐轮行
    assert dims['case_type'].id not in rows1
    # 轮0 跳过项 → 零行
    assert _rows(0) == {}
    # 轮2 失败轮：success_count=0 落行，时延不投（与 list -1 口径一致）
    rows2 = _rows(2)
    assert rows2[dims['success'].id].dimension_value == 0.0
    assert dims['latency'].id not in rows2
    # 写入计数 = 轮1(2) + 轮2(1)
    assert n == 3

    # 幂等：重跑不新增行、计数一致
    n2 = proc._overwrite_round_results(result.id, per_round, group_items, db.session)
    db.session.flush()
    assert n2 == n
    assert db.session.query(TestResultDimension).filter(
        TestResultDimension.test_result_id == result.id,
        TestResultDimension.round_number.isnot(None)).count() == 3
