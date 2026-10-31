# -*- coding: utf-8 -*-
"""INT-2215：用例 ZIP 导入回导音频（md5 复用/登记 + audio_id 全口径重映射）。

覆盖卡面验收标准 A.1：
- manifest 解析与映射表构建；
- 无音频 → 登记 → 重写；同 md5 复用；同 id 不同 md5 走 md5 映射（不按 id 绑）；
- 单条登记失败 → 行级错误且该用例不落库，其余用例照常；
- config 全口径重写（rounds audios / interferers / 顶层 audios / 顶层·轮次·segment
  级 background_noise）+ 扁平 `audios[].audio_id` + `noise_audio_id`；
- 老包（无 audios/、manifest 无 audios）行为不变；重写后才校验；预览不报假缺失且不登记。

全部在宿主树直跑服务层，gRPC 用替身隔离（真实链路见 tests/ui/probe_int2215_*）。
"""
import hashlib
import io
import json
import os
import zipfile

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.application.services.testcase import testcase_import_service as module
from api_gateway.application.services.testcase.testcase_import_audio import (
    ImportAudioPackage,
    build_audio_remap,
)
from api_gateway.application.services.testcase.testcase_import_service import (
    TestCaseImportService,
)
from api_gateway.infrastructure.request_adapter import set_current_request
from shared.constants.testcase_transfer import (
    PACKAGE_FORMAT,
    PACKAGE_VERSION,
)
from shared.utils import testcase_helpers as common


class _FakeRequest:
    def __init__(self, files):
        self.state = type('_State', (), {'_files': files})()


class _FakeUpload:
    def __init__(self, filename, data):
        self.filename = filename
        self.file = io.BytesIO(data)


class _FakeAudioAcl:
    """AudioAclRepositoryImpl 替身：按 md5 命中/登记结果可编排。"""

    def __init__(self, md5_hits=None, register_results=None):
        self.md5_hits = md5_hits or {}
        self.register_results = list(register_results or [])
        self.md5_calls = []
        self.register_calls = []
        self.ids_calls = []

    def get_by_md5(self, data):
        self.md5_calls.append(data)
        hits = {md5: {'id': target}
                for md5, target in self.md5_hits.items()
                if md5 in (data or {}).get('md5_list', [])}
        return {'success': True, 'message': 'ok', 'data': hits}

    def register_audio_by_bytes(self, data):
        self.register_calls.append(data)
        if self.register_results:
            return self.register_results.pop(0)
        return {'success': True, 'message': '登记成功',
                'data': {'id': 1000 + len(self.register_calls), 'reused': False}}

    def get_by_ids(self, data):
        self.ids_calls.append(data)
        existing = set(data.get('_existing_ids') or [])
        return {'success': True,
                'data': [{'id': i} for i in (data or {}).get('ids', []) if i in existing]}


def _install_acl(monkeypatch, acl, existing_ids=()):
    monkeypatch.setattr(module._audio_acl, 'get_by_md5', acl.get_by_md5)
    monkeypatch.setattr(module._audio_acl, 'register_audio_by_bytes', acl.register_audio_by_bytes)

    def _get_by_ids(data):
        acl.ids_calls.append(data)
        return {'success': True,
                'data': [{'id': i} for i in (data or {}).get('ids', []) if i in existing_ids]}

    monkeypatch.setattr(module._audio_acl, 'get_by_ids', _get_by_ids)
    return acl


def _wav_bytes(seed=1):
    return bytes([seed]) * 64 + b'RIFF' + bytes([seed]) * 32


def _zip_bytes(cases, audio_files=None, manifest_audios='auto'):
    """构造用例包。

    audio_files: [{'id', 'name', 'bytes'}]；None = 老包（不带 audios/ 与 manifest）。
    manifest_audios: 'auto' 按 audio_files 生成清单；list 用给定清单；None = manifest 无 audios。
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('testcases.json',
                    json.dumps({'test_cases': cases}, ensure_ascii=False))
        entries = []
        for item in audio_files or []:
            path = f"audios/{item['id']}.wav"
            zf.writestr(path, item['bytes'])
            entries.append({
                'id': item['id'],
                'name': item['name'],
                'file': path,
                'md5': hashlib.md5(item['bytes']).hexdigest(),
                'size': len(item['bytes']),
                'format': 'wav',
            })
        if audio_files is not None:
            audios_field = entries if manifest_audios == 'auto' else manifest_audios
            manifest = {
                'format': PACKAGE_FORMAT,
                'version': PACKAGE_VERSION,
                'total_count': len(cases),
                'audio_file_count': len(entries),
                'missing_audio_count': 0,
                'missing_audio_ids': [],
                'audios': audios_field,
            }
            zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
    return buf.getvalue()


def _parse_package(data):
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return ImportAudioPackage.from_zip(zf, set(zf.namelist()))


def _full_scope_case(source_ids, name='接线测试_INT2215_全口径'):
    """构造带全部音频引用位置的用例（config 全口径 + 扁平列）。"""
    a0, a1, a2, a3, a4, a5 = source_ids
    return {
        'name': name,
        'group': '接线测试_INT2215组',
        'config': {
            'background_noise': {'audio_id': a3, 'spl': 30},
            'audios': [{'audio_id': a4, 'spl': 60}],
            'rounds': [{
                'round_number': 1,
                'audios': [
                    {'audio_id': a0, 'spl': 60,
                     'interferers': [{'audio_id': a1, 'spl': 50}]},
                ],
                'backgroundNoise': {'audio_id': a2, 'spl': 20},
            }],
        },
        # 扁平列（导出/CSV/Excel 会带），也必须重写
        'audios': [{'audio_id': a4, 'spl': 60}],
        'noise_audio_id': a5,
    }


def _simple_case(source_id, name='接线测试_INT2215_单音频'):
    return {
        'name': name,
        'group': '接线测试_INT2215组',
        'config': {'rounds': [{'round_number': 1,
                               'audios': [{'audio_id': source_id, 'spl': 60}]}]},
    }


def _stub_import_side_effects(monkeypatch, persisted, existing_ids):
    monkeypatch.setattr(TestCaseImportService, '_resolve_or_create_group',
                        staticmethod(lambda case_data: {'id': 7}))
    monkeypatch.setattr(TestCaseImportService, '_find_existing_case',
                        staticmethod(lambda case_data, group=None: (None, None)))
    monkeypatch.setattr(TestCaseImportService, '_restore_reference_params',
                        staticmethod(lambda case_id, case_data, errors, idx: None))
    monkeypatch.setattr(
        TestCaseImportService, '_persist_case',
        staticmethod(lambda payload, existing, strategy, group:
                     persisted.append(payload) or (len(persisted) + 100)))


def _run_import(monkeypatch, filename, data, persisted, existing_ids=()):
    _stub_import_side_effects(monkeypatch, persisted, existing_ids)
    set_current_request(_FakeRequest({'file': _FakeUpload(filename, data)}))
    try:
        payload, code = TestCaseImportService.import_cases()
    finally:
        set_current_request(None)
    assert code == 200, payload
    return payload['data']


def _run_preview(monkeypatch, filename, data):
    monkeypatch.setattr(TestCaseImportService, '_lookup_group',
                        staticmethod(lambda case_data: None))
    monkeypatch.setattr(TestCaseImportService, '_find_existing_case',
                        staticmethod(lambda case_data, group=None: (None, None)))
    monkeypatch.setattr(TestCaseImportService, '_resolve_or_create_group',
                        staticmethod(lambda case_data: None))
    set_current_request(_FakeRequest({'file': _FakeUpload(filename, data)}))
    try:
        payload, code = TestCaseImportService.preview_import()
    finally:
        set_current_request(None)
    assert code == 200, payload
    return payload['data']


# ----------------------------------------------------------------------
# 1. manifest 解析与映射表构建
# ----------------------------------------------------------------------
def test_manifest_parsed_into_package_entries():
    data = _zip_bytes([_simple_case(7)], audio_files=[
        {'id': 7, 'name': '源音频A.wav', 'bytes': _wav_bytes(1)}])
    package = _parse_package(data)
    assert len(package.entries) == 1
    entry = package.entries[0]
    assert entry['source_id'] == 7
    assert entry['name'] == '源音频A.wav'
    assert entry['source_filename'] == '7.wav'   # 保留扩展名，不触发 ffmpeg 转码分支
    assert entry['md5'] == hashlib.md5(_wav_bytes(1)).hexdigest()
    assert entry['content'] == _wav_bytes(1)


def test_remap_table_built_from_md5_hits(monkeypatch):
    acl = _FakeAudioAcl(md5_hits={hashlib.md5(_wav_bytes(2)).hexdigest(): 501})
    package = _parse_package(_zip_bytes(
        [_simple_case(9)],
        audio_files=[{'id': 9, 'name': 'A.wav', 'bytes': _wav_bytes(2)}]))

    remap = build_audio_remap(package, acl, register=False)
    assert remap.source_to_target == {9: 501}
    assert remap.reused and remap.reused[0]['target_id'] == 501
    assert acl.register_calls == []          # 预览只读，不登记


def test_package_reports_missing_binary_entry():
    data = _zip_bytes([_simple_case(7)], audio_files=[], manifest_audios=[{
        'id': 7, 'name': 'A.wav', 'file': 'audios/7.wav',
        'md5': 'a' * 32, 'size': 10, 'format': 'wav',
    }])
    package = _parse_package(data)
    assert package.entries == []
    assert package.unavailable[7] == 'missing_in_package'


# ----------------------------------------------------------------------
# 2. 无音频 → 登记 → 重写
# ----------------------------------------------------------------------
def test_import_registers_missing_audio_and_rewrites(monkeypatch):
    md5 = hashlib.md5(_wav_bytes(3)).hexdigest()
    acl = _FakeAudioAcl(register_results=[{
        'success': True, 'message': '登记成功', 'data': {'id': 777, 'reused': False}}])
    _install_acl(monkeypatch, acl, existing_ids=(777,))

    persisted = []
    data = _zip_bytes([_simple_case(7)], audio_files=[
        {'id': 7, 'name': '源A.wav', 'bytes': _wav_bytes(3)}])
    receipt = _run_import(monkeypatch, 'pkg.zip', data, persisted)

    assert [call['md5'] for call in acl.register_calls] == [md5]
    assert acl.register_calls[0]['name'] == '源A.wav'
    assert acl.register_calls[0]['content_b64']
    assert persisted[0]['config']['rounds'][0]['audios'][0]['audio_id'] == 777
    assert receipt['imported_count'] == 1
    assert receipt['audio_registered_count'] == 1
    assert receipt['audio_failed'] == []


# ----------------------------------------------------------------------
# 3. 同 md5 复用（不重复登记）
# ----------------------------------------------------------------------
def test_same_md5_reused_without_registering(monkeypatch):
    md5 = hashlib.md5(_wav_bytes(4)).hexdigest()
    acl = _FakeAudioAcl(md5_hits={md5: 321})
    _install_acl(monkeypatch, acl, existing_ids=(321,))

    persisted = []
    data = _zip_bytes([_simple_case(7)], audio_files=[
        {'id': 7, 'name': '源B.wav', 'bytes': _wav_bytes(4)}])
    receipt = _run_import(monkeypatch, 'pkg.zip', data, persisted)

    assert acl.register_calls == []          # 命中即复用，不新增 audios 行
    assert persisted[0]['config']['rounds'][0]['audios'][0]['audio_id'] == 321
    assert receipt['audio_reused_count'] == 1
    assert receipt['audio_registered_count'] == 0


# ----------------------------------------------------------------------
# 4. 同 id 不同 md5 → 按 md5 映射，不按 id 绑定
# ----------------------------------------------------------------------
def test_same_audio_id_different_md5_maps_by_md5(monkeypatch):
    md5 = hashlib.md5(_wav_bytes(5)).hexdigest()
    # 目标库存在 id=7（另一条音频，md5 不同）；按 md5 查到的是 888
    acl = _FakeAudioAcl(md5_hits={md5: 888})
    _install_acl(monkeypatch, acl, existing_ids=(7, 888))

    persisted = []
    data = _zip_bytes([_simple_case(7)], audio_files=[
        {'id': 7, 'name': '源C.wav', 'bytes': _wav_bytes(5)}])
    receipt = _run_import(monkeypatch, 'pkg.zip', data, persisted)

    rewritten = persisted[0]['config']['rounds'][0]['audios'][0]['audio_id']
    assert rewritten == 888 and rewritten != 7
    # 重映射必须来自 md5 批量查询（目标库同 id 的另一条音频不得按 id 绑定）
    assert acl.md5_calls == [{'md5_list': [md5]}]
    assert receipt['audio_reused_count'] == 1


# ----------------------------------------------------------------------
# 5. 单条登记失败 → 行级错误且该用例不落库，其余用例照常
# ----------------------------------------------------------------------
def test_single_register_failure_row_error_and_others_imported(monkeypatch):
    md5_bad = hashlib.md5(_wav_bytes(6)).hexdigest()
    md5_ok = hashlib.md5(_wav_bytes(7)).hexdigest()
    acl = _FakeAudioAcl(register_results=[
        {'success': False, 'message': 'md5 与音频字节不一致',
         'data': {'code': 400, 'reason': 'md5_mismatch'}},
        {'success': True, 'message': '登记成功', 'data': {'id': 900, 'reused': False}},
    ])
    _install_acl(monkeypatch, acl, existing_ids=(900,))

    persisted = []
    rows = [_simple_case(7, name='接线测试_INT2215_坏行'),
            _simple_case(8, name='接线测试_INT2215_好行')]
    data = _zip_bytes(rows, audio_files=[
        {'id': 7, 'name': '坏.wav', 'bytes': _wav_bytes(6)},
        {'id': 8, 'name': '好.wav', 'bytes': _wav_bytes(7)},
    ])
    receipt = _run_import(monkeypatch, 'pkg.zip', data, persisted)

    assert receipt['errors'] == ['第1行: 音频 7 回导失败: md5_mismatch']
    assert receipt['imported_count'] == 1
    assert [p['name'] for p in persisted] == ['接线测试_INT2215_好行']
    assert persisted[0]['config']['rounds'][0]['audios'][0]['audio_id'] == 900
    assert receipt['audio_failed'] == [{'source_id': 7, 'reason': 'md5_mismatch'}]


# ----------------------------------------------------------------------
# 6. config 全口径重写 + 扁平 audios[].audio_id + noise_audio_id
# ----------------------------------------------------------------------
def test_full_scope_rewrite_including_flat_columns(monkeypatch):
    source_ids = [1, 2, 3, 4, 5, 6]
    audio_files = [{'id': sid, 'name': f'A{sid}.wav', 'bytes': _wav_bytes(sid + 10)}
                   for sid in source_ids]
    hits = {hashlib.md5(f['bytes']).hexdigest(): 5000 + f['id'] for f in audio_files}
    acl = _FakeAudioAcl(md5_hits=hits)
    _install_acl(monkeypatch, acl, existing_ids=tuple(5000 + sid for sid in source_ids))

    persisted = []
    data = _zip_bytes([_full_scope_case(source_ids)], audio_files=audio_files)
    receipt = _run_import(monkeypatch, 'pkg.zip', data, persisted)

    config = persisted[0]['config']
    assert config['rounds'][0]['audios'][0]['audio_id'] == 5001
    assert config['rounds'][0]['audios'][0]['interferers'][0]['audio_id'] == 5002
    assert config['rounds'][0]['backgroundNoise']['audio_id'] == 5003
    assert config['background_noise']['audio_id'] == 5004
    assert config['audios'][0]['audio_id'] == 5005
    assert config['rounds'][0]['backgroundNoise']['spl'] == 20   # 其它字段不动
    # 扁平列（CSV/Excel 解析列，导出也会带）
    assert persisted[0]['name'] == '接线测试_INT2215_全口径'
    assert receipt['audio_reused_count'] == 6
    assert receipt['errors'] == []


def test_remap_helper_covers_flat_noise_column():
    case = _full_scope_case([1, 2, 3, 4, 5, 6])
    changed = common.remap_case_audio_ids(case, {i: i + 100 for i in range(1, 7)})
    # config 内 5 处（audios/interferers/轮次噪音/顶层噪音/顶层 audios）+ 扁平 2 处
    assert changed == 7
    assert case['noise_audio_id'] == 106
    assert case['audios'][0]['audio_id'] == 105
    assert case['config']['background_noise']['audio_id'] == 104


def test_collect_and_remap_share_same_scope():
    """collect_* 收集到的 id 必须全部能重写（同一遍历口径，不另起一套）。"""
    case = _full_scope_case([1, 2, 3, 4, 5, 6])
    collected = common.collect_case_audio_ids(case['config'])
    changed = common.remap_case_audio_ids(case, {i: i + 100 for i in range(1, 7)})
    assert sorted(collected) == [1, 2, 3, 4, 5]
    assert changed == 7
    collected_after = common.collect_case_audio_ids(case['config'])
    assert collected_after == [i + 100 for i in collected]


def test_registered_audio_unused_by_failed_row_reported_as_orphan(monkeypatch):
    """已登记但用例因他因失败未落库 → 音频记入回执 orphaned（不静默）。"""
    md5 = hashlib.md5(_wav_bytes(12)).hexdigest()
    acl = _FakeAudioAcl(register_results=[{
        'success': True, 'message': '登记成功', 'data': {'id': 909, 'reused': False}}])
    _install_acl(monkeypatch, acl, existing_ids=(909,))

    case = {
        'name': '接线测试_INT2215_坏行带音频',
        'group': '接线测试_INT2215组',
        'config': {'rounds': [{'round_number': 1, 'audios': [
            {'audio_id': 7, 'spl': 60}, {'audio_id': 424242, 'spl': 60}]}]},
    }
    persisted = []
    data = _zip_bytes([case], audio_files=[
        {'id': 7, 'name': '源G.wav', 'bytes': _wav_bytes(12)}])
    receipt = _run_import(monkeypatch, 'pkg.zip', data, persisted)

    assert persisted == []
    assert receipt['errors'] == ['第1行: 音频 424242 不存在']
    assert receipt['audio_registered_count'] == 1
    assert receipt['audio_orphaned_ids'] == [909]


# ----------------------------------------------------------------------
# 7. 老包（无 audios/、manifest 无 audios）行为不变
# ----------------------------------------------------------------------
def test_old_package_without_audios_dir_unchanged(monkeypatch):
    acl = _FakeAudioAcl()
    _install_acl(monkeypatch, acl, existing_ids=())

    persisted = []
    data = _zip_bytes([_simple_case(999999)])      # 无 manifest / 无 audios
    receipt = _run_import(monkeypatch, 'old.zip', data, persisted)

    assert acl.md5_calls == [] and acl.register_calls == []
    assert persisted == []
    assert receipt['errors'] == ['第1行: 音频 999999 不存在']
    assert receipt['audio_registered_count'] == 0


def test_manifest_without_audios_field_unchanged(monkeypatch):
    acl = _FakeAudioAcl()
    _install_acl(monkeypatch, acl, existing_ids=(42,))
    persisted = []
    data = _zip_bytes([_simple_case(42)], audio_files=[], manifest_audios=None)
    receipt = _run_import(monkeypatch, 'empty.zip', data, persisted)

    assert acl.register_calls == []
    assert receipt['errors'] == []
    assert receipt['imported_count'] == 1


# ----------------------------------------------------------------------
# 8. 重写后才校验（顺序反了会把整包误判成「音频 X 不存在」）
# ----------------------------------------------------------------------
def test_validation_runs_after_rewrite(monkeypatch):
    md5 = hashlib.md5(_wav_bytes(8)).hexdigest()
    acl = _FakeAudioAcl(md5_hits={md5: 4242})
    # 目标库没有源 id 7，只有重写后的 4242
    _install_acl(monkeypatch, acl, existing_ids=(4242,))

    persisted = []
    data = _zip_bytes([_simple_case(7)], audio_files=[
        {'id': 7, 'name': '源D.wav', 'bytes': _wav_bytes(8)}])
    receipt = _run_import(monkeypatch, 'pkg.zip', data, persisted)

    assert receipt['errors'] == []
    assert receipt['imported_count'] == 1
    assert persisted[0]['config']['rounds'][0]['audios'][0]['audio_id'] == 4242


# ----------------------------------------------------------------------
# 9. 预览：不报假缺失、不登记
# ----------------------------------------------------------------------
def test_preview_package_audio_not_reported_missing_and_not_registered(monkeypatch):
    acl = _FakeAudioAcl()          # 目标库无同 md5
    _install_acl(monkeypatch, acl, existing_ids=())

    data = _zip_bytes([_simple_case(7)], audio_files=[
        {'id': 7, 'name': '源E.wav', 'bytes': _wav_bytes(9)}])
    preview = _run_preview(monkeypatch, 'pkg.zip', data)

    assert preview['errors'] == []              # 包内音频不得报「音频 7 不存在」
    assert acl.register_calls == []             # 预览只读
    assert preview['audioPackageCount'] == 1


def test_preview_rewrites_hit_ids_and_ignores_flat_columns(monkeypatch):
    md5 = hashlib.md5(_wav_bytes(11)).hexdigest()
    acl = _FakeAudioAcl(md5_hits={md5: 606})
    _install_acl(monkeypatch, acl, existing_ids=(606,))

    case = _full_scope_case([1, 2, 3, 4, 5, 6])
    # 只把 a0 的包内音频放进包，其余 id 不在包内 → 仍按引用校验
    data = _zip_bytes([case], audio_files=[
        {'id': 1, 'name': '源F.wav', 'bytes': _wav_bytes(11)}])
    preview = _run_preview(monkeypatch, 'pkg.zip', data)

    # 其余源 id 不在包内也不在目标库 → 按引用口径逐条缺失（命中项 606 不误报）
    assert preview['errors'] == ['第1行: 音频 2、5、4、3 不存在']
    assert acl.register_calls == []


def test_preview_payload_keeps_original_package_ids(monkeypatch):
    """预览回显仍是包内原始行：id 重写只作用于校验副本。"""
    md5 = hashlib.md5(_wav_bytes(13)).hexdigest()
    _install_acl(monkeypatch, _FakeAudioAcl(md5_hits={md5: 606}), existing_ids=(606,))

    data = _zip_bytes([_simple_case(7)], audio_files=[
        {'id': 7, 'name': '源H.wav', 'bytes': _wav_bytes(13)}])
    preview = _run_preview(monkeypatch, 'pkg.zip', data)

    assert preview['errors'] == []
    assert preview['testCases'][0]['config']['rounds'][0]['audios'][0]['audio_id'] == 7


def test_preview_and_import_errors_comparable(monkeypatch):
    """预览 errors 与导入回执 errors 逐条可比（既有约定，INT-2215 不破）。"""
    acl = _FakeAudioAcl()
    _install_acl(monkeypatch, acl, existing_ids=())
    data = _zip_bytes([_simple_case(999999), _simple_case(888888)])
    preview = _run_preview(monkeypatch, 'pkg.zip', data)

    acl2 = _FakeAudioAcl()
    _install_acl(monkeypatch, acl2, existing_ids=())
    persisted = []
    receipt = _run_import(monkeypatch, 'pkg.zip', data, persisted)
    assert preview['errors'] == receipt['errors']
