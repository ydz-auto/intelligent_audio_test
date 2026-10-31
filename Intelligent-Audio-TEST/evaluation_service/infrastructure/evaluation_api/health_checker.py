# -*- coding: utf-8 -*-
"""维度 API 端点健康探测（Infrastructure 层）

HTTP 探测是技术细节，放在 Infrastructure 层。
Application 层通过此服务委托 HTTP 探测，不直接 import requests。

INT-2287：维度真实端点在 ``dimensions.api_url``（单列），而库内
``api_endpoints[].url/endpoint`` 绝大多数是空串。旧实现只遍历 api_endpoints，
一个端点都没探测就直接返回 ``results=[] / all_online=True``（空真），调用方据此
把不可达维度写成「在线」。现在：
- 探测目标 = ``api_url`` ∪ ``api_endpoints[].url/endpoint``（去重保序）；
- 两者都空视为「未配置端点」，返回 configured=False + 明确说明，不再算在线；
- ``all_online`` = 至少探测成功一个且无失败（空列表恒为 False）。
"""
import time
from typing import Any, Dict, List, Optional

import requests
from requests.exceptions import RequestException

from evaluation_service.domain.services.endpoint_helpers import (
    get_api_timeout_seconds,
    get_endpoint_url,
)

# 健康探测是前端弹窗打开即触发的同步请求：即使维度配置了更长的评估超时，
# 单端点探测也不超过该上限，避免死端点把页面拖到评估级超时。
PROBE_TIMEOUT_CAP_SECONDS = 10

# 端点只要有 HTTP 响应（<500）就算可达：评估服务根路径回 404/405 属正常，
# 只有 5xx 才是服务端故障。480~499 也归可达，故上界取 500。
REACHABLE_STATUS_CODE_UPPER_BOUND = 500


class EndpointHealthChecker:
    """对维度配置的 API 端点进行 HTTP 健康探测"""

    @staticmethod
    def _normalize_url(value) -> str:
        return value.strip() if isinstance(value, str) else ''

    def _probe_targets(self, endpoints, api_url) -> List[str]:
        """探测目标：api_url 优先，其次是 api_endpoints 里的 url/endpoint（去重保序）"""
        targets: List[str] = []
        primary = self._normalize_url(api_url)
        if primary:
            targets.append(primary)

        if isinstance(endpoints, list):
            for endpoint in endpoints:
                if not isinstance(endpoint, dict):
                    continue
                url = self._normalize_url(get_endpoint_url(endpoint))
                if url and url not in targets:
                    targets.append(url)
        return targets

    def check_endpoints(
        self,
        endpoints: Optional[List[Dict[str, Any]]] = None,
        api_settings: Optional[Dict[str, Any]] = None,
        api_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """对维度的 API 端点执行健康探测。

        Returns:
            {
                'results': [{url, status, status_code, response_time, message}, ...],
                'all_online': bool,   # 至少探测成功一个且无失败
                'configured': bool,   # False = api_url 与 api_endpoints 都没有可用 URL
                'message': str,       # configured=False 时的说明文案
            }
        """
        settings = api_settings if isinstance(api_settings, dict) else {}
        headers = settings.get('headers')
        if not isinstance(headers, dict):
            headers = {}
        timeout = min(get_api_timeout_seconds(settings), PROBE_TIMEOUT_CAP_SECONDS)

        targets = self._probe_targets(endpoints, api_url)
        if not targets:
            return {
                'results': [],
                'all_online': False,
                'configured': False,
                'message': '未配置 API 端点（api_url 与 api_endpoints 均为空），无可探测端点',
            }

        results = []
        for url in targets:
            start_time = time.time()
            try:
                response = requests.get(url, headers=headers, timeout=timeout)
                duration = (time.time() - start_time) * 1000

                if response.status_code < REACHABLE_STATUS_CODE_UPPER_BOUND:
                    endpoint_status = 'online'
                    message = (
                        '健康探测完成'
                        if response.status_code < 400
                        else f'端点可达（HTTP {response.status_code}）'
                    )
                else:
                    endpoint_status = 'offline'
                    message = f'探测失败，状态码: {response.status_code}'

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

        all_online = bool(results) and all(item['status'] == 'online' for item in results)
        return {'results': results, 'all_online': all_online, 'configured': True, 'message': ''}


# 模块级单例
endpoint_health_checker = EndpointHealthChecker()
