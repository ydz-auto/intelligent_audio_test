"""验证单桶模式：检查 DB 记录的 file_path 与 OSS 实际存储路径"""
import requests
import os, sys

# 查 DB 里的音频记录
resp = requests.get('http://localhost:5000/api/v1/audios?page=1&per_page=100')
print(f'API status: {resp.status_code}')
data = resp.json()
audios = data.get('data', {}).get('audios', [])
print(f'DB 共 {len(audios)} 条记录:')
for a in audios:
    print(f"  name={a.get('name')} | file_path={a.get('file_path')}")

# 查 OSS 单桶里的实际文件
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared.clients.oss_client import oss
print(f'\nOSS 单桶模式: bucket={oss._single_bucket}, prefix={oss._key_prefix}')
print(f'OSS bucket={oss._bucket("audios")}')

# 列出新前缀下的