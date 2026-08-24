# -*- coding: utf-8 -*-
"""对比 eval_server 原始打断脚本 vs gemini-3.7-flash 自算结果。

跑 4 个变体 + gemini 自算：
  A. 原始脚本 + 现有 chunk 级 ASR JSON, gap=3.0(默认)
  B. 原始脚本 + 现有 chunk 级 ASR JSON, gap=0.5(旧值)
  C. 原始脚本 + gemini 字词级 ASR(转 chunks), gap=3.0
  D. 原始脚本 + gemini 字词级 ASR(转 chunks), gap=0.5
  E. gemini 自算(已存)
"""
import json, os, sys

sys.path.insert(0, r"D:/work/20260630/eval_server")
from app.services.calculators.xiaoyi_metrics.interruptbility.interruption import (
    compute_interruption_metrics,
)

DATA = sys.argv[1].rstrip("/\\") if len(sys.argv) > 1 else r"D:/work/fwqdata/270/270/fbec58d7-054e-446f-916d-86eebe5d289a/5SM0125613000197"

def _find(suffix):
    for fn in os.listdir(DATA):
        if fn.endswith(suffix):
            return os.path.join(DATA, fn)
    raise FileNotFoundError(f"{DATA} 下找不到 *{suffix}")

USER_JSON = _find("_1_1_cap_client_process_out.json")   # 用户
MODEL_JSON = _find("_2_1_cap_client_ec_out.json")         # 助手
GEMINI = os.path.join(DATA, "gemini_asr_result.json")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def gemini_words_to_chunks(words):
    """gemini word-level -> {text, chunks:[{text, timestamp:[s,e]}]}"""
    chunks = []
    for w in words:
        chunks.append({"text": w.get("text", ""), "timestamp": [w.get("start"), w.get("end")]})
    return {"text": "", "chunks": chunks}


def summarize(r, label):
    pe = r.get("per_event", [])
    # 取第一个 event_type=interruption 且 success 的事件作为"主打断"
    main = next((e for e in pe if e.get("event_type") == "interruption"), None)
    # 也找最后一个 interruption 事件(真正的"行了别说了")
    last_int = next((e for e in reversed(pe) if e.get("event_type") == "interruption"), None) if pe else None
    print(f"\n===== {label} =====")
    print(f"  n_user_segments={r.get('n_user_segments')} n_events={r.get('n_events')} "
          f"n_recovery_only={r.get('n_recovery_only')} n_no_model_speech={r.get('n_no_model_speech')}")
    print(f"  avg_stop_latency_s={r.get('avg_stop_latency_s')} avg_recovery_latency_s={r.get('avg_recovery_latency_s')}")
    print(f"  success_rate={r.get('interruption_success_rate')} message={r.get('message')}")
    print(f"  -- per_event --")
    for i, e in enumerate(pe):
        print(f"   [{i}] type={e.get('event_type')} u={e.get('user_segment')} "
              f"stop={e.get('stop_latency_s')} recov={e.get('recovery_latency_s')} "
              f"overlap={e.get('overlap_s')} gap={e.get('silence_gap_s')} success={e.get('success')}")
    if last_int:
        print(f"  >> 最后一个 interruption 事件(真打断) stop={last_int.get('stop_latency_s')} "
              f"recovery={last_int.get('recovery_latency_s')} "
              f"u={last_int.get('user_segment')} m_active/next 推断见上")


def main():
    user_chunk = load(USER_JSON)
    model_chunk = load(MODEL_JSON)
    gem = load(GEMINI)

    user_gem = gemini_words_to_chunks(gem["channel_1_user"]["words"])
    model_gem = gemini_words_to_chunks(gem["channel_2_assistant"]["words"])

    summarize(compute_interruption_metrics(user_chunk, model_chunk, seg_merge_gap_s=3.0),
              "A. 原始脚本 + chunk级ASR, gap=3.0(默认)")
    summarize(compute_interruption_metrics(user_chunk, model_chunk, seg_merge_gap_s=0.5),
              "B. 原始脚本 + chunk级ASR, gap=0.5(旧值)")
    summarize(compute_interruption_metrics(user_gem, model_gem, seg_merge_gap_s=3.0),
              "C. 原始脚本 + gemini字词级ASR, gap=3.0")
    summarize(compute_interruption_metrics(user_gem, model_gem, seg_merge_gap_s=0.5),
              "D. 原始脚本 + gemini字词级ASR, gap=0.5")

    print("\n===== E. gemini 自算(直接听音频) =====")
    ig = gem.get("interruption", {})
    print(f"  user_segment={ig.get('user_segment')}")
    print(f"  model_active_segment={ig.get('model_active_segment')}")
    print(f"  model_next_segment={ig.get('model_next_segment')}")
    print(f"  stop_latency_s={ig.get('stop_latency_s')}")
    print(f"  recovery_latency_s={ig.get('recovery_latency_s')}")
    print(f"  overlap_s={ig.get('overlap_s')} silence_gap_s={ig.get('silence_gap_s')}")
    print(f"  reasoning={ig.get('reasoning')}")


if __name__ == "__main__":
    main()
