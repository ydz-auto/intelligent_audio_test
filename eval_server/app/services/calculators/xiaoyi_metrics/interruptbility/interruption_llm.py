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
                           采用 Full-Duplex-Bench v1.5 behavior.txt 的 C 轴（内容关系）四分类，
                           适配"回到原话题"语境，判断模型回复属于：
                           C_RESPOND / C_RESUME / C_UNCERTAIN_HANDLING / C_UNKNOWN
    3. 回到原话题回复打分 : 对回到原话题后的模型回复，按 连贯性/相关性/适应性 打 0-5 分

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
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

LLM_DEFAULT_TIMEOUT = 120
LLM_DEFAULT_TEMPERATURE = 0.1
LLM_DEFAULT_MAX_TOKENS = 1024

# 行为分类的合法取值（与 prompt 的 v1.5 C 轴四分类一致）
_BEHAVIOR_LABELS = ['C_RESPOND', 'C_RESUME', 'C_UNCERTAIN_HANDLING', 'C_UNKNOWN']


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

    回到原话题是独立于打断处理的另一维度。采用 Full-Duplex-Bench v1.5 behavior.txt
    的 C 轴（内容关系）四分类，适配"回到原话题"语境：判断模型对"回到原话题"请求的
    回复属于哪一类行为（C_RESPOND / C_RESUME / C_UNCERTAIN_HANDLING / C_UNKNOWN）。
    """
    topic_line = original_topic or '（未显式给出，需从历史对话推断原话题）'
    return f"""你是语音对话行为分析专家。用户此前偏离了原始话题，现在用户明确要求"回到原始话题"。请判断模型在此轮【回复内容】属于下列哪一类行为（C 轴：内容关系，四选一，仅可选其一）。

【原始话题】：{topic_line}
【用户本轮请求】：{query}
【模型本轮回复】：{answer}

行为类别（参考 Full-Duplex-Bench v1.5 behavior.txt 的 C 轴）：
- C_RESPOND：模型直接回应了"回到原话题"的请求，并围绕原始话题作答/澄清/引导。
- C_RESUME：模型未明确回应请求，但回复内容已自然切回原始话题、继续原任务。
- C_UNCERTAIN_HANDLING：模型表示不确定或请求澄清（如"回到哪个话题？""您是说…"），未给出切题内容。
- C_UNKNOWN：回复与原始话题无关、低信息量（模板话术/兜底/空回复），既未回应、未恢复、也未表达不确定。

输出严格 JSON，不要输出 JSON 以外的任何内容：
{{"behavior": "", "reason": ""}}
behavior 必须是上述四个标签之一（C_RESPOND / C_RESUME / C_UNCERTAIN_HANDLING / C_UNKNOWN），reason 为简短判定理由。"""


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

    behavior_summary: Dict[str, int] = {label: 0 for label in _BEHAVIOR_LABELS}

    for idx, rd in enumerate(rounds, 1):
        if not isinstance(rd, dict):
            continue
        query = _unwrap_value(rd.get('query', '')) or ''
        answer = _unwrap_value(rd.get('answer', '')) or ''
        if not query or not answer:
            logger.info(f"[interruption_llm] 第 {idx} 轮缺 query/answer，跳过打分")
            continue
        is_return = bool(rd.get('is_return_to_topic'))

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
            behavior = str(parsed.get('behavior', '')).strip()
            if behavior in behavior_summary:
                behavior_summary[behavior] += 1
            else:
                # 归一化：尽量映射回合法标签
                behavior_lower = behavior
                matched = next(
                    (label for label in _BEHAVIOR_LABELS if label in behavior_lower),
                    None,
                )
                if matched:
                    behavior_summary[matched] += 1
                    behavior = matched
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
        'message': 'OK',
    }

    logger.info(
        f"[interruption_llm] model={model} n_rounds={len(recovery_per_round)} "
        f"n_return={len(return_behavior)} behavior={behavior_summary} "
        f"recovery_avg_coherence={result['llm_recovery_avg_coherence']} "
        f"return_avg_coherence={result['llm_return_avg_coherence']}"
    )
    return result
