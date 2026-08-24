# -*- coding: utf-8 -*-
"""
interruption_llm.py
打断指标的可选大模型评估

在 calculate_interruption_metrics 算完时序指标后，对多轮打断对话的"回复内容/回到原话题行为"做语义级评估。
仅在 enable_llm_eval=True 且配置了 LLM_JUDGE_API_KEY 时触发，否则由调用方跳过本模块。

三类评估（均由本模块发请求，复用 eval_server/app/config.py 的 config.LLM_JUDGE 配置）：
    1. 打断后回复打分     : 对每轮打断后模型回复，按 连贯性/相关性/适应性 打 0-5 分
                           （对标 Full-Duplex-Bench 论文 GPT-4o Score：coherence/relevance/adaptability，0~5）
    2. 回到原话题行为判断 : 回到原话题是独立于打断处理的另一维度（仅 is_return_to_topic 轮）。
                           5 类行为：回应 / 恢复 / 询问 / 无关回复 / 沉默或无视
                           （与 env_judge.interruption_judge 同一量表，聚焦是否回到原话题）
    3. 回到原话题回复打分 : 对回到原话题后的模型回复，按 连贯性/相关性/适应性 打 0-5 分
    4. 交互过程行为判断   : 每轮判断模型收到用户"指令语言"后的回复行为（5 类，同上量表），
                           适用于所有打断用例的每一轮（停止指令/连续打断/上下文恢复）

数据来源：调用方传入的 rounds 文本结构（与 ASR 时戳解耦），每轮：
    {query: 用户本轮打断/请求文本, answer: 模型本轮回复文本,
     is_return_to_topic: bool（用例打标，缺省 False）}
顶层可选 original_topic（原始话题文本，供 2/3 使用）。

设计原则：
    - 单轮调用失败不阻断其他轮（记 error 字段，不计入均值）
    - LLM 输出严格 JSON；先 json.loads，失败用正则兜底，再失败置 error
"""
import json
import logging
import os
import re
import struct
import tempfile
import wave
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

LLM_DEFAULT_TIMEOUT = 120
LLM_DEFAULT_TEMPERATURE = 0.1
LLM_DEFAULT_MAX_TOKENS = 1024

# 行为分类的合法取值（5 类，与 env_judge.interruption_judge 对齐）
# 回应=直接回复用户指令/回到原话题请求；恢复=未明确回应但自然续上原话题/交互主线；
# 询问=追问澄清确认；无关回复=有回复但与意图无关(含说穿/未停/恢复失败)；沉默或无视=无有效回复/无视指令
_BEHAVIOR_LABELS = ['回应', '恢复', '询问', '无关回复', '沉默或无视']


# ─────────── prompt 构建 ───────────
def _build_recovery_score_prompt(query: str, answer: str,
                                 original_topic: str = '') -> str:
    """1) 打断后回复打分 prompt（每轮）

    对标 Full-Duplex-Bench 论文 GPT-4o Score：coherence/relevance/adaptability，0~5。
    （注：论文正文称三维 0~5；仓库 v1.0 eval_user_interruption.py 实为单一 0~5 相关度分，
     此处沿用论文正文的三维表述，量表统一为 0~5。）
    """
    topic_line = original_topic or '（未显式给出，可从对话推断）'
    return f"""你是语音对话打断恢复质量评估专家。场景：用户和 AI 语音对话，用户在 AI 说话时打断，模型随后给出回复。请对该【模型回复内容】打分。

【原始话题/上下文】：{topic_line}
【用户打断内容】：{query}
【模型回复内容】：{answer}

请从三个维度打分（0-5 的整数，0 分最差、5 分最好；参考 Full-Duplex-Bench GPT-4o Score）：
1. 连贯性(coherence)：回复与打断前对话、与打断内容的衔接是否连贯自然，过渡是否平滑。
   0=完全断裂/无意义 1=几乎不连贯 2=略有衔接 3=基本连贯 4=连贯自然 5=完美衔接
2. 相关性(relevance)：回复是否切合用户打断所表达的需求与意图。
   0=完全无关 1=不相关 2=略微相关 3=相关 4=高度相关 5=完全切题
3. 适应性(adaptability)：模型是否适应了打断带来的话题切换/调整，自然承接而非生硬。
   0=完全未适应 1=未适应 2=略微适应 3=基本适应 4=适应良好 5=完美适应

输出严格 JSON，不要输出 JSON 以外的任何内容：
{{"coherence": 0, "relevance": 0, "adaptability": 0, "overall": 0, "reason": ""}}
其中 overall 为三维平均分（可保留一位小数），reason 为简短打分理由。"""


def _build_return_behavior_prompt(query: str, answer: str,
                                  original_topic: str = '') -> str:
    """2) 回到原话题行为判断 prompt（仅 is_return_to_topic 轮）

    用户明确要求"回到原始话题"，判断模型该轮回复属于哪类行为（5 类）。
    与 env_judge.interruption_judge 同一量表，此处聚焦"是否回到原话题"。
    """
    topic_line = original_topic or '（未显式给出，需从历史对话推断原话题）'
    return f"""你是语音对话行为分析专家。用户此前偏离了原始话题，现在明确要求"回到原始话题"。请判断模型在此轮【回复内容】属于下列哪一类行为（五选一，仅可选其一）。

【原始话题】：{topic_line}
【用户本轮请求】：{query}
【模型本轮回复】：{answer}

行为类别：
- 回应：模型直接回应了"回到原话题"的请求，并围绕原始话题作答/澄清/引导。
- 恢复：模型未明确回应请求，但回复内容已自然切回原始话题、继续原任务。
- 询问：模型对"回到哪个话题/回到哪里"进行追问、澄清或确认（如"您是说…""回到哪个话题？"），未给出切题内容。
- 无关回复：模型产生了回复，但与原始话题、与"回到原话题"请求均无关（模板话术/兜底/答非所问/恢复失败且回复无关）。
- 沉默或无视：模型未产生任何有效回复（无声、空回复、兜底拒答），或完全无视了回到原话题的请求。

输出严格 JSON，不要输出 JSON 以外的任何内容：
{{"behavior": "", "reason": ""}}
behavior 必须是上述五个标签之一（回应/恢复/询问/无关回复/沉默或无视），reason 为简短判定理由。"""


def _build_interaction_behavior_prompt(query: str, answer: str,
                                       original_topic: str = '') -> str:
    """4) 交互过程行为判断 prompt（每轮）

    判断模型收到用户本轮"指令语言"后的回复行为属于哪一类（5 类）。
    适用于所有打断用例的每一轮（含停止指令、连续打断、上下文恢复各轮）。
    """
    topic_line = original_topic or '（未显式给出，可从对话推断）'
    return f"""你是语音对话行为分析专家。用户在语音交互中向模型发出本轮指令（提问/插话/停止/切换话题/要求继续等）。请判断模型收到该指令后的【回复行为】属于下列哪一类（五选一，仅可选其一）。

【原始话题/上下文】：{topic_line}
【用户本轮指令】：{query}
【模型本轮回复】：{answer}

行为类别：
- 回应：模型针对用户本轮指令给出了直接、相关的回复（含停止后简短确认"好的"、针对插话内容作答、回应切换话题请求）。
- 恢复：模型未直接回应当前指令，但其回复已自然回到此前的话题或交互主线，体现对话恢复能力。
- 询问：模型对用户意图追问/澄清/确认（如"您是想了解……吗？"），未直接作答或执行。
- 无关回复：模型产生了回复，但与本轮用户指令、上下文或场景要求无关（含插话后未停止而继续原输出、收到停止指令仍继续、回复混乱/乱码/答非所问）。
- 沉默或无视：模型未产生任何有效回复（无声、空回复、兜底拒答），或完全无视了用户本轮指令。

输出严格 JSON，不要输出 JSON 以外的任何内容：
{{"behavior": "", "reason": ""}}
behavior 必须是上述五个标签之一（回应/恢复/询问/无关回复/沉默或无视），reason 为简短判定理由。"""


def _build_return_score_prompt(query: str, answer: str,
                               original_topic: str = '') -> str:
    """3) 回到原话题回复打分 prompt（仅 is_return_to_topic 轮）

    回到原话题是独立于打断处理的另一维度：用户明确要求"回到原始话题"后，
    对模型回复是否成功回到原话题及内容质量打分（0-5）。
    """
    topic_line = original_topic or '（未显式给出，需从历史对话推断原话题）'
    return f"""你是语音对话质量评估专家。用户明确要求"回到原始话题"，模型随后给出回复。请对该【回复内容】打分，重点看是否成功回到原话题且内容质量如何。

【原始话题】：{topic_line}
【用户回到原话题请求】：{query}
【模型回复内容】：{answer}

请从三个维度打分（0-5 的整数，0 分最差、5 分最好）：
1. 连贯性(coherence)：回复与原话题、与"回到原话题"请求的衔接是否连贯自然。
   0=完全断裂 1=几乎不连贯 2=略有衔接 3=基本连贯 4=连贯自然 5=完美衔接
2. 相关性(relevance)：回复是否切合原始话题、是否真正回到了原话题。
   0=完全无关 1=不相关 2=略微相关 3=相关 4=高度相关 5=完全切题回到原话题
3. 适应性(adaptability)：模型是否平滑回到原话题，而非生硬跳转或答非所问。
   0=完全未适应 1=未适应 2=略微适应 3=基本适应 4=适应良好 5=完美平滑回到

输出严格 JSON，不要输出 JSON 以外的任何内容：
{{"coherence": 0, "relevance": 0, "adaptability": 0, "overall": 0, "reason": ""}}
其中 overall 为三维平均分（可保留一位小数），reason 为简短打分理由。"""


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


def _normalize_behavior(raw: Any, summary: Dict[str, int]) -> tuple:
    """把 LLM 输出的 behavior 归一到合法 5 类标签，命中则给 summary 计数 +1。

    返回 (归一后标签, 是否命中合法标签)。未命中返回 (原值, False) 不计数。
    """
    behavior = str(raw or '').strip()
    if behavior in summary:
        summary[behavior] += 1
        return behavior, True
    # 子串/近义映射：LLM 偶有"回应了""沉默"等变体
    for label in _BEHAVIOR_LABELS:
        if label in behavior:
            summary[label] += 1
            return label, True
    return behavior, False


# ─────────── 主入口 ───────────
def evaluate_interruption_llm(rounds: List[Dict[str, Any]],
                              task_params: Dict[str, Any]) -> Dict[str, Any]:
    """打断对话的可选 LLM 评估主入口

    Args:
        rounds: 多轮文本结构，每轮 {query, answer, is_return_to_topic}
        task_params: 任务参数，读取 original_topic / llm_model / max_tokens / temperature

    Returns:
        dict: 见模块头 docstring 的返回结构
    """
    from app.config import config

    llm_config = getattr(config, 'LLM_JUDGE', {})
    default_model = llm_config.get('default_model', 'gpt-4')
    model = task_params.get('llm_model') or default_model
    max_tokens = int(task_params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS) or LLM_DEFAULT_MAX_TOKENS)
    temperature = float(task_params.get('temperature', LLM_DEFAULT_TEMPERATURE) or LLM_DEFAULT_TEMPERATURE)
    original_topic = _unwrap_value(task_params.get('original_topic', '')) or ''

    # 预检：未配置 API 则整体跳过，避免每轮都重复报错
    if not llm_config.get('api_base_url') or not llm_config.get('api_key'):
        raise ValueError(
            'LLM 评估未配置：请在 eval_server 设置 LLM_JUDGE_API_BASE 与 LLM_JUDGE_API_KEY'
        )

    recovery_per_round: List[Dict[str, Any]] = []
    return_behavior: List[Dict[str, Any]] = []
    return_scores: List[Dict[str, Any]] = []
    interaction_behavior: List[Dict[str, Any]] = []

    behavior_summary: Dict[str, int] = {label: 0 for label in _BEHAVIOR_LABELS}
    interaction_summary: Dict[str, int] = {label: 0 for label in _BEHAVIOR_LABELS}

    for idx, rd in enumerate(rounds, 1):
        if not isinstance(rd, dict):
            continue
        query = _unwrap_value(rd.get('query', '')) or ''
        answer = _unwrap_value(rd.get('answer', '')) or ''
        if not query or not answer:
            logger.info(f"[interruption_llm] 第 {idx} 轮缺 query/answer，跳过打分")
            continue
        is_return = bool(rd.get('is_return_to_topic'))

        # ── 4) 交互过程行为判断（每轮）：模型收到本轮指令后的回复行为 ──
        ib_item: Dict[str, Any] = {
            'round': idx, 'query': query, 'answer': answer,
            'is_return_to_topic': is_return,
            'behavior': '', 'reason': '', 'error': '',
        }
        try:
            prompt = _build_interaction_behavior_prompt(query, answer, original_topic)
            resp = _call_llm_json(prompt, model, max_tokens, temperature)
            parsed = _parse_json(resp['content']) or {}
            ib_item['behavior'], _ = _normalize_behavior(
                parsed.get('behavior', ''), interaction_summary)
            ib_item['reason'] = parsed.get('reason', '')
        except Exception as e:
            ib_item['error'] = str(e)
            logger.warning(f"[interruption_llm] 第 {idx} 轮交互行为判断失败: {e}")
        interaction_behavior.append(ib_item)

        # ── 1) 打断后回复打分（每轮）──
        rec_item: Dict[str, Any] = {
            'round': idx, 'query': query, 'answer': answer,
            'is_return_to_topic': is_return,
            'coherence': None, 'relevance': None, 'adaptability': None,
            'overall': None, 'reason': '', 'error': '',
        }
        try:
            prompt = _build_recovery_score_prompt(query, answer, original_topic)
            resp = _call_llm_json(prompt, model, max_tokens, temperature)
            parsed = _parse_json(resp['content']) or {}
            rec_item['coherence'] = _score_field(parsed, 'coherence')
            rec_item['relevance'] = _score_field(parsed, 'relevance')
            rec_item['adaptability'] = _score_field(parsed, 'adaptability')
            rec_item['overall'] = _score_field(parsed, 'overall')
            if rec_item['overall'] is None and any(
                rec_item[k] is not None for k in ('coherence', 'relevance', 'adaptability')
            ):
                rec_item['overall'] = _avg([rec_item[k] for k in ('coherence', 'relevance', 'adaptability')])
            rec_item['reason'] = parsed.get('reason', '')
        except Exception as e:  # 单轮失败不阻断
            rec_item['error'] = str(e)
            logger.warning(f"[interruption_llm] 第 {idx} 轮回复打分失败: {e}")
        recovery_per_round.append(rec_item)

        # ── 2) & 3) 仅"回到原话题"轮 ──
        if not is_return:
            continue

        # 2) 行为判断
        beh_item: Dict[str, Any] = {
            'round': idx, 'query': query, 'answer': answer,
            'behavior': '', 'reason': '', 'error': '',
        }
        try:
            prompt = _build_return_behavior_prompt(query, answer, original_topic)
            resp = _call_llm_json(prompt, model, max_tokens, temperature)
            parsed = _parse_json(resp['content']) or {}
            behavior, _ = _normalize_behavior(parsed.get('behavior', ''), behavior_summary)
            beh_item['behavior'] = behavior
            beh_item['reason'] = parsed.get('reason', '')
        except Exception as e:
            beh_item['error'] = str(e)
            logger.warning(f"[interruption_llm] 第 {idx} 轮行为判断失败: {e}")
        return_behavior.append(beh_item)

        # 3) 回到原话题回复打分
        rsc_item: Dict[str, Any] = {
            'round': idx, 'query': query, 'answer': answer,
            'coherence': None, 'relevance': None, 'adaptability': None,
            'overall': None, 'reason': '', 'error': '',
        }
        try:
            prompt = _build_return_score_prompt(query, answer, original_topic)
            resp = _call_llm_json(prompt, model, max_tokens, temperature)
            parsed = _parse_json(resp['content']) or {}
            rsc_item['coherence'] = _score_field(parsed, 'coherence')
            rsc_item['relevance'] = _score_field(parsed, 'relevance')
            rsc_item['adaptability'] = _score_field(parsed, 'adaptability')
            rsc_item['overall'] = _score_field(parsed, 'overall')
            if rsc_item['overall'] is None and any(
                rsc_item[k] is not None for k in ('coherence', 'relevance', 'adaptability')
            ):
                rsc_item['overall'] = _avg([rsc_item[k] for k in ('coherence', 'relevance', 'adaptability')])
            rsc_item['reason'] = parsed.get('reason', '')
        except Exception as e:
            rsc_item['error'] = str(e)
            logger.warning(f"[interruption_llm] 第 {idx} 轮回到原话题打分失败: {e}")
        return_scores.append(rsc_item)

    # ── 聚合 ──
    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'original_topic': original_topic,
        'llm_recovery_per_round': recovery_per_round,
        'llm_return_per_round': return_behavior,
        'llm_return_scores_per_round': return_scores,
        'llm_recovery_avg_coherence': _avg([r['coherence'] for r in recovery_per_round]),
        'llm_recovery_avg_relevance': _avg([r['relevance'] for r in recovery_per_round]),
        'llm_recovery_avg_adaptability': _avg([r['adaptability'] for r in recovery_per_round]),
        'llm_return_behavior_summary': behavior_summary,
        'llm_return_avg_coherence': _avg([r['coherence'] for r in return_scores]),
        'llm_return_avg_relevance': _avg([r['relevance'] for r in return_scores]),
        'llm_return_avg_adaptability': _avg([r['adaptability'] for r in return_scores]),
        # 交互过程行为（每轮，所有打断用例）
        'llm_interaction_per_round': interaction_behavior,
        'llm_interaction_behavior_summary': interaction_summary,
        'message': 'OK',
    }

    logger.info(
        f"[interruption_llm] model={model} n_rounds={len(recovery_per_round)} "
        f"n_return={len(return_behavior)} behavior={behavior_summary} "
        f"interaction={interaction_summary} "
        f"recovery_avg_coherence={result['llm_recovery_avg_coherence']} "
        f"return_avg_coherence={result['llm_return_avg_coherence']}"
    )
    return result


def evaluate_interruption_success_llm(user_text: str, model_text: str,
                                       task_params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """兜底：时序算不出 interruption_success_rate(n_events=0)时，
    用 LLM 按对话语义判断模型是否成功处理了用户打断。

    不依赖平台传 answer 文本，直接吃 ai_wav 的 ASR 文本(model_text)作模型回复。

    Args:
        user_text: 用户打断/提问文本(来自 user_asr.text)
        model_text: 模型回复文本(来自 ai_wav ASR 的 model_asr.text)
        task_params: 读 llm_model / LLM_JUDGE 配置

    Returns:
        {'success': bool, 'success_rate': 1.0|0.0, 'reason': str} 或 None(无法判定/未配置/无文本)
    """
    from app.config import config

    llm_config = getattr(config, 'LLM_JUDGE', {})
    if not llm_config.get('api_base_url') or not llm_config.get('api_key'):
        return None
    if not user_text or not model_text:
        return None

    model = task_params.get('llm_model') or llm_config.get('default_model', 'gpt-4o')
    prompt = (
        '你是语音对话打断处理评估专家。用户在模型回复期间打断说话，请判断模型是否【成功处理了打断】'
        '（即模型合理地让出/停下，并给出了与用户打断意图相符的恢复回复；'
        '若模型回复直接回应了用户打断的新需求，或与打断前话题连贯承接恢复，都算成功；'
        '若模型无视打断继续说穿、或回复与打断意图无关/混乱，算失败）。\n\n'
        f'【用户打断内容】：{user_text}\n\n'
        f'【模型回复内容】：{model_text}\n\n'
        '输出严格 JSON，不要输出 JSON 以外的任何内容：\n'
        '{"success": true, "reason": ""}\n'
        'success 为布尔(true/false)，reason 为简短判定理由。'
    )
    try:
        resp = _call_llm_json(prompt, model)
        parsed = _parse_json(resp['content']) or {}
        success = parsed.get('success')
        if isinstance(success, str):
            success = success.strip().lower() in ('true', '1', 'yes', '是', '成功')
        if success is None:
            return None
        success = bool(success)
        return {
            'success': success,
            'success_rate': 1.0 if success else 0.0,
            'reason': str(parsed.get('reason', '')),
            'model': model,
        }
    except Exception as e:
        logger.warning(f"[interruption_llm] success 兜底调用失败: {e}")
        return None


# ═════════════════════════════════════════════════════════════════════════════
# LLM 全量评估：success_rate / stop_latency / recovery_latency / 是否被打断 / 反应
# （2026-08-23）三项主指标改为 LLM 计算，用户侧用本地 ASR 作参考，AI 侧用字词级 ASR，
#  文本时间戳 + 音频多模态；强调用户会进行 2 轮及以上对话。
# ═════════════════════════════════════════════════════════════════════════════

# 音频总大小守卫：原始字节上限(base64≈4/3)，超过则丢弃音频只发文本
_LLM_AUDIO_MAX_BYTES = 12 * 1024 * 1024  # ≈12MB 原始 → ≈16MB base64

# 尾部静音裁剪阈值(16bit 幅度)；用于把长录音压小再发 gemini，偏移保持 0(只裁尾)时间戳不变
_TRIM_AMP_THRESHOLD = 300
_TRIM_FRAME_MS = 20
_TRIM_TAIL_MS = 300


def _trim_wav_tail(wav_path: str) -> str:
    """裁掉 wav 尾部静音到临时文件，返回临时路径；失败/无需裁返回原路径。

    只裁尾部(偏移 0)，时间戳不变；用于把 165s 全录音(语音仅~60s)压到几 MB 再发 gemini。
    """
    try:
        with wave.open(wav_path, 'rb') as w:
            p = w.getparams()
            frames = w.readframes(w.getnframes())
        nchan, sw, sr = p.nchannels, p.sampwidth, p.framerate
        bytes_per_sample = sw * nchan
        frame_bytes = int(sr * _TRIM_FRAME_MS / 1000) * bytes_per_sample
        if frame_bytes == 0:
            frame_bytes = bytes_per_sample
        n = len(frames)
        if n < frame_bytes:
            return wav_path
        pos = n
        last_voice = 0
        while pos > 0:
            start = max(0, pos - frame_bytes)
            chunk = frames[start:pos]
            max_amp = 0
            if sw == 2:
                cnt = len(chunk) // 2
                for i in range(cnt):
                    v = abs(struct.unpack_from('<h', chunk, i * 2)[0])
                    if v > max_amp:
                        max_amp = v
                        if max_amp > _TRIM_AMP_THRESHOLD:
                            break
            elif sw == 1:
                for b in chunk:
                    v = abs(b - 128)
                    if v > max_amp:
                        max_amp = v
                        if max_amp > _TRIM_AMP_THRESHOLD:
                            break
            else:
                return wav_path  # 未知位深不裁
            if max_amp > _TRIM_AMP_THRESHOLD:
                last_voice = pos
                break
            pos = start
        if last_voice == 0:
            return wav_path  # 全静音或未找到语音，不裁
        tail = int(sr * _TRIM_TAIL_MS / 1000) * bytes_per_sample
        end = min(n, last_voice + tail)
        trimmed = frames[:end]
        fd, tmp = tempfile.mkstemp(suffix='_trimmed.wav')
        with os.fdopen(fd, 'wb'):
            pass
        with wave.open(tmp, 'wb') as w:
            w.setparams(p)
            w.writeframes(trimmed)
        return tmp
    except Exception as e:
        logger.warning(f"[interruption_llm_full] trim wav tail 失败 {wav_path}: {e}")
        return wav_path


def _fmt_chunks(chunks: Any, limit: int = 600) -> str:
    """把 chunks 格式成 `text[start,end] text[start,end]` 形式，供 prompt 引用时间戳。"""
    if not chunks:
        return '(无)'
    if isinstance(chunks, dict):
        chunks = chunks.get('chunks') or []
    parts: List[str] = []
    for c in (chunks or [])[:limit]:
        if not isinstance(c, dict):
            continue
        t = str(c.get('text', ''))
        ts = c.get('timestamp')
        if isinstance(ts, (list, tuple)) and len(ts) >= 2 and ts[0] is not None and ts[1] is not None:
            try:
                parts.append(f'{t}[{float(ts[0]):.2f},{float(ts[1]):.2f}]')
            except (TypeError, ValueError):
                parts.append(t)
        else:
            parts.append(t)
    return ' '.join(parts) if parts else '(无)'


def _num(v: Any) -> Optional[float]:
    """转数值(秒)，3 位小数；非数值返回 None。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 3)
    if isinstance(v, str):
        try:
            return round(float(v.strip()), 3)
        except (ValueError, TypeError):
            return None
    return None


def _seg(v: Any) -> Optional[List[float]]:
    """[起, 止] 秒，3 位小数。"""
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        try:
            return [round(float(v[0]), 3), round(float(v[1]), 3)]
        except (TypeError, ValueError):
            return None
    return None


def _to_bool(v: Any) -> bool:
    """str 感知的布尔解析：multipart 上传时 is_return_to_topic 等会变 str('false'/'true')。
    bool('false')=True 是 bug，这里按内容判：'false'/'0'/'no'/'否'→False，其余 truthy→True。
    """
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    if s in ('false', '0', 'no', '否', 'off', ''):
        return False
    return True


def _build_interruption_full_prompt(rounds: List[Dict[str, Any]],
                                    user_asr_ref_pr: List[Any],
                                    ai_word_chunks_pr: List[Any],
                                    original_topic: str = '') -> str:
    """构建多轮打断全量评估 prompt（强调 2 轮及以上、逐轮独立分析）。

    用户/AI 侧均给段级 ASR 时间戳作参考；字词级定位优先由 gemini 听随附音频自己产出
    （本地字词级 ASR 时间戳不可靠，不喂）；音频不可用时回落到段级 ASR 时间戳。
    """
    topic_line = original_topic or '(未显式给出，可从对话推断)'
    blocks: List[str] = []
    for i, rd in enumerate(rounds, 1):
        if not isinstance(rd, dict):
            continue
        u = user_asr_ref_pr[i - 1] if i - 1 < len(user_asr_ref_pr) else None
        a = ai_word_chunks_pr[i - 1] if i - 1 < len(ai_word_chunks_pr) else None
        query = _unwrap_value(rd.get('query', '')) or ''
        answer = _unwrap_value(rd.get('answer', '')) or ''
        is_ret = _to_bool(rd.get('is_return_to_topic'))
        blocks.append(
            f'── 第 {i} 轮 (is_return_to_topic={is_ret}) ──\n'
            f'用户指令(query): {query}\n'
            f'模型回复(answer): {answer}\n'
            f'用户ASR(段级, 参考时间戳, 秒): {_fmt_chunks(u)}\n'
            f'AI回复ASR(段级, 参考时间戳, 秒): {_fmt_chunks(a)}'
        )
    rounds_text = '\n\n'.join(blocks)
    return f"""你是语音对话打断评估专家。**重要：用户会进行 2 轮或 2 轮以上的对话**，请逐轮独立分析；打断可能发生在任一轮。

定位打断边界时，**优先听随附音频做字词级 ASR**（本地 ASR 常把中文短词误识成日文假名，文本不可全信，以你听音频为准）；若未提供音频或音频不可用，则用上方段级 ASR 时间戳作参考。两路音频同一时间轴(秒)。

【原始话题/上下文】: {topic_line}

{rounds_text}

请逐轮判断并输出。每轮需要判定：
1. is_interrupted(布尔): AI 在该轮是否被用户打断(用户在 AI 正在说话期间开口插话)。
2. success(布尔|null): 仅 is_interrupted=true 时判定——AI 是否成功处理打断(合理停下当前输出 + 给出与打断意图相符的恢复回复)；未被打断则 null。
3. stop_latency_s(秒,3位小数|null): 仅打断轮——用户开始打断(user_interrupt_segment[0]) → AI 当前段停止(model_active_segment[1])。未打断则 null。
4. recovery_latency_s(秒,3位小数|null): 仅打断轮——用户讲完(user_interrupt_segment[1]) → AI 重新开口(model_next_segment[0])。未打断则 null。
5. user_interrupt_segment / model_active_segment / model_next_segment: [起, 止]秒|null，定位用户打断段与 AI 当前/下一段(以你听音频的字词级时间戳为准)。
6. reaction_behavior: AI 对打断语句的反应，五选一(回应/恢复/询问/无关回复/沉默或无视)；未被打断填"回应"。
7. reasoning: 简短说明如何定位打断段与各段起止。

另外，对**整条用例**(不是逐轮、不要均值)给出一个恢复质量总分：coherence/relevance/adaptability(0-5整数)，评价 AI 对打断的恢复回复质量(连贯性/相关性/适应性)。一条用例只给一组值。

时延定义须与时间戳一致(秒)：stop_latency = model_active_segment[1] - user_interrupt_segment[0]；recovery_latency = model_next_segment[0] - user_interrupt_segment[1]。model_active_segment 是用户开始打断时 AI 正在说的段(满足 m_s <= u_s < m_e)；model_next_segment 是其结束后 AI 重新开口的下一段。

只输出严格 JSON(不要 markdown 围栏、不要额外文字)：
{{"coherence":0,"relevance":0,"adaptability":0,"rounds":[{{"round":1,"is_interrupted":false,"success":null,"stop_latency_s":null,"recovery_latency_s":null,"user_interrupt_segment":null,"model_active_segment":null,"model_next_segment":null,"reaction_behavior":"回应","reasoning":""}}]}}"""


def evaluate_interruption_llm_full(rounds: List[Dict[str, Any]],
                                   user_asr_ref_pr: List[Any],
                                   ai_word_chunks_pr: List[Any],
                                   ai_wav_pr: List[Any],
                                   user_wav_pr: List[Any],
                                   task_params: Dict[str, Any]) -> Dict[str, Any]:
    """LLM 全量打断评估主入口。

    把 success_rate / stop_latency / recovery_latency 三项主指标交给 LLM 计算，同时判断
    AI 是否被打断、AI 对打断语句的反应(reaction_behavior)与恢复质量(coherence/relevance/adaptability)。

    Args:
        rounds: 多轮文本结构，每轮 {query, answer, is_return_to_topic, user_wav, ai_wav...}
        user_asr_ref_pr: 各轮用户本地 ASR(已 _strip_kana 去日文) {text, chunks} 列表
        ai_word_chunks_pr: 各轮 AI 字词级 ASR chunks 列表
        ai_wav_pr / user_wav_pr: 各轮 wav 路径(多模态音频，带轮号)
        task_params: 读 llm_model / max_tokens / temperature / original_topic

    Returns:
        dict: enabled/model/interruption_success_rate/avg_stop_latency_s/avg_recovery_latency_s/
              llm_recovery_avg_*/llm_interaction_*/per_round/audio_dropped/message
    """
    from app.config import config
    from ..llm_judge.llm_judge_calculator import _call_llm_api

    llm_config = getattr(config, 'LLM_JUDGE', {})
    default_model = llm_config.get('default_model', 'gpt-4')
    model = task_params.get('llm_model') or default_model
    max_tokens = int(task_params.get('max_tokens', 8192) or 8192)
    temperature = float(task_params.get('temperature', 0.0) or 0.0)
    original_topic = _unwrap_value(task_params.get('original_topic', '')) or ''

    if not llm_config.get('api_base_url') or not llm_config.get('api_key'):
        raise ValueError(
            'LLM 评估未配置：请在 eval_server 设置 LLM_JUDGE_API_BASE 与 LLM_JUDGE_API_KEY'
        )

    prompt = _build_interruption_full_prompt(rounds, user_asr_ref_pr, ai_word_chunks_pr, original_topic)

    # ── 多模态音频：收集各轮 ai_wav/user_wav，带轮号标签 ──
    # 先裁尾部静音把长录音压小(偏移0,时间戳不变)，让更多 case 能发音频给 gemini 听
    audio_paths: List[str] = []
    audio_labels: List[str] = []
    temp_files: List[str] = []
    try:
        for i, (aw, uw) in enumerate(zip(ai_wav_pr, user_wav_pr), 1):
            if aw and os.path.isfile(aw):
                tw = _trim_wav_tail(aw)
                if tw != aw:
                    temp_files.append(tw)
                audio_paths.append(tw)
                audio_labels.append(f'第{i}轮_AI回复音频')
            if uw and os.path.isfile(uw):
                tw = _trim_wav_tail(uw)
                if tw != uw:
                    temp_files.append(tw)
                audio_paths.append(tw)
                audio_labels.append(f'第{i}轮_用户音频')

        audio_dropped = False
        if audio_paths:
            total_bytes = sum(os.path.getsize(p) for p in audio_paths)
            if total_bytes > _LLM_AUDIO_MAX_BYTES:
                logger.warning(
                    f"[interruption_llm_full] 裁后音频总 {total_bytes // 1024}KB 仍过大(>{_LLM_AUDIO_MAX_BYTES // 1024}KB)，丢弃音频只发文本"
                )
                audio_paths = []
                audio_labels = []
                audio_dropped = True
            else:
                prompt += '\n\n[附] 随附音频按顺序对应：' + '，'.join(audio_labels) + '（与上方各轮 ASR 时间戳同源，可直接听辨判断是否被打断与 AI 反应）'

        resp = _call_llm_api(model, prompt, max_tokens, temperature, audio_paths=audio_paths)
    finally:
        for tf in temp_files:
            try:
                os.remove(tf)
            except OSError:
                pass
    parsed = _parse_json(resp['content']) or {}
    raw_rounds = parsed.get('rounds')
    if not isinstance(raw_rounds, list):
        raw_rounds = []

    # 用例级恢复质量(单值，非逐轮均值)：coherence/relevance/adaptability 从顶层取
    case_coh = _score_field(parsed, 'coherence')
    case_rel = _score_field(parsed, 'relevance')
    case_adap = _score_field(parsed, 'adaptability')

    interaction_summary: Dict[str, int] = {label: 0 for label in _BEHAVIOR_LABELS}
    per_round: List[Dict[str, Any]] = []
    for idx, rd in enumerate(rounds, 1):
        if not isinstance(rd, dict):
            continue
        rr = raw_rounds[idx - 1] if idx - 1 < len(raw_rounds) else {}
        if not isinstance(rr, dict):
            rr = {}
        is_int = _to_bool(rr.get('is_interrupted'))
        succ = rr.get('success')
        if isinstance(succ, str):
            succ = succ.strip().lower() in ('true', '1', 'yes', '是', '成功')
        beh_raw = rr.get('reaction_behavior', '回应' if not is_int else '')
        beh, _ = _normalize_behavior(beh_raw, interaction_summary)
        per_round.append({
            'round': idx,
            'is_interrupted': is_int,
            'success': bool(succ) if succ is not None else None,
            'stop_latency_s': _num(rr.get('stop_latency_s')),
            'recovery_latency_s': _num(rr.get('recovery_latency_s')),
            'user_interrupt_segment': _seg(rr.get('user_interrupt_segment')),
            'model_active_segment': _seg(rr.get('model_active_segment')),
            'model_next_segment': _seg(rr.get('model_next_segment')),
            'reaction_behavior': beh,
            'reasoning': str(rr.get('reasoning', '')),
        })

    # ── Python 聚合(不让 LLM 算平均) ──
    int_rds = [r for r in per_round if r['is_interrupted']]
    succ_count = sum(1 for r in int_rds if r['success'])
    success_rate = round(succ_count / len(int_rds), 3) if int_rds else 0.0
    stop_lats = [r['stop_latency_s'] for r in int_rds if r['stop_latency_s'] is not None]
    recov_lats = [r['recovery_latency_s'] for r in int_rds if r['recovery_latency_s'] is not None]

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'interruption_success_rate': success_rate,
        'avg_stop_latency_s': _avg(stop_lats),
        'avg_recovery_latency_s': _avg(recov_lats),
        # 恢复质量是用例级单值(LLM 顶层给出)，不是逐轮均值
        'llm_recovery_avg_coherence': case_coh,
        'llm_recovery_avg_relevance': case_rel,
        'llm_recovery_avg_adaptability': case_adap,
        'llm_interaction_behavior_summary': interaction_summary,
        'llm_interaction_per_round': [
            {'round': r['round'], 'is_interrupted': r['is_interrupted'],
             'reaction_behavior': r['reaction_behavior'], 'reasoning': r['reasoning']}
            for r in per_round
        ],
        'llm_recovery_per_round': per_round,
        'per_round': per_round,
        'audio_dropped': audio_dropped,
        'message': 'OK',
    }
    logger.info(
        f"[interruption_llm_full] model={model} n_rounds={len(per_round)} "
        f"n_interrupted={len(int_rds)} success_rate={success_rate} "
        f"avg_stop={result['avg_stop_latency_s']}s avg_recovery={result['avg_recovery_latency_s']}s "
        f"behavior={interaction_summary} audio_dropped={audio_dropped}"
    )
    return result
