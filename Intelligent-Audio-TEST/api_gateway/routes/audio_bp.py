from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.controllers.audio_controller import AudioController
from api_gateway.routes._response import to_response

router = APIRouter()


@router.api_route('', methods=['GET', 'POST'])
def get_all():
    return to_response(AudioController.get_all())


@router.api_route('/ids', methods=['GET', 'POST'])
def get_all_ids():
    return to_response(AudioController.get_all_ids())


@router.post('/by-ids')
def get_by_ids():
    return to_response(AudioController.get_by_ids())


@router.post('/by-md5')
def get_by_md5():
    return to_response(AudioController.get_by_md5())


@router.get('/tags')
def get_all_tags():
    return to_response(AudioController.get_all_tags())


@router.get('/{audio_id}')
def get_one(audio_id: str):
    return to_response(AudioController.get_one(audio_id))


@router.post('/url-import')
def url_import():
    return to_response(AudioController.url_import())


@router.post('/record')
def record():
    return to_response(AudioController.record())


@router.post('/{audio_id}/convert')
def convert(audio_id: str):
    return to_response(AudioController.convert(audio_id))


@router.put('/{audio_id}/metadata')
def update_metadata(audio_id: str):
    return to_response(AudioController.update_metadata(audio_id))


@router.post('/batch/annotations')
def batch_update_annotations():
    return to_response(AudioController.batch_update_annotations())


@router.post('/batch-action')
def batch_action():
    return to_response(AudioController.batch_action())


@router.get('/{audio_id}/stream')
def stream(audio_id: str):
    return to_response(AudioController.stream(audio_id))


@router.post('/{audio_id}/preview')
def preview(audio_id: str):
    return to_response(AudioController.preview(audio_id))


@router.post('/{audio_id}/stop-preview')
def stop_preview(audio_id: str):
    return to_response(AudioController.stop_preview(audio_id))


@router.get('/stream-by-path')
def stream_by_path():
    return to_response(AudioController.stream_by_path())


@router.delete('/{audio_id}')
def delete(audio_id: str):
    return to_response(AudioController.delete(audio_id))


# 分片上传相关接口
@router.post('/upload/init')
def init_upload():
    return to_response(AudioController.init_upload_task())


@router.post('/upload/register')
def register_upload():
    return to_response(AudioController.register_upload_file())


@router.post('/upload/chunk')
def upload_chunk():
    return to_response(AudioController.upload_chunk())


@router.post('/upload/merge')
def merge_chunks():
    return to_response(AudioController.merge_chunks())


@router.get('/upload/progress')
def get_upload_progress():
    return to_response(AudioController.get_upload_progress())


# 前端直传 OSS 相关接口（生产环境多实例部署）
@router.post('/upload/presign')
def presign_upload():
    return to_response(AudioController.presign_upload())


@router.post('/upload/presign-part')
def presign_part():
    return to_response(AudioController.presign_part())


@router.post('/upload/complete-direct')
def complete_direct_upload():
    return to_response(AudioController.complete_direct_upload())


# 音频算法关联接口
@router.get('/{audio_id}/algorithms')
def get_audio_algorithms(audio_id: int):
    return to_response(AudioController.get_audio_algorithms(audio_id))


@router.put('/{audio_id}/algorithms')
def update_audio_algorithms(audio_id: int):
    return to_response(AudioController.update_audio_algorithms(audio_id))


@router.put('/batch/algorithms')
def batch_update_audio_algorithms():
    return to_response(AudioController.batch_update_audio_algorithms())


@router.post('/folder-tree')
def get_folder_tree():
    return to_response(AudioController.get_folder_tree())
