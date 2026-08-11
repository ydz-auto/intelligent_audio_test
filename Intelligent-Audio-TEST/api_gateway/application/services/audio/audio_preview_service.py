import logging
from pydantic import ValidationError
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.audio import BatchPlaybackRequest

logger = logging.getLogger(__name__)


class AudioPreviewService:
    # 试听音频 (前端或后端播放)
    @staticmethod
    def preview(audio_id):
        from api_gateway.infrastructure.grpc_proxies import audio_config_service

        try:
            validated = BatchPlaybackRequest.model_validate(request.get_json() or {})
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        data = validated.model_dump(exclude_none=True)
        result = audio_config_service.preview_audio(audio_id, data)
        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '预览成功'))
        return error_response(result.get('message', '预览失败'), code=result.get('code', 400))

    # 停止音频试听
    @staticmethod
    def stop_preview(audio_id):
        from api_gateway.infrastructure.grpc_proxies import audio_config_service

        result = audio_config_service.stop_preview_audio(audio_id)
        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '已停止'))
        return error_response(result.get('message', '停止失败'), code=result.get('code', 400))
