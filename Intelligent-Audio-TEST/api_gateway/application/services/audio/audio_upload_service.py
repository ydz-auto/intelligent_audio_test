import logging
from pydantic import ValidationError
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.audio import (
    CompleteDirectUploadRequest,
    InitUploadTaskRequest,
    MergeChunksRequest,
    PresignPartRequest,
    PresignUploadRequest,
    RegisterUploadFileRequest,
    URLImportRequest,
)
from api_gateway.infrastructure.acl import AudioAclRepositoryImpl

logger = logging.getLogger(__name__)

_audio_acl = AudioAclRepositoryImpl()


class AudioUploadService:
    # ========== 前端直传 OSS 接口 ==========

    @staticmethod
    def presign_upload():
        """生成 S3 Multipart Upload 初始化信息和第一批分片预签名 URL"""
        
        try:
            data = request.get_json() or {}
            try:
                validated = PresignUploadRequest.model_validate(data)
            except ValidationError as e:
                return error_response(f"参数验证失败: {e}")

            result = _audio_acl.presign_upload(data)
            if result.get('success'):
                return success_response(result.get('data'), result.get('message', '预签名 URL 生成成功'))
            return error_response(result.get('message', '预签名失败'), code=result.get('code', 400))
        except Exception as e:
            logger.error(f"presign_upload failed: {e}", exc_info=True)
            return error_response(str(e))

    @staticmethod
    def presign_part():
        """请求更多分片的预签名 URL（大文件场景）"""
        
        try:
            data = request.get_json() or {}
            try:
                validated = PresignPartRequest.model_validate(data)
            except ValidationError as e:
                return error_response(f"参数验证失败: {e}")

            # 从 query params 获取 oss_key 和 category
            oss_key = request.args.get('oss_key')
            category = request.args.get('category', 'raw_chunks')
            if not oss_key:
                return error_response("缺少 oss_key 参数")

            data['oss_key'] = oss_key
            data['category'] = category

            result = _audio_acl.presign_part(data)
            if result.get('success'):
                return success_response(result.get('data'), result.get('message', '预签名分片成功'))
            return error_response(result.get('message', '预签名失败'), code=result.get('code', 400))
        except Exception as e:
            logger.error(f"presign_part failed: {e}", exc_info=True)
            return error_response(str(e))

    @staticmethod
    def complete_direct_upload():
        """WAV 文件直传 OSS 完成后，合并分片 + 登记 DB"""
        
        try:
            data = request.get_json() or {}
            try:
                validated = CompleteDirectUploadRequest.model_validate(data)
            except ValidationError as e:
                return error_response(f"参数验证失败: {e}")

            result = _audio_acl.complete_direct_upload(data)
            if result.get('success'):
                return success_response(result.get('data'), result.get('message', '直传完成'))
            return error_response(result.get('message', '直传失败'), code=result.get('code', 400))
        except Exception as e:
            logger.error(f"complete_direct_upload failed: {e}", exc_info=True)
            return error_response(str(e))

    @staticmethod
    def init_upload_task():
        """初始化上传任务"""
        
        try:
            data = request.get_json() or {}
            try:
                validated = InitUploadTaskRequest.model_validate(data)
            except ValidationError as e:
                return error_response(f"参数验证失败: {e}")

            result = _audio_acl.init_upload_task(data)
            if result.get('success'):
                return success_response(result.get('data'), result.get('message', '任务初始化成功'))
            return error_response(result.get('message', '初始化失败'), code=result.get('code', 400))
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def register_upload_file():
        """注册上传文件"""
        
        try:
            data = request.get_json() or {}
            try:
                validated = RegisterUploadFileRequest.model_validate(data)
            except ValidationError as e:
                return error_response(f"参数验证失败: {e}")

            result = _audio_acl.register_upload_file(data)
            if result.get('success'):
                return success_response(result.get('data'), result.get('message', '注册成功'))
            return error_response(result.get('message', '注册失败'), code=result.get('code', 400))
        except Exception as e:
            return error_response(f"音频注册失败: {str(e)}")

    @staticmethod
    def upload_chunk():
        """上传分片"""
        
        try:
            file_id = request.form.get('file_id')
            chunk_index = request.form.get('chunk_index', type=int)
            total_chunks = request.form.get('total_chunks', type=int)
            task_id = request.form.get('task_id')

            if not file_id or chunk_index is None or not total_chunks or not task_id:
                return error_response("缺少分片信息")

            if 'chunk' not in request.files:
                return error_response("缺少分片文件")

            chunk_file = request.files['chunk']

            # 读取分片内容并 base64 编码
            import base64
            chunk_content = chunk_file.read()
            chunk_b64 = base64.b64encode(chunk_content).decode('ascii')

            data = {
                'file_id': file_id,
                'chunk_index': chunk_index,
                'total_chunks': total_chunks,
                'task_id': task_id,
                'chunk_data': chunk_b64,
            }

            result = _audio_acl.upload_chunk(data)
            if result.get('success'):
                return success_response(result.get('data'), result.get('message', '分片上传成功'))
            return error_response(result.get('message', '分片上传失败'), code=result.get('code', 400))
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def merge_chunks():
        """合并分片"""
        
        try:
            data = request.get_json() or {}
            try:
                validated = MergeChunksRequest.model_validate(data)
            except ValidationError as e:
                return error_response(f"参数验证失败: {e}")

            result = _audio_acl.merge_chunks(data)
            if result.get('success'):
                return success_response(result.get('data'), result.get('message', '合并完成'))
            return error_response(result.get('message', '合并分片失败'), code=result.get('code', 400))
        except Exception as e:
            logger.error(f"合并分片失败: {str(e)}", exc_info=True)
            return error_response(f"合并分片失败: {str(e)}")

    @staticmethod
    def get_upload_progress():
        """获取上传任务进度"""
        
        try:
            task_id = request.args.get('task_id')
            if not task_id:
                return error_response("缺少任务ID")

            result = _audio_acl.get_upload_progress({'task_id': task_id})
            if result.get('success'):
                return success_response(result.get('data'))
            return error_response(result.get('message', '查询失败'), code=result.get('code', 400))
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def url_import():
        """URL 远程导入"""
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空")

        try:
            validated = URLImportRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        result = _audio_acl.url_import(data)
        if result.get('success'):
            return success_response(result.get('data'), result.get('message', 'URL 导入成功'), http_code=201)
        return error_response(result.get('message', '导入失败'), code=result.get('code', 400))
