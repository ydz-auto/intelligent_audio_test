# -*- coding: utf-8 -*-
"""INT-2182：ZIP/JSON 导入引用音频校验（不存在的 audio_id 不得静默落库）。

约束（卡 INT-2182，口径按规划师派单）：
- 预览与导入共用 `_validate_imported_case` 的同一层引用校验；
- 引用的 `audio_id` 不存在 → 行级 error：`第{N}行: 音频 {id} 不存在`，该行不落库；
- 一行多处缺失只出 1 条（与「每个坏行只 1 条」的既有 errors 契约一致）；
- 音频服务查询失败时 fail-open（不阻断整包导入），不误报。

全部用例在宿主树直跑服务层（不经容器镜像），gRPC 用替身隔离。
"""
import io
import json
import os

# 服务模块导入即实例化 BaseConfig（类属性冻结），单跑本文件时需先伪造凭据
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.application.services.testcase import testcase_import_service as module
from api_gateway.application.services.testcase.testcase_import_service import (
    TestCaseImportService,
)


class _FakeRequest:
    def __init__(self, files):
        self.state = type('_State', (), {'_files': files})()


class _FakeUpload:
    def __init__(self, filename, data):
        self.filename = filename
        self.file = io.BytesIO(data)


def _audio_lookup(monkeypatch, existing_ids=(), success=True, raises=False):
    """替换 AudioAclRepositoryImpl.get_by_ids，记下调用入参。"""
    calls = []

    def _get_by_ids(data):
        calls.append(data)
        if raises:
            raise RuntimeError('audio gRPC down')
        if not success:
            return {'success': False, 'message': '查询失败', 'data': None}
        return {
            'success': True,
            'data': [{'id': audio_id} for audio_id in (data or {}).get('ids', [])
                     if audio_id in existing_ids],
        }

    monkeypatch.setattr(module._audio_acl, 'get_by_ids', _get_by_ids)
    return calls


def _json_bytes(cases):
    return json.dumps({'test_cases': cases}, ensure_ascii=False).encode('utf-8')


def _rounds_case(audio_ids, name='接线测试_INT2182_引用音频'):
    return {
        'name': name,
        'group': '接线测试_INT2182组',
        'config': {
            'rounds': [
                {'round_number': 1, 'audios': [
                    {'audio_id': audio_id, 'spl': 60, 'play_order': i + 1}
                ], 'dimensions': []}
                for i, audio_id in enumerate(audio_ids)
            ],
            'dimensions': [],
        },
    }


def _preview(monkeypatch, filename, data):
    monkeypatch.setattr(
        TestCaseImportService, '_lookup_group', staticmethod(lambda case_data: None))
    monkeypatch.setattr(
        TestCaseImportService, '_find_existing_case',
        staticmethod(lambda case_data, group=None: (None, None)))
    monkeypatch.setattr(
        TestCaseImportService, '_resolve_or_create_group',
        staticmethod(lambda case_data: None))
    from api_gateway.infrastructure.request_adapter import set_current_request
    set_current_request(_FakeRequest({'file': _FakeUpload(filename, data)}))
    try:
        payload, code = TestCaseImportService.preview_import()
    finally:
        set_current_request(None)
    assert code == 200, payload
    return payload['data']


def test_preview_json_reports_missing_audio(monkeypatch):
    _audio_lookup(monkeypatch, existing_ids=())
    data = _preview(monkeypatch, 'ref_missing.json', _json_bytes([_rounds_case([999999])]))
    assert data['totalRows'] == 1
    assert data['errors'] == ['第1行: 音频 999999 不存在']


def test_preview_zip_reports_missing_audio(monkeypatch):
    import zipfile
    _audio_lookup(monkeypatch, existing_ids=())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('testcases.json', json.dumps(
            {'test_cases': [_rounds_case([999999])]}, ensure_ascii=False))
    data = _preview(monkeypatch, 'ref_missing.zip', buf.getvalue())
    assert data['errors'] == ['第1行: 音频 999999 不存在']


def test_preview_existing_audio_no_error(monkeypatch):
    _audio_lookup(monkeypatch, existing_ids=(42,))
    data = _preview(monkeypatch, 'ok.json', _json_bytes([_rounds_case([42])]))
    assert data['errors'] == []


def test_preview_one_error_per_row_multiple_missing(monkeypatch):
    _audio_lookup(monkeypatch, existing_ids=())
    case = _rounds_case([999999, 888888])
    # 同一 id 跨轮重复只报一次，多个缺失 id 合并进同一条
    case['config']['rounds'].append(
        {'round_number': 3, 'audios': [{'audio_id': 999999}], 'dimensions': []})
    data = _preview(monkeypatch, 'multi.json', _json_bytes([case]))
    assert data['errors'] == ['第1行: 音频 999999、888888 不存在']


def test_import_missing_audio_row_not_persisted(monkeypatch):
    _audio_lookup(monkeypatch, existing_ids=(42,))
    persisted = []

    rows = [_rounds_case([999999]), _rounds_case([42], name='接线测试_INT2182_合法')]
    monkeypatch.setattr(
        TestCaseImportService, '_resolve_or_create_group',
        staticmethod(lambda case_data: {'id': 7}))
    monkeypatch.setattr(
        TestCaseImportService, '_find_existing_case',
        staticmethod(lambda case_data, group=None: (None, None)))
    monkeypatch.setattr(
        TestCaseImportService, '_build_case_payload',
        staticmethod(lambda case_data, group: {'name': case_data['name']}))
    monkeypatch.setattr(
        TestCaseImportService, '_persist_case',
        staticmethod(lambda payload, existing, strategy, group: persisted.append(payload) or 1))
    monkeypatch.setattr(
        TestCaseImportService, '_restore_reference_params',
        staticmethod(lambda case_id, case_data, errors, idx: None))

    imported, _, _, _, errors = TestCaseImportService._create_cases_from_rows(rows)
    assert errors == ['第1行: 音频 999999 不存在']
    assert imported == 1
    assert [p['name'] for p in persisted] == ['接线测试_INT2182_合法']


def test_audio_lookup_failure_is_fail_open(monkeypatch):
    _audio_lookup(monkeypatch, success=False)
    data = _preview(monkeypatch, 'ref.json', _json_bytes([_rounds_case([999999])]))
    assert data['errors'] == []


def test_audio_lookup_exception_is_fail_open(monkeypatch):
    _audio_lookup(monkeypatch, raises=True)
    data = _preview(monkeypatch, 'ref.json', _json_bytes([_rounds_case([999999])]))
    assert data['errors'] == []


def test_no_audio_reference_skips_lookup(monkeypatch):
    calls = _audio_lookup(monkeypatch, existing_ids=())
    data = _preview(monkeypatch, 'plain.json',
                    _json_bytes([{'name': '接线测试_INT2182_无音频', 'group': 'g'}]))
    assert data['errors'] == []
    assert calls == []


def test_flat_excel_audio_id_missing_is_reported(monkeypatch):
    """CSV/Excel 扁平格式：AUDIO_ID 列指向不存在的音频同样报错。"""
    import pandas as pd
    _audio_lookup(monkeypatch, existing_ids=())
    testcases = pd.DataFrame([{'ID': '', 'NAME': '接线测试_INT2182_扁平', 'DESCRIPTION': ''}])
    audio_configs = pd.DataFrame([{
        'CASE_ID': '', 'CASE_NAME': '接线测试_INT2182_扁平', 'AUDIO_ID': 999999,
        'AUDIO_NAME': '', 'SPL': 60, 'PLAYBACK_DEVICE_ID': None,
        'PLAYBACK_DEVICE_NAME': None, 'PLAY_ORDER': 1,
    }])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        testcases.to_excel(writer, sheet_name='TestCases', index=False)
        audio_configs.to_excel(writer, sheet_name='AudioConfigs', index=False)
    data = _preview(monkeypatch, 'flat.xlsx', buf.getvalue())
    assert data['errors'] == ['第1行: 音频 999999 不存在']
