#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 task_id 汇总 eval_server tasks 日志，打印客观指标统计。

用法:
    # 汇总指定日期
    python summarize_tasks.py 2026-08-17

    # 汇总所有日期
    python summarize_tasks.py all

    # 默认汇总最新日期
    python summarize_tasks.py

数据来源: static/eval_server/tasks/<date>/task_*.json
"""

import sys
import os
import json
import glob
from collections import defaultdict
from datetime import datetime

# tasks 根目录
TASKS_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'static', 'eval_server', 'tasks'
)

# 视为同一指标体系 task_type
METRICS_TASK_TYPES = ('xiaoyi_metrics', 'turn_taking', 'takeover')


def load_tasks(date_dir):
    """加载某日期目录下全部 task JSON"""
    pattern = os.path.join(date_dir, 'task_*.json')
    tasks = []
    for fp in sorted(glob.glob(pattern)):
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                tasks.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    return tasks


def _safe_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _avg(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def _fmt_ms(val):
    return f'{val:.1f}ms' if val is not None else 'N/A'


def _fmt_pct(count, total):
    if total == 0:
        return 'N/A'
    return f'{count}/{total} = {count / total * 100:.1f}%'


def _fmt_float(val, unit=''):
    return f'{val:.3f}{unit}' if val is not None else 'N/A'


def summarize_metrics_task(results):
    """汇总单个 xiaoyi/turn_taking task 的 result 子项"""
    if not isinstance(results, list):
        results = [results]

    tor_vals, ft_vals, lat_vals = [], [], []
    input_asr_matches, input_asr_total = 0, 0
    intr_success_rates, stop_rates, resume_rates = [], [], []
    intr_stop_lats, intr_recovery_lats = [], []
    nil_stop_lats, nil_recovery_lats = [], []

    for r in results:
        if not isinstance(r, dict):
            continue
        tor_obj = r.get('tor') or {}
        ft_obj = r.get('false_takeover') or {}
        tl_obj = r.get('takeover_latency') or {}

        if tor_obj.get('tor') is not None:
            tor_vals.append(tor_obj['tor'])
        if ft_obj.get('tor') is not None:
            ft_vals.append(ft_obj['tor'])
        if tl_obj.get('takeover_latency_ms') is not None:
            v = _safe_float(tl_obj['takeover_latency_ms'])
            if v is not None:
                lat_vals.append(v)

        # input_asr
        ia = r.get('input_asr') or {}
        if ia.get('match') is not None:
            input_asr_total += 1
            if ia.get('match'):
                input_asr_matches += 1

        # interruption
        intr = r.get('interruption') or {}
        if intr.get('interruption_success_rate') is not None:
            intr_success_rates.append(_safe_float(intr['interruption_success_rate']))
        if intr.get('stop_rate') is not None:
            stop_rates.append(_safe_float(intr['stop_rate']))
        if intr.get('resume_rate') is not None:
            resume_rates.append(_safe_float(intr['resume_rate']))
        if intr.get('avg_stop_latency_s') is not None:
            intr_stop_lats.append(_safe_float(intr['avg_stop_latency_s']))
        if intr.get('avg_recovery_latency_s') is not None:
            intr_recovery_lats.append(_safe_float(intr['avg_recovery_latency_s']))

        # non_interactive_latency
        nil = r.get('non_interactive_latency') or {}
        if nil.get('stop_latency_s') is not None:
            nil_stop_lats.append(_safe_float(nil['stop_latency_s']))
        if nil.get('recovery_latency_s') is not None:
            nil_recovery_lats.append(_safe_float(nil['recovery_latency_s']))

    n_total = len(results)
    tor_1_count = sum(1 for v in tor_vals if v == 1)
    ft_0_count = sum(1 for v in ft_vals if v == 0)

    lines = []
    lines.append(f"  用例总数 total_cases              : {n_total}")
    lines.append(f"  --- tor / false_takeover / takeover_latency ---")
    lines.append(f"  接话率 tor=1 比例                  : {_fmt_pct(tor_1_count, len(tor_vals))}")
    lines.append(f"  平均接管时延 takeover_latency_ms    : {_fmt_ms(_avg(lat_vals))}")
    lines.append(f"  误接管率 false_takeover tor=0 比例  : {_fmt_pct(ft_0_count, len(ft_vals))}")
    lines.append(f"  --- input_asr ---")
    lines.append(f"  问题ASR匹配率                     : {_fmt_pct(input_asr_matches, input_asr_total)}")
    lines.append(f"  --- interruption ---")
    lines.append(f"  打断成功率                         : {_fmt_float(_avg(intr_success_rates))}")
    lines.append(f"  停止率                             : {_fmt_float(_avg(stop_rates))}")
    lines.append(f"  恢复率                             : {_fmt_float(_avg(resume_rates))}")
    lines.append(f"  平均停止时延 (s)                   : {_fmt_float(_avg(intr_stop_lats), 's')}")
    lines.append(f"  平均恢复时延 (s)                   : {_fmt_float(_avg(intr_recovery_lats), 's')}")
    lines.append(f"  --- non_interactive_latency ---")
    lines.append(f"  平均停止时延 (s)                   : {_fmt_float(_avg(nil_stop_lats), 's')}")
    lines.append(f"  平均恢复时延 (s)                   : {_fmt_float(_avg(nil_recovery_lats), 's')}")
    return '\n'.join(lines)


def summarize_llm_judge_task(results):
    """汇总 llm_judge task"""
    if not isinstance(results, list):
        results = [results]

    scores = []
    tokens = []
    models = defaultdict(int)
    for r in results:
        if not isinstance(r, dict):
            continue
        if r.get('llm_judge_score') is not None:
            scores.append(_safe_float(r['llm_judge_score']))
        if r.get('tokens_used') is not None:
            v = _safe_float(r['tokens_used'])
            if v is not None:
                tokens.append(v)
        if r.get('model'):
            models[r['model']] += 1

    lines = []
    lines.append(f"  用例总数 total_cases              : {len(results)}")
    lines.append(f"  平均得分 llm_judge_score          : {_fmt_float(_avg(scores))}  (范围 {min(scores) if scores else 'N/A'}~{max(scores) if scores else 'N/A'})")
    lines.append(f"  平均 token 用量                   : {_fmt_float(_avg(tokens))}")
    lines.append(f"  模型分布                          : {dict(models) if models else 'N/A'}")
    return '\n'.join(lines)


def summarize_generic_task(results, task_type):
    """通用汇总（wer/ser/der 等）"""
    if not isinstance(results, list):
        results = [results]
    lines = [f"  用例总数: {len(results)}"]
    # 尝试提取数值字段做平均
    if results and isinstance(results[0], dict):
        for key in results[0]:
            vals = [_safe_float(r.get(key)) for r in results if isinstance(r, dict) and r.get(key) is not None]
            vals = [v for v in vals if v is not None]
            if vals and len(vals) == len(results):
                lines.append(f"  {key}: avg={_fmt_float(_avg(vals))}  (min={min(vals):.3f}, max={max(vals):.3f})")
    return '\n'.join(lines)


def group_tasks(tasks):
    """按 task_id 分组"""
    groups = defaultdict(list)
    for t in tasks:
        tid = str(t.get('task_id') or 'unknown')
        groups[tid].append(t)
    return groups


def print_summary(tasks):
    groups = group_tasks(tasks)

    for task_id in sorted(groups.keys(), key=lambda x: (len(x), x)):
        grp = groups[task_id]
        # 取 task_type（同组应一致）
        task_type = grp[0].get('task_type', 'unknown')
        completed = [t for t in grp if t.get('status') == 'completed']
        failed = [t for t in grp if t.get('status') == 'failed']
        results = [t['result'] for t in completed if t.get('result')]

        print(f"\n{'=' * 80}")
        print(f"  task_id={task_id}  task_type={task_type}  "
              f"total={len(grp)}  completed={len(completed)}  failed={len(failed)}")
        print(f"{'=' * 80}")

        if not results:
            print("  (无有效 result 数据)")
            if failed:
                errs = set()
                for t in failed:
                    msg = t.get('error_msg') or ''
                    errs.add(msg[:100])
                for e in list(errs)[:5]:
                    print(f"  [failed] {e}")
            continue

        if task_type in METRICS_TASK_TYPES:
            print(summarize_metrics_task(results))
        elif task_type == 'llm_judge':
            print(summarize_llm_judge_task(results))
        else:
            print(summarize_generic_task(results, task_type))


def main():
    if len(sys.argv) > 1 and sys.argv[1] != 'all':
        date_str = sys.argv[1]
    else:
        # 列出所有日期目录，取最新
        if not os.path.isdir(TASKS_ROOT):
            print(f"tasks 目录不存在: {TASKS_ROOT}")
            sys.exit(1)
        all_dates = sorted([d for d in os.listdir(TASKS_ROOT)
                            if os.path.isdir(os.path.join(TASKS_ROOT, d))])
        if not all_dates:
            print("无日期目录")
            sys.exit(1)
        if len(sys.argv) > 1 and sys.argv[1] == 'all':
            date_str = None  # 全部
        else:
            date_str = all_dates[-1]

    if date_str:
        date_dirs = [os.path.join(TASKS_ROOT, date_str)]
    else:
        date_dirs = [os.path.join(TASKS_ROOT, d)
                     for d in sorted(os.listdir(TASKS_ROOT))
                     if os.path.isdir(os.path.join(TASKS_ROOT, d))]

    all_tasks = []
    for dd in date_dirs:
        if os.path.isdir(dd):
            all_tasks.extend(load_tasks(dd))

    if not all_tasks:
        print("未找到任何 task 文件")
        sys.exit(1)

    print(f"\n扫描日期目录: {', '.join(os.path.basename(d) for d in date_dirs)}")
    print(f"加载任务总数: {len(all_tasks)}")
    print_summary(all_tasks)


if __name__ == '__main__':
    main()
