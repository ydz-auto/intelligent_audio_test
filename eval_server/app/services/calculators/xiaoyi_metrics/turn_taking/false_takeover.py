# -*- coding: utf-8 -*-
"""
xiaoyi_false_takeover.py
小艺误接管率（TOR, Take-Off Rate）计算：在用户停顿期间模型是否错误接管（抢话）

判定规则（参考 Full-Duplex-Bench/v1_v1.5/evaluation/eval_pause_handling.py）：
    将所有 pause 区间内命中的模型词拼到一起，统一计算：
        每个命中词的时间戳裁剪到 pause 区间内（只算重叠部分）：
            clip_start = max(word_start, pause_start)
            clip_end   = min(word_end,   pause_end)
        duration = 所有裁剪后命中词的最后一个 end - 第一个 start
        n_words  = 所有命中词数
    若 duration ≥ 1 秒 或 n_words > 3 → TOR=1（抢话）
    否则                                → TOR=0（未抢话）

依赖:
    - {wav同名}.json        : app.utils.pause_json.generate_pause_json 生成的 ASR 词级时间戳
    - {wav同名}.pause.json  : app.utils.pause_json.generate_pause_json 生成的停顿区间
"""
import json
import logging

from app.services.calculators.xiaoyi_metrics.shared.llm_client import (
    call_llm,
    parse_json,
    get_llm_config,
    resolve_model,
)
from app.services.calculators.xiaoyi_metrics.shared.constants import (
    LLM_DEFAULT_MAX_TOKENS,
    LLM_DEFAULT_TEMPERATURE,
    TURN_DURATION_THRESHOLD,
    TURN_NUM_WORDS_THRESHOLD,
    TIMELINE_MAX_ITEMS_CHUNKS,
    TIMELINE_MAX_ITEMS_PAUSES,
)

logger = logging.getLogger(__name__)


def _intervals_overlap(a, b):
    """判断两个 [start, end] 区间是否相交（边界相等不算相交，避免擦边误判）"""
    return a[0] < b[1] and b[0] < a[1]


def compute_false_takeover(chunks, pause_intervals,
                           duration_threshold=TURN_DURATION_THRESHOLD,
                           num_words_threshold=TURN_NUM_WORDS_THRESHOLD):
    """将所有 pause 区间内的命中词拼接到一起，统一判定小艺是否抢话

    判定：模型在所有 pause 区间内的命中词（合并）
        - duration ≥ duration_threshold (默认 1s)  → 抢话
        - n_words  > num_words_threshold (默认 3)   → 抢话
        - 否则                                      → 未抢话

    Args:
        chunks (list): ASR chunks，每项含 {"text", "timestamp": [start, end]}
        pause_intervals (list): pause 区间列表，每项 {"text", "timestamp": [start, end]}
        duration_threshold (float): 时长阈值，默认 1 秒
        num_words_threshold (int): 词数阈值，默认 3（严格大于）

    Returns:
        dict: {
            'tor': int,              0 或 1（0=未抢话，1=抢话）
            'n_words': int,         所有 pause 区间内命中词总数
            'duration': float,      命中词的总跨度（max_end - min_start）
            'total_pauses': int,    pause 区间总数
            'hit_words': list,      所有命中词
            'details': list,        每个 pause 的命中情况
        }
    """
    total = len(pause_intervals)

    # 收集所有 pause 区间内命中的模型词（拼接到一起）
    all_hit_words = []
    details = []

    for p in pause_intervals:
        p_iv = p.get('timestamp') or [p.get('start'), p.get('end')]
        hit_words = []
        for c in chunks:
            if c.get('timestamp') is not None and _intervals_overlap(c['timestamp'], p_iv):
                # 裁剪到 pause 区间内，只算重叠部分的时长
                clip_start = max(c['timestamp'][0], p_iv[0])
                clip_end = min(c['timestamp'][1], p_iv[1])
                hit_words.append({
                    'text': c.get('text', ''),
                    'timestamp': [clip_start, clip_end],
                })
        details.append({
            'pause_interval': p_iv,
            'hit_n_words': len(hit_words),
            'hit_words': hit_words,
        })
        all_hit_words.extend(hit_words)

    # 统一计算合并后的 duration 和 n_words
    n_words = len(all_hit_words)
    if n_words == 0:
        duration = 0.0
    else:
        starts = [w['timestamp'][0] for w in all_hit_words if w['timestamp'][0] is not None]
        ends = [w['timestamp'][1] for w in all_hit_words if w['timestamp'][1] is not None]
        duration = (max(ends) - min(starts)) if starts and ends else 0.0

    # 判定：时长 ≥ 1s 或 词数 > 3
    took_over = (duration >= duration_threshold) or (n_words > num_words_threshold)

    return {
        'tor': 1 if took_over else 0,
        'n_words': n_words,
        'duration': round(duration, 3),
        'total_pauses': total,
        'hit_words': all_hit_words,
        'details': details,
    }


def compute_false_takeover_from_files(asr_json_path, pause_json_path,
                                      duration_threshold=TURN_DURATION_THRESHOLD,
                                      num_words_threshold=TURN_NUM_WORDS_THRESHOLD):
    """从 {name}.json 和 {name}.pause.json 两个文件计算小艺误接管率

    Args:
        asr_json_path (str): pause_json 生成的 ASR JSON 路径（{wav同名}.json）
        pause_json_path (str): pause_json 生成的 pause 区间 JSON 路径（{wav同名}.pause.json）
        duration_threshold (float): 时长阈值，默认 1 秒
        num_words_threshold (int): 词数阈值，默认 3（严格大于）

    Returns:
        dict: 同 compute_false_takeover（读取失败时 tor=0）
    """
    try:
        with open(asr_json_path, "r", encoding="utf-8") as f:
            asr_hyp = json.load(f)
        with open(pause_json_path, "r", encoding="utf-8") as f:
            pause_intervals = json.load(f)
    except Exception as e:
        logger.error(f"读取 ASR/pause JSON 失败: {asr_json_path} / {pause_json_path} {e}")
        return {
            'tor': 0,
            'n_words': 0,
            'duration': 0.0,
            'total_pauses': 0,
            'hit_words': [],
            'details': [],
        }

    chunks = asr_hyp.get("chunks", [])
    res = compute_false_takeover(chunks, pause_intervals,
                                 duration_threshold=duration_threshold,
                                 num_words_threshold=num_words_threshold)
    logger.info(
        f"[误接管率] n_words={res['n_words']} duration={res['duration']}s "
        f"tor={res['tor']}"
    )
    return res


# ─────────── LLM 语义判断 ───────────

def _format_chunks_timeline(chunks, max_items=TIMELINE_MAX_ITEMS_CHUNKS):
    """将 ASR chunks 格式化为带时间戳的时间线文本

    Args:
        chunks: [{text, timestamp:[start, end]}, ...]
        max_items: 最大显示条数（截断过长列表）

    Returns:
        str: 格式化后的时间线，如：
          [4.80-6.10] 这个问题吧。
          [6.10-7.80] （停顿1.70秒）
          ...
    """
    lines = []
    for i, c in enumerate(chunks[:max_items]):
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


def _build_false_takeover_llm_prompt(user_chunks, ai_chunks, pause_intervals):
    """构建误接管 LLM 判断 prompt

    将用户语音段、停顿区间、模型回复词级时间戳拼接为对话时间线，
    让 LLM 从语义层面判断模型是否在用户尚未让出话轮时错误接管。
    """
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

## 强制输出格式（必须严格JSON，不要多余解释，不要markdown）
{{"judge_result": "true", "explanation": "判定详细理由", "evidence": {{"user_utterance_used_by_model": "模型所依据的用户片段文本", "user_full_utterance": "用户本轮完整全部文本"}}}}
judge_result 说明：true = 存在话轮误接管；false = 无话轮误接管"""


def compute_false_takeover_llm(user_chunks, ai_chunks, pause_intervals,
                                task_params=None):
    """LLM 语义判断误接管（时间戳算法的补充）

    时间戳算法只能检测模型词是否落在用户停顿区间内，无法识别"思考停顿"
    和"让出话轮停顿"的区别。本函数用 LLM 从对话语义层面做补充判断。

    触发条件：配置了 LLM_JUDGE_API_KEY 时自动调用，失败或未配置则跳过。

    LLM 判定 false_takeover=1（误接管）时：不计算 tor / takeover_latency，返回 None。
    LLM 判定 false_takeover=0（未误接管）时：计算 tor（接话率）和 takeover_latency（接管时延）。

    Args:
        user_chunks (list): 用户段级 ASR chunks [{text, timestamp:[start,end]}]
        ai_chunks (list): 模型词级 ASR chunks [{text, timestamp:[start,end]}]
        pause_intervals (list): 用户停顿区间 [{text, timestamp:[start,end]}]
        task_params (dict|None): 读取 llm_model 配置

    Returns:
        dict|None: {
            'false_takeover': int,       LLM 判定的误接管结果 0/1
            'reason': str,              判定理由（explanation）
            'evidence': dict,           证据信息（可选）
            'tor': dict|None,           接话率结果（false_takeover=1 时为 None）
            'takeover_latency': dict|None, 接管时延结果（false_takeover=1 时为 None）
        } 或 None（未配置/调用失败/无数据）
    """
    llm_config = get_llm_config()
    if not llm_config.get('api_base_url') or not llm_config.get('api_key'):
        return None

    if not user_chunks or not ai_chunks:
        return None

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
        )
        parsed = parse_json(resp['content']) or {}

        # 新格式: {"judge_result": "true/false", "explanation": "...", "evidence": {...}}
        judge = parsed.get('judge_result')
        if isinstance(judge, str):
            ft_val = 1 if judge.strip().lower() in ('true', '1', '是') else 0
        elif isinstance(judge, bool):
            ft_val = 1 if judge else 0
        else:
            ft_val = 0

        result = {
            'false_takeover': ft_val,
            'reason': str(parsed.get('explanation', '')),
            'evidence': parsed.get('evidence') or {},
        }

        # false_takeover=0（未误接管）时，计算 tor 和 takeover_latency（平铺）
        if ft_val == 0:
            from .tor import compute_tor
            from .takeover_latency import compute_takeover_latency_from_chunks

            tor_res = compute_tor(user_chunks, ai_chunks)
            lat_res = compute_takeover_latency_from_chunks(user_chunks, ai_chunks)
            result['tor'] = tor_res.get('tor')
            result['n_words'] = tor_res.get('n_words')
            result['duration'] = tor_res.get('duration')
            result['hit_words'] = tor_res.get('hit_words')
            result['user_last_word_end_s'] = tor_res.get('user_last_word_end_s')
            result['takeover_latency_ms'] = lat_res.get('takeover_latency_ms')
            result['user_last_word_end_ms'] = lat_res.get('user_last_word_end_ms')
            result['ai_first_word_start_ms'] = lat_res.get('ai_first_word_start_ms')
            result['message'] = lat_res.get('message')
            logger.info(
                f"[false_takeover_llm] 未误接管，tor={result['tor']} "
                f"takeover_latency={result['takeover_latency_ms']}ms"
            )
        else:
            result['tor'] = None
            result['n_words'] = None
            result['duration'] = None
            result['hit_words'] = None
            result['user_last_word_end_s'] = None
            result['takeover_latency_ms'] = None
            result['user_last_word_end_ms'] = None
            result['ai_first_word_start_ms'] = None
            result['message'] = None

        logger.info(
            f"[false_takeover_llm] LLM 判定: false_takeover={ft_val} "
            f"reason={result['reason']!r}"
        )
        return result
    except Exception as e:
        logger.warning(f"[false_takeover_llm] LLM 调用失败: {e}")
        return None


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='计算小艺误接管率 TOR（时长≥1s 或 词数>3 → 抢话）')
    parser.add_argument('--asr_json', required=True,
                        help='{wav同名}.json 路径（pause_json 生成的 ASR 词级时间戳）')
    parser.add_argument('--pause_json', required=True,
                        help='{wav同名}.pause.json 路径（pause_json 生成的停顿区间）')
    parser.add_argument('--duration_threshold', type=float, default=TURN_DURATION_THRESHOLD,
                        help=f'时长阈值（秒），默认 {TURN_DURATION_THRESHOLD}')
    parser.add_argument('--num_words_threshold', type=int, default=TURN_NUM_WORDS_THRESHOLD,
                        help=f'词数阈值（严格大于），默认 {TURN_NUM_WORDS_THRESHOLD}')
    args = parser.parse_args()

    r = compute_false_takeover_from_files(
        args.asr_json, args.pause_json,
        duration_threshold=args.duration_threshold,
        num_words_threshold=args.num_words_threshold,
    )
    print(json.dumps(r, ensure_ascii=False, indent=2))
