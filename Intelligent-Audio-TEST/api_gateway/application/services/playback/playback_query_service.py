import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.acl import PlaybackConfigAclRepositoryImpl

logger = logging.getLogger(__name__)

_playback_acl = PlaybackConfigAclRepositoryImpl()


class PlaybackQueryService:
    """播放设备查询读侧 Service。

    按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 device_service。
    保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
    """

    @staticmethod
    def _log(level, content, task_id=None, test_case_id=None, api_id=None, category='execution', module='Playback', **kwargs):
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

    # 获取所有播放设备
    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        keyword = request.args.get('keyword')
        device_type = request.args.get('type')

        result = _playback_acl.get_all(
            page=page,
            per_page=per_page,
            keyword=keyword,
            device_type=device_type,
        )

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'))

        return success_response(result.get('data'))

    # 获取单个播放设备详情
    @staticmethod
    def get_one(device_id):
        result = _playback_acl.get_one(device_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到播放设备'), 404)
            return error_response(result.get('message', '查询失败'))

        return success_response(result.get('data'))

    @staticmethod
    def scan():
        """扫描可用的物理播放通道，并过滤掉已注册的设备"""
        result = _playback_acl.scan()

        if not result.get('success'):
            return error_response(result.get('message', '扫描失败'))

        data = result.get('data') or []
        return success_response(data, result.get('message', f'成功扫描到 {len(data)} 个新通道'))

    # 检查所有播放设备状态
    @staticmethod
    def check_status():
        result = _playback_acl.check_status()

        if not result.get('success'):
            return error_response(result.get('message', '检查状态失败'))

        return success_response(result.get('data'), result.get('message', '设备状态检查完成'))
