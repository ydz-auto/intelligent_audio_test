# -*- coding: utf-8 -*-
"""用本地 ASR 夹具通过 eval_server API 验证打断指标结果回传。

默认使用内置字词级 ASR，不依赖 WAV 转写或 LLM；传 --base-url 可连接运行中的
真实 eval_server。脚本覆盖单轮成功、单轮失败和两轮全成功/一轮失败四种结果。
"""
import argparse
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.calculators.xiaoyi_metrics.interruptibility.interruption import (  # noqa: E402
    compute_interruption_metrics,
)


def _pair(success=True):
    user = [
        {"text": "初始问题", "timestamp": [1.0, 1.8]},
        {"text": "等等", "timestamp": [3.6, 4.0]},
    ]
    model = [
        {"text": "回答中", "timestamp": [2.5, 3.8]},
        {"text": "恢复回复" if success else "", "timestamp": [4.8, 5.4]},
    ]
    return user, model


def _local_cases():
    user_ok, model_ok = _pair(True)
    _, model_fail = _pair(False)
    return [
        ("single_success", user_ok, model_ok, [0]),
        ("single_failure", user_ok, model_fail, [0]),
        ("multi_all_success", user_ok + [
            {"text": "再问一次", "timestamp": [8.0, 8.8]},
        ], model_ok + [
            {"text": "第二次回答", "timestamp": [7.2, 8.4]},
            {"text": "第二次恢复", "timestamp": [9.3, 9.9]},
        ], [0, 1]),
        ("multi_one_failure", user_ok + [
            {"text": "再问一次", "timestamp": [8.0, 8.8]},
        ], model_ok + [
            {"text": "第二次回答", "timestamp": [7.2, 8.4]},
        ], [0, 1]),
    ]


def calculate_local(name, user_asr, model_asr, rounds):
    result = compute_interruption_metrics(user_asr, model_asr, actual_interruption=True)
    result["case_name"] = name
    result["interruption_rounds"] = rounds
    result["dangling_interruption_rounds"] = []
    return result


def submit(base_url, result, user_asr, model_asr, timeout):
    payload = {
        "task_type": "interruption_metrics",
        "user_asr": user_asr,
        "model_asr": model_asr,
        "enable_llm_eval": False,
        "is_actual_interruption": True,
        "interruption_rounds": result.get("interruption_rounds", []),
    }
    create = requests.post(f"{base_url.rstrip('/')}/api/create_task", json=payload, timeout=15)
    create.raise_for_status()
    body = create.json()
    task_id = body.get("data", {}).get("eval_task_id") or body.get("data", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"创建任务未返回 task_id: {body}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        status = requests.get(f"{base_url.rstrip('/')}/api/get_status/{task_id}", timeout=15)
        status.raise_for_status()
        state = status.json().get("data", {}).get("status")
        if state in {"completed", "failed"}:
            break
        time.sleep(0.5)

    final = requests.get(f"{base_url.rstrip('/')}/api/get_final_result/{task_id}", timeout=15)
    if final.status_code != 200:
        raise RuntimeError(f"获取最终结果失败: {final.status_code} {final.text}")
    return task_id, final.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", help="运行中的 eval_server 地址，例如 http://127.0.0.1:5001")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    for name, user_asr, model_asr, rounds in _local_cases():
        local = calculate_local(name, user_asr, model_asr, rounds)
        print(json.dumps({
            "case_name": name,
            "interruption_success_rate": local["interruption_success_rate"],
            "timing_success_rate": local["timing_success_rate"],
            "n_events": local["n_events"],
            "per_event": local["per_event"],
        }, ensure_ascii=False, indent=2))

        if args.base_url:
            task_id, response = submit(args.base_url, local, user_asr, model_asr, args.timeout)
            print(json.dumps({"task_id": task_id, "platform_result": response}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
