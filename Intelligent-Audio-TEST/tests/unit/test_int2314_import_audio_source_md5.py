# -*- coding: utf-8 -*-
"""INT-2314：manifest.audios[].source_md5 两跳复用（源库 md5 → 包内字节 md5 → 登记）。

背景：存量库 `audios.md5` 是**客户端原始上传字节** md5，导出打包的是**存储对象
字节**，两者普遍不一致；只按包内 md5 查重会让同库导出→导入重复登记全部音频。
契约（需求规划师裁定，方向 A）：manifest 增加 `source_md5`（可空），导入按
「`source_md5` 命中 → 包内 `md5` 命中 → 登记」两跳，`audios.md5` 语义不变。

覆盖卡面验收 A.1 的 6 条：
1. 存量形态（X≠Y）按 X 命中复用，零登记；
2. 库无 X 但有 Y → 第二跳复用；
3. 都没有 → 登记，请求 md5 用包内字节 md5；
4. 老包无 source_md5 → 只有第二跳，行为与 INT-2215 一致；
5. 包内两条同 source_md5 → 同一目标 id，不重复登记；
6. 预览两跳只读、pending 正确、零登记。
"""
import hashlib

from tests.unit.test_int2215_import_audio_remap import (
    _FakeAudioAcl,
    _install_acl,
    _parse_package,
    _run_import,
    _run_preview,
    _simple_case,
    _wav_bytes,
    _zip_bytes,
)
from api_gateway.application.services.testcase.testcase_import_audio import (
    MATCHED_BY_PACKAGE_MD5,
    MATCHED_BY_SOURCE_MD5,
    build_audio_remap,
)

# 存量形态用的「原始上传字节」md5（与包内字节 md5 天然不同）
SOURCE_X = 'a1b2c3d4e5f60718293a4b5c6d7e8f90'
SOURCE_X2 = 'b1b2c3d4e5f60718293a4b5c6d7e8f91'


def _pkg_md5(seed):
    return hashlib.md5(_wav_bytes(seed)).hexdigest()


# ----------------------------------------------------------------------
# 0. manifest 解析：source_md5 合法才留，否则 None（老包同样 None）
# ----------------------------------------------------------------------
def test_from_zip_parses_source_md5_optional():
    data = _zip_bytes(
        [_simple_case(7), _simple_case(8), _simple_case(9)],
        audio_files=[
            {'id': 7, 'name': 'A.wav', 'bytes': _wav_bytes(21),
             'source_md5': SOURCE_X.upper()},
            {'id': 8, 'name': 'B.wav', 'bytes': _wav_bytes(22),
             'source_md5': 'not-a-md5'},
            {'id': 9, 'name': 'C.wav', 'bytes': _wav_bytes(23)},   # 老包形态
        ])
    package = _parse_package(data)
    by_id = {e['source_id']: e for e in package.entries}
    assert by_id[7]['source_md5'] == SOURCE_X        # 去空白 + 转小写
    assert by_id[8]['source_md5'] is None            # 非法 → None，其余校验不动
    assert by_id[9]['source_md5'] is None
    assert by_id[8]['md5'] == _pkg_md5(22)           # 包内 md5 不受影响


# ----------------------------------------------------------------------
# 1. 存量形态：X≠Y，按 X 命中复用，零登记
# ----------------------------------------------------------------------
def test_stock_form_reuses_by_source_md5_without_registering():
    package_md5 = _pkg_md5(31)
    assert SOURCE_X != package_md5
    acl = _FakeAudioAcl(md5_hits={SOURCE_X: 501})
    package = _parse_package(_zip_bytes(
        [_simple_case(7)],
        audio_files=[{'id': 7, 'name': '存量.wav', 'bytes': _wav_bytes(31),
                      'source_md5': SOURCE_X}]))

    remap = build_audio_remap(package, acl, register=True)

    assert remap.source_to_target == {7: 501}
    assert remap.registered == []
    assert acl.register_calls == []                  # 命中原记录，不新增 audios 行
    assert remap.reused[0]['matched_by'] == MATCHED_BY_SOURCE_MD5
    # 一次查询覆盖两跳：source_md5 在前，包内 md5 也在 union 里
    assert acl.md5_calls == [{'md5_list': [SOURCE_X, package_md5]}]


def test_stock_form_import_receipt_counts_reuse(monkeypatch):
    acl = _FakeAudioAcl(md5_hits={SOURCE_X: 501})
    _install_acl(monkeypatch, acl, existing_ids=(501,))
    persisted = []
    data = _zip_bytes(
        [_simple_case(7)],
        audio_files=[{'id': 7, 'name': '存量.wav', 'bytes': _wav_bytes(32),
                      'source_md5': SOURCE_X}])

    receipt = _run_import(monkeypatch, 'pkg.zip', data, persisted)

    assert receipt['audio_reused_count'] == 1
    assert receipt['audio_registered_count'] == 0
    assert acl.register_calls == []
    assert persisted[0]['config']['rounds'][0]['audios'][0]['audio_id'] == 501


# ----------------------------------------------------------------------
# 2. 库无 X 但有 Y → 第二跳复用
# ----------------------------------------------------------------------
def test_second_hop_reuses_by_package_md5_when_source_md5_absent_in_db():
    package_md5 = _pkg_md5(33)
    acl = _FakeAudioAcl(md5_hits={package_md5: 601})
    package = _parse_package(_zip_bytes(
        [_simple_case(7)],
        audio_files=[{'id': 7, 'name': '跨库.wav', 'bytes': _wav_bytes(33),
                      'source_md5': SOURCE_X}]))

    remap = build_audio_remap(package, acl, register=True)

    assert remap.source_to_target == {7: 601}
    assert remap.reused[0]['matched_by'] == MATCHED_BY_PACKAGE_MD5
    assert acl.register_calls == []


def test_source_md5_hit_wins_over_package_md5_hit():
    """两跳都命中且指向不同记录 → 先 source_md5（同环境优先复用原记录）。"""
    package_md5 = _pkg_md5(34)
    acl = _FakeAudioAcl(md5_hits={SOURCE_X: 501, package_md5: 602})
    package = _parse_package(_zip_bytes(
        [_simple_case(7)],
        audio_files=[{'id': 7, 'name': 'A.wav', 'bytes': _wav_bytes(34),
                      'source_md5': SOURCE_X}]))

    remap = build_audio_remap(package, acl, register=True)
    assert remap.source_to_target == {7: 501}
    assert remap.reused[0]['matched_by'] == MATCHED_BY_SOURCE_MD5


# ----------------------------------------------------------------------
# 3. 都没有 → 登记，且请求 md5 用包内字节 md5（不是 source_md5）
# ----------------------------------------------------------------------
def test_no_hit_registers_with_package_md5_not_source_md5():
    package_md5 = _pkg_md5(35)
    acl = _FakeAudioAcl()
    package = _parse_package(_zip_bytes(
        [_simple_case(7)],
        audio_files=[{'id': 7, 'name': '新音频.wav', 'bytes': _wav_bytes(35),
                      'source_md5': SOURCE_X}]))

    remap = build_audio_remap(package, acl, register=True)

    assert [call['md5'] for call in acl.register_calls] == [package_md5]
    assert remap.registered[0]['md5'] == package_md5
    assert remap.reused == []


def test_no_hit_registers_through_import_path(monkeypatch):
    package_md5 = _pkg_md5(36)
    acl = _FakeAudioAcl(register_results=[{
        'success': True, 'message': '登记成功', 'data': {'id': 777, 'reused': False}}])
    _install_acl(monkeypatch, acl, existing_ids=(777,))
    persisted = []
    data = _zip_bytes(
        [_simple_case(7)],
        audio_files=[{'id': 7, 'name': '新音频.wav', 'bytes': _wav_bytes(36),
                      'source_md5': SOURCE_X}])

    receipt = _run_import(monkeypatch, 'pkg.zip', data, persisted)

    assert [call['md5'] for call in acl.register_calls] == [package_md5]
    assert receipt['audio_registered_count'] == 1
    assert receipt['audio_reused_count'] == 0
    assert persisted[0]['config']['rounds'][0]['audios'][0]['audio_id'] == 777


# ----------------------------------------------------------------------
# 4. 老包无 source_md5 → 只有第二跳，行为与 INT-2215 一致
# ----------------------------------------------------------------------
def test_old_package_without_source_md5_uses_package_md5_only():
    package_md5 = _pkg_md5(37)
    acl = _FakeAudioAcl(md5_hits={package_md5: 321})
    package = _parse_package(_zip_bytes(
        [_simple_case(7)],
        audio_files=[{'id': 7, 'name': '老包.wav', 'bytes': _wav_bytes(37)}]))

    remap = build_audio_remap(package, acl, register=True)

    assert acl.md5_calls == [{'md5_list': [package_md5]}]
    assert remap.source_to_target == {7: 321}
    assert remap.reused[0]['matched_by'] == MATCHED_BY_PACKAGE_MD5


# ----------------------------------------------------------------------
# 5. 包内两条 entry 同 source_md5 → 同一目标 id，不重复登记
# ----------------------------------------------------------------------
def test_two_entries_same_source_md5_share_target_without_duplicate_register():
    acl = _FakeAudioAcl(register_results=[{
        'success': True, 'message': '登记成功', 'data': {'id': 800, 'reused': False}}])
    package = _parse_package(_zip_bytes(
        [_simple_case(7), _simple_case(8)],
        audio_files=[
            {'id': 7, 'name': 'A.wav', 'bytes': _wav_bytes(41), 'source_md5': SOURCE_X},
            {'id': 8, 'name': 'B.wav', 'bytes': _wav_bytes(42), 'source_md5': SOURCE_X},
        ]))

    remap = build_audio_remap(package, acl, register=True)

    assert len(acl.register_calls) == 1               # 只登记一次
    assert remap.source_to_target == {7: 800, 8: 800}
    assert [item['source_id'] for item in remap.registered] == [7]
    assert [item['source_id'] for item in remap.reused] == [8]


def test_two_entries_same_source_md5_hit_reuses_both():
    acl = _FakeAudioAcl(md5_hits={SOURCE_X: 900})
    package = _parse_package(_zip_bytes(
        [_simple_case(7), _simple_case(8)],
        audio_files=[
            {'id': 7, 'name': 'A.wav', 'bytes': _wav_bytes(43), 'source_md5': SOURCE_X},
            {'id': 8, 'name': 'B.wav', 'bytes': _wav_bytes(44), 'source_md5': SOURCE_X},
        ]))

    remap = build_audio_remap(package, acl, register=True)

    assert remap.source_to_target == {7: 900, 8: 900}
    assert acl.register_calls == []
    assert len(remap.reused) == 2


# ----------------------------------------------------------------------
# 6. 预览：两跳只读、pending 正确、零登记
# ----------------------------------------------------------------------
def test_preview_two_hops_read_only_and_pending():
    package_md5 = _pkg_md5(45)
    acl = _FakeAudioAcl(md5_hits={SOURCE_X: 501})
    package = _parse_package(_zip_bytes(
        [_simple_case(7), _simple_case(8)],
        audio_files=[
            {'id': 7, 'name': '命中.wav', 'bytes': _wav_bytes(45),
             'source_md5': SOURCE_X},
            {'id': 8, 'name': '未命中.wav', 'bytes': _wav_bytes(46),
             'source_md5': SOURCE_X2},
        ]))

    remap = build_audio_remap(package, acl, register=False)

    assert remap.source_to_target == {7: 501}
    assert remap.pending == [8]
    assert remap.unresolved_source_ids == {8}
    assert acl.register_calls == []
    assert acl.md5_calls == [{'md5_list': [SOURCE_X, package_md5, SOURCE_X2,
                                           _pkg_md5(46)]}]


def test_preview_with_stock_form_reports_no_missing(monkeypatch):
    acl = _FakeAudioAcl(md5_hits={SOURCE_X: 501})
    _install_acl(monkeypatch, acl, existing_ids=(501,))
    data = _zip_bytes(
        [_simple_case(7)],
        audio_files=[{'id': 7, 'name': '存量.wav', 'bytes': _wav_bytes(47),
                      'source_md5': SOURCE_X}])

    preview = _run_preview(monkeypatch, 'pkg.zip', data)

    assert preview['errors'] == []
    assert acl.register_calls == []
