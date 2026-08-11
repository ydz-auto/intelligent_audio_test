# -*- coding: utf-8 -*-
"""维度 API 端点健康探测（Infrastructure 层）

HTTP 探测是技术细节，放在 Infrastructure 层。
Application 层通过此服务委托 HTTP 探测，不直接 import requests。
"""
import time
from typing import Any, Dict, List

import requests
from requests.exceptions import RequestException


class EndpointHealthChecker:
    """对维度配置的 API 端点进行 HTTP 健康探测"""

    def check_endpoints(
        self,
        endpoints: List[Dict[str, Any]],
        api_settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        """对多个端点执行健康探测。

        Returns:
            {
                'results': [{url, status, status_code, response_time, message}, ...],
                'all_online': bool,
            }
        """
        results = []
        all_online = True
        settings = api_settings or {}
        headers = settings.get('headers', {})

        for endpoint in endpoints:
            url = endpoint.get('url') or endpoint.get('endpoint')
            if not url:
                continue

            start_time = time.time()
            try:
                response = requests.get(url, headers=headers, timeout=10)
                duration = (time.time() - start_time) * 1000

                if 200 <= response.status_code < 400:
                    endpoint_status = 'online'
                    message = '健康探测完成'
                else:
                    endpoint_status = 'offline'
                    message = f'探测失败，状态码: {response.status_code}'
                    all_online = False

                results.append({
                    'url': url,
                    'status': endpoint_status,
                    'status_code': response.status_code,
                    'response_time': f'{duration:.2f}ms',
                    'message': message,
                })
            except RequestException as e:
                results.append({
                    'url': url,
                    'status': 'offline',
                    'error': str(e),
                    'message': '健康探测失败',
                })
                all_online = False

        return {'results': results, 'all_online': all_online}


# 模块级单例
endpoint_health_checker = EndpointHealthChecker()
