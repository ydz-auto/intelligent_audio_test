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


def _dim_data(dim, field_path, group_key=None):
    api_settings = {'group_key': group_key} if group_key else {}
    return {
        'id': dim.id, 'name': dim.name, 'rule': {'type': 'direct'}, 'api_settings': api_settings,
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


# ───────────────────────── VEGA-6：native 落库后清旧逐轮行 ─────────────────────────

_FAMILY = 'interruption_v2'   # 打断族 group_key（与 seed_interruption_v2.GROUP_KEY 一致）
_OTHER = 'turn_taking_v2'     # 接管族 group_key（清理绝不触碰）


def _mk_dim(name):
    d = Dimension(name=f'{name}_pr_clean_test', type='auto', result_type=0, weight=1)
    db.session.add(d)
    db.session.flush()
    return d


def _mk_trd(result_id, dim_id, round_number, value=None, algo='voice_llm',
            status='completed'):
    trd = TestResultDimension(test_result_id=result_id, dimension_id=dim_id,
                              algorithm_type=algo, round_number=round_number,
                              dimension_value=value, evaluation_status=status)
    db.session.add(trd)
    db.session.flush()
    return trd


@pytest.fixture
def clean_env(app):
    """打断族(success/latency/stopc) + 接管族(turn) 两 result 的清理测试环境。

    预置：round-0 幽灵行、超产出轮孤儿切片行、stopc 泄漏行（native 从不投影）、
    接管族逐轮行、各维度 overall 整体行、另一 result 的同维度逐轮行。
    """
    dims = {
        'success': _mk_dim('打断成功数量'),
        'latency': _mk_dim('响应时延'),
        'stopc': _mk_dim('停止遵从率'),   # native per_round 从不投影 → 产出 0 → 全删（dim66 泄漏自愈）
        'turn': _mk_dim('接管指标'),       # 非打断族 → 清理不触碰
    }
    paths = {
        'success': 'interruption.success_count',
        'latency': 'interruption.response_latency_avg_ms',
        'stopc': 'interruption.stop_compliance_rate',
        'turn': 'turn.some_metric',
    }
    group_keys = {'success': _FAMILY, 'latency': _FAMILY, 'stopc': _FAMILY, 'turn': _OTHER}

    result_a = TestResult(algorithm_type='voice_llm', result_data={})
    result_b = TestResult(algorithm_type='voice_llm', result_data={})
    db.session.add_all([result_a, result_b])
    db.session.flush()

    # overall 整体行（round_number=None）——清理必须豁免
    overall = {k: _mk_trd(result_a.id, d.id, None, value=1.0) for k, d in dims.items()}

    # result_a 逐轮脏行
    ghosts = {
        # round-0 幽灵行（切片把 round0 也独立重评的幻影）
        'success_r0': _mk_trd(result_a.id, dims['success'].id, 0, value=1.0),
        'latency_r0': _mk_trd(result_a.id, dims['latency'].id, 0, value=99.0),
        # 超出本次产出轮的孤儿切片行
        'success_r5': _mk_trd(result_a.id, dims['success'].id, 5, value=9.9),
        'latency_r2': _mk_trd(result_a.id, dims['latency'].id, 2, value=888.0),
        # stopc 泄漏行：native 从不投影 stop_compliance（无 stop_intent 轮）→ 全删
        'stopc_r1': _mk_trd(result_a.id, dims['stopc'].id, 1, value=1.0),
        # 接管族逐轮行：非打断族 → 保留
        'turn_r1': _mk_trd(result_a.id, dims['turn'].id, 1, value=5.0),
        # success round1 pending 行（应被覆盖而非新建）
        'success_r1_pending': _mk_trd(result_a.id, dims['success'].id, 1, value=None,
                                      status='pending'),
    }

    # result_b 同维度逐轮行——跨 result 隔离，清理必须不触碰
    other_result_row = _mk_trd(result_b.id, dims['success'].id, 1, value=7.0)

    group_items = [(_dim_data(dims[k], paths[k], group_keys[k]), overall[k].id)
                   for k in ('success', 'latency', 'stopc', 'turn')]
    return {
        'dims': dims, 'result_a': result_a, 'result_b': result_b,
        'overall': overall, 'ghosts': ghosts, 'other_result_row': other_result_row,
        'group_items': group_items,
    }


def test_per_round_is_native_shapes(app):
    """native 标记提取：兼容同步 HTTP 包装与事件回调裸 result 两种形态。"""
    proc = EvaluationResultProcessor()
    # 同步 HTTP：code/data → result → per_round_native
    assert proc._per_round_is_native(
        {'code': 0, 'data': {'result': {'per_round': [{'round_number': 1}],
                                         'per_round_native': True}}}) is True
    # 事件回调：裸 calc result
    assert proc._per_round_is_native(
        {'per_round': [{'round_number': 1}], 'per_round_native': True}) is True
    # 切片 fallback / 旧版无标记 → False
    assert proc._per_round_is_native({'per_round': [{'round_number': 1}]}) is False
    assert proc._per_round_is_native({'code': 0, 'data': {'result': {}}}) is False
    assert proc._per_round_is_native(None) is False


def test_native_cleanup_removes_ghosts_and_orphans(app, clean_env):
    """场景 a+b：native 重评落库后，round-0 幽灵行 / 孤儿切片行 / stopc 泄漏行被删；
    overall 整体行、接管族逐轮行、另一 result 的行、本次产出轮均不受影响。"""
    env = clean_env
    dims, result_a = env['dims'], env['result_a']
    proc = EvaluationResultProcessor()
    per_round = _real_per_round()   # success 产出轮{1,2}，latency 产出轮{1}，stopc/turn 产出 0

    n = proc._overwrite_round_results(
        result_a.id, per_round, env['group_items'], db.session, is_native=True)
    db.session.flush()
    # 写入计数 = success(轮1,轮2)=2 + latency(轮1)=1 = 3
    assert n == 3

    def _exists(trd_id):
        return db.session.query(TestResultDimension).get(trd_id) is not None

    def _round_rows(dim_id, round_idx):
        return db.session.query(TestResultDimension).filter(
            TestResultDimension.test_result_id == result_a.id,
            TestResultDimension.dimension_id == dim_id,
            TestResultDimension.round_number == round_idx).all()

    # ── 场景 a：幽灵行/孤儿切片行/泄漏行被删 ──
    assert not _exists(env['ghosts']['success_r0'].id)    # round-0 幽灵行删除
    assert not _exists(env['ghosts']['latency_r0'].id)    # round-0 幽灵行删除
    assert not _exists(env['ghosts']['success_r5'].id)    # 超产出轮孤儿删除
    assert not _exists(env['ghosts']['latency_r2'].id)    # latency 轮2 未产出 → 删除
    assert not _exists(env['ghosts']['stopc_r1'].id)      # stopc 0 产出 → 全删（dim66 泄漏自愈）

    # ── 场景 b：overall 整体行不受影响 ──
    for k, trd in env['overall'].items():
        assert _exists(trd.id), f'overall 行 {k} 被误删'
        assert db.session.query(TestResultDimension).get(trd.id).round_number is None

    # ── 场景 b：接管族（非打断族）逐轮行不受影响 ──
    assert _exists(env['ghosts']['turn_r1'].id)
    assert db.session.query(TestResultDimension).get(
        env['ghosts']['turn_r1'].id).dimension_value == 5.0

    # ── 场景 b：另一 result 的同维度逐轮行不受影响（跨 result 隔离）──
    assert _exists(env['other_result_row'].id)
    assert db.session.query(TestResultDimension).get(
        env['other_result_row'].id).dimension_value == 7.0

    # ── 本次产出轮保留且值正确 ──
    r1 = {r.dimension_id: r for r in _round_rows(dims['success'].id, 1)}
    assert r1[dims['success'].id].dimension_value == 1.0
    assert r1[dims['success'].id].evaluation_status == 'completed'  # pending 被覆盖
    assert _round_rows(dims['success'].id, 2)[0].dimension_value == 0.0
    assert _round_rows(dims['latency'].id, 1)[0].dimension_value == 300.0
    # success 逐轮行仅剩产出轮 {1,2}
    assert sorted(r.round_number for r in db.session.query(TestResultDimension).filter(
        TestResultDimension.test_result_id == result_a.id,
        TestResultDimension.dimension_id == dims['success'].id,
        TestResultDimension.round_number.isnot(None)).all()) == [1, 2]


def test_native_cleanup_skipped_when_nothing_produced(app, clean_env):
    """场景 c：judge 失败/降级 → per_round 全为跳过项（upserted=0）→ 不清理，既有行全保留。"""
    env = clean_env
    result_a = env['result_a']
    proc = EvaluationResultProcessor()
    # 全跳过项：无任何可投影值 → upserted=0
    skip_only = [{'round_number': 0, 'message': '跳过: 非计时轮(无打断时序)'},
                 {'round_number': 1, 'message': '跳过: 无时序数据'}]

    n = proc._overwrite_round_results(
        result_a.id, skip_only, env['group_items'], db.session, is_native=True)
    db.session.flush()
    assert n == 0   # 无产出 → 不触发清理

    # 所有预置逐轮脏行仍在（未误删）
    for key, trd in env['ghosts'].items():
        assert db.session.query(TestResultDimension).get(trd.id) is not None, f'{key} 被误删'
    assert db.session.query(TestResultDimension).get(env['other_result_row'].id) is not None


def test_slice_path_does_not_cleanup(app, clean_env):
    """场景 c：切片 fallback（is_native=False）即便有产出也不清理，避免轮失败误删既有好行。"""
    env = clean_env
    dims, result_a = env['dims'], env['result_a']
    proc = EvaluationResultProcessor()
    per_round = _real_per_round()

    n = proc._overwrite_round_results(
        result_a.id, per_round, env['group_items'], db.session, is_native=False)
    db.session.flush()
    assert n == 3   # 覆盖照常发生

    # 幽灵行/孤儿行仍在（切片路径不清理）
    for key in ('success_r0', 'latency_r0', 'success_r5', 'latency_r2', 'stopc_r1'):
        assert db.session.query(TestResultDimension).get(
            env['ghosts'][key].id) is not None, f'切片路径误删 {key}'
    # 接管族与另一 result 同样保留
    assert db.session.query(TestResultDimension).get(env['ghosts']['turn_r1'].id) is not None
    assert db.session.query(TestResultDimension).get(env['other_result_row'].id) is not None


def test_empty_per_round_no_cleanup(app, clean_env):
    """per_round 为空 → 提前返回 0，不触发任何清理。"""
    env = clean_env
    proc = EvaluationResultProcessor()
    n = proc._overwrite_round_results(
        env['result_a'].id, [], env['group_items'], db.session, is_native=True)
    assert n == 0
    for key, trd in env['ghosts'].items():
        assert db.session.query(TestResultDimension).get(trd.id) is not None, f'{key} 被误删'
