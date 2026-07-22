import requests
import json

# 测试API响应
url = "http://localhost:5001/api/get_final_result/task_2c58b4500f244a549dddcd9b1736bfd2"

print(f"测试API: {url}")
response = requests.get(url)
print(f"响应状态码: {response.status_code}")
print(f"响应头: {response.headers}")
print(f"响应内容: {response.text}")

# 解析JSON响应
response_json = response.json()
print(f"\n解析后的响应:")
print(json.dumps(response_json, indent=2, ensure_ascii=False))

# 检查result字段
if "data" in response_json:
    data = response_json["data"]
    if "result" in data:
        result = data["result"]
        print(f"\nResult字段内容:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if result:
            print("✅ Result字段不为空")
        else:
            print("❌ Result字段为空")
    else:
        print("❌ 响应中没有result字段")
else:
    print("❌ 响应中没有data字段")
