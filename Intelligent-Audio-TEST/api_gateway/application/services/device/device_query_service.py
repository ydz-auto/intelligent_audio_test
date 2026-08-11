import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response, wrap_grpc_response
from api_gateway.infrastructure.grpc_proxies import device_config_service
from api_gateway.schemas.device import (
    DeviceListQuery,
    DeviceStatusQuery,
    DeviceHealthCheckRequest,
)

logger = logging.getLogger(__name__)


class DeviceQueryService:
    """设备查询读侧 Service（CQRS Query Side）。

    按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 device_service。
    保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
    保留 Pydantic schema 校验。
    """

    @staticmethod
    def _log(level, content, task_id=None, test_case_id=None, api_id=None, category='execution', module='TestDevice', **kwargs):
        """统一日志记录方法"""
        from shared.utils.log_handler import log_not_emit
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

    # 获取所有注册设备
    @staticmethod
    def get_all():
        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        query_params = DeviceListQuery.model_validate(query_params_dict)

        result = device_config_service.get_all(
            page=query_params.page,
            per_page=query_params.per_page,
            keyword=query_params.keyword,
            status=query_params.status,
            device_type=query_params.device_type,
            algorithm_type=query_params.algorithm_type,
        )

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='查询失败')

        return success_response(result.get('data'))

    # 批量获取设备状态 (用于 HTTP 轮询降级)
    @staticmethod
    def get_statuses():
        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        query_params = DeviceStatusQuery.model_validate(query_params_dict)
        device_ids = query_params.ids

        result = device_config_service.get_statuses(device_ids)

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='查询失败')

        return success_response(result.get('data'))

    # 扫描物理设备
    @staticmethod
    def scan():
        """触发驱动层扫描 Android, iOS, HarmonyOS 设备"""
        result = device_config_service.scan()

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='扫描失败')

        data = result.get('data') or []
        return success_response(data, result.get('message', f'成功扫描到 {len(data)} 个在线设备'))

    # 测试设备
    @staticmethod
    def test(device_id):
        result = device_config_service.test(device_id)

        if not result.get('success'):
            return wrap_grpc_response(
                result,
                default_error_msg='测试失败',
                error_code_mapping={404: ('未找到设备', 404)},
            )

        return success_response(result.get('data'), result.get('message', '唤醒指令已发送，正在测试'))

    # 停止测试
    @staticmethod
    def stop_test(device_id):
        result = device_config_service.stop_test(device_id)

        if not result.get('success'):
            return wrap_grpc_response(
                result,
                default_error_msg='操作失败',
                error_code_mapping={404: ('未找到设备', 404)},
            )

        return success_response(result.get('data'), result.get('message', '测试已停止'))

    @staticmethod
    def get_driver_keywords():
        """获取所有已注册的驱动关键字"""
        result = device_config_service.get_driver_keywords()

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='获取失败')

        return success_response(result.get('data'), result.get('message', '获取驱动关键字成功'))

    # 获取单个设备详情
    @staticmethod
    def get_one(device_id):
        result = device_config_service.get_one(device_id)

        if not result.get('success'):
            return wrap_grpc_response(
                result,
                default_error_msg='查询失败',
                error_code_mapping={404: ('未找到设备', 404)},
            )

        return success_response(result.get('data'))

    # 批量健康检查
    @staticmethod
    def health_check():
        try:
            req = DeviceHealthCheckRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        device_ids = req.device_ids or []

        result = device_config_service.health_check(device_ids)

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='健康检查失败')

        return success_response(result.get('data'), result.get('message', '健康检查完成'))

    # 获取可用设备详情列表 (用于自动填充)
    @staticmethod
    def get_available_serials():
        """获取通过 ADB/HDC 命令扫描到的可用设备详细信息列表"""
        result = device_config_service.get_available_serials()

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='获取失败')

        data = result.get('data') or []
        return success_response(data, result.get('message', f'成功获取 {len(data)} 个设备详细信息'))
