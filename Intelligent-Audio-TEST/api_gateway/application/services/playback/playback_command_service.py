import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.acl import PlaybackConfigAclRepositoryImpl
from api_gateway.schemas.common import IdData, StatusData
from api_gateway.schemas.playback import (
    PlaybackCreateSchema,
    PlaybackUpdateSchema,
    PlaybackTestSchema,
    PlaybackAssociateSplSchema,
)

logger = logging.getLogger(__name__)

_playback_acl = PlaybackConfigAclRepositoryImpl()


class PlaybackCommandService:
    """播放设备写操作 Service（CRUD + 测试播放控制）。

    按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 device_service。
    保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
    保留 Pydantic schema 校验。
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

    # 添加新的播放设备
    @staticmethod
    def create():
        json_data = request.get_json(silent=True)
        if json_data is None:
            return error_response("请求正文必须是有效的 JSON 格式且不能为空", 400)

        try:
            validated_data = PlaybackCreateSchema.model_validate(json_data)
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data_dict = validated_data.model_dump(by_alias=False, exclude_none=True)

        result = _playback_acl.create(data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到播放设备'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        new_id = (result.get('data') or {}).get('id')
        return success_response(IdData(id=new_id), result.get('message', '播放设备添加成功'), http_code=201)

    # 更新播放设备信息
    @staticmethod
    def update(device_id):
        json_data = request.get_json(silent=True)
        if json_data is None:
            return error_response("请求正文必须是有效的 JSON 格式且不能为空", 400)

        try:
            validated_data = PlaybackUpdateSchema.model_validate(json_data)
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        validated_dict = validated_data.model_dump(by_alias=False, exclude_none=True)

        result = _playback_acl.update(device_id, validated_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到播放设备'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        return success_response(None, result.get('message', '播放设备信息更新成功'))

    # 删除播放设备
    @staticmethod
    def delete(device_id):
        result = _playback_acl.delete(device_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到播放设备'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        return success_response(None, result.get('message', '播放设备已删除 (逻辑删除)'))

    # 关联 SPL 映射
    @staticmethod
    def associate_spl(device_id):
        json_data = request.get_json(silent=True)
        if json_data is None:
            return error_response("请求正文必须是有效的 JSON 格式且不能为空", 400)

        try:
            validated_data = PlaybackAssociateSplSchema.model_validate(json_data)
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        spl_mapping_id = validated_data.spl_mapping_id

        result = _playback_acl.associate_spl(device_id, spl_mapping_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到播放设备'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        return success_response(None, result.get('message', 'SPL 映射关联成功'))

    # 测试播放设备
    @staticmethod
    def test(device_id):
        json_data = request.get_json(silent=True) or {}
        try:
            validated_data = PlaybackTestSchema.model_validate(json_data)
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        test_params = validated_data.model_dump(by_alias=False, exclude_none=True)

        result = _playback_acl.test(device_id, test_params)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到播放设备'), 404)
            if code == 403:
                return error_response(result.get('message', '操作失败'), code=ErrorCode.FORBIDDEN)
            return error_response(result.get('message', '测试播放失败'), code=code)

        return success_response(result.get('data'), result.get('message', '测试播放已启动'))

    # 停止测试
    @staticmethod
    def stop_test(device_id):
        result = _playback_acl.stop_test(device_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到播放设备'), 404)
            return error_response(result.get('message', '停止测试失败'), code=code)

        return success_response(result.get('data'), result.get('message', '测试音播放已停止'))
