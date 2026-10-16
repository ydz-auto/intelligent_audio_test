# -*- coding: utf-8 -*-
"""VEGA-46 测试工程师独立验收用例

验收对象：`ReportUtils.get_resource_name()` 在 `api_id` / `device_id` 双空时抛
`UnboundLocalError: cannot access local variable 'base_resource'`。
修复提交：3faf9453（report_utils.py 仅新增 `base_resource = None` 一行 + 注释）。

验收标准逐条对应：
  AC1 双空（use_time_prefix 真 / 假两条路径）不再抛 UnboundLocalError，返回含 `0-默认资源` 的名称
      → TestAC1DoubleEmpty*
  AC2 既有行为不变：有 api_id / 有 device_id / 有 id 但查不到实体（未知api / 未知设备）
      → TestAC2ExistingBehaviourUnchanged（与「修复前函数体」逐例差分对照）
  AC3 新增测试通过 → 本文件（运行命令见文末）

与开发自测（test_report_resource_name_empty_ids.py）刻意不同的独立角度：
  1. 用**真实 DB 行**（Task + TestResult，api_id / device_id 均 NULL）而非 SimpleNamespace stub，
     并在用例内断言该行的两个外键确为 NULL，避免「因故没走到双空路径却通过」；
  2. 经**生产实际入口** `ReportControllerBase.get_resource_name()` 调用
     （evaluation_result_processor.py:902 与 report_controller*.py 的真实调用链），而非直接调 utils；
  3. AC2 用**修复前函数体差分对照**（同输入下 old 输出 == new 输出），而不是人工断言字面量，
     并对双空输入断言 old 必抛 UnboundLocalError —— 既证明 fixture 确为修复前版本，也证明修复增量恰好只有这一处。

运行（在 Intelligent-Audio-TEST/ 下，需本机 PostgreSQL 已启动：python start_postgres.py）：
    python -m pytest backend/tests/test_vega46_acceptance_independent.py -v
"""
import textwrap
from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.controllers.report_controller_base import ReportControllerBase
from backend.models.database import db
from backend.models.models import API, Device, Task, TestResult
from backend.utils.common.result_data_store import load_full_result_data
from backend.utils.report.report_utils import ReportUtils


# ==========================================================================
# 修复前（3faf9453^）的 get_resource_name 函数体，逐字取自
#   git show 3faf9453^:Intelligent-Audio-TEST/backend/utils/report/report_utils.py
# 用途：AC2 的差分对照基线。若将来有人改动既有分支行为，差分用例会失败。
# ==========================================================================
_OLD_FUNC_SRC = r'''def get_resource_name(result, task=None, use_time_prefix=False):
    """
    获取资源的唯一标识名称。

    统一格式：任务ID-时间-ID-名称小写-version-result_type后缀
    例如：t246-202603251543-16-plaud-1.0.0 或 t246-202603251543-16-plaud-1.0.0-recording

    确保唯一性，所有字母小写。
    支持根据 result_data 中的 result_type 添加后缀以区分不同结果类型（如 recording/fix）。
    """
    version = None
    result_type_suffix = ""

    try:
        if hasattr(result, 'result_data') and result.result_data:
            full_data = load_full_result_data(result.result_data, getattr(result, 'result_data_path', None))
            if isinstance(full_data, dict):
                result_type = full_data.get('result_type')
                if result_type and result_type != 'default':
                    result_type_suffix = f"-{result_type}"
    except:
        pass

    if use_time_prefix and task:
        prefix = ReportUtils.get_task_time_prefix(task)

        if hasattr(result, 'api_id') and result.api_id:
            api_id = result.api_id
            api = API.query.get(api_id)
            if api:
                version = ReportUtils._extract_api_version(api)
                base_resource = f"{api.id}-{api.name.lower()}"
            else:
                base_resource = f"{api_id}-未知api"

        elif hasattr(result, 'device_id') and result.device_id:
            device_id = result.device_id
            device = Device.query.get(device_id)
            if device:
                version = getattr(device, "app_version", None)
                base_resource = f"{device.id}-{device.name.lower()}"
            else:
                base_resource = f"{device_id}-未知设备"

        if not base_resource:
            if isinstance(result, dict):
                if result.get('api_id'):
                    base_resource = f"{result.get('api_id')}-未知api"
                elif result.get('device_id'):
                    base_resource = f"{result.get('device_id')}-未知设备"

        if not base_resource:
            base_resource = "0-默认资源"

        resource = f"{prefix}-{base_resource}"
        if version:
            resource = f"{resource}-{version}"
        return f"{resource}{result_type_suffix}"

    if hasattr(result, 'api_id') and result.api_id:
        api_id = result.api_id
        api = API.query.get(api_id)
        if api:
            version = ReportUtils._extract_api_version(api)
            base_resource = f"{api.id}-{api.name.lower()}"
        else:
            base_resource = f"{api_id}-未知api"

    elif hasattr(result, 'device_id') and result.device_id:
        device_id = result.device_id
        device = Device.query.get(device_id)
        if device:
            version = getattr(device, "app_version", None)
            base_resource = f"{device.id}-{device.name.lower()}"
        else:
            base_resource = f"{device_id}-未知设备"

    if not base_resource:
        if isinstance(result, dict):
            if result.get('api_id'):
                base_resource = f"{result.get('api_id')}-未知api"
            elif result.get('device_id'):
                base_resource = f"{result.get('device_id')}-未知设备"

    if not base_resource:
        base_resource = "0-默认资源"

    resource = base_resource
    if version:
        resource = f"{resource}-{version}"
    return f"{resource}{result_type_suffix}"'''


def _load_old_impl():
    """把修复前函数体 exec 成可调用对象，globals 复用当前被测依赖（未随本次改动变更）"""
    ns = {
        'API': API,
        'Device': Device,
        'ReportUtils': ReportUtils,
        'load_full_result_data': load_full_result_data,
    }
    src = textwrap.dedent(_OLD_FUNC_SRC)
    exec(compile(src, '<vega46_prefix_impl>', 'exec'), ns)
    return ns['get_resource_name']


# ==========================================================================
# 夹具
# ==========================================================================

TASK_STARTED_AT = datetime(2026, 3, 25, 15, 43)


@pytest.fixture
def real_rows(app):
    """真实 DB 行：Task + TestResult(api_id=NULL, device_id=NULL)

    TestResult.device_id 为 nullable=True、api_id 无 nullable=False 约束，
    故「双空」是数据库层面允许的真实状态（VEGA-36 同场景）。
    全部 flush 不 commit，随 app fixture 的外层事务回滚。
    """
    task = Task(
        name='VEGA46验收任务', type='api', status='completed',
        algorithm_type='asr', started_at=TASK_STARTED_AT,
    )
    db.session.add(task)
    db.session.flush()

    result = TestResult(
        task_id=task.id, test_case_id=None, device_id=None, api_id=None,
        algorithm_type='asr', execution_status='completed',
    )
    db.session.add(result)
    db.session.flush()
    return SimpleNamespace(task=task, result=result)


@pytest.fixture
def entities(app):
    """一组真实 API / Device 行，用于 AC2「有 id 且实体存在」"""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    device = Device(
        name=f'V46设备_{suffix}', model='M1', type='phone', system='Android',
        system_version='14', app_name='App', app_version='2.3.4', status='online',
    )
    api = API(
        name=f'V46API_{suffix}', vendor='volc_ast', status='online',
        meta={'version': '1.0.0'}, api_endpoints=[],
    )
    db.session.add_all([device, api])
    db.session.flush()
    return SimpleNamespace(device=device, api=api)


def _stub(**kwargs):
    """轻量 result stub（不设 result_data ⇒ 不触发结果数据读取）"""
    return SimpleNamespace(**kwargs)


# ==========================================================================
# AC1：双空路径不再抛 UnboundLocalError，返回含 0-默认资源 的名称
# ==========================================================================

class TestAC1DoubleEmpty:

    @pytest.mark.parametrize('use_time_prefix', [True, False])
    def test_real_row_double_null_via_production_entry(self, real_rows, use_time_prefix):
        """真实 TestResult 行双 NULL，经生产入口 ReportControllerBase 调用（AC1 主用例）"""
        result, task = real_rows.result, real_rows.task
        # 前置断言：确认这行确实是双空，否则本用例不成立
        assert result.api_id is None and result.device_id is None

        name = ReportControllerBase.get_resource_name(result, task, use_time_prefix=use_time_prefix)

        prefix = ReportUtils.get_task_time_prefix(task)
        assert prefix == f"t{task.id}-202603251543"
        expected = f"{prefix}-0-默认资源" if use_time_prefix else "0-默认资源"
        assert name == expected, f"期望 {expected}，实际 {name}"

    @pytest.mark.parametrize('use_time_prefix', [True, False])
    def test_real_row_double_null_matches_direct_utils_call(self, real_rows, use_time_prefix):
        """生产入口与直接调 utils 结果一致（排除包装层差异）"""
        result, task = real_rows.result, real_rows.task
        via_controller = ReportControllerBase.get_resource_name(result, task, use_time_prefix=use_time_prefix)
        via_utils = ReportUtils.get_resource_name(result, task, use_time_prefix=use_time_prefix)
        assert via_controller == via_utils == (
            f"{ReportUtils.get_task_time_prefix(task)}-0-默认资源" if use_time_prefix else "0-默认资源"
        )

    def test_real_row_double_null_would_crash_before_fix(self, real_rows):
        """同一真实行在修复前函数体上必抛 UnboundLocalError —— 证明触发条件真实成立"""
        result, task = real_rows.result, real_rows.task
        old = _load_old_impl()
        for use_time_prefix in (True, False):
            with pytest.raises(UnboundLocalError) as ei:
                old(result, task, use_time_prefix=use_time_prefix)
            assert 'base_resource' in str(ei.value)

    @pytest.mark.parametrize('use_time_prefix', [True, False])
    def test_missing_id_attributes(self, app, use_time_prefix):
        """result 上根本没有 api_id / device_id 属性（hasattr 为假）同样不崩"""
        task = SimpleNamespace(id=246, started_at=TASK_STARTED_AT)
        name = ReportUtils.get_resource_name(_stub(), task, use_time_prefix=use_time_prefix)
        assert name == ("t246-202603251543-0-默认资源" if use_time_prefix else "0-默认资源")

    @pytest.mark.parametrize('use_time_prefix', [True, False])
    @pytest.mark.parametrize('ids', [{'api_id': None, 'device_id': None},
                                     {'api_id': '', 'device_id': ''},
                                     {'api_id': None},
                                     {'device_id': None}])
    def test_various_empty_shapes(self, app, use_time_prefix, ids):
        """None / 空串 / 仅一个属性存在，均走兜底不抛异常"""
        task = SimpleNamespace(id=246, started_at=TASK_STARTED_AT)
        name = ReportUtils.get_resource_name(_stub(**ids), task, use_time_prefix=use_time_prefix)
        assert "0-默认资源" in name, name

    @pytest.mark.parametrize('use_time_prefix', [True, False])
    def test_dict_double_empty(self, app, use_time_prefix):
        """dict 形态入参双空：既有 dict 兜底分支仍可达"""
        task = SimpleNamespace(id=246, started_at=TASK_STARTED_AT)
        name = ReportUtils.get_resource_name({'api_id': None, 'device_id': None}, task,
                                             use_time_prefix=use_time_prefix)
        assert name == ("t246-202603251543-0-默认资源" if use_time_prefix else "0-默认资源")

    @pytest.mark.parametrize('use_time_prefix', [True, False])
    def test_both_fallback_sites_reachable(self, real_rows, use_time_prefix):
        """两处 `if not base_resource:`（:196 / :229）分别对应 use_time_prefix 真 / 假两条路径，
        改动前它们都不可达；此处按精确期望值分别钉住两条路径的产出。"""
        result, task = real_rows.result, real_rows.task
        name = ReportUtils.get_resource_name(result, task, use_time_prefix=use_time_prefix)
        if use_time_prefix:
            assert name.startswith("t"), "第一段逻辑（带任务时间前缀）未被走到"
        else:
            assert name == "0-默认资源", "第二段逻辑的兜底未被走到"


# ==========================================================================
# AC2：既有行为不变（与修复前函数体差分对照）
# ==========================================================================

def _case_matrix(entities, task):
    """case_id -> (result, use_time_prefix, task_arg, kind, expected_new)

    kind='unchanged'：修复前后必须逐字节一致，且等于 expected_new（AC2）
    kind='fixed'    ：修复前必抛 UnboundLocalError、修复后等于 expected_new（AC1）

    注：`dict` 形态入参在修复前同样抛 UnboundLocalError —— 普通 dict 不满足
    `hasattr(result, 'api_id')`，两个赋值分支都不进，故 `:229` 的 dict 兜底分支
    与「0-默认资源」兜底一样，改动前是死代码。本文件据此把 dict 用例归入 'fixed'。
    """
    api, device = entities.api, entities.device
    api_entity_name = f"{api.id}-{api.name.lower()}-1.0.0"
    device_entity_name = f"{device.id}-{device.name.lower()}-{device.app_version}"
    return {
        # —— 有 api_id 且实体存在 ——
        'api_entity':        (_stub(api_id=api.id, device_id=None), False, task, 'unchanged',
                              api_entity_name),
        'api_entity_prefix': (_stub(api_id=api.id, device_id=None), True, task, 'unchanged',
                              f"t246-202603251543-{api_entity_name}"),
        # —— 有 device_id 且实体存在 ——
        'device_entity':        (_stub(api_id=None, device_id=device.id), False, task, 'unchanged',
                                 device_entity_name),
        'device_entity_prefix': (_stub(api_id=None, device_id=device.id), True, task, 'unchanged',
                                 f"t246-202603251543-{device_entity_name}"),
        # —— 有 id 但查不到实体 ——
        'api_missing_entity':        (_stub(api_id=987654, device_id=None), False, task, 'unchanged',
                                      "987654-未知api"),
        'api_missing_entity_prefix': (_stub(api_id=987654, device_id=None), True, task, 'unchanged',
                                      "t246-202603251543-987654-未知api"),
        'device_missing_entity':        (_stub(api_id=None, device_id=987655), False, task, 'unchanged',
                                         "987655-未知设备"),
        'device_missing_entity_prefix': (_stub(api_id=None, device_id=987655), True, task, 'unchanged',
                                         "t246-202603251543-987655-未知设备"),
        # —— 优先级与后缀等既有分支 ——
        'api_wins_over_device': (_stub(api_id=api.id, device_id=device.id), False, task, 'unchanged',
                                 api_entity_name),
        'result_type_suffix':   (_stub(api_id=api.id, device_id=None,
                                       result_data={'result_type': 'recording'}), False, task,
                                 'unchanged', f"{api_entity_name}-recording"),
        'result_type_default_no_suffix': (_stub(api_id=api.id, device_id=None,
                                                result_data={'result_type': 'default'}), False, task,
                                          'unchanged', api_entity_name),
        # use_time_prefix=True 但 task 为空 → 落第二段逻辑，有 api_id 仍正常
        'no_task_with_prefix_flag': (_stub(api_id=api.id, device_id=None), True, None, 'unchanged',
                                     api_entity_name),
        # —— 双空（修复目标：修复前必抛 UnboundLocalError）——
        'empty_strings':  (_stub(api_id='', device_id=''), False, task, 'fixed', "0-默认资源"),
        'zero_ids':       (_stub(api_id=0, device_id=0), False, task, 'fixed', "0-默认资源"),
        'missing_attrs':  (_stub(), False, task, 'fixed', "0-默认资源"),
        'missing_attrs_prefix': (_stub(), True, task, 'fixed', "t246-202603251543-0-默认资源"),
        'empty_strings_prefix': (_stub(api_id='', device_id=''), True, task, 'fixed',
                                 "t246-202603251543-0-默认资源"),
        # dict 形态：修复前同样抛 UnboundLocalError（见 docstring）
        'dict_api_id':    ({'api_id': 999}, False, task, 'fixed', "999-未知api"),
        'dict_device_id': ({'device_id': 888}, False, task, 'fixed', "888-未知设备"),
        'dict_double_empty': ({'api_id': None, 'device_id': None}, False, task, 'fixed', "0-默认资源"),
    }


_CASE_MATRIX_KEYS = ['api_entity', 'api_entity_prefix', 'device_entity', 'device_entity_prefix',
                     'api_missing_entity', 'api_missing_entity_prefix',
                     'device_missing_entity', 'device_missing_entity_prefix',
                     'api_wins_over_device', 'result_type_suffix', 'result_type_default_no_suffix',
                     'no_task_with_prefix_flag', 'empty_strings', 'zero_ids',
                     'missing_attrs', 'missing_attrs_prefix', 'empty_strings_prefix',
                     'dict_api_id', 'dict_device_id', 'dict_double_empty']

_UNCHANGED_CASES = ['api_entity', 'api_entity_prefix', 'device_entity', 'device_entity_prefix',
                    'api_missing_entity', 'api_missing_entity_prefix',
                    'device_missing_entity', 'device_missing_entity_prefix',
                    'api_wins_over_device', 'result_type_suffix', 'result_type_default_no_suffix',
                    'no_task_with_prefix_flag']

_FIXED_CASES = ['empty_strings', 'zero_ids', 'missing_attrs', 'missing_attrs_prefix',
                'empty_strings_prefix', 'dict_api_id', 'dict_device_id', 'dict_double_empty']


class TestAC2ExistingBehaviourUnchanged:

    @pytest.mark.parametrize('case_id', _UNCHANGED_CASES)
    def test_old_and_new_impl_identical(self, app, entities, case_id):
        """修复前 / 修复后函数体同输入 → 输出完全一致，且等于既定期望值（既有行为不变）"""
        task = SimpleNamespace(id=246, started_at=TASK_STARTED_AT)
        result, use_time_prefix, task_arg, kind, expected = _case_matrix(entities, task)[case_id]
        assert kind == 'unchanged'

        old = _load_old_impl()
        old_out = old(result, task_arg, use_time_prefix=use_time_prefix)
        new_out = ReportUtils.get_resource_name(result, task_arg, use_time_prefix=use_time_prefix)

        assert old_out == new_out, f"{case_id}: 修复前 {old_out!r} != 修复后 {new_out!r}"
        assert new_out == expected, f"{case_id}: 期望 {expected!r}，实际 {new_out!r}"

    @pytest.mark.parametrize('case_id', _FIXED_CASES)
    def test_old_raises_new_returns_expected(self, app, entities, case_id):
        """修复增量只把「抛 UnboundLocalError」变成「按既有意图返回」，未改动其他输出"""
        task = SimpleNamespace(id=246, started_at=TASK_STARTED_AT)
        result, use_time_prefix, task_arg, kind, expected = _case_matrix(entities, task)[case_id]
        assert kind == 'fixed'

        old = _load_old_impl()
        with pytest.raises(UnboundLocalError) as ei:
            old(result, task_arg, use_time_prefix=use_time_prefix)
        assert 'base_resource' in str(ei.value)

        new_out = ReportUtils.get_resource_name(result, task_arg, use_time_prefix=use_time_prefix)
        assert new_out == expected, f"{case_id}: 期望 {expected!r}，实际 {new_out!r}"

    def test_exhaustive_differential_sweep(self, app, entities):
        """全组合差分扫描：修复前能跑通的输入，修复后输出必须逐字节一致

        维度：api_id × device_id × use_time_prefix × task 有无 × 入参形态（有属性 stub / 无属性 stub / dict）
        任一组合若「修复前不抛 UnboundLocalError」，则断言 old == new。
        这是 AC2「既有行为不变」的穷举式证据（非抽样）。
        """
        api, device = entities.api, entities.device
        task = SimpleNamespace(id=246, started_at=TASK_STARTED_AT)
        ids = [None, '', 0, api.id, device.id, 987654]
        old = _load_old_impl()

        def forms(a, d):
            yield _stub(api_id=a, device_id=d)
            yield {'api_id': a, 'device_id': d}
            yield _stub()                      # 两个属性都不存在
            yield _stub(api_id=a)              # 只有 api_id 属性
            yield _stub(device_id=d)           # 只有 device_id 属性

        compared = raised = 0
        for a in ids:
            for d in ids:
                for use_time_prefix in (True, False):
                    for task_arg in (task, None):
                        for result in forms(a, d):
                            new_out = ReportUtils.get_resource_name(
                                result, task_arg, use_time_prefix=use_time_prefix)
                            try:
                                old_out = old(result, task_arg, use_time_prefix=use_time_prefix)
                            except UnboundLocalError:
                                raised += 1
                                assert "0-默认资源" in new_out or "未知" in new_out, \
                                    f"修复前崩溃的组合修复后未落到兜底: {new_out!r}"
                                continue
                            assert old_out == new_out, (
                                f"既有行为被改动: api_id={a!r} device_id={d!r} "
                                f"prefix={use_time_prefix} task={task_arg is not None} "
                                f"form={type(result).__name__}: old={old_out!r} new={new_out!r}")
                            compared += 1

        # 扫描规模自检：既要有大量「行为不变」样本，也要有「修复前崩溃」样本
        assert compared > 100, compared
        assert raised > 0, raised
        print(f"\n[VEGA-46 差分扫描] 行为一致 {compared} 例 / 修复前崩溃 {raised} 例")

    def test_unknown_entity_labels_pinned(self, app):
        """「有 id 查不到实体」的既有标签未被本次初始化改写（字面钉住）"""
        task = SimpleNamespace(id=246, started_at=TASK_STARTED_AT)
        assert ReportUtils.get_resource_name(_stub(api_id=987654), task) == "987654-未知api"
        assert ReportUtils.get_resource_name(_stub(device_id=987655), task) == "987655-未知设备"
        assert ReportUtils.get_resource_name(_stub(api_id=987654), task, use_time_prefix=True) == \
            "t246-202603251543-987654-未知api"
        assert ReportUtils.get_resource_name(_stub(device_id=987655), task, use_time_prefix=True) == \
            "t246-202603251543-987655-未知设备"

    def test_entity_name_version_pinned(self, app, entities):
        """有实体时 {id}-{name小写}-{version} 形态未被改写"""
        task = SimpleNamespace(id=246, started_at=TASK_STARTED_AT)
        api, device = entities.api, entities.device
        assert ReportUtils.get_resource_name(_stub(api_id=api.id), task) == \
            f"{api.id}-{api.name.lower()}-1.0.0"
        assert ReportUtils.get_resource_name(_stub(device_id=device.id), task) == \
            f"{device.id}-{device.name.lower()}-{device.app_version}"


# ==========================================================================
# 修复范围检查：report_utils.py 本次只多一行初始化，未动其他函数
# ==========================================================================

def test_version_still_initialized_at_entry(app):
    """`version` 在入口初始化为 None（既有，:159）—— 双空路径下 `if version:` 不会 UnboundLocalError"""
    task = SimpleNamespace(id=246, started_at=TASK_STARTED_AT)
    # 双空且 result_data 带后缀，覆盖 version 与 result_type_suffix 同时参与的返回拼装
    name = ReportUtils.get_resource_name(
        _stub(api_id=None, device_id=None, result_data={'result_type': 'recording'}), task)
    assert name == "0-默认资源-recording"
