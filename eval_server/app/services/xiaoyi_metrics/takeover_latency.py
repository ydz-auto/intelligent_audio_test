# -*- coding: utf-8 -*-
"""
xiaoyi_takeover_latency.py
计算"小艺接管时延" = 模型回复第一个词时刻 - (音响开始播放时刻 + input首个词偏移 + offset)

公式:
    takeover_latency_ms = model_first_word_ms - (start_ms + t2_ms + offset_ms)
    model_first_word_ms = first_frame_corrected_ms + first_word_begin_ms
    first_frame_corrected_ms = first_frame_ms - first_frame_offset_ms

其中:
    first_frame_ms        : harmony_xiaoyichat.get_results() 返回的 recorder_first_frame_ms
                           (录屏首帧写入的绝对时刻, 毫秒 Unix 时间戳)
    first_frame_offset_ms : 录屏首帧检测时延补偿, 默认 100ms
                           (first_frame_ms 为主机轮询检测到文件 size>0 的时刻,
                            相对首帧真正写入设备时刻系统性偏晚, 扣除该值予以修正)
    first_word_begin_ms   : app.utils.PAUSE_JSON.generate_pause_json() 生成的 ASR JSON 中
                           chunks[0].timestamp[0] * 1000
                           (模型回复第一个词相对 mp4 起点的偏移, 毫秒)
    start_ms              : harmony_xiaoyichat.get_results() 返回的 start_ms
                           (本轮音频播放开始的绝对时刻, 毫秒 Unix 时间戳)
    t2_ms                 : 主服务下发的 input 词级时间戳中最后一个词的 end
                           input[-1].timestamp[-1] * 1000 (秒转毫秒)
    offset_ms             : 时延补偿, 默认 40ms
"""
import os
import json
import logging

logger = logging.getLogger(__name__)

# 音响结束播放时间戳与音频内容最后一个词的时延补偿（毫秒）
DEFAULT_OFFSET_MS = 40

# 录屏首帧检测时延补偿（毫秒）：first_frame_ms 为主机轮询检测到文件 size>0 的时刻，
# 相对首帧真正写入设备时刻系统性偏晚，扣除该默认值予以修正
DEFAULT_FIRST_FRAME_OFFSET_MS = 100


def _extract_t2_ms(input_words):
    """从 input 词级时间戳中提取最后一个词的 end（秒转毫秒）

    Args:
        input_words (list): [{"text": "...", "timestamp": [start, end]}, ...]

    Returns:
        int: 最后一个词的 end 毫秒值；input 为空或缺失时返回 0
    """
    if not input_words:
        return 0
    try:
        last_end_s = input_words[-1].get('timestamp', [0.0, 0.0])[-1]
        if last_end_s is None:
            last_end_s = 0.0
        return int(last_end_s * 1000)
    except (IndexError, TypeError, KeyError):
        return 0


def compute_takeover_latency(first_frame_ms, asr_json_path, start_ms, input_words,
                             offset_ms=DEFAULT_OFFSET_MS,
                             first_frame_offset_ms=DEFAULT_FIRST_FRAME_OFFSET_MS):
    """
    计算小艺接管时延（从 ASR JSON 文件读取）

    公式: takeover_latency_ms = model_first_word_ms - (start_ms + t2_ms + offset_ms)
           model_first_word_ms = (first_frame_ms - first_frame_offset_ms) + first_word_begin_ms

    Args:
        first_frame_ms (int|None): 录屏首帧写入的绝对时刻（毫秒 Unix 时间戳）
        asr_json_path (str): app.utils.PAUSE_JSON.generate_pause_json() 生成的 ASR JSON 文件路径
        start_ms (int|None): 本轮音频播放开始的绝对时刻（毫秒 Unix 时间戳）
        input_words (list): 主服务下发的 input 词级时间戳
                            [{"text": "...", "timestamp": [start, end]}, ...]
        offset_ms (int): 时延补偿, 默认 40ms
        first_frame_offset_ms (int): 录屏首帧检测时延补偿, 默认 100ms

    Returns:
        dict: {
            'takeover_latency_ms': int|None,        接管时延（毫秒）
            'first_frame_ms': int|None,             录屏首帧时刻（原始）
            'first_frame_corrected_ms': int|None,   校正后首帧时刻（扣除检测时延）
            'first_word_begin_ms': int,             ASR 第一个词相对 mp4 起点的偏移（毫秒）
            'model_first_word_ms': int|None,        模型回复第一个词的绝对时刻（毫秒 Unix 时间戳）
            'start_ms': int|None,                   音频播放开始时刻
            't2_ms': int,                           input 首词 start 偏移（毫秒）
            'offset_ms': int,                      时延补偿
            'first_frame_offset_ms': int,           录屏首帧检测时延补偿
            'audio_start_with_offset_ms': int|None, start_ms + t2_ms + offset_ms
            'message': str,                         错误/成功说明
        }
    """
    result = {
        'takeover_latency_ms': None,
        'first_frame_ms': first_frame_ms,
        'first_frame_corrected_ms': None,
        'first_word_begin_ms': 0,
        'model_first_word_ms': None,
        'start_ms': start_ms,
        't2_ms': 0,
        'offset_ms': offset_ms,
        'first_frame_offset_ms': first_frame_offset_ms,
        'audio_start_with_offset_ms': None,
        'message': '',
    }

    # 1. 校验 first_frame_ms
    if first_frame_ms is None:
        result['message'] = 'first_frame_ms 为 None, 无法计算（录屏未启动或未检测到首帧）'
        logger.warning(result['message'])
        return result

    # 2. 校验 start_ms
    if start_ms is None:
        result['message'] = 'start_ms 为 None, 无法计算（未收到音响开始时间戳）'
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

    # 5. 首帧时刻扣除检测时延补偿（first_frame_ms 为主机轮询检测时刻, 偏晚）
    first_frame_corrected_ms = first_frame_ms - first_frame_offset_ms
    result['first_frame_corrected_ms'] = first_frame_corrected_ms

    # 6. 模型回复第一个词的绝对时刻 = 校正后首帧时刻 + ASR 首词偏移
    model_first_word_ms = first_frame_corrected_ms + first_word_begin_ms
    result['model_first_word_ms'] = model_first_word_ms

    # 7. 从 input 中取第一个词的 start 作为 t2（秒转毫秒）
    t2_ms = _extract_t2_ms(input_words)
    result['t2_ms'] = t2_ms

    # 8. 音响开始时刻 + t2 + offset
    audio_start_with_offset_ms = start_ms + t2_ms + offset_ms
    result['audio_start_with_offset_ms'] = audio_start_with_offset_ms

    # 9. 接管时延 = 模型第一词 - (音响开始 + t2 + offset)
    takeover_latency_ms = model_first_word_ms - audio_start_with_offset_ms
    result['takeover_latency_ms'] = takeover_latency_ms
    result['message'] = 'OK'

    logger.info(
        f"[接管时延] first_frame_ms={first_frame_ms} "
        f"first_frame_corrected_ms={first_frame_corrected_ms}(first_frame_offset_ms={first_frame_offset_ms}) "
        f"first_word_begin_ms={first_word_begin_ms} "
        f"model_first_word_ms={model_first_word_ms} "
        f"start_ms={start_ms} t2_ms={t2_ms} offset_ms={offset_ms} "
        f"audio_start_with_offset_ms={audio_start_with_offset_ms} "
        f"takeover_latency_ms={takeover_latency_ms}ms"
    )
    return result


def compute_takeover_latency_from_raw(first_frame_ms, asr_hyp, start_ms, input_words,
                                      offset_ms=DEFAULT_OFFSET_MS,
                                      first_frame_offset_ms=DEFAULT_FIRST_FRAME_OFFSET_MS):
    """
    与 compute_takeover_latency 相同, 但直接传 ASR 结果对象（不读文件）

    Args:
        first_frame_ms: 录屏首帧时刻
        asr_hyp (dict): app.utils.PAUSE_JSON.generate_pause_json() 返回过程中使用的 ASR 结果
                          {text, chunks:[...]}（由 call_modelscope_asr + parse_result 产生）
        start_ms: 音响开始播放时刻
        input_words (list): 主服务下发的 input 词级时间戳
        offset_ms: 时延补偿
        first_frame_offset_ms: 录屏首帧检测时延补偿

    Returns:
        dict: 同 compute_takeover_latency
    """
    result = {
        'takeover_latency_ms': None,
        'first_frame_ms': first_frame_ms,
        'first_frame_corrected_ms': None,
        'first_word_begin_ms': 0,
        'model_first_word_ms': None,
        'start_ms': start_ms,
        't2_ms': 0,
        'offset_ms': offset_ms,
        'first_frame_offset_ms': first_frame_offset_ms,
        'audio_start_with_offset_ms': None,
        'message': '',
    }

    if first_frame_ms is None:
        result['message'] = 'first_frame_ms 为 None, 无法计算'
        return result
    if start_ms is None:
        result['message'] = 'start_ms 为 None, 无法计算'
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

    # 首帧时刻扣除检测时延补偿（first_frame_ms 为主机轮询检测时刻, 偏晚）
    first_frame_corrected_ms = first_frame_ms - first_frame_offset_ms
    result['first_frame_corrected_ms'] = first_frame_corrected_ms

    model_first_word_ms = first_frame_corrected_ms + first_word_begin_ms
    result['model_first_word_ms'] = model_first_word_ms

    t2_ms = _extract_t2_ms(input_words)
    result['t2_ms'] = t2_ms

    audio_start_with_offset_ms = start_ms + t2_ms + offset_ms
    result['audio_start_with_offset_ms'] = audio_start_with_offset_ms

    takeover_latency_ms = model_first_word_ms - audio_start_with_offset_ms
    result['takeover_latency_ms'] = takeover_latency_ms
    result['message'] = 'OK'

    logger.info(
        f"[接管时延] first_frame_ms={first_frame_ms} "
        f"first_frame_corrected_ms={first_frame_corrected_ms}(first_frame_offset_ms={first_frame_offset_ms}) "
        f"first_word_begin_ms={first_word_begin_ms} "
        f"model_first_word_ms={model_first_word_ms} "
        f"start_ms={start_ms} t2_ms={t2_ms} offset_ms={offset_ms} "
        f"audio_start_with_offset_ms={audio_start_with_offset_ms} "
        f"takeover_latency_ms={takeover_latency_ms}ms"
    )
    return result
