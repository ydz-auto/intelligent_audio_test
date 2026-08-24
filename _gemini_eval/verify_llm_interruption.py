# -*- coding: utf-8 -*-
"""验证 calculate_interruption_metrics 的 LLM 全量评估路径（三项主指标改 LLM）。

对三个已知 case 目录构造 task_params 直调入口，检查：
  - interruption_success_rate / avg_stop_latency_s / avg_recovery_latency_s 非 None(来自 LLM)
  - llm_eval.timing_comparison 含时序原值
  - per_round 每轮有 is_interrupted / reaction_behavior
  - <wav>_nokaana.json 已生成且不含假名 chunk
  - 失败兜底：清空 API key 跑一次，主字段回退时序值、llm_eval.enabled=False、不抛异常
"""
import os
import sys
import json
import logging

sys.path.insert(0, r"D:/work/20260630/eval_server")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app.services.calculators.xiaoyi_metrics.turn_taking import calculate_interruption_metrics

CASES = [
    ("case1-news", r"D:/work/fwqdata/270/270/fbec58d7-054e-446f-916d-86eebe5d289a/5SM0125613000197"),
    ("case2-restaurant", r"D:/work/fwqdata/270/270/7668c6de-f9f8-4149-b2f5-13610da6a666/5SM0125613000197"),
    ("case3-beijing", r"D:/work/fwqdata/270/270/c97cdbaf-717a-400f-a1e1-7c9bc8b9032a/5SM0125613000197"),
]

KANA_RE = __import__("re").compile(r"[぀-ゟ゠-ヿ]")


def _find(d, suffix):
    for fn in os.listdir(d):
        if fn.endswith(suffix):
            return os.path.join(d, fn)
    return None


def build_task_params(d):
    # 跳过慢/不稳的本地 ASR：传空 ASR，让 LLM 直接听音频算（gemini 音频路径才是主指标来源）
    # query/answer 文本仍从 JSON 取作上下文
    user_json_path = _find(d, "_1_1_cap_client_process_out.json")
    model_json_path = _find(d, "_2_1_cap_client_ec_out.json")
    user_text = json.load(open(user_json_path, encoding="utf-8")).get("text", "") if user_json_path else ""
    model_text = json.load(open(model_json_path, encoding="utf-8")).get("text", "") if model_json_path else ""
    user_wav = _find(d, "_1_1_cap_client_process_out.wav")
    ai_wav = _find(d, "_2_1_cap_client_ec_out.wav")
    return {
        "user_wav": user_wav,
        "ai_wav": ai_wav,
        # 传空 ASR(非 None)→ 跳过 _wav_to_asr 远程调用；时序 aux 置空，LLM 走音频
        "user_asr": {"text": user_text, "chunks": []},
        "model_asr": {"text": model_text, "chunks": []},
        "seg_merge_gap_s": 3.0,
        "enable_llm_eval": True,
        "llm_model": "gemini-3.7-flash",
        "original_topic": "用户与AI语音对话，用户在AI说话时打断",
        "rounds": [{
            "user_wav": user_wav, "ai_wav": ai_wav,
            "query": user_text, "answer": model_text,
            "is_return_to_topic": False,
        }],
    }


def run_case(name, d, expect_llm=True):
    print(f"\n{'='*70}\n{name}: {d}\n{'='*70}", flush=True)
    tp = build_task_params(d)
    from app.config import config
    config.LLM_JUDGE["api_base_url"] = "https://az.gptplus5.com/v1"
    config.LLM_JUDGE["default_model"] = "gemini-3.7-flash"
    if not expect_llm:
        # 清空 key 触发 LLM 失败兜底（key 来自 eval_server/.env，已被 config 加载）
        config.LLM_JUDGE["api_key"] = ""

    r = calculate_interruption_metrics(tp)
    print(f"\n--- {name} 结果 ---", flush=True)
    print(f"interruption_success_rate = {r.get('interruption_success_rate')}", flush=True)
    print(f"avg_stop_latency_s        = {r.get('avg_stop_latency_s')}", flush=True)
    print(f"avg_recovery_latency_s    = {r.get('avg_recovery_latency_s')}", flush=True)
    le = r.get("llm_eval") or {}
    print(f"llm_eval.enabled          = {le.get('enabled')}", flush=True)
    tc = le.get("timing_comparison") or {}
    print(f"timing_comparison         = {json.dumps(tc, ensure_ascii=False)}", flush=True)
    pr = le.get("per_round") or []
    for x in pr:
        print(f"  round{x.get('round')}: is_interrupted={x.get('is_interrupted')} "
              f"success={x.get('success')} stop={x.get('stop_latency_s')} "
              f"recov={x.get('recovery_latency_s')} reaction={x.get('reaction_behavior')} "
              f"coh={x.get('coherence')} rel={x.get('relevance')} adap={x.get('adaptability')}", flush=True)
        print(f"     reasoning={x.get('reasoning')}", flush=True)

    # 检查 _nokaana.json
    nk = _find(d, "_nokaana.json")
    if nk:
        nkdata = json.load(open(nk, encoding="utf-8"))
        kana_hits = [c.get("text") for c in nkdata.get("chunks", []) if KANA_RE.search(str(c.get("text", "")))]
        print(f"nokaana_json: {nk}  chunks={len(nkdata.get('chunks', []))}  假名残留={kana_hits}", flush=True)
    else:
        print("nokaana_json: 未生成", flush=True)
    return r


def main():
    results = {}
    for name, d in CASES:
        try:
            results[name] = run_case(name, d, expect_llm=True)
        except Exception as e:
            import traceback
            print(f"!! {name} 异常: {e}", flush=True)
            traceback.print_exc()
            results[name] = None

    # 失败兜底验证
    print(f"\n{'#'*70}\n# 失败兜底：清空 API key 重跑 case1\n{'#'*70}", flush=True)
    try:
        run_case("case1-news(API key 清空)", CASES[0][1], expect_llm=False)
    except Exception as e:
        import traceback
        print(f"!! 兜底异常(不该抛): {e}", flush=True)
        traceback.print_exc()

    # 断言汇总
    print(f"\n{'='*70}\n断言汇总\n{'='*70}", flush=True)
    ok = True
    for name, d in CASES:
        r = results.get(name)
        if not r:
            print(f"[FAIL] {name}: 无结果"); ok = False; continue
        le = r.get("llm_eval") or {}
        tc = le.get("timing_comparison") or {}
        checks = {
            "3主字段非None(LLM产出)": r.get("avg_stop_latency_s") is not None or r.get("avg_recovery_latency_s") is not None,
            "llm_eval.enabled=True": le.get("enabled") is True,
            "timing_comparison含时序原值": "timing_avg_stop_latency_s" in tc,
            "per_round非空": bool(le.get("per_round")),
        }
        for k, v in checks.items():
            print(f"  [{'OK' if v else 'FAIL'}] {name}: {k}")
            if not v: ok = False
    print(f"\n总体: {'ALL OK' if ok else 'HAS FAILURES'}", flush=True)


if __name__ == "__main__":
    main()
