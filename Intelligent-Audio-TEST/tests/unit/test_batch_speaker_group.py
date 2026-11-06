# -*- coding: utf-8 -*-
"""批量配置更新：逻辑音箱组写入（用例只关联逻辑音箱）。

覆盖：
- `_apply_speaker_group_to_round`：音频/背景噪声/干扰人/声纹写组引用并清实体设备键
- `_apply_noise_to_round` / `_apply_noise_to_case_bn`：噪声按组写入
- `_extract_speaker_group_id(s)`：入参解析
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from task_service.application.testcase.testcase_batch_service import TestCaseBatchService


def _service():
    return TestCaseBatchService.__new__(TestCaseBatchService)


def _round_with_targets():
    return {
        'round_number': 1,
        'audios': [{
            'audio_id': 1,
            'playback_device_id': 5,
            'playback_device_name': '设备正面',
            'background_noise': {'audio_id': 9, 'device_ids': [5]},
            'interferers': [{'audio_id': 3, 'playback_device_id': 5}],
            'voiceprint': {'audio_id': 4, 'playback_device_id': 5},
        }],
        'backgroundNoise': {'audio_id': 9, 'device_ids': [5]},
    }


class TestExtractSpeakerGroup:
    def test_single(self):
        assert TestCaseBatchService._extract_speaker_group_id({'speakerGroupId': 7}) == 7
        assert TestCaseBatchService._extract_speaker_group_id({'speaker_group_id': 8}) == 8
        assert TestCaseBatchService._extract_speaker_group_id({'deviceId': 5}) is None

    def test_list(self):
        assert TestCaseBatchService._extract_speaker_group_ids([7, 8]) == [7, 8]
        assert TestCaseBatchService._extract_speaker_group_ids(
            {'speakerGroupIds': [7]}) == [7]
        assert TestCaseBatchService._extract_speaker_group_ids(None) is None


class TestApplySpeakerGroupToRound:
    def test_audio_and_nested_targets_rewritten(self):
        round_item = _round_with_targets()
        _service()._apply_speaker_group_to_round(
            round_item, 7, ['audio', 'segmentBackgroundNoise', 'interferers', 'voiceprint'])

        audio = round_item['audios'][0]
        assert audio['playback_speaker_group_id'] == 7
        assert 'playback_device_id' not in audio
        assert 'playback_device_name' not in audio
        assert audio['background_noise']['playback_speaker_group_ids'] == [7]
        assert 'device_ids' not in audio['background_noise']
        assert audio['interferers'][0]['playback_speaker_group_id'] == 7
        assert 'playback_device_id' not in audio['interferers'][0]
        assert audio['voiceprint']['playback_speaker_group_id'] == 7

    def test_round_level_background_noise(self):
        round_item = _round_with_targets()
        _service()._apply_speaker_group_to_round(round_item, 7, ['caseBackgroundNoise'])

        bn = round_item['backgroundNoise']
        assert bn['playback_speaker_group_ids'] == [7]
        assert 'device_ids' not in bn


class TestApplyNoiseWithGroups:
    def test_round_noise_writes_groups(self):
        round_item = _round_with_targets()
        _service()._apply_noise_to_round(
            round_item, 9, 60, [], ['segmentBackgroundNoise', 'caseBackgroundNoise'],
            speaker_group_ids=[7, 8])

        assert round_item['backgroundNoise']['playback_speaker_group_ids'] == [7, 8]
        assert 'device_ids' not in round_item['backgroundNoise']
        bn = round_item['audios'][0]['background_noise']
        assert bn['playback_speaker_group_ids'] == [7, 8]
        assert 'device_ids' not in bn

    def test_case_bn_group_overrides_device(self):
        config = {'background_noise': {'audio_id': 9, 'device_ids': [5]}}
        _service()._apply_noise_to_case_bn(
            config, 9, 60, [5], speaker_group_ids=[7])

        assert config['background_noise']['playback_speaker_group_ids'] == [7]
        assert 'device_ids' not in config['background_noise']
