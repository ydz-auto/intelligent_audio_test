# -*- coding: utf-8 -*-
"""
WER/SER/CPWER/TCPWER/STM_WER/DER 指标计算样例脚本

通过 API 调用计算指标，支持：
- 纯文本格式 (WER/SER)
- STM 字符串格式 (CPWER/TCPWER/STM_WER)
- JSON 格式 (优先处理，正则化后再转 STM)
"""

import requests
import time
import json

API_BASE_URL = "http://localhost:5001"


def wait_for_task_completed(task_id, max_wait=60, poll_interval=0.5):
    """等待任务完成"""
    start_time = time.time()
    while time.time() - start_time < max_wait:
        status_response = requests.get(f"{API_BASE_URL}/api/get_status/{task_id}")
        if status_response.status_code == 200:
            status_data = status_response.json()
            status = status_data.get('data', {}).get('status')
            print(f"  任务状态: {status}")
            if status == 'completed':
                return True
            elif status == 'failed':
                return False
        time.sleep(poll_interval)
    return False


def create_text_task(task_type, asr_ref, asr_result, **kwargs):
    """创建纯文本任务（WER/SER）并等待结果"""
    print(f"\n{'='*60}")
    print(f"创建 {task_type.upper()} 任务（纯文本）")
    print(f"{'='*60}")
    print(f"参考文本: {asr_ref}")
    print(f"识别结果: {asr_result}")
    if kwargs.get('normalize'):
        print(f"正则化: 开启")

    payload = {
        "task_type": task_type,
        "asr_ref": asr_ref,
        "asr_result": asr_result,
        **kwargs
    }

    response = requests.post(f"{API_BASE_URL}/api/create_task", json=payload)
    print(f"\n创建任务响应: {response.status_code}")

    if response.status_code != 200:
        print(f"创建任务失败: {response.text}")
        return None

    data = response.json()
    task_id = data['data']['task_id']
    print(f"任务 ID: {task_id}")

    if not wait_for_task_completed(task_id):
        print("任务等待超时或失败")
        return None

    result_response = requests.get(f"{API_BASE_URL}/api/get_final_result/{task_id}")
    if result_response.status_code == 200:
        result_data = result_response.json()
        return result_data.get('data', {}).get('result')
    return None


def create_stm_task(task_type, ref_stm, hyp_stm, **kwargs):
    """创建 STM 格式任务（CPWER/TCPWER/STM_WER）并等待结果"""
    print(f"\n{'='*60}")
    print(f"创建 {task_type.upper()} 任务（STM格式）")
    print(f"{'='*60}")

    normalize = kwargs.get('normalize', False)

    if isinstance(ref_stm, dict):
        print(f"输入格式: JSON")
        print(f"参考 JSON: {json.dumps(ref_stm, ensure_ascii=False)[:100]}...")
        print(f"识别 JSON: {json.dumps(hyp_stm, ensure_ascii=False)[:100]}...")
    else:
        print(f"输入格式: STM字符串")
        print(f"参考 STM:\n{ref_stm}")
        print(f"识别 STM:\n{hyp_stm}")

    if normalize:
        print(f"处理流程: STM字符串 -> JSON -> 正则化 -> STM")

    payload = {
        "task_type": task_type,
        "ref_stm": ref_stm,
        "hyp_stm": hyp_stm,
        **kwargs
    }

    response = requests.post(f"{API_BASE_URL}/api/create_task", json=payload)
    print(f"\n创建任务响应: {response.status_code}")

    if response.status_code != 200:
        print(f"创建任务失败: {response.text}")
        return None

    data = response.json()
    task_id = data['data']['task_id']
    print(f"任务 ID: {task_id}")

    if not wait_for_task_completed(task_id):
        print("任务等待超时或失败")
        return None

    result_response = requests.get(f"{API_BASE_URL}/api/get_final_result/{task_id}")
    if result_response.status_code == 200:
        result_data = result_response.json()
        return result_data.get('data', {}).get('result')
    return None


def create_der_task(rttm_ref, stm_ref, rttm_res, stm_res, **kwargs):
    """创建 DER 任务并等待结果"""
    print(f"\n{'='*60}")
    print(f"创建 DER 任务")
    print(f"{'='*60}")

    if isinstance(rttm_ref, dict):
        print(f"输入格式: JSON")
    else:
        print(f"输入格式: RTTM/STM 字符串")

    payload = {
        "task_type": "der",
        "rttm_ref": rttm_ref,
        "stm_ref": stm_ref,
        "rttm_res": rttm_res,
        "stm_res": stm_res,
        **kwargs
    }

    response = requests.post(f"{API_BASE_URL}/api/create_task", json=payload)
    print(f"\n创建任务响应: {response.status_code}")

    if response.status_code != 200:
        print(f"创建任务失败: {response.text}")
        return None

    data = response.json()
    task_id = data['data']['task_id']
    print(f"任务 ID: {task_id}")

    if not wait_for_task_completed(task_id):
        print("任务等待超时或失败")
        return None

    result_response = requests.get(f"{API_BASE_URL}/api/get_final_result/{task_id}")
    if result_response.status_code == 200:
        result_data = result_response.json()
        return result_data.get('data', {}).get('result')
    return None


def example_wer():
    """WER 计算样例（纯文本）"""
    ref = "今天天气很好 我们出去走走吧"
    hyp = "今天天气很好 我们出去走走吧"

    result = create_text_task("wer", ref, hyp)
    if result:
        print(f"\nWER 结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))


def example_wer_normalize():
    """WER 计算样例（带正则化）"""
    ref = "今天天气很好 我们出去走走吧"
    hyp = "今天天气很好    我们出去走走吧"

    result = create_text_task("wer", ref, hyp, normalize=True)
    if result:
        print(f"\nWER 结果 (正则化):")
        print(json.dumps(result, indent=2, ensure_ascii=False))


def example_ser():
    """SER 计算样例（纯文本）"""
    ref = "今天天气很好。我们出去走走吧！"
    hyp = "今天天气很好。我们出去走走吧。"

    result = create_text_task("ser", ref, hyp)
    if result:
        print(f"\nSER 结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))


def example_cpwer_string():
    """CPWER 计算样例（STM字符串格式）"""
    ref_stm = """rec1 1 spk1 0 1.5 hello world this is a test
rec1 1 spk2 1.5 3.0 how are you today"""

    hyp_stm = """rec1 1 spk1 0 1.5 hello world this is test
rec1 1 spk2 1.5 3.0 how are you"""

    result = create_stm_task("cpwer", ref_stm, hyp_stm)
    if result:
        print(f"\nCPWER 结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))


def example_cpwer_string_normalize():
    """CPWER 计算样例（STM字符串格式，带正则化）"""
    ref_stm = """rec1 1 spk1 0 1.5 hello world this is a test
rec1 1 spk2 1.5 3.0 how are you today"""

    hyp_stm = """rec1 1 spk1 0 1.5 hello world this is test
rec1 1 spk2 1.5 3.0 how are you"""

    result = create_stm_task("cpwer", ref_stm, hyp_stm, normalize=True)
    if result:
        print(f"\nCPWER 结果 (正则化):")
        print(json.dumps(result, indent=2, ensure_ascii=False))


def example_cpwer_json():
    """CPWER 计算样例（JSON格式）"""
    ref_json = {
        "json": [
            {"file_id": "rec1", "channel": "1", "speaker": "spk1", "start": 0.0, "end": 1.5, "text": "hello world this is a test"},
            {"file_id": "rec1", "channel": "1", "speaker": "spk2", "start": 1.5, "end": 3.0, "text": "how are you today"}
        ]
    }

    hyp_json = {
        "json": [
            {"file_id": "rec1", "channel": "1", "speaker": "spk1", "start": 0.0, "end": 1.5, "text": "hello world this is test"},
            {"file_id": "rec1", "channel": "1", "speaker": "spk2", "start": 1.5, "end": 3.0, "text": "how are you"}
        ]
    }

    result = create_stm_task("cpwer", ref_json, hyp_json, normalize=True)
    if result:
        print(f"\nCPWER 结果 (JSON格式):")
        print(json.dumps(result, indent=2, ensure_ascii=False))


def example_tcpwer():
    """TCPWER 计算样例（STM格式，带时间约束）"""
    ref_stm = """rec1 1 spk1 0 1.0 the quick brown fox
rec1 1 spk1 1.0 2.0 jumps over the
rec1 1 spk1 2.0 3.0 lazy dog today"""

    hyp_stm = """rec1 1 spk1 0 1.0 the quick brown
rec1 1 spk1 1.0 2.0 jumps over lazy dog"""

    result = create_stm_task("tcpwer", ref_stm, hyp_stm, collar=0.5)
    if result:
        print(f"\nTCPWER 结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))


def example_stm_wer():
    """STM_WER 计算样例（STM格式）"""
    ref_stm = """rec1 1 spk1 0 2.0 hello world this is a test
rec1 1 spk2 2.0 4.0 how are you today"""

    hyp_stm = """rec1 1 spk1 0 2.0 hello world this is test
rec1 1 spk2 2.0 4.0 how are you"""

    result = create_stm_task("stm_wer", ref_stm, hyp_stm)
    if result:
        print(f"\nSTM_WER 结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))


def example_der():
    """DER 计算样例"""
    rttm_ref = {
        "json": [
            {"speaker": "speaker1", "start": 0.0, "duration": 1.0},
            {"speaker": "speaker2", "start": 1.0, "duration": 2.0}
        ]
    }
    stm_ref = {
        "json": [
            {"file_id": "rec1", "channel": "1", "speaker": "speaker1", "start": 0.0, "end": 1.0, "text": "hello world"},
            {"file_id": "rec1", "channel": "1", "speaker": "speaker2", "start": 1.0, "end": 2.0, "text": "test text"}
        ]
    }
    rttm_res = {
        "json": [
            {"speaker": "speaker1", "start": 0.0, "duration": 1.0},
            {"speaker": "speaker1", "start": 1.0, "duration": 2.0}
        ]
    }
    stm_res = {
        "json": [
            {"file_id": "rec1", "channel": "1", "speaker": "speaker1", "start": 0.0, "end": 1.0, "text": "hello world"},
            {"file_id": "rec1", "channel": "1", "speaker": "speaker1", "start": 1.0, "end": 2.0, "text": "test"}
        ]
    }

    result = create_der_task(rttm_ref, stm_ref, rttm_res, stm_res)
    if result:
        print(f"\nDER 结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))


def example_parallel_requests():
    """并发请求样例"""
    print(f"\n{'='*60}")
    print("并发请求样例")
    print(f"{'='*60}")

    tasks = [
        ("wer", "今天天气很好", "今天天气很好"),
        ("wer", "hello world", "hello world"),
        ("ser", "你好。世界！", "你好。世界"),
    ]

    def submit_text_task(task_type, ref, hyp):
        payload = {
            "task_type": task_type,
            "asr_ref": ref,
            "asr_result": hyp
        }
        response = requests.post(f"{API_BASE_URL}/api/create_task", json=payload)
        if response.status_code == 200:
            return response.json()['data']['task_id']
        return None

    task_ids = []
    print("提交并发任务...")
    for task_type, ref, hyp in tasks:
        task_id = submit_text_task(task_type, ref, hyp)
        if task_id:
            task_ids.append((task_type, task_id))
            print(f"  {task_type}: {task_id}")

    print("\n等待所有任务完成...")
    time.sleep(2)

    for task_type, task_id in task_ids:
        status_resp = requests.get(f"{API_BASE_URL}/api/get_status/{task_id}")
        if status_resp.status_code == 200:
            status = status_resp.json()['data']['status']
            print(f"  {task_type} ({task_id}): {status}")


def check_server():
    """检查服务器是否运行"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/status", timeout=2)
        if response.status_code == 200:
            print(f"✓ 服务器运行正常: {API_BASE_URL}")
            data = response.json()
            print(f"  本地并发: {data['data']['local']}")
            return True
    except requests.exceptions.RequestException as e:
        print(f"✗ 无法连接到服务器: {API_BASE_URL}")
        print(f"  错误: {e}")
        print(f"\n请先启动服务器: python app.py")
        return False


def main():
    """主函数"""
    print("="*60)
    print("WER/SER/CPWER/TCPWER/STM_WER/DER 指标计算 API 样例")
    print("="*60)

    if not check_server():
        return

    print("\n" + "="*60)
    print("纯文本任务")
    print("="*60)
    example_wer()
    time.sleep(1)

    example_wer_normalize()
    time.sleep(1)

    example_ser()
    time.sleep(1)

    print("\n" + "="*60)
    print("STM 字符串格式任务")
    print("="*60)
    example_cpwer_string()
    time.sleep(1)

    example_cpwer_string_normalize()
    time.sleep(1)

    example_tcpwer()
    time.sleep(1)

    example_stm_wer()
    time.sleep(1)

    print("\n" + "="*60)
    print("JSON 格式任务（优先处理）")
    print("="*60)
    example_cpwer_json()
    time.sleep(1)

    print("\n" + "="*60)
    print("DER 任务")
    print("="*60)
    example_der()
    time.sleep(1)

    print("\n" + "="*60)
    print("并发请求")
    print("="*60)
    example_parallel_requests()

    print("\n" + "="*60)
    print("所有样例执行完成")
    print("="*60)


if __name__ == '__main__':
    main()
