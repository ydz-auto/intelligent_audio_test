import requests
import json

# API端点
url = 'http://127.0.0.1:5001/calculate_wer'

# 测试数据
data = {
    'asr_ref': '这是一个测试测试文本text',
    'asr_hyp': '这是一个测试文本text'
}

# 发送POST请求
try:
    response = requests.post(url, json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
except Exception as e:
    print(f"Error: {e}")