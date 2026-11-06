# -*- coding: utf-8 -*-
"""
pause_json.py
流程：本地 wav → 调用 ASR_JSON.transcribe_and_dump 拿词级时间戳
      → 扫描相邻词间隔，筛出 [MIN_GAP, MAX_GAP] 范围内的停顿
      → 生成 {wav 同名}.pause.json

输出格式（与 Full-Duplex-Bench pause.json 兼容）：
    [
      {"text": "[PAUSE]", "timestamp": [start, end]},
      ...
    ]

参数说明：
    MIN_GAP = 0.2   最小停顿阈值（秒），小于此值不算 pause
    MAX_GAP = 3.0   最大停顿阈值（秒），大于此值视为静音/段末，不算 pause
"""
import os
import json
import argparse

# ─── 加载 .env 到 os.environ（参考 app/config.py） ───
from pathlib import Path
_env_path = Path(__file__).resolve().parent.parent.parent / '.env'
if _env_path.exists():
    with open(_env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

from app.utils.ASR_JSON import transcribe_and_dump

# ─────────── 停顿阈值（秒） ───────────
MIN_GAP = 0.2
MAX_GAP = 3.0


def detect_pauses(chunks, min_gap=MIN_GAP, max_gap=MAX_GAP):
    """
    从 asr_server 词级时间戳中检测相邻词之间的停顿区间。

    Args:
        chunks: [{"text": "...", "timestamp": [start, end]}, ...]
        min_gap: 停顿最小长度（秒），默认 0.2
        max_gap: 停顿最大长度（秒），默认 3.0

    Returns:
        [{"text": "[PAUSE]", "timestamp": [pause_start, pause_end]}, ...]
        pause_start = 前一个词的 end
        pause_end   = 后一个词的 start
    """
    pauses = []
    for i in range(len(chunks) - 1):
        prev_end = chunks[i]["timestamp"][1]
        next_start = chunks[i + 1]["timestamp"][0]
        gap = next_start - prev_end
        if min_gap <= gap <= max_gap:
            pauses.append({
                "text": "[PAUSE]",
                "timestamp": [prev_end, next_start]
            })
    return pauses


def generate_pause_json(wav_path, language=None, min_gap=MIN_GAP, max_gap=MAX_GAP):
    """
    端到端：wav → asr_server → 检测停顿 → 写 pause.json

    输出文件：{wav_path 去扩展名}.pause.json
    返回：pauses list
    """
    # 1. asr_server 转录（已自动生成 {wav}.json）
    result = transcribe_and_dump(wav_path, language)
    chunks = result.get("chunks", [])
    if len(chunks) < 2:
        print(f"[Warning] 词数过少（{len(chunks)}），无法检测停顿")
        return []

    # 2. 检测停顿
    pauses = detect_pauses(chunks, min_gap, max_gap)

    # 3. 写 pause.json
    out_path = os.path.splitext(wav_path)[0] + ".pause.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pauses, f, indent=2, ensure_ascii=False)

    print(f"已生成: {out_path} ({len(pauses)} pauses)")
    for i, p in enumerate(pauses):
        s, e = p["timestamp"]
        print(f"  [{i+1}] [{s:.3f}, {e:.3f}]  gap={e-s:.3f}s")
    return pauses


if __name__ == "__main__":
    # 清代理（参考 asr_api.py），避免 ProxyError
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(k, None)
    os.environ["NO_PROXY"] = "*"

    parser = argparse.ArgumentParser(
        description="从 wav 生成 pause.json：词间停顿长度在 [MIN_GAP, MAX_GAP] 范围内的区间"
    )
    parser.add_argument("--wav", required=True, help="本地 wav 文件路径")
    parser.add_argument("--language", default=None, help="语种（默认自动检测）")
    parser.add_argument("--min_gap", type=float, default=MIN_GAP,
                        help=f"停顿最小长度（秒），默认 {MIN_GAP}")
    parser.add_argument("--max_gap", type=float, default=MAX_GAP,
                        help=f"停顿最大长度（秒），默认 {MAX_GAP}")
    args = parser.parse_args()

    generate_pause_json(args.wav, args.language, args.min_gap, args.max_gap)
