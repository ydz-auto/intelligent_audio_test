import logging
from pydantic import ValidationError
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.audio import ConvertFormatRequest
from api_gateway.infrastructure.acl import AudioAclRepositoryImpl

logger = logging.getLogger(__name__)

_audio_acl = AudioAclRepositoryImpl()


class AudioConvertService:
    @staticmethod
    def convert(audio_id):
        """将音频文件转换为带标注和参考参数的测试用例"""
        
        try:
            data = request.get_json() or {}
            try:
                validated = ConvertFormatRequest.model_validate(data)
            except ValidationError as e:
                return error_response(f"参数验证失败: {e}")

            result = _audio_acl.convert_audio(audio_id, data)
            if result.get('success'):
                return success_response(result.get('data'), result.get('message', '转换成功'))
            return error_response(result.get('message', '转换失败'), code=result.get('code', 400))
        except Exception as e:
            logger.error(f"音频转换失败: {e}", exc_info=True)
            return error_response(str(e))
