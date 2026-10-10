# -*- coding: utf-8 -*-
"""INT-113 验收补充测试（测试工程师独立验收）——覆盖开发自测未覆盖的薄弱点

在 tests/unit/test_int113_rounds_audio_resolution.py 之外补充以下场景：
1. 真实复现场景的另一种形态：库内陈旧同名记录 md5 与本次上传不同（旧素材同名不同内容），
   必须绑本次任务内新记录，不绑陈旧同名记录
2. 改名再传：任务文件 filename/original_filename 双键入任务内映射，库内同 md5 旧记录取最新
3. 混编场景：rounds 同时引用本任务文件名与库内已有素材名（非本任务文件），
   任务内优先、库内素材走 find_audio_by_name 最新同名
4. name→id 预查映射翻页封顶：恰好在 50 页处停止，不无限翻页；窗口外名字走逐名兜底
5. 秒传链路 wiring：_instant_upload_with_testcase 必须把 upload_file.upload_task_id
   透传给 create_test_case_from_audio（属性名错会静默退化为库内解析，须防回归）
"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int113acc_') + '/audio.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

from types import SimpleNamespace

from audio_service.application.services.audio_testcase_creation_service import (
    AudioTestCaseCreationService,
)
from audio_service.application.services.audio_upload.merge_mixin import AudioMergeMixin
from audio_service.application.services.audio_upload.round_config_service import (
    AudioRoundConfigService,
)


DRY_DEVICES = [
    {'id': 7, 'name': 'Dry Speaker', 'device_type': 'dry', 'is_deleted': False},
]


def _make_audio(audio_id=1, name='a.wav', md5=None, original_filename=None):
    return SimpleNamespace(id=audio_id, name=name, md5=md5 or f'md5-{audio_id}',
                           created_at=None,
                           original_filename=original_filename or name)


def _make_service(audio=None, find_by_name=None, library_pages=None,
                  task_files=None, md5_audios=None, captured=None,
                  list_audios_call_count=None, infinite_full_pages=False):
    svc = AudioTestCaseCreationService.__new__(AudioTestCaseCreationService)
    if audio is None:
        audio = _make_audio()

    class _Repo:
        def get_audio(self, _id):
            return audio

        def find_audio_by_name(self, name):
            if find_by_name is None:
                return audio if name == audio.name else None
            return find_by_name.get(name)

        def list_audios(self, query):
            page = query.get('page', 1)
            if list_audios_call_count is not None:
                list_audios_call_count.append(page)
            if infinite_full_pages:
                items = [_make_audio(200000 + i, f'filler-{i}.wav') for i in range(1000)]
            else:
                pages = library_pages or ([audio] if audio else [])
                idx = page - 1
                items = pages[idx] if 0 <= idx < len(pages) else []
            return SimpleNamespace(items=list(items), total=len(items) * 1000)

        def list_upload_files(self, _task_id):
            return task_files or []

        def get_audios_by_md5_list(self, _md5s):
            return list(md5_audios or [])

    svc.repo = _Repo()
    svc._playback_acl = SimpleNamespace(
        list_playback_devices=lambda: DRY_DEVICES,
    )
    svc._testcase_acl = SimpleNamespace(
        list_testcases=lambda **kw: {'items': [], 'total': 0},
        create_testcase_config=lambda data: (captured.append(data), {'id': 100})[1],
    )
    svc._algorithm_acl = SimpleNamespace(list_case_params=lambda _t: [])
    return svc


def _upload_file(filename, md5, original_filename=None):
    return SimpleNamespace(filename=filename,
                           original_filename=original_filename or filename, md5=md5)


class TestStaleSameNameDifferentMd5:
    """真实复现场景：库内陈旧同名记录与本次上传内容不同（md5 不同）"""

    def test_stale_record_with_different_md5_not_bound(self):
        """陈旧记录 718 与新记录 2235 同名但 md5 不同：md5 定位只命中 2235，
        轮次必须绑 2235，find_audio_by_name 返回的 718 不得参与"""
        name = 'B-IS-002_待办事项.wav'
        captured = []
        svc = _make_service(
            audio=_make_audio(2235, name, md5='md5-new'),
            find_by_name={name: _make_audio(718, name, md5='md5-old')},
            library_pages=[[_make_audio(718, name, md5='md5-old')]],
            task_files=[_upload_file(name, 'md5-new')],
            md5_audios=[_make_audio(2235, name, md5='md5-new')],
            captured=captured,
        )
        rounds = [{'round_number': 1,
                   'audios': [{'audio_name': name, 'play_order': 0}]}]
        svc.create_test_case_from_audio(
            2235, ['e2e'], [], rounds_config=rounds, raw_annotations=None,
            upload_task_id='task-113',
        )
        assert captured[0]['config']['rounds'][0]['audios'][0]['audio_id'] == 2235


class TestRenameReuploadTaskMap:
    """改名再传：任务文件双键（filename/original_filename）映射到 md5 命中的记录"""

    def test_both_name_keys_bind_md5_record(self):
        """改名再传：任务文件 filename='take2.wav'、original_filename='旧名.wav'，
        同 md5 新旧记录并存（库内旧 700 + 本次新建 2236）：任一键名都应经任务内
        映射绑到最新创建的 2236，同名异 md5 陈旧记录不得参与"""
        captured = []
        svc = _make_service(
            audio=_make_audio(2236, 'take2.wav', md5='md5-renamed'),
            find_by_name={
                '旧名.wav': _make_audio(700, '旧名.wav', md5='md5-renamed'),
                '陈旧同名.wav': _make_audio(718, '陈旧同名.wav', md5='md5-stale'),
            },
            library_pages=[[_make_audio(700, '旧名.wav', md5='md5-renamed')]],
            task_files=[_upload_file('take2.wav', 'md5-renamed',
                                     original_filename='旧名.wav')],
            # 同 md5 新旧并存：旧 700 在前，任务内映射须取最新 2236
            md5_audios=[_make_audio(700, '旧名.wav', md5='md5-renamed'),
                        _make_audio(2236, 'take2.wav', md5='md5-renamed')],
            captured=captured,
        )
        rounds = [
            {'round_number': 1,
             'audios': [{'audio_name': 'take2.wav', 'play_order': 0}]},
            {'round_number': 2,
             'audios': [{'audio_name': '旧名.wav', 'play_order': 1}]},
        ]
        svc.create_test_case_from_audio(
            2236, ['e2e'], [], rounds_config=rounds, raw_annotations=None,
            upload_task_id='task-113',
        )
        rounds_out = captured[0]['config']['rounds']
        assert rounds_out[0]['audios'][0]['audio_id'] == 2236
        assert rounds_out[1]['audios'][0]['audio_id'] == 2236


class TestMixedTaskAndLibraryNames:
    """混编：rounds 同时引用本任务文件名与库内已有素材名"""

    def test_task_file_and_library_only_name_each_resolved(self):
        """round1 是本任务文件（绑任务内 2235），round2 是库内已有素材名（非本任务
        文件，走 find_audio_by_name 绑最新同名 800），互不干扰"""
        task_name = '本次上传.wav'
        lib_name = '库内素材.wav'
        captured = []
        svc = _make_service(
            audio=_make_audio(2235, task_name, md5='md5-new'),
            find_by_name={lib_name: _make_audio(800, lib_name, md5='md5-lib')},
            library_pages=[[_make_audio(800, lib_name, md5='md5-lib')]],
            task_files=[_upload_file(task_name, 'md5-new')],
            md5_audios=[_make_audio(2235, task_name, md5='md5-new')],
            captured=captured,
        )
        rounds = [
            {'round_number': 1,
             'audios': [{'audio_name': task_name, 'play_order': 0}]},
            {'round_number': 2,
             'audios': [{'audio_name': lib_name, 'play_order': 1}]},
        ]
        svc.create_test_case_from_audio(
            2235, ['e2e'], [], rounds_config=rounds, raw_annotations=None,
            upload_task_id='task-113',
        )
        rounds_out = captured[0]['config']['rounds']
        assert rounds_out[0]['audios'][0]['audio_id'] == 2235
        assert rounds_out[1]['audios'][0]['audio_id'] == 800


class TestNameMapPagingCap:
    """name→id 预查映射翻页封顶：恰在 50 页停止"""

    def test_paging_stops_at_fifty_pages(self):
        """仓储每页都返回满页（模拟库超大）：list_audios 恰好被调 50 次后停止，
        不无限翻页"""
        call_pages = []
        captured = []
        svc = _make_service(
            audio=None,
            captured=captured,
            list_audios_call_count=call_pages,
            infinite_full_pages=True,
        )
        audio_map, _dev_map = svc._build_name_to_id_maps()
        assert len(call_pages) == 50, f'应恰好翻 50 页，实际 {len(call_pages)}'
        assert audio_map['filler-0.wav'] == 200000

    def test_window_outside_name_resolved_via_fallback(self):
        """50 页封顶后窗口外的名字：create_test_case_from_audio 轮次经
        find_audio_by_name 逐名兜底仍能绑定"""
        captured = []
        svc = _make_service(
            audio=None,
            find_by_name={'窗口外.wav': _make_audio(9001, '窗口外.wav')},
            library_pages=[[]],
            captured=captured,
        )
        rounds = [{'round_number': 1,
                   'audios': [{'audio_name': '窗口外.wav', 'play_order': 0}]}]
        svc.create_test_case_from_audio(
            9001, ['api'], [], rounds_config=rounds, raw_annotations=None,
        )
        assert captured[0]['config']['rounds'][0]['audios'][0]['audio_id'] == 9001


class TestInstantUploadChainWiring:
    """秒传链路 wiring：upload_task_id 必须透传到 create_test_case_from_audio"""

    def test_instant_upload_passes_upload_task_id(self):
        """_instant_upload_with_testcase 收到含 upload_task_id 的 upload_file 时，
        create_test_case_from_audio 必须收到相同 upload_task_id（防属性名错静默退化）"""
        mixin = AudioMergeMixin.__new__(AudioMergeMixin)
        existing = _make_audio(718, '旧名.wav', md5='md5-old')
        upload_file = SimpleNamespace(filename='新名.wav',
                                      original_filename='新名.wav',
                                      upload_task_id='task-xyz')

        match_calls = {}
        mixin._round_config_service = SimpleNamespace(
            match_existing_audio_in_rounds=lambda rounds, audio, upload_filenames=None:
            (match_calls.update(upload_filenames=upload_filenames), 1)[1],
        )
        mixin._annotation_service = SimpleNamespace(
            persist_annotations_and_raw=lambda *a, **kw: [],
        )
        creation_calls = {}
        mixin._testcase_creation_service = SimpleNamespace(
            create_test_case_from_audio=lambda *a, **kw: (
                creation_calls.update(upload_task_id=kw.get('upload_task_id')), [100])[1],
        )
        mixin.repo = SimpleNamespace(commit=lambda: None)

        params = {
            'rounds_config': [{'round_number': 1,
                               'audios': [{'audio_name': '新名.wav', 'play_order': 0}]}],
            'test_types': ['e2e'],
            'algorithm_type': None,
            'default_playback_device_id': None,
            'default_spl': 65.0,
            'noise_spl': 60.0,
            'noise_audio_id': None,
            'test_case_group_name': None,
            'dimensions_data': None,
            'algorithm_params_dict': None,
            'tc_inherit_tags': True,
        }
        mixin._instant_upload_with_testcase(existing, upload_file, {}, params, [])
        assert match_calls['upload_filenames'] == ('新名.wav', '新名.wav')
        assert creation_calls['upload_task_id'] == 'task-xyz', (
            '秒传链路必须把 upload_file.upload_task_id 透传给建用例服务，'
            '否则任务内解析静默退化为库内解析')

    def test_upload_file_entity_has_upload_task_id_attribute(self):
        """UploadFileEntity.upload_task_id 属性真实存在且默认 None
        （getattr 透传依赖此属性名）"""
        from audio_service.domain.entities.upload import UploadFileEntity
        f = UploadFileEntity(id='f1', upload_task_id='t1', filename='a.wav',
                             original_filename='a.wav', md5='m')
        assert f.upload_task_id == 't1'
        f2 = UploadFileEntity(id='f2', filename='b.wav', original_filename='b.wav', md5='m2')
        assert f2.upload_task_id is None
