# -*- coding: utf-8 -*-
"""音频分析领域服务

纯逻辑部分迁移自 shared/algorithm/reference_params/audio_utils.py
gRPC 调用部分移至 infrastructure/acl/audio_acl_repository.py
"""

from typing import Dict, List, Optional


class AudioAnalysisService:
    """音频分析领域服务 - 纯逻辑（不含 gRPC I/O）"""

    @staticmethod
    def ann_field(ann, key, default=None):
        """兼容 ORM 对象与 dict"""
        if isinstance(ann, dict):
            return ann.get(key, default)
        return getattr(ann, key, default)

    @staticmethod
    def audio_field(audio, key, default=None):
        """兼容 ORM 对象与 dict"""
        if isinstance(audio, dict):
            return audio.get(key, default)
        return getattr(audio, key, default)

    @staticmethod
    def adjust_segment_timestamps(segments: List[Dict], offset: float, play_order: int = None) -> List[Dict]:
        """偏移 start/end 时间戳"""
        adjusted = []
        for seg in segments:
            new_seg = dict(seg)
            new_seg['start'] = seg.get('start', 0) + offset
            new_seg['end'] = seg.get('end', 0) + offset
            if play_order is not None:
                new_seg['play_order'] = play_order
            adjusted.append(new_seg)
        return adjusted

    @staticmethod
    def merge_annotation_segments(segments_list: List[List[Dict]]) -> List[Dict]:
        """合并并按 (start, play_order) 排序"""
        all_segments = []
        for segs in segments_list:
            all_segments.extend(segs)
        all_segments.sort(key=lambda s: (s.get('start', 0), s.get('play_order', 0)))
        return all_segments

    @staticmethod
    def segments_to_rttm(segments: List[Dict], file_id: str = "test") -> str:
        """转 RTTM 文本"""
        lines = []
        for seg in segments:
            speaker = seg.get('speaker', 'unknown')
            start = seg.get('start', 0)
            end = seg.get('end', 0)
            duration = end - start
            lines.append(
                f"SPEAKER {file_id} 1 {start:.3f} {duration:.3f} <NA> <NA> {speaker} <NA> <NA>"
            )
        return '\n'.join(lines)

    @staticmethod
    def segments_to_stm(segments: List[Dict], file_id: str = "test", channel: int = 1) -> str:
        """转 STM 文本"""
        lines = []
        for seg in segments:
            speaker = seg.get('speaker', 'unknown')
            start = seg.get('start', 0)
            end = seg.get('end', 0)
            text = seg.get('text', '')
            lines.append(f"{start:.3f} {end:.3f} {file_id};;{channel};;{speaker};;{text}")
        return '\n'.join(lines)

    @staticmethod
    def extract_speakers_from_annotations(audio_id: int, annotation_map: Dict = None) -> set:
        """从预加载的 annotation_map 提取 speaker 集合（纯逻辑）"""
        speakers = set()
        if annotation_map and audio_id in annotation_map:
            for ann in annotation_map[audio_id]:
                if isinstance(ann, dict):
                    ann_type = ann.get('annotation_code') or ann.get('type', '')
                    if ann_type == 'diarization':
                        data = ann.get('data', {})
                        segments = data.get('segments', []) if isinstance(data, dict) else []
                        for seg in segments:
                            sp = seg.get('speaker')
                            if sp:
                                speakers.add(sp)
        return speakers

    @staticmethod
    def calculate_speaker_aware_offsets(
        audios_config: List[Dict],
        overlap_rate: float,
        overlap_time: float = 0,
        audio_durations: Dict[int, float] = None,
        audio_speakers: Dict[int, set] = None,
    ) -> Dict[int, float]:
        """speaker 感知偏移计算（纯逻辑，需要外部传入 durations 和 speakers）"""
        offsets = {}
        cumulative = 0.0

        audio_durations = audio_durations or {}
        audio_speakers = audio_speakers or {}

        for i, audio_item in enumerate(audios_config):
            audio_id = audio_item.get('audio_id')
            if i == 0:
                offsets[audio_id] = 0.0
            else:
                prev_id = audios_config[i - 1].get('audio_id')
                prev_duration = audio_durations.get(prev_id, 0)
                prev_speakers = audio_speakers.get(prev_id, set())
                curr_speakers = audio_speakers.get(audio_id, set())

                if prev_speakers & curr_speakers:
                    # 有共同 speaker，顺序播放
                    offsets[audio_id] = cumulative
                else:
                    # 无共同 speaker，交叠播放
                    overlap = max(overlap_time, prev_duration * overlap_rate)
                    offsets[audio_id] = cumulative - overlap

            duration = audio_durations.get(audio_id, 0)
            cumulative = offsets[audio_id] + duration

        return offsets

    @staticmethod
    def calculate_audio_offsets(
        audios_config: List[Dict],
        overlap_rate: float,
        overlap_time: float = 0,
        audio_durations: Dict[int, float] = None,
    ) -> Dict[int, float]:
        """链式交叠公式（纯逻辑）"""
        offsets = {}
        cumulative = 0.0
        audio_durations = audio_durations or {}

        for i, audio_item in enumerate(audios_config):
            audio_id = audio_item.get('audio_id')
            if i == 0:
                offsets[audio_id] = 0.0
            else:
                prev_id = audios_config[i - 1].get('audio_id')
                prev_duration = audio_durations.get(prev_id, 0)
                overlap = max(overlap_time, prev_duration * overlap_rate)
                offsets[audio_id] = cumulative - overlap

            cumulative = offsets[audio_id] + audio_durations.get(audio_id, 0)

        return offsets
