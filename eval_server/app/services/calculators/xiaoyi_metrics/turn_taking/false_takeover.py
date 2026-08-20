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

logger = logging.getLogger(__name__)

# ─────────── 阈值（与 daily_chat_TOR 保持一致） ───────────
TURN_DURATION_THRESHOLD = 1   # 秒：命中词时长 ≥ 1s 算抢话
TURN_NUM_WORDS_THRESHOLD = 3  # 词数 > 3 算抢话


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
