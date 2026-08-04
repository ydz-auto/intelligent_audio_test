# -*- coding: utf-8 -*-
"""API 配置查询 Service（读侧）。

将 api_controller 中的查询读侧函数迁移为 ApiQueryService 的静态方法。
保留原有逻辑，不改业务。
"""
import time
import requests
import websocket
from urllib.parse import urlparse

from api_gateway.infrastructure.request_adapter import request
from shared.models.models import API
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.log_handler import log_not_emit
from shared.utils.query_utils import now_cst
from api_gateway.schemas.api import (
    ApiEndpointItem,
    ApiHealthCheckData,
    ApiItem,
    ApiListData,
)


class ApiQueryService:
    # ========== 日志辅助 ==========

    @staticmethod
    def _log(level, content, task_id=None, test_case_id=None, api_id=None, category='execution', module='API', **kwargs):
        """统一日志记录方法"""
        log_not_emit(
            level=level,
            module=module,
            content=content,
            category=category,
            source='backend',
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs
        )

    # ========== 查询 ==========

    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        keyword = request.args.get('keyword')
        status = request.args.get('status')
        algorithm_type = request.args.get('algorithm_type')

        query = API.query.filter_by(deleted=False)
        if keyword:
            query = query.filter(
                (API.name.like(f"%{keyword}%")) |
                (API.description.like(f"%{keyword}%"))
            )
        if status:
            query = query.filter_by(status=status)
        if algorithm_type:
            query = query.filter_by(algorithm_type=algorithm_type)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        apis = pagination.items

        data = []
        for api in apis:
            endpoints = []
            for i, ep in enumerate(api.api_endpoints):
                endpoints.append(
                    ApiEndpointItem(
                        id=f"{api.id}_{i}",
                        endpoint=ep.get('endpoint', ''),
                        name=ep.get('name', ''),
                        max_process=ep.get('max_process', 5),
                        max_timeout=ep.get('max_timeout', 30),
                        max_audio_duration=ep.get('max_audio_duration', 60),
                        status=ep.get('status', 'online'),
                        health_score=ep.get('health_score', 100),
                        priority=ep.get('priority', 0),
                        description=ep.get('description', ''),
                    )
                )

            data.append(
                ApiItem(
                    id=api.id,
                    name=api.name,
                    vendor=api.vendor,
                    api_url=api.api_url,
                    description=api.description,
                    status=api.status,
                    meta=api.meta if isinstance(api.meta, dict) else {},
                    algorithm_type=api.algorithm_type,
                    default_max_process=api.default_max_process,
                    default_max_timeout=api.default_max_timeout,
                    default_max_audio_duration=api.default_max_audio_duration,
                    health_score=api.health_score,
                    endpoints=endpoints,
                    created_at=api.created_at.isoformat(),
                    updated_at=api.updated_at.isoformat(),
                )
            )

        return success_response(
            ApiListData(
                items=data,
                total=pagination.total,
                page=pagination.page,
                per_page=pagination.per_page,
                pages=pagination.pages,
            )
        )

    # 获取单个API配置详情
    @staticmethod
    def get_one(api_id):
        api = API.query.filter_by(id=api_id, deleted=False).first()
        if not api:
            return error_response("未找到API配置", 404)

        endpoints = []
        for i, ep in enumerate(api.api_endpoints):
            endpoints.append(
                ApiEndpointItem(
                    id=f"{api.id}_{i}",
                    endpoint=ep.get('endpoint', ''),
                    name=ep.get('name', ''),
                    max_process=ep.get('max_process', 5),
                    max_timeout=ep.get('max_timeout', 30),
                    max_audio_duration=ep.get('max_audio_duration', 60),
                    status=ep.get('status', 'online'),
                    health_score=ep.get('health_score', 100),
                    priority=ep.get('priority', 0),
                    description=ep.get('description', ''),
                )
            )

        return success_response(
            ApiItem(
                id=api.id,
                name=api.name,
                vendor=api.vendor,
                api_url=api.api_url,
                description=api.description,
                status=api.status,
                meta=api.meta if isinstance(api.meta, dict) else {},
                algorithm_type=api.algorithm_type,
                default_max_process=api.default_max_process,
                default_max_timeout=api.default_max_timeout,
                default_max_audio_duration=api.default_max_audio_duration,
                health_score=api.health_score,
                endpoints=endpoints,
                created_at=api.created_at.isoformat(),
                updated_at=api.updated_at.isoformat(),
            )
        )

    # 测试API连接 (兼容 health_check)
    @staticmethod
    def test_connection(api_id):
        api = API.query.filter_by(id=api_id, deleted=False).first()
        if not api:
            return error_response("未找到API配置", 404)

        from shared.models.models import Log
        start_time = time.time()
        try:
            # 1. 测试api_url本身
            api_url_status = False
            api_url_error = None
            if api.api_url:
                test_api_url = api.api_url
                parsed_api_url = urlparse(test_api_url)
                api_scheme = parsed_api_url.scheme.lower()

                try:
                    if api_scheme in ['ws', 'wss']:
                        # WebSocket 测试逻辑
                        ws = websocket.WebSocket()
                        ws.settimeout(30)
                        ws.connect(test_api_url)
                        ws.close()
                        api_url_status = True
                    elif api_scheme in ['http', 'https']:
                        # 添加健康检查路径，如果URL以/结尾则直接添加，否则添加/health
                        if test_api_url and not test_api_url.endswith('/'):
                            test_api_url += '/health'
                        elif test_api_url and test_api_url.endswith('/'):
                            test_api_url += 'health'

                        api_url_response = requests.get(
                            test_api_url,
                            timeout=30,  # 使用默认超时
                            headers={"User-Agent": "Task-Manager-Health-Checker/1.0"}
                        )
                        if 200 <= api_url_response.status_code < 400:
                            api_url_status = True
                        else:
                            api_url_error = f"api_url连接失败: {api_url_response.status_code}"
                    else:
                        api_url_error = f"不支持的协议: {api_scheme}"
                except Exception as e:
                    api_url_error = f"api_url连接异常: {str(e)}"
            else:
                api_url_error = "未配置api_url"

            # 2. 测试endpoints
            endpoints_status = False
            endpoint_error = None
            endpoint_response = None
            endpoint_duration = 0

            if not api.api_endpoints:
                endpoint_error = "没有配置任何端点"
                endpoints_status = True  # 允许端点列表为空
            else:
                # 使用第一个端点进行测试
                endpoint = api.api_endpoints[0]
                test_url = endpoint.get('endpoint', '')

                if not test_url:
                    endpoint_error = "第一个端点URL为空"
                    endpoints_status = True  # 允许端点URL为空
                else:
                    # 识别协议
                    parsed_url = urlparse(test_url)
                    scheme = parsed_url.scheme.lower()

                    try:
                        if scheme in ['ws', 'wss']:
                            # WebSocket 测试逻辑
                            ws = websocket.WebSocket()
                            ws.settimeout(endpoint.get('max_timeout', 30))
                            ws.connect(test_url)
                            endpoint_duration = (time.time() - start_time) * 1000 # ms
                            ws.close()
                            endpoints_status = True

                        elif scheme in ['http', 'https']:
                            # HTTP 测试逻辑
                            # 添加健康检查路径，如果URL以/结尾则直接添加，否则添加/health
                            if test_url and not test_url.endswith('/'):
                                test_url += '/health'
                            elif test_url and test_url.endswith('/'):
                                test_url += 'health'

                            endpoint_response = requests.get(
                                test_url,
                                timeout=endpoint.get('max_timeout', 30),
                                headers={"User-Agent": "Task-Manager-Health-Checker/1.0"}
                            )
                            endpoint_duration = (time.time() - start_time) * 1000 # ms

                            if 200 <= endpoint_response.status_code < 400:
                                endpoints_status = True
                            else:
                                endpoint_error = f"端点连接失败: {endpoint_response.status_code}"
                        else:
                            endpoint_error = f"不支持的协议: {scheme}"

                    except Exception as e:
                        endpoint_error = f"端点连接异常: {str(e)}"

            # 3. 综合判断API状态
            # 修改：只要主URL在线，API就认为在线
            overall_status = api_url_status

            # 4. 记录日志
            if overall_status:
                log_content = f"API [{api.name}] 连接测试成功: 主URL在线"
                if not endpoints_status:
                    log_content += f" (端点测试状态: {endpoint_error})"
                elif endpoint_duration > 0:
                    log_content += f", 端点响应耗时: {endpoint_duration:.2f}ms"
                log_level = 'INFO'
            else:
                log_content = f"API [{api.name}] 连接测试失败: {api_url_error}"
                log_level = 'ERROR'

            # 写入日志
            ApiQueryService._log(
                level=log_level,
                category='HealthCheck',
                source='System',
                content=log_content,
                api_id=api.id
            )

            # 5. 更新API状态
            new_status = 'online' if overall_status else 'offline'
            if api.status != new_status:
                api.status = new_status
                api.updated_at = now_cst()
                db.session.commit()

            # 6. 构建响应
            return success_response(
                ApiHealthCheckData(
                    id=api.id,
                    status=new_status,
                    health_score=api.health_score,
                    api_url_status=str(api_url_status),
                    endpoints_status=str(endpoints_status),
                    error=api_url_error if not overall_status else None,
                    warning=endpoint_error if overall_status and not endpoints_status else None,
                    status_code=endpoint_response.status_code if endpoint_response else None,
                    response_time=f"{endpoint_duration:.2f}ms" if endpoint_duration > 0 else None,
                ),
                "连接测试完成" if overall_status else "连接测试失败",
                200,
            )

        except Exception as e:
            # 写入错误日志
            ApiQueryService._log(
                level='ERROR',
                category='HealthCheck',
                source='System',
                content=f"API [{api.name}] 连接测试异常: {str(e)}",
                api_id=api.id
            )

            # 更新API状态为offline
            if api.status != 'offline':
                api.status = 'offline'
                api.updated_at = now_cst()
                db.session.commit()

            return success_response(
                ApiHealthCheckData(
                    id=api.id,
                    status="offline",
                    error=str(e),
                    health_score=api.health_score,
                    api_url_status=str(False),
                    endpoints_status=str(False),
                ),
                "连接测试失败",
                200,
            )

    # 保持向下兼容
    @staticmethod
    def health_check(api_id):
        return ApiQueryService.test_connection(api_id)

    # 停止测试 API
    @staticmethod
    def stop_test(api_id):
        api = API.query.filter_by(id=api_id, deleted=False).first()
        if not api:
            return error_response("未找到API配置", 404)

        try:
            return success_response(ApiHealthCheckData(id=api.id, status=api.status), "测试已停止")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))
