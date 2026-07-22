# -*- coding: utf-8 -*-
"""测试 /api/create_task_upload 和 /api/create_task 端点"""
import requests
import time
import os

BASE_URL = "http://127.0.0.1:5001"

def _wait_and_get_result(eval_task_id):
    """等待任务完成并获取结果"""
    for _ in range(10):
        time.sleep(2)
        status_resp = requests.get(f"{BASE_URL}/api/get_status/{eval_task_id}")
        status_data = status_resp.json()
        status = status_data.get('data', {}).get('status', '')
        print(f"  状态: {status}")
        if status in ('completed', 'failed'):
            result_resp = requests.get(f"{BASE_URL}/api/get_final_result/{eval_task_id}")
            print(f"  最终结果: {result_resp.json()}")
            return result_resp.json()
    print("  超时")
    return None

def test_text_file_upload():
    """测试文本文件上传（WER 任务），带调用方 task_id"""
    print("\n=== 测试1: 文本文件上传 (WER) + 调用方 task_id ===")

    ref_text = "hello world this is a test"
    hyp_text = "hello word this is test"

    files = {
        'asr_ref': ('asr_ref.txt', ref_text.encode('utf-8'), 'text/plain'),
        'asr_hyp': ('asr_hyp.txt', hyp_text.encode('utf-8'), 'text/plain'),
    }
    data = {'task_type': 'wer', 'task_id': 'caller_test_001'}

    resp = requests.post(f"{BASE_URL}/api/create_task_upload", data=data, files=files)
    print(f"Status: {resp.status_code}")
    resp_json = resp.json()
    print(f"Response: {resp_json}")

    if resp_json.get('code') == 0:
        eval_task_id = resp_json['data']['eval_task_id']
        returned_task_id = resp_json['data'].get('task_id')
        print(f"  eval_task_id: {eval_task_id}")
        print(f"  task_id (调用方): {returned_task_id}")
        _wait_and_get_result(eval_task_id)
    return resp_json

def test_binary_file_upload():
    """测试二进制文件上传，验证按 task_id 分文件夹存储"""
    print("\n=== 测试2: 二进制文件上传 + 按 task_id 存储 ===")

    fake_wav = b'RIFF' + b'\x00' * 100 + b'WAVE' + b'\x00' * 200

    files = {
        'audio_file': ('test.wav', fake_wav, 'audio/wav'),
    }
    data = {'task_type': 'wer', 'asr_ref': 'reference text', 'asr_hyp': 'result text', 'task_id': 'caller_test_002'}

    resp = requests.post(f"{BASE_URL}/api/create_task_upload", data=data, files=files)
    print(f"Status: {resp.status_code}")
    resp_json = resp.json()
    print(f"Response: {resp_json}")

    # 检查文件是否保存到 uploads/caller_test_002/ 目录
    upload_base = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'eval_server', 'uploads')
    expected_dir = os.path.join(upload_base, 'caller_test_002')
    if os.path.exists(expected_dir):
        saved_files = os.listdir(expected_dir)
        print(f"  上传目录: uploads/caller_test_002/")
        print(f"  文件数: {len(saved_files)}")
        if saved_files:
            print(f"  文件: {saved_files}")
    else:
        print(f"  [警告] 期望目录不存在: {expected_dir}")
        if os.path.exists(upload_base):
            print(f"  uploads/ 目录内容: {os.listdir(upload_base)}")

    return resp_json

def test_json_endpoint_still_works():
    """测试原 JSON 端点仍然正常（向后兼容）"""
    print("\n=== 测试3: JSON 端点向后兼容 ===")

    payload = {
        'task_type': 'wer',
        'asr_ref': 'hello world',
        'asr_hyp': 'hello word'
    }
    resp = requests.post(f"{BASE_URL}/api/create_task",
                         json=payload,
                         headers={'Content-Type': 'application/json'})
    print(f"Status: {resp.status_code}")
    resp_json = resp.json()
    print(f"Response: {resp_json}")

    if resp_json.get('code') == 0:
        eval_task_id = resp_json['data']['eval_task_id']
        print(f"  eval_task_id: {eval_task_id}")
        _wait_and_get_result(eval_task_id)

    return resp_json

def test_mixed_upload():
    """测试混合上传（STM 文件 + 标量字段）"""
    print("\n=== 测试4: 混合上传（STM 文件 + 标量参数）===")

    ref_stm = """1 0 0 5.0 1.0 speaker1 hello world
1 0 5.0 10.0 1.0 speaker1 this is a test"""
    hyp_stm = """1 0 0 5.0 1.0 speaker1 hello word
1 0 5.0 10.0 1.0 speaker1 this is test"""

    files = {
        'ref_stm': ('ref.stm', ref_stm.encode('utf-8'), 'text/plain'),
        'hyp_stm': ('hyp.stm', hyp_stm.encode('utf-8'), 'text/plain'),
    }
    data = {'task_type': 'cpwer', 'task_id': 'caller_test_004'}

    resp = requests.post(f"{BASE_URL}/api/create_task_upload", data=data, files=files)
    print(f"Status: {resp.status_code}")
    resp_json = resp.json()
    print(f"Response: {resp_json}")

    if resp_json.get('code') == 0:
        eval_task_id = resp_json['data']['eval_task_id']
        print(f"  eval_task_id: {eval_task_id}")
        _wait_and_get_result(eval_task_id)

    return resp_json

if __name__ == '__main__':
    test_text_file_upload()
    test_binary_file_upload()
    test_json_endpoint_still_works()
    test_mixed_upload()
    print("\n=== 所有测试完成 ===")
