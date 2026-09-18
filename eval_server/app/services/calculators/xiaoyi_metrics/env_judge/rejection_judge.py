# -*- coding: utf-8 -*-
"""rejection_judge.py
拒识场景 LLM 裁判：以模型回复音频(ai_wav)为主输入，评估模型在拒识场景下的行为

支持两种模式：
    多轮拒识（is_single_round=False）:
        用户输入音频包含两部分内容：第一段为用户交互内容，第二段为拒识干扰内容
    单轮拒识（is_single_round=True）:
        user_wav 直接就是需要被拒识的语音内容，无意图交互段落

timing 由外部手动传入（"回复过程中" / "静默"），LLM 根据 timing 对应的行为定义判断 behavior。

行为类别（五选一）:
    回应 / 恢复 / 不确定询问 / 无关回复 / 静默

rate 由代码根据 timing + behavior 计算:
    0 = 拒识成功, 1 = 拒识询问, 2 = 拒识失败
    特殊: timing=静默 + behavior=恢复 → rate 返回字符串 "拒识成功"

输出: 严格 JSON，{behavior, reason}
      额外返回 behavior 0/1 字段 + rate 字段
"""
import json
import os
import logging
from typing import Any, Dict, List, Optional

from app.services.calculators.xiaoyi_metrics.shared.llm_client import (
    call_llm as call_llm_api,
    build_timeline_text,
    build_interaction_text,
    parse_json,
    parse_evaluations,
    get_asr_chunks,
    get_asr_text,
    get_llm_config,
    resolve_model,
)
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)


# ─────────── 场景定义 ───────────
REJECTION_SCENES = {
    '非目标人拒识': '在目标人与模型对话过程中，出现的非目标人干扰讲话。',
    '目标人非交互意图': '在目标人与模型对话过程中，出现了目标人临时插入与其他人的讲话、打电话等，不具备与模型交互意图的语音。',
    '环境噪声': '音频中出现环境噪声，如关门声、交通噪声、音乐声等非语音噪声。',
    '用户BC': '用户在交互过程中发出"嗯""啊""好的""对"等短反馈词，不具备发起新请求的意图。',
}

# ─────────── 拒识发生时机定义 ───────────
REJECTION_TIMING = """- 回复过程中：拒识干扰内容在模型正在语音回复的过程中出现，即非意图交互内容与模型的主动语音输出在时间上重叠。此时模型正在说话，干扰可能打断或穿插在模型回复中。
- 静默：拒识干扰内容在模型未在进行语音回复的静默期间出现，即模型当前没有主动语音输出，干扰发生在模型的停顿、等待或回复结束后的间隙中。"""

# ─────────── 行为类别定义 — 回复过程中 ───────────
REJECTION_BEHAVIORS_REPLY = """- 回应：模型中断或偏离正在进行的回复，转而对重叠的拒识干扰内容进行了有意义的回应，包括回答、澄清或对干扰内容做出反应。
- 恢复：模型忽略重叠的拒识干扰内容，继续或完成重叠之前正在进行中的回复或任务。
- 不确定询问：模型因干扰内容暂停正在进行中的回复，表示不确定或难以听清、缺少信息（如"我没听清…""能重复一下吗？"），未给出明确的、针对内容的回答。所有泛化的重复或澄清行为归入此类。
- 无关回复：模型输出语义偏离目标或答非所问，未明确恢复、回应或表达不确定（如无关填充语、模板化噪音、与当前对话上下文无关的内容）。
- 静默：模型在重叠发生后完全中断语音输出且未恢复，未产生任何有意义的语音内容。"""

# ─────────── 行为类别定义 — 静默时 ───────────
REJECTION_BEHAVIORS_SILENT = """- 回应：模型在静默期间对拒识干扰内容进行了有意义的回应，即模型本应保持静默但被干扰内容触发产生了针对内容的回复、回答或反应。
- 恢复：模型忽略静默期间出现的拒识干扰内容，保持静默状态或恢复到重叠之前的任务上下文继续推进，未对干扰内容做出反应。
- 不确定询问：模型因静默期间出现的干扰内容打破沉默，表示不确定或难以听清、缺少信息（如"我没听清…""能重复一下吗？"），未给出明确的、针对内容的回答。所有泛化的重复或澄清行为归入此类。
- 无关回复：模型输出语义偏离目标或答非所问，未明确恢复、回应或表达不确定（如无关填充语、模板化噪音、与当前对话上下文无关的内容）。
- 静默：模型在静默期间收到干扰后始终未产生任何语音输出，未给出任何有意义的语音内容。"""

# 行为 → 字段名映射
BEHAVIOR_FIELD_MAP = {
    '回应': 'behavior_respond',
    '恢复': 'behavior_recover',
    '不确定询问': 'behavior_uncertain',
    '无关回复': 'behavior_irrelevant',
    '静默': 'behavior_silent',
}

# rate → (timing, behavior) 组合映射，用于统计各 rate 下的 timing+behavior 数量
RATE_COMBOS = {
    '拒识成功': [('回复过程中', '恢复'), ('静默', '静默'), ('静默', '恢复')],
    '拒识询问': [('回复过程中', '不确定询问'), ('静默', '不确定询问')],
    '拒识失败': [('回复过程中', '回应'), ('回复过程中', '无关回复'), ('回复过程中', '静默'),
               ('静默', '回应'), ('静默', '无关回复')],
}
RATE_KEY_MAP = {'拒识成功': 'success', '拒识询问': 'inquiry', '拒识失败': 'failure'}


# ─────────── rate 计算 ───────────
def compute_rate(timing: str, behavior: str) -> str:
    """根据 timing + behavior 计算 rate

    规则:
        timing=回复过程中 + behavior=恢复 → "拒识成功"
        timing=静默 + behavior=静默 → "拒识成功"
        behavior=不确定询问 → "拒识询问"（不论 timing）
        behavior=回应 / 无关回复 → "拒识失败"（不论 timing）
        timing=回复过程中 + behavior=静默 → "拒识失败"
        timing=静默 + behavior=恢复 → "拒识成功"

    Returns:
        str: "拒识成功" / "拒识询问" / "拒识失败"
    """
    if behavior == '不确定询问':
        return '拒识询问'
    if behavior in ('回应', '无关回复'):
        return '拒识失败'
    if timing == '回复过程中':
        if behavior == '恢复':
            return '拒识成功'
        if behavior == '静默':
            return '拒识失败'
    if timing == '静默':
        if behavior == '静默':
            return '拒识成功'
        if behavior == '恢复':
            return '拒识成功'
    return '拒识失败'


# ─────────── prompt 构建 ───────────
def _build_scenes_text() -> str:
    """构建场景定义文本块"""
    scene_blocks = []
    for i, (key, definition) in enumerate(REJECTION_SCENES.items(), 1):
        scene_blocks.append(
            f"场景{i} — {key}\n"
            f"  {definition}"
        )
    return '\n\n'.join(scene_blocks)


def _build_timeline_block(timeline_text: str) -> str:
    """构建用户侧 ASR 时间线文本块"""
    if not timeline_text:
        return ''
    return (
        '═══════════════════════════════════════\n'
        '【用户侧 ASR 时间线】\n'
        '═══════════════════════════════════════\n\n'
        f'{timeline_text}\n\n'
    )


def _get_behaviors_for_timing(timing: str) -> str:
    """根据 timing 返回对应的行为类别定义"""
    if timing == '静默':
        return REJECTION_BEHAVIORS_SILENT
    return REJECTION_BEHAVIORS_REPLY


def build_multi_round_rejection_prompt(timeline_text: str = '', timing: str = '', interaction_text: str = '') -> str:
    """构建多轮拒识场景评估 prompt

    多轮模式：用户输入音频包含两部分内容，
    第一段为用户交互内容，第二段为非意图交互内容（拒识干扰）。

    Args:
        timeline_text: 用户侧 ASR 转写时间线
        timing: 拒识发生时机（"回复过程中" / "静默"）
        interaction_text: 完整交互文字（query/answer + 时间戳，辅助参考）
    """
    timeline_block = _build_timeline_block(timeline_text)
    scenes_text = _build_scenes_text()
    behaviors_text = _get_behaviors_for_timing(timing)

    interaction_block = f"""═══════════════════════════════════════
【完整交互文字】（query/answer + 时间戳，辅助参考，以实际音频为准）
═══════════════════════════════════════

{interaction_text if interaction_text else '（无）'}

""" if interaction_text else ''

    return f"""你是语音对话能力的裁判专家。你将收到【模型回复音频】和【用户输入音频】以及下方【用户侧 ASR 时间线】和【完整交互文字】（均为辅助参考）。

用户输入音频包含两部分内容：第一段为用户交互内容，第二段为非意图交互内容（拒识干扰）。上述场景定义涵盖了非意图交互内容的类型。非意图交互内容往往与模型对第一段用户交互语音内容的回复内容在时间上重叠，即"重叠内容"。

注意：用户输入音频中可能包含环境噪声（如地铁播报、商场环境声等），这些噪声信息在 ASR 时间线中可能丢失，请以实际音频为准进行判断。

本次评估的拒识发生时机为：【{timing}】。请根据该时机对应的行为类别定义进行判断。

【判断要点】
1. 仔细听模型回复音频，关注模型在重叠内容出现后说了什么。
2. 【关键】对比模型回复内容与拒识干扰内容的语义关联：如果模型回复内容与干扰内容（第二段非意图交互内容）在语义上相关或直接回应了干扰内容，应判定为"回应"。例如：干扰内容提到"开门"，模型回复中出现"门"相关内容；干扰内容提到人名，模型回复中出现对人名的回应。
3. 只有当模型完全忽略干扰内容、继续完成重叠之前的任务且回复内容与干扰内容无任何语义关联时，才判定为"恢复"。
4. 切勿仅凭 ASR 文字时间线做表面推理，必须以实际音频语义为准。

【分析步骤】（请在 reason 中体现）
1. 指出拒识干扰内容（第二段非意图交互内容）是什么，以及它的时间戳。
2. 【关键】在完整交互文字中，找到时间戳在干扰内容之后的【所有 answer 行】，逐行列出。这是模型在听到干扰后做出的回复。
3. 逐一检查这些 answer 行的内容是否与干扰内容存在语义关联（如关键词重叠、话题回应、指令执行等）。只要任意一条 answer 与干扰内容相关，即应判定为"回应"。
4. 给出最终行为类别判断。

请结合模型回复音频、用户输入音频、时间线和场景定义，判断在接收到重叠内容后，模型表现出的行为类别，并给出理由。

{timeline_block}{interaction_block}═══════════════════════════════════════
【场景定义】（拒识干扰内容类型参考）
═══════════════════════════════════════

{scenes_text}

═══════════════════════════════════════
【行为类别定义】（五选一，仅可选其一）
═══════════════════════════════════════

{behaviors_text}

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
- reason 为简短判定理由，需说明你从回复音频中听到了什么、结合时间线观察到什么、为何归类为此行为"""


def build_single_round_rejection_prompt(timeline_text: str = '', timing: str = '', interaction_text: str = '') -> str:
    """构建单轮拒识场景评估 prompt

    单轮模式：user_wav 直接就是需要被拒识的语音内容，
    不存在第一段意图交互 + 第二段拒识干扰的分段结构。

    Args:
        timeline_text: 用户侧 ASR 转写时间线
        timing: 拒识发生时机（"回复过程中" / "静默"）
        interaction_text: 完整交互文字（query/answer + 时间戳，辅助参考）
    """
    timeline_block = _build_timeline_block(timeline_text)
    scenes_text = _build_scenes_text()
    behaviors_text = _get_behaviors_for_timing(timing)

    interaction_block = f"""═══════════════════════════════════════
【完整交互文字】（query/answer + 时间戳，辅助参考，以实际音频为准）
═══════════════════════════════════════

{interaction_text if interaction_text else '（无）'}

""" if interaction_text else ''

    return f"""你是语音对话能力的裁判专家。你将收到【模型回复音频】和【用户输入音频】以及下方【用户侧 ASR 时间线】和【完整交互文字】（均为辅助参考）。

用户输入音频中的内容为非意图交互内容（拒识干扰），即用户输入的语音内容不具备与模型交互的意图，模型应当拒识该内容。上述场景定义涵盖了非意图交互内容的类型。

注意：用户输入音频中可能包含环境噪声（如地铁播报、商场环境声等），这些噪声信息在 ASR 时间线中可能丢失，请以实际音频为准进行判断。

本次评估的拒识发生时机为：【{timing}】。请根据该时机对应的行为类别定义进行判断。

【判断要点】
1. 仔细听模型回复音频，关注模型在接收到拒识干扰内容后说了什么。
2. 对比模型回复内容与拒识干扰内容的语义关联：如果模型回复内容与干扰内容在语义上相关或直接回应了干扰内容，应判定为"回应"。
3. 只有当模型完全忽略干扰内容、继续完成之前的任务或保持静默时，才判定为"恢复"或"静默"。
4. 切勿仅凭 ASR 文字时间线做表面推理，必须以实际音频语义为准。

请结合模型回复音频、用户输入音频、时间线和场景定义，判断模型在接收到该拒识干扰内容后表现出的行为类别，并给出理由。

{timeline_block}{interaction_block}═══════════════════════════════════════
【场景定义】（拒识干扰内容类型参考）
═══════════════════════════════════════

{scenes_text}

═══════════════════════════════════════
【行为类别定义】（五选一，仅可选其一）
═══════════════════════════════════════

{behaviors_text}

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
- reason 为简短判定理由，需说明你从回复音频中听到了什么、结合时间线观察到什么、为何归类为此行为"""


def build_rejection_prompt(timeline_text: str = '', is_single_round: bool = False, timing: str = '', interaction_text: str = '') -> str:
    """构建拒识场景评估 prompt（统一入口）

    Args:
        timeline_text: 用户侧 ASR 转写时间线
        is_single_round: True=单轮拒识，False=多轮拒识
        timing: 拒识发生时机（"回复过程中" / "静默"）
        interaction_text: 完整交互文字（query/answer + 时间戳，辅助参考）
    """
    if is_single_round:
        return build_single_round_rejection_prompt(timeline_text, timing, interaction_text)
    return build_multi_round_rejection_prompt(timeline_text, timing, interaction_text)


# ─────────── 主入口 ───────────
def evaluate_rejection_judge(
    ai_wav: str = '',
    user_wav: str = '',
    model: str = '',
    max_tokens: int = LLM_DEFAULT_MAX_TOKENS,
    temperature: float = LLM_DEFAULT_TEMPERATURE,
    is_single_round: bool = False,
    timing: str = '',
) -> Dict[str, Any]:
    """拒识场景 LLM 裁判主入口

    以【模型回复音频 ai_wav】为主输入（裁判模型直接听回复，不过小 ASR），
    用户侧 ASR 转写作为文本时间线上下文。

    Args:
        ai_wav: 模型回复音频路径（主输入，被判定对象）
        user_wav: 用户通道音频路径（用于生成用户侧 ASR 时间线上下文）
        is_single_round: True=单轮拒识（user_wav 直接为拒识内容），
                         False=多轮拒识（user_wav 包含意图交互+拒识干扰两段）
        timing: 拒识发生时机，手动传入（"回复过程中" / "静默"）

    Returns:
        dict: {
            'enabled': True,
            'model': str,
            'ai_wav': str,
            'timing': str,
            'evaluations': [{behavior, reason}, ...],
            'query': str,
            'answer': str,
            'behavior_respond': int,      # 回应 → 1, 否则 0
            'behavior_recover': int,      # 恢复 → 1, 否则 0
            'behavior_uncertain': int,    # 不确定询问 → 1, 否则 0
            'behavior_irrelevant': int,   # 无关回复 → 1, 否则 0
            'behavior_silent': int,       # 静默 → 1, 否则 0
            'rate': int | str,            # 0=拒识成功, 1=拒识询问, 2=拒识失败, "拒识成功"=特殊
            'rate_success': int,          # rate=0 → 1, 否则 0
            'rate_inquiry': int,          # rate=1 → 1, 否则 0
            'rate_failure': int,          # rate=2 → 1, 否则 0
            'tokens_used': int,
            'input_token': int,
            'output_token': int,
            'message': str,
        }
    """
    llm_config = get_llm_config()
    if not model:
        model = resolve_model(dimension='reject_judge')
    if not max_tokens:
        max_tokens = llm_config.get('max_tokens', LLM_DEFAULT_MAX_TOKENS)
    if temperature is None:
        temperature = llm_config.get('temperature', LLM_DEFAULT_TEMPERATURE)

    # 主音频：ai_wav（模型回复，被判定对象）
    if not ai_wav or not os.path.isfile(ai_wav):
        raise FileNotFoundError(
            f'模型回复音频(ai_wav)不存在或路径无效: ai_wav={ai_wav!r}'
        )

    file_paths: List[str] = [ai_wav]

    # ── 将 user_wav 也作为音频直接发给 LLM（环境噪声等信息 ASR 会丢失） ──
    if user_wav and os.path.isfile(user_wav):
        file_paths.append(user_wav)

    # ── 构建文本时间线（用户侧 ASR，作为辅助参考） ──
    user_chunks: Optional[List[Dict[str, Any]]] = None
    if user_wav and os.path.isfile(user_wav):
        user_chunks = get_asr_chunks(user_wav)

    timeline_text = build_timeline_text(user_chunks)

    # ── 完整交互文字（query/answer + 时间戳）：模型侧走词级 ASR，仅用于返回展示，不进 prompt ──
    model_chunks: Optional[List[Dict[str, Any]]] = get_asr_chunks(ai_wav)
    interaction_text = build_interaction_text(user_chunks, model_chunks)

    # ── 提取 query / answer 文本（从 ASR 结果 JSON 读取） ──
    query_text = get_asr_text(user_wav)
    answer_text = get_asr_text(ai_wav)

    prompt = build_rejection_prompt(timeline_text, is_single_round=is_single_round, timing=timing, interaction_text=interaction_text)

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'ai_wav': ai_wav,
        'timing': timing,
        'evaluations': [],
        'interaction_text': interaction_text,
        'query': query_text,
        'answer': answer_text,
        'behavior_respond': 0,
        'behavior_recover': 0,
        'behavior_uncertain': 0,
        'behavior_irrelevant': 0,
        'behavior_silent': 0,
        'rate': None,
        'rate_success': 0,
        'rate_inquiry': 0,
        'rate_failure': 0,
        'rate_success_count': {'拒识成功数量': 0, **{f'{t}_{b}': 0 for t, b in RATE_COMBOS['拒识成功']}},
        'rate_inquiry_count': {'拒识询问数量': 0, **{f'{t}_{b}': 0 for t, b in RATE_COMBOS['拒识询问']}},
        'rate_failure_count': {'拒识失败数量': 0, **{f'{t}_{b}': 0 for t, b in RATE_COMBOS['拒识失败']}},
        'tokens_used': 0,
        'input_token': 0,
        'output_token': 0,
        'message': '',
    }

    try:
        response = call_llm_api(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            file_paths=file_paths,
            log_context={'dimension': 'reject_judge'},
        )
    except Exception as e:
        result['message'] = f'LLM 调用失败: {e}'
        result['enabled'] = False
        logger.error(f'[rejection_judge] LLM 调用失败: {e}')
        return result

    result['tokens_used'] = response.get('tokens_used', 0)
    result['input_token'] = response.get('input_token', 0)
    result['output_token'] = response.get('output_token', 0)

    parsed = parse_json(response['content'])
    if not parsed:
        result['message'] = 'LLM 输出解析失败'
        logger.error(
            f'[rejection_judge] LLM 输出解析失败: '
            f'{response["content"][:200]}'
        )
        return result

    evaluations = parse_evaluations(parsed)
    result['evaluations'] = evaluations
    result['message'] = 'OK'

    # 按行为类别拆分为 0/1 字段 + 计算 rate + 统计 timing+behavior 数量
    if evaluations:
        ev = evaluations[0]
        behavior = ev.get('behavior', '')

        # 行为 0/1 字段（取首轮）
        field = BEHAVIOR_FIELD_MAP.get(behavior)
        if field:
            result[field] = 1

        # 计算 rate（取首轮）
        rate = compute_rate(timing, behavior)
        result['rate'] = rate
        if rate == '拒识成功':
            result['rate_success'] = 1
        elif rate == '拒识询问':
            result['rate_inquiry'] = 1
        elif rate == '拒识失败':
            result['rate_failure'] = 1

        # 遍历所有 evaluations，统计各 rate 下的 timing+behavior 数量
        for ev_item in evaluations:
            ev_behavior = ev_item.get('behavior', '')
            ev_rate = compute_rate(timing, ev_behavior)
            count_key = f'{timing}_{ev_behavior}'
            rate_field = f'rate_{RATE_KEY_MAP.get(ev_rate, "")}_count'
            if rate_field in result:
                # 累加总数
                total_key = f'{ev_rate}数量'
                if total_key in result[rate_field]:
                    result[rate_field][total_key] += 1
                # 累加 timing+behavior 组合数
                if count_key in result[rate_field]:
                    result[rate_field][count_key] += 1

    logger.info(
        f'[rejection_judge] '
        f'model={model} ai_wav={ai_wav} '
        f'timing={timing} '
        f'n_evaluations={len(evaluations)} '
        f'tokens={result["tokens_used"]}'
    )
    return result


if __name__ == '__main__':
    import argparse
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
        description='拒识场景 LLM 裁判：评估模型在拒识场景下的行为'
    )
    parser.add_argument('ai_wav', help='模型回复音频文件路径')
    parser.add_argument('--user_wav', default='', help='用户通道音频路径')
    parser.add_argument('--is_single_round', action='store_true',
                        help='单轮拒识模式：user_wav 直接为拒识内容')
    parser.add_argument('--timing', default='回复过程中',
                        choices=['回复过程中', '静默'],
                        help='拒识发生时机（回复过程中/静默）')
    args = parser.parse_args()

    r = evaluate_rejection_judge(
        ai_wav=args.ai_wav,
        user_wav=args.user_wav,
        is_single_round=args.is_single_round,
        timing=args.timing,
    )

    print('=' * 60)
    print(f'模型: {r["model"]}')
    print(f'ai_wav: {r["ai_wav"]}')
    print(f'timing: {r["timing"]}')
    print(f'tokens: {r["tokens_used"]} (in={r["input_token"]}, out={r["output_token"]})')
    print(f'message: {r["message"]}')
    print('-' * 60)
    for ev in r.get('evaluations', []):
        print(f'\n  行为: {ev.get("behavior", "")}')
        print(f'  理由: {ev.get("reason", "")}')
    print(f'\n  rate: {r["rate"]}')
    print('=' * 60)
    print(json.dumps(r, ensure_ascii=False, indent=2))
