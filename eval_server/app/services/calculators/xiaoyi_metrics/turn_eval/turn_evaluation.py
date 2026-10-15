# -*- coding: utf-8 -*-
"""对话轮次切分 + 逐轮三分类评判（误接管 / 接管 / 未接管）

本模块聚合了三大功能：
1. 对话轮次切分：
   - 有 query 文本：用每轮 query 匹配 ASR chunks 到对应轮次（LLM 完成，保留时间戳）
   - 无 query 文本：时间戳粗预切 + LLM 语义确认（回退）
2. 逐轮三分类（综合 prompt 一次性判定误接管/接管/未接管）：
   - classify_turn_comprehensive：单一 prompt 综合判定，不短路
   - 回退：classify_turn（先误接管 → 再接管/未接管，短路逻辑）

输出每轮的分类结果，供 turn_eval/strategy.py 汇总为 "正常接管N，未接管M，误接管K"。
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

    MISUNDERSTAND = '误接管'
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
    """找到本轮用户发言期间及之后、下一个用户段之前的 AI 回复段

    起点取 user_seg['start']（而非 user_end）：全双工下模型可能在本轮用户说话中途
    插话（停顿词/短插入），这些正是误接管信号，必须并入本轮 ai_chunks 供 LLM 判定；
    合并轮（用户多段连续发言）时轮内插话也在此窗口内。
    """
    user_start = user_seg['start']
    boundary = next_user_start if next_user_start is not None else float('inf')
    return [ai_seg for ai_seg in ai_segments
            if ai_seg['start'] >= user_start and ai_seg['start'] < boundary]


def _pre_split_turns(user_chunks: List[Dict[str, Any]],
                     ai_chunks: List[Dict[str, Any]],
                     user_gap: float = TURN_SPLIT_PRE_GAP_S,
                     ai_gap: float = ASR_MODEL_SEG_MERGE_GAP_S,
                     max_no_ai_gap: float = TURN_SPLIT_MAX_GAP_S,
                     one_turn: bool = False,
                     ) -> List[TurnInfo]:
    """时间戳粗预切对话轮次

    策略（轮次边界只由**用户语音停顿**决定，模型反馈不参与切轮）：
    1. 将 user_chunks 按 user_gap 聚类为用户语音段
    2. 将 ai_chunks 按 ai_gap 聚类为 AI 回复段（仅用于并入各轮的 ai_chunks，不切轮）
    3. 用户两段间隔 > max_no_ai_gap 判为不同轮次；否则合并为同一轮。
       模型在两段之间说了什么（停顿词/实质性回复）都不改变轮次数，
       中途插话作为误接管信号随本轮 ai_chunks 交给 LLM 判定。
    4. 下一段用户是简短应答（如"啊"、"好的"、"嗯"）时并入当前轮，不单独成轮

    one_turn=True：按配置轮次切分——整轮 user_chunks + ai_chunks 合并为 1 个话轮，
    轮内不再切分（用户连续多次提问、模型最后一次性回复的场景视为 1 轮）。
    """
    if not user_chunks:
        return []

    # 按配置轮次切分：1 配置轮次 = 1 话轮，轮内不做音频切分
    if one_turn:
        u_start, _ = valid_ts(user_chunks[0].get('timestamp'))
        _, u_end = valid_ts(user_chunks[-1].get('timestamp'))
        ai_all = ai_chunks or []
        ai_start = None
        ai_end = None
        if ai_all:
            ai_start, _ = valid_ts(ai_all[0].get('timestamp'))
            _, ai_end = valid_ts(ai_all[-1].get('timestamp'))
        return [TurnInfo(
            turn_index=1,
            user_chunks=user_chunks,
            ai_chunks=ai_all,
            user_start_s=u_start,
            user_end_s=u_end,
            ai_start_s=ai_start,
            ai_end_s=ai_end,
        )]

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

            # 下一段用户是否只是简短应答（如"啊"、"好的"、"嗯"）——并入当前轮。
            # 只按字数（≤2 字）判断：不能用"时长<1s"（语速快的完整提问如"你会唱歌吗"
            # 0.97s 说完也会被误判为简短应答而错误并入前一轮）
            next_text = next_seg['text']
            is_brief_response = len(next_text) <= 2

            # 轮次边界只由用户停顿决定：间隔 > max_no_ai_gap 且非简短应答 → 不同轮次；
            # 模型在两段之间说了什么都不参与切轮（中途插话作为误接管信号随本轮 ai_chunks 判定）
            if gap > max_no_ai_gap and not is_brief_response:
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
                    nx_text = nx['text']
                    if g > max_no_ai_gap and len(nx_text) > 2:
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
                one_turn: bool = False,
                ) -> List[TurnInfo]:
    """对话轮次切分主入口：粗预切 → LLM 确认

    one_turn=True：按配置轮次切分，整轮合并为 1 个话轮，跳过 LLM 确认（无合并对象）。
    """
    turns = _pre_split_turns(user_chunks, ai_chunks, one_turn=one_turn)

    if not turns:
        logger.info("[turn_evaluation] 粗预切结果为空，返回空列表")
        return []

    if one_turn:
        logger.info("[turn_evaluation] 按配置轮次切分: 整轮合并为 1 个话轮")
        return turns

    turns = _llm_confirm_turns(turns, task_params)

    logger.info(f"[turn_evaluation] 最终轮次数: {len(turns)}")
    for t in turns:
        logger.info(
            f"  轮{t.turn_index}: user[{t.user_start_s:.1f}-{t.user_end_s:.1f}s] "
            f"({'有AI回复' if t.has_ai_reply() else '无AI回复'})"
        )

    return turns


# ═══════════════════════════════════════════════════════════════
#  第二部分：误接管判断（LLM 主判）
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
    """逐轮误接管判断（LLM 主判）

    Args:
        user_chunks: 该轮用户 ASR chunks
        ai_chunks: 该轮 AI ASR chunks
        pause_intervals: 该轮用户停顿区间
        task_params: 读取 llm_model 配置

    Returns:
        dict: {
            'false_takeover': int,   1=误接管, 0=非误接管
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
        result['reason'] = '无 AI 回复，不存在误接管'
        return result

    llm_config = get_llm_config()
    if not llm_config.get('api_base_url') or not llm_config.get('api_key'):
        result['reason'] = 'LLM未配置，默认非误接管'
        return result

    if not user_chunks:
        result['reason'] = '无用户ASR数据，默认非误接管'
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
            f"[turn_evaluation] 误接管LLM判定: false_takeover={ft_val} "
            f"reason={result['reason']!r}"
        )
        return result

    except Exception as e:
        # LLM 调用失败不再降级兜底：误接管判定不可信，整任务置为失败
        logger.error(f"[turn_evaluation] 误接管LLM调用失败，任务置为失败: {e}")
        raise


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
        # LLM 调用失败不再降级兜底：接管判定不可信，整任务置为失败
        logger.error(f"[turn_evaluation] 接管LLM调用失败，任务置为失败: {e}")
        raise


# ═══════════════════════════════════════════════════════════════
#  主入口：逐轮三分类
# ═══════════════════════════════════════════════════════════════

def classify_turn(turn: TurnInfo,
                  task_params: Optional[Dict[str, Any]] = None,
                  ) -> TurnClassification:
    """单轮三分类（误接管 → TOR 客观 + 接管判断 → 接管/未接管）

    evaluate_all_turns（ASR 切轮）与 turn_eval 锚点定轮次（_build_turns_from_anchors）
    共用同一判定口径，保证不同轮次来源的分类结果可比。

    Args:
        turn: 单轮对话（user_chunks + ai_chunks + 时间戳）
        task_params: 读取 llm_model 配置

    Returns:
        TurnClassification: 误接管 / 接管 / 未接管 之一
    """
    # 该轮的 pause_intervals
    turn_pauses = compute_pause_intervals(turn.user_chunks) if turn.user_chunks else []

    # 2a. 误接管判断
    ft_result = judge_false_takeover(
        turn.user_chunks, turn.ai_chunks, turn_pauses, task_params,
    )

    if ft_result['false_takeover'] == 1:
        return TurnClassification(
            turn_index=turn.turn_index,
            classification=TurnClassification.MISUNDERSTAND,
            false_takeover=ft_result,
        )

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
        return TurnClassification(
            turn_index=turn.turn_index,
            classification=TurnClassification.TAKEOVER,
            false_takeover=ft_result,
            tor=tor_result,
            takeover_judge=takeover_result,
        )
    return TurnClassification(
        turn_index=turn.turn_index,
        classification=TurnClassification.NO_TAKEOVER,
        false_takeover=ft_result,
        tor=tor_result,
        takeover_judge=takeover_result,
    )


# ═══════════════════════════════════════════════════════════════
#  新流程：query 匹配轮次 + 综合三分类 prompt
# ═══════════════════════════════════════════════════════════════

# 说话人前缀正则（参考打断 round_metrics._SPEAKER_PREFIX_RE）
_SPEAKER_PREFIX_RE = __import__('re').compile(r'^\s*用户\d*\s*[:：]\s*')


def _norm_text(text: str) -> str:
    """文本归一化：剥说话人前缀 + 转小写 + 去标点 + 压空白

    参考打断 round_metrics._anchor_norm_text → input_asr._normalize_text
    """
    if not text:
        return ''
    text = _SPEAKER_PREFIX_RE.sub('', str(text))
    text = text.lower()
    text = __import__('re').sub(r'[^\w\s\u4e00-\u9fff]', '', text)
    text = __import__('re').sub(r'\s+', ' ', text).strip()
    return text


def _match_turns_by_text_similarity(
        round_queries: List[str],
        user_chunks: List[Dict[str, Any]],
        ai_chunks: List[Dict[str, Any]],
        ) -> Tuple[List[TurnInfo], List[int]]:
    """本地文本相似度匹配（LLM 失败时的回退，参考打断 locate_text_window）

    用 difflib.SequenceMatcher 将每轮 query 与 ASR 用户段做模糊匹配，
    命中窗口内的用户 chunks = 本轮用户发言，窗口后到下一轮窗口前的 AI chunks = 本轮回复。
    单调时间约束：后续轮匹配起点不早于前轮锚点末端。

    Returns:
        (turns, round_numbers): 轮次列表 + 每轮真实轮次索引；无匹配返回空
    """
    import difflib
    from app.services.calculators.xiaoyi_metrics.shared.asr_utils import to_segments_with_text
    from app.services.calculators.xiaoyi_metrics.shared.constants import (
        TEXT_ANCHOR_SIMILARITY_THRESHOLD,
        TEXT_ANCHOR_MONOTONIC_TOLERANCE_S,
        ASR_USER_SEG_MERGE_GAP_S,
    )

    user_segs = to_segments_with_text(user_chunks, ASR_USER_SEG_MERGE_GAP_S)
    if not user_segs:
        return [], []

    turns = []
    round_numbers = []
    after = None  # 单调约束：后续轮起点不早于前轮末端 - 容差

    for rn, query in enumerate(round_queries):
        q = _norm_text(query)
        if not q:
            continue

        best = None  # (sim, seg_start, seg_end)
        for i, (s, e, text) in enumerate(user_segs):
            if after is not None and s < after - TEXT_ANCHOR_MONOTONIC_TOLERANCE_S:
                continue
            acc = ''
            for j in range(i, min(i + 3, len(user_segs))):
                acc += _norm_text(user_segs[j][2])
                if not acc:
                    continue
                sim = difflib.SequenceMatcher(None, q, acc).ratio()
                if sim >= TEXT_ANCHOR_SIMILARITY_THRESHOLD and (best is None or sim > best[0]):
                    best = (sim, user_segs[i][0], user_segs[j][1])

        if best is None:
            logger.warning(f"[turn_evaluation] 文本相似度匹配: 轮{rn} query 未命中")
            continue

        u_start, u_end = best[1], best[2]
        # 下一轮窗口起点（用于界定本轮 AI 回复范围）
        next_start = None
        # 找下一个有 query 的轮的匹配窗口
        for rn2 in range(rn + 1, len(round_queries)):
            q2 = _norm_text(round_queries[rn2])
            if not q2:
                continue
            best2 = None
            for i, (s, e, text) in enumerate(user_segs):
                if s <= u_end:
                    continue
                acc = ''
                for j in range(i, min(i + 3, len(user_segs))):
                    acc += _norm_text(user_segs[j][2])
                    if not acc:
                        continue
                    sim = difflib.SequenceMatcher(None, q2, acc).ratio()
                    if sim >= TEXT_ANCHOR_SIMILARITY_THRESHOLD and (best2 is None or sim > best2[0]):
                        best2 = (sim, user_segs[i][0], user_segs[j][1])
            if best2:
                next_start = best2[1]
                break

        # 本轮用户 chunks：窗口内的 ASR 词
        t_user_chunks = [
            c for c in user_chunks
            if valid_ts(c.get('timestamp'))[0] >= u_start - 0.1
            and valid_ts(c.get('timestamp'))[1] <= u_end + 0.1
        ]
        # 本轮 AI chunks：用户说完后、下一轮用户之前
        boundary = next_start if next_start is not None else float('inf')
        t_ai_chunks = [
            c for c in (ai_chunks or [])
            if u_start <= valid_ts(c.get('timestamp'))[0] < boundary
        ]

        turn = TurnInfo(
            turn_index=len(turns) + 1,
            user_chunks=t_user_chunks,
            ai_chunks=t_ai_chunks,
            user_start_s=u_start,
            user_end_s=u_end,
            ai_start_s=min(valid_ts(c.get('timestamp'))[0] for c in t_ai_chunks) if t_ai_chunks else None,
            ai_end_s=max(valid_ts(c.get('timestamp'))[1] for c in t_ai_chunks) if t_ai_chunks else None,
        )
        turns.append(turn)
        round_numbers.append(rn)
        after = u_end

        logger.info(
            f"[turn_evaluation] 文本匹配 轮{rn}: sim={best[0]:.2f} "
            f"user[{u_start:.1f}-{u_end:.1f}s] "
            f"u_chunks={len(t_user_chunks)} a_chunks={len(t_ai_chunks)}"
        )

    if not turns:
        logger.warning("[turn_evaluation] 文本相似度匹配全部未命中")
        return [], []

    logger.info(f"[turn_evaluation] 文本相似度匹配完成: {len(turns)} 轮")
    return turns, round_numbers


def _extract_round_queries(task_params: Optional[Dict[str, Any]]) -> List[str]:
    """从 task_params['rounds'] 提取每轮 query 文本列表

    Returns:
        list[str]: 每轮 query 文本，无 query 的轮返回空字符串
    """
    if not task_params:
        return []
    rounds = task_params.get('rounds') or []
    if not (rounds and isinstance(rounds, list)):
        return []
    queries = []
    for rd in rounds:
        if isinstance(rd, dict):
            q = rd.get('query') or rd.get('round_query') or ''
            # 兼容平台映射产物：reference 来源的 query 为 {'text': ..., 'json': []}
            # （参考打断 interruptibility 的 unwrap 写法），先解包再取文本
            if isinstance(q, dict) and 'text' in q:
                q = q['text']
            queries.append(str(q).strip() if q else '')
        else:
            queries.append('')
    return queries


def _build_query_match_prompt(round_queries: List[str],
                              user_chunks: List[Dict[str, Any]],
                              ai_chunks: List[Dict[str, Any]],
                              ) -> str:
    """构建 query 匹配轮次 LLM prompt

    将每轮的 query 文本 + 完整 ASR 时间线（用户 + AI，带时间戳）交给 LLM，
    让 LLM 把 ASR chunks 归属到对应轮次。
    """
    # 轮次 query 列表
    round_lines = []
    for i, q in enumerate(round_queries):
        round_lines.append(f'  轮次{i}: query="{q}"')
    rounds_text = '\n'.join(round_lines)

    # 用户 ASR 时间线
    user_lines = []
    for idx, c in enumerate(user_chunks[:TIMELINE_MAX_ITEMS_CHUNKS]):
        ts = c.get('timestamp')
        text = c.get('text', '')
        if ts and len(ts) >= 2:
            user_lines.append(f'  [{ts[0]:.2f}-{ts[1]:.2f}] #{idx} {text}')
        else:
            user_lines.append(f'  #{idx} {text}')
    if len(user_chunks) > TIMELINE_MAX_ITEMS_CHUNKS:
        user_lines.append(f'  ...（共 {len(user_chunks)} 条，已截断）')
    user_timeline = '\n'.join(user_lines) if user_lines else '  （无用户ASR数据）'

    # AI ASR 时间线
    ai_lines = []
    for idx, c in enumerate((ai_chunks or [])[:TIMELINE_MAX_ITEMS_CHUNKS]):
        ts = c.get('timestamp')
        text = c.get('text', '')
        if ts and len(ts) >= 2:
            ai_lines.append(f'  [{ts[0]:.2f}-{ts[1]:.2f}] #{idx} {text}')
        else:
            ai_lines.append(f'  #{idx} {text}')
    if len(ai_chunks or []) > TIMELINE_MAX_ITEMS_CHUNKS:
        ai_lines.append(f'  ...（共 {len(ai_chunks)} 条，已截断）')
    ai_timeline = '\n'.join(ai_lines) if ai_lines else '  （无AI回复ASR数据）'

    return f"""# 角色：全双工语音交互轮次匹配裁判

## 核心任务
根据每轮的预期 query 文本，将 ASR 转写的用户语音片段和 AI 回复片段归属到对应的对话轮次。
通过语义匹配（而非字面完全一致，ASR 可能有识别误差），判断每个 ASR 片段属于哪一轮。

## 输入数据

### 各轮预期 query（用户本轮应说的话）
{rounds_text}

### 用户侧 ASR 时间线（带序号 #N 和时间戳）
{user_timeline}

### AI 侧 ASR 时间线（带序号 #N 和时间戳）
{ai_timeline}

## 匹配规则
1. 语义匹配：ASR 转写可能有误差，按语义相似度匹配，不要求字面完全一致
2. 时间顺序：轮次按时间排列，轮次0的用户片段应在轮次1之前
3. 每个 ASR 片段最多归属一个轮次，无匹配的片段可标记为 -1
4. AI 回复片段归属到其回复的那个轮次（通常在该轮用户片段之后、下一轮用户片段之前）
5. 用户对模型回复的简短应答（如"啊""好的""嗯"）归到前一轮

## 强制输出格式（必须严格JSON，不要多余解释，不要markdown）
{{"rounds": [
  {{"round": 0, "user_chunks": [0, 1, 2], "ai_chunks": [0, 1], "user_text": "匹配到的用户文本", "ai_text": "匹配到的AI回复文本"}},
  {{"round": 1, "user_chunks": [3, 4], "ai_chunks": [2, 3], "user_text": "...", "ai_text": "..."}}
]}}
round: 轮次序号（0-based，对应输入的轮次序号）
user_chunks: 该轮用户 ASR 片段的序号列表（#N 中的 N）
ai_chunks: 该轮 AI ASR 片段的序号列表（#N 中的 N）
user_text: 该轮匹配到的用户文本拼接
ai_text: 该轮匹配到的AI回复文本拼接"""


def split_turns_by_query(user_chunks: List[Dict[str, Any]],
                         ai_chunks: List[Dict[str, Any]],
                         task_params: Optional[Dict[str, Any]] = None,
                         ) -> Tuple[List[TurnInfo], List[int]]:
    """用每轮 query 文本匹配 ASR chunks 到对应轮次（LLM 完成，保留时间戳）

    匹配优先级：
    1. LLM 语义匹配：将 query 文本 + 完整 ASR 时间线交给 LLM，LLM 返回每轮对应的 chunks 序号
    2. 本地文本相似度匹配（回退）：difflib.SequenceMatcher 模糊匹配 query ↔ ASR 用户段
       参考打断 round_metrics.locate_text_window

    Args:
        user_chunks: 用户侧 ASR chunks（来自 FFT 对齐后的干净音频）
        ai_chunks:  AI 侧 ASR chunks
        task_params: 读取 rounds[*].query 和 llm_model 配置

    Returns:
        (turns, round_numbers): 轮次列表 + 每轮真实轮次索引
    """
    round_queries = _extract_round_queries(task_params)
    if not round_queries or not any(round_queries):
        logger.info("[turn_evaluation] 无 query 文本，回退 ASR 切轮")
        return [], []

    llm_config = get_llm_config()
    if not llm_config.get('api_base_url') or not llm_config.get('api_key'):
        # LLM 未配置 → 直接走本地文本相似度匹配
        logger.info("[turn_evaluation] LLM 未配置，尝试本地文本相似度匹配")
        return _match_turns_by_text_similarity(round_queries, user_chunks, ai_chunks)

    model = ''
    if task_params:
        model = task_params.get('llm_model') or ''
    if not model:
        model = resolve_model(dimension='false_takeover')

    max_tokens = int(task_params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS) or LLM_DEFAULT_MAX_TOKENS) if task_params else LLM_DEFAULT_MAX_TOKENS
    temperature = float(task_params.get('temperature', LLM_DEFAULT_TEMPERATURE) or LLM_DEFAULT_TEMPERATURE) if task_params else LLM_DEFAULT_TEMPERATURE

    prompt = _build_query_match_prompt(round_queries, user_chunks, ai_chunks)

    try:
        resp = call_llm(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            log_context={'dimension': 'turn_split_by_query'},
        )
        parsed = parse_json(resp['content']) or {}

        llm_rounds = parsed.get('rounds', [])
        if not isinstance(llm_rounds, list) or not llm_rounds:
            logger.warning("[turn_evaluation] LLM 返回空 rounds，回退 ASR 切轮")
            return [], []

        turns = []
        round_numbers = []
        for llm_round in llm_rounds:
            if not isinstance(llm_round, dict):
                continue
            rn = llm_round.get('round')
            if rn is None:
                continue
            rn = int(rn)

            # 按 LLM 返回的序号取 chunks
            user_indices = llm_round.get('user_chunks', [])
            ai_indices = llm_round.get('ai_chunks', [])
            if not isinstance(user_indices, list):
                user_indices = []
            if not isinstance(ai_indices, list):
                ai_indices = []

            t_user_chunks = [
                user_chunks[idx] for idx in user_indices
                if isinstance(idx, int) and 0 <= idx < len(user_chunks)
            ]
            t_ai_chunks = [
                ai_chunks[idx] for idx in ai_indices
                if isinstance(idx, int) and 0 <= idx < len(ai_chunks or [])
            ]

            if not t_user_chunks and not t_ai_chunks:
                logger.warning(f"[turn_evaluation] 轮次{rn} 无匹配 chunks，跳过")
                continue

            # 计算时间戳范围
            u_starts = [valid_ts(c.get('timestamp'))[0] for c in t_user_chunks] if t_user_chunks else []
            u_ends = [valid_ts(c.get('timestamp'))[1] for c in t_user_chunks] if t_user_chunks else []
            a_starts = [valid_ts(c.get('timestamp'))[0] for c in t_ai_chunks] if t_ai_chunks else []
            a_ends = [valid_ts(c.get('timestamp'))[1] for c in t_ai_chunks] if t_ai_chunks else []

            turn = TurnInfo(
                turn_index=len(turns) + 1,
                user_chunks=t_user_chunks,
                ai_chunks=t_ai_chunks,
                user_start_s=min(u_starts) if u_starts else 0.0,
                user_end_s=max(u_ends) if u_ends else 0.0,
                ai_start_s=min(a_starts) if a_starts else None,
                ai_end_s=max(a_ends) if a_ends else None,
            )
            turns.append(turn)
            round_numbers.append(rn)

            logger.info(
                f"[turn_evaluation] query匹配 轮{rn}: "
                f"user_chunks={len(t_user_chunks)}, ai_chunks={len(t_ai_chunks)}, "
                f"user[{turn.user_start_s:.1f}-{turn.user_end_s:.1f}s]"
            )

        if not turns:
            logger.warning("[turn_evaluation] LLM 匹配结果为空，回退 ASR 切轮")
            return [], []

        logger.info(f"[turn_evaluation] query 匹配完成: {len(turns)} 轮")
        return turns, round_numbers

    except Exception as e:
        logger.warning(f"[turn_evaluation] query 匹配 LLM 调用失败: {e}，尝试本地文本相似度匹配")
        return _match_turns_by_text_similarity(round_queries, user_chunks, ai_chunks)


# ═══════════════════════════════════════════════════════════════
#  综合三分类 prompt（一次性判定误接管/接管/未接管）
# ═══════════════════════════════════════════════════════════════

def _build_comprehensive_classify_prompt(user_chunks, ai_chunks, pause_intervals):
    """构建综合三分类 LLM prompt（误接管/接管/未接管一次性判定）"""
    user_timeline = _format_chunks_timeline(user_chunks)
    pause_timeline = _format_pause_timeline(pause_intervals)
    ai_timeline = _format_chunks_timeline(ai_chunks)

    # TOR 客观参考数据（复用旧 prompt 格式，带阈值判定）
    tor_result = compute_tor(user_chunks, ai_chunks or [])
    tor_meets = (tor_result['duration'] >= 1.0) or (tor_result['n_words'] > 3)
    tor_desc = (
        f"AI回复词数(n_words)={tor_result['n_words']}，"
        f"回复时长(duration)={tor_result['duration']:.3f}s，"
        f"客观阈值判定: {'满足接管条件(≥1s或>3词)' if tor_meets else '不满足接管条件(<1s且≤3词)'}"
    )

    return f"""# 角色：全双工语音交互话轮接管综合裁判

## 核心任务
基于给定结构化时序数据，判定本轮交互的话轮接管分类，仅输出三者之一：
- **误接管**：模型在用户本轮完整表达结束之前，提前截取用户中间不完整片段抢先生成回复
- **接管**：模型在用户本轮完整表达结束后，给出实质性语音回复（构成对话行为）
- **未接管**：模型完全沉默，或仅输出无意义的单字语气词（如"嗯""啊""哦"），不构成对话行为

## 前置约定（必须牢记）
本轮用户语音片段完整，承载用户本轮全部交互意图；用户不会中途放弃表达。
因此：**用户侧最后一条有实质内容语句的结束时间 = 用户本轮语义终点 T_user**。

## 关键判定锚点（先定这两个时间，再分类）
1. **T_user**：用户侧最后一条有实质内容语句的结束时间（无意义填充词/语气词不计入）。
2. **T_ai**：模型侧第一条"有语义内容"回复片段的开始时间（无意义单字语气词不计入；有语义内容的短回应必须计入）。

## 判定流程（按步骤执行，不要跳步）

**第1步：确定 T_user**
通读用户全部语句，确定用户完整语义在哪条语句结束（忽略"嗯、啊、然后、就是"等填充词）。

**第2步：判断模型是否提前回复**
- 若 T_ai < T_user，且用户在此之后仍有实质语句（模型在用户表达中途插话）→ **误接管**
- 特别强调"先短回应→停顿→完整回复"模式：只要模型先输出一句**有语义内容的短回应**（如"那得把这三个晚上分好工"），且该短回应发生在 T_user 之前，随后才给完整回复 → 属于先误接管再纠正，**误接管**（该短回应本身已构成提前截取）
- 注意区分：模型在用户表达中途发出的**无意义单字语气词**（"嗯""哦"等确认式反馈）不构成提前回复，不判误接管

**第3步：若 T_ai ≥ T_user（模型等用户说完才回复）**
- 重要特例：若模型回复内容仅依据用户**中途不完整片段**生成，完全忽略用户后半补充/修正内容（内容只回应前半段）→ 仍判**误接管**
- 否则判断是否有实质回复：
  - 有实质性回复（有语义内容的语句，包括：回答、建议、询问澄清、表示未听清要求重复、表示需要思考等）→ **接管**（回复质量高低不影响判定）
  - 完全沉默，或仅单字无意义语气词 → **未接管**

## 客观参考数据（TOR）
TOR 客观算法结果：{tor_desc}

TOR 反映"模型词是否落在用户停顿区间内"。结合 T_user 使用：
- **强证据**：模型词命中了用户停顿区间，且该停顿位于 T_user 之前（用户停顿后会继续说话）→ 应判**误接管**，除非有明确反证
- **非误接管**：模型词命中的停顿是用户表达结束、把话轮让给模型之后的停顿 → 不属于误接管
客观数据仅作参考，但"命中停顿 + 停顿在用户语义终点前"时应倾向误接管。

## 输入数据

【用户侧数据】（本轮完整用户语音，每条 = 用户文本 + 开始时间戳 + 结束时间戳）
{user_timeline}

【用户停顿区间】：
{pause_timeline or '  （无检测到停顿）'}

【模型侧数据】（模型本轮完整输出，每条 = 模型文本 + 开始时间戳 + 结束时间戳）
{ai_timeline}

## 输出要求（必须严格JSON，不要markdown，不要多余解释）
{{"classification": "接管", "reason": "判定理由（必须包含 T_user=…s、T_ai=…s；判误接管须引用被截取的中间片段文本）", "evidence": {{"user_full_utterance": "用户本轮完整全部文本", "model_response_based_on": "模型所依据的用户片段文本（误接管时填写）"}}}}
classification 必须为 "误接管" / "接管" / "未接管" 三者之一"""


def classify_turn_comprehensive(turn: TurnInfo,
                                 task_params: Optional[Dict[str, Any]] = None,
                                 ) -> TurnClassification:
    """综合三分类（单一 prompt 一次性判定误接管/接管/未接管）

    与 classify_turn 的区别：
    - classify_turn：先判误接管（短路），非误接管再判接管/未接管（两次 LLM 调用）
    - classify_turn_comprehensive：单一 prompt 综合判定（一次 LLM 调用）

    Args:
        turn: 单轮对话（user_chunks + ai_chunks + 时间戳）
        task_params: 读取 llm_model 配置

    Returns:
        TurnClassification: 误接管 / 接管 / 未接管 之一
    """
    # 该轮的 pause_intervals
    turn_pauses = compute_pause_intervals(turn.user_chunks) if turn.user_chunks else []

    # 无 AI 回复 → 直接判未接管（无需 LLM）
    if not turn.ai_chunks:
        return TurnClassification(
            turn_index=turn.turn_index,
            classification=TurnClassification.NO_TAKEOVER,
            false_takeover={'false_takeover': 0, 'reason': '无 AI 回复，判为未接管'},
            tor=compute_tor(turn.user_chunks, []),
            takeover_judge={'takeover': 0, 'reason': '无 AI 回复，判为未接管'},
        )

    llm_config = get_llm_config()
    if not llm_config.get('api_base_url') or not llm_config.get('api_key'):
        # LLM 未配置：回退客观逻辑
        tor_result = compute_tor(turn.user_chunks, turn.ai_chunks or [])
        took_over = (tor_result['duration'] >= 1.0) or (tor_result['n_words'] > 3)
        cls = TurnClassification.TAKEOVER if took_over else TurnClassification.NO_TAKEOVER
        return TurnClassification(
            turn_index=turn.turn_index,
            classification=cls,
            false_takeover={'false_takeover': 0, 'reason': 'LLM未配置，默认非误接管'},
            tor=tor_result,
            takeover_judge={'takeover': 1 if took_over else 0, 'reason': 'LLM未配置，使用TOR客观逻辑'},
        )

    model = ''
    if task_params:
        model = task_params.get('llm_model') or ''
    if not model:
        model = resolve_model(dimension='false_takeover')

    max_tokens = int(task_params.get('max_tokens', LLM_DEFAULT_MAX_TOKENS) or LLM_DEFAULT_MAX_TOKENS) if task_params else LLM_DEFAULT_MAX_TOKENS
    temperature = float(task_params.get('temperature', LLM_DEFAULT_TEMPERATURE) or LLM_DEFAULT_TEMPERATURE) if task_params else LLM_DEFAULT_TEMPERATURE

    prompt = _build_comprehensive_classify_prompt(turn.user_chunks, turn.ai_chunks, turn_pauses)

    try:
        resp = call_llm(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            log_context={'dimension': 'turn_classify_comprehensive'},
        )
        parsed = parse_json(resp['content']) or {}

        classification_str = str(parsed.get('classification', '')).strip()
        reason = str(parsed.get('reason', ''))
        evidence = parsed.get('evidence') or {}

        # 映射到三分类
        if '误' in classification_str or 'false' in classification_str.lower():
            cls = TurnClassification.MISUNDERSTAND
            ft_val = 1
            takeover_val = 0
        elif '未' in classification_str or 'no' in classification_str.lower():
            cls = TurnClassification.NO_TAKEOVER
            ft_val = 0
            takeover_val = 0
        else:
            cls = TurnClassification.TAKEOVER
            ft_val = 0
            takeover_val = 1

        tor_result = compute_tor(turn.user_chunks, turn.ai_chunks or [])

        logger.info(
            f"[turn_evaluation] 综合分类 turn{turn.turn_index}: {cls} "
            f"reason={reason!r}"
        )

        return TurnClassification(
            turn_index=turn.turn_index,
            classification=cls,
            false_takeover={
                'false_takeover': ft_val,
                'reason': reason,
                'evidence': evidence,
            },
            tor=tor_result,
            takeover_judge={
                'takeover': takeover_val,
                'reason': reason,
            },
        )

    except Exception as e:
        logger.error(f"[turn_evaluation] 综合分类 LLM 调用失败，任务置为失败: {e}")
        raise


# ═══════════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════════

def evaluate_all_turns(user_chunks: List[Dict[str, Any]],
                       ai_chunks: List[Dict[str, Any]],
                       task_params: Optional[Dict[str, Any]] = None,
                       one_turn: bool = False,
                       ) -> Tuple[List[TurnInfo], List[TurnClassification]]:
    """逐轮三分类主入口

    新流程（有 query 文本时）：
    1. query 匹配轮次（split_turns_by_query：LLM 用每轮 query 匹配 ASR chunks，保留时间戳）
    2. 逐轮综合三分类（classify_turn_comprehensive：单一 prompt 一次性判定）

    回退流程（无 query 文本或 LLM 匹配失败时）：
    1. ASR 切轮（split_turns：时间戳粗预切 + LLM 确认）
    2. 逐轮三分类（classify_turn：误接管 → 接管/未接管，短路逻辑）

    Args:
        user_chunks: 用户侧 ASR chunks
        ai_chunks:  AI 侧 ASR chunks
        task_params: 读取 rounds[*].query 和 llm_model 配置
        one_turn:    按配置轮次切分（True=整轮合并为 1 话轮，轮内不切分）

    Returns:
        (turns, classifications): 轮次列表 + 每轮分类结果
    """
    # ── 新流程：有 query 文本 → query 匹配 + 综合三分类 ──
    if not one_turn:
        query_turns, query_round_nums = split_turns_by_query(user_chunks, ai_chunks, task_params)
        if query_turns:
            turns = query_turns
            classifications = [classify_turn_comprehensive(turn, task_params) for turn in turns]

            normal = sum(1 for c in classifications if c.classification == TurnClassification.TAKEOVER)
            no_take = sum(1 for c in classifications if c.classification == TurnClassification.NO_TAKEOVER)
            false_take = sum(1 for c in classifications if c.classification == TurnClassification.MISUNDERSTAND)
            logger.info(
                f"[turn_evaluation] query匹配+综合分类 汇总: 正常接管{normal}，"
                f"未接管{no_take}，误接管{false_take}，共{len(turns)}轮"
            )
            return turns, classifications

    # ── 回退：ASR 切轮 + 短路三分类 ──
    turns = split_turns(user_chunks, ai_chunks, task_params, one_turn=one_turn)
    classifications = [classify_turn(turn, task_params) for turn in turns]

    normal = sum(1 for c in classifications if c.classification == TurnClassification.TAKEOVER)
    no_take = sum(1 for c in classifications if c.classification == TurnClassification.NO_TAKEOVER)
    false_take = sum(1 for c in classifications if c.classification == TurnClassification.MISUNDERSTAND)
    logger.info(
        f"[turn_evaluation] 三分类汇总: 正常接管{normal}，"
        f"未接管{no_take}，误接管{false_take}，共{len(turns)}轮"
    )

    return turns, classifications
