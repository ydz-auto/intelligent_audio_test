from flask import Blueprint
from api_gateway.controllers.audio_controller import AudioController

audio_bp = Blueprint('audios', __name__)

@audio_bp.route('', methods=['GET', 'POST'])
def get_all():
    return AudioController.get_all()

@audio_bp.route('/ids', methods=['GET', 'POST'])
def get_all_ids():
    return AudioController.get_all_ids()

@audio_bp.route('/by-ids', methods=['POST'])
def get_by_ids():
    return AudioController.get_by_ids()

@audio_bp.route('/by-md5', methods=['POST'])
def get_by_md5():
    return AudioController.get_by_md5()

@audio_bp.route('/<audio_id>', methods=['GET'])
def get_one(audio_id):
    return AudioController.get_one(audio_id)

@audio_bp.route('/tags', methods=['GET'])
def get_all_tags():
    return AudioController.get_all_tags()

@audio_bp.route('/upload', methods=['POST'])
def upload():
    return AudioController.upload()

@audio_bp.route('/url-import', methods=['POST'])
def url_import():
    return AudioController.url_import()

@audio_bp.route('/record', methods=['POST'])
def record():
    return AudioController.record()

@audio_bp.route('/<audio_id>/convert', methods=['POST'])
def convert(audio_id):
    return AudioController.convert(audio_id)

@audio_bp.route('/<audio_id>/metadata', methods=['PUT'])
def update_metadata(audio_id):
    return AudioController.update_metadata(audio_id)

@audio_bp.route('/batch/annotations', methods=['POST'])
def batch_update_annotations():
    return AudioController.batch_update_annotations()

@audio_bp.route('/batch-action', methods=['POST'])
def batch_action():
    return AudioController.batch_action()

@audio_bp.route('/<audio_id>/stream', methods=['GET'])
def stream(audio_id):
    return AudioController.stream(audio_id)

@audio_bp.route('/<audio_id>/preview', methods=['POST'])
def preview(audio_id):
    return AudioController.preview(audio_id)

@audio_bp.route('/<audio_id>/stop-preview', methods=['POST'])
def stop_preview(audio_id):
    return AudioController.stop_preview(audio_id)

@audio_bp.route('/stream-by-path', methods=['GET'])
def stream_by_path():
    return AudioController.stream_by_path()

@audio_bp.route('/folder-import', methods=['POST'])
def folder_import():
    return AudioController.folder_import()

@audio_bp.route('/<audio_id>', methods=['DELETE'])
def delete(audio_id):
    return AudioController.delete(audio_id)

# 分片上传相关接口
@audio_bp.route('/upload/init', methods=['POST'])
def init_upload():
    return AudioController.init_upload_task()

@audio_bp.route('/upload/register', methods=['POST'])
def register_upload():
    return AudioController.register_upload_file()

@audio_bp.route('/upload/chunk', methods=['POST'])
def upload_chunk():
    return AudioController.upload_chunk()

@audio_bp.route('/upload/merge', methods=['POST'])
def merge_chunks():
    return AudioController.merge_chunks()

@audio_bp.route('/upload/progress', methods=['GET'])
def get_upload_progress():
    return AudioController.get_upload_progress()

# 音频算法关联接口
@audio_bp.route('/<int:audio_id>/algorithms', methods=['GET'])
def get_audio_algorithms(audio_id):
    return AudioController.get_audio_algorithms(audio_id)

@audio_bp.route('/<int:audio_id>/algorithms', methods=['PUT'])
def update_audio_algorithms(audio_id):
    return AudioController.update_audio_algorithms(audio_id)

@audio_bp.route('/batch/algorithms', methods=['PUT'])
def batch_update_audio_algorithms():
    return AudioController.batch_update_audio_algorithms()

@audio_bp.route('/folder-tree', methods=['POST'])
def get_folder_tree():
    return AudioController.get_folder_tree()
