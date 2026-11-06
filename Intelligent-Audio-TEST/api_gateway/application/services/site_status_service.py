# -*- coding: utf-8 -*-
"""站点状态应用服务（INT-620）。

GET /api/status 契约（对位 newAPI）：snake_case wire 字段
`{ api_base_url, server_address }`，前端 infrastructure/statusApi.ts 是
唯一 snake→camel 转换层。server_address 取请求可达地址（X-Forwarded-Proto
/ X-Forwarded-Host 优先——nginx 反代场景下 client 见到的协议/主机，回退
请求 scheme/netloc）；api_base_url = 站点根 + /api/v1（与 frontend-react
client.ts API_BASE_URL='/api/v1' 及文档页「示例地址 = 站点根 + /api/v1」
口径一致）。读侧，无副作用。
"""
import logging

from api_gateway.utils.response import error_response, success_response

logger = logging.getLogger(__name__)

API_PREFIX = '/api/v1'


class SiteStatusService:
    """站点状态读侧服务。"""

    @staticmethod
    def get_site_status(request):
        """由请求推导站点状态；异常时 500 结构化错误（前端回退 origin）。"""
        try:
            headers = request.headers
            scheme = (headers.get('x-forwarded-proto')
                      or getattr(request.url, 'scheme', '') or 'http')
            host = (headers.get('x-forwarded-host')
                    or headers.get('host')
                    or getattr(request.url, 'netloc', '') or '')
            server_address = f'{scheme}://{host}'
            api_base_url = f'{server_address}{API_PREFIX}'
            return success_response(data={
                'api_base_url': api_base_url,
                'server_address': server_address,
            })
        except Exception as e:
            logger.warning("获取站点状态失败", exc_info=True)
            return error_response(message=f"获取站点状态失败: {e}")
