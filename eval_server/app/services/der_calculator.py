import os
import logging

logger = logging.getLogger(__name__)

try:
    from pyannote.metrics.diarization import DiarizationErrorRate
    from pyannote.core import Annotation, Segment
    PYANNOTE_AVAILABLE = True
except ImportError:
    PYANNOTE_AVAILABLE = False
    Annotation = None
    Segment = None

from ..utils.normalizer import normalize_text, normalize_stm_text, normalize_rttm_speaker

import json


def calculate_der(rttm_ref, stm_ref, rttm_res, stm_res, source_lang=None, target_lang=None, translate_direct=None, collar=0.5, skip_overlap=False, normalize=False):
    """
    计算 Diarization Error Rate (DER)

    参数:
        rttm_ref (str/dict): 参考音频的 RTTM 文件路径或内容，或 JSON 格式
        stm_ref (str/dict): 参考音频的 STM 文件路径或内容，或 JSON 格式
        rttm_res (str/dict): 识别结果的 RTTM 文件路径或内容，或 JSON 格式
        stm_res (str/dict): 识别结果的 STM 文件路径或内容，或 JSON 格式
        source_lang (str, optional): 源语言
        target_lang (str, optional): 目标语言
        translate_direct (str, optional): 翻译方向
        collar (float, optional): 时间对齐容差 (秒)，默认 0.5
        skip_overlap (bool, optional): 是否跳过重叠语音计算，默认 False
        normalize (bool, optional): 是否正则化文本，默认 False

    返回:
        dict: 包含 DER 计算结果
    """
    if not PYANNOTE_AVAILABLE:
        return {
            'der': None,
            'error': 'pyannote.metrics not installed',
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translate_direct': translate_direct
        }

    def parse_rttm_to_annotation(content):
        if not content:
            return Annotation() if Annotation else None

        annotation = Annotation()
        for line in content.strip().split('\n'):
            if line.startswith('SPEAKER'):
                parts = line.split()
                if len(parts) >= 6:
                    start = float(parts[3])
                    duration = float(parts[4])
                    speaker = parts[7] if len(parts) > 7 else 'unknown'
                    segment = Segment(start, start + duration)
                    annotation[segment] = speaker
        return annotation

    def parse_stm_to_annotation(content):
        if not content:
            return Annotation() if Annotation else None

        annotation = Annotation()
        for line in content.strip().split('\n'):
            if line and not line.startswith(';'):
                parts = line.split()
                if len(parts) >= 5:
                    start = float(parts[3])
                    end = float(parts[4])
                    speaker = parts[2] if len(parts) > 2 else 'unknown'
                    segment = Segment(start, end)
                    annotation[segment] = speaker
        return annotation

    def parse_rttm_from_json(rttm_data):
        if not rttm_data:
            return ""

        if isinstance(rttm_data, dict):
            if 'text' in rttm_data:
                return rttm_data['text']
            elif 'json' in rttm_data:
                json_data = rttm_data['json']
                if isinstance(json_data, str):
                    json_data = json.loads(json_data)

                lines = []
                for item in json_data:
                    speaker = item.get('speaker', 'unknown')
                    start = item.get('start', 0.0)
                    duration = item.get('duration', 0.0)

                    line = f"SPEAKER unknown 1 {start} {duration} <NA> <NA> {speaker} <NA>"
                    lines.append(line)

                return '\n'.join(lines)

        if isinstance(rttm_data, str):
            return rttm_data

        return str(rttm_data)

    def parse_stm_from_json(stm_data):
        if not stm_data:
            return ""

        if isinstance(stm_data, dict):
            if 'text' in stm_data:
                return stm_data['text']
            elif 'json' in stm_data:
                json_data = stm_data['json']
                if isinstance(json_data, str):
                    json_data = json.loads(json_data)

                lines = []
                for item in json_data:
                    file_id = item.get('file_id', 'unknown')
                    channel = item.get('channel', '1')
                    speaker = item.get('speaker', 'unknown')
                    start = item.get('start', 0.0)
                    end = item.get('end', 0.0)
                    text = item.get('text', '')

                    line = f"{file_id} {channel} {speaker} {start} {end} <o> {text}"
                    lines.append(line)

                return '\n'.join(lines)

        if isinstance(stm_data, str):
            return stm_data

        return str(stm_data)

    def is_file_path(content):
        if not content:
            return False
        if isinstance(content, dict):
            return False
        if not isinstance(content, str):
            return False
        return os.path.isabs(content) and os.path.exists(content)

    def get_annotation(file_or_content, file_type):
        if is_file_path(file_or_content):
            try:
                with open(file_or_content, 'r') as f:
                    content = f.read()
            except Exception:
                content = file_or_content
        else:
            if isinstance(file_or_content, dict):
                if file_type == 'rttm':
                    content = parse_rttm_from_json(file_or_content)
                else:
                    content = parse_stm_from_json(file_or_content)
            else:
                content = file_or_content

        if normalize and file_type == 'rttm':
            content = normalize_rttm_speaker(content)
        elif normalize and file_type == 'stm':
            content = normalize_stm_text(content)

        if file_type == 'rttm':
            return parse_rttm_to_annotation(content) if content else Annotation()
        elif file_type == 'stm':
            return parse_stm_to_annotation(content) if content else Annotation()
        return Annotation()

    try:
        ref_annotation = get_annotation(rttm_ref, 'rttm') if rttm_ref else get_annotation(stm_ref, 'stm')
        hyp_annotation = get_annotation(rttm_res, 'rttm') if rttm_res else get_annotation(stm_res, 'stm')

        if not list(ref_annotation):
            return {
                'der': -1,
                'error': 'No reference segments found',
                'source_lang': source_lang,
                'target_lang': target_lang,
                'translate_direct': translate_direct
            }

        metric = DiarizationErrorRate(collar=collar, skip_overlap=skip_overlap)

        der_value = metric(ref_annotation, hyp_annotation)

        try:
            detailed = metric.detailed_report(ref_annotation, hyp_annotation)
            false_alarm = detailed.get('false alarm', 0)
            missed_speech = detailed.get('missed speech', 0)
            speaker_error = detailed.get('speaker error', 0)
        except Exception:
            false_alarm = 0
            missed_speech = 0
            speaker_error = 0

        try:
            total_ref_time = 0.0
            for segment, track, label in ref_annotation.itertracks(yield_label=True):
                if hasattr(segment, 'duration'):
                    total_ref_time += segment.duration
        except Exception:
            total_ref_time = 0.0

        return {
            'der': round(der_value, 4),
            'missed_speech_rate': round(missed_speech, 4),
            'false_alarm_rate': round(false_alarm, 4),
            'speaker_error_rate': round(speaker_error, 4),
            'total_reference_time': round(total_ref_time, 2),
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translate_direct': translate_direct,
            'collar': collar,
            'skip_overlap': skip_overlap
        }
    except Exception as e:
        logger.error(f"DER calculation error: {e}")
        return {
            'der': None,
            'error': str(e),
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translate_direct': translate_direct
        }
