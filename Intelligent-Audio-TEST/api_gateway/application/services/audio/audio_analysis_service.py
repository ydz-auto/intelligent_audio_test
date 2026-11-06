import logging

from pydantic import ValidationError

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response, wrap_grpc_response
from api_gateway.schemas.audio import AudioProcessRequest
from api_gateway.infrastructure.acl import AudioAclRepositoryImpl

logger = logging.getLogger(__name__)

_audio_acl = AudioAclRepositoryImpl()


class AudioAnalysisService:
    """音频特征分析 / 质量评估 / 处理（降噪/增益/剪辑）网关服务（INT-820 §3.3.2）。

    只读端点（features/quality）委托 gRPC AudioConfigService，
    处理端点（process）校验 AudioProcessRequest 后透传。
    """

    @staticmethod
    def analyze_features(audio_id):
        """音频特征分析：频谱 / 能量分布 / 时域特征。"""
        try:
            result = _audio_acl.analyze_audio_features(audio_id)
            if result.get('success'):
                return success_response(result.get('data'))
            return wrap_grpc_response(
                result,
                default_error_msg='特征分析失败',
                error_code_mapping={404: ('音频文件不存在', 404)},
            )
        except Exception as e:
            logger.error(f"音频特征分析失败: {e}", exc_info=True)
            return error_response(str(e))

    @staticmethod
    def assess_quality(audio_id):
        """音频质量评估：信噪比 / 动态范围 / 频率响应 / 质量评分。"""
        try:
            result = _audio_acl.assess_audio_quality(audio_id)
            if result.get('success'):
                return success_response(result.get('data'))
            return wrap_grpc_response(
                result,
                default_error_msg='质量评估失败',
                error_code_mapping={404: ('音频文件不存在', 404)},
            )
        except Exception as e:
            logger.error(f"音频质量评估失败: {e}", exc_info=True)
            return error_response(str(e))

    @staticmethod
    def process(audio_id):
        """音频处理：降噪 / 增益调整 / 剪辑。"""
        try:
            data = request.get_json() or {}
            try:
                validated = AudioProcessRequest.model_validate(data)
            except ValidationError as e:
                return error_response(f"参数验证失败: {e}")

            payload = {
                'operation': validated.operation,
                'mode': validated.mode,
                'gain_db': validated.gain_db,
                'start_ms': validated.start_ms,
                'end_ms': validated.end_ms,
            }
            result = _audio_acl.process_audio(audio_id, payload)
            if result.get('success'):
                return success_response(result.get('data'))
            return wrap_grpc_response(
                result,
                default_error_msg='音频处理失败',
                error_code_mapping={404: ('音频文件不存在', 404)},
            )
        except Exception as e:
            logger.error(f"音频处理失败: {e}", exc_info=True)
            return error_response(str(e))
