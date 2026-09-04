# -*- coding: utf-8 -*-
"""
interruption_llm.py
打断指标的大模型评估（吃字词级 ASR，做语义复核 + 回复打分）

在 calculate_interruption_metrics 算完本地时序指标后，对每个打断事件做两件事：
    1. 是否真的打断（is_real_interruption）：基于用户与模型两侧的字词级 ASR（词+时间戳）
       做语义复核，给出布尔结论与简短原因。这是对本地时序结论的语义复核，
       不回写覆盖本地 interruption_success_rate——本地数值始终是唯一权威。
    2. AI 回复内容打分：对模型恢复回复，按 连贯性/相关性/适应性 打 0-5 分
       （对标 Full-Duplex-Bench 论文 GPT-4o Score：coherence/relevance/adaptability，0~5）

数据来源：调用方传入的 per_event（来自 compute_interruption_metrics，已富集字词级 ASR），
每个 interruption 事件含 user_text/user_words、model_interrupted_text/words、
model_recovery_text/words 及本地时序结论（success/stop_latency/recovery_latency）。
即 LLM 直接吃用户和模型的字词级 ASR 结果，不再依赖与 ASR 解耦的 rounds 文本。

设计原则：
    - 数值指标（时延/成功率/让出率/恢复率等）全部本地算，本模块不产出任何数值指标
    - 单事件调用失败不阻断其他事件（记 error 字段，不计入均值）
    - LLM 输出严格 JSON；先 json.loads，失败用正则兜底，再失败置 error
    - 返回字段沿用既有结构（llm_recovery_avg_* / llm_recovery_per_round / llm_return_* / llm_eval），
      is_real_interruption/interruption_reason 折进 llm_recovery_per_round 每项与 llm_eval，
      不新增顶层维度字段
"""
import json
import logging
from typing import Any, Dict, List, Optional

from app.services.calculators.base import BaseCalculator
from app.services.calculators.xiaoyi_metrics.shared.llm_client import (
    call_llm,
    parse_json,
    get_llm_config,
    resolve_model,
)
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)


# ─────────── prompt 构建 ───────────
def _fmt_ts(t: Any) -> str:
    """秒 → 2 位小数字符串"""
    try:
        return f'{float(t):.2f}'
    except (TypeError, ValueError):
        return '?'


def _words_range(words: List[Dict[str, Any]]) -> Optional[List[float]]:
    """从字词级 chunks 取 [start, end] 范围；无有效时间戳返回 None"""
    starts: List[float] = []
    ends: List[float] = []
    for w in words or []:
        if not isinstance(w, dict):
            continue
        ts = w.get('timestamp') or []
        if isinstance(ts, (list, tuple)) and len(ts) >= 2 and ts[0] is not None and ts[1] is not None:
            try:
                starts.append(float(ts[0]))
                ends.append(float(ts[1]))
            except (TypeError, ValueError):
                pass
    if not starts:
        return None
    return [min(starts), max(ends)]


def _seg_overlap(s: Dict[str, Any], rng: Any) -> bool:
    """段 s 与区间 rng=[a,b] 是否重叠（边界相接不算）"""
    try:
        ss = float(s.get('start'))
        se_ = float(s.get('end'))
        a = float(rng[0])
        b = float(rng[1])
    except (TypeError, ValueError):
        return False
    return max(ss, a) < min(se_, b) - 1e-6


def _fmt_segments(segs: List[Dict[str, Any]], label: str,
                  marks: Optional[Dict[int, str]] = None) -> str:
    """把语音段列表格式化成时间线文本。

    segs: [{start, end, text, words}, ...] —— 用整段 text（不再拆到字词级，太长）
    label: 角色标签（'用户'/'AI'）
    marks: {段索引: 标注文本}，在对应行尾追加 '  ← 标注'，用于高亮本事件相关段
    """
    if not segs:
        return f'  （无 {label} 语音）'
    lines = []
    for i, s in enumerate(segs):
        if not isinstance(s, dict):
            continue
        ts = f'[{_fmt_ts(s.get("start"))}-{_fmt_ts(s.get("end"))}]'
        txt = str(s.get('text', '')).strip()
        mark = (marks or {}).get(i)
        mark_str = f'  ← {mark}' if mark else ''
        lines.append(f'  {ts} {label}: {txt}{mark_str}')
    return '\n'.join(lines)


def _build_event_prompt(ev: Dict[str, Any], original_topic: str = '',
                        user_segs: Optional[List[Dict[str, Any]]] = None,
                        model_segs: Optional[List[Dict[str, Any]]] = None) -> str:
    """单事件复核+打分 prompt（喂两路完整时间线）

    给 LLM：原始话题 + 用户侧完整时间线 + 模型侧完整时间线（标注本事件相关段）
    + 本地时序结论作参考。要求返回：是否真的打断+原因、success（只要 AI 停下）
    +原因、回复三维打分+理由。严格区分角色：仅"用户打断"是人类输入；
    模型侧时间线都是 AI(语音助手)的话。
    """
    topic_line = original_topic or '（未显式给出，可从对话推断）'
    user_segs = user_segs or []
    model_segs = model_segs or []

    # ── 标注本事件相关段，便于 LLM 在完整时间线里定位 ──
    # 用户打断段：ev['user_segment'] = [u_s, u_e]
    user_marks: Dict[int, str] = {}
    u_seg = ev.get('user_segment')
    if isinstance(u_seg, (list, tuple)) and len(u_seg) >= 2 and u_seg[0] is not None and u_seg[1] is not None:
        for i, s in enumerate(user_segs):
            if _seg_overlap(s, [u_seg[0], u_seg[1]]):
                user_marks[i] = '本事件打断段'
    # 模型被打断段 m_active / 恢复段 m_next：从 ev 的字词级 words 取范围匹配
    model_marks: Dict[int, str] = {}
    m_int_range = _words_range(ev.get('model_interrupted_words'))
    m_rec_range = _words_range(ev.get('model_recovery_words'))
    if m_int_range:
        for i, s in enumerate(model_segs):
            if _seg_overlap(s, m_int_range):
                model_marks[i] = '被打断段(本事件)'
    if m_rec_range:
        for i, s in enumerate(model_segs):
            if i in model_marks:
                continue
            if _seg_overlap(s, m_rec_range):
                model_marks[i] = '恢复段(本事件)'

    user_tl = _fmt_segments(user_segs, '用户', user_marks)
    model_tl = _fmt_segments(model_segs, 'AI', model_marks)

    return f"""你是语音对话打断处理评估专家。请严格区分两个角色：
- 用户(人类)：打断者，在 AI 说话时插入语音。
- AI(语音助手，被评估对象)：被打断后停下，可能给出恢复回复。
【重要·角色区分】下方【用户侧完整时间线】是人类说的话；【模型侧完整时间线】都是 AI(语音助手)说的话，**不是用户输入**，切勿把 AI 的话当成用户说的。

【原始话题/上下文】：{topic_line}
【用户侧完整时间线(人类)】：
{user_tl}
【模型侧完整时间线(AI)】：
{model_tl}
【本事件本地时序结论(仅供参考，勿照搬)】：user_interrupt_segment={ev.get('user_segment')} success={ev.get('success')} stop_latency_ms={ev.get('stop_latency_s')} recovery_latency_ms={ev.get('recovery_latency_s')}

(A) is_real_interruption：是否真的打断(用户确有打断意图且在 AI 说话期间插入、AI 确有让出/停下)。给布尔+简短 interruption_reason。
    若用户只是应答词("嗯/好")、或未在 AI 说话期间插入、或 AI 全程未被影响，则不算。
(B) success：模型是否【成功处理了打断】= 只要 AI 在被打断后**停止了输出(停下来)**即算成功，不要求是否恢复、也不看恢复回复质量。
    成功 = AI 在用户打断后停下了当前输出(让出)；
    失败 = AI 无视打断说穿(继续把原来的话说完，未停下)。
    给布尔 + 简短 success_reason(只解释为何停下/说穿)。
    注意：success 与下方(C)三维打分相互独立——即使 AI 未给恢复回复(三维为0)，只要停下了，success 仍为 true。
(C) 对【模型恢复回复】(AI 的话，非用户输入) 三维打分(0-5 整数，0 最差、5 最好；参考 Full-Duplex-Bench GPT-4o Score)，
    每维各给一个简短理由(只解释该维为何这个分)；若模型未给恢复回复(停下后没恢复)，三维均给 0，但不影响(B)的 success：
    1. coherence(连贯性)：回复与被打断尾巴、与打断内容的衔接是否连贯自然。
       0=完全断裂 1=几乎不连贯 2=略有衔接 3=基本连贯 4=连贯自然 5=完美衔接
    2. relevance(相关性)：回复是否切合用户打断所表达的需求与意图。
       0=完全无关 1=不相关 2=略微相关 3=相关 4=高度相关 5=完全切题
    3. adaptability(适应性)：AI 是否适应了打断带来的话题切换/调整，自然承接而非生硬。
       0=完全未适应 1=未适应 2=略微适应 3=基本适应 4=适应良好 5=完美适应

输出严格 JSON，不要输出 JSON 以外的任何内容，且必须只含下列键：
{{"is_real_interruption": true, "interruption_reason": "", "success": true, "success_reason": "", "coherence": 0, "relevance": 0, "adaptability": 0, "overall": 0, "coherence_reason": "", "relevance_reason": "", "adaptability_reason": ""}}
其中 overall 为三维平均分(保留一位小数)；coherence_reason/relevance_reason/adaptability_reason 分别是对应维度的简短打分理由。"""


# ─────────── LLM 调用 ───────────

# _unwrap_value / _avg 由 BaseCalculator 统一提供


def _score_field(parsed: dict, key: str) -> Optional[float]:
    """从 parsed 中取数值分；非数值返回 None"""
    v = parsed.get(key)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except (ValueError, TypeError):
            return None
    return None


def _bool_field(parsed: dict, key: str) -> Optional[bool]:
    """从 parsed 中取布尔；无法判定返回 None"""
    v = parsed.get(key)
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ('true', '1', 'yes', '是', '真正打断', '真正')
    return None


# ─────────── 主入口 ───────────
def evaluate_interruption_llm(per_event: List[Dict[str, Any]],
                              task_params: Dict[str, Any],
                              user_segments: Optional[List[Dict[str, Any]]] = None,
                              model_segments: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """打断对话的大模型评估主入口（吃两路完整时间线，语义复核 + 回复打分）

    Args:
        per_event: compute_interruption_metrics 产出的事件列表，每个 interruption 事件
            含 user_text/user_words、model_interrupted_text/words、model_recovery_text/words
            及本地时序结论（success/stop_latency_s/recovery_latency_s）
        task_params: 任务参数，读取 original_topic / llm_model / max_tokens / temperature
        user_segments: 用户侧完整语音段时间线（compute_interruption_metrics 导出，含 words）
        model_segments: 模型侧完整语音段时间线（同上）
        task_params: 任务参数，读取 original_topic / llm_model / max_tokens / temperature

    Returns:
        dict: 沿用既有字段结构——
            llm_recovery_per_round: 每事件复核+打分明细（含 is_real_interruption/interruption_reason）
            llm_recovery_avg_coherence/relevance/adaptability: 三维均分
            llm_return_*: 保留字段（空），向后兼容
            llm_eval 内的 interruption_real_rate: LLM 判定真正打断的事件占比
    """
    llm_config = get_llm_config()
    model = task_params.get('llm_model') or resolve_model(dimension='interruption_llm')
    max_tokens = int(task_params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS) or LLM_DEFAULT_MAX_TOKENS)
    temperature = float(task_params.get('temperature', LLM_DEFAULT_TEMPERATURE) or LLM_DEFAULT_TEMPERATURE)
    original_topic = BaseCalculator._unwrap_value(task_params.get('original_topic', '')) or ''

    # 预检：未配置 API 则整体跳过，避免每事件都重复报错
    if not llm_config.get('api_base_url') or not llm_config.get('api_key'):
        raise ValueError(
            'LLM 评估未配置：请在 eval_server 设置 LLM_JUDGE_API_BASE 与 LLM_JUDGE_API_KEY'
        )

    # 仅对真正发生了 barge-in 的事件做 LLM 评估
    events = [e for e in (per_event or []) if isinstance(e, dict) and e.get('event_type') == 'interruption']

    recovery_per_round: List[Dict[str, Any]] = []
    real_count = 0
    success_count = 0

    for idx, ev in enumerate(events, 1):
        item: Dict[str, Any] = {
            'event': idx,
            'user_text': ev.get('user_text', ''),
            'model_interrupted_text': ev.get('model_interrupted_text', ''),
            'model_recovery_text': ev.get('model_recovery_text', ''),
            'is_real_interruption': None,
            'interruption_reason': '',
            'success': None,
            'success_reason': '',
            'coherence': None,
            'relevance': None,
            'adaptability': None,
            'overall': None,
            'coherence_reason': '',
            'relevance_reason': '',
            'adaptability_reason': '',
            'error': '',
        }
        try:
            prompt = _build_event_prompt(ev, original_topic, user_segments, model_segments)
            response = call_llm(
                model=model,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                system_message='You are a precise dialog evaluator.',
            )
            parsed = parse_json(response['content']) or {}
            item['is_real_interruption'] = _bool_field(parsed, 'is_real_interruption')
            item['interruption_reason'] = str(parsed.get('interruption_reason', ''))
            item['success'] = _bool_field(parsed, 'success')
            item['success_reason'] = str(parsed.get('success_reason', ''))
            item['coherence'] = _score_field(parsed, 'coherence')
            item['relevance'] = _score_field(parsed, 'relevance')
            item['adaptability'] = _score_field(parsed, 'adaptability')
            item['overall'] = _score_field(parsed, 'overall')
            if item['overall'] is None and any(
                item[k] is not None for k in ('coherence', 'relevance', 'adaptability')
            ):
                item['overall'] = BaseCalculator._avg([item[k] for k in ('coherence', 'relevance', 'adaptability')])
            item['coherence_reason'] = str(parsed.get('coherence_reason', ''))
            item['relevance_reason'] = str(parsed.get('relevance_reason', ''))
            item['adaptability_reason'] = str(parsed.get('adaptability_reason', ''))
            if item['is_real_interruption'] is True:
                real_count += 1
            if item['success'] is True:
                success_count += 1
        except Exception as e:  # 单事件失败不阻断
            item['error'] = str(e)
            logger.warning(f"[interruption_llm] 第 {idx} 事件复核/打分失败: {e}")
        recovery_per_round.append(item)

    # ── 聚合 ──
    n_eval = len(recovery_per_round)
    interruption_real_rate = round(real_count / n_eval, 3) if n_eval else None
    # LLM 语义判定的打断成功率(成功事件 / 已评估事件)，由 orchestrator 覆盖本地 interruption_success_rate
    llm_success_rate = round(success_count / n_eval, 3) if n_eval else None

    def _join_reasons(key: str) -> str:
        """把各事件的某维分项理由拼接成单段文本(用'；'连接)，供 seed 的 *_reason field_path 取值"""
        parts = [r.get(key, '') for r in recovery_per_round if r.get(key)]
        return '；'.join(parts)

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'original_topic': original_topic,
        'llm_recovery_per_round': recovery_per_round,
        # 回到原话题独立打分链路已移除，保留字段为空以兼容既有维度
        'llm_return_scores_per_round': [],
        'llm_recovery_avg_coherence': BaseCalculator._avg([r['coherence'] for r in recovery_per_round]),
        'llm_recovery_avg_relevance': BaseCalculator._avg([r['relevance'] for r in recovery_per_round]),
        'llm_recovery_avg_adaptability': BaseCalculator._avg([r['adaptability'] for r in recovery_per_round]),
        # 三维分项理由(拼接各事件)，对应 seed 的 llm_recovery_*_reason field_path
        'llm_recovery_coherence_reason': _join_reasons('coherence_reason'),
        'llm_recovery_relevance_reason': _join_reasons('relevance_reason'),
        'llm_recovery_adaptability_reason': _join_reasons('adaptability_reason'),
        'llm_return_avg_coherence': None,
        'llm_return_avg_relevance': None,
        'llm_return_avg_adaptability': None,
        # LLM 语义判定：是否真的打断占比 + 成功率(成功事件/已评估事件)
        'interruption_real_rate': interruption_real_rate,
        'llm_success_rate': llm_success_rate,
        'n_events_evaluated': n_eval,
        'message': 'OK',
    }

    logger.info(
        f"[interruption_llm] model={model} n_events_evaluated={n_eval} "
        f"interruption_real_rate={interruption_real_rate} "
        f"recovery_avg_coherence={result['llm_recovery_avg_coherence']} "
        f"recovery_avg_relevance={result['llm_recovery_avg_relevance']} "
        f"recovery_avg_adaptability={result['llm_recovery_avg_adaptability']}"
    )
    return result
