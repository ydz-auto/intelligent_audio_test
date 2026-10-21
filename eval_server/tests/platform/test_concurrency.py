# -*- coding: utf-8 -*-
"""并发排队冒烟脚本：创建多轮 WER/SER 任务并观察 /api/status 并发水位。

旧脚本调用无 /api 前缀的 /create_task（已下线），且用 data.task_id 当主键；
现统一走 /api/create_task，主键取 data.eval_task_id。
"""
import argparse
import time

import requests

DEFAULT_BASE_URL = 'http://127.0.0.1:5001'


def create_task(base_url, i, task_type):
    payload = {
        "asr_ref": f"参考文本 {i}",
        "asr_hyp": f"结果文本 {i}",
        "task_type": task_type,
    }
    response = requests.post(f"{base_url.rstrip('/')}/api/create_task", json=payload)
    response.raise_for_status()
    body = response.json()
    return body['data']['eval_task_id']


def check_health(base_url, duration=10, interval=1):
    for _ in range(int(duration / interval)):
        response = requests.get(f"{base_url.rstrip('/')}/api/status")
        response.raise_for_status()
        local = response.json()['data']['local']
        print(
            f"Health check - 本地: {local['current_concurrency']}/{local['max_concurrency']}"
        )
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL)
    args = parser.parse_args()

    # 创建 3 个 WER 任务
    for i in range(3):
        task_id = create_task(args.base_url, i, 'wer')
        print(f"WER Task {i} created: {task_id}")

    # 创建 2 个 SER 任务
    for i in range(2):
        task_id = create_task(args.base_url, i, 'ser')
        print(f"SER Task {i} created: {task_id}")

    check_health(args.base_url)


if __name__ == '__main__':
    main()
