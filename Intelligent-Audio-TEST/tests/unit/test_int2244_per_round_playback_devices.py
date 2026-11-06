# -*- coding: utf-8 -*-
"""INT-2244 专项：批量逐轮播放设备设置（per_round 只传 round_values）。

缺陷：`_batch_update_playback_devices` 前置校验放过「只传 round_values」，
随后又用顶层 playback_devices 判空拦截，逐轮分支恒不可达 → React 弹窗逐轮
保存必现 400「更新播放设备需要 'deviceId' 或 'speakerGroupId'」。

覆盖：
1. per_round 只传 round_values（无 playback_devices / case_level）：成功且每轮
   按 roundValues 写 deviceId / speakerGroupId，未指定的轮次保持原配置
2. 非 per_round 只传 case_level（整体背景噪声）：成功，只写 config 级背景噪声
3. 非 per_round 且顶层 device/group 都缺、case_level 也空：仍按原口径 400
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from task_service.application.testcase.testcase_batch_service import TestCaseBatchService
from task_service.infrastructure.persistence.models.testcase_models import TestCase


class _FakeRepo:
    def __init__(self, cases):
        self._cases = cases
        self.flushed = False

    def list_testcases_by_ids(self, ids):
        return [c for c in self._cases if c.id in ids]

    def flush(self):
        self.flushed = True


def _service(cases):
    svc = TestCaseBatchService.__new__(TestCaseBatchService)
    svc.repo = _FakeRepo(cases)
    return svc


def _round_config():
    """两轮 E2E 形态用例：audio 携带播放设备，满足 has_playback_audio。"""
    return {
        'rounds': [
            {'round_number': 1, 'audios': [{'audio_id': 1, 'playback_device_id': 5}]},
            {'round_number': 2, 'audios': [{'audio_id': 2, 'playback_device_id': 6}]},
        ]
    }


def _case(case_id='tc-int2244'):
    return TestCase(
        id=case_id,
        name='INT-2244 逐轮设备用例',
        config=_round_config(),
        visibility='shared',
        deleted=False,
    )


def test_per_round_round_values_only_succeeds():
    tc = _case()
    svc = _service([tc])

    result = svc._batch_update_playback_devices({
        'ids': [tc.id],
        'round_mode': 'per_round',
        'round_numbers': [],
        'round_values': {'1': {'deviceId': 123}},
    })

    assert isinstance(result, str), f'应成功，实际: {result}'
    assert '已成功更新 1 个用例' in result
    rounds = tc.config['rounds']
    # 第 1 轮按 roundValues 写入
    assert rounds[0]['audios'][0]['playback_device_id'] == 123
    # 未指定的第 2 轮保持原配置
    assert rounds[1]['audios'][0]['playback_device_id'] == 6
    assert svc.repo.flushed is True


def test_per_round_speaker_group_per_round():
    tc = _case('tc-int2244-group')
    svc = _service([tc])

    result = svc._batch_update_playback_devices({
        'ids': [tc.id],
        'round_mode': 'per_round',
        'round_values': {
            '1': {'speakerGroupId': 7},
            '2': {'speakerGroupId': 8},
        },
    })

    assert isinstance(result, str), f'应成功，实际: {result}'
    rounds = tc.config['rounds']
    assert rounds[0]['audios'][0]['playback_speaker_group_id'] == 7
    assert rounds[1]['audios'][0]['playback_speaker_group_id'] == 8


def test_case_level_only_writes_config_background_noise():
    tc = _case('tc-int2244-case')
    tc.config = {
        **_round_config(),
        'background_noise': {'audio_id': 9, 'device_ids': [5]},
    }
    svc = _service([tc])

    result = svc._batch_update_playback_devices({
        'ids': [tc.id],
        'round_mode': 'all',
        'case_level': {'deviceId': 77},
        'targets': ['caseBackgroundNoise'],
    })

    assert isinstance(result, str), f'应成功，实际: {result}'
    assert tc.config['background_noise']['device_ids'] == [77]
    # 轮次级设备不受整体设置影响
    assert tc.config['rounds'][0]['audios'][0]['playback_device_id'] == 5


def test_unified_mode_without_device_or_group_still_rejected():
    tc = _case('tc-int2244-reject')
    svc = _service([tc])

    result = svc._batch_update_playback_devices({
        'ids': [tc.id],
        'round_mode': 'all',
        'playback_devices': {'foo': 1},
    })

    assert result == ("更新播放设备需要 'deviceId' 或 'speakerGroupId'", True)
    assert tc.config == _round_config()
