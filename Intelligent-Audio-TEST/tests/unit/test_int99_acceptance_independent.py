# -*- coding: utf-8 -*-
"""INT-99 测试工程师独立验收补充测试

交付单测（test_int99_speakers_map_passthrough.py）之外的补充覆盖：

1. E2E 提取链路回归：extract_speakers_from_annotations 本次被重构为复用纯函数
   speakers_from_annotation_data（行为保持），E2E 侧此前无直接单测——补上
   真实调用链（build_speakers_map_from_dry_audios → extract_speakers_from_annotations
   → repo.get_annotations_by_audio）的回归保护。
2. AC1 结构级同语义对照：E2E build_audio_timelines（playback_orchestrator 消费）
   与 API 渲染路径共用的 calculate_speaker_aware_audio_delays 在相同输入下
   起始时刻逐一相等——共同 speaker 顺序 / 无共同 speaker 交叠（overlap_time、
   overlap_rate 两口径）/ 无 speakers_map 回退。
3. AC1 键归一：API 侧 speakers_map 经 JSON 往返为 str 键，E2E 原生为 int 键，
   两侧各自查找口径下同语义。
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test-access')
os.environ.setdefault('OSS_SECRET_KEY', 'test-secret')

from audio_service.infrastructure.audio.audio_timeline import (
    build_audio_timelines,
    build_speakers_map_from_dry_audios,
    calculate_speaker_aware_audio_delays,
    extract_speakers_from_annotations,
    speakers_from_annotation_data,
)


# ── E2E 提取链路回归（本次重构面） ─────────────────────────


class _Ann:
    def __init__(self, data):
        self.data = data


@pytest.fixture
def stub_annotations_repo(monkeypatch):
    """替换 AudioRepository.get_annotations_by_audio（保留真实调用链）"""
    store = {}

    def _fake(self, audio_id):
        return store.get(int(audio_id), [])

    monkeypatch.setattr(
        'audio_service.infrastructure.persistence.audio_repository.AudioRepository.get_annotations_by_audio',
        _fake)
    return store


class TestE2EExtractionChain:
    def test_extract_union_across_annotation_shapes(self, stub_annotations_repo):
        stub_annotations_repo[11] = [
            _Ann({'segments': [{'speaker': 'spk9', 'start': 0},
                               {'speaker': 'spk8', 'start': 1},
                               {'start': 2}]}),           # dict + segments，无 speaker 段跳过
            _Ann([{'speaker': 'spk7'}]),                  # list 形态
            _Ann({'transcript': 'no speakers'}),          # 无 speaker 键
            _Ann(None),                                   # data 为 None
        ]
        assert extract_speakers_from_annotations(11) == {'spk9', 'spk8', 'spk7'}

    def test_extract_no_annotations_returns_empty(self, stub_annotations_repo):
        assert extract_speakers_from_annotations(999) == set()

    def test_extract_falsy_audio_id_short_circuits(self, monkeypatch):
        """audio_id 为空：不触 repo（短路语义保持）"""
        import audio_service.infrastructure.persistence.audio_repository as repo_mod

        def _boom(self, audio_id):
            raise AssertionError('falsy audio_id 不应触达 repo')

        monkeypatch.setattr(repo_mod.AudioRepository, 'get_annotations_by_audio', _boom)
        assert extract_speakers_from_annotations(None) == set()
        assert extract_speakers_from_annotations(0) == set()

    def test_pure_function_matches_old_inline_semantics(self):
        """纯函数与重构前内联口径一致：dict/list 两形态、空 speaker 值不收集"""
        assert speakers_from_annotation_data(
            {'segments': [{'speaker': 'a'}, {'speaker': ''}, {'speaker': None}, {}]}
        ) == {'a'}
        assert speakers_from_annotation_data([{'speaker': 'b'}, 'not-a-dict']) == {'b'}
        assert speakers_from_annotation_data({}) == set()
        assert speakers_from_annotation_data(None) == set()

    def test_build_speakers_map_from_dry_audios(self, stub_annotations_repo):
        """int 键映射 + 缺 audio_id 条目跳过"""
        stub_annotations_repo[1] = [_Ann({'segments': [{'speaker': 'spk9'}]})]
        stub_annotations_repo[2] = [_Ann({'segments': [{'speaker': 'spk8'}]})]
        dry = [
            ({'audio_id': 1, 'play_order': 0}, SimpleNamespace(duration=1.0)),
            ({'play_order': 1}, SimpleNamespace(duration=1.0)),   # 无 audio_id → 跳过
            ({'audio_id': 2, 'play_order': 2}, SimpleNamespace(duration=2.0)),
        ]
        result = build_speakers_map_from_dry_audios(dry)
        assert result == {1: {'spk9'}, 2: {'spk8'}}


# ── AC1：E2E build_audio_timelines ↔ API calculate_speaker_aware_audio_delays ──
# 时长取 1.0 / 2.0 / 1.5、交叠取 0.5（二进制精确浮点），断言无舍入噪声。


def _e2e_dry(durations_by_id):
    """E2E 形态干声：[(config_dict, audio_obj)]，audio_id 即 play_order 顺序"""
    dry = []
    for play_order, (audio_id, duration) in enumerate(durations_by_id):
        dry.append(({'audio_id': audio_id, 'play_order': play_order},
                    SimpleNamespace(duration=duration, file_path='')))
    return dry


def _api_configs(durations_by_id):
    """API 渲染时间轴形态干声（audio_stream_orchestrator._build_timeline 同构）"""
    configs = []
    for play_order, (audio_id, duration) in enumerate(durations_by_id):
        configs.append({'audio_id': str(audio_id), 'type': 'speaker',
                        'play_order': play_order, 'duration': duration,
                        'offset': 0, 'file': ''})
    return configs


DURATIONS = [(1, 1.0), (2, 2.0), (3, 1.5)]


def _starts_e2e(speakers_map=None, overlap_time=0.0, overlap_rate=0.0):
    timelines = build_audio_timelines(
        _e2e_dry(DURATIONS), overlap_rate, overlap_time,
        speakers_map={k: set(v) for k, v in (speakers_map or {}).items()} or None)
    return [t['start'] for t in timelines]


def _starts_api(speakers_map=None, overlap_time=0.0, overlap_rate=0.0):
    sm = {str(k): set(v) for k, v in (speakers_map or {}).items()} or None
    delays = calculate_speaker_aware_audio_delays(
        _api_configs(DURATIONS), overlap_rate=overlap_rate, is_overlap=True,
        global_offset=0, overlap_time=overlap_time, speakers_map=sm)
    return [start for _, start in delays]


class TestE2EApiTimelineParity:
    def test_common_speaker_sequential_parity(self):
        """相邻共同 speaker → 双侧顺序（start = prev_end），交叠配置被覆盖"""
        sm = {1: ['spk9'], 2: ['spk9'], 3: ['spk9']}
        e2e = _starts_e2e(sm, overlap_time=0.5)
        api = _starts_api(sm, overlap_time=0.5)
        assert e2e == api == [0.0, 1.0, 3.0]

    def test_no_common_speaker_overlap_time_parity(self):
        """无共同 speaker + overlap_time → 双侧同交叠量"""
        sm = {1: ['spk9'], 2: ['spk8'], 3: ['spk7']}
        e2e = _starts_e2e(sm, overlap_time=0.5)
        api = _starts_api(sm, overlap_time=0.5)
        assert e2e == api == [0.0, 0.5, 2.0]

    def test_no_common_speaker_overlap_rate_parity(self):
        """无共同 speaker + overlap_rate → start = prev_end * (1 - rate) 链式"""
        sm = {1: ['spk9'], 2: ['spk8'], 3: ['spk7']}
        e2e = _starts_e2e(sm, overlap_rate=0.5)
        api = _starts_api(sm, overlap_rate=0.5)
        assert e2e == api == [0.0, 0.5, 1.25]

    def test_fallback_without_speakers_map_parity(self):
        """无 speakers_map → 双侧回退 play_order 链式交叠（INT-82 现状同口径）"""
        assert _starts_e2e(None, overlap_time=0.5) == [0.0, 0.5, 2.0]
        assert _starts_api(None, overlap_time=0.5) == [0.0, 0.5, 2.0]
        assert _starts_e2e(None, overlap_rate=0.5) == [0.0, 0.5, 1.25]
        assert _starts_api(None, overlap_rate=0.5) == [0.0, 0.5, 1.25]

    def test_partial_annotations_mixed_parity(self):
        """部分标注：有共同 speaker 的相邻对顺序，无标注对按交叠——逐对同语义"""
        sm = {1: ['spk9'], 2: ['spk9']}   # audio 3 无标注 → 与前对无共同 speaker
        e2e = _starts_e2e(sm, overlap_time=0.5)
        api = _starts_api(sm, overlap_time=0.5)
        assert e2e == api == [0.0, 1.0, 2.5]

    def test_int_key_and_str_key_equivalent(self):
        """AC1 键归一：E2E int 键与 API str 键在各自查找口径下同语义"""
        sm = {1: ['spk9'], 2: ['spk8']}
        assert _starts_e2e(sm, overlap_time=0.5) == _starts_api(sm, overlap_time=0.5) \
            == [0.0, 0.5, 2.0]
