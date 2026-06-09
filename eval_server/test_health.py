import requests
import json

# API端点
url = 'http://127.0.0.1:5001/'

# 发送GET请求
try:
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
except Exception as e:
    print(f"Error: {e}")