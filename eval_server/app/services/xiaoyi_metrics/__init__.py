# -*- coding: utf-8 -*-
"""
xiaoyi_metrics 包
小艺评估指标统一入口：调一次 ASR，三个维度共享结果

维度:
    - tor (正确回复率)       : tor.compute_tor
    - false_takeover (误接管率) : false_takeover.compute_false_takeover
    - takeover_latency (接管时延) : takeover_latency.compute_takeover_latency_from_raw
"""
import os
import logging
from datetime import datetime, timezone, timedelta

from .tor import compute_tor
from .false_takeover import compute_false_takeover
from .takeover_latency import compute_takeover_latency_from_raw
from .input_asr import compute_input_asr_match
from .interruption import compute_interruption_metrics

logger = logging.getLogger(__name__)


def _get_asr_chunks(wav_path):
    """调用远程 ASR 服务获取字词时间戳（user_wav / ai_wav 共用）

    Args:
        wav_path: 本地 wav 文件路径

    Returns:
        list: chunks 列表 [{text, timestamp:[start_s, end_s]}, ...]
        None: ASR 失败或 chunks 为空
    """
    if not wav_path or not os.path.isfile(wav_path):
        logger.error(f"wav 文件不存在: {wav_path}")
        return None

    from app.utils.asr_adapator import call_modelscope_asr, parse_result

    try:
        raw = call_modelscope_asr(wav_path)
        asr_result = parse_result(raw)
        chunks = asr_result.get('chunks', [])
        if not chunks:
            logger.warning(f"ASR chunks 为空: {wav_path}")
            return None
        return chunks
    except Exception as e:
        logger.error(f"ASR 调用失败 {wav_path}: {e}")
        return None


def _get_asr_word_chunks(wav_path):
    """调用远程 ASR 服务的 /asr_word 端点（Paraformer 词级时间戳）

    用于 false_takeover 等需要词级粒度的指标。

    Args:
        wav_path: 本地 wav 文件路径

    Returns:
        list: chunks 列表 [{text, timestamp:[start_s, end_s]}, ...]
        None: ASR 失败或 chunks 为空
    """
    if not wav_path or not os.path.isfile(wav_path):
        logger.error(f"wav 文件不存在: {wav_path}")
        return None

    from app.utils.asr_adapator import call_modelscope_asr_word, parse_result

    try:
        raw = call_modelscope_asr_word(wav_path)
        asr_result = parse_result(raw)
        chunks = asr_result.get('chunks', [])
        if not chunks:
            logger.warning(f"ASR(词级) chunks 为空: {wav_path}")
            return None
        return chunks
    except Exception as e:
        logger.error(f"ASR(词级) 调用失败 {wav_path}: {e}")
        return None

_CST = timezone(timedelta(hours=8))


def _ms_to_utc(ms):
    """毫秒 Unix 时间戳 → 东八区时间字符串"""
    if ms is None:
        return 'N/A'
    return datetime.fromtimestamp(ms / 1000, tz=_CST).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


def _format_takeover_latency(r):
    """格式化 takeover_latency 结果用于日志打印"""
    return (
        f"{{takeover_latency_ms={r.get('takeover_latency_ms')} "
        f"user_last_word_end_ms={r.get('user_last_word_end_ms')} "
        f"ai_first_word_start_ms={r.get('ai_first_word_start_ms')} "
        f"message={r.get('message')}}}"
    )


def _format_input_asr(r):
    """格式化 input_asr 结果用于日志打印"""
    return (
        f"{{match={r.get('match')} "
        f"similarity={r.get('similarity')} "
        f"query_original={r.get('query_original')!r} "
        f"question_original={r.get('question_original')!r} "
        f"query_normalized={r.get('query_normalized')!r} "
        f"question_normalized={r.get('question_normalized')!r} "
        f"threshold={r.get('threshold')} "
        f"message={r.get('message')}}}"
    )


def _short(val, maxlen=80):
    """控制台打印用：路径/长文本截断显示，None 显示为 <空>"""
    if val is None or val == '':
        return '<空>'
    s = str(val)
    return s if len(s) <= maxlen else s[:maxlen] + '...'


def _len_of(val):
    """控制台打印用：list/dict/str 取条数/长度，None 显示为 0"""
    if val is None or val == '':
        return 0
    if isinstance(val, (list, tuple, dict, str)):
        return len(val)
    return 1


def calculate_xiaoyi_metrics(task_params):
    """
    统一入口：调一次 ASR，三个维度共享结果

    Args:
        task_params (dict): 包含以下字段
            - record_file (str): wav 录音文件路径
            - pause (list): 停顿区间数据
            - first_frame_ms (int|None): 录屏首帧时刻
            - start_ms (int|None): 音频开始播放时刻
            - input (list): 主服务下发的 input 词级时间戳
            - offset_ms (int): 时延补偿，默认 40
            - query (str): 参考参数 JSON 中的 query 文本（与 pause 同源）
            - question (str): get_results() 返回的设备识别用户提问文本
            - user_wav (str|None): 用户打断语音 wav 路径（打断指标用；两路 wav 齐全才算）
            - ai_wav (str|None): 模型恢复语音 wav 路径（打断指标用；两路 wav 齐全才算）

    Returns:
        dict: {
            'tor': {...},              接话率结果
            'false_takeover': {...},   误接管率结果
            'takeover_latency': {...}, 接管时延结果
            'input_asr': {...},        输入识别准确率结果
            'interruption': {...},     打断指标结果（无双路 wav 时为空结构）
        }
    """
    import json as _json
    from app.utils.asr_adapator import call_modelscope_asr, parse_result

    logger.info(f"[xiaoyi_metrics] 收到 task_params: {_json.dumps(task_params, ensure_ascii=False, default=str)}")

    # ── 控制台打印收到的关键数据（带中文说明），便于确认 user_wav/ai_wav 等是否送达 ──
    _rounds = task_params.get('rounds') or []
    _round0 = _rounds[0] if (isinstance(_rounds, list) and _rounds and isinstance(_rounds[0], dict)) else {}
    _user_wav = task_params.get('user_wav') or _round0.get('user_wav')
    _ai_wav = task_params.get('ai_wav') or _round0.get('ai_wav')
    _pause_val = task_params.get('pause') or _round0.get('pause')
    _input_val = task_params.get('input') or task_params.get('input_lastword') or _round0.get('input') or _round0.get('input_lastword')
    _first_frame = task_params.get('first_frame_ms') or _round0.get('first_frame_ms')
    _start_ms = task_params.get('start_ms') or _round0.get('start_ms')
    _end_ms = task_params.get('end_ms') or _round0.get('end_ms')
    _offset_ms = task_params.get('offset_ms') or _round0.get('offset_ms')
    _query = task_params.get('query') or _round0.get('query')
    _question = task_params.get('question') or _round0.get('question')
    print(
        "\n==================== xiaoyi_metrics 收到数据 ====================\n"
        f"  录音文件(record_file)        : {_short(task_params.get('record_file') or task_params.get('wav_path'))}\n"
        f"  用户打断音频(user_wav)       : {_short(_user_wav)}\n"
        f"  模型恢复音频(ai_wav)         : {_short(_ai_wav)}\n"
        f"  录屏首帧时刻(first_frame_ms) : {_first_frame}\n"
        f"  音频开始(start_ms) / 结束(end_ms): {_start_ms} / {_end_ms}\n"
        f"  停顿区间(pause)             : {_len_of(_pause_val)} 条\n"
        f"  输入末词(input_lastword)     : {_len_of(_input_val)} 个\n"
        f"  用例问题(query) / 模型识别(question): {(_query or '')!r} / {(_question or '')!r}\n"
        f"  时延补偿(offset_ms)          : {_offset_ms}\n"
        f"  双路音频是否齐全             : {'是 → 将计算打断指标' if (_user_wav and _ai_wav) else '否 → 跳过打断指标'}\n"
        "================================================================"
    )

    wav_path = task_params.get('record_file') or task_params.get('record_path') or task_params.get('wav_path')
    if wav_path:
        # 1. 调一次 ASR，三个维度共享（不写文件，通过返回值传递）
        raw = call_modelscope_asr(wav_path)
        asr_hyp = parse_result(raw)
        chunks = asr_hyp.get("chunks", [])
        logger.info(f"ASR 完成，chunks={len(chunks)}，开始计算三个维度")
    else:
        asr_hyp = {'text': '', 'chunks': []}
        logger.info("record_file 为空，跳过主录音 ASR，takeover_latency 将无法计算")

    # 2. pause 数据
    pause_intervals = task_params.get('pause', [])
    if isinstance(pause_intervals, str):
        pause_intervals = _json.loads(pause_intervals)

    # 3. 三个维度共享 asr_hyp
    results = {}

    # tor / takeover_latency 共用：user_wav + ai_wav 双路 ASR，各调一次
    rounds = task_params.get('rounds', [])
    round0 = rounds[0] if rounds else {}
    input_words = (
        task_params.get('input')
        or task_params.get('input_lastword')
        or round0.get('input')
        or round0.get('input_lastword')
        or []
    )
    user_wav = task_params.get('user_wav') or round0.get('user_wav')
    ai_wav = task_params.get('ai_wav') or round0.get('ai_wav')
    start_ms = task_params.get('start_ms') or round0.get('start_ms')
    offset_ms = task_params.get('offset_ms') or round0.get('offset_ms') or 40

    user_chunks = _get_asr_chunks(user_wav) if user_wav else None
    ai_chunks = _get_asr_chunks(ai_wav) if ai_wav else None

    # tor: 用户结束说话后模型是否正确开始回复
    results['tor'] = compute_tor(user_chunks=user_chunks or [], ai_chunks=ai_chunks or [])
    logger.info(f"[tor] {results['tor']}")

    # false_takeover: 用 ai_wav + Paraformer 词级 ASR，时间戳裁剪到 pause 区间
    ai_word_chunks = _get_asr_word_chunks(ai_wav) if ai_wav else []
    results['false_takeover'] = compute_false_takeover(ai_word_chunks or [], pause_intervals)
    logger.info(f"[false_takeover] {results['false_takeover']}")

    # takeover_latency: 优先使用双路 ASR chunks，回退到旧逻辑
    results['takeover_latency'] = compute_takeover_latency_from_raw(
        first_frame_ms=task_params.get('first_frame_ms'),
        asr_hyp=asr_hyp,
        start_ms=start_ms,
        input_words=input_words,
        offset_ms=offset_ms,
        user_chunks=user_chunks,
        ai_chunks=ai_chunks,
    )
    logger.info(f"[takeover_latency] {_format_takeover_latency(results['takeover_latency'])}")

    # input_asr: 对比参考 query 与设备识别 question
    results['input_asr'] = compute_input_asr_match(
        task_params=task_params,
    )
    logger.info(f"[input_asr] {_format_input_asr(results['input_asr'])}")

    # 4. 打断指标：两路 wav（user_wav 用户打断 + ai_wav 模型恢复）各 ASR 一次，共享打断计算
    #    字段可能放顶层 task_params 或 rounds[0]（取决于 body_template），多级回退取值
    user_wav = task_params.get('user_wav') or round0.get('user_wav')
    ai_wav = task_params.get('ai_wav') or round0.get('ai_wav')
    if user_wav and ai_wav:
        try:
            user_asr = parse_result(call_modelscope_asr(user_wav))   # {text, chunks}
            model_asr = parse_result(call_modelscope_asr(ai_wav))
            results['interruption'] = compute_interruption_metrics(user_asr, model_asr)
            logger.info(
                f"[interruption] 双路 ASR 完成 user_chunks={len(user_asr.get('chunks', []))} "
                f"model_chunks={len(model_asr.get('chunks', []))} "
                f"success_rate={results['interruption'].get('interruption_success_rate')} "
                f"n_events={results['interruption'].get('n_events')} "
                f"avg_stop={results['interruption'].get('avg_stop_latency_s')}s "
                f"avg_recovery={results['interruption'].get('avg_recovery_latency_s')}s "
                f"msg={results['interruption'].get('message')}"
            )
        except Exception as e:
            # 打断失败不阻断 xiaoyi 主指标，记录空结构
            logger.warning(f"[interruption] 打断指标计算失败，跳过: {e}")
            results['interruption'] = _empty_interruption(f"打断计算失败: {e}")
    else:
        logger.info("[interruption] 无双路音频(user_wav/ai_wav)，跳过打断指标")
        results['interruption'] = _empty_interruption('无双路音频，跳过打断')

    # ── 控制台打印最终评估结果（中英文对照），便于直观核对 ──
    _print_results_bilingual(results)

    return results


def calculate_takeover_metrics(task_params):
    """话轮接管维度：计算接话率 + 误接管率 + 接管时延

    与 calculate_xiaoyi_metrics 不同：只计算 tor、false_takeover 和 takeover_latency，
    不执行主录音 ASR、input_asr、interruption。

    Args:
        task_params (dict): 包含以下字段（可通过 rounds[0] 传同等效字段）
            - user_wav (str|None): 用户通道 wav 路径
            - ai_wav   (str|None): AI 回复通道 wav 路径
            - pause    (list|str): 停顿区间数据
            - first_frame_ms (int|None): 录屏首帧时刻（legacy 回退用）
            - start_ms        (int|None): 音频开始播放时刻（legacy 回退用）
            - input / input_lastword (list): 主服务下发的 input 词级时间戳（legacy 回退用）
            - offset_ms (int): 时延补偿，默认 40
            - rounds (list): 多轮数据，从中提取上述字段

    Returns:
        dict: {
            'tor':              {...},  接话率结果
            'false_takeover':   {...},  误接管率结果
            'takeover_latency': {...},  接管时延结果
        }
    """
    import json as _json

    logger.info(f"[takeover_metrics] 收到 task_params: {_json.dumps(task_params, ensure_ascii=False, default=str)}")

    rounds = task_params.get('rounds', [])
    round0 = rounds[0] if (isinstance(rounds, list) and rounds and isinstance(rounds[0], dict)) else {}

    user_wav = task_params.get('user_wav') or round0.get('user_wav')
    ai_wav = task_params.get('ai_wav') or round0.get('ai_wav')
    start_ms = task_params.get('start_ms') or round0.get('start_ms')
    _raw_offset_ms = task_params.get('offset_ms') or round0.get('offset_ms') or 40
    try:
        offset_ms = int(_raw_offset_ms)
    except (TypeError, ValueError):
        offset_ms = 40
    first_frame_ms = task_params.get('first_frame_ms') or round0.get('first_frame_ms')
    input_words = (
        task_params.get('input')
        or task_params.get('input_lastword')
        or round0.get('input')
        or round0.get('input_lastword')
        or []
    )

    # pause 数据：兼容顶层 / rounds[0] / JSON 字符串
    pause_intervals = task_params.get('pause') or round0.get('pause') or []
    if isinstance(pause_intervals, str):
        try:
            pause_intervals = _json.loads(pause_intervals)
        except _json.JSONDecodeError:
            logger.warning(f"[takeover_metrics] pause JSON 解析失败，使用空列表")
            pause_intervals = []
    if pause_intervals is None:
        pause_intervals = []

    print(
        "\n==================== takeover_metrics 收到数据 ====================\n"
        f"  用户通道音频(user_wav) : {_short(user_wav)}\n"
        f"  AI回复音频(ai_wav)     : {_short(ai_wav)}\n"
        f"  停顿区间(pause)        : {_len_of(pause_intervals)} 条\n"
        f"  录屏首帧(first_frame_ms): {first_frame_ms}\n"
        f"  音频开始(start_ms)     : {start_ms}\n"
        f"  时延补偿(offset_ms)    : {offset_ms}\n"
        f"  输入末词(input)        : {_len_of(input_words)} 个\n"
        "================================================================="
    )

    results = {}

    # ── 双路 ASR：字级时间戳（tor / takeover_latency 共用） ──
    user_chunks = _get_asr_chunks(user_wav) if user_wav else None
    ai_chunks = _get_asr_chunks(ai_wav) if ai_wav else None

    # 接话率：用户结束说话后模型是否正确开始回复
    results['tor'] = compute_tor(user_chunks=user_chunks or [], ai_chunks=ai_chunks or [])
    logger.info(f"[tor] {results['tor']}")

    # 误接管率：用 ai_wav 词级时间戳 + pause 区间
    ai_word_chunks = _get_asr_word_chunks(ai_wav) if ai_wav else []
    results['false_takeover'] = compute_false_takeover(ai_word_chunks or [], pause_intervals)
    logger.info(f"[false_takeover] {results['false_takeover']}")

    # 接管时延：优先双路 ASR chunks 直接相减，回退到 legacy 逻辑
    results['takeover_latency'] = compute_takeover_latency_from_raw(
        first_frame_ms=first_frame_ms,
        asr_hyp={'text': '', 'chunks': []},
        start_ms=start_ms,
        input_words=input_words,
        offset_ms=offset_ms,
        user_chunks=user_chunks,
        ai_chunks=ai_chunks,
    )
    logger.info(f"[takeover_latency] {_format_takeover_latency(results['takeover_latency'])}")

    _print_takeover_results(results)

    return results


def _print_takeover_results(results):
    """打印话轮接管三项指标（中英文对照）"""
    def _x(v):
        return v if v is not None else 'None'

    tor = results.get('tor', {})
    ft = results.get('false_takeover', {})
    tl = results.get('takeover_latency', {})

    print(
        "\n==================== takeover_metrics 评估结果 ====================\n"
        f"  1. 接话率 TOR / Turn-Over Rate\n"
        f"     接话率 tor                       : {_x(tor.get('tor'))}\n"
        f"     词数 n_words                     : {_x(tor.get('n_words'))}\n"
        f"     时长 duration(s)                : {_x(tor.get('duration'))}\n"
        f"     命中词 hit_words                 : {tor.get('hit_words')}\n"
        f"     用户末词 user_last_word_end_s    : {_x(tor.get('user_last_word_end_s'))}\n"
        f"     说明 message                     : {_x(tor.get('message'))}\n"
        f"  2. 误接管率 False Takeover\n"
        f"     误接管率 tor                     : {_x(ft.get('tor'))}\n"
        f"     词数 n_words                     : {_x(ft.get('n_words'))}\n"
        f"     时长 duration(s)                : {_x(ft.get('duration'))}\n"
        f"     停顿数 total_pauses              : {_x(ft.get('total_pauses'))}\n"
        f"     命中词 hit_words                 : {ft.get('hit_words')}\n"
        f"     明细 details                     : {ft.get('details')}\n"
        f"  3. 接管时延 Takeover Latency\n"
        f"     接管时延 takeover_latency_ms     : {_x(tl.get('takeover_latency_ms'))}\n"
        f"     用户末词 user_last_word_end_ms   : {_x(tl.get('user_last_word_end_ms'))}\n"
        f"     模型首词 ai_first_word_start_ms  : {_x(tl.get('ai_first_word_start_ms'))}\n"
        f"     说明 message                     : {_x(tl.get('message'))}\n"
        "================================================================="
    )


def _print_results_bilingual(results):
    """把五项指标按中英文打印到控制台，格式与『收到数据』块对齐。"""
    def _x(v):
        return v if v is not None else 'None'

    tor = results.get('tor', {})
    ft = results.get('false_takeover', {})
    tl = results.get('takeover_latency', {})
    ia = results.get('input_asr', {})
    it = results.get('interruption', {})

    print(
        "\n==================== xiaoyi_metrics 评估结果 / Evaluation Result ====================\n"
        f"  1. 接话率 TOR / Turn-Over Rate\n"
        f"     接话率 tor                       : {_x(tor.get('tor'))}\n"
        f"     词数 n_words                     : {_x(tor.get('n_words'))}\n"
        f"     时长 duration(s)                : {_x(tor.get('duration'))}\n"
        f"     命中词 hit_words                 : {tor.get('hit_words')}\n"
        f"     用户末词结束 user_last_word_end_s: {_x(tor.get('user_last_word_end_s'))}\n"
        f"     说明 message                     : {_x(tor.get('message'))}\n"
        f"  2. 误接管率 False Takeover\n"
        f"     误接管率 tor                     : {_x(ft.get('tor'))}\n"
        f"     词数 n_words                     : {_x(ft.get('n_words'))}\n"
        f"     时长 duration(s)                : {_x(ft.get('duration'))}\n"
        f"     停顿数 total_pauses              : {_x(ft.get('total_pauses'))}\n"
        f"     命中词 hit_words                 : {ft.get('hit_words')}\n"
        f"     明细 details                     : {ft.get('details')}\n"
        f"  3. 接管时延 Takeover Latency\n"
        f"     接管时延 takeover_latency_ms     : {_x(tl.get('takeover_latency_ms'))}\n"
        f"     用户末词 user_last_word_end_ms   : {_x(tl.get('user_last_word_end_ms'))}\n"
        f"     模型首词 ai_first_word_start_ms  : {_x(tl.get('ai_first_word_start_ms'))}\n"
        f"     音频起点 start_ms                : {_x(tl.get('start_ms'))}\n"
        f"     时延补偿 offset_ms               : {_x(tl.get('offset_ms'))}\n"
        f"     说明 message                     : {_x(tl.get('message'))}\n"
        f"  4. 输入识别匹配 Input ASR Match\n"
        f"     是否匹配 match                   : {_x(ia.get('match'))}\n"
        f"     相似度 similarity                : {_x(ia.get('similarity'))}\n"
        f"     阈值 threshold                  : {_x(ia.get('threshold'))}\n"
        f"     参考文本 query_original           : {str(ia.get('query_original',''))[:80]}\n"
        f"     设备识别 question_original        : {str(ia.get('question_original',''))[:80]}\n"
        f"     说明 message                     : {_x(ia.get('message'))}\n"
        f"  5. 打断指标 Interruption Metrics\n"
        f"     打断成功率 interruption_success_rate : {_x(it.get('interruption_success_rate'))}\n"
        f"     停下率 stop_rate                      : {_x(it.get('stop_rate'))}\n"
        f"     恢复率 resume_rate                    : {_x(it.get('resume_rate'))}\n"
        f"     平均停下时延 avg_stop_latency_s      : {_x(it.get('avg_stop_latency_s'))}\n"
        f"     平均恢复时延 avg_recovery_latency_s   : {_x(it.get('avg_recovery_latency_s'))}\n"
        f"     平均重叠 avg_overlap_s               : {_x(it.get('avg_overlap_s'))}\n"
        f"     平均静默 avg_silence_gap_s            : {_x(it.get('avg_silence_gap_s'))}\n"
        f"     事件数 n_events                       : {_x(it.get('n_events'))}\n"
        f"     用户段数 n_user_segments              : {_x(it.get('n_user_segments'))}\n"
        f"     仅恢复 n_recovery_only                : {_x(it.get('n_recovery_only'))}\n"
        f"     无模型语音 n_no_model_speech          : {_x(it.get('n_no_model_speech'))}\n"
        f"     明细 per_event                        : {it.get('per_event')}\n"
        f"     说明 message                          : {_x(it.get('message'))}\n"
        "===================================================================================="
    )


def _empty_interruption(message):
    """无双路音频或计算失败时返回的空打断结构（与 compute_interruption_metrics 输出键一致）"""
    return {
        'interruption_success_rate': 0.0,
        'stop_rate': 0.0,
        'resume_rate': 0.0,
        'avg_stop_latency_s': None,
        'avg_recovery_latency_s': None,
        'avg_overlap_s': None,
        'avg_silence_gap_s': None,
        'n_events': 0,
        'n_user_segments': 0,
        'n_recovery_only': 0,
        'n_no_model_speech': 0,
        'per_event': [],
        'message': message,
        'llm_eval': {'enabled': False, 'message': '未启用 LLM 评估'},
    }


def calculate_interruption_metrics(task_params):
    """打断指标统一入口：用户流 + 模型恢复流 ASR 词级时间戳，直接算三项指标

    与 calculate_xiaoyi_metrics 不同：不内部调 ASR，由调用方直接传两路已对齐的 ASR 结果。

    Args:
        task_params (dict): 包含以下字段
            - user_asr  (list|dict): 用户提问/打断 ASR（chunks 或 {text, chunks}）
            - model_asr (list|dict): 模型恢复 ASR（同上，与 user_asr 等长、同一时间轴）
            - seg_merge_gap_s  (float, 可选): 词合并为段的间隙阈值(秒)，默认 0.3

    Returns:
        dict: {
            'interruption_success_rate': float, 打断成功率
            'stop_rate': float,                 停下率
            'resume_rate': float,               恢复率
            'avg_stop_latency_s': float|None,   平均打断检查时延(秒)
            'avg_recovery_latency_s': float|None, 平均打断恢复时延(秒)
            'avg_overlap_s': float|None,        平均双方同时说话时长(秒)
            'avg_silence_gap_s': float|None,    平均静默时长(秒)
            'n_events': int, 'n_user_segments': int,
            'n_recovery_only': int, 'n_no_model_speech': int,
            'per_event': list, 'message': str,
        }
    """
    import json as _json

    logger.info(f"[interruption_metrics] 收到 task_params: {_json.dumps(task_params, ensure_ascii=False, default=str)}")

    user_asr = task_params.get('user_asr') or task_params.get('user_chunks') or task_params.get('input_asr')
    model_asr = task_params.get('model_asr') or task_params.get('model_chunks') or task_params.get('recovery_asr')

    if user_asr is None:
        raise ValueError("interruption_metrics: 缺少 user_asr（用户提问/打断 ASR）")
    if model_asr is None:
        raise ValueError("interruption_metrics: 缺少 model_asr（模型恢复 ASR）")

    stop_tol = task_params.get('stop_tolerance_s')
    merge_gap = task_params.get('seg_merge_gap_s')

    kwargs = {}
    if stop_tol is not None:
        # 兼容旧入参；当前 success 不再被容差门控，该值仅保留不报错
        logger.info("[interruption_metrics] stop_tolerance_s 已废弃（success 改为让出+恢复），忽略")
    if merge_gap is not None:
        kwargs['seg_merge_gap_s'] = merge_gap

    result = compute_interruption_metrics(user_asr, model_asr, **kwargs)
    logger.info(
        f"[interruption_metrics] success_rate={result['interruption_success_rate']} "
        f"stop_rate={result['stop_rate']} resume_rate={result['resume_rate']} "
        f"avg_stop={result['avg_stop_latency_s']}s avg_recovery={result['avg_recovery_latency_s']}s "
        f"message={result['message']}"
    )

    # ── 可选：大模型评估（打断后回复打分 / 回到原话题行为判断 / 回到原话题回复打分）──
    # 触发条件：enable_llm_eval=True 且 task_params 携带 rounds 文本结构
    # 未配置 LLM_JUDGE_API_KEY 或评估异常时跳过，不影响时序指标
    enable_llm = bool(task_params.get('enable_llm_eval'))
    rounds = task_params.get('rounds')
    if enable_llm and rounds:
        try:
            from .interruption_llm import evaluate_interruption_llm
            llm_result = evaluate_interruption_llm(rounds, task_params)
            result['llm_eval'] = llm_result
            # 顶层平铺关键聚合值，便于维度参数直接按 field_path 取值
            for k in (
                'llm_recovery_avg_coherence', 'llm_recovery_avg_relevance',
                'llm_recovery_avg_adaptability', 'llm_return_behavior_summary',
                'llm_return_avg_coherence', 'llm_return_avg_relevance',
                'llm_return_avg_adaptability', 'llm_recovery_per_round',
                'llm_return_per_round', 'llm_return_scores_per_round',
            ):
                result[k] = llm_result.get(k)
            logger.info(
                f"[interruption_metrics] LLM 评估完成 model={llm_result.get('model')} "
                f"n_rounds={len(llm_result.get('llm_recovery_per_round') or [])} "
                f"n_return={len(llm_result.get('llm_return_per_round') or [])} "
                f"behavior={llm_result.get('llm_return_behavior_summary')}"
            )
        except Exception as e:
            logger.warning(f"[interruption_metrics] LLM 评估失败，跳过: {e}")
            result['llm_eval'] = {'enabled': False, 'message': f'LLM 评估失败: {e}'}
    else:
        reason = '未启用(enable_llm_eval=False)' if not enable_llm else '无 rounds 文本数据'
        result['llm_eval'] = {'enabled': False, 'message': reason}
        logger.info(f"[interruption_metrics] LLM 评估跳过：{reason}")

    return result
