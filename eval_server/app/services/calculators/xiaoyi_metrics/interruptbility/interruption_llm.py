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
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

LLM_DEFAULT_TIMEOUT = 120
LLM_DEFAULT_TEMPERATURE = 0.1
LLM_DEFAULT_MAX_TOKENS = 1024


# ─────────── prompt 构建 ───────────
def _fmt_words(words: List[Dict[str, Any]]) -> str:
    """把字词级 ASR chunks 格式化为 "词(start-end) 词2(s-e) ..." 便于 LLM 看文本+时间戳"""
    if not words:
        return ''
    parts = []
    for w in words:
        if not isinstance(w, dict):
            continue
        txt = str(w.get('text', ''))
        ts = w.get('timestamp') or []
        if isinstance(ts, (list, tuple)) and len(ts) >= 2 and ts[0] is not None and ts[1] is not None:
            try:
                parts.append(f'{txt}({round(float(ts[0]), 2)}-{round(float(ts[1]), 2)})')
                continue
            except (TypeError, ValueError):
                pass
        parts.append(txt)
    return ' '.join(parts)


def _build_event_prompt(ev: Dict[str, Any], original_topic: str = '') -> str:
    """单事件复核+打分 prompt

    给 LLM：原始话题 + 用户打断字词级ASR + 模型被打断尾巴字词级ASR + 模型恢复回复字词级ASR
    + 本地时序结论（success/stop_latency/recovery_latency）作参考。
    要求返回：是否真的打断+原因，以及回复三维打分+理由。
    """
    topic_line = original_topic or '（未显式给出，可从对话推断）'
    user_w = _fmt_words(ev.get('user_words')) or ev.get('user_text', '')
    int_w = _fmt_words(ev.get('model_interrupted_words')) or ev.get('model_interrupted_text', '')
    rec_w = _fmt_words(ev.get('model_recovery_words')) or ev.get('model_recovery_text', '')

    return f"""你是语音对话打断处理评估专家。场景：用户在 AI 说话时打断，AI 随后停下并给出恢复回复。
请基于以下【字词级 ASR（词+时间戳，秒）】做两件事：(A) 语义复核这是否是一次"真正的打断"；(B) 对 AI 的恢复回复打分。

【原始话题/上下文】：{topic_line}
【用户打断 字词级ASR】：{user_w}
【模型被打断时正在说的尾巴 字词级ASR】：{int_w}
【模型恢复回复 字词级ASR】：{rec_w}
【本地时序结论(仅供参考，勿直接照搬)】：success={ev.get('success')} stop_latency_s={ev.get('stop_latency_s')} recovery_latency_s={ev.get('recovery_latency_s')}

(A) 是否真的打断（is_real_interruption）：用户确有打断意图并在模型说话期间插入语音、模型也确有让出/恢复响应，
    视为真正的打断；若用户只是应答词("嗯/好")、或并未在模型说话期间插入、或模型全程未被影响，则不算。
    给出布尔结论与简短原因(interruption_reason)。
(B) 对【模型恢复回复】从三维打分（0-5 整数，0 最差、5 最好；参考 Full-Duplex-Bench GPT-4o Score）：
    1. 连贯性(coherence)：回复与被打断尾巴、与打断内容的衔接是否连贯自然。
       0=完全断裂 1=几乎不连贯 2=略有衔接 3=基本连贯 4=连贯自然 5=完美衔接
    2. 相关性(relevance)：回复是否切合用户打断所表达的需求与意图。
       0=完全无关 1=不相关 2=略微相关 3=相关 4=高度相关 5=完全切题
    3. 适应性(adaptability)：模型是否适应了打断带来的话题切换/调整，自然承接而非生硬。
       0=完全未适应 1=未适应 2=略微适应 3=基本适应 4=适应良好 5=完美适应

输出严格 JSON，不要输出 JSON 以外的任何内容：
{{"is_real_interruption": true, "interruption_reason": "", "coherence": 0, "relevance": 0, "adaptability": 0, "overall": 0, "reason": ""}}
其中 overall 为三维平均分（可保留一位小数），reason 为打分简短理由。"""


# ─────────── LLM 调用 ───────────
def _call_llm_json(prompt: str, model: str,
                   max_tokens: int = LLM_DEFAULT_MAX_TOKENS,
                   temperature: float = LLM_DEFAULT_TEMPERATURE) -> Dict[str, Any]:
    """调用 OpenAI 兼容的 LLM，返回 content 文本。

    复用 config.LLM_JUDGE（api_base_url/api_key/timeout）。未配置抛 ValueError。
    """
    from app.config import config

    llm_config = getattr(config, 'LLM_JUDGE', {})
    api_base = llm_config.get('api_base_url', '')
    api_key = llm_config.get('api_key', '')
    timeout = llm_config.get('timeout', LLM_DEFAULT_TIMEOUT)

    if not api_base or not api_key:
        raise ValueError(
            'LLM 评估未配置：请在 eval_server 设置 LLM_JUDGE_API_BASE 与 LLM_JUDGE_API_KEY'
        )

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': 'You are a precise dialog evaluator.'},
            {'role': 'user', 'content': prompt},
        ],
        'max_tokens': max_tokens,
        'temperature': temperature,
        'response_format': {'type': 'json_object'},
    }

    with httpx.Client(trust_env=False, timeout=timeout) as client:
        response = client.post(
            f'{api_base.rstrip("/")}/chat/completions',
            headers=headers,
            json=payload,
        )

    response.raise_for_status()
    data = response.json()
    content = data['choices'][0]['message']['content']
    tokens_used = data.get('usage', {}).get('total_tokens', 0)
    return {'content': content, 'tokens_used': tokens_used}


def _parse_json(content: str) -> Optional[dict]:
    """解析 LLM 输出为 dict。先 json.loads，失败用正则兜底，再失败返回 None。"""
    if not content:
        return None
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        pass
    m = re.search(r'\{.*\}', content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _unwrap_value(val: Any) -> str:
    """解包 {'text': '...'} 格式（与 task_service._unwrap_value 一致）"""
    if isinstance(val, dict) and 'text' in val:
        return val['text']
    return val


def _avg(values: List[float]) -> Optional[float]:
    """取平均，保留 3 位小数；空列表返回 None"""
    values = [v for v in values if isinstance(v, (int, float))]
    if not values:
        return None
    return round(sum(values) / len(values), 3)


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
                              task_params: Dict[str, Any]) -> Dict[str, Any]:
    """打断对话的大模型评估主入口（吃字词级 ASR，语义复核 + 回复打分）

    Args:
        per_event: compute_interruption_metrics 产出的事件列表，每个 interruption 事件
            含 user_text/user_words、model_interrupted_text/words、model_recovery_text/words
            及本地时序结论（success/stop_latency_s/recovery_latency_s）
        task_params: 任务参数，读取 original_topic / llm_model / max_tokens / temperature

    Returns:
        dict: 沿用既有字段结构——
            llm_recovery_per_round: 每事件复核+打分明细（含 is_real_interruption/interruption_reason）
            llm_recovery_avg_coherence/relevance/adaptability: 三维均分
            llm_return_*: 保留字段（空），向后兼容
            llm_eval 内的 interruption_real_rate: LLM 判定真正打断的事件占比
    """
    from app.config import config

    llm_config = getattr(config, 'LLM_JUDGE', {})
    default_model = llm_config.get('default_model', 'gpt-4')
    model = task_params.get('llm_model') or default_model
    max_tokens = int(task_params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS) or LLM_DEFAULT_MAX_TOKENS)
    temperature = float(task_params.get('temperature', LLM_DEFAULT_TEMPERATURE) or LLM_DEFAULT_TEMPERATURE)
    original_topic = _unwrap_value(task_params.get('original_topic', '')) or ''

    # 预检：未配置 API 则整体跳过，避免每事件都重复报错
    if not llm_config.get('api_base_url') or not llm_config.get('api_key'):
        raise ValueError(
            'LLM 评估未配置：请在 eval_server 设置 LLM_JUDGE_API_BASE 与 LLM_JUDGE_API_KEY'
        )

    # 仅对真正发生了 barge-in 的事件做 LLM 评估
    events = [e for e in (per_event or []) if isinstance(e, dict) and e.get('event_type') == 'interruption']

    recovery_per_round: List[Dict[str, Any]] = []
    real_count = 0

    for idx, ev in enumerate(events, 1):
        item: Dict[str, Any] = {
            'event': idx,
            'user_text': ev.get('user_text', ''),
            'model_interrupted_text': ev.get('model_interrupted_text', ''),
            'model_recovery_text': ev.get('model_recovery_text', ''),
            'is_real_interruption': None,
            'interruption_reason': '',
            'coherence': None,
            'relevance': None,
            'adaptability': None,
            'overall': None,
            'reason': '',
            'error': '',
        }
        try:
            prompt = _build_event_prompt(ev, original_topic)
            resp = _call_llm_json(prompt, model, max_tokens, temperature)
            parsed = _parse_json(resp['content']) or {}
            item['is_real_interruption'] = _bool_field(parsed, 'is_real_interruption')
            item['interruption_reason'] = str(parsed.get('interruption_reason', ''))
            item['coherence'] = _score_field(parsed, 'coherence')
            item['relevance'] = _score_field(parsed, 'relevance')
            item['adaptability'] = _score_field(parsed, 'adaptability')
            item['overall'] = _score_field(parsed, 'overall')
            if item['overall'] is None and any(
                item[k] is not None for k in ('coherence', 'relevance', 'adaptability')
            ):
                item['overall'] = _avg([item[k] for k in ('coherence', 'relevance', 'adaptability')])
            item['reason'] = parsed.get('reason', '')
            if item['is_real_interruption'] is True:
                real_count += 1
        except Exception as e:  # 单事件失败不阻断
            item['error'] = str(e)
            logger.warning(f"[interruption_llm] 第 {idx} 事件复核/打分失败: {e}")
        recovery_per_round.append(item)

    # ── 聚合 ──
    n_eval = len(recovery_per_round)
    interruption_real_rate = round(real_count / n_eval, 3) if n_eval else None

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'original_topic': original_topic,
        'llm_recovery_per_round': recovery_per_round,
        # 回到原话题独立打分链路已移除，保留字段为空以兼容既有维度
        'llm_return_scores_per_round': [],
        'llm_recovery_avg_coherence': _avg([r['coherence'] for r in recovery_per_round]),
        'llm_recovery_avg_relevance': _avg([r['relevance'] for r in recovery_per_round]),
        'llm_recovery_avg_adaptability': _avg([r['adaptability'] for r in recovery_per_round]),
        'llm_return_avg_coherence': None,
        'llm_return_avg_relevance': None,
        'llm_return_avg_adaptability': None,
        # LLM 语义复核汇总（折进 llm_eval json，不新增顶层维度字段）
        'interruption_real_rate': interruption_real_rate,
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
