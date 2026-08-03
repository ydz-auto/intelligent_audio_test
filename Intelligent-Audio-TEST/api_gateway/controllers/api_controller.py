import requests
import time
import websocket
from urllib.parse import urlparse
from api_gateway.controllers.request_adapter import request
from shared.models.models import API
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.log_handler import log_not_emit
from api_gateway.schemas.api import ApiEndpointItem, ApiHealthCheckData, ApiItem, ApiListData, ApiCreateInput, ApiUpdateInput
from api_gateway.schemas.common import IdData
from datetime import datetime, timezone, timedelta
from shared.utils.query_utils import now_cst

class APIController:
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

    @staticmethod
    def _validate_api_data(data):
        """验证 API 配置数据"""
        # 2. 验证 meta 是否为合法的 JSON 对象
        meta = data.get('meta')
        if meta is not None and not isinstance(meta, dict):
            return "元数据 (meta) 必须是一个 JSON 对象"

        # 3. 校验数值字段范围
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
                # 支持 http, https, ws, wss 协议
                if not all([result.scheme, result.netloc]):
                    return "无效的接口地址 (endpoint)，必须包含协议 (http/https/ws/wss)"
                # 检查协议是否在允许列表中
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

    # 创建新的API配置
    @staticmethod
    def _build_endpoints_list(endpoints_data, default_max_process, default_max_timeout, default_max_audio_duration):
        """构建 api_endpoints JSON 数组"""
        api_endpoints = []
        for ep in endpoints_data:
            api_endpoints.append({
                'endpoint': ep.endpoint or '',
                'name': ep.name or '',
                'max_process': ep.max_process if ep.max_process is not None else default_max_process,
                'max_timeout': ep.max_timeout if ep.max_timeout is not None else default_max_timeout,
                'max_audio_duration': ep.max_audio_duration if ep.max_audio_duration is not None else default_max_audio_duration,
                'status': ep.status or 'online',
                'health_score': 100,
                'priority': ep.priority if ep.priority is not None else 0,
                'description': ep.description or ''
            })
        return api_endpoints

    @staticmethod
    def _validate_endpoint_obj(ep):
        """验证单个端点对象（用于Pydantic模型）"""
        data = {
            'endpoint': ep.endpoint,
            'max_process': ep.max_process,
            'max_timeout': ep.max_timeout,
            'max_audio_duration': ep.max_audio_duration,
            'priority': ep.priority
        }
        return APIController._validate_endpoint_data(data)

    @staticmethod
    def create():
        try:
            data = ApiCreateInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        if not data.name or not data.meta:
            return error_response(f"缺少必要字段: name, meta")

        error = APIController._validate_api_data({
            'meta': data.meta,
            'default_max_process': data.default_max_process,
            'default_max_timeout': data.default_max_timeout,
            'default_max_audio_duration': data.default_max_audio_duration
        })
        if error:
            return error_response(error)

        try:
            if data.endpoints:
                for ep in data.endpoints:
                    error = APIController._validate_endpoint_obj(ep)
                    if error:
                        return error_response(error)
            
            default_max_process = data.default_max_process if data.default_max_process is not None else 5
            default_max_timeout = data.default_max_timeout if data.default_max_timeout is not None else 30
            default_max_audio_duration = data.default_max_audio_duration if data.default_max_audio_duration is not None else 60
            
            api_endpoints = APIController._build_endpoints_list(
                data.endpoints or [],
                default_max_process,
                default_max_timeout,
                default_max_audio_duration
            )
            
            new_api = API(
                name=data.name,
                vendor=data.vendor,
                api_url=data.api_url,
                description=data.description,
                meta=data.meta,
                algorithm_type=data.algorithm_type,
                max_process=default_max_process,
                max_timeout=default_max_timeout,
                max_audio_duration=default_max_audio_duration,
                default_max_process=default_max_process,
                default_max_timeout=default_max_timeout,
                default_max_audio_duration=default_max_audio_duration,
                status=data.status or 'online',
                health_score=100,
                api_endpoints=api_endpoints
            )
            db.session.add(new_api)
            db.session.commit()

            from shared.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(IdData(id=new_api.id), "API配置创建成功", http_code=201)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 更新API配置
    @staticmethod
    def update(api_id):
        api = API.query.filter_by(id=api_id, deleted=False).first()
        if not api:
            return error_response("未找到API配置", 404)

        try:
            data = ApiUpdateInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        data_dict = {k: v for k, v in data.model_dump(exclude_none=True).items() if v is not None}
        
        error = APIController._validate_api_data(data_dict)
        if error:
            return error_response(error)

        try:
            if data.name is not None:
                api.name = data.name
            if data.vendor is not None:
                api.vendor = data.vendor
            if data.api_url is not None:
                api.api_url = data.api_url
            if data.description is not None:
                api.description = data.description
            if data.meta is not None:
                api.meta = data.meta
            if data.algorithm_type is not None:
                api.algorithm_type = data.algorithm_type
            if data.default_max_process is not None:
                api.default_max_process = data.default_max_process
            if data.default_max_timeout is not None:
                api.default_max_timeout = data.default_max_timeout
            if data.default_max_audio_duration is not None:
                api.default_max_audio_duration = data.default_max_audio_duration
            if data.status is not None:
                api.status = data.status
            
            if data.endpoints is not None:
                for ep in data.endpoints:
                    error = APIController._validate_endpoint_obj(ep)
                    if error:
                        return error_response(error)
                
                default_max_process = api.default_max_process
                default_max_timeout = api.default_max_timeout
                default_max_audio_duration = api.default_max_audio_duration
                
                new_api_endpoints = []
                for ep in data.endpoints:
                    new_api_endpoints.append({
                        'endpoint': ep.endpoint or '',
                        'name': ep.name or '',
                        'max_process': ep.max_process if ep.max_process is not None else default_max_process,
                        'max_timeout': ep.max_timeout if ep.max_timeout is not None else default_max_timeout,
                        'max_audio_duration': ep.max_audio_duration if ep.max_audio_duration is not None else default_max_audio_duration,
                        'status': ep.status or 'online',
                        'health_score': 100,
                        'priority': ep.priority if ep.priority is not None else 0,
                        'description': ep.description or ''
                    })
                api.api_endpoints = new_api_endpoints
            
            api.updated_at = now_cst()
            db.session.commit()
            return success_response(None, "API配置更新成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 删除API配置（逻辑删除）
    @staticmethod
    def delete(api_id):
        api = API.query.filter_by(id=api_id, deleted=False).first()
        if not api:
            return error_response("未找到API配置", 404)

        try:
            # 影响面检查：检查是否有正在运行的任务引用此 API
            from shared.models.models import Task, TaskAPI
            running_tasks = db.session.query(Task).join(TaskAPI).filter(
                TaskAPI.api_id == api_id,
                Task.status == 'running',
                Task.deleted == False
            ).all()

            if running_tasks:
                task_names = [t.name for t in running_tasks]
                return error_response(f"无法删除：以下正在运行的任务正在使用此 API: {', '.join(task_names)}。请先停止任务。", code=202)

            api.deleted = True
            api.updated_at = now_cst()
            db.session.commit()

            from shared.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(None, "API配置已删除")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

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
            APIController._log(
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
            APIController._log(
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
        return APIController.test_connection(api_id)

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
