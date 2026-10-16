"""VEGA-37 独立验收探针 —— asr_server(:10095) 并发行为 / 回归 / 内存。

测试工程师自写，不依赖开发工程师B的脚本。用法：

  python -I probe_asr.py shape   --wav <path> --ns 1,2,4,8 --reps 2
  python -I probe_asr.py hol     --long <path> --short <path> --reps 3
  python -I probe_asr.py regress --list <wavs.json> --sample 10 --seed 20261016
  python -I probe_asr.py health

输出：JSON 打到 stdout（供留档/附件）。

判据（VEGA-37 验收口径，规划师裁定）：
  - shape：看**各请求耗时的形状**，不要用「Σ耗时/墙钟」——该指标串行/并行都给 N。
    串行 ⇒ 阶梯状（第 k 个 ≈ k × 单发）、离散度随 N 增长、并发墙钟 ≈ 客户端串行墙钟；
    并发 ⇒ 齐平（离散度小）、wall/max ≈ 1、并发墙钟明显小于客户端串行墙钟。
  - hol：长文件在飞时短文件应立刻完成；串行服务下短请求必须等前面全部做完。
  - regress：段数是硬不变量（必须逐文件相等）；text/timestamp 以「同版本自身两次运行」
    的抖动带为界（该带按文件而异，本批实测上界约 0.44s，不是 0.18s）。

提交于 VEGA-37 验收（本地 commit，未 push）。VEGA-47（ASR_MAX_CONCURRENCY 1→2）、
VEGA-48（限制 torch intra-op 线程数）落地后可直接复跑同一口径做对照。
"""
import argparse
import json
import os
import random
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import psutil

BASE = os.environ.get("ASR_BASE", "http://127.0.0.1:10095")
URL_WORD = BASE + "/asr_word"
TIMEOUT = 900.0


# ─────────── 进程探针 ───────────
def asr_pid():
    me = os.getpid()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.info["pid"] == me:
                continue
            cl = " ".join(p.info["cmdline"] or [])
            if "asr_server.py" in cl:
                return p.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


class MemSampler(threading.Thread):
    """后台采样 asr_server 进程的内存，取峰值。"""

    def __init__(self, pid, interval=0.2):
        super().__init__(daemon=True)
        self.pid, self.interval = pid, interval
        self.stop_flag = threading.Event()
        self.samples = []

    def run(self):
        try:
            proc = psutil.Process(self.pid)
        except psutil.NoSuchProcess:
            return
        while not self.stop_flag.is_set():
            try:
                mi = proc.memory_info()
                pm = proc.memory_full_info()
                self.samples.append({
                    "t": time.time(),
                    "rss_mb": round(mi.rss / 1048576, 1),
                    "private_mb": round(getattr(pm, "private", 0) / 1048576, 1),
                    "vms_mb": round(mi.vms / 1048576, 1),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return
            time.sleep(self.interval)

    def peak(self):
        if not self.samples:
            return {}
        return {
            "rss_peak_mb": max(s["rss_mb"] for s in self.samples),
            "rss_min_mb": min(s["rss_mb"] for s in self.samples),
            "private_peak_mb": max(s["private_mb"] for s in self.samples),
            "private_min_mb": min(s["private_mb"] for s in self.samples),
            "n_samples": len(self.samples),
        }


# ─────────── 单请求 ───────────
def one_request(wav_path, t0, idx, client=None):
    own = client is None
    cl = client or httpx.Client(timeout=TIMEOUT)
    rec = {"idx": idx, "wav": os.path.basename(wav_path)}
    try:
        with open(wav_path, "rb") as fh:
            data = fh.read()
        rec["upload_bytes"] = len(data)
        ts = time.time() - t0
        with cl.stream("POST", URL_WORD,
                       files={"file": (os.path.basename(wav_path), data, "audio/wav")}) as r:
            body = r.read()
        te = time.time() - t0
        rec.update(http=r.status_code, t_start=round(ts, 3), t_end=round(te, 3),
                   elapsed=round(te - ts, 3))
        if r.status_code == 200:
            j = json.loads(body)
            rec["n_chunks"] = len(j.get("chunks") or [])
            rec["text_len"] = len(j.get("text") or "")
            rec["text"] = j.get("text")
            rec["chunks"] = j.get("chunks")
        else:
            rec["error"] = body[:300].decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        rec.update(error=f"{type(e).__name__}: {e}", elapsed=round(time.time() - t0 - rec.get("t_start", 0), 3))
    finally:
        if own:
            cl.close()
    return rec


def run_concurrent(wav_path, n, t0, client=None):
    """n 个并发请求（同一起跑线）。"""
    barrier = threading.Barrier(n)

    def task(i):
        barrier.wait()
        return one_request(wav_path, t0, i, client)

    with ThreadPoolExecutor(max_workers=n) as ex:
        return list(ex.map(task, range(n)))


def summarize(n, wall, per, extra=None):
    el = [p["elapsed"] for p in per if "elapsed" in p]
    out = {
        "n": n,
        "wall": round(wall, 3),
        "elapsed": [round(e, 2) for e in el],
        "sum_elapsed": round(sum(el), 2),
        "max_elapsed": round(max(el), 2) if el else None,
        "min_elapsed": round(min(el), 2) if el else None,
        "spread": round(max(el) - min(el), 2) if el else None,
        "n_ok": sum(1 for p in per if p.get("http") == 200),
        "n_err": sum(1 for p in per if p.get("http") != 200),
        "errors": [p.get("error") for p in per if p.get("error")][:5],
        "chunks": sorted({p.get("n_chunks") for p in per if p.get("n_chunks") is not None}),
    }
    if out["max_elapsed"]:
        # 串行度：wall / 单请求最大耗时。≈1 = 完全并行；≈N = 完全串行。
        out["wall_over_max"] = round(wall / out["max_elapsed"], 2)
    if extra:
        out.update(extra)
    return out


# ─────────── 子命令 ───────────
def cmd_health(_a):
    pid = asr_pid()
    with httpx.Client(timeout=30) as c:
        h = c.get(BASE + "/health").json()
    out = {"health": h, "asr_pid": pid}
    if pid:
        p = psutil.Process(pid)
        out["asr_process"] = {
            "create_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.create_time())),
            "uptime_sec": round(time.time() - p.create_time(), 1),
            "rss_mb": round(p.memory_info().rss / 1048576, 1),
            "num_threads": p.num_threads(),
            "cpu_count": psutil.cpu_count(),
            "mem_free_mb": round(psutil.virtual_memory().available / 1048576, 1),
        }
    print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_shape(a):
    pid = asr_pid()
    res = {"wav": a.wav, "audio_sec": a.audio_sec, "pid": pid, "rounds": []}
    with httpx.Client(timeout=TIMEOUT, limits=httpx.Limits(max_connections=64)) as c:
        for n in [int(x) for x in a.ns.split(",")]:
            for rep in range(1, a.reps + 1):
                s = MemSampler(pid) if pid else None
                if s:
                    s.start()
                t0 = time.time()
                per = run_concurrent(a.wav, n, t0, c)
                wall = time.time() - t0
                if s:
                    s.stop_flag.set()
                    s.join(timeout=5)
                r = summarize(n, wall, per, {"rep": rep, "mode": "concurrent"})
                if s:
                    r["mem"] = s.peak()
                res["rounds"].append(r)
                print(f"  concurrent n={n} rep={rep} wall={r['wall']} elapsed={r['elapsed']} "
                      f"ok={r['n_ok']}/{n} chunks={r['chunks']}", file=sys.stderr)
            # 顺序基线：同样 n 个请求，一个接一个（客户端串行）
            t0 = time.time()
            per = [one_request(a.wav, t0, i, c) for i in range(n)]
            wall = time.time() - t0
            r = summarize(n, wall, per, {"rep": 0, "mode": "sequential"})
            res["rounds"].append(r)
            print(f"  sequential n={n} wall={r['wall']} elapsed={r['elapsed']} "
                  f"ok={r['n_ok']}/{n}", file=sys.stderr)
    # 判定表
    verdict = []
    for n in [int(x) for x in a.ns.split(",")]:
        cc = [r for r in res["rounds"] if r["n"] == n and r["mode"] == "concurrent"]
        ss = [r for r in res["rounds"] if r["n"] == n and r["mode"] == "sequential"]
        if not cc or not ss:
            continue
        wc = statistics.median(r["wall"] for r in cc)
        ws = statistics.median(r["wall"] for r in ss)
        verdict.append({
            "n": n,
            "wall_concurrent_median": round(wc, 2),
            "wall_sequential_median": round(ws, 2),
            "speedup_vs_sequential": round(ws / wc, 2),
            "wall_over_max_median": round(statistics.median(r.get("wall_over_max", 0) for r in cc), 2),
            "elapsed_median": round(statistics.median(r["max_elapsed"] for r in cc), 2),
            "spread_median": round(statistics.median(r["spread"] for r in cc if r["spread"] is not None), 2),
        })
    res["verdict"] = verdict
    res["判据"] = ("speedup_vs_sequential≈1 且 wall_over_max≈1 → 并发未重叠（串行）；"
                 "speedup 明显>1 且 wall_over_max≈1 → 请求真重叠")
    print(json.dumps(res, ensure_ascii=False))


def cmd_hol(a):
    """队头阻塞测试：长文件在飞时，短文件能不能立刻拿到服务。"""
    res = {"long": a.long, "long_sec": a.long_sec, "short": a.short,
           "short_sec": a.short_sec, "n_long": a.nlong, "rounds": []}
    pid = asr_pid()
    with httpx.Client(timeout=TIMEOUT, limits=httpx.Limits(max_connections=8)) as c:
        for rep in range(1, a.reps + 1):
            t0 = time.time()
            with ThreadPoolExecutor(max_workers=a.nlong + 1) as ex:
                fl = [ex.submit(one_request, a.long, t0, i, c) for i in range(a.nlong)]
                time.sleep(0.5)          # 让长请求先进服务（复现 VEGA-25 的排队场景）
                short = ex.submit(one_request, a.short, t0, 99, c).result()
                longs = [f.result() for f in fl]
            r = {
                "rep": rep,
                "long_elapsed": [x["elapsed"] for x in longs],
                "long_http": [x.get("http") for x in longs],
                "long_chunks": [x.get("n_chunks") for x in longs],
                "short_elapsed": short["elapsed"], "short_http": short.get("http"),
                "short_chunks": short.get("n_chunks"),
                "short_finished_before_all_long": all(short["t_end"] < x["t_end"] for x in longs),
                "short_end": short["t_end"],
                "long_end_max": max(x["t_end"] for x in longs),
            }
            res["rounds"].append(r)
            print(f"  hol rep={rep} long={r['long_elapsed']} short={r['short_elapsed']}s "
                  f"short_before_all_long={r['short_finished_before_all_long']}", file=sys.stderr)
    res["asr_pid"] = pid
    res["判据"] = ("串行服务：短请求必须等前面所有长请求做完（short_elapsed ≥ 最长长请求耗时）；"
                 "并发服务：短请求在长请求仍在飞时就完成（short_elapsed ≪ 长请求耗时）")
    print(json.dumps(res, ensure_ascii=False))


def cmd_regress(a):
    all_wavs = json.load(open(a.list, encoding="utf-8"))
    paths = [w["path"] for w in all_wavs if w["path"].lower().endswith(".wav")]
    rnd = random.Random(a.seed)
    sample = rnd.sample(paths, min(a.sample, len(paths)))
    if a.include:
        for p in a.include.split(";"):
            if p and p not in sample:
                sample.append(p)
    res = {"seed": a.seed, "n_sample": len(sample), "files": {}}
    with httpx.Client(timeout=TIMEOUT, limits=httpx.Limits(max_connections=64)) as c:
        # ① 顺序两遍（同版本自身抖动带）
        for p in sample:
            runs = []
            for _ in range(2):
                t0 = time.time()
                runs.append(one_request(p, t0, 0, c))
            res["files"][p] = {"seq": runs}
            print(f"  seq {os.path.basename(p)} chunks={[r.get('n_chunks') for r in runs]}",
                  file=sys.stderr)
        # ② 并发一遍（N = 样本数，线程池上限内）
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=len(sample)) as ex:
            conc = list(ex.map(lambda ip: one_request(ip[1], t0, ip[0], c), enumerate(sample)))
        for p, r in zip(sample, conc):
            res["files"][p]["conc"] = r
            print(f"  conc {os.path.basename(p)} chunks={r.get('n_chunks')} http={r.get('http')}",
                  file=sys.stderr)
    # ③ 判定
    def diff(a_, b_):
        ca, cb = a_.get("chunks") or [], b_.get("chunks") or []
        if len(ca) != len(cb):
            return {"n_chunks": [len(ca), len(cb)], "count_mismatch": True}
        nd = 0
        dt = dd = 0.0
        for x, y in zip(ca, cb):
            if x.get("text") != y.get("text"):
                nd += 1
            tx, ty = x.get("timestamp") or [0, 0], y.get("timestamp") or [0, 0]
            dt = max(dt, abs(tx[0] - ty[0]))
            dd = max(dd, abs(tx[1] - ty[1]))
        return {"n_chunks": [len(ca), len(cb)], "count_mismatch": False,
                "text_diff": nd, "max_d_start": round(dt, 3), "max_d_end": round(dd, 3),
                "text_same": (a_.get("text") == b_.get("text"))}

    summary = {"count_mismatch_any": False, "conc_vs_seq_jitter_band": [], "rows": []}
    for p, v in res["files"].items():
        seq = v["seq"]
        jitter = diff(seq[0], seq[1])            # 同版本自身抖动带
        cross = diff(seq[0], v["conc"])          # 并发 vs 顺序（本改动引入的差异）
        v["jitter_self"] = jitter
        v["conc_vs_seq"] = cross
        if cross.get("count_mismatch") or jitter.get("count_mismatch"):
            summary["count_mismatch_any"] = True
        row = {
            "file": os.path.basename(p),
            "chunks_seq": jitter["n_chunks"], "chunks_conc": cross["n_chunks"][1],
            "jitter_text_diff": jitter.get("text_diff"), "jitter_max_d": [jitter.get("max_d_start"), jitter.get("max_d_end")],
            "conc_text_diff": cross.get("text_diff"), "conc_max_d": [cross.get("max_d_start"), cross.get("max_d_end")],
            "conc_http": v["conc"].get("http"), "conc_elapsed": v["conc"].get("elapsed"),
        }
        row["conc_within_jitter"] = (
            not cross.get("count_mismatch")
            and cross.get("text_diff", 0) <= max(jitter.get("text_diff", 0), 1)
            and cross.get("max_d_start", 0) <= max(jitter.get("max_d_start", 0), 0.2) + 1e-9
            and cross.get("max_d_end", 0) <= max(jitter.get("max_d_end", 0), 0.2) + 1e-9
        )
        summary["rows"].append(row)
    summary["all_count_equal"] = not summary["count_mismatch_any"]
    summary["all_within_jitter"] = all(r["conc_within_jitter"] for r in summary["rows"])
    res["summary"] = summary
    print(json.dumps(res, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("health"); h.set_defaults(fn=cmd_health)

    s = sub.add_parser("shape")
    s.add_argument("--wav", required=True)
    s.add_argument("--audio-sec", type=float, default=None)
    s.add_argument("--ns", default="1,2,4,8")
    s.add_argument("--reps", type=int, default=2)
    s.set_defaults(fn=cmd_shape)

    o = sub.add_parser("hol")
    o.add_argument("--long", required=True)
    o.add_argument("--long-sec", type=float, default=None)
    o.add_argument("--short", required=True)
    o.add_argument("--short-sec", type=float, default=None)
    o.add_argument("--nlong", type=int, default=1)
    o.add_argument("--reps", type=int, default=3)
    o.set_defaults(fn=cmd_hol)

    r = sub.add_parser("regress")
    r.add_argument("--list", required=True)
    r.add_argument("--sample", type=int, default=10)
    r.add_argument("--seed", type=int, default=20261016)
    r.add_argument("--include", default="")
    r.set_defaults(fn=cmd_regress)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
