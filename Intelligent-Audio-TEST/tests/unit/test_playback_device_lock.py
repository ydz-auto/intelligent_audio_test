# -*- coding: utf-8 -*-
"""播放设备互斥锁（audio_service）：同一只音箱同一时刻只播一轮。

同实验室并行用例共用音箱时在 play_round 内排队串行出音；
不同实验室用不同音箱各自拿锁，仍并行。
"""
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from audio_service.infrastructure.audio.playback_orchestrator import PlaybackOrchestrator


def _engine():
    engine = PlaybackOrchestrator(audio_service=MagicMock())
    engine._log = MagicMock()
    return engine


ROUND_CONFIG = {
    'audios': [
        {'audio_id': 1, 'playback_device_id': 5},
        {'audio_id': 2, 'playback_device_id': '7'},
    ],
    'algorithm_params': [{'interferers': [{'playback_device_id': 9}]}],
}


class TestCollectPlaybackDeviceIds:

    def test_nested_ids_unique(self):
        ids = PlaybackOrchestrator.collect_playback_device_ids(ROUND_CONFIG)
        assert ids == [5, 7, 9]

    def test_empty_config(self):
        assert PlaybackOrchestrator.collect_playback_device_ids(None) == []
        assert PlaybackOrchestrator.collect_playback_device_ids({}) == []


class TestPlaybackDeviceLock:

    def test_no_device_no_lock(self):
        engine = _engine()
        engine._play_round_body = MagicMock(return_value={'playback_result': True})

        result = engine.play_round({'audios': []}, 't1', round_number=1)

        assert result == {'playback_result': True}
        engine._play_round_body.assert_called_once()

    def test_locks_sorted_and_released(self):
        engine = _engine()
        engine._play_round_body = MagicMock(return_value={'playback_result': True})
        locks = [MagicMock(), MagicMock(), MagicMock()]
        with patch('shared.utils.distributed_coordinator.DistributedLock',
                   side_effect=locks) as lock_cls:
            engine.play_round(ROUND_CONFIG, 't1', round_number=1)

        keys = [c.args[0] for c in lock_cls.call_args_list]
        assert keys[0].endswith(':5') and keys[1].endswith(':7') and keys[2].endswith(':9')
        for lock in locks:
            lock.release.assert_called_once()

    def test_busy_device_skips_playback_and_releases_held(self):
        engine = _engine()
        engine._play_round_body = MagicMock(return_value={'playback_result': True})
        held, busy = MagicMock(), MagicMock()
        busy.acquire.return_value = False
        with patch('shared.utils.distributed_coordinator.DistributedLock',
                   side_effect=[held, busy]):
            result = engine.play_round(ROUND_CONFIG, 't1', round_number=1)

        assert result is None
        engine._play_round_body.assert_not_called()
        held.release.assert_called_once()
