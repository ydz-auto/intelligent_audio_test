# -*- coding: utf-8 -*-
"""INT-2095 voice_llm 用例参数定义恢复种子（seed_voice_llm_case_params_int2095.py）
计划层契约测试。

覆盖：
- 软删 10 行 → 10 个 restore（回拨 deleted=false，不新造重复行）；
- 已是目标状态 → 全 skip（重复执行 0 变更，幂等）；
- 行被硬删 → insert（按 §接口 表重插）；
- 活行字段漂移 → update（字段对齐）；
- 同自然键软删+活行并存 → 优先活行；
- 目标参数表与卡面 §接口 表一一对应（10 个 param_code 与类型）。
"""
import importlib.util
import os
import sys

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_SEED_PATH = os.path.join(
    _REPO_ROOT, 'scripts', 'migrations', '202610',
    'seed_voice_llm_case_params_int2095.py',
)


def _load_seed_module():
    spec = importlib.util.spec_from_file_location('seed_int2095_case_params', _SEED_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_seed = _load_seed_module()


def _spec_row(code):
    """从 TARGET_CASE_PARAMS 取目标定义，作为「活行已一致」的基准行。"""
    return {s['param_code']: s for s in _seed.TARGET_CASE_PARAMS}[code]


def _make_row(code, deleted=False, pid=None, **overrides):
    row = dict(_spec_row(code))
    row.update({'param_code': code, 'deleted': deleted, 'id': pid})
    row.update(overrides)
    return row


def _ops_by_code(ops):
    return {op['param_code']: op for op in ops}


def _expect_all_restores(ops):
    assert len(ops) == len(_seed.TARGET_CASE_PARAMS)
    by_code = _ops_by_code(ops)
    for spec in _seed.TARGET_CASE_PARAMS:
        assert by_code[spec['param_code']]['op'] == 'restore'


def test_target_matches_int2095_spec_table():
    """目标参数表与卡面 §接口 表一一对应（10 个参数、自然键、类型/scope/ui_order）。"""
    assert len(_seed.TARGET_CASE_PARAMS) == 10
    codes = [s['param_code'] for s in _seed.TARGET_CASE_PARAMS]
    assert codes == [
        'interferers', 'record_mode', 'type', 'timing', 'is_interruption',
        'stop_intent', 'is_return_to_topic', 'is_reject', 'is_single_round',
        'correctAnswer',
    ]
    assert {s['param_type'] for s in _seed.TARGET_CASE_PARAMS} == {'text', 'json', 'switch'}
    # scope 用后端 CaseParamScope 现行词表（common + DeviceType 三值）；
    # 旧词表 e2e 已废弃，物理侧统一为 physical
    assert {s['param_code']: s['scope'] for s in _seed.TARGET_CASE_PARAMS}['interferers'] == 'physical'


def test_restores_all_soft_deleted_rows():
    """真实库现状（10 行全软删）→ 全 restore，携带回拨 id，不新插。"""
    existing = [_make_row(s['param_code'], deleted=True, pid=42 + i)
                for i, s in enumerate(_seed.TARGET_CASE_PARAMS)]
    ops = _seed.plan_case_params_changes(existing)
    _expect_all_restores(ops)
    by_code = _ops_by_code(ops)
    assert all(by_code[s['param_code']]['id'] is not None
               for s in _seed.TARGET_CASE_PARAMS)


def test_idempotent_when_already_applied():
    """恢复后重跑：活行与 §接口 表一致 → 全 skip（重复执行 0 变更）。"""
    existing = [_make_row(s['param_code'], deleted=False, pid=42 + i)
                for i, s in enumerate(_seed.TARGET_CASE_PARAMS)]
    ops = _seed.plan_case_params_changes(existing)
    assert len(ops) == 10
    assert all(op['op'] == 'skip' for op in ops)


def test_inserts_hard_deleted_or_missing_rows():
    """自然键不存在（行被硬删 / 全新库）→ insert。"""
    ops = _seed.plan_case_params_changes([])
    assert len(ops) == 10
    assert all(op['op'] == 'insert' for op in ops)


def test_updates_drifted_active_row():
    """活行存在但字段与 §接口 表不一致 → update（不软删、不重插）。"""
    existing = [
        _make_row('record_mode', deleted=False, pid=44, help_text='漂移的展示文案'),
        _make_row('type', deleted=False, pid=45),
    ]
    ops = _ops_by_code(_seed.plan_case_params_changes(existing))
    assert ops['record_mode']['op'] == 'update'
    assert ops['record_mode']['id'] == 44
    assert ops['type']['op'] == 'skip'
    # 其余目标参数缺失 → insert
    assert ops['interferers']['op'] == 'insert'


def test_prefers_active_row_on_duplicate_natural_key():
    """同自然键（algorithm_type+param_code）软删与活行并存时，优先活行。"""
    existing = [
        _make_row('timing', deleted=True, pid=46),
        _make_row('timing', deleted=False, pid=99),
    ]
    ops = _ops_by_code(_seed.plan_case_params_changes(existing))
    assert ops['timing']['op'] == 'skip'
    assert ops['timing']['id'] == 99
