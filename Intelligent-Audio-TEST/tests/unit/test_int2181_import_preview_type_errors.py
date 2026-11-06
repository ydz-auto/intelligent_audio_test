# -*- coding: utf-8 -*-
"""INT-2181：导入预览行级 errors 与导入回执同口径（类型错误行）。

缺陷（INT-2178 走查）：预览只跑 `_validate_imported_case`（名称非空），
导入还会跑 `_build_case_payload` 的纯计算，`tags` 非数组等类型错误只在导入
时才报，预览 `errors=[]`，前端按 `totalRows - errors.length` 算出的可导入
条数偏多。

约束：
- 预览与导入共用同一段行级校验（`_validate_row_full` = 名称校验 +
  `_build_case_payload` 纯计算），错误文案 `第{N}行: 原因` 逐条可比；
- 名称必须是非空字符串（打回项：JSON/旧版 Excel 的数字名称此前预览漏报，
  导入才在 `_find_existing_case` 的 `.strip()` 上抛 AttributeError）；
- 每个坏行只出 1 条；预览只读：不建分组、不写库；
- 落库 / 参考参数恢复等写路径异常不在预览范围内（仍只出现在导入回执）。

全部用例在宿主树直跑服务层（不经容器镜像），DB/写路径依赖用 monkeypatch 隔离。
"""
import io
import json
import zipfile

import pandas as pd
import pytest

from api_gateway.application.services.testcase import (
    testcase_import_service as _tis_module,
)
from api_gateway.application.services.testcase.testcase_import_service import (
    TestCaseImportService,
)
from api_gateway.infrastructure.request_adapter import set_current_request

try:
    import openpyxl  # noqa: F401
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False

_requires_openpyxl = pytest.mark.skipif(
    not _HAS_OPENPYXL, reason='openpyxl 未安装，Excel 用例跳过')


class _FakeAudioAcl:
    """INT-2182 合入适配：行级校验新增「引用音频存在性」查库，单测按全部存在放行。

    本文件聚焦 类型校验/名称校验 的同口径，不覆盖音频引用；若不桩掉，合法夹具里
    的 `audio_id=1` 会被判「音频 1 不存在」，与 `test_valid_rows_have_no_errors`
    的意图冲突（INT-2182 的引用校验另有自己的单测）。
    """

    @staticmethod
    def get_by_ids(payload):
        ids = [int(i) for i in ((payload or {}).get('ids') or [])]
        return {'success': True, 'data': [{'id': i} for i in ids]}


def _stub_audio_acl(monkeypatch):
    monkeypatch.setattr(_tis_module, '_audio_acl', _FakeAudioAcl())


class _FakeRequest:
    """最小 request 替身：只提供 request.files 所需的 state._files。"""

    def __init__(self, files):
        self.state = type('_State', (), {'_files': files})()


class _FakeUpload:
    """Flask FileStorage 替身（filename + 同步 read，供 _UploadedFile 包装）。"""

    def __init__(self, filename, data):
        self.filename = filename
        self.file = io.BytesIO(data)


def _preview(filename, data, monkeypatch):
    """调用 preview_import，返回 (payload_dict, http_code)；同时守预览只读。"""
    monkeypatch.setattr(
        TestCaseImportService, '_lookup_group',
        staticmethod(lambda case_data: None))
    monkeypatch.setattr(
        TestCaseImportService, '_find_existing_case',
        staticmethod(lambda case_data, group=None: (None, None)))
    monkeypatch.setattr(
        TestCaseImportService, '_resolve_or_create_group',
        staticmethod(lambda case_data: pytest.fail('预览不得建分组/写库')))
    monkeypatch.setattr(
        TestCaseImportService, '_persist_case',
        staticmethod(lambda *a, **k: pytest.fail('预览不得写库')))
    _stub_audio_acl(monkeypatch)
    set_current_request(_FakeRequest({'file': _FakeUpload(filename, data)}))
    try:
        return TestCaseImportService.preview_import()
    finally:
        set_current_request(None)


def _preview_data(filename, data, monkeypatch):
    payload, code = _preview(filename, data, monkeypatch)
    assert code == 200, payload
    assert payload['success'] is True
    return payload['data']


def _import_errors(filename, data, monkeypatch):
    """同一文件走导入路径，只把落库/写库动作替换成空实现，返回 errors。"""
    rows = TestCaseImportService._parse_rows_for_validation(io.BytesIO(data),
                                                           _fmt(filename))
    monkeypatch.setattr(TestCaseImportService, '_resolve_or_create_group',
                        staticmethod(lambda case_data: None))
    monkeypatch.setattr(TestCaseImportService, '_find_existing_case',
                        staticmethod(lambda case_data, group=None: (None, None)))
    monkeypatch.setattr(TestCaseImportService, '_persist_case',
                        staticmethod(lambda payload, existing, strategy, group: 1))
    monkeypatch.setattr(TestCaseImportService, '_restore_reference_params',
                        staticmethod(lambda case_id, case_data, errors, idx: None))
    _stub_audio_acl(monkeypatch)
    _, _, _, _, errors = TestCaseImportService._create_cases_from_rows(rows)
    return errors


def _fmt(filename):
    return TestCaseImportService._detect_import_format(filename)


def _json_bytes(cases):
    return json.dumps({'test_cases': cases}, ensure_ascii=False).encode('utf-8')


def _zip_bytes(cases):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('testcases.json',
                    json.dumps({'test_cases': cases}, ensure_ascii=False))
    return buf.getvalue()


GOOD = {'name': '接线测试_INT2181_ok', 'group': '接线测试_INT2181组'}


def _row(name, **extra):
    return dict(GOOD, name=name, **extra)


# ----------------------------------------------------------------------
# 缺陷复现：tags 非数组
# ----------------------------------------------------------------------
def test_json_tags_not_list_reports_in_preview(monkeypatch):
    cases = [GOOD, _row('接线测试_INT2181_tags', tags=123)]
    data = _preview_data('type_error.json', _json_bytes(cases), monkeypatch)
    assert data['totalRows'] == 2
    assert data['errors'] == ["第2行: 'int' object is not iterable"]


def test_zip_tags_not_list_reports_in_preview(monkeypatch):
    cases = [GOOD, _row('接线测试_INT2181_tags', tags=123)]
    data = _preview_data('type_error.zip', _zip_bytes(cases), monkeypatch)
    assert data['totalRows'] == 2
    assert data['errors'] == ["第2行: 'int' object is not iterable"]


def test_audios_item_not_dict_reports_in_preview(monkeypatch):
    cases = [GOOD, _row('接线测试_INT2181_audios', audios=[123])]
    data = _preview_data('type_error.json', _json_bytes(cases), monkeypatch)
    assert data['totalRows'] == 2
    assert data['errors'] == ["第2行: 'int' object has no attribute 'get'"]


# ----------------------------------------------------------------------
# 与导入回执逐条可比
# ----------------------------------------------------------------------
def test_preview_errors_equal_import_receipt(monkeypatch):
    cases = [
        GOOD,
        _row('接线测试_INT2181_tags', tags=123),
        _row('接线测试_INT2181_audios', audios=[123]),
        {'name': '', 'group': '接线测试_INT2181组'},
        _row('接线测试_INT2181_ok2'),
    ]
    raw = _json_bytes(cases)
    preview = _preview_data('parity.json', raw, monkeypatch)
    import_errors = _import_errors('parity.json', raw, monkeypatch)

    assert preview['totalRows'] == 5
    assert preview['errors'] == import_errors
    assert preview['errors'] == [
        "第2行: 'int' object is not iterable",
        "第3行: 'int' object has no attribute 'get'",
        '第4行: 用例名称不能为空',
    ]


def test_bad_row_still_one_error(monkeypatch):
    """一行既名称空又 tags 非法 → 仍只出 1 条（名称优先，与导入一致）。"""
    cases = [GOOD, {'name': '', 'group': 123, 'tags': 123, 'audios': 5}]
    data = _preview_data('one.json', _json_bytes(cases), monkeypatch)
    assert data['errors'] == ['第2行: 用例名称不能为空']


# ----------------------------------------------------------------------
# 合法行不受影响
# ----------------------------------------------------------------------
def test_valid_rows_have_no_errors(monkeypatch):
    cases = [
        GOOD,
        _row('接线测试_INT2181_full', description='d', tags=['a', 'b'],
             audios=[{'audio_id': 1, 'spl': 60, 'play_order': 1}],
             dimensions=[{'id': 7}]),
        _row('接线测试_INT2181_rounds',
             config={'rounds': [{'roundNumber': 1, 'audios': []}]}),
    ]
    data = _preview_data('ok.json', _json_bytes(cases), monkeypatch)
    assert data['totalRows'] == 3
    assert data['errors'] == []


def test_preview_does_not_write_or_create_group(monkeypatch):
    """预览全程不得走写路径/建分组（_preview 里已把两者设成 fail）。"""
    cases = [GOOD, _row('接线测试_INT2181_tags', tags=123)]
    data = _preview_data('readonly.json', _json_bytes(cases), monkeypatch)
    assert data['errors'] == ["第2行: 'int' object is not iterable"]
    # 原始预览行不被校验口径改写
    assert [c.get('name') for c in data['testCases']] == [
        GOOD['name'], '接线测试_INT2181_tags']


# ----------------------------------------------------------------------
# 复测缺口（打回项）：name 非字符串两侧同口径
# ----------------------------------------------------------------------
NAME_TYPE_MSG = '第2行: 用例名称必须是字符串'


def test_json_name_not_string_reports_in_preview(monkeypatch):
    """JSON `name: 12345`：预览即报，且与导入回执同一条。"""
    cases = [GOOD, {'name': 12345, 'group': GOOD['group']}]
    raw = _json_bytes(cases)
    preview = _preview_data('name_type.json', raw, monkeypatch)
    assert preview['totalRows'] == 2
    assert preview['errors'] == [NAME_TYPE_MSG]
    assert _import_errors('name_type.json', raw, monkeypatch) == preview['errors']


def test_zip_name_not_string_reports_in_preview(monkeypatch):
    cases = [GOOD, {'name': 12345, 'group': GOOD['group']}]
    raw = _zip_bytes(cases)
    preview = _preview_data('name_type.zip', raw, monkeypatch)
    assert preview['errors'] == [NAME_TYPE_MSG]
    assert _import_errors('name_type.zip', raw, monkeypatch) == preview['errors']


def _excel_legacy_bytes(rows):
    """旧版单 Sheet Excel（列 用例名称）：数字名称单元格读回为 int。"""
    df = pd.DataFrame(rows, columns=['用例名称', '分组'])
    buf = io.BytesIO()
    df.to_excel(buf, sheet_name='Sheet1', index=False, engine='openpyxl')
    return buf.getvalue()


@_requires_openpyxl
def test_excel_numeric_name_reports_in_preview(monkeypatch):
    """旧版 Excel 用例名称填数字（单元格 int）：预览与导入回执同一条。"""
    rows = [
        [GOOD['name'], GOOD['group']],
        [12345, GOOD['group']],
    ]
    raw = _excel_legacy_bytes(rows)
    preview = _preview_data('name_type.xlsx', raw, monkeypatch)
    assert preview['totalRows'] == 2
    assert preview['errors'] == [NAME_TYPE_MSG]
    assert _import_errors('name_type.xlsx', raw, monkeypatch) == preview['errors']


def test_name_type_error_precedence_over_payload_error(monkeypatch):
    """名称非字符串且 tags 非法 → 仍只出 1 条，名称类型优先（两侧一致）。"""
    cases = [GOOD, {'name': 12345, 'group': GOOD['group'], 'tags': 123}]
    raw = _json_bytes(cases)
    preview = _preview_data('name_type_mixed.json', raw, monkeypatch)
    assert preview['errors'] == [NAME_TYPE_MSG]
    assert _import_errors('name_type_mixed.json', raw, monkeypatch) == preview['errors']
