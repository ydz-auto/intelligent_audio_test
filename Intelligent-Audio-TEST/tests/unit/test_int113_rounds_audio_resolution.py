# -*- coding: utf-8 -*-
"""INT-113 验收测试 — 用例自动创建 rounds 音频解析错配修复

缺陷链路（INT-95 主链实机复跑）：快照库自带同名陈旧素材（718/719/720，file_path
指向本机不存在的旧目录），OSS 直传同名文件生成新记录（2235/2236/2237）后，
/audios/upload/merge 自动建用例出现：
- 多轮用例 round1/round2 绑到陈旧记录 718/719（find_audio_by_name 无排序取最旧同名）；
- 单轮用例 audio_name 与 audio_id 语义错配（「仅剩 1 个未匹配项直接赋值」兜底不校验名称）；
- name→id 预查映射只取 per_page=1000 第一页，库 2400+ 条时窗口外名字走逐个兜底。

验收标准：
1. 任务内解析优先：rounds 音频名优先解析到本次上传任务内的音频记录（按 md5 定位），
   同 md5 多条记录（库内陈旧 + 本次新建）取最新创建的一条，绝不绑陈旧同名记录
2. 任务文件尚无对应记录时保持未匹配，不回退库内陈旧同名记录，也不强赋当前音频
3. 秒传兜底必须校验名称：改名场景经 upload_filenames 兜底匹配；名称对不上绝不跨名强赋
4. name→id 预查映射翻页遍历全量（同名保留最新），不再只取第一页
5. find_audio_by_name 同名多条时取最新创建的一条（真实 sqlite 库验证）
"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int113_') + '/audio.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

from types import SimpleNamespace

from audio_service.application.services.audio_testcase_creation_service import (
    AudioTestCaseCreationService,
)
from audio_service.application.services.audio_upload.round_config_service import (
    AudioRoundConfigService,
)


DRY_DEVICES = [
    {'id': 7, 'name': 'Dry Speaker', 'device_type': 'dry', 'is_deleted': False},
]


def _make_audio(audio_id=1, name='a.wav', md5=None, created_at=None, original_filename=None):
    return SimpleNamespace(id=audio_id, name=name, md5=md5 or f'md5-{audio_id}',
                           created_at=created_at,
                           original_filename=original_filename or name)


def _make_service(audio=None, find_by_name=None, library_pages=None,
                  task_files=None, md5_audios=None, captured=None):
    """构造替身注入的创建服务实例（绕过 __init__ 的 ACL 仓储拉起）"""
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
            pages = library_pages or ([audio] if audio else [])
            idx = page - 1
            items = pages[idx] if 0 <= idx < len(pages) else []
            total = sum(len(p) for p in pages)
            return SimpleNamespace(items=list(items), total=total)

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
    return SimpleNamespace(filename=filename, original_filename=original_filename or filename,
                           md5=md5)


class TestTaskScopedRoundResolution:
    """验收标准 1/2：本次上传任务内的音频记录优先，陈旧同名记录与强赋兜底均不生效"""

    def test_task_scoped_resolution_beats_stale_same_name(self):
        """INT-113 复现场景：库内同名陈旧记录（718/719/720）+ 本次新上传（2235/2236/2237），
        三轮配置各自解析到本次任务内的记录，同 md5 新旧并存时取最新创建的一条"""
        names = ['B-IS-002_待办事项.wav', 'B-IS-002_杭州景点.wav', 'B-IS-002_天气播报.wav']
        md5s = ['md5-n1', 'md5-n2', 'md5-n3']
        stale_ids = [718, 719, 720]
        new_ids = [2235, 2236, 2237]

        task_files = [_upload_file(names[i], md5s[i]) for i in range(3)]
        # md5-n1 库内陈旧记录与新记录并存：陈旧(718)在前，验证排序后新记录(2235)胜出
        md5_audios = (
            [_make_audio(718, names[0], md5='md5-n1'), _make_audio(2235, names[0], md5='md5-n1')]
            + [_make_audio(new_ids[i], names[i], md5=md5s[i]) for i in (1, 2)]
        )
        # 库内同名陈旧记录：逐名查库兜底会拿到它们，但任务内解析必须优先
        find_by_name = {names[i]: _make_audio(stale_ids[i], names[i]) for i in range(3)}
        captured = []
        svc = _make_service(
            audio=_make_audio(2237, names[2], md5='md5-n3'),
            find_by_name=find_by_name,
            library_pages=[[_make_audio(stale_ids[i], names[i]) for i in range(3)]],
            task_files=task_files,
            md5_audios=md5_audios,
            captured=captured,
        )
        rounds = [
            {'round_number': i + 1, 'audios': [{'audio_name': names[i], 'play_order': i}]}
            for i in range(3)
        ]
        tc_ids = svc.create_test_case_from_audio(
            2237, ['e2e'], [], rounds_config=rounds, raw_annotations=None,
            upload_task_id='task-113',
        )
        assert tc_ids == [100]
        rounds_out = captured[0]['config']['rounds']
        got_ids = [rnd['audios'][0]['audio_id'] for rnd in rounds_out]
        assert got_ids == new_ids, f'rounds 应绑定本次上传记录 {new_ids}，实际 {got_ids}'
        assert 718 not in got_ids and 719 not in got_ids and 720 not in got_ids

    def test_task_file_without_record_left_unmatched(self):
        """任务内文件尚无对应音频记录（如分文件 merge 时序在前）：保持未匹配，
        不回退库内陈旧同名记录，也不强赋当前音频"""
        names = ['a.wav', 'b.wav']
        task_files = [_upload_file(names[0], 'md5-a'), _upload_file(names[1], 'md5-b')]
        # 只有 a.wav 有本次记录；b.wav 尚未 merge，库内同名陈旧记录 719 存在
        md5_audios = [_make_audio(2235, names[0], md5='md5-a')]
        find_by_name = {names[1]: _make_audio(719, names[1])}
        captured = []
        svc = _make_service(
            audio=_make_audio(2235, names[0], md5='md5-a'),
            find_by_name=find_by_name,
            library_pages=[[_make_audio(719, names[1])]],
            task_files=task_files,
            md5_audios=md5_audios,
            captured=captured,
        )
        rounds = [
            {'round_number': 1, 'audios': [{'audio_name': names[0], 'play_order': 0}]},
            {'round_number': 2, 'audios': [{'audio_name': names[1], 'play_order': 1}]},
        ]
        svc.create_test_case_from_audio(
            2235, ['api'], [], rounds_config=rounds, raw_annotations=None,
            upload_task_id='task-113',
        )
        rounds_out = captured[0]['config']['rounds']
        assert rounds_out[0]['audios'][0]['audio_id'] == 2235
        assert 'audio_id' not in rounds_out[1]['audios'][0]

    def test_single_round_name_mismatch_not_force_assigned(self):
        """单轮错配回归（INT-113 实测：audio_name=待办事项.wav 配上 audio_id=2237 杭州景点）：
        名称对不上且查无此名时，绝不触发「仅剩 1 个未匹配项直接赋值」强赋当前音频"""
        captured = []
        svc = _make_service(
            audio=_make_audio(2237, '杭州景点.wav'),
            find_by_name={},
            library_pages=[[]],
            captured=captured,
        )
        rounds = [{'round_number': 1,
                   'audios': [{'audio_name': '待办事项.wav', 'play_order': 0}]}]
        svc.create_test_case_from_audio(
            2237, ['api'], [], rounds_config=rounds, raw_annotations=None,
        )
        audio_cfg = captured[0]['config']['rounds'][0]['audios'][0]
        assert 'audio_id' not in audio_cfg


class TestNameMapFullPaging:
    """验收标准 4：name→id 预查映射翻页遍历全量，同名保留最新"""

    def test_map_pages_beyond_first_page_and_prefers_newest(self):
        """库 2400+ 条时第二页的名字必须入映射；同名字段第一页（最新）记录优先"""
        newest_dup = _make_audio(2400, 'dup.wav')
        stale_dup = _make_audio(718, 'dup.wav')
        old_only = _make_audio(719, 'old-only.wav')
        page1 = [newest_dup] + [_make_audio(2300 + i, f'filler-{i}.wav') for i in range(999)]
        page2 = [stale_dup, old_only]
        captured = []
        svc = _make_service(audio=None, library_pages=[page1, page2], captured=captured)
        audio_map, _dev_map = svc._build_name_to_id_maps()
        assert audio_map['dup.wav'] == newest_dup.id
        assert audio_map['old-only.wav'] == old_only.id
        assert audio_map['filler-998.wav'] == 2300 + 998


class TestInstantUploadNameValidation:
    """验收标准 3：秒传兜底必须校验名称（round_config_service）"""

    def test_renamed_file_matched_via_upload_filenames(self):
        """秒传改名场景：已有记录 name 为旧名，本次上传文件名为新名 → 经
        upload_filenames 兜底匹配成功"""
        svc = AudioRoundConfigService()
        existing = _make_audio(718, '旧名.wav', md5='md5-old')
        rounds = [{'round_number': 1, 'audios': [{'audio_name': '新名.wav', 'play_order': 0}]}]
        matched = svc.match_existing_audio_in_rounds(
            rounds, existing, upload_filenames=('新名.wav', '新名.wav'))
        assert matched == 1
        assert rounds[0]['audios'][0]['audio_id'] == 718

    def test_cross_name_not_assigned(self):
        """名称对不上且无本次上传文件名可兜底：不匹配、不强赋（原「仅剩 1 个
        未匹配项直接赋值」盲赋兜底的回归保护）"""
        svc = AudioRoundConfigService()
        existing = _make_audio(2237, '杭州景点.wav', md5='md5-new')
        rounds = [{'round_number': 1, 'audios': [{'audio_name': '待办事项.wav', 'play_order': 0}]}]
        matched = svc.match_existing_audio_in_rounds(rounds, existing)
        assert matched == 0
        assert 'audio_id' not in rounds[0]['audios'][0]

    def test_multi_round_only_current_file_matched(self):
        """多轮秒传：只有名字对得上的轮次项绑定当前音频，其他轮次项保持未匹配"""
        svc = AudioRoundConfigService()
        existing = _make_audio(2236, '新名.wav', md5='md5-cur')
        rounds = [
            {'round_number': 1, 'audios': [{'audio_name': '其他文件.wav', 'play_order': 0}]},
            {'round_number': 2, 'audios': [{'audio_name': '新名.wav', 'play_order': 1}]},
        ]
        matched = svc.match_existing_audio_in_rounds(
            rounds, existing, upload_filenames=('新名.wav',))
        assert matched == 1
        assert 'audio_id' not in rounds[0]['audios'][0]
        assert rounds[1]['audios'][0]['audio_id'] == 2236


class TestFindAudioByNameNewestFirst:
    """验收标准 5：find_audio_by_name 同名多条时取最新创建的一条（真实 sqlite 库）"""

    def test_same_name_returns_newest_record(self):
        from shared.models.database import init_db, get_engine, remove_db_session
        from audio_service.infrastructure.persistence.models import Audio
        from audio_service.infrastructure.persistence.audio_repository import AudioRepository

        init_db(pool_size=2)
        remove_db_session()
        engine = get_engine()
        Base = Audio.__table__.metadata
        Base.create_all(bind=engine, tables=[Audio.__table__])

        repo = AudioRepository()
        session_kw = dict(
            name='同名素材.wav', original_filename='同名素材.wav', file_path='/lib/x.wav',
            size=1, duration=1.0, format='wav', deleted=False, md5='md5-x',
        )
        try:
            from shared.models.database import get_db_session
            from datetime import datetime, timedelta
            session = get_db_session()
            base = datetime(2026, 10, 1, 12, 0, 0)
            stale = Audio(created_at=base, **session_kw)
            fresh = Audio(created_at=base + timedelta(days=1), **session_kw)
            session.add(stale)
            session.flush()
            stale_id = stale.id
            session.add(fresh)
            session.flush()
            fresh_id = fresh.id
            session.commit()
            assert stale_id < fresh_id

            found = repo.find_audio_by_name('同名素材.wav')
            assert found.id == fresh_id, '同名多条应取最新创建的一条'
        finally:
            remove_db_session()
