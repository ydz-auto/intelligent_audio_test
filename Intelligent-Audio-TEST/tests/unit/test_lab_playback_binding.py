# -*- coding: utf-8 -*-
"""播放设备按实验室换绑（e2e_test_service）。

被测设备与播放设备必须同实验室：用例里配置的播放设备只属于编写用例的
那个实验室，跨实验室执行必须换成执行实验室自己的播放设备。
选择顺序：已属于本实验室 → 同名 → 在线 → 任一；实验室无设备 → 用例失败。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from unittest.mock import MagicMock

import pytest

from e2e_test_service.application.services.e2e_executor.executor import E2EExecutor
from e2e_test_service.application.services.e2e_executor.lab_playback_binding import (
    LabPlaybackBindingError,
)


def _lab_device(device_id, name, status='online'):
    return {'id': device_id, 'name': name, 'status': status, 'lab_id': 39}


def _host(lab_devices):
    ex = E2EExecutor.__new__(E2EExecutor)
    ex._log = MagicMock()
    ex._playback_repo = MagicMock()
    ex._playback_repo.list_playback_devices.return_value = lab_devices
    ex._playback_repo.resolve_speaker_device.return_value = None
    ex._playback_repo.resolve_speaker_group_device.return_value = None
    return ex


def _case_config(device_id=5, name='设备正面（0.5m+0°）'):
    return {
        'rounds': [
            {'round_number': 1, 'audios': [
                {'audio_id': 1558, 'playback_device_id': device_id,
                 'playback_device_name': name},
            ]},
        ],
        'background_noise': {'playback_device_id': device_id},
    }


DEVICES_LAB_B = [
    _lab_device(21, '设备正面（0.5m+0°）', status='offline'),
    _lab_device(22, '音箱0°', status='online'),
]


class TestLabPlaybackBinding:

    def test_speaker_group_wins(self):
        """逻辑音箱组（源音箱 → 组 → 执行实验室设备）优先于同名/在线兜底。"""
        ex = _host(DEVICES_LAB_B)
        ex._playback_repo.resolve_speaker_device.return_value = 22
        config = _case_config()

        ex._bind_lab_playback_devices(7, 'c1', config,
                                      [{'device_id': 1, 'lab_id': 39}])

        ex._playback_repo.resolve_speaker_device.assert_called_with(5, 39)
        assert config['rounds'][0]['audios'][0]['playback_device_id'] == 22

    def test_stale_group_item_falls_back_to_name(self):
        """组内对应设备已不属于该实验室 → 按无对应处理（同名兜底）。"""
        ex = _host(DEVICES_LAB_B)
        ex._playback_repo.resolve_speaker_device.return_value = 999
        config = _case_config()

        ex._bind_lab_playback_devices(7, 'c1', config,
                                      [{'device_id': 1, 'lab_id': 39}])

        assert config['rounds'][0]['audios'][0]['playback_device_id'] == 21

    def test_same_name_preferred(self):
        ex = _host(DEVICES_LAB_B)
        config = _case_config()

        ex._bind_lab_playback_devices(7, 'c1', config,
                                      [{'device_id': 1, 'lab_id': 39}])

        audio = config['rounds'][0]['audios'][0]
        assert audio['playback_device_id'] == 21
        assert audio['playback_device_name'] == '设备正面（0.5m+0°）'
        # 背景噪声同样换绑
        assert config['background_noise']['playback_device_id'] == 21

    def test_online_device_when_name_missing(self):
        ex = _host(DEVICES_LAB_B)
        config = _case_config(name='不存在的摆位')

        ex._bind_lab_playback_devices(7, 'c1', config,
                                      [{'device_id': 1, 'lab_id': 39}])

        assert config['rounds'][0]['audios'][0]['playback_device_id'] == 22
        assert config['rounds'][0]['audios'][0]['playback_device_name'] == '音箱0°'

    def test_any_device_when_none_online(self):
        ex = _host([_lab_device(31, '唯一离线音箱', status='offline')])
        config = _case_config(name='不存在的摆位')

        ex._bind_lab_playback_devices(7, 'c1', config,
                                      [{'device_id': 1, 'lab_id': 39}])

        assert config['rounds'][0]['audios'][0]['playback_device_id'] == 31

    def test_already_in_lab_keeps_config(self):
        ex = _host(DEVICES_LAB_B)
        config = _case_config(device_id=22, name='音箱0°')

        ex._bind_lab_playback_devices(7, 'c1', config,
                                      [{'device_id': 1, 'lab_id': 39}])

        assert config['rounds'][0]['audios'][0]['playback_device_id'] == 22
        assert config['background_noise']['playback_device_id'] == 22

    def test_lab_without_playback_device_fails(self):
        ex = _host([])
        with pytest.raises(LabPlaybackBindingError):
            ex._bind_lab_playback_devices(7, 'c1', _case_config(),
                                          [{'device_id': 1, 'lab_id': 39}])

    def test_device_without_lab_fails(self):
        ex = _host(DEVICES_LAB_B)
        with pytest.raises(LabPlaybackBindingError):
            ex._bind_lab_playback_devices(7, 'c1', _case_config(),
                                          [{'device_id': 1, 'lab_id': None}])

    def test_cross_lab_group_fails(self):
        ex = _host(DEVICES_LAB_B)
        with pytest.raises(LabPlaybackBindingError):
            ex._bind_lab_playback_devices(
                7, 'c1', _case_config(),
                [{'device_id': 1, 'lab_id': 38}, {'device_id': 2, 'lab_id': 39}])

    def test_no_playback_config_skips_lookup(self):
        ex = _host(DEVICES_LAB_B)
        config = {'rounds': [{'round_number': 1, 'audios': []}]}

        ex._bind_lab_playback_devices(7, 'c1', config, [{'device_id': 1, 'lab_id': None}])

        ex._playback_repo.list_playback_devices.assert_not_called()

    def test_binding_disabled_keeps_config(self, monkeypatch):
        from shared.infrastructure.config import BaseConfig
        monkeypatch.setattr(BaseConfig, 'PLAYBACK_LAB_BINDING_ENABLED', False)
        ex = _host(DEVICES_LAB_B)
        config = _case_config()

        ex._bind_lab_playback_devices(7, 'c1', config, [{'device_id': 1, 'lab_id': 39}])

        assert config['rounds'][0]['audios'][0]['playback_device_id'] == 5
        ex._playback_repo.list_playback_devices.assert_not_called()


class TestSpeakerGroupBinding:
    """用例直接关联逻辑音箱（playback_speaker_group_id）"""

    def _group_config(self, group_id=3):
        return {
            'rounds': [
                {'round_number': 1, 'audios': [
                    {'audio_id': 1558, 'playback_speaker_group_id': group_id},
                ]},
            ],
            'background_noise': {'playback_speaker_group_id': group_id},
        }

    def test_group_resolves_for_execution_lab(self):
        """组 + 执行实验室 → 组内该实验室设备（名称一并回填）"""
        ex = _host(DEVICES_LAB_B)
        ex._playback_repo.resolve_speaker_group_device.return_value = 22
        config = self._group_config()

        ex._bind_lab_playback_devices(7, 'c1', config, [{'device_id': 1, 'lab_id': 39}])

        ex._playback_repo.resolve_speaker_group_device.assert_called_with(3, 39)
        audio = config['rounds'][0]['audios'][0]
        assert audio['playback_device_id'] == 22
        assert audio['playback_device_name'] == '音箱0°'
        assert config['background_noise']['playback_device_id'] == 22

    def test_group_wins_over_legacy_device_id(self):
        """同时存在组与老设备 ID 时以组为准"""
        ex = _host(DEVICES_LAB_B)
        ex._playback_repo.resolve_speaker_group_device.return_value = 21
        config = {'rounds': [{'round_number': 1, 'audios': [
            {'audio_id': 1558, 'playback_device_id': 5,
             'playback_device_name': '设备正面（0.5m+0°）',
             'playback_speaker_group_id': 3},
        ]}]}

        ex._bind_lab_playback_devices(7, 'c1', config, [{'device_id': 1, 'lab_id': 39}])

        assert config['rounds'][0]['audios'][0]['playback_device_id'] == 21
        ex._playback_repo.resolve_speaker_device.assert_not_called()

    def test_group_without_lab_device_fails(self):
        """组在该实验室未配置设备 → 用例直接失败"""
        ex = _host(DEVICES_LAB_B)
        with pytest.raises(LabPlaybackBindingError):
            ex._bind_lab_playback_devices(7, 'c1', self._group_config(),
                                          [{'device_id': 1, 'lab_id': 39}])

    def test_group_device_outside_lab_fails(self):
        """组内对应设备不属于该实验室（数据过期）→ 用例直接失败"""
        ex = _host(DEVICES_LAB_B)
        ex._playback_repo.resolve_speaker_group_device.return_value = 999
        with pytest.raises(LabPlaybackBindingError):
            ex._bind_lab_playback_devices(7, 'c1', self._group_config(),
                                          [{'device_id': 1, 'lab_id': 39}])

    def test_group_resolved_once_per_group(self):
        """同一组多次引用只解析一次"""
        ex = _host(DEVICES_LAB_B)
        ex._playback_repo.resolve_speaker_group_device.return_value = 22
        config = self._group_config()

        ex._bind_lab_playback_devices(7, 'c1', config, [{'device_id': 1, 'lab_id': 39}])

        assert ex._playback_repo.resolve_speaker_group_device.call_count == 1


class TestBackgroundNoiseGroupBinding:
    """背景噪声多选逻辑音箱（playback_speaker_group_ids → device_ids）"""

    def test_group_ids_resolved_to_lab_devices(self):
        ex = _host(DEVICES_LAB_B)
        ex._playback_repo.resolve_speaker_group_device.side_effect = lambda gid, lab: {
            3: 21, 4: 22,
        }.get(gid)
        config = {'rounds': [{'audios': [{
            'audio_id': 1,
            'background_noise': {'audio_id': 9, 'spl': 60, 'loop': True,
                                 'playback_speaker_group_ids': [3, 4]},
        }]}]}

        ex._bind_lab_playback_devices(7, 'c1', config, [{'device_id': 1, 'lab_id': 39}])

        noise = config['rounds'][0]['audios'][0]['background_noise']
        assert noise['device_ids'] == [21, 22]
        # 逻辑音箱引用保留（用例配置不改写，仅补执行用设备 id）
        assert noise['playback_speaker_group_ids'] == [3, 4]

    def test_group_without_lab_mapping_fails(self):
        ex = _host(DEVICES_LAB_B)
        ex._playback_repo.resolve_speaker_group_device.return_value = None
        config = {'background_noise': {'audio_id': 9, 'spl': 60,
                                       'playback_speaker_group_ids': [3]}}

        with pytest.raises(LabPlaybackBindingError):
            ex._bind_lab_playback_devices(7, 'c1', config,
                                          [{'device_id': 1, 'lab_id': 39}])


class TestVoiceprintGroupResolution:
    """声纹在 algorithm_params 独立列，需单独按执行实验室解析逻辑音箱"""

    def test_group_resolves_to_lab_device(self):
        ex = _host(DEVICES_LAB_B)
        ex._playback_repo.resolve_speaker_group_device.return_value = 22

        device_id = ex._voiceprint_playback_device(
            {'playback_speaker_group_id': 3},
            [{'device_id': 1, 'lab_id': 39}], 7, 'c1')

        assert device_id == 22
        ex._playback_repo.resolve_speaker_group_device.assert_called_with(3, 39)

    def test_missing_mapping_fails(self):
        ex = _host(DEVICES_LAB_B)
        with pytest.raises(LabPlaybackBindingError):
            ex._voiceprint_playback_device(
                {'playback_speaker_group_id': 3},
                [{'device_id': 1, 'lab_id': 39}], 7, 'c1')

    def test_legacy_device_id_passthrough(self):
        ex = _host(DEVICES_LAB_B)

        device_id = ex._voiceprint_playback_device(
            {'playback_device_id': 5}, [{'device_id': 1, 'lab_id': 39}], 7, 'c1')

        assert device_id == 5
        ex._playback_repo.resolve_speaker_group_device.assert_not_called()
