import requests
import json
import time

# API端点
url = 'http://127.0.0.1:5001/api/create_task'

# 测试数据，包含新参数，使用SER任务类型
data = {
    'asr_ref': '这是第一个测试句子。这是第二个测试句子。',
    'asr_hyp': '这是第一个测试句子这是第二个测试句子。',
    'task_type': 'ser',
    'source_lang': 'zh',
    'target_lang': 'en',
    'translate_direct': 'zh2en'
}

# 发送POST请求创建任务
try:
    print("发送POST请求创建SER任务...")
    response = requests.post(url, json=data)
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    if response.status_code == 200:
        response_data = response.json()
        task_id = response_data['data']['task_id']
        status_url = response_data['data']['status_url']
        result_url = response_data['data']['final_result_url']
        
        # 等待一段时间后查询任务状态
        time.sleep(2)
        
        print("\n查询任务状态...")
        status_response = requests.get(status_url)
        print(f"状态码: {status_response.status_code}")
        print(f"响应: {json.dumps(status_response.json(), indent=2, ensure_ascii=False)}")
        
        # 获取最终结果
        print("\n获取最终结果...")
        result_response = requests.get(result_url)
        print(f"状态码: {result_response.status_code}")
        print(f"响应: {json.dumps(result_response.json(), indent=2, ensure_ascii=False)}")
        
except Exception as e:
    print(f"错误: {e}")
