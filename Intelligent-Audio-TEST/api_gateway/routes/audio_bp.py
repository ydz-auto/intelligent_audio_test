from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.audio.audio_query_service import AudioQueryService
from api_gateway.application.services.audio.audio_upload_service import AudioUploadService
from api_gateway.application.services.audio.audio_command_service import AudioCommandService
from api_gateway.application.services.audio.audio_preview_service import AudioPreviewService
from api_gateway.application.services.audio.audio_convert_service import AudioConvertService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()


@router.api_route('', methods=['GET', 'POST'])
def get_all(_: None = require_permission('audio:read')):
    return to_response(AudioQueryService.get_all())


@router.api_route('/ids', methods=['GET', 'POST'])
def get_all_ids(_: None = require_permission('audio:read')):
    return to_response(AudioQueryService.get_all_ids())


@router.post('/by-ids')
def get_by_ids(_: None = require_permission('audio:read')):
    return to_response(AudioQueryService.get_by_ids())


@router.post('/by-md5')
def get_by_md5(_: None = require_permission('audio:read')):
    return to_response(AudioQueryService.get_by_md5())


@router.get('/tags')
def get_all_tags(_: None = require_permission('audio:read')):
    return to_response(AudioQueryService.get_all_tags())


@router.get('/{audio_id}')
def get_one(audio_id: str, _: None = require_permission('audio:read')):
    return to_response(AudioQueryService.get_one(audio_id))


@router.post('/url-import')
def url_import(_: None = require_permission('audio:upload')):
    return to_response(AudioUploadService.url_import())


@router.post('/record')
def record(_: None = require_permission('audio:upload')):
    # 此端点未实现（原 Controller 中即无 record 方法）
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="record 端点未实现")


@router.post('/{audio_id}/convert')
def convert(audio_id: str, _: None = require_permission('audio:convert')):
    return to_response(AudioConvertService.convert(audio_id))


@router.put('/{audio_id}/metadata')
def update_metadata(audio_id: str, _: None = require_permission('audio:update')):
    return to_response(AudioCommandService.update_metadata(audio_id))


@router.post('/batch/annotations')
def batch_update_annotations(_: None = require_permission('audio:update')):
    return to_response(AudioCommandService.batch_update_annotations())


@router.post('/batch-action')
def batch_action(_: None = require_permission('audio:update')):
    return to_response(AudioCommandService.batch_action())


@router.get('/{audio_id}/stream')
def stream(audio_id: str, _: None = require_permission('audio:read')):
    return to_response(AudioQueryService.stream(audio_id))


@router.post('/{audio_id}/preview')
def preview(audio_id: str, _: None = require_permission('audio:read')):
    return to_response(AudioPreviewService.preview(audio_id))


@router.post('/{audio_id}/stop-preview')
def stop_preview(audio_id: str, _: None = require_permission('audio:read')):
    return to_response(AudioPreviewService.stop_preview(audio_id))


@router.get('/stream-by-path')
def stream_by_path(_: None = require_permission('audio:read')):
    return to_response(AudioQueryService.stream_by_path())


@router.delete('/{audio_id}')
def delete(audio_id: str, _: None = require_permission('audio:delete')):
    return to_response(AudioCommandService.delete(audio_id))


# 分片上传相关接口
@router.post('/upload/init')
def init_upload(_: None = require_permission('audio:upload')):
    return to_response(AudioUploadService.init_upload_task())


@router.post('/upload/register')
def register_upload(_: None = require_permission('audio:upload')):
    return to_response(AudioUploadService.register_upload_file())


@router.post('/upload/chunk')
def upload_chunk(_: None = require_permission('audio:upload')):
    return to_response(AudioUploadService.upload_chunk())


@router.post('/upload/merge')
def merge_chunks(_: None = require_permission('audio:upload')):
    return to_response(AudioUploadService.merge_chunks())


@router.get('/upload/progress')
def get_upload_progress(_: None = require_permission('audio:read')):
    return to_response(AudioUploadService.get_upload_progress())


# 前端直传 OSS 相关接口（生产环境多实例部署）
@router.post('/upload/presign')
def presign_upload(_: None = require_permission('audio:upload')):
    return to_response(AudioUploadService.presign_upload())


@router.post('/upload/presign-part')
def presign_part(_: None = require_permission('audio:upload')):
    return to_response(AudioUploadService.presign_part())


@router.post('/upload/complete-direct')
def complete_direct_upload(_: None = require_permission('audio:upload')):
    return to_response(AudioUploadService.complete_direct_upload())


# 音频算法关联接口
@router.get('/{audio_id}/algorithms')
def get_audio_algorithms(audio_id: int, _: None = require_permission('audio:read')):
    return to_response(AudioQueryService.get_audio_algorithms(audio_id))


@router.put('/{audio_id}/algorithms')
def update_audio_algorithms(audio_id: int, _: None = require_permission('audio:update')):
    return to_response(AudioCommandService.update_audio_algorithms(audio_id))


@router.put('/batch/algorithms')
def batch_update_audio_algorithms(_: None = require_permission('audio:update')):
    return to_response(AudioCommandService.batch_update_audio_algorithms())


@router.post('/folder-tree')
def get_folder_tree(_: None = require_permission('audio:folder')):
    return to_response(AudioQueryService.get_folder_tree())
