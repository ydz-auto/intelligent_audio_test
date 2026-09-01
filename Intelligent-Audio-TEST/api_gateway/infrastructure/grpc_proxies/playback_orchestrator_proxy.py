"""playback_orchestrator 代理：_PlaybackOrchestratorProxy 及模块级单例 playback_orchestrator。"""
import json

from shared.clients.grpc_clients import get_playback_service_stub

from ._common import _grpc_call


class _PlaybackOrchestratorProxy:
    """playback_orchestrator 代理：把方法调用转发到 gRPC PlaybackService"""

    def preview(self, audio_configs=None, case_config=None, task_id=None,
                offset=0, overlap_rate=0, overlap_time=0, **kwargs):
        """预览播放编排"""
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_playback_service_stub()
            playback_config = {
                'mode': 'preview',
                'audio_configs': audio_configs,
                'case_config': case_config,
                'offset': offset,
                'overlap_rate': overlap_rate,
                'overlap_time': overlap_time,
                'kwargs': kwargs,
            }
            resp = stub.StartPlayback(audio_pb.StartPlaybackRequest(
                task_id=str(task_id or ''),
                playback_config=json.dumps(playback_config)
            ))
            if not resp.success or not resp.data:
                return None
            return json.loads(resp.data)

        return _grpc_call(_call, default_return=None, error_msg_prefix="预览播放编排失败")

    def play_round(self, round_config=None, task_id=None, case_config=None,
                   test_case_id=None, round_number=None, **kwargs):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_playback_service_stub()
            playback_config = {
                'mode': 'round',
                'round_config': round_config,
                'case_config': case_config,
                'test_case_id': test_case_id,
                'round_number': round_number,
                'kwargs': kwargs,
            }
            resp = stub.StartPlayback(audio_pb.StartPlaybackRequest(
                task_id=str(task_id or ''),
                playback_config=json.dumps(playback_config)
            ))
            if not resp.success or not resp.data:
                return None
            return json.loads(resp.data)

        return _grpc_call(_call, default_return=None, error_msg_prefix="轮次播放失败")

    def play_voiceprint(self, voiceprint_config, task_id=None, **kwargs):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_playback_service_stub()
            playback_config = {
                'mode': 'voiceprint',
                'vp_config': voiceprint_config,
                'kwargs': kwargs,
            }
            resp = stub.StartPlayback(audio_pb.StartPlaybackRequest(
                task_id=str(task_id or ''),
                playback_config=json.dumps(playback_config)
            ))
            return resp.success

        return _grpc_call(_call, default_return=False, error_msg_prefix="声纹播放失败")

    def stop_playback(self, task_id=None, **kwargs):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_playback_service_stub()
            stub.StopPlayback(audio_pb.StopPlaybackRequest(task_id=str(task_id or '')))

        _grpc_call(_call, default_return=None, log_error=False)


playback_orchestrator = _PlaybackOrchestratorProxy()
