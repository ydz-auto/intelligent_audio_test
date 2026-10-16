# -*- coding: utf-8 -*-
"""VEGA-46 开发自测：report_utils.get_resource_name 在 api_id/device_id 双空时的兜底

背景（VEGA-46）：
    `ReportUtils.get_resource_name()` 中 `base_resource` 只在 `if api_id:` / `elif device_id:`
    两个分支内赋值。两个分支都不进入（api_id 与 device_id 均空，或属性不存在）时，
    紧随其后的 `if not base_resource:` 会抛
    `UnboundLocalError: cannot access local variable 'base_resource' ...`，
    使原本为「双空」准备的 `"0-默认资源"` 兜底永远不可达。

本文件覆盖三条验收标准：
    1. 双空（use_time_prefix 真 / 假两条路径）不再抛异常，返回含 `0-默认资源` 的名称；
    2. 既有行为不变：有 api_id、有 device_id、以及「有 id 但查不到实体」（未知api / 未知设备）；
    3. 顺带覆盖 `dict` 形态入参与「属性不存在」形态入参。

运行（在 Intelligent-Audio-TEST/ 下，需本机 PostgreSQL 已启动 python start_postgres.py）：
    python -m pytest backend/tests/test_report_resource_name_empty_ids.py -v
"""
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.models.database import db
from backend.models.models import API, Device
from backend.utils.report.report_utils import ReportUtils


# --------------------------------------------------------------------------
# 夹具：任务前缀用轻量 stub（get_task_time_prefix 只读 id / started_at）
# --------------------------------------------------------------------------

_TASK = SimpleNamespace(id=246, started_at=datetime(2026, 3, 25, 15, 43))
_PREFIX = "t246-202603251543"


def _result(**kwargs):
    """轻量 result stub：只带 get_resource_name 会读到的属性

    不设 result_data ⇒ 跳过 load_full_result_data，测试不依赖结果数据存储。
    """
    return SimpleNamespace(**kwargs)


@pytest.fixture
def entities(app):
    """造一组真实 API / Device 行（flush 不 commit，测试结束随外层事务回滚）"""
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


# --------------------------------------------------------------------------
# 验收标准 1：双空不再抛 UnboundLocalError，返回默认资源名
# --------------------------------------------------------------------------

@pytest.mark.parametrize('use_time_prefix', [True, False])
def test_both_ids_empty_returns_default_resource(app, use_time_prefix):
    """api_id / device_id 双空：两条路径都返回 0-默认资源（改动前抛 UnboundLocalError）"""
    result = _result(api_id=None, device_id=None)

    name = ReportUtils.get_resource_name(result, _TASK, use_time_prefix=use_time_prefix)

    assert "0-默认资源" in name, name
    expected = f"{_PREFIX}-0-默认资源" if use_time_prefix else "0-默认资源"
    assert name == expected, f"期望 {expected}，实际 {name}"


def test_both_ids_empty_without_task_returns_default_resource(app):
    """use_time_prefix=True 但 task 为空 → 落到第二段逻辑，同样返回默认资源"""
    result = _result(api_id=None, device_id=None)

    name = ReportUtils.get_resource_name(result, None, use_time_prefix=True)

    assert name == "0-默认资源", name


def test_missing_id_attributes_returns_default_resource(app):
    """result 上根本没有 api_id / device_id 属性（hasattr 为假）也不应崩"""
    result = _result()

    assert ReportUtils.get_resource_name(result, _TASK, use_time_prefix=True) == \
        f"{_PREFIX}-0-默认资源"
    assert ReportUtils.get_resource_name(result, _TASK, use_time_prefix=False) == "0-默认资源"


@pytest.mark.parametrize('use_time_prefix', [True, False])
def test_empty_string_ids_returns_default_resource(app, use_time_prefix):
    """空串（而非 None）同样视为"无资源"，走同一兜底"""
    result = _result(api_id="", device_id="")

    name = ReportUtils.get_resource_name(result, _TASK, use_time_prefix=use_time_prefix)
    assert "0-默认资源" in name, name


@pytest.mark.parametrize('use_time_prefix', [True, False])
def test_dict_both_ids_empty_returns_default_resource(app, use_time_prefix):
    """dict 形态入参：双空同样返回默认资源（既有 dict 分支保持可达）"""
    result = {'api_id': None, 'device_id': None}

    name = ReportUtils.get_resource_name(result, _TASK, use_time_prefix=use_time_prefix)
    assert "0-默认资源" in name, name


def test_dict_with_id_uses_unknown_fallback(app):
    """dict 带 id（无实体查询能力）→ 未知api / 未知设备，非默认资源"""
    assert ReportUtils.get_resource_name({'api_id': 999}, _TASK, use_time_prefix=False) == \
        "999-未知api"
    assert ReportUtils.get_resource_name({'device_id': 888}, _TASK, use_time_prefix=False) == \
        "888-未知设备"


# --------------------------------------------------------------------------
# 验收标准 2：既有行为不变
# --------------------------------------------------------------------------

def test_with_api_id_unchanged(app, entities):
    """有 api_id 且实体存在：{api.id}-{name小写}[-version]"""
    api = entities.api
    result = _result(api_id=api.id, device_id=None)

    expected = f"{api.id}-{api.name.lower()}-1.0.0"
    assert ReportUtils.get_resource_name(result, _TASK, use_time_prefix=False) == expected
    assert ReportUtils.get_resource_name(result, _TASK, use_time_prefix=True) == \
        f"{_PREFIX}-{expected}"


def test_with_device_id_unchanged(app, entities):
    """有 device_id 且实体存在：{device.id}-{name小写}-{app_version}"""
    device = entities.device
    result = _result(api_id=None, device_id=device.id)

    expected = f"{device.id}-{device.name.lower()}-{device.app_version}"
    assert ReportUtils.get_resource_name(result, _TASK, use_time_prefix=False) == expected
    assert ReportUtils.get_resource_name(result, _TASK, use_time_prefix=True) == \
        f"{_PREFIX}-{expected}"


def test_api_id_present_but_entity_missing(app):
    """有 api_id 但查不到实体 → {id}-未知api"""
    result = _result(api_id=987654, device_id=None)

    assert ReportUtils.get_resource_name(result, _TASK, use_time_prefix=False) == \
        "987654-未知api"
    assert ReportUtils.get_resource_name(result, _TASK, use_time_prefix=True) == \
        f"{_PREFIX}-987654-未知api"


def test_device_id_present_but_entity_missing(app):
    """有 device_id 但查不到实体 → {id}-未知设备"""
    result = _result(api_id=None, device_id=987655)

    assert ReportUtils.get_resource_name(result, _TASK, use_time_prefix=False) == \
        "987655-未知设备"
    assert ReportUtils.get_resource_name(result, _TASK, use_time_prefix=True) == \
        f"{_PREFIX}-987655-未知设备"


def test_api_id_takes_precedence_over_device_id(app, entities):
    """api_id 与 device_id 同时存在时以 api_id 为准（既有优先级不变）"""
    result = _result(api_id=entities.api.id, device_id=entities.device.id)

    name = ReportUtils.get_resource_name(result, _TASK, use_time_prefix=False)
    assert name.startswith(f"{entities.api.id}-"), name
    assert "未知设备" not in name, name


def test_result_type_suffix_unchanged(app):
    """result_type 后缀逻辑不受本次改动影响（default 不加后缀，其余追加）"""
    default_result = _result(api_id=None, device_id=None)
    assert ReportUtils.get_resource_name(default_result, _TASK, use_time_prefix=False) == \
        "0-默认资源"

    # result_data 为普通 dict（非 'default'）→ 追加后缀
    suffix_result = _result(api_id=None, device_id=None, result_data={'result_type': 'recording'})
    assert ReportUtils.get_resource_name(suffix_result, _TASK, use_time_prefix=False) == \
        "0-默认资源-recording"
