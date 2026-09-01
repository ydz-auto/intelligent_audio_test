"""Audio 配置读操作 Mixin：查询类方法。

把方法调用转发到 gRPC AudioConfigService。
与 audio_config_command_mixin、audio_config_proxy 组合为完整的 _AudioConfigProxy。
所有方法返回 dict: {success, message, data, code}
"""
import json

from shared.clients.grpc_clients import get_audio_config_service_stub

from ._common import _grpc_call


class _AudioConfigQueryMixin:
    """Audio 配置查询相关方法"""

    def _resp(self, resp):
        """统一解析 AudioConfigResponse 为 dict"""
        return {
            'success': resp.success,
            'message': resp.message,
            'data': json.loads(resp.data) if resp.data else None,
        }

    # ---------- 读操作 ----------

    def get_all_tags(self):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetAllAudioTags(audio_pb.GetAllAudioTagsRequest())
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取标签失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取标签失败',
        )

    def get_all(self, params):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.ListAudios(audio_pb.ListAudiosRequest(
                data=json.dumps(params or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询音频列表失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='查询音频列表失败',
        )

    def get_one(self, audio_id):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetAudio(audio_pb.GetAudioRequest(
                audio_id=int(audio_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询音频详情失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='查询音频详情失败',
        )

    def get_by_ids(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetAudiosByIds(audio_pb.GetAudiosByIdsRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'按ID查询音频失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='按ID查询音频失败',
        )

    def get_by_md5(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetAudioByMD5(audio_pb.GetAudioByMD5Request(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'按MD5查询音频失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='按MD5查询音频失败',
        )

    def get_all_ids(self, params):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetAllAudioIds(audio_pb.GetAllAudioIdsRequest(
                data=json.dumps(params or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取音频ID列表失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取音频ID列表失败',
        )

    def stream_audio(self, audio_id, data=None):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.StreamAudio(audio_pb.StreamAudioRequest(
                audio_id=int(audio_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'流式播放音频失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='流式播放音频失败',
        )

    def stream_audio_by_path(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.StreamAudioByPath(audio_pb.StreamAudioByPathRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'按路径流式播放失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='按路径流式播放失败',
        )

    def get_audio_algorithms(self, audio_id):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetAudioAlgorithms(audio_pb.GetAudioAlgorithmsRequest(
                audio_id=int(audio_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取音频算法失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取音频算法失败',
        )

    def get_folder_tree(self, data):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_config_service_stub()
            resp = stub.GetAudioFolderTree(audio_pb.GetAudioFolderTreeRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取音频目录树失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='获取音频目录树失败',
        )
