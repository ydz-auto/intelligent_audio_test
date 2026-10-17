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
    success_silent_recover: int  — 静默时拒识恢复行为(恢复或静默) → 1
    success_reply_recover: int   — 回复时拒识恢复行为(恢复) → 1
    inquiry_silent: int          — 静默时拒识询问行为(不确定询问) → 1
    inquiry_reply: int           — 回复时拒识询问行为(不确定询问) → 1
    failure_silent_respond: int  — 静默时拒识回应行为(回应) → 1
    failure_reply_respond: int   — 回复时拒识回应行为(回应) → 1
    failure_silent_irrelevant: int — 静默时拒识无关行为(无关回复) → 1
    failure_reply_irrelevant: int  — 回复时拒识无关行为(无关回复) → 1
    failure_reply_silent: int      — 回复时拒识静默行为(静默) → 1
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


# ─────────── 波形能量活跃段检测（定位无 ASR 文本的干扰，如环境噪声）───────────

def _load_audio_mono(filepath):
    """加载 WAV 为 mono float64，返回 (sr, data)。"""
    from scipy.io import wavfile
    import numpy as np
    sr, data = wavfile.read(filepath)
    if data.ndim > 1:
        data = data.mean(axis=1)
    dt = data.dtype
    if dt == np.int16:
        data = data.astype(np.float64) / 32768.0
    elif dt == np.int32:
        data = data.astype(np.float64) / 2147483648.0
    elif dt == np.uint8:
        data = (data.astype(np.float64) - 128.0) / 128.0
    else:
        data = data.astype(np.float64)
        peak = np.max(np.abs(data)) if len(data) else 0
        if peak > 0:
            data /= peak
    return sr, data


def get_active_segments(wav_path, frame_ms=50, hop_ms=25, threshold_factor=0.12,
                        min_gap_s=0.35, min_seg_s=0.1):
    """检测用户侧波形活跃段（RMS 能量），返回 [[start_s, end_s], ...]。

    用途：环境噪声/非语音干扰可能没有 ASR 文本，但存在波形能量，
    用该函数定位干扰时段，辅助 LLM 判定 timing 与行为。
    """
    try:
        import numpy as np
        sr, data = _load_audio_mono(wav_path)
    except Exception as e:
        logger.warning(f'[reject_judge] 波形活跃段读取失败 {wav_path}: {e}')
        return []
    if len(data) == 0:
        return []
    frame_len = int(sr * frame_ms / 1000)
    hop_len = int(sr * hop_ms / 1000)
    n_frames = max(1, (len(data) - frame_len) // hop_len + 1)
    rms = np.zeros(n_frames)
    for i in range(n_frames):
        seg = data[i * hop_len:i * hop_len + frame_len]
        if len(seg) > 0:
            rms[i] = float(np.sqrt(np.mean(seg ** 2)))
    max_rms = float(np.max(rms))
    if max_rms <= 1e-6:
        return []
    active = rms > max_rms * threshold_factor
    segments = []
    in_seg = False
    seg_start = 0.0
    for i in range(n_frames):
        t = i * hop_len / sr
        if active[i] and not in_seg:
            in_seg = True
            seg_start = t
        elif not active[i] and in_seg:
            in_seg = False
            seg_end = t + frame_len / sr
            segments.append([round(seg_start, 2), round(seg_end, 2)])
    if in_seg:
        segments.append([round(seg_start, 2), round((n_frames * hop_len + frame_len) / sr, 2)])
    # 合并间隔过小的相邻段
    merged = []
    for seg in segments:
        if seg[1] - seg[0] < min_seg_s:
            continue
        if merged and seg[0] - merged[-1][1] < min_gap_s:
            merged[-1][1] = seg[1]
        else:
            merged.append(seg)
    return merged


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


def _normalize_timing(timing: str) -> str:
    """归一化 timing 标签：模糊匹配到 静默 / 回复过程中"""
    timing = timing.strip()
    if timing in _TEXT_JUDGE_TIMINGS:
        return timing
    if '静默' in timing:
        return '静默'
    if '回复' in timing and '过程' in timing:
        return '回复过程中'
    return timing


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


def _build_focused_interaction_text(user_chunks, model_chunks, focus_start, focus_end):
    """按本轮新增干扰窗口 [focus_start, focus_end] 裁剪交互文字。

    目的：round_i 音频是累积的（含 round 0..i-1 内容），
    逐轮评估只保留「意图 query 首段 + 本轮干扰 + 干扰后的模型回复」，
    避免更早轮次的干扰内容重复进入本轮判定。
    """
    from app.services.calculators.xiaoyi_metrics.interruptibility.interruption import (
        _to_segments,
        USER_SEG_MERGE_GAP_S,
        MODEL_SEG_MERGE_GAP_S,
    )
    from app.services.calculators.xiaoyi_metrics.shared.llm_client import (
        _fmt_mmss,
    )

    lines = []
    user_keep = []
    first_done = False
    for s in _to_segments(user_chunks or [], gap=USER_SEG_MERGE_GAP_S):
        if s['start'] < focus_start - 0.3:
            # 干扰前：仅保留意图 query 首段作为上下文（丢弃更早的拒识轮内容）
            if not first_done:
                first_done = True
                user_keep.append(s)
        elif s['start'] <= focus_end + 1.0:
            user_keep.append(s)
    model_keep = [
        s for s in _to_segments(model_chunks or [], gap=MODEL_SEG_MERGE_GAP_S)
        if s['start'] >= focus_start - 0.1
    ]
    for s in user_keep:
        lines.append((s['start'],
                      f"query [{_fmt_mmss(s['start'])}; {_fmt_mmss(s['end'])}]{s['text']}"))
    for s in model_keep:
        lines.append((s['start'],
                      f"answer [{_fmt_mmss(s['start'])}; {_fmt_mmss(s['end'])}]{s['text']}"))
    lines.sort(key=lambda x: x[0])
    if not lines:
        return ''
    return ''.join(f'{text}\n' for _, text in lines)


# ─────────── prompt 构建 ───────────

def _build_single_round_prompt(timing: str, interaction_text: str,
                               active_segments_text: str = '') -> str:
    """单轮拒识模式 prompt"""
    timing_def = _get_timing_definition(timing)
    behavior_defs = _get_behavior_definitions(timing)
    waveform_ref = (
        f'\n{active_segments_text}\n' if active_segments_text
        else '（无波形活跃段信息）'
    )

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
【用户侧波形活跃段】（能量检测，含环境噪声等无 ASR 文本的干扰；格式 [起-止]秒，可能存在误差）
═══════════════════════════════════════

{waveform_ref}

═══════════════════════════════════════
【评估步骤】
═══════════════════════════════════════

1. 听取 ai_wav（模型回复音频），了解模型的实际表现。
2. 听取 user_wav（用户输入音频），了解拒识干扰内容，记录其时间戳。结合【用户侧波形活跃段】定位干扰时段——环境噪声等非语音干扰没有 ASR 文字，但波形活跃段会标记其时段。注意：干扰可能是环境噪声等非语音内容，ASR 文字可能为空，请直接听音频定位干扰时段。
3. 判定拒识发生时机 timing：定位干扰发生的时间戳（听音频定位，不依赖 ASR 文本），检查该时刻模型是否正在语音输出——AI 通道 answer 段与其时间重叠或紧随其后，则模型正在说话，timing=「回复过程中」；若该时刻模型无任何语音输出，timing=「静默」。判定只依据干扰发生时模型是否在说话，不受场景说明中的拒识发生时机影响。
4. 根据行为类别定义，判断模型的行为属于哪一类。
5. 若在音频中完全听不出任何拒识干扰内容（例如被降噪去除、音量过低），则 behavior 输出 null，并在 reason 说明「未检测到干扰(可能被降噪)」。
6. 给出最终行为类别、timing 判定和理由。

═══════════════════════════════════════
【输出格式】
═══════════════════════════════════════

输出严格 JSON，不要输出 JSON 以外的任何内容：

{{
  "behavior": "",
  "reason": "",
  "timing": ""
}}

其中：
- behavior 必须是【回应】【恢复】【不确定询问】【无关回复】【静默】五个类别之一
- timing 必须是【静默】【回复过程中】之一（依据步骤3的用户说话时模型是否也在说话判定，勿照抄场景说明中的拒识发生时机）
- reason 为简短判定理由，说明模型的行为表现、timing 判定依据和判定结论"""


def _build_multi_round_prompt(timing: str, interaction_text: str,
                              active_segments_text: str = '',
                              focus_window: Optional[list] = None) -> str:
    """多轮拒识模式 prompt"""
    timing_def = _get_timing_definition(timing)
    behavior_defs = _get_behavior_definitions(timing)
    waveform_ref = (
        f'\n{active_segments_text}\n' if active_segments_text
        else '（无波形活跃段信息）'
    )
    focus_ref = ''
    if focus_window:
        focus_ref = (
            f'\n本轮待评估干扰时段（仅评估该时段新增的干扰，忽略更早内容）: '
            f'[{focus_window[0]:.2f}s-{focus_window[1]:.2f}s]\n'
        )

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
【用户侧波形活跃段】（能量检测，含环境噪声等无 ASR 文本的干扰；格式 [起-止]秒，可能存在误差）
═══════════════════════════════════════

{waveform_ref}
{focus_ref}
═══════════════════════════════════════
【评估步骤】
═══════════════════════════════════════

1. 听取 user_wav，识别第一段意图交互内容和第二段非意图交互内容（拒识干扰：用户插话、非目标人语音、环境噪声等），记录干扰内容的时间戳。结合【用户侧波形活跃段】定位干扰时段——环境噪声等非语音干扰没有 ASR 文字，但波形活跃段会标记其时段。若给出了【本轮待评估干扰时段】，则只评估该时段对应的干扰，更早轮次的干扰一律忽略。注意：干扰可能是环境噪声等非语音内容，ASR 文字可能为空，请直接听音频定位干扰时段，不要因 ASR 无文字就认为没有干扰。
2. 判定拒识发生时机 timing：定位本轮干扰发生的时间戳（听音频定位，不依赖 ASR 文本），检查该时刻模型是否正在语音输出——AI 通道 answer 段与其时间重叠或紧随其后，则模型正在说话，timing=「回复过程中」；若该时刻模型无任何语音输出，timing=「静默」。判定只依据干扰发生时模型是否在说话，不受场景说明中的拒识发生时机影响。
3. 在完整交互文字中，找到时间戳在干扰内容之后的所有 answer 行，逐行列出。这是模型在听到干扰后做出的回复。
4. 逐一检查这些 answer 行的内容是否与干扰内容存在语义关联（如关键词重叠、话题回应、指令执行等）。只要任意一条 answer 与干扰内容相关，即应判定为"回应"。
5. 听取 ai_wav（模型回复音频），结合上述分析，判断模型的行为属于哪一类。
6. 若在音频中完全听不出任何拒识干扰内容（例如被降噪去除、音量过低、该轮本无干扰），则 behavior 输出 null，并在 reason 说明「未检测到干扰(可能被降噪)」；只有明确听出干扰时才进行 1-5 的完整判定。
7. 给出最终行为类别、timing 判定和理由。

═══════════════════════════════════════
【输出格式】
═══════════════════════════════════════

输出严格 JSON，不要输出 JSON 以外的任何内容：

{{
  "behavior": "",
  "reason": "",
  "timing": ""
}}

其中：
- behavior 必须是【回应】【恢复】【不确定询问】【无关回复】【静默】五个类别之一
- timing 必须是【静默】【回复过程中】之一（依据步骤2的用户说话时模型是否也在说话判定，勿照抄场景说明中的拒识发生时机）
- reason 为简短判定理由，说明模型的行为表现、timing 判定依据和判定结论"""


def _get_timing_definition(timing: str) -> str:
    if timing == '回复过程中':
        return '拒识干扰内容在模型正在语音回复的过程中出现，即非意图交互内容与模型的主动语音输出在时间上重叠。'
    return '拒识干扰内容在模型未在进行语音回复的静默期间出现，即模型当前没有主动语音输出。'


def _get_behavior_definitions(timing: str) -> str:
    if timing == '回复过程中':
        defs = [
            ('回应', '模型中断或偏离正在进行的回复，转而对拒识干扰内容进行了有意义的回应（回答、澄清或反应）。'),
            ('恢复', '模型忽略拒识干扰内容，继续或完成正在进行中的回复或任务；要求原回复在干扰后连贯延续或完成（被打断的句子继续说下去，或语义自然衔接）。'),
            ('不确定询问', '模型因干扰内容暂停回复，表示不确定或难以听清、缺少信息，未给出明确回答。所有泛化的重复或澄清行为归入此类。'),
            ('无关回复', '模型输出语义偏离目标或答非所问，未明确恢复、回应或表达不确定；或原回复被干扰打断/破坏——未说完即终止或跳转（被打断的句子不完整、下一句与其不衔接，如中途转到索取信息/换话题），回复完整性受损，即使未直接回应干扰内容也视为无关回复（拒识失败）。'),
            ('静默', '模型在重叠发生后完全中断语音输出且未恢复，未产生任何有意义的语音内容。'),
        ]
    else:
        defs = [
            ('回应', '模型在静默期间对拒识干扰内容进行了有意义的回应，即本应保持静默但被干扰触发产生了回复。'),
            ('恢复', '模型忽略静默期间出现的干扰内容，保持静默状态或恢复到之前的任务上下文继续推进。'),
            ('不确定询问', '模型因静默期间出现的干扰内容打破沉默，表示不确定或难以听清、缺少信息。'),
            ('无关回复', '模型输出语义偏离目标或答非所问，未明确恢复、回应或表达不确定；或回复被干扰重新触发但不连贯/不完整，答非所问，原任务推进受损，视为无关回复（拒识失败）。'),
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
    prev_active_end: Optional[float] = None,
    active_segments: Optional[List[list]] = None,
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
        prev_active_end: 上一轮用户侧波形活跃段覆盖终点(秒)。
                         用于本轮窗口化：只评估本轮新增干扰，避免累积音频重复评估。
        active_segments: 用户侧波形活跃段 [[start_s, end_s], ...]。
                         多轮聚合时由 calculator 一次性算出并复用，避免重复能量扫描。

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
        # 新增：timing 由 LLM 判定（静默/回复过程中），与配置 timing 对比，不一致则该轮不计入统计
        'judged_timing': '',
        'timing_config': timing,
        'timing_match': True,
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
        # 子维度 0/1 字段（按 timing+behavior 组合，供子维度 field_path 提取）
        'success_silent_recover': 0,
        'success_reply_recover': 0,
        'inquiry_silent': 0,
        'inquiry_reply': 0,
        'failure_silent_respond': 0,
        'failure_reply_respond': 0,
        'failure_silent_irrelevant': 0,
        'failure_reply_irrelevant': 0,
        'failure_reply_silent': 0,
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

    # ─── 用户侧波形活跃段（能量检测，定位无 ASR 文本的干扰，如环境噪声） ───
    # 多轮聚合时由 calculator 算好传入复用；单轮/独立调用时此处计算
    if active_segments is None and user_wav and os.path.isfile(user_wav):
        active_segments = get_active_segments(user_wav)
    active_segments = active_segments or []
    active_segments_text = '、'.join(
        f'[{s:.2f}s-{e:.2f}s]' for s, e in active_segments) if active_segments else ''
    focus_window = None
    if active_segments and prev_active_end is not None:
        # 本轮新增干扰窗口 = 上一轮覆盖终点之后的新活跃段（累积音频窗口化）
        new_segs = [s for s in active_segments
                    if s[0] >= float(prev_active_end) - 0.3]
        if new_segs:
            focus_window = new_segs[-1]
    result['user_active_segments'] = active_segments_text
    result['focus_window'] = focus_window

    # 窗口化：只保留本轮新增干扰及其后的模型回复，避免累积音频重复评估
    if focus_window:
        focused_text = _build_focused_interaction_text(
            user_chunks, model_chunks, focus_window[0], focus_window[1])
        if focused_text:
            interaction_text = focused_text
            result['interaction_text'] = interaction_text

    # ─── 构建 prompt ───
    if is_single_round:
        prompt = _build_single_round_prompt(timing, interaction_text, active_segments_text)
    else:
        prompt = _build_multi_round_prompt(timing, interaction_text, active_segments_text, focus_window)

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
        result['is_success'] = False
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

    # 提取 behavior / reason / timing
    raw_behavior = parsed.get('behavior')
    if raw_behavior is None or (isinstance(raw_behavior, str) and not raw_behavior.strip()):
        # 干扰不可判定（被降噪抹掉/音量过低/该轮本无干扰）→ 该轮不计入统计
        result['undetectable'] = True
        result['message'] = f'未检测到拒识干扰(可能被降噪/音量过低): {str(parsed.get("reason", ""))[:120]}'
        result['rate'] = ''
        logger.info(f'[reject_judge] 未检测到干扰, 该轮不可判定: {result["message"]}')
        return result

    behavior = str(raw_behavior).strip()
    behavior = _normalize_behavior(behavior)
    reason = parsed.get('reason', '')

    # 新增：timing 由模型基于「用户说话时模型是否也在说话」判定（静默/回复过程中）
    judged_timing = str(parsed.get('timing', '')).strip()
    if judged_timing not in ('静默', '回复过程中'):
        judged_timing = ''
    # 生效 timing：模型判定优先，缺失时回退配置值
    effective_timing = judged_timing or timing
    result['judged_timing'] = judged_timing
    result['timing_config'] = timing
    result['timing'] = effective_timing
    result['timing_match'] = (not judged_timing) or (judged_timing == timing)

    evaluations = [{'behavior': behavior, 'reason': reason, 'timing': judged_timing}]
    result['evaluations'] = evaluations

    # ─── 行为 0/1 字段（取首轮 evaluation） ───
    field = BEHAVIOR_FIELD_MAP.get(behavior)
    if field:
        result[field] = 1

    # ─── rate 评级（按生效 timing） ───
    rate = compute_rate(effective_timing, behavior)
    result['rate'] = rate
    if rate == '拒识成功':
        result['rate_success'] = 1
    elif rate == '拒识询问':
        result['rate_inquiry'] = 1
    elif rate == '拒识失败':
        result['rate_failure'] = 1

    # ─── 分组统计（按生效 timing） ───
    for ev in evaluations:
        ev_behavior = _normalize_behavior(ev.get('behavior', ''))
        _update_count(result['rate_success_count'], effective_timing, ev_behavior)
        _update_count(result['rate_inquiry_count'], effective_timing, ev_behavior)
        _update_count(result['rate_failure_count'], effective_timing, ev_behavior)

    # ─── 子维度 0/1 字段（按 timing+behavior 组合设置） ───
    _SUB_BEHAVIOR_MAP = {
        ('静默', '恢复'): 'success_silent_recover',
        ('静默', '静默'): 'success_silent_recover',
        ('回复过程中', '恢复'): 'success_reply_recover',
        ('静默', '不确定询问'): 'inquiry_silent',
        ('回复过程中', '不确定询问'): 'inquiry_reply',
        ('静默', '回应'): 'failure_silent_respond',
        ('回复过程中', '回应'): 'failure_reply_respond',
        ('静默', '无关回复'): 'failure_silent_irrelevant',
        ('回复过程中', '无关回复'): 'failure_reply_irrelevant',
        ('回复过程中', '静默'): 'failure_reply_silent',
    }
    sub_field = _SUB_BEHAVIOR_MAP.get((effective_timing, behavior))
    if sub_field:
        result[sub_field] = 1

    result['message'] = 'OK'

    logger.info(
        f'[reject_judge] '
        f'model={model} timing={effective_timing} config_timing={timing} '
        f'judged_timing={judged_timing or "-"} '
        f'behavior={behavior} rate={rate} '
        f'tokens={result["tokens_used"]}'
    )
    return result


# ════════════════════════════════════════════════════════════════════
# 文本模态整体拒识裁判（参考打断 full_timeline_judge）
# 最终轮双路 wav → ASR 词级全时间线 → 轮次切分 → 一次 LLM 逐轮判定
# timing/behavior/reason 全部由模型自主判定，不再使用配置 timing；
# rate 由代码按 (timing, behavior) 查 _RATE_RULES 映射。
# ════════════════════════════════════════════════════════════════════

# 子维度 0/1 字段映射（按 timing+behavior 组合）
_SUB_BEHAVIOR_MAP = {
    ('静默', '恢复'): 'success_silent_recover',
    ('静默', '静默'): 'success_silent_recover',
    ('回复过程中', '恢复'): 'success_reply_recover',
    ('静默', '不确定询问'): 'inquiry_silent',
    ('回复过程中', '不确定询问'): 'inquiry_reply',
    ('静默', '回应'): 'failure_silent_respond',
    ('回复过程中', '回应'): 'failure_reply_respond',
    ('静默', '无关回复'): 'failure_silent_irrelevant',
    ('回复过程中', '无关回复'): 'failure_reply_irrelevant',
    ('回复过程中', '静默'): 'failure_reply_silent',
}

_TEXT_JUDGE_TIMINGS = ('静默', '回复过程中')
_TEXT_JUDGE_BEHAVIORS = REJECT_BEHAVIOR_LABELS

_TEXT_JUDGE_SYSTEM = """你是语音对话能力的裁判专家。你将收到一段【完整对话词级 ASR 时间线】（query=用户侧，answer=模型侧，单位秒）。

【拒识场景说明】
- 用户侧第一段语音是意图交互内容（正常提问）；
- 意图之后出现的每一段用户语音（如附和"嗯/对/好/没错"、语气词、噪声等）都是非意图交互内容（拒识干扰）。
模型应当忽略这些干扰，继续或完成之前的回复/任务；被干扰触发产生回应/偏离/中断即为失败行为。

【timing 判定】（判断拒识干扰发生时，模型整体是否处于回复过程中；不能只看干扰瞬间是否有字词重叠）
- 回复过程中：干扰发生在模型整体回复语义流中——模型正处于连续回复/任务输出阶段（含句与句之间的短暂停顿），干扰前后模型都在推进同一回复；判定需结合整体语义，而非仅看干扰那一刻是否正好有语音。
- 静默：干扰发生在模型回复已结束（或尚未开始）的静默等待期——干扰前模型已完成输出且干扰后未恢复输出，整体不处于回复过程中。

【behavior 判定】（五选一）
- 恢复：模型忽略拒识干扰内容，继续或完成正在进行中的回复或任务；要求原回复在干扰后**连贯延续或完成**（被打断的句子继续说下去，或语义自然衔接）。
- 回应：模型中断或偏离正在进行的回复，转而对拒识干扰内容进行了有意义的回应（回答、澄清或反应）；
- 静默：模型在干扰发生后完全中断语音输出且未恢复，未产生任何有意义的语音内容；
- 不确定询问：模型因干扰内容暂停回复，表示不确定或难以听清、缺少信息，未给出明确回答；所有泛化的重复或澄清行为归入此类；
- 无关回复：模型输出语义偏离目标或答非所问，未明确恢复、回应或表达不确定；或原回复被干扰**打断/破坏**——未说完即终止或跳转（被打断的句子不完整、下一句与其不衔接，如中途转到索取信息/换话题），回复完整性受损，即使未直接回应干扰内容也视为无关回复（拒识失败）。

【判定注意事项】（务必遵守）
1. ASR 文本可能不完整/存在漏字、时间戳误差：某句话显示为片段（如句子戛然而止）不代表模型被打断或行为异常，不代表干扰造成了中断。判断 timing/behavior 一律以整体语义连续性为准：干扰前模型是否处于回复语义流中、干扰后是否继续推进同一回复。
2. 「回应」必须是被干扰内容触发的新行为（干扰之后才发生的回答/澄清/反应/重复索取信息）。若模型说的话是原回答流程的自然延续——即使语义上看句子未说完——也不属于回应。
3. 不要因为某处出现短停顿（句与句之间、词语之间的自然间隙）就判定为静默或中断；静默指模型整体不处于回复过程中（回复已结束/尚未开始），而非说话中的短暂停顿。
4. 干扰内容本身（如"嗯/对/好"）不计入模型行为，只看模型对它的反应。
5. 区分「恢复」与「无关回复」：恢复要求干扰后原回复连贯延续或完成；若原回复在干扰后未说完即跳转/终止（被打断的句子不完整，下一句与前句不衔接，如中途转向索取信息或换话题），判定为无关回复 → 拒识失败。
6. 原句未说完即跳转的判定从严：若模型正在讲解/说明，被打断的句子在语法或内容上明显未完成（如"……再用"就停了），且下一句不是其直接延续（如转而索取信息、另起话头），一律判「无关回复」（拒识失败）；仅凭主题仍相关/仍围绕原任务，不能作为判「恢复」的理由。

【输出要求】
必须逐轮实际判断并填写 reason（结合时间线与整体语义说明依据），输出严格 JSON（禁止任何额外文字）：
{"round_details": [{"round": 轮号, "timing": "静默|回复过程中", "behavior": "恢复|回应|静默|不确定询问|无关回复", "reason": "判断理由"}]}
轮号必须与【待评估拒识轮】一一对应，不得缺轮、重复或改写轮号。"""


def _text_judgment_fields(timing: str, behavior: str, reason: str) -> Dict[str, Any]:
    """把单轮 (timing, behavior) 映射为与既有单轮结果同构的字段集（rate/子维度/count）。"""
    j: Dict[str, Any] = {
        'timing': timing, 'behavior': behavior, 'reason': reason,
        'rate': '', 'rate_success': 0, 'rate_inquiry': 0, 'rate_failure': 0,
        'rate_success_count': _init_success_count(),
        'rate_inquiry_count': _init_inquiry_count(),
        'rate_failure_count': _init_failure_count(),
        'evaluations': [{'behavior': behavior, 'reason': reason, 'timing': timing}],
    }
    field = BEHAVIOR_FIELD_MAP.get(behavior)
    if field:
        j[field] = 1
    rate = compute_rate(timing, behavior)
    j['rate'] = rate
    if rate == '拒识成功':
        j['rate_success'] = 1
    elif rate == '拒识询问':
        j['rate_inquiry'] = 1
    elif rate == '拒识失败':
        j['rate_failure'] = 1
    sub_field = _SUB_BEHAVIOR_MAP.get((timing, behavior))
    if sub_field:
        j[sub_field] = 1
    for count_dict in (j['rate_success_count'], j['rate_inquiry_count'], j['rate_failure_count']):
        _update_count(count_dict, timing, behavior)
    return j


def evaluate_rejection_judge_text(user_wav: str, ai_wav: str, model: str = '',
                                  max_tokens: Optional[int] = None,
                                  temperature: Optional[float] = None,
                                  has_intent: bool = True,
                                  configured_rounds: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """文本模态整体拒识裁判：最终轮双路 wav → ASR 全时间线 → 轮次切分 → 一次 LLM 逐轮判定。

    Args:
        user_wav: 最终轮（累积）用户侧音频
        ai_wav:   最终轮（累积）模型侧音频
        model:    LLM 模型名（空则按维度配置解析；文本模态，不传音频附件）
        has_intent: True=首段用户语音为意图交互（不评，其后续段才是拒识轮）
                    False=全部用户语音段都是拒识干扰
    Returns:
        dict: {
            'model', 'tokens_used',
            'rounds': [单轮判定结果(含 timing/behavior/rate/reason/子维度)…],
            'message', 'enabled'
        }
    """
    llm_config = get_llm_config()
    if not model:
        model = resolve_model(dimension='reject_judge')
    if not max_tokens:
        max_tokens = llm_config.get('max_tokens', LLM_DEFAULT_MAX_TOKENS)
    if temperature is None:
        temperature = llm_config.get('temperature', LLM_DEFAULT_TEMPERATURE)

    user_chunks = get_asr_chunks(user_wav) if user_wav and os.path.isfile(user_wav) else None
    model_chunks = get_asr_chunks(ai_wav) if ai_wav and os.path.isfile(ai_wav) else None
    if not user_chunks:
        return {'enabled': False, 'message': '用户侧 ASR 无词级结果，无法轮次切分', 'rounds': []}
    if not model_chunks:
        return {'enabled': False, 'message': '模型侧 ASR 无词级结果', 'rounds': []}

    if configured_rounds is not None:
        from .rejection_rounds_v3 import build_packet, judge
        try:
            packet = build_packet(user_chunks, model_chunks, configured_rounds)
            rows, response = judge(packet, call_llm_api, model, max_tokens, temperature)
        except Exception as exc:
            logger.exception('[reject_judge_rounds_v3] 轮次裁判失败')
            return {'enabled': False, 'message': f'LLM 输出解析失败/轮次校验失败: {exc}', 'rounds': []}
        judged = []
        ordinal = 0
        for row in rows:
            if not row['evaluate_rejection']:
                continue
            ordinal += 1
            if row['evaluation_status'] == 'evaluated':
                item = _text_judgment_fields(row['timing'], row['behavior'], row['reason'])
            else:
                item = {'evaluation_status': 'unjudgeable', 'behavior': None, 'rate': None,
                        'message': '不可判定: ' + row['reason']}
            item.update(row)
            item['round'] = ordinal
            judged.append(item)
        return {'enabled': True, 'model': model, 'rounds': judged,
                'round_alignment': rows, 'prompt_version': 'rounds_v3',
                'tokens_used': response.get('tokens_used', 0),
                'input_token': response.get('input_token', 0),
                'output_token': response.get('output_token', 0), 'message': 'OK'}

    from app.services.calculators.xiaoyi_metrics.interruptibility.interruption import (
        _to_segments, USER_SEG_MERGE_GAP_S, MODEL_SEG_MERGE_GAP_S,
    )
    user_segs = _to_segments(user_chunks, gap=USER_SEG_MERGE_GAP_S) or []
    if not user_segs:
        return {'enabled': False, 'message': '用户侧未检测到语音段', 'rounds': []}
    bc_segs = user_segs[1:] if has_intent else user_segs
    # 轮次切分可追溯日志：wav 文件名 + 用户ASR段数 + 切出的拒识轮数，便于定位切分偏少的用例
    logger.info(
        f'[reject_judge_text] 轮次切分: user_wav={os.path.basename(user_wav)} '
        f'用户ASR段数={len(user_segs)} (has_intent={has_intent}) 切出拒识轮={len(bc_segs)}'
    )
    if not bc_segs:
        return {'enabled': False, 'message': '未检测到拒识干扰（用户侧仅意图段/无干扰）', 'rounds': []}

    # 构建完整词级时间线（与打断 build_input 同构）
    words: List[Dict[str, Any]] = []
    for prefix, speaker, chunks in (('U', 'query', user_chunks), ('M', 'answer', model_chunks)):
        for index, chunk in enumerate(chunks or []):
            if not isinstance(chunk, dict):
                continue
            ts = chunk.get('timestamp') or []
            if len(ts) != 2:
                continue
            try:
                s, e = float(ts[0]), float(ts[1])
            except (TypeError, ValueError):
                continue
            words.append({'word_id': f'{prefix}{index:04d}', 'speaker': speaker,
                          'text': str(chunk.get('text') or ''), 'start': s, 'end': e})
    words.sort(key=lambda w: (w['start'], w['end'], w['word_id']))

    timeline_lines = ['query|answer [起-止]秒 文本（query=用户, answer=模型）']
    for w in words:
        timeline_lines.append(f"{w['speaker']} [{w['start']:.2f}-{w['end']:.2f}s] {w['text']}")

    # 逐轮窗口：本轮干扰 = 该用户段；模型侧给出「干扰前最近输出段 + 干扰时/后输出」，
    # 让模型基于整体语义判断 timing（回复过程中 vs 静默），而非只看干扰瞬间是否有词重叠
    model_segs = _to_segments(model_chunks, gap=MODEL_SEG_MERGE_GAP_S) or []
    round_blocks = []
    for k, seg in enumerate(bc_segs, start=1):
        win_s, win_e = float(seg['start']), float(seg['end'])
        u_words = [w for w in words if w['speaker'] == 'query'
                   and w['end'] >= win_s - 0.3 and w['start'] <= win_e + 0.3]
        ut = ' '.join(w['text'] for w in u_words) if u_words else ''
        # 干扰前最近一段模型输出（整体语义上下文）
        prev_model = next((ms for ms in model_segs if float(ms['end']) < win_s), None)
        # 干扰后仍输出：干扰后 8s 内或至下一用户段前的模型输出
        next_user_start = None
        for nxt in bc_segs:
            if float(nxt['start']) > win_e:
                next_user_start = float(nxt['start'])
                break
        after_end = next_user_start if next_user_start is not None else win_e + 8.0
        m_words = [w for w in words if w['speaker'] == 'answer'
                   and w['end'] >= win_s - 0.3 and w['start'] <= after_end]
        mt = ' '.join(w['text'] for w in m_words) if m_words else '（无）'
        if prev_model is not None:
            pt = prev_model.get('text', '')
            pm = f"[{float(prev_model['start']):.2f}-{float(prev_model['end']):.2f}s] {pt}"
        else:
            pm = '（无）'
        round_blocks.append(
            f"轮{k}: 用户干扰段 [{win_s:.2f}-{win_e:.2f}s] ASR: {ut or '（无ASR文本，可能是噪声）'}\n"
            f"    干扰前模型输出(最近一段): {pm}\n"
            f"    干扰时/后模型输出: {mt or '（无）'}"
        )

    request = '\n'.join([
        '【完整词级时间线】',
        '\n'.join(timeline_lines),
        '',
        '【待评估拒识轮】',
        '\n'.join(round_blocks),
    ])

    import re

    judged: List[Dict[str, Any]] = []
    missing = []
    raw_llm_output = ''
    last_error = ''
    # gpt-6-sol 等模型输出有格式波动（轮号可能输出为 "轮1"/"第2轮"/1.0 等），
    # 判定为空时自动重试一次，降低整例失败率
    for attempt in range(2):
        try:
            response = call_llm_api(model=model, prompt=request, system_message=_TEXT_JUDGE_SYSTEM,
                                    max_tokens=max_tokens, temperature=temperature,
                                    log_context={'dimension': 'reject_judge_text',
                                                 'attempt': attempt + 1})
        except Exception as e:
            last_error = f'LLM 调用失败: {e}'
            raw_llm_output = ''
            break

        raw_llm_output = response.get('content', '')
        parsed = parse_json(raw_llm_output)
        if not parsed:
            last_error = 'LLM 输出解析失败'
            continue
        raw_details = parsed.get('round_details')
        if not isinstance(raw_details, list):
            last_error = 'LLM 输出缺少 round_details 数组'
            continue

        by_round = {}
        for item in raw_details:
            if not isinstance(item, dict):
                continue
            rn = item.get('round')
            if isinstance(rn, bool):
                continue
            # 兼容模型把轮号序列化为 "1" / "轮1" / "第2轮" / 1.0 等形态
            if isinstance(rn, str):
                m = re.search(r'\d+', rn.strip())
                rn = int(m.group()) if m else None
            elif isinstance(rn, float) and rn.is_integer():
                rn = int(rn)
            if not isinstance(rn, int):
                continue
            by_round[rn] = item

        judged = []
        missing = []
        for k in range(1, len(bc_segs) + 1):
            item = by_round.get(k)
            if not item:
                missing.append(k)
                continue
            timing = _normalize_timing(str(item.get('timing', '')))
            behavior = _normalize_behavior(str(item.get('behavior', '')))
            reason = str(item.get('reason', '')).strip()
            if timing not in _TEXT_JUDGE_TIMINGS or behavior not in _TEXT_JUDGE_BEHAVIORS:
                missing.append(k)
                continue
            j = _text_judgment_fields(timing, behavior, reason)
            j['round'] = k
            judged.append(j)

        if judged:
            break
        last_error = '所有拒识轮均无法判定'
        logger.warning(f'[reject_judge_text] 第{attempt + 1}次调用无可判定轮，重试: {raw_llm_output[:200]}')

    if not judged:
        return {'enabled': False, 'message': last_error, 'rounds': [],
                'raw_llm_output': raw_llm_output}

    message = 'OK'
    if missing:
        message = f'以下轮次无有效判定，不计入统计: {missing}'
    return {
        'enabled': True,
        'model': model,
        'tokens_used': response.get('tokens_used', 0),
        'input_token': response.get('input_token', 0),
        'output_token': response.get('output_token', 0),
        'rounds': judged,
        'message': message,
    }


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
