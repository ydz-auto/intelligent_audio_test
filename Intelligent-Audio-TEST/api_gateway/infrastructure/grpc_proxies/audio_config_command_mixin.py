"""Audio 配置写操作 Mixin：元数据更新、删除、批量操作、上传、转换/预览。

把方法调用转发到 gRPC AudioConfigService。
与 audio_config_query_mixin、audio_config_proxy 组合为完整的 _AudioConfigProxy。
所有方法返回 dict: {success, message, data, code}
"""
import json

from shared.clients.grpc_clients import get_audio_config_service_stub

from ._common import _grpc_call


class _AudioConfigCommandMixin:
    """Audio 配置写/上传/转换/预览相关方法"""

    def _resp(self, resp):
        """统一解析 AudioConfigResponse 为 dict"""
        return {
            'success': resp.success,
            'message': resp.message,
            'data': json.loads(resp.data) if resp.data else None,
        }

    # ---------- 写操作 ----------

    def update_metadata(self, audio_id, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.UpdateAudioMetadata(audio_pb.UpdateAudioMetadataRequest(
                audio_id=int(audio_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新音频元数据失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='更新音频元数据失败',
        )

    def batch_update_annotations(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.BatchUpdateAnnotations(audio_pb.BatchUpdateAnnotationsRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'批量更新标注失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='批量更新标注失败',
        )

    def batch_action(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.BatchActionAudios(audio_pb.BatchActionAudiosRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'批量操作失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='批量操作失败',
        )

    def delete(self, audio_id):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.DeleteAudio(audio_pb.DeleteAudioRequest(
                audio_id=int(audio_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除音频失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='删除音频失败',
        )

    def update_audio_algorithms(self, audio_id, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.UpdateAudioAlgorithms(audio_pb.UpdateAudioAlgorithmsRequest(
                audio_id=int(audio_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新算法关联失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='更新算法关联失败',
        )

    def batch_update_audio_algorithms(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.BatchUpdateAudioAlgorithms(audio_pb.BatchUpdateAudioAlgorithmsRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'批量更新算法关联失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='批量更新算法关联失败',
        )

    # ---------- 上传操作 ----------

    def presign_upload(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.PresignUpload(audio_pb.PresignUploadRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'预签名上传失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='预签名上传失败',
        )

    def presign_part(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.PresignPart(audio_pb.PresignPartRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'预签名分片失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='预签名分片失败',
        )

    def complete_direct_upload(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.CompleteDirectUpload(audio_pb.CompleteDirectUploadRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'完成直传失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='完成直传失败',
        )

    def init_upload_task(self, data=None):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.InitUploadTask(audio_pb.InitUploadTaskRequest())
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'初始化上传任务失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='初始化上传任务失败',
        )

    def register_upload_file(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.RegisterUploadFile(audio_pb.RegisterUploadFileRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'注册上传文件失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='注册上传文件失败',
        )

    def upload_chunk(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.UploadChunk(audio_pb.UploadChunkRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'上传分片失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='上传分片失败',
        )

    def merge_chunks(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.MergeChunks(audio_pb.MergeChunksRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'合并分片失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='合并分片失败',
        )

    def get_upload_progress(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetUploadProgress(audio_pb.GetUploadProgressRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取上传进度失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取上传进度失败',
        )

    def url_import(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.UrlImport(audio_pb.UrlImportRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'URL导入失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='URL导入失败',
        )

    # ---------- 转换/预览操作 ----------

    def convert_audio(self, audio_id, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.ConvertAudio(audio_pb.ConvertAudioRequest(
                audio_id=int(audio_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'转换音频失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='转换音频失败',
        )

    def preview_audio(self, audio_id, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.PreviewAudio(audio_pb.PreviewAudioRequest(
                audio_id=int(audio_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'预览音频失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='预览音频失败',
        )

    def stop_preview_audio(self, audio_id):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.StopPreviewAudio(audio_pb.StopPreviewAudioRequest(
                audio_id=int(audio_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'停止预览失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='停止预览失败',
        )
