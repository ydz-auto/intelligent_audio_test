# -*- coding: utf-8 -*-
"""interruption_judge.py
打断场景 LLM 裁判：一次带音频的 LLM 调用产出全部打断 LLM 维度

以模型回复音频(ai_wav)为主输入，用户侧 ASR 时间线为文本上下文。按平台勾选的
sub_tasks 拼接 prompt 分块，因此**每个用例只调用一次 LLM**：

    1. 行为分类（始终执行）：回应 / 恢复 / 不确定询问 / 未知 → behavior_* one-hot
    2. 打断询问率：由行为分类派生（不确定询问 → 1，否则 0；无有效解析 → None）
    3. 事件语义判定（定位到目标事件时始终执行）：is_real_interruption（是否真正打断）
       + success（模型在被打断后是否停下，停下即成功；与恢复回复质量相互独立）
       → llm_is_real_interruption / interruption_real_rate / llm_success / llm_success_rate；
       与本地时序 interruption_success_rate 互补，不回写覆盖本地数值（本地始终是唯一权威）。
    4. 回复内容评分（勾选时）：对**最后一个有效实际打断轮**的首个恢复回复打
       连贯性/相关性/适应性(0-5)；单实际轮用例写 interruption_reply_overall，
       多实际轮用例写 first_recovery_overall
    5. 停止指令遵从率（勾选且该轮为停止指令时）：模型停止原内容输出即遵从，
       只回复"好的/我明白了"等确认语同样算遵从，继续输出原内容才算不遵从

回复内容评分需要知道哪一段是"恢复回复"，这里复用本地时序计算
（compute_interruption_metrics，纯本地、不调 LLM），并复用裁判已有的两路 ASR
结果，因此不会新增 ASR 或 LLM 调用。
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
    get_llm_config,
    resolve_model,
)
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)


# ─────────── 场景定义 ───────────
INTERRUPTION_SCENES = {
    '插话打断': '模型正在输出回复时，用户插话打断了模型，用户发起新的提问或请求。',
    '停止指令': '用户对模型发出明确的停止指令，如"停""闭嘴""不用了""停下来""好了好了"等。',
    '恢复原话题': '在多轮对话中，用户打断并切换了话题（如询问天气、时间等），模型完成打断话题的回复后，用户要求回到原始话题（如"我们继续聊刚才说的""回到之前的话题"）。',
}

# 行为类别定义
INTERRUPTION_BEHAVIORS = """- 回应：模型对重叠内容进行了有意义的回应，包括回答、澄清或对重叠中提到或引入的内容做出反应。
- 恢复：模型忽略重叠，继续或完成重叠之前正在进行中的任务或回答。
- 不确定询问：模型表示不确定或难以听清、缺少信息（如"我没听清…""能重复一下吗？"），未给出明确的、针对内容的回答。所有泛化的重复或澄清行为归入此类。
- 未知：模型输出语义偏离目标或信息量低，未明确恢复、回应或表达不确定（如无关填充语、模板化噪音）。包括重叠后模型完全没有语音输出的情况。"""

# ─────────── sub_tasks 门控 ───────────
# 回复内容评分：单轮用例(打断回复内容评分) / 多轮用例(恢复首轮内容评分) / 三维均分
CONTENT_SCORE_TASKS = frozenset({
    'interruption_reply_content',
    'interruption_first_recovery_content',
    'interruption_coherence',
    'interruption_relevance',
    'interruption_adaptability',
})
# 停止指令遵从率
STOP_COMPLIANCE_TASKS = frozenset({'interruption_stop_instruction_compliance'})

_SCORE_CRITERIA = """1. coherence(连贯性)：恢复回复与被打断内容、与用户打断意图的衔接是否连贯自然。
   0=完全断裂 1=几乎不连贯 2=略有衔接 3=基本连贯 4=连贯自然 5=完美衔接
2. relevance(相关性)：恢复回复是否切合用户的打断意图。
   0=完全无关 1=不相关 2=略微相关 3=相关 4=高度相关 5=完全切题
3. adaptability(适应性)：模型是否适应了打断带来的话题切换/调整，自然承接而非生硬。
   0=完全未适应 1=未适应 2=略微适应 3=基本适应 4=适应良好 5=完美适应"""


def _selected(sub_tasks: Optional[Any], codes: frozenset) -> bool:
    """sub_tasks 未传时保持旧行为（只做行为分类），不额外拼接 prompt。"""
    if sub_tasks is None:
        return False
    if isinstance(sub_tasks, str):
        try:
            sub_tasks = json.loads(sub_tasks)
        except (ValueError, TypeError):
            sub_tasks = [sub_tasks]
    return bool(set(sub_tasks or []) & codes)


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except (ValueError, TypeError):
            return None
    return None


def _tri_state(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ('true', '1', 'yes', 'y', '是'):
            return True
        if text in ('false', '0', 'no', 'n', '否'):
            return False
    return None


# ─────────── prompt 构建 ───────────
def _event_block(event: Dict[str, Any], need_score: bool = False) -> str:
    """事件语义判定块：is_real_interruption + success（始终）+ 回复三维评分（need_score 时）。

    把本地时序定位到的目标轮事件三段文本喂给裁判，避免它自己猜恢复段；success（模型是否
    停下）与三维评分相互独立——即使未给恢复回复，只要停下 success 仍为 true。
    """
    ctx = (
        f'【用户打断意图】：{event.get("user_text") or "（未识别到用户语音）"}\n'
        f'【被打断时模型正在说】：{event.get("model_interrupted_text") or "（无）"}\n'
        f'【模型恢复回复】：{event.get("model_recovery_text") or "（模型未给出恢复回复）"}\n'
        f'【本地时序结论（仅供参考，勿照搬）】：success={event.get("success")} '
        f'stop_latency_ms={event.get("stop_latency_s")} recovery_latency_ms={event.get("recovery_latency_s")}\n\n'
    )
    parts = [
        '═══════════════════════════════════════\n'
        '【事件语义判定任务】\n'
        '═══════════════════════════════════════\n\n'
        '下面是本地时序从两路 ASR 中定位出的**最后一个有效实际打断轮**事件内容：\n\n'
        + ctx
    ]
    parts.append(
        '(A) is_real_interruption：是否真的打断（用户确有打断意图且在模型说话期间插入、模型确有让出/停下）。'
        '给布尔 + 简短 interruption_reason。\n'
        '    若用户只是应答词（"嗯/好"）、或未在模型说话期间插入、或模型全程未被影响，则不算。\n'
    )
    parts.append(
        '(B) success：模型是否【成功处理了打断】= 只要模型在被打断后停止了当前输出（让出/停下）即算成功，'
        '不要求是否恢复、也不看恢复回复质量。\n'
        '    成功 = 模型在用户打断后停下了当前输出；失败 = 模型无视打断说穿（继续把原来的话说完，未停下）。\n'
        '    给布尔 + 简短 success_reason（只解释为何停下/说穿）。\n'
        '    注意：success 与 (C) 三维评分相互独立——即使模型未给恢复回复（三维为 0），只要停下了，success 仍为 true。\n'
    )
    if need_score:
        parts.append(
            '(C) 对【模型恢复回复】三维打分（0-5 整数，0 最差、5 最好）：\n'
            f'{_SCORE_CRITERIA}\n\n'
            '注意：若模型未给出恢复回复，三维均给 0，并在理由中说明。\n'
        )
    return ''.join(parts)


def _stop_block(event: Optional[Dict[str, Any]]) -> str:
    """停止指令遵从块。"""
    context = ''
    if event:
        context = (
            f'【用户停止指令】：{event.get("user_text") or "（未识别到用户语音）"}\n'
            f'【指令前模型正在说】：{event.get("model_interrupted_text") or "（无）"}\n'
            f'【指令后模型语音】：{event.get("model_recovery_text") or "（指令后无模型语音）"}\n\n'
        )
    return (
        '═══════════════════════════════════════\n'
        '【停止指令遵从判定任务】\n'
        '═══════════════════════════════════════\n\n'
        '本轮用户发出的是**停止指令**。请判定模型是否遵从了停止指令：\n'
        '- 遵从(true)：模型停止了原来正在输出的内容；'
        '只回复"好的""我明白了""已为你停止"这类简短确认语**同样算遵从**；'
        '停止后完全没有新的语音输出也算遵从。\n'
        '- 不遵从(false)：模型无视停止指令，继续输出原来的内容。\n\n'
        f'{context}'
    )


def build_interruption_prompt(timeline_text: str = '',
                              event: Optional[Dict[str, Any]] = None,
                              need_score: bool = False,
                              need_stop_compliance: bool = False,
                              stop_event: Optional[Dict[str, Any]] = None) -> str:
    """构建打断场景评估 prompt

    Args:
        timeline_text: 用户侧 ASR 转写时间线
        event: 本地时序定位到的目标轮事件；非空时拼接事件语义判定块
            （is_real_interruption + success 始终，三维评分在 need_score 时）
        need_score: 是否在事件块里拼接回复三维评分（勾选内容评分且本轮为目标轮）
        need_stop_compliance: 是否拼接停止指令遵从判定块
        stop_event: 停止指令轮的本地时序事件（可为空）
    """
    timeline_block = ''
    if timeline_text:
        timeline_block = (
            '═══════════════════════════════════════\n'
            '【用户侧 ASR 时间线】\n'
            '═══════════════════════════════════════\n\n'
            f'{timeline_text}\n\n'
        )

    scene_blocks = []
    for i, (key, definition) in enumerate(INTERRUPTION_SCENES.items(), 1):
        scene_blocks.append(
            f"场景{i} — {key}\n"
            f"  {definition}"
        )
    scenes_text = '\n\n'.join(scene_blocks)

    extra_blocks = ''
    if event is not None:
        extra_blocks += '\n' + _event_block(event, need_score)
    if need_stop_compliance:
        extra_blocks += '\n' + _stop_block(stop_event)

    # 输出 JSON 的键按勾选动态拼接：未要求的块不出现在输出格式里
    output_keys = ['  "behavior": ""', '  "reason": ""']
    output_notes = [
        '- behavior 必须是【回应】【恢复】【不确定询问】【未知】四个类别之一',
        '- reason 为简短判定理由，需说明你从回复音频中听到了什么、结合时间线观察到什么、为何归类为此行为',
    ]
    if event is not None:
        output_keys.append('  "is_real_interruption": true')
        output_keys.append('  "interruption_reason": ""')
        output_keys.append('  "success": true')
        output_keys.append('  "success_reason": ""')
        output_notes.append(
            '- is_real_interruption 为是否真正发生打断(布尔)，interruption_reason 为简短理由'
        )
        output_notes.append(
            '- success 为模型是否成功处理打断(停下即算成功，布尔)，success_reason 为简短理由'
        )
    if need_score:
        output_keys.append(
            '  "recovery_score": {"coherence": 0, "relevance": 0, "adaptability": 0, "overall": 0, '
            '"coherence_reason": "", "relevance_reason": "", "adaptability_reason": ""}'
        )
        output_notes.append(
            '- recovery_score 为【模型恢复回复】的三维打分(0-5 整数)与 overall(三维平均，保留一位小数)，'
            '各 *_reason 为该维简短理由'
        )
    if need_stop_compliance:
        output_keys.append('  "stop_complied": true')
        output_keys.append('  "stop_compliance_reason": ""')
        output_notes.append(
            '- stop_complied 为模型是否遵从停止指令(布尔)，stop_compliance_reason 为简短理由'
        )

    output_json = '{\n' + ',\n'.join(output_keys) + '\n}'

    return f"""你是语音对话能力的裁判专家。你将收到【模型回复音频】以及下方【用户侧 ASR 时间线】。

用户输入音频包含两部分内容：第一段为用户交互内容，第二段为打断干扰内容。上述场景定义涵盖了打断干扰内容的类型。打断干扰内容往往与模型对第一段用户交互语音内容的回复内容在时间上重叠，即"重叠内容"。

请结合回复音频、时间线和场景定义，判断在接收到重叠内容后，模型表现出的行为类别，并给出理由。

{timeline_block}═══════════════════════════════════════
【场景定义】（打断干扰内容类型参考）
═══════════════════════════════════════

{scenes_text}

═══════════════════════════════════════
【行为类别定义】（四选一，仅可选其一）
═══════════════════════════════════════

{INTERRUPTION_BEHAVIORS}
{extra_blocks}
═══════════════════════════════════════
【输出格式】
═══════════════════════════════════════

输出严格 JSON，不要输出 JSON 以外的任何内容：

{output_json}

其中：
{chr(10).join(output_notes)}"""


# ─────────── 本地时序定位（复用，不调 LLM） ───────────
def _locate_target_event(rounds, round_number, interruption_rounds,
                         user_chunks, model_chunks):
    """用裁判已有的两路 ASR 跑本地时序，定位目标轮的打断/恢复文本。

    Returns:
        (event|None, is_multi, is_target, current_round, valid_rounds)
    """
    from app.services.calculators.xiaoyi_metrics.interruptibility import (
        _as_int, _current_round, _derive_interruption_rounds, _target_interruption_event,
    )
    from app.services.calculators.xiaoyi_metrics.interruptibility.interruption import (
        compute_interruption_metrics,
    )

    valid, _dangling = _derive_interruption_rounds({
        'rounds': rounds,
        'interruption_rounds': interruption_rounds,
    })
    current = _as_int(round_number)
    if current is None:
        current = _current_round({'rounds': rounds, 'round_number': None}, valid)
    is_multi = len(valid) > 1
    is_target = (not valid) or current == valid[-1]

    if not user_chunks or not model_chunks:
        return None, is_multi, is_target, current, valid

    timing = compute_interruption_metrics(
        user_chunks, model_chunks, actual_interruption=True,
    )
    # 与打断时延口径一致：取重叠时长最大的事件作为本轮打断
    return _target_interruption_event(timing.get('per_event')), is_multi, is_target, current, valid


# ─────────── 主入口 ───────────
def evaluate_interruption_judge(
    ai_wav: str = '',
    user_wav: str = '',
    model: str = '',
    max_tokens: int = LLM_DEFAULT_MAX_TOKENS,
    temperature: float = LLM_DEFAULT_TEMPERATURE,
    sub_tasks: Optional[Any] = None,
    rounds: Optional[List[Dict[str, Any]]] = None,
    round_number: Any = None,
    interruption_rounds: Optional[Any] = None,
    stop_intent: Any = None,
) -> Dict[str, Any]:
    """打断场景 LLM 裁判主入口（一次调用产出全部打断 LLM 维度）

    Args:
        ai_wav: 模型回复音频路径（主输入，被判定对象）
        user_wav: 用户通道音频路径（用于生成用户侧 ASR 时间线上下文）
        sub_tasks: 平台勾选的子维度 task_type_code 列表，用于按需拼接 prompt
        rounds / round_number / interruption_rounds: 轮次元数据，用于定位
            "最后一个有效实际打断轮"（只有该轮的回复是完整的）
        stop_intent: 本轮是否为显式停止指令轮（不把 is_interruption 当停止指令）

    Returns:
        dict: 行为分类 + interaction_text + 询问率 + 回复内容评分 + 停止指令遵从率
    """
    llm_config = get_llm_config()
    if not model:
        model = resolve_model(dimension='interruption_judge')
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

    # ── 构建文本时间线（用户侧 ASR） ──
    user_chunks: Optional[List[Dict[str, Any]]] = None
    if user_wav and os.path.isfile(user_wav):
        user_chunks = get_asr_chunks(user_wav)

    # ── 完整交互文字（query/answer + 时间戳）：模型侧走词级 ASR，仅用于返回展示，不进 prompt ──
    model_chunks: Optional[List[Dict[str, Any]]] = get_asr_chunks(ai_wav)
    interaction_text = build_interaction_text(user_chunks, model_chunks)

    # ── 按勾选决定是否拼接附加 prompt 块（不新增 LLM/ASR 调用） ──
    from app.services.calculators.xiaoyi_metrics.interruptibility import _as_bool, _get_stop_intent

    is_stop_round = _as_bool(stop_intent) or _get_stop_intent(
        {'stop_intent': stop_intent},
        (rounds or [{}])[-1] if rounds else None,
    )
    need_score = _selected(sub_tasks, CONTENT_SCORE_TASKS)
    need_stop = bool(_selected(sub_tasks, STOP_COMPLIANCE_TASKS) and is_stop_round)

    # 始终定位目标轮事件：除内容评分/停止遵从外，is_real_interruption + success
    # 语义判定也依赖该事件的三段文本，故不再只在 need_score/need_stop 时才定位。
    target_event = None
    stop_event = None
    score_event = None
    is_multi = False
    if user_chunks and model_chunks:
        event, is_multi, is_target, current_round, valid = _locate_target_event(
            rounds, round_number, interruption_rounds, user_chunks, model_chunks,
        )
        target_event = event  # 始终用于 is_real/success 语义判定
        if need_stop:
            # 停止指令轮即使没定位到恢复段也要判定（停止后无语音即为遵从）
            stop_event = event
        # 只有最后一个有效实际打断轮的回复是完整的，其余轮不做内容评分
        if need_score and is_target:
            score_event = event or {}
        logger.info(
            f'[interruption_judge] 轮次定位: current={current_round} valid={valid} '
            f'is_multi={is_multi} is_target={is_target} '
            f'need_score={bool(score_event)} need_stop={need_stop}'
        )

    timeline_text = build_timeline_text(user_chunks)
    prompt = build_interruption_prompt(
        timeline_text,
        event=target_event,
        need_score=bool(score_event),
        need_stop_compliance=need_stop,
        stop_event=stop_event,
    )

    result: Dict[str, Any] = {
        'enabled': True,
        'model': model,
        'ai_wav': ai_wav,
        'evaluations': [],
        'interaction_text': interaction_text,
        'behavior_respond': 0,
        'behavior_recover': 0,
        'behavior_uncertain': 0,
        'behavior_unknown': 0,
        # ── 合并进同一次调用的 LLM 维度（未勾选/不适用/解析失败均为 None，不得当 0）──
        'interruption_inquiry_rate': None,
        # ── 事件语义判定（is_real_interruption + success），与本地时序 success 互补，不回写覆盖 ──
        'llm_is_real_interruption': None,
        'interruption_real_rate': None,
        'interruption_reason': None,
        'llm_success': None,
        'llm_success_rate': None,
        'llm_success_reason': None,
        'recovery_coherence': None,
        'recovery_relevance': None,
        'recovery_adaptability': None,
        'interruption_reply_overall': None,
        'first_recovery_overall': None,
        'recovery_score_reasons': None,
        'stop_complied': None,
        'stop_compliance_reason': None,
        'stop_instruction_compliance_rate': None,
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
            log_context={'dimension': 'interruption_judge'},
        )
    except Exception as e:
        result['message'] = f'LLM 调用失败: {e}'
        result['enabled'] = False
        logger.error(f'[interruption_judge] LLM 调用失败: {e}')
        return result

    result['tokens_used'] = response.get('tokens_used', 0)
    result['input_token'] = response.get('input_token', 0)
    result['output_token'] = response.get('output_token', 0)

    parsed = parse_json(response['content'])
    if not parsed:
        result['message'] = 'LLM 输出解析失败'
        logger.error(
            f'[interruption_judge] LLM 输出解析失败: '
            f'{response["content"][:200]}'
        )
        return result

    evaluations = parse_evaluations(parsed)
    result['evaluations'] = evaluations
    result['message'] = 'OK'

    # 按行为类别拆分为 0/1 字段（供子维度 pass_rate 聚合）
    if evaluations:
        ev = evaluations[0]
        behavior = ev.get('behavior', '')
        if behavior == '回应':
            result['behavior_respond'] = 1
        elif behavior == '恢复':
            result['behavior_recover'] = 1
        elif behavior == '不确定询问':
            result['behavior_uncertain'] = 1
        elif behavior == '未知':
            result['behavior_unknown'] = 1
        # 打断询问率由行为分类派生：有效解析才有分母
        result['interruption_inquiry_rate'] = 1.0 if behavior == '不确定询问' else 0.0

    # ── 事件语义判定：is_real_interruption + success（与本地时序 success 互补，不回写覆盖）──
    if target_event is not None:
        is_real = _tri_state(parsed.get('is_real_interruption'))
        llm_success = _tri_state(parsed.get('success'))
        result['llm_is_real_interruption'] = is_real
        result['interruption_real_rate'] = None if is_real is None else float(is_real)
        result['interruption_reason'] = str(parsed.get('interruption_reason', ''))
        result['llm_success'] = llm_success
        result['llm_success_rate'] = None if llm_success is None else float(llm_success)
        result['llm_success_reason'] = str(parsed.get('success_reason', ''))

    # ── 回复内容评分（单实际轮 → 打断回复内容评分；多实际轮 → 恢复首轮内容评分）──
    if score_event is not None:
        score = parsed.get('recovery_score') or {}
        if isinstance(score, dict):
            dims = {
                'coherence': _num(score.get('coherence')),
                'relevance': _num(score.get('relevance')),
                'adaptability': _num(score.get('adaptability')),
            }
            overall = _num(score.get('overall'))
            if overall is None:
                values = [v for v in dims.values() if v is not None]
                overall = round(sum(values) / len(values), 1) if values else None
            result['recovery_coherence'] = dims['coherence']
            result['recovery_relevance'] = dims['relevance']
            result['recovery_adaptability'] = dims['adaptability']
            # 打分对象始终是"最后一个有效实际打断轮的首个恢复回复"，两个维度内容一致：
            # 打断回复内容评分面向单实际轮用例、恢复首轮内容评分面向多实际轮用例，
            # 同时填充可保证用例无论勾选哪一个都能看到结果。
            result['interruption_reply_overall'] = overall
            result['first_recovery_overall'] = overall
            result['recovery_score_reasons'] = {
                key: str(score.get(f'{key}_reason', '')) for key in dims
            }

    # ── 停止指令遵从率 ──
    if need_stop:
        complied = _tri_state(parsed.get('stop_complied'))
        result['stop_complied'] = complied
        result['stop_compliance_reason'] = str(parsed.get('stop_compliance_reason', ''))
        result['stop_instruction_compliance_rate'] = (
            None if complied is None else float(complied)
        )

    logger.info(
        f'[interruption_judge] '
        f'model={model} ai_wav={ai_wav} '
        f'n_evaluations={len(evaluations)} '
        f'inquiry_rate={result["interruption_inquiry_rate"]} '
        f'is_real={result["llm_is_real_interruption"]} '
        f'llm_success={result["llm_success"]} llm_success_rate={result["llm_success_rate"]} '
        f'reply_overall={result["interruption_reply_overall"]} '
        f'first_recovery_overall={result["first_recovery_overall"]} '
        f'stop_compliance={result["stop_instruction_compliance_rate"]} '
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
        description='打断场景 LLM 裁判：评估模型在打断场景下的行为'
    )
    parser.add_argument('ai_wav', help='模型回复音频文件路径')
    parser.add_argument('--user_wav', default='', help='用户通道音频路径')
    args = parser.parse_args()

    r = evaluate_interruption_judge(
        ai_wav=args.ai_wav,
        user_wav=args.user_wav,
    )

    print('=' * 60)
    print(f'模型: {r["model"]}')
    print(f'ai_wav: {r["ai_wav"]}')
    print(f'tokens: {r["tokens_used"]} (in={r["input_token"]}, out={r["output_token"]})')
    print(f'message: {r["message"]}')
    print('-' * 60)
    for ev in r.get('evaluations', []):
        print(f'\n  行为: {ev.get("behavior", "")}')
        print(f'  理由: {ev.get("reason", "")}')
    print('=' * 60)
    print(json.dumps(r, ensure_ascii=False, indent=2))
