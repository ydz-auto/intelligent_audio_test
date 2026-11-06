# -*- coding: utf-8 -*-
"""WER/SER 新 API 冒烟脚本（/api/create_task + /api/get_status + /api/get_final_result）。

由旧脚本 tests/test_new_api.py + tests/test_new_api_ser.py 合并更新：
  - 端点统一为 /api/create_task（旧 /calculate_wer、/calculate_ser 已下线）
  - 任务主键取 data.eval_task_id（data.task_id 是调用方 id，未传时为空）
用法：
  python tests/text_metrics/test_text_api.py [--base-url http://127.0.0.1:5001]
"""
import argparse
import json
import sys
import time

import requests

DEFAULT_BASE_URL = 'http://127.0.0.1:5001'


def _create_and_poll(base_url, task_type, payload, timeout=15):
    create = requests.post(f"{base_url.rstrip('/')}/api/create_task", json=payload, timeout=15)
    create.raise_for_status()
    body = create.json()
    if body.get('code') != 0:
        raise RuntimeError(f"创建任务失败: {body}")
    eval_task_id = body['data']['eval_task_id']
    print(f"  任务已创建: task_type={task_type}, eval_task_id={eval_task_id}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        status = requests.get(f"{base_url.rstrip('/')}/api/get_status/{eval_task_id}", timeout=15)
        status.raise_for_status()
        state = status.json().get('data', {}).get('status')
        if state in {'completed', 'failed'}:
            break
        time.sleep(0.5)

    final = requests.get(f"{base_url.rstrip('/')}/api/get_final_result/{eval_task_id}", timeout=15)
    final.raise_for_status()
    return eval_task_id, final.json()


def _run_wer(base_url):
    print("=== WER 任务 ===")
    payload = {
        'task_type': 'wer',
        'asr_ref': '这是一个测试测试文本text',
        'asr_hyp': '这是一个测试文本text',
    }
    eval_task_id, response = _create_and_poll(base_url, 'wer', payload)
    result = response.get('data', {}).get('result', {})
    assert result.get('wer') is not None, f"WER 结果缺失: {response}"
    print(f"  WER 结果: wer={result['wer']}, wer_zh={result['wer_zh']}, wer_en={result['wer_en']}")
    return eval_task_id


def _run_ser(base_url):
    print("=== SER 任务 ===")
    payload = {
        'task_type': 'ser',
        'asr_ref': '这是第一个测试句子。这是第二个测试句子。',
        'asr_hyp': '这是第一个测试句子这是第二个测试句子。',
    }
    eval_task_id, response = _create_and_poll(base_url, 'ser', payload)
    result = response.get('data', {}).get('result', {})
    assert result.get('ser') is not None, f"SER 结果缺失: {response}"
    print(f"  SER 结果: ser={result['ser']}, error_sentences={result.get('error_sentences')}")
    return eval_task_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL)
    args = parser.parse_args()

    _run_wer(args.base_url)
    _run_ser(args.base_url)
    print("=== WER/SER 新 API 冒烟测试完成 ===")


if __name__ == '__main__':
    main()
