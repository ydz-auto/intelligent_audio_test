# -*- coding: utf-8 -*-
"""API 配置命令 Service（写侧 / CRUD）。

将 api_controller 中的写操作函数迁移为 ApiCommandService 的静态方法。
保留原有逻辑，不改业务。
"""
from urllib.parse import urlparse

from api_gateway.infrastructure.request_adapter import request
from shared.models.models import API
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.query_utils import now_cst
from api_gateway.schemas.api import ApiCreateInput, ApiUpdateInput
from api_gateway.schemas.common import IdData


class ApiCommandService:
    # ========== 校验辅助 ==========

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
        return ApiCommandService._validate_endpoint_data(data)

    # ========== 写操作 ==========

    @staticmethod
    def create():
        try:
            data = ApiCreateInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        if not data.name or not data.meta:
            return error_response(f"缺少必要字段: name, meta")

        error = ApiCommandService._validate_api_data({
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
                    error = ApiCommandService._validate_endpoint_obj(ep)
                    if error:
                        return error_response(error)

            default_max_process = data.default_max_process if data.default_max_process is not None else 5
            default_max_timeout = data.default_max_timeout if data.default_max_timeout is not None else 30
            default_max_audio_duration = data.default_max_audio_duration if data.default_max_audio_duration is not None else 60

            api_endpoints = ApiCommandService._build_endpoints_list(
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

        error = ApiCommandService._validate_api_data(data_dict)
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
                    error = ApiCommandService._validate_endpoint_obj(ep)
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
