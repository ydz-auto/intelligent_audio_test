# -*- coding: utf-8 -*-
"""API 配置 CRUD 应用服务

把原 api_gateway 的 ApiCommandService / ApiQueryService 业务逻辑下沉到微服务。
- 不再依赖 request 对象，改为接收 dict 参数
- 返回 dict（{success, message, data, code}），由 servicer 层包装为 gRPC 响应
- 校验逻辑（_validate_api_data 等）一并下沉
"""
import time
import requests
import websocket
from urllib.parse import urlparse

from shared.utils.query_utils import now_cst
from shared.utils.log_handler import log_not_emit
from api_gateway.application.services.stats_cache import refresh_stats_cache
from api_test_service.infrastructure.persistence.api_test_repository import api_test_repository


class APICrudService:
    """API 配置 CRUD 应用服务（写侧 + 读侧）"""

    # ========== 校验辅助 ==========

    @staticmethod
    def _validate_api_data(data):
        """验证 API 配置数据"""
        meta = data.get('meta')
        if meta is not None and not isinstance(meta, dict):
            return "元数据 (meta) 必须是一个 JSON 对象"

        if 'default_max_process' in data:
            val = data['default_max_process']
            if not isinstance(val, int) or val < 1 or val > 100:
                return "默认最大并发数 (default_max_process) 必须在 1-100 之间"

        if 'default_max_timeout' in data:
            val = data['default_max_timeout']
            if not isinstance(val, int) or val < 1 or val > 3000:
                return "默认最大超时时间 (default_max_timeout) 必须在 1-3000 之间"

        if 'default_max_audio_duration' in data:
            val = data['default_max_audio_duration']
            if not isinstance(val, int) or val < 1 or val > 36000:
                return "默认最大音频时长 (default_max_audio_duration) 必须在 1-36000 之间"

        return None

    @staticmethod
    def _validate_endpoint_data(data):
        """验证 API 链接数据"""
        endpoint = data.get('endpoint')
        if endpoint:
            try:
                result = urlparse(endpoint)
                if not all([result.scheme, result.netloc]):
                    return "无效的接口地址 (endpoint)，必须包含协议 (http/https/ws/wss)"
                allowed_schemes = ['http', 'https', 'ws', 'wss']
                if result.scheme not in allowed_schemes:
                    return f"无效的协议 {result.scheme}，仅支持 http, https, ws, wss"
            except Exception:
                return "无效的接口地址 (endpoint)"

        if 'max_process' in data:
            val = data['max_process']
            if not isinstance(val, int) or val < 1 or val > 100:
                return "最大并发数 (max_process) 必须在 1-100 之间"

        if 'max_timeout' in data:
            val = data['max_timeout']
            if not isinstance(val, int) or val < 1 or val > 300:
                return "最大超时时间 (max_timeout) 必须在 1-300 之间"

        if 'max_audio_duration' in data:
            val = data['max_audio_duration']
            if not isinstance(val, int) or val < 1 or val > 3600:
                return "最大音频时长 (max_audio_duration) 必须在 1-3600 之间"

        if 'priority' in data:
            val = data['priority']
            if not isinstance(val, int) or val < 0:
                return "优先级 (priority) 必须为非负整数"

        return None

    @staticmethod
    def _build_endpoints_list(endpoints_data, default_max_process, default_max_timeout, default_max_audio_duration):
        """构建 api_endpoints JSON 数组

        Args:
            endpoints_data: 端点字典列表，每个元素含 endpoint/name/max_process/...
        """
        api_endpoints = []
        for ep in endpoints_data:
            api_endpoints.append({
                'endpoint': ep.get('endpoint') or '',
                'name': ep.get('name') or '',
                'max_process': ep.get('max_process') if ep.get('max_process') is not None else default_max_process,
                'max_timeout': ep.get('max_timeout') if ep.get('max_timeout') is not None else default_max_timeout,
                'max_audio_duration': ep.get('max_audio_duration') if ep.get('max_audio_duration') is not None else default_max_audio_duration,
                'status': ep.get('status') or 'online',
                'health_score': 100,
                'priority': ep.get('priority') if ep.get('priority') is not None else 0,
                'description': ep.get('description') or ''
            })
        return api_endpoints

    @staticmethod
    def _validate_endpoint_obj(ep):
        """验证单个端点对象（dict）

        Args:
            ep: 端点字典
        """
        data = {
            'endpoint': ep.get('endpoint'),
            'max_process': ep.get('max_process'),
            'max_timeout': ep.get('max_timeout'),
            'max_audio_duration': ep.get('max_audio_duration'),
            'priority': ep.get('priority')
        }
        return APICrudService._validate_endpoint_data(data)

    # ========== 序列化辅助 ==========

    @staticmethod
    def _api_to_dict(api):
        """将 API ORM 对象序列化为 dict（保持与原 ApiItem 一致的结构）"""
        endpoints = []
        for i, ep in enumerate(api.api_endpoints or []):
            endpoints.append({
                'id': f"{api.id}_{i}",
                'endpoint': ep.get('endpoint', ''),
                'name': ep.get('name', ''),
                'max_process': ep.get('max_process', 5),
                'max_timeout': ep.get('max_timeout', 30),
                'max_audio_duration': ep.get('max_audio_duration', 60),
                'status': ep.get('status', 'online'),
                'health_score': ep.get('health_score', 100),
                'priority': ep.get('priority', 0),
                'description': ep.get('description', ''),
            })

        return {
            'id': api.id,
            'name': api.name,
            'vendor': api.vendor,
            'api_url': api.api_url,
            'description': api.description,
            'status': api.status,
            'meta': api.meta if isinstance(api.meta, dict) else {},
            'algorithm_type': api.algorithm_type,
            'default_max_process': api.default_max_process,
            'default_max_timeout': api.default_max_timeout,
            'default_max_audio_duration': api.default_max_audio_duration,
            'health_score': api.health_score,
            'endpoints': endpoints,
            'created_at': api.created_at.isoformat() if api.created_at else None,
            'updated_at': api.updated_at.isoformat() if api.updated_at else None,
        }

    @staticmethod
    def _log(level, content, task_id=None, test_case_id=None, api_id=None,
             category='execution', module='API', **kwargs):
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

    # ========== 写操作 ==========

    @classmethod
    def create(cls, data: dict) -> dict:
        """创建 API 配置

        Args:
            data: API 配置参数字典

        Returns:
            dict: {success, message, data, code}
        """
        if not data.get('name') or not data.get('meta'):
            return {'success': False, 'message': '缺少必要字段: name, meta', 'data': None, 'code': 400}

        error = cls._validate_api_data({
            'meta': data.get('meta'),
            'default_max_process': data.get('default_max_process'),
            'default_max_timeout': data.get('default_max_timeout'),
            'default_max_audio_duration': data.get('default_max_audio_duration')
        })
        if error:
            return {'success': False, 'message': error, 'data': None, 'code': 400}

        endpoints = data.get('endpoints') or []
        for ep in endpoints:
            error = cls._validate_endpoint_obj(ep)
            if error:
                return {'success': False, 'message': error, 'data': None, 'code': 400}

        try:
            default_max_process = data.get('default_max_process') if data.get('default_max_process') is not None else 5
            default_max_timeout = data.get('default_max_timeout') if data.get('default_max_timeout') is not None else 30
            default_max_audio_duration = data.get('default_max_audio_duration') if data.get('default_max_audio_duration') is not None else 60

            api_endpoints = cls._build_endpoints_list(
                endpoints,
                default_max_process,
                default_max_timeout,
                default_max_audio_duration
            )

            create_data = {
                'name': data['name'],
                'vendor': data.get('vendor'),
                'api_url': data.get('api_url'),
                'description': data.get('description'),
                'meta': data.get('meta', {}),
                'algorithm_type': data.get('algorithm_type'),
                'default_max_process': default_max_process,
                'default_max_timeout': default_max_timeout,
                'default_max_audio_duration': default_max_audio_duration,
                'max_process': default_max_process,
                'max_timeout': default_max_timeout,
                'max_audio_duration': default_max_audio_duration,
                'status': data.get('status') or 'online',
                'api_endpoints': api_endpoints,
            }

            new_api = api_test_repository.create_api(create_data)

            try:
                refresh_stats_cache()
            except Exception:
                pass

            return {
                'success': True,
                'message': 'API配置创建成功',
                'data': {'id': new_api.id},
                'code': 201,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    @classmethod
    def update(cls, api_id: int, data: dict) -> dict:
        """更新 API 配置

        Args:
            api_id: API ID
            data: 需要更新的字段字典

        Returns:
            dict: {success, message, data, code}
        """
        api = api_test_repository.get_api(api_id)
        if not api:
            return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}

        # 校验 API 数据
        data_dict = {k: v for k, v in data.items() if v is not None}
        error = cls._validate_api_data(data_dict)
        if error:
            return {'success': False, 'message': error, 'data': None, 'code': 400}

        try:
            update_fields = {}

            if data.get('name') is not None:
                update_fields['name'] = data['name']
            if data.get('vendor') is not None:
                update_fields['vendor'] = data['vendor']
            if data.get('api_url') is not None:
                update_fields['api_url'] = data['api_url']
            if data.get('description') is not None:
                update_fields['description'] = data['description']
            if data.get('meta') is not None:
                update_fields['meta'] = data['meta']
            if data.get('algorithm_type') is not None:
                update_fields['algorithm_type'] = data['algorithm_type']
            if data.get('default_max_process') is not None:
                update_fields['default_max_process'] = data['default_max_process']
            if data.get('default_max_timeout') is not None:
                update_fields['default_max_timeout'] = data['default_max_timeout']
            if data.get('default_max_audio_duration') is not None:
                update_fields['default_max_audio_duration'] = data['default_max_audio_duration']
            if data.get('status') is not None:
                update_fields['status'] = data['status']

            if data.get('endpoints') is not None:
                for ep in data['endpoints']:
                    error = cls._validate_endpoint_obj(ep)
                    if error:
                        return {'success': False, 'message': error, 'data': None, 'code': 400}

                default_max_process = api.default_max_process
                default_max_timeout = api.default_max_timeout
                default_max_audio_duration = api.default_max_audio_duration

                new_api_endpoints = cls._build_endpoints_list(
                    data['endpoints'],
                    default_max_process,
                    default_max_timeout,
                    default_max_audio_duration
                )
                update_fields['api_endpoints'] = new_api_endpoints

            update_fields['updated_at'] = now_cst()

            updated_api = api_test_repository.update_api(api_id, update_fields)
            if not updated_api:
                return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}

            return {
                'success': True,
                'message': 'API配置更新成功',
                'data': None,
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    @classmethod
    def delete(cls, api_id: int) -> dict:
        """软删除 API 配置

        Args:
            api_id: API ID

        Returns:
            dict: {success, message, data, code}
        """
        api = api_test_repository.get_api(api_id)
        if not api:
            return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}

        try:
            # 影响面检查：检查是否有正在运行的任务引用此 API
            running_tasks = api_test_repository.check_api_in_running_tasks(api_id)

            if running_tasks:
                task_names = [t.get('name') if isinstance(t, dict) else t.name for t in running_tasks]
                return {
                    'success': False,
                    'message': f"无法删除：以下正在运行的任务正在使用此 API: {', '.join(task_names)}。请先停止任务。",
                    'data': None,
                    'code': 202,
                }

            success = api_test_repository.delete_api(api_id)
            if not success:
                return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}

            try:
                refresh_stats_cache()
            except Exception:
                pass

            return {
                'success': True,
                'message': 'API配置已删除',
                'data': None,
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    # ========== 读操作 ==========

    @classmethod
    def get_all(cls, page: int = 1, per_page: int = 10, keyword: str = None,
                status: str = None, algorithm_type: str = None) -> dict:
        """分页查询 API 列表

        Args:
            page: 页码
            per_page: 每页条数
            keyword: 搜索关键字
            status: 状态过滤
            algorithm_type: 算法类型过滤

        Returns:
            dict: {success, message, data, code}
        """
        try:
            result = api_test_repository.list_apis(
                page=page, per_page=per_page,
                keyword=keyword, status=status, algorithm_type=algorithm_type,
            )

            data = {
                'items': [cls._api_to_dict(api) for api in result['items']],
                'total': result['total'],
                'page': result['page'],
                'per_page': result['per_page'],
                'pages': result['pages'],
            }

            return {
                'success': True,
                'message': 'Success',
                'data': data,
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    @classmethod
    def get_one(cls, api_id: int) -> dict:
        """查询单个 API 详情

        Args:
            api_id: API ID

        Returns:
            dict: {success, message, data, code}
        """
        api = api_test_repository.get_api(api_id)
        if not api:
            return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}

        return {
            'success': True,
            'message': 'Success',
            'data': cls._api_to_dict(api),
            'code': 200,
        }

    @classmethod
    def test_connection(cls, api_id: int) -> dict:
        """测试 API 连接（含 WebSocket/HTTP 健康检查）

        Args:
            api_id: API ID

        Returns:
            dict: {success, message, data, code}
        """
        api = api_test_repository.get_api(api_id)
        if not api:
            return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}

        start_time = time.time()
        try:
            # 1. 测试 api_url 本身
            api_url_status = False
            api_url_error = None
            if api.api_url:
                test_api_url = api.api_url
                parsed_api_url = urlparse(test_api_url)
                api_scheme = parsed_api_url.scheme.lower()

                try:
                    if api_scheme in ['ws', 'wss']:
                        ws = websocket.WebSocket()
                        ws.settimeout(30)
                        ws.connect(test_api_url)
                        ws.close()
                        api_url_status = True
                    elif api_scheme in ['http', 'https']:
                        if test_api_url and not test_api_url.endswith('/'):
                            test_api_url += '/health'
                        elif test_api_url and test_api_url.endswith('/'):
                            test_api_url += 'health'

                        api_url_response = requests.get(
                            test_api_url,
                            timeout=30,
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

            # 2. 测试 endpoints
            endpoints_status = False
            endpoint_error = None
            endpoint_response = None
            endpoint_duration = 0

            if not api.api_endpoints:
                endpoint_error = "没有配置任何端点"
                endpoints_status = True
            else:
                endpoint = api.api_endpoints[0]
                test_url = endpoint.get('endpoint', '')

                if not test_url:
                    endpoint_error = "第一个端点URL为空"
                    endpoints_status = True
                else:
                    parsed_url = urlparse(test_url)
                    scheme = parsed_url.scheme.lower()

                    try:
                        if scheme in ['ws', 'wss']:
                            ws = websocket.WebSocket()
                            ws.settimeout(endpoint.get('max_timeout', 30))
                            ws.connect(test_url)
                            endpoint_duration = (time.time() - start_time) * 1000
                            ws.close()
                            endpoints_status = True

                        elif scheme in ['http', 'https']:
                            if test_url and not test_url.endswith('/'):
                                test_url += '/health'
                            elif test_url and test_url.endswith('/'):
                                test_url += 'health'

                            endpoint_response = requests.get(
                                test_url,
                                timeout=endpoint.get('max_timeout', 30),
                                headers={"User-Agent": "Task-Manager-Health-Checker/1.0"}
                            )
                            endpoint_duration = (time.time() - start_time) * 1000

                            if 200 <= endpoint_response.status_code < 400:
                                endpoints_status = True
                            else:
                                endpoint_error = f"端点连接失败: {endpoint_response.status_code}"
                        else:
                            endpoint_error = f"不支持的协议: {scheme}"

                    except Exception as e:
                        endpoint_error = f"端点连接异常: {str(e)}"

            # 3. 综合判断 API 状态
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

            cls._log(
                level=log_level,
                category='HealthCheck',
                source='System',
                content=log_content,
                api_id=api.id
            )

            # 5. 更新 API 状态
            new_status = 'online' if overall_status else 'offline'
            if api.status != new_status:
                api_test_repository.update_api(api.id, {
                    'status': new_status,
                    'updated_at': now_cst(),
                })

            # 6. 构建响应
            return {
                'success': True,
                'message': '连接测试完成' if overall_status else '连接测试失败',
                'data': {
                    'id': api.id,
                    'status': new_status,
                    'health_score': api.health_score,
                    'api_url_status': str(api_url_status),
                    'endpoints_status': str(endpoints_status),
                    'error': api_url_error if not overall_status else None,
                    'warning': endpoint_error if overall_status and not endpoints_status else None,
                    'status_code': endpoint_response.status_code if endpoint_response else None,
                    'response_time': f"{endpoint_duration:.2f}ms" if endpoint_duration > 0 else None,
                },
                'code': 200,
            }

        except Exception as e:
            cls._log(
                level='ERROR',
                category='HealthCheck',
                source='System',
                content=f"API [{api.name}] 连接测试异常: {str(e)}",
                api_id=api.id
            )

            if api.status != 'offline':
                api_test_repository.update_api(api.id, {
                    'status': 'offline',
                    'updated_at': now_cst(),
                })

            return {
                'success': True,
                'message': '连接测试失败',
                'data': {
                    'id': api.id,
                    'status': 'offline',
                    'error': str(e),
                    'health_score': api.health_score,
                    'api_url_status': str(False),
                    'endpoints_status': str(False),
                },
                'code': 200,
            }

    @classmethod
    def health_check(cls, api_id: int) -> dict:
        """兼容别名，等同 test_connection"""
        return cls.test_connection(api_id)

    @classmethod
    def stop_test(cls, api_id: int) -> dict:
        """停止测试 API

        Args:
            api_id: API ID

        Returns:
            dict: {success, message, data, code}
        """
        api = api_test_repository.get_api(api_id)
        if not api:
            return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}

        try:
            return {
                'success': True,
                'message': '测试已停止',
                'data': {
                    'id': api.id,
                    'status': api.status,
                    'health_score': api.health_score,
                    'api_url_status': str(False),
                    'endpoints_status': str(False),
                },
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


# 模块级实例
api_crud_service = APICrudService()
