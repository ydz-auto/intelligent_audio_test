# -*- coding: utf-8 -*-
"""INT-89 验收测试 — e2e 用例自动创建缺省回填 playback_device_id

缺陷链路：音频上传 E2E 全链路（tests/api/test_e2e_full_chain.py）末尾用例自动创建为 0，
task_service 拒绝「第1轮第1个音频配置为 E2E 类型用例，必须指定 playback_device_id」。

根因：_inject_spl_and_device_from_annotations 在 raw_annotations 为空时提前 return，
rounds 音频条目的 playback_device_name 解析与 e2e 缺省回填（自动选中的 dry 设备）均被跳过。

验收标准：
1. 无标注 + rounds_config：e2e 逐音频回填自动选中 dry 设备与默认 spl，task_service 校验可通过
2. 多轮 e2e：所有轮次音频条目均回填
3. rounds 自带 playback_device_name：名字解析优先于缺省回填（不依赖标注）
4. 有标注：标注 spl/设备优先，未命中条目回填（原行为回归保护）
5. 显式传入 playback_device_id：全轮次使用显式值
6. 非 e2e（api）：不注入 playback_device_id（回归保护）
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

from types import SimpleNamespace

from audio_service.application.services.audio_testcase_creation_service import (
    AudioTestCaseCreationService,
)


DRY_DEVICES = [
    {'id': 7, 'name': 'Dry Speaker', 'device_type': 'dry', 'is_deleted': False},
    {'id': 9, 'name': 'Named Dry Dev', 'device_type': 'dry', 'is_deleted': False},
    {'id': 8, 'name': 'Ear Sim', 'device_type': 'ear', 'is_deleted': False},
]


def _make_audio(audio_id=1, name='a.wav'):
    return SimpleNamespace(id=audio_id, name=name, original_filename=name,
                           md5=f'md5-{audio_id}')


def _make_service(audio=None, devices=None, captured=None):
    """构造替身注入的创建服务实例（绕过 __init__ 的 ACL 仓储拉起）"""
    svc = AudioTestCaseCreationService.__new__(AudioTestCaseCreationService)
    audio = audio or _make_audio()

    class _Repo:
        def get_audio(self, _id):
            return audio

        def find_audio_by_name(self, _name):
            return audio if _name == audio.name else None

        def list_audios(self, _query):
            return SimpleNamespace(items=[audio])

    svc.repo = _Repo()
    svc._playback_acl = SimpleNamespace(
        list_playback_devices=lambda: devices if devices is not None else DRY_DEVICES,
    )
    svc._testcase_acl = SimpleNamespace(
        list_testcases=lambda **kw: {'items': [], 'total': 0},
        create_testcase_config=lambda data: (captured.append(data), {'id': 100})[1],
    )
    svc._algorithm_acl = SimpleNamespace(list_case_params=lambda _t: [])
    return svc


class TestE2EDefaultDeviceBackfill:
    """create_test_case_from_audio 的 e2e 播放设备缺省回填行为"""

    def test_no_annotations_rounds_backfilled(self):
        """缺陷复现场景：无标注 + rounds_config → 逐音频回填自动选中 dry 设备与默认 spl"""
        captured = []
        svc = _make_service(captured=captured)
        rounds = [{'roundNumber': 1,
                   'audios': [{'audio_name': 'a.wav', 'play_order': 0}]}]
        tc_ids = svc.create_test_case_from_audio(
            1, ['e2e'], [], playback_device_id=None, spl=65.0,
            rounds_config=rounds, raw_annotations=None,
        )
        assert tc_ids == [100]
        audio_cfg = captured[0]['config']['rounds'][0]['audios'][0]
        assert audio_cfg['playback_device_id'] == 7
        assert audio_cfg['spl'] == 65.0
        assert audio_cfg['audio_id'] == 1
        assert audio_cfg['play_order'] == 0

    def test_multi_round_all_backfilled(self):
        """多轮 e2e：所有轮次音频条目均回填设备与 spl"""
        captured = []
        svc = _make_service(captured=captured)
        rounds = [
            {'roundNumber': 1, 'audios': [{'audio_name': 'a.wav', 'play_order': 0}]},
            {'roundNumber': 2, 'audios': [{'audio_name': 'b.wav', 'play_order': 1}]},
        ]
        svc.create_test_case_from_audio(
            1, ['e2e'], [], rounds_config=rounds, raw_annotations=None,
        )
        rounds_out = captured[0]['config']['rounds']
        assert len(rounds_out) == 2
        for rnd in rounds_out:
            for audio_cfg in rnd['audios']:
                assert audio_cfg['playback_device_id'] == 7
                assert audio_cfg['spl'] == 65.0

    def test_named_device_in_rounds_resolved_without_annotations(self):
        """rounds 自带 playback_device_name：无标注时也解析，优先于缺省回填"""
        captured = []
        svc = _make_service(captured=captured)
        rounds = [{'roundNumber': 1,
                   'audios': [{'audio_name': 'a.wav', 'play_order': 0,
                               'playback_device_name': 'Named Dry Dev'}]}]
        svc.create_test_case_from_audio(
            1, ['e2e'], [], rounds_config=rounds, raw_annotations=None,
        )
        audio_cfg = captured[0]['config']['rounds'][0]['audios'][0]
        assert audio_cfg['playback_device_id'] == 9

    def test_annotation_values_win_over_backfill(self):
        """有标注：标注 spl/设备优先于缺省回填"""
        captured = []
        svc = _make_service(captured=captured)
        rounds = [{'roundNumber': 1,
                   'audios': [{'audio_name': 'a.wav', 'play_order': 0}]}]
        raw_annotations = [{'code': 'unified', 'data': {'segments': [
            {'audio': 'a.wav', 'spl': 78.5, 'playback_device_name': 'Named Dry Dev'},
        ]}}]
        svc.create_test_case_from_audio(
            1, ['e2e'], [], rounds_config=rounds, raw_annotations=raw_annotations,
        )
        audio_cfg = captured[0]['config']['rounds'][0]['audios'][0]
        assert audio_cfg['spl'] == 78.5
        assert audio_cfg['playback_device_id'] == 9

    def test_backfill_fills_fields_annotations_miss(self):
        """标注只含部分字段：缺失字段由缺省回填补齐"""
        captured = []
        svc = _make_service(captured=captured)
        rounds = [{'roundNumber': 1,
                   'audios': [{'audio_name': 'a.wav', 'play_order': 0}]}]
        raw_annotations = [{'code': 'unified', 'data': {'segments': [
            {'audio': 'a.wav', 'spl': 78.5},
        ]}}]
        svc.create_test_case_from_audio(
            1, ['e2e'], [], rounds_config=rounds, raw_annotations=raw_annotations,
        )
        audio_cfg = captured[0]['config']['rounds'][0]['audios'][0]
        assert audio_cfg['spl'] == 78.5
        assert audio_cfg['playback_device_id'] == 7

    def test_explicit_playback_device_id_used_for_all_rounds(self):
        """显式传入 playback_device_id：全轮次使用显式值而非自动选中"""
        captured = []
        svc = _make_service(captured=captured)
        rounds = [
            {'roundNumber': 1, 'audios': [{'audio_name': 'a.wav', 'play_order': 0}]},
            {'roundNumber': 2, 'audios': [{'audio_name': 'b.wav', 'play_order': 1}]},
        ]
        svc.create_test_case_from_audio(
            1, ['e2e'], [], playback_device_id=55, rounds_config=rounds,
            raw_annotations=None,
        )
        for rnd in captured[0]['config']['rounds']:
            for audio_cfg in rnd['audios']:
                assert audio_cfg['playback_device_id'] == 55

    def test_api_type_no_device_injected(self):
        """非 e2e（api）：不注入 playback_device_id（回归保护）"""
        captured = []
        svc = _make_service(captured=captured)
        rounds = [{'roundNumber': 1,
                   'audios': [{'audio_name': 'a.wav', 'play_order': 0}]}]
        svc.create_test_case_from_audio(
            1, ['api'], [], rounds_config=rounds, raw_annotations=None,
        )
        audio_cfg = captured[0]['config']['rounds'][0]['audios'][0]
        assert 'playback_device_id' not in audio_cfg

    def test_deleted_device_not_selected(self):
        """自动选中跳过 is_deleted 的 dry 设备"""
        devices = [
            {'id': 3, 'name': 'Deleted Dry', 'device_type': 'dry', 'is_deleted': True},
            {'id': 7, 'name': 'Dry Speaker', 'device_type': 'dry', 'is_deleted': False},
        ]
        captured = []
        svc = _make_service(devices=devices, captured=captured)
        rounds = [{'roundNumber': 1,
                   'audios': [{'audio_name': 'a.wav', 'play_order': 0}]}]
        svc.create_test_case_from_audio(
            1, ['e2e'], [], rounds_config=rounds, raw_annotations=None,
        )
        audio_cfg = captured[0]['config']['rounds'][0]['audios'][0]
        assert audio_cfg['playback_device_id'] == 7
