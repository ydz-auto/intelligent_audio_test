# -*- coding: utf-8 -*-
"""INT-2157 / INT-2158：导入预览 `data.errors` 行级校验。

约束（父卡 INT-2157）：
- 校验行由导入同一解析函数产出（_parse_json_file / _parse_csv_rows /
  _parse_excel_rows / _parse_zip_rows），逐行 _validate_imported_case；
- 行号 enumerate(rows, 1)，与导入回执 `第{idx+1}行` 完全对齐；
- 每个坏行只出 1 条；全量校验，无真截断字段；
- 旧版单 Sheet Excel 也补齐预览行（totalRows 与 errors 枚举行数一致）；
- 预览只读：不建分组、不写库。

全部用例在宿主树直跑服务层（不经容器镜像），DB 依赖用 monkeypatch 隔离。
"""
import io
import json
import zipfile

import pandas as pd
import pytest

from api_gateway.application.services.testcase.testcase_import_service import (
    TestCaseImportService,
)
from api_gateway.infrastructure.request_adapter import set_current_request


class _FakeRequest:
    """最小 request 替身：只提供 request.files 所需的 state._files。"""

    def __init__(self, files):
        self.state = type('_State', (), {'_files': files})()


class _FakeUpload:
    """Flask FileStorage 替身（filename + 同步 read，供 _UploadedFile 包装）。"""

    def __init__(self, filename, data):
        self.filename = filename
        self.file = io.BytesIO(data)


def _preview(filename, data, monkeypatch, find_existing=None):
    """调用 preview_import，返回 (payload_dict, http_code)。"""
    monkeypatch.setattr(
        TestCaseImportService, '_lookup_group',
        staticmethod(lambda case_data: None))
    monkeypatch.setattr(
        TestCaseImportService, '_find_existing_case',
        staticmethod(find_existing or (lambda case_data, group=None: (None, None))))
    monkeypatch.setattr(
        TestCaseImportService, '_resolve_or_create_group',
        staticmethod(lambda case_data: pytest.fail('预览不得建分组/写库')))
    set_current_request(_FakeRequest({'file': _FakeUpload(filename, data)}))
    try:
        return TestCaseImportService.preview_import()
    finally:
        set_current_request(None)


def _preview_data(filename, data, monkeypatch, find_existing=None):
    payload, code = _preview(filename, data, monkeypatch, find_existing)
    assert code == 200, payload
    assert payload['success'] is True
    return payload['data']


# ----------------------------------------------------------------------
# 样本构造
# ----------------------------------------------------------------------
def _json_bytes(cases):
    return json.dumps({'test_cases': cases}, ensure_ascii=False).encode('utf-8')


def _csv_bytes(rows, header=('用例名称', '描述')):
    lines = [','.join(header)]
    lines.extend(','.join(r) for r in rows)
    return ('\n'.join(lines) + '\n').encode('utf-8')


def _excel_new_bytes(rows):
    """新版 Excel：TestCases Sheet（列 NAME / ID）。"""
    df = pd.DataFrame(rows, columns=['ID', 'NAME', 'DESCRIPTION'])
    buf = io.BytesIO()
    df.to_excel(buf, sheet_name='TestCases', index=False, engine='openpyxl')
    return buf.getvalue()


def _excel_legacy_bytes(rows):
    """旧版 Excel：单 Sheet，列名 用例名称。"""
    df = pd.DataFrame(rows, columns=['用例名称', '描述'])
    buf = io.BytesIO()
    df.to_excel(buf, sheet_name='Sheet1', index=False, engine='openpyxl')
    return buf.getvalue()


def _zip_bytes(cases, extra_files=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('testcases.json', json.dumps({'test_cases': cases}, ensure_ascii=False))
        for name, content in (extra_files or {}).items():
            zf.writestr(name, content)
    return buf.getvalue()


GOOD = {'name': '接线测试_INT2157_ok', 'group': '接线测试_INT2157_grp'}
BAD = {'name': '', 'group': '接线测试_INT2157_grp'}
EXPECT_ROW2 = '第2行: 用例名称不能为空'


# ----------------------------------------------------------------------
# A1~A5 四种格式
# ----------------------------------------------------------------------
def test_a1_json_row_error(monkeypatch):
    data = _preview_data('cases.json', _json_bytes([GOOD, BAD]), monkeypatch)
    assert data['totalRows'] == 2
    assert data['errors'] == [EXPECT_ROW2]
    # testCases 仍是原始行，不被校验口径改写
    assert [c.get('name') for c in data['testCases']] == [GOOD['name'], '']


def test_a2_csv_row_error(monkeypatch):
    data = _preview_data(
        'cases.csv', _csv_bytes([('接线测试_INT2157_ok', 'x'), ('', 'y')]), monkeypatch)
    assert data['totalRows'] == 2
    assert data['errors'] == [EXPECT_ROW2]


def test_a3_excel_new_format_row_error(monkeypatch):
    data = _preview_data(
        'cases.xlsx',
        _excel_new_bytes([['', '接线测试_INT2157_ok', 'd'], ['', '', 'd2']]),
        monkeypatch)
    assert data['totalRows'] == 2
    assert data['errors'] == [EXPECT_ROW2]


def test_a4_excel_legacy_single_sheet_row_error(monkeypatch):
    """行为变更：旧版单 Sheet 此前 totalRows=0，现补齐预览行。"""
    data = _preview_data(
        'legacy.xlsx',
        _excel_legacy_bytes([['接线测试_INT2157_ok', 'd'], ['', 'y']]),
        monkeypatch)
    assert data['totalRows'] == 2
    assert len(data['testCases']) == 2
    assert data['errors'] == [EXPECT_ROW2]


def test_a5_zip_row_error_and_no_reference_content(monkeypatch):
    cases = [GOOD, dict(BAD, reference_params_content={'1': {'a': 1}})]
    payload, code = _preview('cases.zip', _zip_bytes(cases), monkeypatch)
    assert code == 200
    data = payload['data']
    assert data['totalRows'] == 2
    assert data['errors'] == [EXPECT_ROW2]
    assert 'reference_params_content' not in json.dumps(payload, ensure_ascii=False)


# ----------------------------------------------------------------------
# A6 全合法 / A13 空表
# ----------------------------------------------------------------------
def test_a6_all_valid_no_errors(monkeypatch):
    data = _preview_data('cases.json', _json_bytes([GOOD, dict(GOOD, name='另一个')]), monkeypatch)
    assert data['errors'] == []
    assert data['totalRows'] == 2


@pytest.mark.parametrize('filename,payload', [
    ('empty.json', _json_bytes([])),
    ('empty.csv', _csv_bytes([])),
    ('empty.xlsx', _excel_new_bytes([])),
    ('empty_legacy.xlsx', _excel_legacy_bytes([])),
])
def test_a13_empty_table(filename, payload, monkeypatch):
    data = _preview_data(filename, payload, monkeypatch)
    assert data['totalRows'] == 0
    assert data['errors'] == []


# ----------------------------------------------------------------------
# A7 与导入回执同口径（行号 + 文案逐条一致）
# ----------------------------------------------------------------------
def test_a7_preview_matches_import_receipt(monkeypatch):
    csv_bytes = _csv_bytes([
        ('接线测试_INT2157_ok', 'd'),
        ('', 'y'),
        ('接线测试_INT2157_ok2', 'd'),
        ('', 'z'),
    ])
    preview = _preview_data('cases.csv', csv_bytes, monkeypatch)

    # 导入侧：同一解析函数产出同一批行，只把落库动作替换为空实现
    rows = TestCaseImportService._parse_csv_rows(io.BytesIO(csv_bytes))
    monkeypatch.setattr(TestCaseImportService, '_resolve_or_create_group',
                        staticmethod(lambda case_data: None))
    monkeypatch.setattr(TestCaseImportService, '_find_existing_case',
                        staticmethod(lambda case_data, group=None: (None, None)))
    monkeypatch.setattr(TestCaseImportService, '_build_case_payload',
                        staticmethod(lambda case_data, group: {}))
    monkeypatch.setattr(TestCaseImportService, '_persist_case',
                        staticmethod(lambda payload, existing, strategy, group: 1))
    monkeypatch.setattr(TestCaseImportService, '_restore_reference_params',
                        staticmethod(lambda case_id, case_data, errors, idx: None))
    _, _, _, _, import_errors = TestCaseImportService._create_cases_from_rows(rows)

    assert preview['errors'] == import_errors
    # 表头不计行号，第 1 条数据行即「第1行」起
    assert preview['errors'] == ['第2行: 用例名称不能为空', '第4行: 用例名称不能为空']


# ----------------------------------------------------------------------
# A8 一行多非法 → 只 1 条
# ----------------------------------------------------------------------
def test_a8_one_error_per_bad_row(monkeypatch):
    bad = {'name': '', 'group': 123, 'group_id': {'weird': True}, 'id': []}
    data = _preview_data('cases.json', _json_bytes([GOOD, bad]), monkeypatch)
    assert data['errors'] == ['第2行: 用例名称不能为空']


# ----------------------------------------------------------------------
# A9 600 行、第 520 行坏 → 不被 500 行重复扫描上限截断
# ----------------------------------------------------------------------
def test_a9_no_scan_truncation(monkeypatch):
    cases = [dict(GOOD, name='接线测试_INT2157_%d' % i) for i in range(1, 601)]
    cases[519]['name'] = ''
    data = _preview_data('big.json', _json_bytes(cases), monkeypatch)
    assert data['totalRows'] == 600
    assert data['errors'] == ['第520行: 用例名称不能为空']
    assert 'errorsScanTruncated' not in data
    assert 'errorsTruncated' not in data
    assert 'truncatedFields' not in data


# ----------------------------------------------------------------------
# A11 重复检测语义不动
# ----------------------------------------------------------------------
def test_a11_duplicates_semantics_unchanged(monkeypatch):
    def find_existing(case_data, group=None):
        if case_data.get('name') == 'dup':
            return {'id': 9, 'name': 'dup'}, 'name'
        return None, None

    cases = [dict(GOOD, name='dup'), dict(GOOD, name='fresh')]
    data = _preview_data('cases.json', _json_bytes(cases), monkeypatch, find_existing)
    assert data['duplicateCount'] == 1
    assert [d['row'] for d in data['duplicates']] == [1]
    assert data['duplicateScanTruncated'] is False
    # 错误口径与重复口径相互独立
    assert data['errors'] == []


def test_a11_duplicate_scan_truncated_over_limit(monkeypatch):
    cases = [dict(GOOD, name='接线测试_INT2157_%d' % i) for i in range(1, 601)]
    data = _preview_data('big.json', _json_bytes(cases), monkeypatch)
    assert data['duplicateCount'] == 0
    assert data['duplicateScanTruncated'] is True


# ----------------------------------------------------------------------
# A12 裸数组 JSON 仍 400，不新增支持
# ----------------------------------------------------------------------
def test_a12_bare_array_json_still_400(monkeypatch):
    payload, code = _preview(
        'bare.json', json.dumps([GOOD]).encode('utf-8'), monkeypatch)
    assert code == 400
    assert payload['message'] == "预览失败: 'list' object has no attribute 'get'"
