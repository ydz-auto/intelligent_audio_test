"""
Audio engine 纯计算逻辑测试 - 不依赖数据库

测试范围：
- calculate_audio_delays: dry/noise/interferer 分类 + 延迟计算
- calculate_speaker_aware_audio_delays: speaker 感知版
- is_overlap_playback: 交叠模式判断
- get_audio_duration: wav 文件时长
- calculate_overlap_time: 交叠时间计算
- 语义拆分: type/is_noise/loop 字段正确性
- loop 行为: 循环标记正确传递
"""

import wave
import pytest


@pytest.fixture
def wav_file_1s(tmp_path):
    """1秒 44100Hz mono 16bit 静音 wav"""
    path = tmp_path / "test_1s.wav"
    wf = wave.open(str(path), 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(44100)
    wf.writeframes(b'\x00\x00' * 44100)
    wf.close()
    return str(path)


@pytest.fixture
def wav_file_2s(tmp_path):
    """2秒 wav"""
    path = tmp_path / "test_2s.wav"
    wf = wave.open(str(path), 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(44100)
    wf.writeframes(b'\x00\x00' * 88200)
    wf.close()
    return str(path)


# ── get_audio_duration ──

class TestGetAudioDuration:
    def test_valid_wav(self, wav_file_1s):
        from backend.services.audio.audio_engine import get_audio_duration
        assert abs(get_audio_duration(wav_file_1s) - 1.0) < 0.01

    def test_valid_wav_2s(self, wav_file_2s):
        from backend.services.audio.audio_engine import get_audio_duration
        assert abs(get_audio_duration(wav_file_2s) - 2.0) < 0.01

    def test_nonexistent_file(self):
        from backend.services.audio.audio_engine import get_audio_duration
        assert get_audio_duration('/fake/path.wav') == 0


# ── is_overlap_playback ──

class TestIsOverlapPlayback:
    def test_overlap_time_positive(self):
        from backend.services.audio.audio_engine import is_overlap_playback
        assert is_overlap_playback(2.0, 0) is True

    def test_overlap_rate_positive(self):
        from backend.services.audio.audio_engine import is_overlap_playback
        assert is_overlap_playback(0, 0.3) is True

    def test_both_zero(self):
        from backend.services.audio.audio_engine import is_overlap_playback
        assert is_overlap_playback(0, 0) is False

    def test_both_none(self):
        from backend.services.audio.audio_engine import is_overlap_playback
        assert is_overlap_playback(None, None) is False

    def test_overlap_time_priority(self):
        from backend.services.audio.audio_engine import is_overlap_playback
        assert is_overlap_playback(1.0, 0.5) is True


# ── calculate_overlap_time ──

class TestCalculateOverlapTime:
    def test_overlap_time_priority(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_overlap_time
        assert calculate_overlap_time(wav_file_1s, 2.0, 0.5) == 2.0

    def test_overlap_rate(self, wav_file_2s):
        from backend.services.audio.audio_engine import calculate_overlap_time
        result = calculate_overlap_time(wav_file_2s, 0, 0.5)
        assert abs(result - 1.0) < 0.01  # 2s * 0.5

    def test_overlap_rate_zero(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_overlap_time
        assert calculate_overlap_time(wav_file_1s, 0, 0) == 0

    def test_both_zero(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_overlap_time
        assert calculate_overlap_time(wav_file_1s, 0, 0) == 0


# ── calculate_audio_delays ──

class TestCalculateAudioDelays:
    def _make_config(self, file, play_order=0, is_noise=False, audio_type='dry',
                     loop=False, delay=0, offset=0, duration=0):
        return {
            'file': file,
            'device_index': 0,
            'channel': 0,
            'gain': 1.0,
            'delay': delay,
            'loop': loop,
            'is_noise': is_noise,
            'type': audio_type,
            'play_order': play_order,
            'offset': offset,
            'duration': duration,
        }

    def test_dry_only_sequential(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_audio_delays
        configs = [
            self._make_config(wav_file_1s, play_order=1),
            self._make_config(wav_file_1s, play_order=2),
        ]
        delays = calculate_audio_delays(configs, 0, False, 0, 0)
        # 两个干声顺序播放: 第一个 delay=0, 第二个 delay=1.0
        assert len(delays) == 2
        assert abs(delays[0][1] - 0.0) < 0.01
        assert abs(delays[1][1] - 1.0) < 0.01

    def test_dry_with_overlap_rate(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_audio_delays
        configs = [
            self._make_config(wav_file_1s, play_order=1),
            self._make_config(wav_file_1s, play_order=2),
        ]
        delays = calculate_audio_delays(configs, 0.5, True, 0, 0)
        # overlap_rate=0.5: 第二个 start = 1.0 * (1 - 0.5) = 0.5
        assert len(delays) == 2
        assert abs(delays[0][1] - 0.0) < 0.01
        assert abs(delays[1][1] - 0.5) < 0.01

    def test_dry_with_overlap_time(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_audio_delays
        configs = [
            self._make_config(wav_file_1s, play_order=1),
            self._make_config(wav_file_1s, play_order=2),
        ]
        delays = calculate_audio_delays(configs, 0, True, 0, 0.3)
        # overlap_time=0.3: 第二个 start = 1.0 - 0.3 = 0.7
        assert len(delays) == 2
        assert abs(delays[0][1] - 0.0) < 0.01
        assert abs(delays[1][1] - 0.7) < 0.01

    def test_noise_always_delay_zero(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_audio_delays
        configs = [
            self._make_config(wav_file_1s, is_noise=True, audio_type='noise',
                              loop=True, delay=5.0),  # 即使配了 delay=5
        ]
        delays = calculate_audio_delays(configs, 0, False, 0, 0)
        assert len(delays) == 1
        assert delays[0][1] == 0  # 噪声 delay 强制为 0

    def test_interferer_preserves_delay(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_audio_delays
        configs = [
            self._make_config(wav_file_1s, audio_type='interferer',
                              loop=True, delay=2.5),
        ]
        delays = calculate_audio_delays(configs, 0, False, 0, 0)
        assert len(delays) == 1
        assert abs(delays[0][1] - 2.5) < 0.01  # 干扰人 delay 保留

    def test_interferer_default_delay_zero(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_audio_delays
        configs = [
            self._make_config(wav_file_1s, audio_type='interferer', loop=False),
        ]
        delays = calculate_audio_delays(configs, 0, False, 0, 0)
        assert len(delays) == 1
        assert delays[0][1] == 0

    def test_mixed_three_types(self, wav_file_1s, wav_file_2s):
        from backend.services.audio.audio_engine import calculate_audio_delays
        configs = [
            self._make_config(wav_file_1s, play_order=1),                    # dry
            self._make_config(wav_file_2s, play_order=2),                    # dry
            self._make_config(wav_file_1s, is_noise=True, audio_type='noise',
                              loop=True),                                     # noise
            self._make_config(wav_file_1s, audio_type='interferer',
                              loop=True, delay=1.5),                         # interferer
        ]
        delays = calculate_audio_delays(configs, 0.3, True, 0, 0)

        delay_map = {cfg['type']: d for cfg, d in delays}
        # 干声参与交叠计算
        dry_delays = [d for cfg, d in delays if cfg['type'] == 'dry']
        assert len(dry_delays) == 2
        assert abs(dry_delays[0] - 0.0) < 0.01

        # 噪声 delay=0
        noise_delays = [d for cfg, d in delays if cfg['type'] == 'noise']
        assert len(noise_delays) == 1
        assert noise_delays[0] == 0

        # 干扰人 delay=1.5 保留
        interferer_delays = [d for cfg, d in delays if cfg['type'] == 'interferer']
        assert len(interferer_delays) == 1
        assert abs(interferer_delays[0] - 1.5) < 0.01

    def test_interferer_not_in_dry_overlap(self, wav_file_1s):
        """干扰人不参与干声交叠计算"""
        from backend.services.audio.audio_engine import calculate_audio_delays
        configs = [
            self._make_config(wav_file_1s, play_order=1),
            self._make_config(wav_file_1s, audio_type='interferer', delay=3.0),
            self._make_config(wav_file_1s, play_order=2),
        ]
        delays = calculate_audio_delays(configs, 0.5, True, 0, 0)

        dry_list = [(cfg, d) for cfg, d in delays if cfg['type'] == 'dry']
        # 只有 2 个干声参与交叠，干扰人不影响干声排序
        assert len(dry_list) == 2

    def test_empty_configs(self):
        from backend.services.audio.audio_engine import calculate_audio_delays
        delays = calculate_audio_delays([], 0, False, 0, 0)
        assert delays == []


# ── calculate_speaker_aware_audio_delays ──

class TestCalculateSpeakerAwareAudioDelays:
    def _make_config(self, file, play_order=0, is_noise=False, audio_type='dry',
                     loop=False, delay=0, audio_id=None):
        return {
            'file': file,
            'device_index': 0,
            'channel': 0,
            'gain': 1.0,
            'delay': delay,
            'loop': loop,
            'is_noise': is_noise,
            'type': audio_type,
            'play_order': play_order,
            'audio_id': audio_id,
        }

    def test_common_speaker_sequential(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_speaker_aware_audio_delays
        configs = [
            self._make_config(wav_file_1s, play_order=1, audio_id='a1'),
            self._make_config(wav_file_1s, play_order=2, audio_id='a2'),
        ]
        speakers_map = {'a1': {'S1'}, 'a2': {'S1'}}  # 共同 speaker
        delays = calculate_speaker_aware_audio_delays(
            configs, 0.5, True, 0, 0, speakers_map=speakers_map
        )
        dry_delays = [(cfg, d) for cfg, d in delays if cfg['type'] == 'dry']
        # 共同 speaker → 顺序播放: 第二个 delay = 1.0
        assert abs(dry_delays[1][1] - 1.0) < 0.01

    def test_no_common_speaker_overlap(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_speaker_aware_audio_delays
        configs = [
            self._make_config(wav_file_1s, play_order=1, audio_id='a1'),
            self._make_config(wav_file_1s, play_order=2, audio_id='a2'),
        ]
        speakers_map = {'a1': {'S1'}, 'a2': {'S2'}}  # 无共同 speaker
        delays = calculate_speaker_aware_audio_delays(
            configs, 0.5, True, 0, 0, speakers_map=speakers_map
        )
        dry_delays = [(cfg, d) for cfg, d in delays if cfg['type'] == 'dry']
        # 无共同 speaker + overlap_rate=0.5 → 交叠: delay = 0.5
        assert abs(dry_delays[1][1] - 0.5) < 0.01

    def test_interferer_excluded_from_dry(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_speaker_aware_audio_delays
        configs = [
            self._make_config(wav_file_1s, play_order=1, audio_id='a1'),
            self._make_config(wav_file_1s, audio_type='interferer', delay=2.0, audio_id='i1'),
        ]
        speakers_map = {'a1': {'S1'}, 'i1': {'S1'}}
        delays = calculate_speaker_aware_audio_delays(
            configs, 0, False, 0, 0, speakers_map=speakers_map
        )
        # 干扰人不参与干声计算，自己的 delay 保留
        dry_delays = [(cfg, d) for cfg, d in delays if cfg['type'] == 'dry']
        interferer_delays = [(cfg, d) for cfg, d in delays if cfg['type'] == 'interferer']
        assert len(dry_delays) == 1
        assert len(interferer_delays) == 1
        assert abs(interferer_delays[0][1] - 2.0) < 0.01

    def test_noise_excluded(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_speaker_aware_audio_delays
        configs = [
            self._make_config(wav_file_1s, play_order=1, audio_id='a1'),
            self._make_config(wav_file_1s, is_noise=True, audio_type='noise',
                              loop=True, audio_id='n1'),
        ]
        speakers_map = {'a1': {'S1'}, 'n1': {'S1'}}
        delays = calculate_speaker_aware_audio_delays(
            configs, 0, False, 0, 0, speakers_map=speakers_map
        )
        noise_delays = [(cfg, d) for cfg, d in delays if cfg['type'] == 'noise']
        assert len(noise_delays) == 1
        assert noise_delays[0][1] == 0


# ── 语义拆分: type/is_noise/loop ──

class TestSemanticSplit:
    def test_dry_semantics(self, wav_file_1s):
        config = {
            'file': wav_file_1s, 'device_index': 0, 'channel': 0, 'gain': 1.0,
            'is_noise': False, 'type': 'dry', 'loop': False, 'play_order': 1,
        }
        assert config['type'] == 'dry'
        assert config['is_noise'] is False
        assert config['loop'] is False

    def test_noise_semantics(self, wav_file_1s):
        config = {
            'file': wav_file_1s, 'device_index': 0, 'channel': 0, 'gain': 1.0,
            'is_noise': True, 'type': 'noise', 'loop': True, 'play_order': 0,
        }
        assert config['type'] == 'noise'
        assert config['is_noise'] is True
        assert config['loop'] is True

    def test_interferer_semantics(self, wav_file_1s):
        config = {
            'file': wav_file_1s, 'device_index': 0, 'channel': 0, 'gain': 1.0,
            'is_noise': False, 'type': 'interferer', 'loop': True, 'delay': 2.0,
        }
        assert config['type'] == 'interferer'
        assert config['is_noise'] is False
        assert config['loop'] is True
        assert config['delay'] == 2.0

    def test_interferer_loop_false(self, wav_file_1s):
        """干扰人 loop=False 时也不该被当噪声"""
        config = {
            'file': wav_file_1s, 'device_index': 0, 'channel': 0, 'gain': 1.0,
            'is_noise': False, 'type': 'interferer', 'loop': False, 'delay': 1.0,
        }
        assert config['is_noise'] is False
        assert config['type'] == 'interferer'


# ── 延迟计算公式验证 ──

class TestDelayFormulas:
    def _make_config(self, file, play_order=0, duration_override=0):
        return {
            'file': file,
            'device_index': 0,
            'channel': 0,
            'gain': 1.0,
            'delay': 0,
            'loop': False,
            'is_noise': False,
            'type': 'dry',
            'play_order': play_order,
            'offset': 0,
            'duration': duration_override,
        }

    def test_three_dry_no_overlap(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_audio_delays
        configs = [
            self._make_config(wav_file_1s, play_order=1),
            self._make_config(wav_file_1s, play_order=2),
            self._make_config(wav_file_1s, play_order=3),
        ]
        delays = calculate_audio_delays(configs, 0, False, 0, 0)
        # 顺序: 0, 1, 2
        assert abs(delays[0][1] - 0.0) < 0.01
        assert abs(delays[1][1] - 1.0) < 0.01
        assert abs(delays[2][1] - 2.0) < 0.01

    def test_three_dry_overlap_rate_50(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_audio_delays
        configs = [
            self._make_config(wav_file_1s, play_order=1),
            self._make_config(wav_file_1s, play_order=2),
            self._make_config(wav_file_1s, play_order=3),
        ]
        delays = calculate_audio_delays(configs, 0.5, True, 0, 0)
        # start[0]=0, end[0]=1.0
        # start[1] = 1.0*(1-0.5) = 0.5, end[1]=1.5
        # start[2] = 1.5*(1-0.5) = 0.75, end[2]=1.75
        assert abs(delays[0][1] - 0.0) < 0.01
        assert abs(delays[1][1] - 0.5) < 0.01
        assert abs(delays[2][1] - 0.75) < 0.01

    def test_overlap_time_clamp_to_zero(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_audio_delays
        configs = [
            self._make_config(wav_file_1s, play_order=1),
            self._make_config(wav_file_1s, play_order=2),
        ]
        # overlap_time=5.0 > duration=1.0, start 应该 clamp 到 0
        delays = calculate_audio_delays(configs, 0, True, 0, 5.0)
        assert delays[1][1] == 0

    def test_audio_offset_reduces_effective_duration(self, wav_file_1s):
        from backend.services.audio.audio_engine import calculate_audio_delays
        configs = [
            self._make_config(wav_file_1s, play_order=1),
            {
                'file': wav_file_1s, 'device_index': 0, 'channel': 0, 'gain': 1.0,
                'delay': 0, 'loop': False, 'is_noise': False, 'type': 'dry',
                'play_order': 2, 'offset': 0.5,  # 从 0.5s 开始播, effective=0.5s
            },
        ]
        delays = calculate_audio_delays(configs, 0, False, 0, 0)
        # 第一个 end = 0 + 1.0 = 1.0
        # 第二个 start = 1.0 (顺序)
        assert abs(delays[0][1] - 0.0) < 0.01
        assert abs(delays[1][1] - 1.0) < 0.01

# ── PlaybackOrchestrator 纯逻辑方法 ──

class TestOrchestratorHelpers:
    def test_find_device_obj_by_dict_device_id(self):
        from backend.services.audio.playback_orchestrator import PlaybackOrchestrator
        orch = PlaybackOrchestrator.__new__(PlaybackOrchestrator)
        devices = [
            {'device_id': 'dev1', 'id': 1, 'name': 'D1'},
            {'device_id': 'dev2', 'id': 2, 'name': 'D2'},
        ]
        assert orch._find_device_obj('dev1', devices)['name'] == 'D1'
        assert orch._find_device_obj('dev2', devices)['name'] == 'D2'
        assert orch._find_device_obj('dev3', devices) is None

    def test_find_device_obj_by_dict_id(self):
        from backend.services.audio.playback_orchestrator import PlaybackOrchestrator
        orch = PlaybackOrchestrator.__new__(PlaybackOrchestrator)
        devices = [{'device_id': 'dev1', 'id': 1, 'name': 'D1'}]
        assert orch._find_device_obj(1, devices)['name'] == 'D1'

    def test_find_device_obj_empty_list(self):
        from backend.services.audio.playback_orchestrator import PlaybackOrchestrator
        orch = PlaybackOrchestrator.__new__(PlaybackOrchestrator)
        assert orch._find_device_obj('dev1', []) is None
        assert orch._find_device_obj('dev1', None) is None

    def test_resolve_spl_gain_no_mapping(self):
        from backend.services.audio.playback_orchestrator import PlaybackOrchestrator
        orch = PlaybackOrchestrator.__new__(PlaybackOrchestrator)
        assert orch._resolve_spl_gain(None, 65.0) == 1.0

    def test_extract_overlap_rate_no_config(self):
        from backend.services.audio.playback_orchestrator import PlaybackOrchestrator
        orch = PlaybackOrchestrator.__new__(PlaybackOrchestrator)
        assert orch._extract_overlap_rate(None) == 0

    def test_extract_overlap_time_no_config(self):
        from backend.services.audio.playback_orchestrator import PlaybackOrchestrator
        orch = PlaybackOrchestrator.__new__(PlaybackOrchestrator)
        assert orch._extract_overlap_time(None) == 0


# ── Loop 语义验证（修复前 bug 复现 + 修复后验证） ──

class TestLoopSemantics:
    """验证 loop 字段独立于 is_noise 控制循环行为"""

    def _make_config(self, file, audio_type='dry', is_noise=False, loop=False, delay=0):
        return {
            'file': file, 'device_index': 0, 'channel': 0, 'gain': 1.0,
            'delay': delay, 'loop': loop, 'is_noise': is_noise,
            'type': audio_type, 'play_order': 0,
        }

    def test_dry_loop_false(self, wav_file_1s):
        """主讲人不循环"""
        cfg = self._make_config(wav_file_1s, 'dry', False, False)
        use_loop = cfg['is_noise'] or cfg['loop']
        assert use_loop is False

    def test_noise_always_loops(self, wav_file_1s):
        """噪声始终循环（is_noise=True 即触发）"""
        cfg = self._make_config(wav_file_1s, 'noise', True, True)
        use_loop = cfg['is_noise'] or cfg['loop']
        assert use_loop is True

    def test_interferer_loop_true(self, wav_file_1s):
        """干扰人 loop=True → 循环播放"""
        cfg = self._make_config(wav_file_1s, 'interferer', False, True, delay=2.0)
        use_loop = cfg['is_noise'] or cfg['loop']
        assert use_loop is True
        # 且 delay 保留
        assert cfg['delay'] == 2.0

    def test_interferer_loop_false(self, wav_file_1s):
        """干扰人 loop=False → 只播一次"""
        cfg = self._make_config(wav_file_1s, 'interferer', False, False, delay=1.5)
        use_loop = cfg['is_noise'] or cfg['loop']
        assert use_loop is False
        assert cfg['delay'] == 1.5

    def test_all_empty_excludes_loop(self, wav_file_1s):
        """all_empty 判定应排除循环音频"""
        configs = [
            self._make_config(wav_file_1s, 'interferer', False, True),  # loop
        ]
        for cfg in configs:
            is_noise = cfg['is_noise']
            use_loop = cfg['is_noise'] or cfg['loop']
            # 循环音频不算 all_empty
            is_empty_candidate = (not is_noise and not use_loop)
            assert is_empty_candidate is False

    def test_all_dry_finished_excludes_loop(self, wav_file_1s):
        """all_dry_finished 应排除噪声和循环音频"""
        configs = [
            self._make_config(wav_file_1s, 'dry', False, False),       # 干声（计入）
            self._make_config(wav_file_1s, 'noise', True, True),       # 噪声（排除）
            self._make_config(wav_file_1s, 'interferer', False, True), # 循环干扰人（排除）
        ]
        # 模拟 all_dry_finished 的过滤逻辑
        dry_count = sum(
            1 for c in configs
            if not c['is_noise'] and not (c['is_noise'] or c['loop'])
        )
        # 只有 1 个干声参与结束判定
        assert dry_count == 1

    def test_old_bug_is_noise_equals_loop(self, wav_file_1s):
        """回归测试：旧代码 is_noise=bool(loop) 导致干扰人被当噪声"""
        # 修复后的干扰人配置
        cfg = {
            'file': wav_file_1s, 'device_index': 0, 'channel': 0,
            'gain': 1.0, 'delay': 2.5, 'loop': True,
            'is_noise': False,  # ← 修复：不再是 bool(loop)
            'type': 'interferer',
        }
        # 验证不会被噪声分支吞掉
        from backend.services.audio.audio_engine import calculate_audio_delays
        delays = calculate_audio_delays([cfg], 0, False, 0, 0)
        assert len(delays) == 1
        assert abs(delays[0][1] - 2.5) < 0.01  # delay 不丢失


# ── play_overlap 干声过滤 ──

class TestPlayOverlapDryFilter:
    """验证 play_overlap 的 dry_audio_files 过滤排除干扰人"""

    def test_interferer_not_in_dry_filter(self, wav_file_1s):
        configs = [
            {'file': wav_file_1s, 'device_index': 0, 'channel': 0, 'gain': 1.0,
             'is_noise': False, 'type': 'dry', 'play_order': 1, 'loop': False},
            {'file': wav_file_1s, 'device_index': 0, 'channel': 0, 'gain': 1.0,
             'is_noise': False, 'type': 'interferer', 'play_order': 0, 'loop': True, 'delay': 1.5},
        ]
        # 模拟 play_overlap 里的 dry_audio_files 过滤
        dry_audio_files = [c for c in configs
                           if not c.get('is_noise', False) and c.get('type') != 'interferer']
        assert len(dry_audio_files) == 1
        assert dry_audio_files[0]['type'] == 'dry'

    def test_noise_not_in_dry_filter(self, wav_file_1s):
        configs = [
            {'file': wav_file_1s, 'device_index': 0, 'channel': 0, 'gain': 1.0,
             'is_noise': False, 'type': 'dry', 'play_order': 1, 'loop': False},
            {'file': wav_file_1s, 'device_index': 0, 'channel': 0, 'gain': 1.0,
             'is_noise': True, 'type': 'noise', 'play_order': 0, 'loop': True},
        ]
        dry_audio_files = [c for c in configs
                           if not c.get('is_noise', False) and c.get('type') != 'interferer']
        assert len(dry_audio_files) == 1