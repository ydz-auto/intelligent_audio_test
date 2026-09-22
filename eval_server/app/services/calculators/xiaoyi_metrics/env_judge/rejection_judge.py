# -*- coding: utf-8 -*-
"""rejection_judge.py
拒识裁判：评估语音对话模型在拒识场景（非意图交互内容出现时）下的行为表现。

裁判 LLM 直接听取 ai_wav + user_wav 音频，结合 ASR 时间线辅助参考，
判断模型行为类别（五选一），再由代码根据 timing + behavior 计算 rate 评级。

输入:
    ai_wav           — 模型回复音频路径（主输入，被判定对象）
    user_wav         — 用户通道音频路径（可选）
    is_single_round  — True=单轮拒识 / False=多轮拒识（默认）
    timing           — 拒识发生时机："回复过程中" 或 "静默"
    model            — LLM 模型名（留空自动解析）
    max_tokens       — LLM 最大输出 token 数
    temperature      — LLM 温度参数

输出:
    evaluations: list        — 逐轮评估 [{behavior, reason}, ...]
    behavior_respond: int    — 命中"回应" → 1
    behavior_recover: int    — 命中"恢复" → 1
    behavior_uncertain: int  — 命中"不确定询问" → 1
    behavior_irrelevant: int — 命中"无关回复" → 1
    behavior_silent: int     — 命中"静默" → 1
    rate: str                — "拒识成功" / "拒识询问" / "拒识失败"
    rate_success: int        — rate="拒识成功" → 1
    rate_inquiry: int        — rate="拒识询问" → 1
    rate_failure: int        — rate="拒识失败" → 1
    rate_success_count: dict — 拒识成功分组统计
    rate_inquiry_count: dict — 拒识询问分组统计
    rate_failure_count: dict — 拒识失败分组统计
"""
import os
import logging
from typing import Any, Dict, List, Optional

from app.services.calculators.xiaoyi_metrics.shared.llm_client import (
    call_llm as call_llm_api,
    parse_json,
    get_asr_chunks,
    get_asr_text,
    get_llm_config,
    resolve_model,
    build_interaction_text,
)
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)

# ─────────── 行为类别 ───────────
REJECT_BEHAVIOR_LABELS = ['回应', '恢复', '不确定询问', '无关回复', '静默']

BEHAVIOR_FIELD_MAP = {
    '回应': 'behavior_respond',
    '恢复': 'behavior_recover',
    '不确定询问': 'behavior_uncertain',
    '无关回复': 'behavior_irrelevant',
    '静默': 'behavior_silent',
}

# ─────────── rate 计算规则 ───────────
# (timing, behavior) → rate
_RATE_RULES = {
    ('回复过程中', '恢复'): '拒识成功',
    ('回复过程中', '不确定询问'): '拒识询问',
    ('回复过程中', '回应'): '拒识失败',
    ('回复过程中', '无关回复'): '拒识失败',
    ('回复过程中', '静默'): '拒识失败',
    ('静默', '静默'): '拒识成功',
    ('静默', '恢复'): '拒识成功',
    ('静默', '不确定询问'): '拒识询问',
    ('静默', '回应'): '拒识失败',
    ('静默', '无关回复'): '拒识失败',
}

# rate 分组统计的键定义
_SUCCESS_KEYS = ['拒识成功数量', '回复过程中_恢复', '静默_静默', '静默_恢复']
_INQUIRY_KEYS = ['拒识询问数量', '回复过程中_不确定询问', '静默_不确定询问']
_FAILURE_KEYS = ['拒识失败数量', '回复过程中_回应', '回复过程中_无关回复',
                 '回复过程中_静默', '静默_回应', '静默_无关回复']


def compute_rate(timing: str, behavior: str) -> str:
    """根据 timing + behavior 计算 rate 评级"""
    return _RATE_RULES.get((timing, behavior), '拒识失败')


def _init_count_dict(keys: List[str]) -> Dict[str, int]:
    return {k: 0 for k in keys}


def _init_success_count() -> Dict[str, int]:
    return _init_count_dict(_SUCCESS_KEYS)


def _init_inquiry_count() -> Dict[str, int]:
    return _init_count_dict(_INQUIRY_KEYS)


def _init_failure_count() -> Dict[str, int]:
    return _init_count_dict(_FAILURE_KEYS)


def _update_count(count_dict: Dict[str, int], timing: str, behavior: str):
    """更新分组统计字典

    每个字典只更新自身包含的键：timing_behavior 分组键 + 所属类别的总数键。
    """
    key = f'{timing}_{behavior}'
    if key in count_dict:
        count_dict[key] += 1
    # 更新总数（仅当该键存在于当前字典中时才递增）
    rate = compute_rate(timing, behavior)
    total_key = None
    if rate == '拒识成功':
        total_key = '拒识成功数量'
    elif rate == '拒识询问':
        total_key = '拒识询问数量'
    elif rate == '拒识失败':
        total_key = '拒识失败数量'
    if total_key and total_key in count_dict:
        count_dict[total_key] += 1


def _normalize_behavior(behavior: str) -> str:
    """归一化 behavior 标签，模糊匹配到标准标签"""
    behavior = behavior.strip()
    if behavior in REJECT_BEHAVIOR_LABELS:
        return behavior
    for label in REJECT_BEHAVIOR_LABELS:
        if label in behavior:
            return label
    return behavior


def _to_bool(value, default=False) -> bool:
    """将各种类型的值转为 bool"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes')
    return default


# ─────────── prompt 构建 ───────────

def _build_single_round_prompt(timing: str, interaction_text: str) -> str:
    """单轮拒识模式 prompt"""
    timing_def = _get_timing_definition(timing)
    behavior_defs = _get_behavior_definitions(timing)

    return f"""你是语音对话能力的裁判专家。你将收到【模型回复音频】(ai_wav) 和【用户输入音频】(user_wav)。

请直接听音频内容进行判断，下方 ASR 时间线仅供参考，以实际音频为准。

═══════════════════════════════════════
【拒识场景说明】
═══════════════════════════════════════

在单轮拒识场景中，user_wav 中的内容即为需要被拒识的非意图交互内容。
模型应当对该内容不予回应（保持静默或继续之前的任务）。

拒识发生时机：{timing}
{timing_def}

═══════════════════════════════════════
【行为类别定义】（五选一）
═══════════════════════════════════════

{behavior_defs}

═══════════════════════════════════════
【ASR 时间线参考】（可能存在误差，以音频为准）
═══════════════════════════════════════

{interaction_text or '（无时间线数据）'}

═══════════════════════════════════════
【评估步骤】
═══════════════════════════════════════

1. 听取 ai_wav（模型回复音频），了解模型的实际表现。
2. 听取 user_wav（用户输入音频），了解拒识干扰内容。
3. 根据行为类别定义，判断模型的行为属于哪一类。
4. 给出最终行为类别判断和理由。

═══════════════════════════════════════
【输出格式】
═══════════════════════════════════════

输出严格 JSON，不要输出 JSON 以外的任何内容：

{{
  "behavior": "",
  "reason": ""
}}

其中：
- behavior 必须是【回应】【恢复】【不确定询问】【无关回复】【静默】五个类别之一
- reason 为简短判定理由，说明模型的行为表现和判定依据"""


def _build_multi_round_prompt(timing: str, interaction_text: str) -> str:
    """多轮拒识模式 prompt"""
    timing_def = _get_timing_definition(timing)
    behavior_defs = _get_behavior_definitions(timing)

    return f"""你是语音对话能力的裁判专家。你将收到【模型回复音频】(ai_wav) 和【用户输入音频】(user_wav)。

请直接听音频内容进行判断，下方 ASR 时间线仅供参考，以实际音频为准。

═══════════════════════════════════════
【拒识场景说明】
═══════════════════════════════════════

在多轮拒识场景中，user_wav 包含两部分内容：
1. 第一段：用户意图交互内容（正常对话）
2. 第二段：非意图交互内容（拒识干扰）

模型应当忽略第二段非意图交互内容，继续或完成之前的回复/任务。

拒识发生时机：{timing}
{timing_def}

═══════════════════════════════════════
【行为类别定义】（五选一）
═══════════════════════════════════════

{behavior_defs}

═══════════════════════════════════════
【ASR 时间线参考】（可能存在误差，以音频为准）
═══════════════════════════════════════

{interaction_text or '（无时间线数据）'}

═══════════════════════════════════════
【评估步骤】
═══════════════════════════════════════

1. 听取 user_wav，识别第一段意图交互内容和第二段非意图交互内容（拒识干扰），记录干扰内容的时间戳。
2. 在完整交互文字中，找到时间戳在干扰内容之后的所有 answer 行，逐行列出。这是模型在听到干扰后做出的回复。
3. 逐一检查这些 answer 行的内容是否与干扰内容存在语义关联（如关键词重叠、话题回应、指令执行等）。只要任意一条 answer 与干扰内容相关，即应判定为"回应"。
4. 听取 ai_wav（模型回复音频），结合上述分析，判断模型的行为属于哪一类。
5. 给出最终行为类别判断和理由。

═══════════════════════════════════════
【输出格式】
═══════════════════════════════════════

输出严格 JSON，不要输出 JSON 以外的任何内容：

{{
  "behavior": "",
  "reason": ""
}}

其中：
- behavior 必须是【回应】【恢复】【不确定询问】【无关回复】【静默】五个类别之一
- reason 为简短判定理由，说明模型的行为表现和判定依据"""


def _get_timing_definition(timing: str) -> str:
    if timing == '回复过程中':
        return '拒识干扰内容在模型正在语音回复的过程中出现，即非意图交互内容与模型的主动语音输出在时间上重叠。'
    return '拒识干扰内容在模型未在进行语音回复的静默期间出现，即模型当前没有主动语音输出。'


def _get_behavior_definitions(timing: str) -> str:
    if timing == '回复过程中':
        defs = [
            ('回应', '模型中断或偏离正在进行的回复，转而对拒识干扰内容进行了有意义的回应（回答、澄清或反应）。'),
            ('恢复', '模型忽略拒识干扰内容，继续或完成正在进行中的回复或任务。'),
            ('不确定询问', '模型因干扰内容暂停回复，表示不确定或难以听清、缺少信息，未给出明确回答。所有泛化的重复或澄清行为归入此类。'),
            ('无关回复', '模型输出语义偏离目标或答非所问，未明确恢复、回应或表达不确定。'),
            ('静默', '模型在重叠发生后完全中断语音输出且未恢复，未产生任何有意义的语音内容。'),
        ]
    else:
        defs = [
            ('回应', '模型在静默期间对拒识干扰内容进行了有意义的回应，即本应保持静默但被干扰触发产生了回复。'),
            ('恢复', '模型忽略静默期间出现的干扰内容，保持静默状态或恢复到之前的任务上下文继续推进。'),
            ('不确定询问', '模型因静默期间出现的干扰内容打破沉默，表示不确定或难以听清、缺少信息。'),
            ('无关回复', '模型输出语义偏离目标或答非所问，未明确恢复、回应或表达不确定。'),
            ('静默', '模型在静默期间收到干扰后始终未产生任何语音输出。'),
        ]
    return '\n'.join(f'- {name}：{desc}' for name, desc in defs)


# ─────────── 主入口 ───────────

def evaluate_rejection_judge(
    ai_wav: str,
    user_wav: str = '',
    is_single_round: bool = False,
    timing: str = '静默',
    model: str = '',
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """拒识裁判

    评估模型在拒识场景下的行为表现。

    Args:
        ai_wav:          模型回复音频路径（主输入，被判定对象）
        user_wav:        用户通道音频路径（可选）
        is_single_round: True=单轮拒识 / False=多轮拒识
        timing:          拒识发生时机："回复过程中" 或 "静默"
        model:           LLM 模型名（空则按维度配置解析）
        max_tokens:      LLM max_tokens
        temperature:     LLM temperature

    Returns:
        dict: 评估结果
    """
    llm_config = get_llm_config()
    if not model:
        model = resolve_model(dimension='reject_judge')
    if not max_tokens:
        max_tokens = llm_config.get('max_tokens', LLM_DEFAULT_MAX_TOKENS)
    if temperature is None:
        temperature = llm_config.get('temperature', LLM_DEFAULT_TEMPERATURE)

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'ai_wav': ai_wav,
        'user_wav': user_wav,
        'is_single_round': is_single_round,
        'timing': timing,
        'evaluations': [],
        'interaction_text': '',
        'query': '',
        'answer': '',
        'behavior_respond': 0,
        'behavior_recover': 0,
        'behavior_uncertain': 0,
        'behavior_irrelevant': 0,
        'behavior_silent': 0,
        'rate': '',
        'rate_success': 0,
        'rate_inquiry': 0,
        'rate_failure': 0,
        'rate_success_count': _init_success_count(),
        'rate_inquiry_count': _init_inquiry_count(),
        'rate_failure_count': _init_failure_count(),
        'tokens_used': 0,
        'input_token': 0,
        'output_token': 0,
        'message': '',
    }

    # ─── 参数校验 ───
    if not ai_wav or not os.path.isfile(ai_wav):
        result['message'] = f'模型回复音频(ai_wav)不存在或路径无效: ai_wav={ai_wav!r}'
        result['enabled'] = False
        logger.error(f'[reject_judge] {result["message"]}')
        return result

    # ─── 构建 ASR 时间线 + 交互文字 ───
    user_chunks = None
    model_chunks = None
    if user_wav and os.path.isfile(user_wav):
        user_chunks = get_asr_chunks(user_wav)
    if ai_wav and os.path.isfile(ai_wav):
        model_chunks = get_asr_chunks(ai_wav)

    interaction_text = build_interaction_text(user_chunks, model_chunks)
    result['interaction_text'] = interaction_text

    # 提取 query / answer 纯文本
    if user_chunks:
        result['query'] = ' '.join(
            c.get('text', '') for c in user_chunks
            if isinstance(c, dict) and c.get('text')
        )
    if model_chunks:
        result['answer'] = ' '.join(
            c.get('text', '') for c in model_chunks
            if isinstance(c, dict) and c.get('text')
        )
    # fallback: 用 get_asr_text 取整体文本
    if not result['answer'] and ai_wav:
        result['answer'] = get_asr_text(ai_wav)
    if not result['query'] and user_wav:
        result['query'] = get_asr_text(user_wav)

    # ─── 构建 prompt ───
    if is_single_round:
        prompt = _build_single_round_prompt(timing, interaction_text)
    else:
        prompt = _build_multi_round_prompt(timing, interaction_text)

    # ─── 调用 LLM ───
    file_paths = [ai_wav]
    if user_wav and os.path.isfile(user_wav):
        file_paths.append(user_wav)

    try:
        response = call_llm_api(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            file_paths=file_paths,
            log_context={'dimension': 'reject_judge', 'timing': timing,
                         'is_single_round': is_single_round},
        )
    except Exception as e:
        result['message'] = f'LLM 调用失败: {e}'
        result['enabled'] = False
        logger.error(f'[reject_judge] LLM 调用失败: {e}')
        return result

    result['tokens_used'] = response.get('tokens_used', 0)
    result['input_token'] = response.get('input_token', 0)
    result['output_token'] = response.get('output_token', 0)

    # ─── 解析 LLM 输出 ───
    parsed = parse_json(response['content'])
    if not parsed:
        result['message'] = 'LLM 输出解析失败'
        logger.error(f'[reject_judge] LLM 输出解析失败: {response["content"][:200]}')
        return result

    # 提取 behavior / reason
    behavior = str(parsed.get('behavior', '')).strip()
    behavior = _normalize_behavior(behavior)
    reason = parsed.get('reason', '')

    evaluations = [{'behavior': behavior, 'reason': reason}]
    result['evaluations'] = evaluations

    # ─── 行为 0/1 字段（取首轮 evaluation） ───
    field = BEHAVIOR_FIELD_MAP.get(behavior)
    if field:
        result[field] = 1

    # ─── rate 评级 ───
    rate = compute_rate(timing, behavior)
    result['rate'] = rate
    if rate == '拒识成功':
        result['rate_success'] = 1
    elif rate == '拒识询问':
        result['rate_inquiry'] = 1
    elif rate == '拒识失败':
        result['rate_failure'] = 1

    # ─── 分组统计 ───
    for ev in evaluations:
        ev_behavior = _normalize_behavior(ev.get('behavior', ''))
        _update_count(result['rate_success_count'], timing, ev_behavior)
        _update_count(result['rate_inquiry_count'], timing, ev_behavior)
        _update_count(result['rate_failure_count'], timing, ev_behavior)

    result['message'] = 'OK'

    logger.info(
        f'[reject_judge] '
        f'model={model} timing={timing} '
        f'behavior={behavior} rate={rate} '
        f'tokens={result["tokens_used"]}'
    )
    return result


if __name__ == '__main__':
    import argparse
    import json as json_module
    from pathlib import Path

    # 独立运行时加载 eval_server/.env
    _env_path = Path(__file__).resolve().parents[4] / '.env'
    if _env_path.exists():
        with open(_env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

    parser = argparse.ArgumentParser(
        description='拒识裁判：评估模型在拒识场景下的行为表现'
    )
    parser.add_argument('ai_wav', help='模型回复音频路径')
    parser.add_argument('--user_wav', default='', help='用户通道音频路径')
    parser.add_argument('--is_single_round', type=str, default='false',
                        help='True=单轮拒识 / False=多轮拒识')
    parser.add_argument('--timing', default='静默',
                        choices=['回复过程中', '静默'],
                        help='拒识发生时机')
    args = parser.parse_args()

    r = evaluate_rejection_judge(
        ai_wav=args.ai_wav,
        user_wav=args.user_wav,
        is_single_round=_to_bool(args.is_single_round),
        timing=args.timing,
    )

    print('=' * 60)
    print(f'模型: {r["model"]}')
    print(f'timing: {r["timing"]}')
    print(f'tokens: {r["tokens_used"]} (in={r["input_token"]}, out={r["output_token"]})')
    print(f'message: {r["message"]}')
    print('-' * 60)
    print(f'  behavior: {r["evaluations"][0]["behavior"] if r["evaluations"] else "N/A"}')
    print(f'  rate: {r["rate"]}')
    print(f'  reason: {r["evaluations"][0]["reason"] if r["evaluations"] else ""}')
    print('=' * 60)
    print(json_module.dumps(r, ensure_ascii=False, indent=2))
