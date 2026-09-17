# -*- coding: utf-8 -*-
"""对话轮次切分 + 逐轮三分类评判（误解管 / 接管 / 未接管）

本模块聚合了三大功能：
1. 对话轮次切分：时间戳粗预切 + LLM 语义确认
2. 误解管判断：LLM 主判，复用 false_takeover 的 prompt
3. 接管/未接管判断：TOR 客观数据 + LLM 确认

输出每轮的分类结果，供 turn_eval/strategy.py 汇总为 "正常接管N，未接管M，误解管K"。
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.services.calculators.xiaoyi_metrics.shared.constants import (
    TURN_SPLIT_PRE_GAP_S,
    TURN_SPLIT_MAX_GAP_S,
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
    TIMELINE_MAX_ITEMS_CHUNKS,
    TIMELINE_MAX_ITEMS_PAUSES,
    ASR_USER_SEG_MERGE_GAP_S,
    ASR_MODEL_SEG_MERGE_GAP_S,
)
from app.services.calculators.xiaoyi_metrics.shared.asr_utils import (
    valid_ts,
    compute_pause_intervals,
)
from app.services.calculators.xiaoyi_metrics.shared.llm_client import (
    call_llm,
    parse_json,
    get_llm_config,
    resolve_model,
)
from app.services.calculators.xiaoyi_metrics.turn_taking.tor import compute_tor

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  数据结构
# ═══════════════════════════════════════════════════════════════

class TurnInfo:
    """单轮对话信息"""

    def __init__(self, turn_index: int,
                 user_chunks: List[Dict[str, Any]],
                 ai_chunks: List[Dict[str, Any]],
                 user_start_s: float, user_end_s: float,
                 ai_start_s: Optional[float] = None,
                 ai_end_s: Optional[float] = None):
        self.turn_index = turn_index
        self.user_chunks = user_chunks
        self.ai_chunks = ai_chunks
        self.user_start_s = user_start_s
        self.user_end_s = user_end_s
        self.ai_start_s = ai_start_s
        self.ai_end_s = ai_end_s

    def has_ai_reply(self) -> bool:
        return bool(self.ai_chunks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'turn_index': self.turn_index,
            'user_chunks': self.user_chunks,
            'ai_chunks': self.ai_chunks,
            'user_start_s': self.user_start_s,
            'user_end_s': self.user_end_s,
            'ai_start_s': self.ai_start_s,
            'ai_end_s': self.ai_end_s,
            'has_ai_reply': self.has_ai_reply(),
        }


class TurnClassification:
    """单轮三分类结果"""

    MISUNDERSTAND = '误解管'
    TAKEOVER = '接管'
    NO_TAKEOVER = '未接管'

    def __init__(self, turn_index: int, classification: str,
                 false_takeover: Optional[Dict] = None,
                 tor: Optional[Dict] = None,
                 takeover_judge: Optional[Dict] = None):
        self.turn_index = turn_index
        self.classification = classification
        self.false_takeover = false_takeover
        self.tor = tor
        self.takeover_judge = takeover_judge

    def to_dict(self) -> Dict[str, Any]:
        return {
            'turn_index': self.turn_index,
            'classification': self.classification,
            'false_takeover': self.false_takeover,
            'tor': self.tor,
            'takeover_judge': self.takeover_judge,
        }


# ═══════════════════════════════════════════════════════════════
#  第一部分：对话轮次切分
# ═══════════════════════════════════════════════════════════════

def _cluster_chunks(chunks: List[Dict[str, Any]],
                    gap_threshold: float) -> List[Dict[str, Any]]:
    """将 chunks 按间隔聚类为语音段"""
    if not chunks:
        return []

    segments = []
    cur_chunks = [chunks[0]]
    cur_start, cur_end = valid_ts(chunks[0].get('timestamp'))

    for i in range(1, len(chunks)):
        s, e = valid_ts(chunks[i].get('timestamp'))
        if s - cur_end > gap_threshold:
            segments.append({
                'chunks': cur_chunks,
                'start': cur_start,
                'end': cur_end,
                'text': ''.join(c.get('text', '') for c in cur_chunks),
            })
            cur_chunks = [chunks[i]]
            cur_start, cur_end = s, e
        else:
            cur_chunks.append(chunks[i])
            cur_end = max(cur_end, e)

    segments.append({
        'chunks': cur_chunks,
        'start': cur_start,
        'end': cur_end,
        'text': ''.join(c.get('text', '') for c in cur_chunks),
    })
    return segments


def _find_ai_segments_for_user(user_seg: Dict[str, Any],
                               ai_segments: List[Dict[str, Any]],
                               next_user_start: Optional[float],
                               ) -> List[Dict[str, Any]]:
    """找到用户段之后、下一个用户段之前的 AI 回复段"""
    user_end = user_seg['end']
    boundary = next_user_start if next_user_start is not None else float('inf')
    return [ai_seg for ai_seg in ai_segments
            if ai_seg['start'] >= user_end and ai_seg['start'] < boundary]


def _pre_split_turns(user_chunks: List[Dict[str, Any]],
                     ai_chunks: List[Dict[str, Any]],
                     user_gap: float = TURN_SPLIT_PRE_GAP_S,
                     ai_gap: float = ASR_MODEL_SEG_MERGE_GAP_S,
                     max_no_ai_gap: float = TURN_SPLIT_MAX_GAP_S,
                     ) -> List[TurnInfo]:
    """时间戳粗预切对话轮次

    策略：
    1. 将 user_chunks 按 user_gap 聚类为用户语音段
    2. 将 ai_chunks 按 ai_gap 聚类为 AI 回复段
    3. AI 回复段的出现是轮次边界（强信号）
    4. 无 AI 回复时，用户两段间隔 > max_no_ai_gap 判为不同轮次（弱信号）
    """
    if not user_chunks:
        return []

    user_segments = _cluster_chunks(user_chunks, user_gap)
    ai_segments = _cluster_chunks(ai_chunks, ai_gap) if ai_chunks else []

    turns = []
    turn_idx = 1
    i = 0

    while i < len(user_segments):
        user_seg = user_segments[i]
        next_user_start = None

        if i + 1 < len(user_segments):
            next_seg = user_segments[i + 1]
            gap = next_seg['start'] - user_seg['end']

            has_ai_between = any(
                ai_seg['start'] >= user_seg['end'] and ai_seg['start'] < next_seg['start']
                for ai_seg in ai_segments
            )

            # 判断下一段用户是否只是简短应答（如"啊"、"好的"、"嗯"）
            # 如果是，即使中间有 AI 回复，也合并到当前轮（属于同一轮交互）
            next_text = next_seg['text']
            next_dur = next_seg['end'] - next_seg['start']
            is_brief_response = len(next_text) <= 2 or next_dur < 1.0

            if (has_ai_between and not is_brief_response) or gap > max_no_ai_gap:
                next_user_start = next_seg['start']
            else:
                merged_chunks = user_seg['chunks'] + next_seg['chunks']
                user_seg = {
                    'chunks': merged_chunks,
                    'start': user_seg['start'],
                    'end': next_seg['end'],
                    'text': user_seg['text'] + next_seg['text'],
                }
                next_user_start = None
                i += 1
                while i + 1 < len(user_segments):
                    nx = user_segments[i + 1]
                    g = nx['start'] - user_seg['end']
                    has_ai = any(
                        ai_seg['start'] >= user_seg['end'] and ai_seg['start'] < nx['start']
                        for ai_seg in ai_segments
                    )
                    if has_ai or g > max_no_ai_gap:
                        next_user_start = nx['start']
                        break
                    else:
                        user_seg['chunks'].extend(nx['chunks'])
                        user_seg['end'] = nx['end']
                        user_seg['text'] += nx['text']
                        i += 1

        matched_ai = _find_ai_segments_for_user(user_seg, ai_segments, next_user_start)
        ai_chunks_for_turn = []
        ai_start = None
        ai_end = None
        for ai_seg in matched_ai:
            ai_chunks_for_turn.extend(ai_seg['chunks'])
            if ai_start is None or ai_seg['start'] < ai_start:
                ai_start = ai_seg['start']
            if ai_end is None or ai_seg['end'] > ai_end:
                ai_end = ai_seg['end']

        turns.append(TurnInfo(
            turn_index=turn_idx,
            user_chunks=user_seg['chunks'],
            ai_chunks=ai_chunks_for_turn,
            user_start_s=user_seg['start'],
            user_end_s=user_seg['end'],
            ai_start_s=ai_start,
            ai_end_s=ai_end,
        ))
        turn_idx += 1
        i += 1

    logger.info(
        f"[turn_evaluation] 粗预切完成: {len(turns)} 轮, "
        f"user_segments={len(user_segments)}, ai_segments={len(ai_segments)}"
    )
    return turns


def _format_chunks_timeline(chunks, max_items=TIMELINE_MAX_ITEMS_CHUNKS):
    """将 ASR chunks 格式化为带时间戳的时间线文本"""
    lines = []
    for c in chunks[:max_items]:
        ts = c.get('timestamp')
        text = c.get('text', '')
        if ts and len(ts) >= 2:
            lines.append(f"  [{ts[0]:.2f}-{ts[1]:.2f}] {text}")
        else:
            lines.append(f"  {text}")
    if len(chunks) > max_items:
        lines.append(f"  ...（共 {len(chunks)} 条，已截断）")
    return '\n'.join(lines)


def _format_pause_timeline(pause_intervals, max_items=TIMELINE_MAX_ITEMS_PAUSES):
    """将停顿区间格式化为时间线文本"""
    lines = []
    for p in pause_intervals[:max_items]:
        ts = p.get('timestamp') or [p.get('start'), p.get('end')]
        if ts and len(ts) >= 2:
            dur = ts[1] - ts[0]
            lines.append(f"  [{ts[0]:.2f}-{ts[1]:.2f}] （停顿{dur:.2f}秒）")
    if len(pause_intervals) > max_items:
        lines.append(f"  ...（共 {len(pause_intervals)} 条，已截断）")
    return '\n'.join(lines)


def _build_turn_split_llm_prompt(turns: List[TurnInfo]) -> str:
    """构建轮次确认 LLM prompt"""
    lines = []
    for t in turns:
        user_text = ''.join(c.get('text', '') for c in t.user_chunks[:TIMELINE_MAX_ITEMS_CHUNKS])
        if t.has_ai_reply():
            ai_text = ''.join(c.get('text', '') for c in t.ai_chunks[:TIMELINE_MAX_ITEMS_CHUNKS])
            lines.append(
                f"  候选轮{t.turn_index}: 用户[{t.user_start_s:.1f}-{t.user_end_s:.1f}s] \"{user_text}\" "
                f"→ AI回复[{t.ai_start_s:.1f}-{t.ai_end_s:.1f}s] \"{ai_text}\""
            )
        else:
            lines.append(
                f"  候选轮{t.turn_index}: 用户[{t.user_start_s:.1f}-{t.user_end_s:.1f}s] \"{user_text}\" "
                f"→ 无AI回复"
            )

    timeline = '\n'.join(lines)

    return f"""# 角色：对话轮次分析裁判

## 核心任务
基于给定结构化时序数据，判断这段录音包含几轮完整对话。
每轮对话 = 用户一次完整提问/指令 + 模型可能的回复。

## 重要说明
- 用户可能在同一轮内有停顿（思考、犹豫），这不一定是不同轮次
- 以下数据是时间戳粗预切的结果，可能存在误切或漏切
- 你需要从语义层面判断：用户的不同片段是否属于同一轮表达

## 输入数据（粗预切结果）
{timeline}

## 判定规则
1. 如果用户在一个片段中表达了完整的语义意图（提问/指令），且模型给出了回复，这就是一轮
2. 如果两个相邻用户片段语义上是连续的（比如前半句和后半句），应该合并为一轮
3. 如果两个相邻用户片段语义完全不同（不同的提问/指令），应该是两轮
4. 无 AI 回复的用户片段也算一轮（模型未接管）
5. 用户对模型回复的简短应答（如"啊"、"好的"、"嗯"、"对"）属于同一轮交互的延续，不应单独成轮，应合并到前一轮

## 强制输出格式（必须严格JSON，不要多余解释，不要markdown）
{{"turn_count": 3, "turns": [{{"turn": 1, "user_text": "用户完整文本", "ai_text": "AI回复文本或空", "merged_from": [1, 2]}}]}}
turn_count: 实际轮次数
turns: 每轮的详细信息
merged_from: 如果该轮由多个候选轮合并而来，列出原始候选轮编号（1-based）；未合并则为 [n]"""


def _llm_confirm_turns(turns: List[TurnInfo],
                        task_params: Optional[Dict[str, Any]] = None,
                        ) -> List[TurnInfo]:
    """用 LLM 确认/修正粗预切的轮次"""
    if len(turns) <= 1:
        return turns

    llm_config = get_llm_config()
    if not llm_config.get('api_base_url') or not llm_config.get('api_key'):
        logger.info("[turn_evaluation] LLM 未配置，使用粗预切结果")
        return turns

    model = ''
    if task_params:
        model = task_params.get('llm_model') or ''
    if not model:
        model = resolve_model(dimension='false_takeover')

    max_tokens = int(task_params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS) or LLM_DEFAULT_MAX_TOKENS) if task_params else LLM_DEFAULT_MAX_TOKENS
    temperature = float(task_params.get('temperature', LLM_DEFAULT_TEMPERATURE) or LLM_DEFAULT_TEMPERATURE) if task_params else LLM_DEFAULT_TEMPERATURE

    prompt = _build_turn_split_llm_prompt(turns)

    try:
        resp = call_llm(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            log_context={'dimension': 'turn_split'},
        )
        parsed = parse_json(resp['content']) or {}

        llm_turn_count = parsed.get('turn_count')
        llm_turns = parsed.get('turns', [])

        if not isinstance(llm_turn_count, int) or llm_turn_count < 1:
            logger.warning(f"[turn_evaluation] LLM 返回无效 turn_count={llm_turn_count}，使用粗预切结果")
            return turns

        if llm_turn_count == len(turns):
            logger.info(f"[turn_evaluation] LLM 确认轮次数={llm_turn_count}，与粗预切一致")
            return turns

        if llm_turn_count < len(turns):
            merged_turns = []
            for llm_t in llm_turns:
                if not isinstance(llm_t, dict):
                    continue
                merged_from = llm_t.get('merged_from', [])
                if not isinstance(merged_from, list) or not merged_from:
                    continue

                indices = [idx - 1 for idx in merged_from if isinstance(idx, int) and 1 <= idx <= len(turns)]
                if not indices:
                    continue

                merged_user_chunks = []
                merged_ai_chunks = []
                user_start = float('inf')
                user_end = 0.0
                ai_start = None
                ai_end = None

                for idx in indices:
                    t = turns[idx]
                    merged_user_chunks.extend(t.user_chunks)
                    merged_ai_chunks.extend(t.ai_chunks)
                    user_start = min(user_start, t.user_start_s)
                    user_end = max(user_end, t.user_end_s)
                    if t.ai_start_s is not None:
                        ai_start = t.ai_start_s if ai_start is None else min(ai_start, t.ai_start_s)
                    if t.ai_end_s is not None:
                        ai_end = t.ai_end_s if ai_end is None else max(ai_end, t.ai_end_s)

                if user_start == float('inf'):
                    continue

                merged_turns.append(TurnInfo(
                    turn_index=len(merged_turns) + 1,
                    user_chunks=merged_user_chunks,
                    ai_chunks=merged_ai_chunks,
                    user_start_s=user_start,
                    user_end_s=user_end,
                    ai_start_s=ai_start,
                    ai_end_s=ai_end,
                ))

            if len(merged_turns) == llm_turn_count:
                logger.info(f"[turn_evaluation] LLM 合并后轮次数={llm_turn_count}（原{len(turns)}轮）")
                return merged_turns
            else:
                logger.warning(
                    f"[turn_evaluation] LLM 合并后轮次数={len(merged_turns)}与预期={llm_turn_count}不符，使用粗预切结果"
                )
                return turns

        logger.info(f"[turn_evaluation] LLM 返回更多轮次={llm_turn_count}（粗预切={len(turns)}），使用粗预切结果")
        return turns

    except Exception as e:
        logger.warning(f"[turn_evaluation] LLM 确认轮次失败: {e}，使用粗预切结果")
        return turns


def split_turns(user_chunks: List[Dict[str, Any]],
                ai_chunks: List[Dict[str, Any]],
                task_params: Optional[Dict[str, Any]] = None,
                ) -> List[TurnInfo]:
    """对话轮次切分主入口：粗预切 → LLM 确认"""
    turns = _pre_split_turns(user_chunks, ai_chunks)

    if not turns:
        logger.info("[turn_evaluation] 粗预切结果为空，返回空列表")
        return []

    turns = _llm_confirm_turns(turns, task_params)

    logger.info(f"[turn_evaluation] 最终轮次数: {len(turns)}")
    for t in turns:
        logger.info(
            f"  轮{t.turn_index}: user[{t.user_start_s:.1f}-{t.user_end_s:.1f}s] "
            f"({'有AI回复' if t.has_ai_reply() else '无AI回复'})"
        )

    return turns


# ═══════════════════════════════════════════════════════════════
#  第二部分：误解管判断（LLM 主判）
# ═══════════════════════════════════════════════════════════════

def _build_false_takeover_llm_prompt(user_chunks, ai_chunks, pause_intervals):
    """构建误接管 LLM 判断 prompt（复用 false_takeover.py 中的 prompt）"""
    user_timeline = _format_chunks_timeline(user_chunks)
    pause_timeline = _format_pause_timeline(pause_intervals)
    ai_timeline = _format_chunks_timeline(ai_chunks)

    return f"""# 角色：全双工语音交互话轮裁判

## 核心任务
基于给定结构化时序数据，判定本轮交互是否发生【话轮误接管（误打断）】，并输出判定理由。

## 重要前置约定（必须牢记）
本轮提供的用户语音片段**是完整的、包含用户本轮全部交互意图**的语音。
用户表达行为：不会等待模型是否回复，会一次性完整讲完整轮想说的所有内容，整条用户语音不存在中途主动放弃、提前终止表达的情况。

## 关键术语定义（严格遵循，不得自行修改）
话轮误接管（误打断）：
用户本轮完整表达还未结束（语义不完整、语句仍在延续），模型提前截取用户**中间不完整片段**作为依据生成回复。
重要特例：
若模型语音播报输出时间，晚于用户语音结束时间，但模型回复内容仅依据用户中途不完整片段生成，没有等待用户完整语义，依然判定为【误接管】。
✅ 正常无误接管：模型等待用户本轮全部语义说完，基于用户完整整轮输入生成回复。

## 输入数据说明（你会收到如下结构化信息）
1. 用户侧数据：本轮完整用户语音（保证整条语音片段完整，承载用户本轮全部意图），包含拆分后的多条语句：每条 = 用户文本 + 开始时间戳 + 结束时间戳
2. 模型侧数据：模型本轮完整输出，拆分后的多条回复片段：每条 = 模型文本 + 开始时间戳 + 结束时间戳

【用户侧数据】：
{user_timeline}

【用户停顿区间】：
{pause_timeline or '  （无检测到停顿）'}

【模型侧数据】：
{ai_timeline}

## 判定规则（按优先级执行）
1. 先通读用户全部语句，判断用户完整语义终点：识别用户整轮表达什么时候语义完整结束
2. 对模型每条回复片段逐条分析语义依据：该片段是基于【用户中间局部片段】，还是【用户完整全部输入】。只要有一条片段是基于用户中间不完整片段生成的回复，即判定为误接管
3. 特别关注"先短回应→停顿→重新完整回复"模式：若模型先输出一句简短的局部回应（如回应用户的犹豫、停顿、情绪），间隔后再给出实质性完整回复，属于先误接管再纠正的典型模式，判定为误接管
4. 不只用物理播放时间判断！必须结合语义上下文：
   - 模型回复内容只回应用户前半段话，忽略用户后半补充内容 → 大概率误接管
   - 用户后半句是补充、修正、延续前文，模型完全没有纳入理解 → 判定误接管
5. 边界区分：
   - 用户单句语义完整收尾，无后续补充语句，模型正常应答 → 不属于误接管
   - 用户仍有后续延续语句未说完，模型在表达过程中截取中间内容生成回复 → 属于误接管
6. 【关键边界】语义理解错误 ≠ 话轮误接管：
   - 模型在用户完整表达结束后才开始回复，但回复内容语义上有误（如忽略了否定词、理解偏差、答非所问）→ 不属于误接管，属于回复质量问题
   - 只有当模型在用户表达尚未结束时，截取中间不完整片段抢先回复，才是误接管
   - 区分标准：看模型是否等待了用户本轮完整表达结束。若已等待完整表达，无论回复内容质量如何，均不属于误接管

## 强制输出格式（必须严格JSON，不要多余解释，不要markdown）
{{"judge_result": "true", "explanation": "判定详细理由", "evidence": {{"user_utterance_used_by_model": "模型所依据的用户片段文本", "user_full_utterance": "用户本轮完整全部文本"}}}}
judge_result 说明：true = 存在话轮误接管；false = 无话轮误接管"""


def judge_false_takeover(user_chunks, ai_chunks, pause_intervals,
                         task_params: Optional[Dict[str, Any]] = None,
                         ) -> Dict[str, Any]:
    """逐轮误解管判断（LLM 主判）

    Args:
        user_chunks: 该轮用户 ASR chunks
        ai_chunks: 该轮 AI ASR chunks
        pause_intervals: 该轮用户停顿区间
        task_params: 读取 llm_model 配置

    Returns:
        dict: {
            'false_takeover': int,   1=误解管, 0=非误解管
            'reason': str,           判断理由
            'evidence': dict,        证据信息
        }
    """
    result = {
        'false_takeover': 0,
        'reason': '',
        'evidence': {},
    }

    if not ai_chunks:
        result['reason'] = '无 AI 回复，不存在误解管'
        return result

    llm_config = get_llm_config()
    if not llm_config.get('api_base_url') or not llm_config.get('api_key'):
        result['reason'] = 'LLM未配置，默认非误解管'
        return result

    if not user_chunks:
        result['reason'] = '无用户ASR数据，默认非误解管'
        return result

    model = ''
    if task_params:
        model = task_params.get('llm_model') or ''
    if not model:
        model = resolve_model(dimension='false_takeover')

    max_tokens = int(task_params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS) or LLM_DEFAULT_MAX_TOKENS) if task_params else LLM_DEFAULT_MAX_TOKENS
    temperature = float(task_params.get('temperature', LLM_DEFAULT_TEMPERATURE) or LLM_DEFAULT_TEMPERATURE) if task_params else LLM_DEFAULT_TEMPERATURE

    prompt = _build_false_takeover_llm_prompt(user_chunks, ai_chunks, pause_intervals)

    try:
        resp = call_llm(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            log_context={'dimension': 'false_takeover_per_turn'},
        )
        parsed = parse_json(resp['content']) or {}

        judge = parsed.get('judge_result')
        if isinstance(judge, str):
            ft_val = 1 if judge.strip().lower() in ('true', '1', '是') else 0
        elif isinstance(judge, bool):
            ft_val = 1 if judge else 0
        else:
            ft_val = 0

        result['false_takeover'] = ft_val
        result['reason'] = str(parsed.get('explanation', ''))
        result['evidence'] = parsed.get('evidence') or {}

        logger.info(
            f"[turn_evaluation] 误解管LLM判定: false_takeover={ft_val} "
            f"reason={result['reason']!r}"
        )
        return result

    except Exception as e:
        logger.warning(f"[turn_evaluation] 误解管LLM调用失败: {e}，默认非误解管")
        result['reason'] = f'LLM调用失败: {e}'
        return result


# ═══════════════════════════════════════════════════════════════
#  第三部分：接管/未接管判断（TOR 客观数据 + LLM 确认）
# ═══════════════════════════════════════════════════════════════

def _build_takeover_judge_prompt(user_chunks, ai_chunks,
                                tor_n_words: int, tor_duration: float,
                                ) -> str:
    """构建接管/未接管 LLM 判断 prompt"""
    user_text = ''.join(c.get('text', '') for c in user_chunks[:TIMELINE_MAX_ITEMS_CHUNKS])
    ai_text = ''.join(c.get('text', '') for c in ai_chunks[:TIMELINE_MAX_ITEMS_CHUNKS]) if ai_chunks else ''

    user_lines = []
    for c in user_chunks[:TIMELINE_MAX_ITEMS_CHUNKS]:
        ts = c.get('timestamp')
        text = c.get('text', '')
        if ts and len(ts) >= 2:
            user_lines.append(f"  [{ts[0]:.2f}-{ts[1]:.2f}] {text}")
    user_timeline = '\n'.join(user_lines)

    ai_lines = []
    for c in (ai_chunks or [])[:TIMELINE_MAX_ITEMS_CHUNKS]:
        ts = c.get('timestamp')
        text = c.get('text', '')
        if ts and len(ts) >= 2:
            ai_lines.append(f"  [{ts[0]:.2f}-{ts[1]:.2f}] {text}")
    ai_timeline = '\n'.join(ai_lines) if ai_lines else '  （无AI回复）'

    tor_meets = (tor_duration >= 1.0) or (tor_n_words > 3)
    tor_desc = (
        f"AI回复词数(n_words)={tor_n_words}，回复时长(duration)={tor_duration:.3f}s，"
        f"客观阈值判定: {'满足接管条件(≥1s或>3词)' if tor_meets else '不满足接管条件(<1s且≤3词)'}"
    )

    return f"""# 角色：语音交互接管判断裁判

## 核心任务
判断模型是否对用户的提问/指令进行了有效接管（有效回复）。

## 判断标准
- **接管**：模型在用户表达结束后给出了语音回复。只要模型开口进行了实质性的语音回复（有实际内容、构成对话行为），即算接管。包括但不限于：直接回答、提供建议、询问澄清、表示未听清要求重复、表示需要思考等——这些都是模型接管了话轮、参与了对话交互。
- **未接管**：模型完全未回复，或仅输出无意义的简单语气词（如单个"嗯"、"啊"、"哦"），不构成任何对话行为。

## 重要边界说明
- "未听清要求重复"、"等我想一想"等回复虽然未直接回答用户问题，但模型已接管话轮并进行了对话交互，应判为"接管"。回复质量的高低不影响接管判定，质量问题是回复质量评分模块的职责。
- 只有模型完全沉默或仅发出无意义单字语气词时，才判为"未接管"。

## 客观参考数据
TOR（Take-Off Rate）客观算法结果：
{tor_desc}

注意：客观数据仅作为参考。即使客观条件满足（词数>3或时长≥1s），如果回复仅为无意义语气词，也应判为"未接管"。反之，客观条件不满足但回复确实有效（如简短但准确的回答），也可判为"接管"。

## 输入数据
【用户提问时间线】：
{user_timeline}

【用户提问文本】：{user_text}

【模型回复时间线】：
{ai_timeline}

【模型回复文本】：{ai_text or '（无回复）'}

## 强制输出格式（必须严格JSON，不要多余解释，不要markdown）
{{"takeover": "true", "reason": "判断理由", "user_text": "用户提问文本", "ai_text": "模型回复文本"}}
takeover 说明：true = 接管（有效回复）；false = 未接管"""


def judge_takeover(user_chunks, ai_chunks,
                   tor_n_words: int = 0, tor_duration: float = 0.0,
                   task_params: Optional[Dict[str, Any]] = None,
                   ) -> Dict[str, Any]:
    """LLM 判断模型是否有效接管

    Args:
        user_chunks: 该轮用户 ASR chunks
        ai_chunks: 该轮 AI ASR chunks
        tor_n_words: TOR 命中词数
        tor_duration: TOR 命中词时长
        task_params: 读取 llm_model 配置

    Returns:
        dict: {
            'takeover': int,     1=接管, 0=未接管
            'reason': str,       判断理由
            'tor_n_words': int,  TOR 客观词数
            'tor_duration': float, TOR 客观时长
        }
    """
    result = {
        'takeover': 0,
        'reason': '',
        'tor_n_words': tor_n_words,
        'tor_duration': round(tor_duration, 3),
    }

    if not ai_chunks:
        result['takeover'] = 0
        result['reason'] = '无 AI 回复，判为未接管'
        return result

    llm_config = get_llm_config()
    if not llm_config.get('api_base_url') or not llm_config.get('api_key'):
        took_over = (tor_duration >= 1.0) or (tor_n_words > 3)
        result['takeover'] = 1 if took_over else 0
        result['reason'] = f'LLM未配置，使用TOR客观逻辑: n_words={tor_n_words}, duration={tor_duration:.3f}s'
        return result

    model = ''
    if task_params:
        model = task_params.get('llm_model') or ''
    if not model:
        model = resolve_model(dimension='false_takeover')

    max_tokens = int(task_params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS) or LLM_DEFAULT_MAX_TOKENS) if task_params else LLM_DEFAULT_MAX_TOKENS
    temperature = float(task_params.get('temperature', LLM_DEFAULT_TEMPERATURE) or LLM_DEFAULT_TEMPERATURE) if task_params else LLM_DEFAULT_TEMPERATURE

    prompt = _build_takeover_judge_prompt(user_chunks, ai_chunks, tor_n_words, tor_duration)

    try:
        resp = call_llm(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            log_context={'dimension': 'takeover_judge'},
        )
        parsed = parse_json(resp['content']) or {}

        takeover_val = parsed.get('takeover')
        if isinstance(takeover_val, str):
            result['takeover'] = 1 if takeover_val.strip().lower() in ('true', '1', '是') else 0
        elif isinstance(takeover_val, bool):
            result['takeover'] = 1 if takeover_val else 0
        else:
            result['takeover'] = 0

        result['reason'] = str(parsed.get('reason', ''))

        logger.info(
            f"[turn_evaluation] 接管LLM判定: takeover={result['takeover']} "
            f"reason={result['reason']!r}"
        )
        return result

    except Exception as e:
        logger.warning(f"[turn_evaluation] 接管LLM调用失败: {e}，回退到TOR客观逻辑")
        took_over = (tor_duration >= 1.0) or (tor_n_words > 3)
        result['takeover'] = 1 if took_over else 0
        result['reason'] = f'LLM调用失败，回退TOR客观逻辑: {e}'
        return result


# ═══════════════════════════════════════════════════════════════
#  主入口：逐轮三分类
# ═══════════════════════════════════════════════════════════════

def evaluate_all_turns(user_chunks: List[Dict[str, Any]],
                       ai_chunks: List[Dict[str, Any]],
                       task_params: Optional[Dict[str, Any]] = None,
                       ) -> Tuple[List[TurnInfo], List[TurnClassification]]:
    """逐轮三分类主入口

    流程：
    1. 对话轮次切分（split_turns）
    2. 逐轮：
       a. 误解管判断（LLM）→ true → 误解管
       b. TOR 客观数据 + 接管/未接管 LLM 判断
       c. 接管 → 分类=接管；否则 → 分类=未接管

    Args:
        user_chunks: 用户侧 ASR chunks
        ai_chunks: AI 侧 ASR chunks
        task_params: 读取 llm_model 配置

    Returns:
        (turns, classifications): 轮次列表 + 每轮分类结果
    """
    # 1. 轮次切分
    turns = split_turns(user_chunks, ai_chunks, task_params)

    classifications = []

    for turn in turns:
        # 该轮的 pause_intervals
        turn_pauses = compute_pause_intervals(turn.user_chunks) if turn.user_chunks else []

        # 2a. 误解管判断
        ft_result = judge_false_takeover(
            turn.user_chunks, turn.ai_chunks, turn_pauses, task_params,
        )

        if ft_result['false_takeover'] == 1:
            classifications.append(TurnClassification(
                turn_index=turn.turn_index,
                classification=TurnClassification.MISUNDERSTAND,
                false_takeover=ft_result,
            ))
            continue

        # 2b. TOR 客观数据
        tor_result = compute_tor(turn.user_chunks, turn.ai_chunks or [])

        # 2c. 接管/未接管 LLM 判断
        takeover_result = judge_takeover(
            turn.user_chunks, turn.ai_chunks,
            tor_n_words=tor_result['n_words'],
            tor_duration=tor_result['duration'],
            task_params=task_params,
        )

        if takeover_result['takeover'] == 1:
            classifications.append(TurnClassification(
                turn_index=turn.turn_index,
                classification=TurnClassification.TAKEOVER,
                false_takeover=ft_result,
                tor=tor_result,
                takeover_judge=takeover_result,
            ))
        else:
            classifications.append(TurnClassification(
                turn_index=turn.turn_index,
                classification=TurnClassification.NO_TAKEOVER,
                false_takeover=ft_result,
                tor=tor_result,
                takeover_judge=takeover_result,
            ))

    # 汇总日志
    normal = sum(1 for c in classifications if c.classification == TurnClassification.TAKEOVER)
    no_take = sum(1 for c in classifications if c.classification == TurnClassification.NO_TAKEOVER)
    false_take = sum(1 for c in classifications if c.classification == TurnClassification.MISUNDERSTAND)
    logger.info(
        f"[turn_evaluation] 三分类汇总: 正常接管{normal}，"
        f"未接管{no_take}，误解管{false_take}，共{len(turns)}轮"
    )

    return turns, classifications
