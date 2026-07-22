# -*- coding: utf-8 -*-
"""
xiaoyi_takeover_latency.py
计算"小艺接管时延" = 模型回复第一个词时刻 - (音响结束播放时刻 + offset)

公式:
    takeover_latency_ms = (first_frame_ms + first_word_begin_ms) - (end_ms + offset_ms)

其中:
    first_frame_ms       : harmony_xiaoyichat.get_results() 返回的 recorder_first_frame_ms
                           (录屏首帧写入的绝对时刻, 毫秒 Unix 时间戳)
    first_word_begin_ms  : app.utils.PAUSE_JSON.generate_pause_json() 生成的 ASR JSON 中
                           chunks[0].timestamp[0] * 1000
                           (模型回复第一个词相对 mp4 起点的偏移, 毫秒)
    end_ms               : harmony_xiaoyichat.get_results() 返回的 end_ms
                           (本轮音频播放结束的绝对时刻, 毫秒 Unix 时间戳)
    offset_ms           : 音响结束播放时间戳与音频内容最后一个词的时延补偿, 默认 40ms
"""
import os
import json
import logging

logger = logging.getLogger(__name__)

# 音响结束播放时间戳与音频内容最后一个词的时延补偿（毫秒）
DEFAULT_OFFSET_MS = 40


def compute_takeover_latency(first_frame_ms, asr_json_path, end_ms, offset_ms=DEFAULT_OFFSET_MS):
    """
    计算小艺接管时延（从 ASR JSON 文件读取）

    Args:
        first_frame_ms (int|None): 录屏首帧写入的绝对时刻（毫秒 Unix 时间戳）
                                    对应 harmony_xiaoyichat.get_results() 的 recorder_first_frame_ms
        asr_json_path (str): app.utils.PAUSE_JSON.generate_pause_json() 生成的 ASR JSON 文件路径
                             （注意：引用的是 {wav同名}.json，不是 {wav同名}.pause.json）
        end_ms (int|None): 本轮音频播放结束的绝对时刻（毫秒 Unix 时间戳）
                           对应 harmony_xiaoyichat.get_results() 的 end_ms
        offset_ms (int): 音响结束播放与音频最后内容词的时延补偿, 默认 40ms

    Returns:
        dict: {
            'takeover_latency_ms': int|None,   接管时延（毫秒）
            'first_frame_ms': int|None,        录屏首帧时刻
            'first_word_begin_ms': int,        ASR 第一个词相对 mp4 起点的偏移（毫秒）
            'model_first_word_ms': int|None,   模型回复第一个词的绝对时刻（毫秒 Unix 时间戳）
            'end_ms': int|None,                音频播放结束时刻
            'offset_ms': int,                  时延补偿
            'audio_end_with_offset_ms': int|None, end_ms + offset_ms
            'message': str,                    错误/成功说明
        }
    """
    result = {
        'takeover_latency_ms': None,
        'first_frame_ms': first_frame_ms,
        'first_word_begin_ms': 0,
        'model_first_word_ms': None,
        'end_ms': end_ms,
        'offset_ms': offset_ms,
        'audio_end_with_offset_ms': None,
        'message': '',
    }

    # 1. 校验 first_frame_ms
    if first_frame_ms is None:
        result['message'] = 'first_frame_ms 为 None, 无法计算（录屏未启动或未检测到首帧）'
        logger.warning(result['message'])
        return result

    # 2. 校验 end_ms
    if end_ms is None:
        result['message'] = 'end_ms 为 None, 无法计算（未收到音响结束时间戳）'
        logger.warning(result['message'])
        return result

    # 3. 读取 ASR JSON 文件
    if not os.path.exists(asr_json_path):
        result['message'] = f'ASR JSON 文件不存在: {asr_json_path}'
        logger.error(result['message'])
        return result

    try:
        with open(asr_json_path, 'r', encoding='utf-8') as f:
            asr_hyp = json.load(f)
    except Exception as e:
        result['message'] = f'读取 ASR JSON 失败: {e}'
        logger.error(result['message'])
        return result

    chunks = asr_hyp.get('chunks', [])
    if not chunks:
        result['message'] = 'ASR chunks 为空, 无法定位第一个词'
        logger.warning(result['message'])
        return result

    # 4. 取第一个词的 begin_time（JSON 中单位是秒, 转毫秒）
    first_word_begin_s = chunks[0]['timestamp'][0]
    if first_word_begin_s is None:
        first_word_begin_s = 0.0
    first_word_begin_ms = int(first_word_begin_s * 1000)
    result['first_word_begin_ms'] = first_word_begin_ms

    # 5. 模型回复第一个词的绝对时刻
    model_first_word_ms = first_frame_ms + first_word_begin_ms
    result['model_first_word_ms'] = model_first_word_ms

    # 6. 音响结束时刻 + offset
    audio_end_with_offset_ms = end_ms + offset_ms
    result['audio_end_with_offset_ms'] = audio_end_with_offset_ms

    # 7. 接管时延 = 模型第一词 - (音响结束 + offset)
    takeover_latency_ms = model_first_word_ms - audio_end_with_offset_ms
    result['takeover_latency_ms'] = takeover_latency_ms
    result['message'] = 'OK'

    logger.info(
        f"[接管时延] first_frame_ms={first_frame_ms} "
        f"first_word_begin_ms={first_word_begin_ms} "
        f"model_first_word_ms={model_first_word_ms} "
        f"end_ms={end_ms} offset_ms={offset_ms} "
        f"audio_end_with_offset_ms={audio_end_with_offset_ms} "
        f"takeover_latency_ms={takeover_latency_ms}ms"
    )
    return result


def compute_takeover_latency_from_raw(first_frame_ms, asr_hyp, end_ms, offset_ms=DEFAULT_OFFSET_MS):
    """
    与 compute_takeover_latency 相同, 但直接传 ASR 结果对象（不读文件）

    Args:
        first_frame_ms: 录屏首帧时刻
        asr_hyp (dict): app.utils.PAUSE_JSON.generate_pause_json() 返回过程中使用的 ASR 结果
                           {text, chunks:[...]}（由 call_modelscope_asr + parse_result 产生）
        end_ms: 音响结束时刻
        offset_ms: 时延补偿

    Returns:
        dict: 同 compute_takeover_latency
    """
    result = {
        'takeover_latency_ms': None,
        'first_frame_ms': first_frame_ms,
        'first_word_begin_ms': 0,
        'model_first_word_ms': None,
        'end_ms': end_ms,
        'offset_ms': offset_ms,
        'audio_end_with_offset_ms': None,
        'message': '',
    }

    if first_frame_ms is None:
        result['message'] = 'first_frame_ms 为 None, 无法计算'
        return result
    if end_ms is None:
        result['message'] = 'end_ms 为 None, 无法计算'
        return result

    chunks = (asr_hyp or {}).get('chunks', [])
    if not chunks:
        result['message'] = 'ASR chunks 为空'
        return result

    first_word_begin_s = chunks[0]['timestamp'][0]
    if first_word_begin_s is None:
        first_word_begin_s = 0.0
    first_word_begin_ms = int(first_word_begin_s * 1000)
    result['first_word_begin_ms'] = first_word_begin_ms

    model_first_word_ms = first_frame_ms + first_word_begin_ms
    result['model_first_word_ms'] = model_first_word_ms

    audio_end_with_offset_ms = end_ms + offset_ms
    result['audio_end_with_offset_ms'] = audio_end_with_offset_ms

    takeover_latency_ms = model_first_word_ms - audio_end_with_offset_ms
    result['takeover_latency_ms'] = takeover_latency_ms
    result['message'] = 'OK'

    logger.info(
        f"[接管时延] first_frame_ms={first_frame_ms} "
        f"first_word_begin_ms={first_word_begin_ms} "
        f"model_first_word_ms={model_first_word_ms} "
        f"end_ms={end_ms} offset_ms={offset_ms} "
        f"audio_end_with_offset_ms={audio_end_with_offset_ms} "
        f"takeover_latency_ms={takeover_latency_ms}ms"
    )
    return result
