import logging
from pydantic import ValidationError
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.audio import (
    BatchActionRequest,
    BatchUpdateAnnotationsRequest,
    UpdateMetadataRequest,
)
from api_gateway.infrastructure.acl import AudioAclRepositoryImpl

logger = logging.getLogger(__name__)

_audio_acl = AudioAclRepositoryImpl()


def _write_http_code(result):
    """写路径下游错误码 → HTTP 状态映射（INT-564）：403/404 原样透出。

    下游 audio_service 命令侧已做 owner 校验（私有非 owner 403），网关须把
    code=403 映射为 HTTP 403，避免统一落 400。
    """
    code = result.get('code', 400)
    return code if code in (403, 404) else 400


class AudioCommandService:
    # 元数据管理
    @staticmethod
    def update_metadata(audio_id):
        
        data = request.get_json() or {}
        try:
            validated = UpdateMetadataRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        # INT-466：admin 修改私有音频落 PRIVATE_RESOURCE_ACCESS 审计（旁路预取，仅 admin 取数）
        from api_gateway.application.services.visibility.visibility_audit import (
            maybe_audit_private_write,
            preload_private_state,
        )
        pre_data = preload_private_state(
            lambda: _audio_acl.get_one(audio_id).get('data') or {})

        result = _audio_acl.update_metadata(audio_id, data)
        if result.get('success'):
            maybe_audit_private_write('audio', audio_id, 'update', pre_data)
            return success_response(result.get('data'), result.get('message', '元数据更新成功'))
        return error_response(result.get('message', '更新失败'),
                              code=result.get('code', 400),
                              http_code=_write_http_code(result))

    # 批量更新标注
    @staticmethod
    def batch_update_annotations():
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空")

        try:
            validated = BatchUpdateAnnotationsRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        if not validated.items:
            return error_response("标注列表不能为空")

        result = _audio_acl.batch_update_annotations(data)
        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '批量更新标注成功'))
        return error_response(result.get('message', '批量更新失败'), code=result.get('code', 400))

    # 批量操作
    @staticmethod
    def batch_action():
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空")

        try:
            validated = BatchActionRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        result = _audio_acl.batch_action(data)
        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '批量操作成功'))
        return error_response(result.get('message', '批量操作失败'), code=result.get('code', 400))

    # 删除音频文件（逻辑删除）
    @staticmethod
    def delete(audio_id):
        # INT-466：admin 删除私有音频落 PRIVATE_RESOURCE_ACCESS 审计（旁路预取，仅 admin 取数）
        from api_gateway.application.services.visibility.visibility_audit import (
            maybe_audit_private_write,
            preload_private_state,
        )
        pre_data = preload_private_state(
            lambda: _audio_acl.get_one(audio_id).get('data') or {})

        result = _audio_acl.delete(audio_id)
        if result.get('success'):
            maybe_audit_private_write('audio', audio_id, 'delete', pre_data)
            return success_response(result.get('data'), result.get('message', '音频文件已删除'))
        return error_response(result.get('message', '删除失败'),
                              code=result.get('code', 400),
                              http_code=_write_http_code(result))

    # 更新音频关联的算法
    @staticmethod
    def update_audio_algorithms(audio_id):
        from api_gateway.schemas.audio import UpdateAudioAlgorithmsRequest

        data = request.get_json() or {}
        try:
            validated = UpdateAudioAlgorithmsRequest.model_validate(data)
        except Exception as e:
            return error_response(f"参数验证失败: {e}")

        # INT-466：admin 修改私有音频关联落 PRIVATE_RESOURCE_ACCESS 审计（旁路预取，仅 admin 取数）
        from api_gateway.application.services.visibility.visibility_audit import (
            maybe_audit_private_write,
            preload_private_state,
        )
        pre_data = preload_private_state(
            lambda: _audio_acl.get_one(audio_id).get('data') or {})

        result = _audio_acl.update_audio_algorithms(audio_id, data)
        if result.get('success'):
            maybe_audit_private_write('audio', audio_id, 'update', pre_data)
            return success_response(result.get('data'), result.get('message', '算法关联更新成功'))
        return error_response(result.get('message', '更新失败'),
                              code=result.get('code', 400),
                              http_code=_write_http_code(result))

    # 批量更新音频算法关联
    @staticmethod
    def batch_update_audio_algorithms():
        from api_gateway.schemas.audio import BatchUpdateAudioAlgorithmsRequest

        data = request.get_json() or {}
        try:
            validated = BatchUpdateAudioAlgorithmsRequest.model_validate(data)
        except Exception as e:
            return error_response(f"参数验证失败: {e}")

        result = _audio_acl.batch_update_audio_algorithms(data)
        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '批量更新算法关联成功'))
        return error_response(result.get('message', '批量更新失败'), code=result.get('code', 400))
