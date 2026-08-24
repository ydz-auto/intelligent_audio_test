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
from .false_takeover import compute_false_takeover, compute_false_takeover_llm
from .takeover_latency import compute_takeover_latency_from_raw
from .input_asr import compute_input_asr_match
from .high_freq_turn_taking import compute_high_freq_turn_taking
from .high_freq_llm_judge import evaluate_high_freq_llm
from ..interruptbility.interruption import compute_interruption_metrics
from ..rejection_scene_awareness.non_interactive_latency import compute_non_interactive_latency

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
    统一入口：调一次 ASR，多个维度共享结果

    Args:
        task_params (dict): 包含以下字段
            - user_wav (str|None): 用户语音 wav 路径
            - ai_wav (str|None): 模型语音 wav 路径
            - rounds (list|None): 多轮文本上下文，整体保留传给 high_freq_llm_judge 逐轮处理

    Returns:
        dict: {
            'tor': {...},              接话率结果
            'false_takeover': {...},   误接管率结果
            'takeover_latency': {...}, 接管时延结果
            'interruption': {...},     打断指标结果（无双路 wav 时为空结构）
            'non_interactive_latency': {...}, 非交互意图时延结果（无双路 wav 时为空结构）
            'high_freq_turn_taking': {...},  高频轮换每轮回复时延结果
            'high_freq_llm_judge': {...},    高频轮换 LLM 裁判结果
        }
    """
    import json as _json
    from app.utils.asr_adapator import call_modelscope_asr, parse_result

    logger.info(f"[xiaoyi_metrics] 收到 task_params: {_json.dumps(task_params, ensure_ascii=False, default=str)}")

    # ── 控制台打印收到的关键数据 ──
    _rounds = task_params.get('rounds') or []
    _round0 = _rounds[0] if (isinstance(_rounds, list) and _rounds and isinstance(_rounds[0], dict)) else {}
    _user_wav = task_params.get('user_wav') or _round0.get('user_wav')
    _ai_wav = task_params.get('ai_wav') or _round0.get('ai_wav')
    print(
        "\n==================== xiaoyi_metrics 收到数据 ====================\n"
        f"  用户音频(user_wav)       : {_short(_user_wav)}\n"
        f"  模型音频(ai_wav)         : {_short(_ai_wav)}\n"
        f"  双路音频是否齐全         : {'是 → 将计算打断指标' if (_user_wav and _ai_wav) else '否 → 跳过打断指标'}\n"
        "================================================================"
    )

    results = {}

    # 双路 ASR：user_wav + ai_wav 各调一次
    rounds = task_params.get('rounds', [])
    round0 = rounds[0] if rounds else {}
    user_wav = task_params.get('user_wav') or round0.get('user_wav')
    ai_wav = task_params.get('ai_wav') or round0.get('ai_wav')

    user_chunks = _get_asr_chunks(user_wav) if user_wav else None
    ai_chunks = _get_asr_chunks(ai_wav) if ai_wav else None

    # pause 数据：从 user_wav ASR 结果（用户通道）自动计算停顿区间
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

    # false_takeover LLM 补充判断：时间戳 tor=0 时用 LLM 做语义判断
    _ft_tor = results['false_takeover'].get('tor', 0)
    if _ft_tor == 0 and user_chunks and ai_word_chunks:
        try:
            llm_result = compute_false_takeover_llm(
                user_chunks, ai_word_chunks, pause_intervals, task_params,
            )
            if llm_result is not None:
                results['false_takeover']['llm_eval'] = llm_result
                if llm_result.get('false_takeover', 0) == 1:
                    results['false_takeover']['tor'] = 1
                logger.info(
                    f"[false_takeover_llm] LLM 判定: false_takeover={llm_result.get('false_takeover')} "
                    f"reason={llm_result.get('reason')!r}"
                )
            else:
                results['false_takeover']['llm_eval'] = {'false_takeover': _ft_tor, 'reason': 'LLM未配置或无数据'}
        except Exception as e:
            logger.warning(f"[false_takeover_llm] LLM 评估失败，跳过: {e}")
            results['false_takeover']['llm_eval'] = {'false_takeover': _ft_tor, 'reason': f'LLM评估失败: {e}'}
    elif _ft_tor == 1:
        results['false_takeover']['llm_eval'] = {'false_takeover': 1, 'reason': '时间戳算法已判定抢话'}
    else:
        results['false_takeover']['llm_eval'] = {'false_takeover': 0, 'reason': '无用户或模型ASR数据'}

    # takeover_latency: 使用双路 ASR chunks 计算接管时延
    results['takeover_latency'] = compute_takeover_latency_from_raw(
        first_frame_ms=None,
        asr_hyp=None,
        start_ms=None,
        input_words=[],
        offset_ms=40,
        user_chunks=user_chunks,
        ai_chunks=ai_chunks,
    )
    logger.info(f"[takeover_latency] {_format_takeover_latency(results['takeover_latency'])}")

    # 打断指标：两路 wav（user_wav 用户打断 + ai_wav 模型恢复）各 ASR 一次，共享打断计算
    # model_asr 打断路径改用词级(Paraformer /asr_word)以获更精确停/复时延；
    # 词级 ai_word_chunks 已在上方 false_takeover 抓好，此处复用，不新增 ASR 调用。
    # 词级会把标点作为独立 chunk 输出——compute_interruption_metrics→_to_segments
    # 的 _is_punct_or_empty 已跳过纯标点/空白 chunk，去标点由此生效。
    if user_wav and ai_wav:
        try:
            user_asr = parse_result(call_modelscope_asr(user_wav))
            model_asr = parse_result(call_modelscope_asr(ai_wav))  # 段级，供 non_interactive_latency 用
            # 打断用词级 model ASR；词级为空(ASR 失败)则退化到段级 model_asr
            interrupt_model = ai_word_chunks if ai_word_chunks else model_asr
            results['interruption'] = compute_interruption_metrics(user_asr, interrupt_model)
            _im_chunks = (len(interrupt_model) if isinstance(interrupt_model, list)
                          else len(interrupt_model.get('chunks', [])) if isinstance(interrupt_model, dict)
                          else 0)
            logger.info(
                f"[interruption] 双路 ASR 完成(词级) user_chunks={len(user_asr.get('chunks', []))} "
                f"model_chunks={_im_chunks} "
                f"success_rate={results['interruption'].get('interruption_success_rate')} "
                f"n_events={results['interruption'].get('n_events')} "
                f"avg_stop={results['interruption'].get('avg_stop_latency_s')}s "
                f"avg_recovery={results['interruption'].get('avg_recovery_latency_s')}s "
                f"msg={results['interruption'].get('message')}"
            )
        except Exception as e:
            logger.warning(f"[interruption] 打断指标计算失败，跳过: {e}")
            results['interruption'] = _empty_interruption(f"打断计算失败: {e}")

        # 非交互意图时延：用户在模型回复期间说话的 stop / recovery 时延
        try:
            results['non_interactive_latency'] = compute_non_interactive_latency(user_asr, model_asr)
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

    # 高频轮换：每轮回复时延，复用已算好的双路 ASR chunks
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

    # 高频轮换 LLM 裁判：发送模型回复音频(ai_wav)给多模态 LLM，逐轮判断问答内容是否符合预期
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

    # false_takeover LLM 补充判断：时间戳 tor=0 时用 LLM 做语义判断
    _ft_tor = results['false_takeover'].get('tor', 0)
    if _ft_tor == 0 and user_chunks and ai_word_chunks:
        try:
            llm_result = compute_false_takeover_llm(
                user_chunks, ai_word_chunks, pause_intervals, task_params,
            )
            if llm_result is not None:
                results['false_takeover']['llm_eval'] = llm_result
                if llm_result.get('false_takeover', 0) == 1:
                    results['false_takeover']['tor'] = 1
                logger.info(
                    f"[false_takeover_llm] LLM 判定: false_takeover={llm_result.get('false_takeover')} "
                    f"reason={llm_result.get('reason')!r}"
                )
            else:
                results['false_takeover']['llm_eval'] = {'false_takeover': _ft_tor, 'reason': 'LLM未配置或无数据'}
        except Exception as e:
            logger.warning(f"[false_takeover_llm] LLM 评估失败，跳过: {e}")
            results['false_takeover']['llm_eval'] = {'false_takeover': _ft_tor, 'reason': f'LLM评估失败: {e}'}
    elif _ft_tor == 1:
        results['false_takeover']['llm_eval'] = {'false_takeover': 1, 'reason': '时间戳算法已判定抢话'}
    else:
        results['false_takeover']['llm_eval'] = {'false_takeover': 0, 'reason': '无用户或模型ASR数据'}

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
        """wav → {text, chunks}，调远程 asr_server。

        失败不致命：返回空结构(时序置空)，让后续 LLM 改听音频自己算——
        本地 ASR 仅用于时序 aux 对照，LLM(音频驱动)才是主指标来源，不应被慢/超时的 ASR 阻断。
        """
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
            logger.warning(f"[interruption_metrics] {label} ASR 调用失败 ({wav_path}): {e}；时序置空，LLM 改听音频")
            return {'text': '', 'chunks': []}

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

    # ── 可选：大模型全量评估 ──
    # 触发条件：enable_llm_eval=True 且 task_params 携带 rounds 文本结构
    # 三项主指标(success_rate/stop_latency/recovery_latency)改为 LLM 计算；用户侧用本地 ASR
    # 作参考，AI 侧用字词级 ASR；文本时间戳 + 音频多模态；强调用户会进行 2 轮及以上对话。
    # LLM 失败/未配置：主字段回退时序原值(下方 _timing_* 留底)，不破坏现有行为。
    # multipart 上传时 enable_llm_eval 是字符串('False'/'true')，bool('False')=True 会误判，用白名单
    # 默认开启(未传视为 True)；显式传 false/'false' 才关闭
    enable_llm = task_params.get('enable_llm_eval', True) in (True, 'true', '1', 1)
    rounds = task_params.get('rounds')

    # 留底时序原值，LLM 覆写后作 timing_comparison 对照
    _timing_success_rate = result.get('interruption_success_rate')
    _timing_avg_stop = result.get('avg_stop_latency_s')
    _timing_avg_recov = result.get('avg_recovery_latency_s')

    if enable_llm and rounds:
        try:
            from ..interruptbility.interruption_llm import evaluate_interruption_llm_full
            # ── 逐轮收集：用户 ASR / AI 字词级 ASR / wav ──
            user_asr_ref_pr = []
            ai_word_chunks_pr = []
            ai_wav_pr = []
            user_wav_pr = []
            for idx, rd in enumerate(rounds, 1):
                if not isinstance(rd, dict):
                    user_asr_ref_pr.append(None)
                    ai_word_chunks_pr.append(None)
                    ai_wav_pr.append(None)
                    user_wav_pr.append(None)
                    continue
                r_user_wav = rd.get('user_wav') or (user_wav if idx == 1 else None)
                r_ai_wav = (rd.get('ai_wav') or rd.get('model_wav')
                             or (ai_wav if idx == 1 else None))
                r_user_asr = (rd.get('user_asr') or rd.get('user_chunks')
                              or (user_asr if idx == 1 else None))
                r_model_asr = (rd.get('model_asr') or rd.get('model_chunks')
                               or (model_asr if idx == 1 else None))
                # 用户 ASR：缺则远程段级 ASR（原样传入，不去日文）
                if r_user_asr is None and r_user_wav:
                    r_user_asr = _wav_to_asr(r_user_wav, f'round{idx}_user_wav')
                user_asr_ref_pr.append(r_user_asr)
                # AI 侧参考 ASR(段级, 时间戳准确)；字词级定位由 gemini 听音频自己产出，
                # 不用本地字词级 ASR(其时间戳不可靠)
                ai_wc = None
                if isinstance(r_model_asr, dict) and r_model_asr.get('chunks'):
                    ai_wc = r_model_asr.get('chunks')
                elif r_ai_wav:
                    _seg_asr = _wav_to_asr(r_ai_wav, f'round{idx}_ai_wav')
                    ai_wc = _seg_asr.get('chunks') if isinstance(_seg_asr, dict) else None
                ai_word_chunks_pr.append(ai_wc)
                ai_wav_pr.append(r_ai_wav)
                user_wav_pr.append(r_user_wav)

            llm_result = evaluate_interruption_llm_full(
                rounds, user_asr_ref_pr, ai_word_chunks_pr,
                ai_wav_pr, user_wav_pr, task_params,
            )
            # ── 覆写三项主指标(LLM 产出) ──
            result['interruption_success_rate'] = llm_result.get('interruption_success_rate')
            result['avg_stop_latency_s'] = llm_result.get('avg_stop_latency_s')
            result['avg_recovery_latency_s'] = llm_result.get('avg_recovery_latency_s')
            # ── 平铺 LLM 聚合到顶层(与维度 field_path 对齐) ──
            for k in (
                'llm_recovery_avg_coherence', 'llm_recovery_avg_relevance',
                'llm_recovery_avg_adaptability',
                'llm_recovery_coherence_reason', 'llm_recovery_relevance_reason',
                'llm_recovery_adaptability_reason',
                'llm_interaction_per_round', 'llm_interaction_behavior_summary',
                'llm_recovery_per_round',
            ):
                result[k] = llm_result.get(k)
            # ── aux 结构字段也从 LLM per_round 派生，保持返回值一致 ──
            # 否则 timing 的 n_events/stop_rate/per_event 会与 LLM 主字段(success_rate/latency)矛盾
            _per_round = llm_result.get('per_round') or []
            _int_rds = [r for r in _per_round if r.get('is_interrupted')]
            _n_ev = len(_int_rds)
            _succ_n = sum(1 for r in _int_rds if r.get('success'))
            _rate = round(_succ_n / _n_ev, 3) if _n_ev else 0.0
            result['n_events'] = _n_ev
            result['n_user_segments'] = len(_per_round)
            result['n_recovery_only'] = 0
            result['n_no_model_speech'] = 0
            result['per_event'] = _per_round
            result['stop_rate'] = _rate
            result['resume_rate'] = _rate
            result['message'] = 'OK (LLM)'

            def _seg_overlap(r):
                u = r.get('user_interrupt_segment')
                m = r.get('model_active_segment')
                if not (isinstance(u, (list, tuple)) and isinstance(m, (list, tuple))
                        and len(u) >= 2 and len(m) >= 2):
                    return None
                try:
                    s, e = max(float(u[0]), float(m[0])), min(float(u[1]), float(m[1]))
                    return round(e - s, 3) if e > s else 0.0
                except (TypeError, ValueError):
                    return None

            def _seg_silence(r):
                m = r.get('model_active_segment')
                nx = r.get('model_next_segment')
                if (isinstance(m, (list, tuple)) and isinstance(nx, (list, tuple))
                        and len(m) >= 2 and len(nx) >= 1
                        and m[1] is not None and nx[0] is not None):
                    try:
                        return round(float(nx[0]) - float(m[1]), 3)
                    except (TypeError, ValueError):
                        return None
                return None

            def _mean(vals):
                vals = [v for v in vals if isinstance(v, (int, float))]
                return round(sum(vals) / len(vals), 3) if vals else None

            result['avg_overlap_s'] = _mean([_seg_overlap(r) for r in _int_rds])
            result['avg_silence_gap_s'] = _mean([_seg_silence(r) for r in _int_rds])
            # ── llm_eval：含时序对照 ──
            result['llm_eval'] = {
                'enabled': True,
                'model': llm_result.get('model'),
                'timing_comparison': {
                    'timing_success_rate': _timing_success_rate,
                    'timing_avg_stop_latency_s': _timing_avg_stop,
                    'timing_avg_recovery_latency_s': _timing_avg_recov,
                    'llm_success_rate': llm_result.get('interruption_success_rate'),
                    'llm_avg_stop_latency_s': llm_result.get('avg_stop_latency_s'),
                    'llm_avg_recovery_latency_s': llm_result.get('avg_recovery_latency_s'),
                },
                'per_round': llm_result.get('per_round'),
                'audio_dropped': llm_result.get('audio_dropped'),
                'message': 'OK',
            }
            logger.info(
                f"[interruption_metrics] LLM 全量评估完成 model={llm_result.get('model')} "
                f"n_rounds={len(llm_result.get('per_round') or [])} "
                f"success_rate={result['interruption_success_rate']} "
                f"avg_stop={result['avg_stop_latency_s']}s "
                f"avg_recovery={result['avg_recovery_latency_s']}s "
                f"timing(stop={_timing_avg_stop}s/recov={_timing_avg_recov}s "
                f"success={_timing_success_rate}) "
                f"behavior={llm_result.get('llm_interaction_behavior_summary')} "
                f"audio_dropped={llm_result.get('audio_dropped')}"
            )
        except Exception as e:
            logger.warning(f"[interruption_metrics] LLM 全量评估失败，回退本地时序计算(compute_interruption_metrics): {e}")
            # 本地时序计算作为兜底：三项主字段保持为 compute_interruption_metrics 的时序值
            # (上方未覆写)，llm_eval 标 fallback='timing' 并记所用时序值
            result['llm_eval'] = {
                'enabled': False,
                'fallback': 'timing',
                'message': f'LLM 全量评估失败，已回退本地时序计算: {e}',
                'timing_comparison': {
                    'timing_success_rate': _timing_success_rate,
                    'timing_avg_stop_latency_s': _timing_avg_stop,
                    'timing_avg_recovery_latency_s': _timing_avg_recov,
                },
            }
    else:
        reason = '未启用(enable_llm_eval=False)' if not enable_llm else '无 rounds 文本数据'
        result['llm_eval'] = {'enabled': False, 'message': reason}
        logger.info(f"[interruption_metrics] LLM 评估跳过：{reason}")

    # 包成 {'interruption': <result>}：与 seed field_path 'interruption.X' 前缀约定一致
    # (xiaoyi/turn_taking 同款嵌套约定)；平台 extract_by_path('interruption.X', resp) 才能取到。
    # turn_taking 子维度路径(results['interruption']=本返回)会双层嵌套，但 interruption 维度
    # 走独立 interruption_metrics 任务、不从 turn_taking 提取，故无害。
    return {'interruption': result}


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

    发送【模型回复音频 ai_wav】给多模态 LLM（直接听回复，不过小 ASR），
    结合 rounds 文本上下文（用户提问/预期答案），逐轮判断模型回复是否符合预期，
    返回 pass/fail + reason。

    Args:
        task_params (dict): 包含以下字段
            - ai_wav (str): 模型回复音频路径（主输入，被判定对象）
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

    rounds = task_params.get('rounds') or []
    _r0 = rounds[0] if (isinstance(rounds, list) and rounds and isinstance(rounds[0], dict)) else {}
    # 模型回复音频（主输入）
    ai_wav = task_params.get('ai_wav') or _r0.get('ai_wav') or ''
    scenario_type = task_params.get('scenario_type') or ''
    scenario_rules = task_params.get('scenario_rules') or ''
    model = task_params.get('llm_model') or ''
    max_tokens = int(task_params.get('max_tokens', 4096) or 4096)
    temperature = float(task_params.get('temperature', 0.1) or 0.1)

    print(
        "\n==================== high_freq_llm_judge 收到数据 ====================\n"
        f"  模型回复音频(ai_wav)   : {_short(ai_wav)}\n"
        f"  场景类型(scenario_type): {scenario_type or 'N/A'}\n"
        f"  轮次数(n_rounds)       : {_len_of(rounds)}\n"
        f"  模型(llm_model)        : {model or '(default)'}\n"
        "======================================================================"
    )

    try:
        result = evaluate_high_freq_llm(
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
