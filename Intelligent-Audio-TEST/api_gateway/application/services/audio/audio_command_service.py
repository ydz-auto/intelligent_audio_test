import logging
from pydantic import ValidationError
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.audio import (
    BatchActionRequest,
    BatchUpdateAnnotationsRequest,
    UpdateMetadataRequest,
)

logger = logging.getLogger(__name__)


class AudioCommandService:
    # 元数据管理
    @staticmethod
    def update_metadata(audio_id):
        from api_gateway.infrastructure.grpc_proxies import audio_config_service

        data = request.get_json() or {}
        try:
            validated = UpdateMetadataRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        result = audio_config_service.update_metadata(audio_id, data)
        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '元数据更新成功'))
        return error_response(result.get('message', '更新失败'), code=result.get('code', 400))

    # 批量更新标注
    @staticmethod
    def batch_update_annotations():
        from api_gateway.infrastructure.grpc_proxies import audio_config_service

        data = request.get_json()
        if not data:
            return error_response("请求体不能为空")

        try:
            validated = BatchUpdateAnnotationsRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        if not validated.items:
            return error_response("标注列表不能为空")

        result = audio_config_service.batch_update_annotations(data)
        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '批量更新标注成功'))
        return error_response(result.get('message', '批量更新失败'), code=result.get('code', 400))

    # 批量操作
    @staticmethod
    def batch_action():
        from api_gateway.infrastructure.grpc_proxies import audio_config_service

        data = request.get_json()
        if not data:
            return error_response("请求体不能为空")

        try:
            validated = BatchActionRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        result = audio_config_service.batch_action(data)
        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '批量操作成功'))
        return error_response(result.get('message', '批量操作失败'), code=result.get('code', 400))

    # 删除音频文件（逻辑删除）
    @staticmethod
    def delete(audio_id):
        from api_gateway.infrastructure.grpc_proxies import audio_config_service

        result = audio_config_service.delete(audio_id)
        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '音频文件已删除'))
        return error_response(result.get('message', '删除失败'), code=result.get('code', 400))

    # 更新音频关联的算法
    @staticmethod
    def update_audio_algorithms(audio_id):
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        from api_gateway.schemas.audio import UpdateAudioAlgorithmsRequest

        data = request.get_json() or {}
        try:
            validated = UpdateAudioAlgorithmsRequest.model_validate(data)
        except Exception as e:
            return error_response(f"参数验证失败: {e}")

        result = audio_config_service.update_audio_algorithms(audio_id, data)
        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '算法关联更新成功'))
        return error_response(result.get('message', '更新失败'), code=result.get('code', 400))

    # 批量更新音频算法关联
    @staticmethod
    def batch_update_audio_algorithms():
        from api_gateway.infrastructure.grpc_proxies import audio_config_service
        from api_gateway.schemas.audio import BatchUpdateAudioAlgorithmsRequest

        data = request.get_json() or {}
        try:
            validated = BatchUpdateAudioAlgorithmsRequest.model_validate(data)
        except Exception as e:
            return error_response(f"参数验证失败: {e}")

        result = audio_config_service.batch_update_audio_algorithms(data)
        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '批量更新算法关联成功'))
        return error_response(result.get('message', '批量更新失败'), code=result.get('code', 400))
