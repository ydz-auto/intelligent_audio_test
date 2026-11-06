# -*- coding: utf-8 -*-
"""健康检查冒烟脚本：/api/status（旧根路径 / 的并发统计已迁移至此）。"""
import argparse
import json

import requests

DEFAULT_BASE_URL = 'http://127.0.0.1:5001'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL)
    args = parser.parse_args()

    url = f"{args.base_url.rstrip('/')}/api/status"
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    body = response.json()
    print(json.dumps(body, indent=2, ensure_ascii=False))

    data = body.get('data', {})
    assert body.get('code') == 0, f"健康检查失败: {body}"
    assert 'local' in data and 'dimension' in data, f"响应缺少并发统计: {body}"
    local = data['local']
    print(
        f"本地并发: {local['current_concurrency']}/{local['max_concurrency']} "
        f"(可用 {local['available_concurrency']})"
    )
    print(f"维度并发: {json.dumps(data['dimension'], ensure_ascii=False)}")


if __name__ == '__main__':
    main()
