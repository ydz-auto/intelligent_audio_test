# -*- coding: utf-8 -*-
"""
turn_taking 包
小艺评估指标统一入口：调一次 ASR，多个维度共享结果

维度:
    - tor (正确回复率)              : tor.compute_tor
    - false_takeover (误接管率)       : false_takeover.compute_false_takeover
    - takeover_latency (接管时延)     : takeover_latency.compute_takeover_latency_from_raw
    - high_freq_turn_taking (高频轮换) : high_freq_turn_taking.compute_high_freq_turn_taking
    - high_freq_llm_judge (高频LLM裁判): high_freq_llm_judge.evaluate_high_freq_llm
"""
import os
import logging
from datetime import datetime, timezone, timedelta

from .tor import compute_tor
from .false_takeover import compute_false_takeover
from .takeover_latency import compute_takeover_latency_from_raw
from .input_asr import compute_input_asr_match
from .high_freq_turn_taking import compute_high_freq_turn_taking
from .high_freq_llm_judge import evaluate_high_freq_llm
from ..interruptbility.interruption import compute_interruption_metrics
from ..rejection_scene_awareness.non_interactive_latency import compute_non_interactive_latency, _compute_from_asr

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
            'non_interactive_latency': {...}, 非交互意图时延结果（无双路 wav 时为空结构）
            'high_freq_turn_taking': {...},  高频轮换每轮回复时延结果
            'high_freq_llm_judge': {...},    高频轮换 LLM 裁判结果
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

    # 2. pause 数据（兼容 JSON 和 Python repr 格式）
    pause_intervals = task_params.get('pause', [])
    if isinstance(pause_intervals, str):
        import ast
        try:
            pause_intervals = _json.loads(pause_intervals)
        except _json.JSONDecodeError:
            try:
                pause_intervals = ast.literal_eval(pause_intervals)
                logger.info(f"[xiaoyi_metrics] pause 非合法JSON，用 ast.literal_eval 解析成功: {pause_intervals}")
            except (ValueError, SyntaxError):
                logger.warning(f"[xiaoyi_metrics] pause 解析失败，使用空列表: {pause_intervals!r}")
                pause_intervals = []

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

    # pause 数据：始终从 user_wav ASR 结果（用户通道）计算停顿区间
    #    detect_pauses 逻辑：相邻 chunk 间隔在 0.2s~3.0s 之间视为停顿
    if user_chunks:
        pause_intervals = []
        for i in range(len(user_chunks) - 1):
            prev_end = user_chunks[i]['timestamp'][1]
            next_start = user_chunks[i + 1]['timestamp'][0]
            gap = next_start - prev_end
            if 0.2 <= gap <= 3.0:
                pause_intervals.append({'text': '[PAUSE]', 'timestamp': [prev_end, next_start]})
        logger.info(f"[xiaoyi_metrics] 从 user_wav ASR 检测到 {len(pause_intervals)} 条停顿: {pause_intervals}")
    else:
        pause_intervals = []
        logger.warning(f"[xiaoyi_metrics] 无 user_chunks，pause 为空")

    # tor: 用户结束说话后模型是否正确开始回复
    results['tor'] = compute_tor(user_chunks=user_chunks or [], ai_chunks=ai_chunks or [])
    logger.info(f"[tor] {results['tor']}")

    # false_takeover: 用 ai_wav + Paraformer 词级 ASR，时间戳裁剪到 pause 区间
    ai_word_chunks = (_get_asr_word_chunks(ai_wav) or []) if ai_wav else []
    logger.info(
        f"[false_takeover] 输入数据: "
        f"pause_intervals({len(pause_intervals)}条)={pause_intervals}, "
        f"ai_word_chunks({len(ai_word_chunks)}个)={ai_word_chunks[:5]}{'...' if len(ai_word_chunks) > 5 else ''}"
    )
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

        # 5. 非交互意图时延：用户在模型回复期间说话的 stop / recovery 时延
        #    复用第 4 步已算好的双路 ASR（避免重复调 ASR 服务）
        try:
            results['non_interactive_latency'] = _compute_from_asr(user_asr, model_asr)
            logger.info(
                f"[non_interactive_latency] stop={results['non_interactive_latency'].get('stop_latency_s')}s "
                f"recovery={results['non_interactive_latency'].get('recovery_latency_s')}s "
                f"silence={results['non_interactive_latency'].get('silence_gap_s')}s "
                f"overlap={results['non_interactive_latency'].get('overlap_s')}s "
                f"msg={results['non_interactive_latency'].get('message')}"
            )
        except Exception as e:
            logger.warning(f"[non_interactive_latency] 计算失败，跳过: {e}")
            results['non_interactive_latency'] = _empty_non_interactive_latency(f"计算失败: {e}")
    else:
        logger.info("[interruption] 无双路音频(user_wav/ai_wav)，跳过打断指标")
        results['interruption'] = _empty_interruption('无双路音频，跳过打断')
        results['non_interactive_latency'] = _empty_non_interactive_latency('无双路音频，跳过')

    # 6. 高频轮换：每轮回复时延（飞花令/成语接龙/快问快答等），复用已算好的双路 ASR chunks
    try:
        _merge_gap = task_params.get('seg_merge_gap_s') or round0.get('seg_merge_gap_s')
        _hf_kwargs = {}
        if _merge_gap is not None:
            _hf_kwargs['seg_merge_gap_s'] = float(_merge_gap)
        results['high_freq_turn_taking'] = compute_high_freq_turn_taking(
            user_chunks=user_chunks or [],
            ai_chunks=ai_chunks or [],
            **_hf_kwargs,
        )
        _print_high_freq_results(results['high_freq_turn_taking'])
        logger.info(
            f"[high_freq_turn_taking] "
            f"n_rounds={results['high_freq_turn_taking'].get('n_rounds')} "
            f"matched={results['high_freq_turn_taking'].get('n_matched_rounds')} "
            f"missed={results['high_freq_turn_taking'].get('n_missed_rounds')} "
            f"avg_latency={results['high_freq_turn_taking'].get('avg_response_latency_s')}s "
            f"msg={results['high_freq_turn_taking'].get('message')}"
        )
    except Exception as e:
        logger.warning(f"[high_freq_turn_taking] 计算失败，跳过: {e}")
        results['high_freq_turn_taking'] = {'n_rounds': 0, 'per_round': [], 'message': f'计算失败: {e}'}

    # 7. 高频轮换 LLM 裁判：传输录屏，逐轮判断问答内容是否符合预期
    try:
        results['high_freq_llm_judge'] = calculate_high_freq_llm_judge(task_params)
    except Exception as e:
        logger.warning(f"[high_freq_llm_judge] 计算失败，跳过: {e}")
        results['high_freq_llm_judge'] = {'enabled': False, 'message': f'计算失败: {e}'}

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

    # pause 数据：兼容顶层 / rounds[0] / JSON / Python repr 字符串
    pause_intervals = task_params.get('pause') or round0.get('pause') or []
    if isinstance(pause_intervals, str):
        import ast
        try:
            pause_intervals = _json.loads(pause_intervals)
        except _json.JSONDecodeError:
            try:
                pause_intervals = ast.literal_eval(pause_intervals)
                logger.info(f"[takeover_metrics] pause 非合法JSON，用 ast.literal_eval 解析成功: {pause_intervals}")
            except (ValueError, SyntaxError):
                logger.warning(f"[takeover_metrics] pause 解析失败，使用空列表: {pause_intervals!r}")
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

    # pause 数据：始终从 user_wav ASR 结果（用户通道）计算停顿区间
    #    detect_pauses 逻辑：相邻 chunk 间隔在 0.2s~3.0s 之间视为停顿
    if user_chunks:
        pause_intervals = []
        for i in range(len(user_chunks) - 1):
            prev_end = user_chunks[i]['timestamp'][1]
            next_start = user_chunks[i + 1]['timestamp'][0]
            gap = next_start - prev_end
            if 0.2 <= gap <= 3.0:
                pause_intervals.append({'text': '[PAUSE]', 'timestamp': [prev_end, next_start]})
        logger.info(f"[takeover_metrics] 从 user_wav ASR 检测到 {len(pause_intervals)} 条停顿: {pause_intervals}")
    else:
        pause_intervals = []
        logger.warning(f"[takeover_metrics] 无 user_chunks，pause 为空")

    # 接话率：用户结束说话后模型是否正确开始回复
    results['tor'] = compute_tor(user_chunks=user_chunks or [], ai_chunks=ai_chunks or [])
    logger.info(f"[tor] {results['tor']}")

    # 误接管率：用 ai_wav 词级时间戳 + pause 区间
    ai_word_chunks = (_get_asr_word_chunks(ai_wav) or []) if ai_wav else []
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
    nil = results.get('non_interactive_latency', {})

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
        f"  6. 非交互意图时延 Non-Interactive Latency\n"
        f"     停止时延 stop_latency_s              : {_x(nil.get('stop_latency_s'))}\n"
        f"     恢复时延 recovery_latency_s          : {_x(nil.get('recovery_latency_s'))}\n"
        f"     静默 silence_gap_s                  : {_x(nil.get('silence_gap_s'))}\n"
        f"     重叠 overlap_s                      : {_x(nil.get('overlap_s'))}\n"
        f"     用户段 user_segment                 : {_x(nil.get('user_segment'))}\n"
        f"     模型回复段 model_active_segment      : {_x(nil.get('model_active_segment'))}\n"
        f"     模型恢复段 model_recovery_segment    : {_x(nil.get('model_recovery_segment'))}\n"
        f"     用户段数 n_user_segments             : {_x(nil.get('n_user_segments'))}\n"
        f"     模型段数 n_model_segments            : {_x(nil.get('n_model_segments'))}\n"
        f"     说明 message                        : {_x(nil.get('message'))}\n"
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


def _empty_non_interactive_latency(message):
    """无双路音频或计算失败时返回的空结构（与 compute_non_interactive_latency 输出键一致）"""
    return {
        'stop_latency_s': None,
        'recovery_latency_s': None,
        'user_segment': None,
        'model_active_segment': None,
        'model_recovery_segment': None,
        'silence_gap_s': None,
        'overlap_s': None,
        'n_user_segments': 0,
        'n_model_segments': 0,
        'message': message,
    }


def calculate_interruption_metrics(task_params):
    """打断指标统一入口：用户流 + 模型恢复流 ASR 词级时间戳，直接算三项指标

    与 calculate_xiaoyi_metrics 不同：本入口只算打断，不计算 tor/false_takeover/takeover_latency。
    支持两种入参形式（优先 wav，向后兼容已对齐 chunks）：
      A. 传两路 wav 路径（user_wav / ai_wav）：内部调远程 asr_server 转成 ASR chunks 再算
         （与 calculate_xiaoyi_metrics 打断段一致），平台 driver 只产 wav，走这条。
      B. 直接传两路已对齐 ASR 结果（user_asr / model_asr，chunks 或 {text, chunks}）：
         不内部调 ASR，适用于调用方已自行对齐的高级用法。

    Args:
        task_params (dict): 包含以下字段
            - user_wav  (str|None): 用户打断语音 wav 路径（走 A 时必填）
            - ai_wav    (str|None): 模型恢复语音 wav 路径（走 A 时必填；别名 model_wav）
            - user_asr  (list|dict|None): 用户提问/打断 ASR（走 B 时必填）
            - model_asr (list|dict|None): 模型恢复 ASR（走 B 时必填）
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
    from app.utils.asr_adapator import call_modelscope_asr, parse_result

    logger.info(f"[interruption_metrics] 收到 task_params: {_json.dumps(task_params, ensure_ascii=False, default=str)}")

    # 兼容参数在顶层或 rounds[0]（body_template 把数据字段放 rounds 里）
    _rounds = task_params.get('rounds') or []
    _r0 = _rounds[0] if (isinstance(_rounds, list) and _rounds and isinstance(_rounds[0], dict)) else {}

    # 优先走 wav：平台 driver 只产 user_wav/ai_wav，由本入口内部调 asr_server 转 chunks
    user_wav = task_params.get('user_wav') or _r0.get('user_wav')
    ai_wav = task_params.get('ai_wav') or task_params.get('model_wav') or _r0.get('ai_wav') or _r0.get('model_wav')

    # 向后兼容：调用方直接传已对齐 ASR 结果
    user_asr = task_params.get('user_asr') or task_params.get('user_chunks') or task_params.get('input_asr') or _r0.get('user_asr') or _r0.get('user_chunks')
    model_asr = task_params.get('model_asr') or task_params.get('model_chunks') or task_params.get('recovery_asr') or _r0.get('model_asr') or _r0.get('model_chunks')

    def _wav_to_asr(wav_path, label):
        """wav → {text, chunks}，调远程 asr_server；失败抛 ValueError 使任务 failed。"""
        if not wav_path:
            return None
        try:
            raw = call_modelscope_asr(wav_path)
            asr_result = parse_result(raw)  # {text, chunks}
            if not asr_result.get('chunks'):
                logger.warning(f"[interruption_metrics] {label} ASR chunks 为空: {wav_path}")
            logger.info(f"[interruption_metrics] {label} ASR 完成 chunks={len(asr_result.get('chunks', []))} wav={wav_path}")
            return asr_result
        except Exception as e:
            raise ValueError(f"interruption_metrics: {label} ASR 调用失败 ({wav_path}): {e}") from e

    # 有 wav 则内部 ASR 转 chunks（不覆盖调用方已传的 asr 结果）
    if user_asr is None and user_wav:
        user_asr = _wav_to_asr(user_wav, 'user_wav')
    if model_asr is None and ai_wav:
        model_asr = _wav_to_asr(ai_wav, 'ai_wav')

    if user_asr is None:
        raise ValueError("interruption_metrics: 缺少 user_wav 或 user_asr（用户提问/打断 wav 或 ASR）")
    if model_asr is None:
        raise ValueError("interruption_metrics: 缺少 ai_wav 或 model_asr（模型恢复 wav 或 ASR）")

    stop_tol = task_params.get('stop_tolerance_s')
    merge_gap = task_params.get('seg_merge_gap_s') or _r0.get('seg_merge_gap_s')

    kwargs = {}
    if stop_tol is not None:
        # 兼容旧入参；当前 success 不再被容差门控，该值仅保留不报错
        logger.info("[interruption_metrics] stop_tolerance_s 已废弃（success 改为让出+恢复），忽略")
    if merge_gap is not None:
        # multipart 上传时标量字段是字符串('0.3')，需转 float；非法值则回退默认
        try:
            gap_val = float(merge_gap)
            # 0.3 太严会拆段，强制最小 0.5
            if gap_val < 0.5:
                logger.info(f"[interruption_metrics] seg_merge_gap_s={gap_val} < 0.5，强制提升到 0.5")
                gap_val = 0.5
            kwargs['seg_merge_gap_s'] = gap_val
        except (TypeError, ValueError):
            logger.warning(f"[interruption_metrics] seg_merge_gap_s 非数值({merge_gap!r})，用默认 0.5")

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
    # multipart 上传时 enable_llm_eval 是字符串('False'/'true')，bool('False')=True 会误判，用白名单
    enable_llm = task_params.get('enable_llm_eval') in (True, 'true', '1', 1)
    rounds = task_params.get('rounds')
    if enable_llm and rounds:
        try:
            from ..interruptbility.interruption_llm import evaluate_interruption_llm
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


def calculate_high_freq_turn_taking_metrics(task_params):
    """高频轮换场景：计算每轮回复时延（飞花令 / 成语接龙 / 快问快答等）

    user_wav 有多段用户讲话，ai_wav 有多段模型回复。
    逐轮匹配用户段与 AI 回复段，计算每轮回复时延 = AI段起点 - 用户段终点。

    Args:
        task_params (dict): 包含以下字段（可通过 rounds[0] 传同等效字段）
            - user_wav (str|None): 用户通道 wav 路径
            - ai_wav   (str|None): AI 回复通道 wav 路径
            - rounds (list): 多轮数据，从中提取上述字段
            - seg_merge_gap_s (float, 可选): 词合并为段的间隙阈值(秒)，默认 0.7

    Returns:
        dict: {
            'n_rounds': int,                      轮数（用户段总数）
            'per_round': list,                    每轮结果
            'avg_response_latency_s': float|None, 平均回复时延（秒）
            'min_response_latency_s': float|None, 最小回复时延（秒）
            'max_response_latency_s': float|None, 最大回复时延（秒）
            'avg_response_latency_ms': float|None, 平均回复时延（毫秒）
            'n_user_segments': int,               用户段总数
            'n_ai_segments': int,                 AI段总数
            'n_matched_rounds': int,              成功匹配的轮数
            'n_missed_rounds': int,               未匹配的轮数
            'n_unmatched_ai_segments': int,       未消费的AI段数
            'message': str,
        }
    """
    import json as _json

    logger.info(f"[high_freq_turn_taking] 收到 task_params: {_json.dumps(task_params, ensure_ascii=False, default=str)}")

    rounds = task_params.get('rounds', [])
    round0 = rounds[0] if (isinstance(rounds, list) and rounds and isinstance(rounds[0], dict)) else {}

    user_wav = task_params.get('user_wav') or round0.get('user_wav')
    ai_wav = task_params.get('ai_wav') or round0.get('ai_wav')
    merge_gap = task_params.get('seg_merge_gap_s') or round0.get('seg_merge_gap_s')

    print(
        "\n==================== high_freq_turn_taking 收到数据 ====================\n"
        f"  用户通道音频(user_wav) : {_short(user_wav)}\n"
        f"  AI回复音频(ai_wav)     : {_short(ai_wav)}\n"
        f"  合并间隙(seg_merge_gap_s): {merge_gap or 0.7}\n"
        "========================================================================"
    )

    kwargs = {}
    if merge_gap is not None:
        kwargs['seg_merge_gap_s'] = float(merge_gap)

    user_chunks = _get_asr_chunks(user_wav) if user_wav else None
    ai_chunks = _get_asr_chunks(ai_wav) if ai_wav else None

    results = compute_high_freq_turn_taking(
        user_chunks=user_chunks or [],
        ai_chunks=ai_chunks or [],
        **kwargs,
    )

    _print_high_freq_results(results)
    return results


def _print_high_freq_results(results):
    """打印高频轮换指标（中英文对照）"""
    def _x(v):
        return v if v is not None else 'None'

    per_round = results.get('per_round', [])

    lines = [
        "\n==================== high_freq_turn_taking 评估结果 / Evaluation Result ====================\n"
        f"  高频轮换 High-Frequency Turn-Taking\n"
        f"     总轮数 n_rounds                    : {_x(results.get('n_rounds'))}\n"
        f"     用户段数 n_user_segments            : {_x(results.get('n_user_segments'))}\n"
        f"     AI段数 n_ai_segments                : {_x(results.get('n_ai_segments'))}\n"
        f"     匹配轮数 n_matched_rounds           : {_x(results.get('n_matched_rounds'))}\n"
        f"     未匹配轮数 n_missed_rounds          : {_x(results.get('n_missed_rounds'))}\n"
        f"     未消费AI段 n_unmatched_ai_segments   : {_x(results.get('n_unmatched_ai_segments'))}\n"
        f"     平均回复时延 avg_latency_ms         : {_x(results.get('avg_response_latency_ms'))}\n"
        f"     最小回复时延 min_latency_s          : {_x(results.get('min_response_latency_s'))}\n"
        f"     最大回复时延 max_latency_s          : {_x(results.get('max_response_latency_s'))}\n"
        f"     说明 message                        : {_x(results.get('message'))}\n"
    ]

    if per_round:
        lines.append("  ── 每轮明细 Per-Round Detail ──\n")
        for rd in per_round:
            us = rd.get('user_segment') or []
            ai = rd.get('ai_segment')
            latency = rd.get('response_latency_ms')
            gap = rd.get('inter_round_gap_s')
            u_text = us[2][:40] if len(us) > 2 else ''
            if ai:
                ai_text = ai[2][:40] if len(ai) > 2 else ''
                lines.append(
                    f"     轮{rd['round_index']}: "
                    f"用户[{us[0]:.2f}-{us[1]:.2f}] '{u_text}' "
                    f"→ AI[{ai[0]:.2f}-{ai[1]:.2f}] '{ai_text}' "
                    f"时延={latency:.0f}ms"
                )
                if gap is not None:
                    lines[-1] += f"  间隔={gap:.2f}s"
            else:
                lines.append(
                    f"     轮{rd['round_index']}: "
                    f"用户[{us[0]:.2f}-{us[1]:.2f}] '{u_text}' "
                    f"→ 未匹配 ({rd.get('message', '')})"
                )

    lines.append("=========================================================================================")
    print(''.join(lines))


def calculate_high_freq_llm_judge(task_params):
    """高频轮换场景 LLM 裁判：以模型回复音频(ai_wav)为主输入，逐轮判断问答内容是否符合预期

    录屏不再可用：改为发送【模型回复音频 ai_wav】给多模态 LLM（直接听回复，不过小 ASR），
    结合 rounds 文本上下文（用户提问/预期答案），逐轮判断模型回复是否符合预期，
    返回 pass/fail + reason。ai_wav 缺失时回退 record_file（legacy 录屏）。

    Args:
        task_params (dict): 包含以下字段
            - ai_wav (str): 模型回复音频路径（主输入，被判定对象）
            - record_file (str): legacy 录屏/音频文件路径（ai_wav 缺失时回退用）
            - rounds (list): 多轮文本数据，每轮 {query, answer, expected_answer}
            - scenario_type (str): 场景类型（飞花令/成语接龙/快问快答/自定义）
            - scenario_rules (str): 自定义场景规则
            - llm_model (str): LLM 模型名，缺省读 config.LLM_JUDGE.default_model
            - max_tokens (int): 最大输出 token，默认 4096
            - temperature (float): 采样温度，默认 0.1

    Returns:
        dict: {
            'enabled': bool,
            'model': str,
            'scenario_type': str,
            'n_rounds': int,
            'per_round': [{round, pass, reason}, ...],
            'overall_pass_rate': float|None,
            'n_passed': int,
            'n_failed': int,
            'summary': str,
            'tokens_used': int,
            'message': str,
        }
    """
    import json as _json

    logger.info(f"[high_freq_llm_judge] 收到 task_params: {_json.dumps(task_params, ensure_ascii=False, default=str)}")

    record_file = task_params.get('record_file') or task_params.get('record_path') or task_params.get('wav_path') or ''
    rounds = task_params.get('rounds') or []
    _r0 = rounds[0] if (isinstance(rounds, list) and rounds and isinstance(rounds[0], dict)) else {}
    # 模型回复音频（主输入）：优先 ai_wav，回退 record_file（legacy 录屏）
    ai_wav = task_params.get('ai_wav') or _r0.get('ai_wav') or ''
    scenario_type = task_params.get('scenario_type') or ''
    scenario_rules = task_params.get('scenario_rules') or ''
    model = task_params.get('llm_model') or ''
    max_tokens = task_params.get('max_tokens', 4096)
    temperature = task_params.get('temperature', 0.1)

    print(
        "\n==================== high_freq_llm_judge 收到数据 ====================\n"
        f"  模型回复音频(ai_wav)   : {_short(ai_wav)}\n"
        f"  录屏文件(record_file)  : {_short(record_file)}\n"
        f"  场景类型(scenario_type): {scenario_type or 'N/A'}\n"
        f"  轮次数(n_rounds)       : {_len_of(rounds)}\n"
        f"  模型(llm_model)        : {model or '(default)'}\n"
        "======================================================================"
    )

    try:
        result = evaluate_high_freq_llm(
            video_path=record_file,
            rounds=rounds,
            scenario_type=scenario_type,
            scenario_rules=scenario_rules,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            ai_wav=ai_wav,
        )
    except Exception as e:
        logger.error(f"[high_freq_llm_judge] 评估失败: {e}")
        result = {
            'enabled': False,
            'model': model,
            'scenario_type': scenario_type,
            'ai_wav': ai_wav,
            'video_path': record_file,
            'n_rounds': _len_of(rounds),
            'per_round': [],
            'message': f'评估失败: {e}',
        }

    _print_high_freq_llm_results(result)
    return result


def _print_high_freq_llm_results(results):
    """打印高频轮换 LLM 裁判结果（中英文对照）"""
    def _x(v):
        return v if v is not None else 'None'

    per_round = results.get('per_round', [])

    lines = [
        "\n==================== high_freq_llm_judge 评估结果 / Evaluation Result ====================\n"
        f"  高频轮换 LLM 裁判 High-Frequency LLM Judge\n"
        f"     模型 model                      : {_x(results.get('model'))}\n"
        f"     场景 scenario_type              : {_x(results.get('scenario_type'))}\n"
        f"     总轮数 n_rounds                 : {_x(results.get('n_rounds'))}\n"
        f"     通过轮数 n_passed                : {_x(results.get('n_passed'))}\n"
        f"     未通过轮数 n_failed             : {_x(results.get('n_failed'))}\n"
        f"     通过率 overall_pass_rate        : {_x(results.get('overall_pass_rate'))}\n"
        f"     tokens (in/out/total)           : {results.get('input_token', 0)}/{results.get('output_token', 0)}/{results.get('tokens_used', 0)}\n"
        f"     说明 message                    : {_x(results.get('message'))}\n"
    ]

    if per_round:
        lines.append("  ── 每轮明细 Per-Round Detail ──\n")
        for rd in per_round:
            status = 'PASS' if rd.get('pass') else 'FAIL'
            lines.append(
                f"     轮{rd['round']} [{status}]\n"
                f"       理由: {rd.get('reason', '')}\n"
            )

    if results.get('summary'):
        lines.append(f"  ── 总结 Summary ──\n     {results['summary']}\n")

    lines.append("==========================================================================================")
    print(''.join(lines))
