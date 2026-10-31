# -*- coding: utf-8 -*-
"""INT-2214：用例 ZIP 导出 include_audios（音频附件进包 + manifest 清单/缺失计数）。

验收口径（INT-2205 审计定稿）：
1. include_audios=true → 包内 `audios/{audio_id}.{ext}`，manifest.audio_file_count
   与实际文件数一致；同一音频被多个用例引用只打 1 份；md5 与包内文件一致；
2. 不传 / false → 包内无 `audios/`，manifest 的 audios/missing 为空、计数为 0；
3. 引用库内不存在的 id / 二进制读不到 → 200 + missing 计数，不 500、不静默跳过；
3b. audio_service ACL 不可用 → 5xx（503），不产出半包；
5. 扩展名 format 优先、回落 file_path 后缀；
6. 噪声音频（含干扰人与各级 backgroundNoise）同样入包。

全部用例在宿主树直跑服务层（不经容器镜像），gRPC / 存储用替身隔离。
"""
import hashlib
import io
import json
import os
import zipfile

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.application.services.testcase import testcase_export_service as module
from api_gateway.application.services.testcase.testcase_export_service import (
    TestCaseExportService,
)
from api_gateway.domain.dto import CommandResultDTO
from api_gateway.schemas.testcase import TestCaseExportRequest as _ExportRequest
from shared.utils.testcase_helpers import (
    collect_case_audio_ids,
    collect_case_audio_references,
)

AUDIO_STORAGE = 'shared.infrastructure.storage'


def _case(case_id, config):
    return {'id': case_id, 'config': config}


def _fake_audio_lookup(monkeypatch, records, raises=False, success=True, data=None):
    """替换 ACL get_by_ids，返回只命中请求 ids 的记录；记下调用入参。"""
    calls = []

    def _get_by_ids(payload):
        calls.append(payload)
        if raises:
            raise RuntimeError('audio gRPC down')
        if not success:
            return CommandResultDTO(success=False, message='查询失败', data=None)
        if data is not None:
            return CommandResultDTO(success=True, data=data)
        wanted = set((payload or {}).get('ids') or [])
        return CommandResultDTO(
            success=True, data=[r for r in records if r['id'] in wanted])

    monkeypatch.setattr(module._audio_acl, 'get_by_ids', _get_by_ids)
    return calls


def _fake_storage(monkeypatch, files, raising_paths=()):
    """替换 storage_load_bytes：files 为 {file_path: bytes}，raise 列表模拟读失败。"""
    import shared.infrastructure.storage as storage_mod

    def _load(path):
        if path in raising_paths:
            raise RuntimeError(f'storage down: {path}')
        return files[path]

    monkeypatch.setattr(storage_mod, 'storage_load_bytes', _load)


def _read_zip(response):
    zf = zipfile.ZipFile(io.BytesIO(response.body))
    manifest = json.loads(zf.read('manifest.json'))
    return zf, manifest


# ----------------------------------------------------------------------
# 1. 全口径收集（direct + interferers + 各级背景噪音）
# ----------------------------------------------------------------------
def test_collect_case_audio_references_full_scope():
    config = {
        'background_noise': {'audio_id': 91},
        'rounds': [
            {
                'round_number': 1,
                'audios': [
                    {'audio_id': 11, 'interferers': [{'audio_id': 21}, {'audio_id': '22'}]},
                    {'audio_id': 12, 'background_noise': {'audio_id': 31}},
                ],
                'backgroundNoise': {'audio_id': 41},
            },
            {'round_number': 2, 'audios': [{'audio_id': 11}]},
        ],
    }
    direct, noise = collect_case_audio_references(config)
    assert direct == [11, 21, 22, 12], '播放音频 + 干扰人（含字符串 id）'
    assert noise == [91, 41, 31], '顶层 / 轮次级 camelCase / segment 级噪音'
    assert collect_case_audio_ids(config) == [11, 21, 22, 12, 91, 41, 31]


def test_collect_case_audio_ids_flat_config():
    assert collect_case_audio_ids(
        {'audios': [{'audio_id': 7}, {'audio_id': None}, {'audio_id': 'x'}]}) == [7]


def test_export_request_defaults_to_without_audios():
    req = _ExportRequest.model_validate({'ids': ['1'], 'format': 'zip'})
    assert req.include_audios is False, '老客户端不传该字段 → 默认不打包音频'
    assert _ExportRequest.model_validate(
        {'ids': ['1'], 'include_audios': True}).include_audios is True


# ----------------------------------------------------------------------
# 2. 音频进包 + manifest 清单 + 去重 + md5/size
# ----------------------------------------------------------------------
def _records():
    return [
        {'id': 11, 'name': '播放音频', 'file_path': 'oss://b/play.wav', 'format': 'wav'},
        {'id': 12, 'name': '干扰人', 'file_path': 'oss://b/interf.mp3', 'format': None},
        {'id': 13, 'name': None, 'file_path': 'oss://b/noise.wav', 'format': 'FLAC'},
    ]


def _files():
    return {
        'oss://b/play.wav': b'AAAA',
        'oss://b/interf.mp3': b'BBBBB',
        'oss://b/noise.wav': b'CCCCCC',
    }


def _export_data_with_audio():
    return [
        _case('c1', {'rounds': [{'round_number': 1, 'audios': [{'audio_id': 11}]}]}),
        _case('c2', {'rounds': [{'round_number': 1, 'audios': [
            {'audio_id': 11},
            {'audio_id': 12, 'interferers': [{'audio_id': 13}]},
        ]}]}),
    ]


def test_zip_includes_audios_and_manifest(monkeypatch):
    calls = _fake_audio_lookup(monkeypatch, _records())
    _fake_storage(monkeypatch, _files())

    response = TestCaseExportService._generate_zip_export(
        _export_data_with_audio(), include_reference_params=False, include_audios=True)
    zf, manifest = _read_zip(response)

    names = zf.namelist()
    assert 'audios/11.wav' in names
    assert 'audios/12.mp3' in names, 'format 缺失 → 回落 file_path 后缀'
    assert 'audios/13.flac' in names, 'format 优先于 file_path 后缀'
    assert sorted(n for n in names if n.startswith('audios/')) == [
        'audios/11.wav', 'audios/12.mp3', 'audios/13.flac'
    ]
    # 同一 audio_id 被 2 条用例引用 → 包内只 1 份
    assert names.count('audios/11.wav') == 1
    assert manifest['audio_file_count'] == 3
    assert manifest['missing_audio_count'] == 0
    assert manifest['missing_audio_ids'] == []
    assert manifest['version'] == '1.1'
    assert manifest['options']['include_audios'] is True

    by_id = {a['id']: a for a in manifest['audios']}
    assert set(by_id) == {11, 12, 13}
    assert by_id[11] == {
        'id': 11,
        'name': '播放音频',
        'file': 'audios/11.wav',
        'md5': hashlib.md5(b'AAAA').hexdigest(),
        'size': 4,
        'format': 'wav',
    }
    assert by_id[13]['name'] == 'noise.wav', 'name 缺失回落文件名'
    for audio_id, record in by_id.items():
        packed = zf.read(record['file'])
        assert hashlib.md5(packed).hexdigest() == record['md5']
        assert len(packed) == record['size']
    # 去重后只向 audio_service 查一次
    assert len(calls) == 1
    assert calls[0]['ids'] == [11, 12, 13]


# ----------------------------------------------------------------------
# 3. 不打包音频时包内文件条目与现状一致
# ----------------------------------------------------------------------
def test_zip_without_audios_keeps_entries_clean(monkeypatch):
    calls = _fake_audio_lookup(monkeypatch, _records())
    _fake_storage(monkeypatch, _files())

    response = TestCaseExportService._generate_zip_export(
        _export_data_with_audio(), include_reference_params=False)
    zf, manifest = _read_zip(response)

    assert not [n for n in zf.namelist() if n.startswith('audios/')]
    assert sorted(zf.namelist()) == ['manifest.json', 'testcases.json']
    assert manifest['options']['include_audios'] is False
    assert manifest['audio_file_count'] == 0
    assert manifest['missing_audio_count'] == 0
    assert manifest['audios'] == []
    assert manifest['missing_audio_ids'] == []
    assert calls == [], '不勾选音频时不查 audio_service'


# ----------------------------------------------------------------------
# 4. 缺失分类：库里不存在 / 二进制读不到 → 200 + missing
# ----------------------------------------------------------------------
def test_missing_and_unreadable_audios_are_counted(monkeypatch):
    # 11 在库但存储读失败；12 在库中不存在
    _fake_audio_lookup(monkeypatch, [r for r in _records() if r['id'] == 11])
    _fake_storage(monkeypatch, _files(), raising_paths=('oss://b/play.wav',))

    export_data = [
        _case('c1', {'rounds': [{'audios': [{'audio_id': 11}, {'audio_id': 12}]}]}),
    ]
    response = TestCaseExportService._generate_zip_export(
        export_data, include_reference_params=False, include_audios=True)

    # 200 Response（不是 error tuple），且不静默跳过
    assert not isinstance(response, tuple)
    zf, manifest = _read_zip(response)
    assert manifest['audio_file_count'] == 0
    assert manifest['missing_audio_count'] == 2
    assert manifest['missing_audio_ids'] == [11, 12]
    assert manifest['audios'] == []
    assert not [n for n in zf.namelist() if n.startswith('audios/')]


# ----------------------------------------------------------------------
# 3b. audio_service 不可用 → 5xx，不产出半包
# ----------------------------------------------------------------------
def test_audio_service_failure_returns_5xx(monkeypatch):
    _fake_audio_lookup(monkeypatch, _records(), raises=True)
    _fake_storage(monkeypatch, _files())

    result = TestCaseExportService._generate_zip_export(
        _export_data_with_audio(), include_reference_params=False, include_audios=True)
    assert isinstance(result, tuple), '依赖不可用不得返回 ZIP 半包'
    payload, http_code = result
    assert http_code == 503
    assert payload['code'] == 306  # ErrorCode.EXTERNAL_SERVICE_ERROR
    assert '音频服务不可用' in payload['message']


def test_audio_service_unsuccessful_envelope_returns_5xx(monkeypatch):
    _fake_audio_lookup(monkeypatch, _records(), success=False)
    result = TestCaseExportService._generate_zip_export(
        _export_data_with_audio(), include_audios=True)
    assert isinstance(result, tuple)
    assert result[1] == 503


def test_audio_service_non_list_payload_returns_5xx(monkeypatch):
    _fake_audio_lookup(monkeypatch, _records(), data={'unexpected': True})
    result = TestCaseExportService._generate_zip_export(
        _export_data_with_audio(), include_audios=True)
    assert isinstance(result, tuple)
    assert result[1] == 503


# ----------------------------------------------------------------------
# 5. 扩展名解析
# ----------------------------------------------------------------------
def test_resolve_audio_extension_prefers_format_then_path():
    resolve = TestCaseExportService._resolve_audio_extension
    assert resolve({'format': 'wav', 'file_path': 'a/b.mp3'}) == 'wav'
    assert resolve({'format': '.WAV', 'file_path': 'a/b.mp3'}) == 'wav'
    assert resolve({'format': None, 'file_path': 'oss://bucket/x.MP3'}) == 'mp3'
    assert resolve({'format': '', 'file_path': 'oss://bucket/noext'}) == 'bin'
    assert resolve({'format': 'bad/format', 'file_path': 'oss://bucket/y.wav'}) == 'wav'


# ----------------------------------------------------------------------
# 6. 噪声音频入包（含干扰人）
# ----------------------------------------------------------------------
def test_noise_audio_referenced_in_rounds_is_packaged(monkeypatch):
    records = [
        {'id': 51, 'name': 'top-noise', 'file_path': 'oss://b/top.wav', 'format': 'wav'},
        {'id': 52, 'name': 'round-noise', 'file_path': 'oss://b/round.wav', 'format': 'wav'},
        {'id': 53, 'name': 'segment-noise', 'file_path': 'oss://b/seg.wav', 'format': 'wav'},
        {'id': 54, 'name': 'interferer', 'file_path': 'oss://b/inf.wav', 'format': 'wav'},
    ]
    files = {r['file_path']: b'x' * (i + 1) for i, r in enumerate(records)}
    _fake_audio_lookup(monkeypatch, records)
    _fake_storage(monkeypatch, files)

    config = {
        'background_noise': {'audio_id': 51},
        'rounds': [
            {
                'backgroundNoise': {'audio_id': 52},
                'audios': [
                    {'audio_id': 99,
                     'interferers': [{'audio_id': 54}],
                     'background_noise': {'audio_id': 53}},
                ],
            }
        ],
    }
    # 99 是播放音频但库中不存在 → 只计入 missing，不阻断噪音入包
    response = TestCaseExportService._generate_zip_export(
        [_case('c1', config)], include_reference_params=False, include_audios=True)
    zf, manifest = _read_zip(response)

    assert manifest['audio_file_count'] == 4
    assert {a['id'] for a in manifest['audios']} == {51, 52, 53, 54}
    assert manifest['missing_audio_ids'] == [99]
    assert 'audios/51.wav' in zf.namelist()
    assert 'audios/52.wav' in zf.namelist()
    assert 'audios/53.wav' in zf.namelist()
    assert 'audios/54.wav' in zf.namelist()
