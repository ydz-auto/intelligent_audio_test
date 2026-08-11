# -*- coding: utf-8 -*-
"""audio_service gRPC servicer 实现（interfaces 层）。

将 gRPC RPC 方法委托给 application / infrastructure 层：
- AudioServiceServicer        -> audio_engine
- PlaybackServiceServicer     -> playback_orchestrator
- AudioConfigServiceServicer  -> application/handlers (CQRS)

约定：
- 复杂参数通过 JSON string 传递，方法内 _loads 解析
- 返回结果通过 JSON string 封装到 data 字段
- 所有方法用 try/except 包裹，异常返回 success=False

说明：proto 已拆分为 audio_service_pb2。
"""

from shared.proto import audio_service_pb2 as e2e_pb
from shared.proto import audio_service_pb2_grpc as e2e_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


# ==================== AudioServiceServicer ====================

class AudioServiceServicer(e2e_grpc.AudioServiceServicer):
    """音频服务 gRPC servicer，委托给 audio_service"""

    def __init__(self):
        self._audio_service = None

    @property
    def audio_service(self):
        if self._audio_service is None:
            from audio_service.infrastructure.audio.audio_engine import audio_service
            self._audio_service = audio_service
        return self._audio_service

    def PlayAudio(self, request, context=None):
        """播放音频"""
        try:
            play_config = _loads(request.play_config, {})
            file_path = request.audio_file_paths
            task_id = request.task_id or play_config.get('task_id', '0')
            device_index = play_config.get('device_index')
            channel_index = play_config.get('channel_index', 0)
            gain = play_config.get('gain', 1.0)
            loop = play_config.get('loop', False)
            player_type = play_config.get('player_type', 'dry')
            offset = play_config.get('offset', 0)

            self.audio_service.play_audio(
                task_id=task_id,
                file_path=file_path,
                device_index=device_index,
                channel_index=channel_index,
                gain=gain,
                loop=loop,
                player_type=player_type,
                offset=offset,
            )
            return e2e_pb.PlayAudioResponse(
                success=True,
                message="ok",
                data=_dumps({"task_id": str(task_id), "file": file_path}),
            )
        except Exception as e:
            return e2e_pb.PlayAudioResponse(success=False, message=str(e), data="")

    def StopAudio(self, request, context=None):
        """停止播放"""
        try:
            task_id = request.task_id
            self.audio_service.stop_task_audio(task_id)
            return e2e_pb.StopAudioResponse(success=True, message="ok", data=_dumps({"task_id": str(task_id)}))
        except Exception as e:
            return e2e_pb.StopAudioResponse(success=False, message=str(e), data="")

    def GetPlayStatus(self, request, context=None):
        """获取播放状态"""
        try:
            task_id = request.task_id
            active_players = getattr(self.audio_service, 'active_players', {})
            players_info = {}
            task_key = task_id
            if task_key not in active_players and task_id is not None:
                task_key = str(task_id)
            if task_key not in active_players and isinstance(task_id, str) and task_id.isdigit():
                int_key = int(task_id)
                if int_key in active_players:
                    task_key = int_key
            task_players = active_players.get(task_key, {})
            for p_type, info in task_players.items():
                players_info[p_type] = {
                    "running": not info.get("future").done() if info.get("future") else False,
                }
            return e2e_pb.GetPlayStatusResponse(
                success=True, message="ok", data=_dumps({"task_id": str(task_id), "players": players_info})
            )
        except Exception as e:
            return e2e_pb.GetPlayStatusResponse(success=False, message=str(e), data="")

    def GetAudioInfo(self, request, context=None):
        """获取音频文件信息"""
        try:
            file_path = request.audio_file_path
            from audio_service.infrastructure.audio.audio_timeline import get_audio_duration
            duration = get_audio_duration(file_path)
            import os
            file_size = os.path.getsize(file_path) if file_path and os.path.exists(file_path) else 0
            return e2e_pb.AudioInfoResponse(
                success=True, message="ok",
                data=_dumps({"file_path": file_path, "duration": duration, "file_size": file_size}),
            )
        except Exception as e:
            return e2e_pb.AudioInfoResponse(success=False, message=str(e), data="")

    def GetPhysicalDevices(self, request, context=None):
        """扫描所有物理输出设备"""
        try:
            devices = self.audio_service.get_all_physical_devices()
            return e2e_pb.GetPhysicalDevicesResponse(
                success=True, message="ok", data=_dumps(devices),
            )
        except Exception as e:
            return e2e_pb.GetPhysicalDevicesResponse(success=False, message=str(e), data="")

    def GetDeviceIndex(self, request, context=None):
        """根据唯一标识获取设备索引"""
        try:
            unique_id = request.unique_id
            device_index = self.audio_service.get_device_index(unique_id)
            return e2e_pb.GetDeviceIndexResponse(
                success=True, message="ok",
                data=_dumps({"device_index": device_index}),
            )
        except Exception as e:
            return e2e_pb.GetDeviceIndexResponse(success=False, message=str(e), data="")

    def StopAudioByPattern(self, request, context=None):
        """按模式停止音频播放"""
        try:
            self.audio_service.stop_task_audio_by_pattern(
                request.task_id_pattern,
                request.player_type_pattern,
            )
            return e2e_pb.StopAudioByPatternResponse(success=True, message="ok", data="")
        except Exception as e:
            return e2e_pb.StopAudioByPatternResponse(success=False, message=str(e), data="")

    def PrepareAudios(self, request, context=None):
        """预下载并按设备目标采样率重采样音频。

        请求 data JSON: {"audio_ids": [int], "playback_device_ids": [int|str]}
        返回 data JSON: {audio_id: {target_rate: local_path, "original": local_path}}
        """
        try:
            data = _loads(request.data, {})
            audio_ids = data.get('audio_ids', [])
            playback_device_ids = data.get('playback_device_ids', [])
            result = self.audio_service.prepare_audios(audio_ids, playback_device_ids)
            return e2e_pb.PrepareAudiosResponse(
                success=True, message="ok", data=_dumps(result),
            )
        except Exception as e:
            return e2e_pb.PrepareAudiosResponse(success=False, message=str(e), data="")

    def MeasureSPL(self, request, context=None):
        """声压级测量"""
        try:
            measure_config = _loads(request.measure_config, {})
            from audio_service.infrastructure.audio.spl_service import spl_service
            mapping_id = measure_config.get('mapping_id')
            target_spl = measure_config.get('target_spl', 70.0)
            gain = 1.0
            if mapping_id is not None:
                gain = spl_service.spl_to_gain(mapping_id, target_spl)
            return e2e_pb.SPLResponse(
                success=True, message="ok",
                data=_dumps({"mapping_id": mapping_id, "target_spl": target_spl, "gain": gain}),
            )
        except Exception as e:
            return e2e_pb.SPLResponse(success=False, message=str(e), data="")

    def StartSPL(self, request, context=None):
        """开始 SPL 测量"""
        try:
            spl_config = _loads(request.spl_config, {})
            return e2e_pb.StartSPLResponse(
                success=True, message="ok",
                data=_dumps({"task_id": request.task_id, "config": spl_config, "started": True}),
            )
        except Exception as e:
            return e2e_pb.StartSPLResponse(success=False, message=str(e), data="")

    def StopSPL(self, request, context=None):
        """停止 SPL 测量"""
        try:
            return e2e_pb.StopSPLResponse(
                success=True, message="ok",
                data=_dumps({"task_id": request.task_id, "stopped": True}),
            )
        except Exception as e:
            return e2e_pb.StopSPLResponse(success=False, message=str(e), data="")


# ==================== PlaybackServiceServicer ====================

class PlaybackServiceServicer(e2e_grpc.PlaybackServiceServicer):
    """播放编排服务 gRPC servicer，委托给 playback_orchestrator"""

    def __init__(self):
        self._orchestrator = None

    @property
    def orchestrator(self):
        if self._orchestrator is None:
            from audio_service.infrastructure.audio.playback_orchestrator import playback_orchestrator
            self._orchestrator = playback_orchestrator
        return self._orchestrator

    def StartPlayback(self, request, context=None):
        """开始播放编排"""
        try:
            playback_config = _loads(request.playback_config, {})
            task_id = request.task_id
            mode = playback_config.get('mode', 'round')

            if mode == 'preview':
                audio_configs = playback_config.get('audio_configs', [])
                case_config = playback_config.get('case_config', {})
                offset = playback_config.get('offset', 0)
                overlap_rate = playback_config.get('overlap_rate', 0)
                overlap_time = playback_config.get('overlap_time', 0)
                result = self.orchestrator.preview(
                    audio_configs, case_config, task_id,
                    offset=offset, overlap_rate=overlap_rate, overlap_time=overlap_time,
                )
            elif mode == 'voiceprint':
                vp_config = playback_config.get('vp_config', {})
                result = self.orchestrator.play_voiceprint(vp_config, task_id)
            else:
                round_config = playback_config.get('round_config', {})
                case_config = playback_config.get('case_config')
                test_case_id = playback_config.get('test_case_id')
                round_number = playback_config.get('round_number')
                audio_local_paths = playback_config.get('audio_local_paths', {})
                result = self.orchestrator.play_round(
                    round_config, task_id,
                    case_config=case_config,
                    test_case_id=test_case_id,
                    round_number=round_number,
                    audio_local_paths=audio_local_paths,
                )
            return e2e_pb.StartPlaybackResponse(
                success=True, message="ok",
                data=_dumps({"result": result, "mode": mode}),
            )
        except Exception as e:
            return e2e_pb.StartPlaybackResponse(success=False, message=str(e), data="")

    def StopPlayback(self, request, context=None):
        """停止播放编排"""
        try:
            from audio_service.infrastructure.audio.audio_engine import audio_service
            task_id = request.task_id
            audio_service.stop_task_audio(task_id)
            return e2e_pb.StopPlaybackResponse(
                success=True, message="ok", data=_dumps({"task_id": str(task_id), "stopped": True})
            )
        except Exception as e:
            return e2e_pb.StopPlaybackResponse(success=False, message=str(e), data="")


# ==================== AudioConfigServiceServicer ====================

class AudioConfigServiceServicer(e2e_grpc.AudioConfigServiceServicer):
    """音频配置 CRUD 服务 gRPC servicer，委托给 CQRS handler。

    遵循 DDD 分层：servicer（interfaces 层）只做协议适配，
    业务逻辑由 application/handlers 层处理。
    """

    def __init__(self):
        self._cmd_handler = None
        self._query_handler = None
        self._upload_handler = None

    @property
    def cmd_handler(self):
        if self._cmd_handler is None:
            from audio_service.application.handlers import audio_command_handler
            self._cmd_handler = audio_command_handler
        return self._cmd_handler

    @property
    def query_handler(self):
        if self._query_handler is None:
            from audio_service.application.handlers import audio_query_handler
            self._query_handler = audio_query_handler
        return self._query_handler

    @property
    def upload_handler(self):
        if self._upload_handler is None:
            from audio_service.application.handlers import audio_upload_handler
            self._upload_handler = audio_upload_handler
        return self._upload_handler

    def _wrap(self, result):
        """将 handler 返回的 dict 包装为 AudioConfigResponse"""
        return e2e_pb.AudioConfigResponse(
            success=result.get('success', False),
            message=result.get('message', ''),
            data=_dumps(result.get('data')),
        )

    # ---------- 写操作 ----------

    def UpdateAudioMetadata(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import UpdateAudioMetadataCommand
            result = self.cmd_handler.handle_update_metadata(
                UpdateAudioMetadataCommand(audio_id=request.audio_id, data=data)
            )
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def BatchUpdateAnnotations(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import BatchUpdateAnnotationsCommand
            result = self.cmd_handler.handle_batch_update_annotations(
                BatchUpdateAnnotationsCommand(data=data)
            )
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def BatchActionAudios(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import BatchActionAudiosCommand
            result = self.cmd_handler.handle_batch_action(
                BatchActionAudiosCommand(data=data)
            )
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def DeleteAudio(self, request, context=None):
        try:
            from audio_service.application.commands import DeleteAudioCommand
            result = self.cmd_handler.handle_delete(
                DeleteAudioCommand(audio_id=request.audio_id)
            )
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def UpdateAudioAlgorithms(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import UpdateAudioAlgorithmsCommand
            result = self.cmd_handler.handle_update_audio_algorithms(
                UpdateAudioAlgorithmsCommand(audio_id=request.audio_id, data=data)
            )
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def BatchUpdateAudioAlgorithms(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import BatchUpdateAudioAlgorithmsCommand
            result = self.cmd_handler.handle_batch_update_audio_algorithms(
                BatchUpdateAudioAlgorithmsCommand(data=data)
            )
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    # ---------- 读操作 ----------

    def GetAllAudioTags(self, request, context=None):
        try:
            from audio_service.application.queries import GetAllAudioTagsQuery
            result = self.query_handler.handle_get_all_tags(GetAllAudioTagsQuery())
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def ListAudios(self, request, context=None):
        try:
            params = _loads(request.data, {})
            from audio_service.application.queries import ListAudiosQuery
            result = self.query_handler.handle_list_audios(ListAudiosQuery(params=params))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def GetAudio(self, request, context=None):
        try:
            from audio_service.application.queries import GetAudioQuery
            result = self.query_handler.handle_get_audio(GetAudioQuery(audio_id=request.audio_id))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def GetAudiosByIds(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.queries import GetAudiosByIdsQuery
            result = self.query_handler.handle_get_by_ids(GetAudiosByIdsQuery(ids=data.get('ids', [])))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def GetAudioByMD5(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.queries import GetAudioByMD5Query
            result = self.query_handler.handle_get_by_md5(
                GetAudioByMD5Query(md5_list=data.get('md5_list', []))
            )
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def GetAllAudioIds(self, request, context=None):
        try:
            params = _loads(request.data, {})
            from audio_service.application.queries import GetAllAudioIdsQuery
            result = self.query_handler.handle_get_all_ids(GetAllAudioIdsQuery(params=params))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def StreamAudio(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.queries import StreamAudioQuery
            result = self.query_handler.handle_stream_audio(
                StreamAudioQuery(audio_id=request.audio_id, data=data)
            )
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def StreamAudioByPath(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.queries import StreamAudioByPathQuery
            result = self.query_handler.handle_stream_audio_by_path(StreamAudioByPathQuery(data=data))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def GetAudioAlgorithms(self, request, context=None):
        try:
            from audio_service.application.queries import GetAudioAlgorithmsQuery
            result = self.query_handler.handle_get_audio_algorithms(
                GetAudioAlgorithmsQuery(audio_id=request.audio_id)
            )
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def GetAudioFolderTree(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.queries import GetAudioFolderTreeQuery
            result = self.query_handler.handle_get_folder_tree(GetAudioFolderTreeQuery(data=data))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    # ---------- 上传操作 ----------

    def PresignUpload(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import PresignUploadCommand
            result = self.upload_handler.handle_presign_upload(PresignUploadCommand(data=data))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def PresignPart(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import PresignPartCommand
            result = self.upload_handler.handle_presign_part(PresignPartCommand(data=data))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def CompleteDirectUpload(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import CompleteDirectUploadCommand
            result = self.upload_handler.handle_complete_direct_upload(CompleteDirectUploadCommand(data=data))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def InitUploadTask(self, request, context=None):
        try:
            from audio_service.application.commands import InitUploadTaskCommand
            result = self.upload_handler.handle_init_upload_task(InitUploadTaskCommand(data={}))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def RegisterUploadFile(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import RegisterUploadFileCommand
            result = self.upload_handler.handle_register_upload_file(RegisterUploadFileCommand(data=data))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def UploadChunk(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import UploadChunkCommand
            result = self.upload_handler.handle_upload_chunk(UploadChunkCommand(data=data))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def MergeChunks(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import MergeChunksCommand
            result = self.upload_handler.handle_merge_chunks(MergeChunksCommand(data=data))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def GetUploadProgress(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import GetUploadProgressCommand
            result = self.upload_handler.handle_get_upload_progress(GetUploadProgressCommand(data=data))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def UrlImport(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import UrlImportCommand
            result = self.upload_handler.handle_url_import(UrlImportCommand(data=data))
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    # ---------- 转换/预览操作 ----------

    def ConvertAudio(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import ConvertAudioCommand
            result = self.cmd_handler.handle_convert_audio(
                ConvertAudioCommand(audio_id=request.audio_id, data=data)
            )
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def PreviewAudio(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from audio_service.application.commands import PreviewAudioCommand
            result = self.cmd_handler.handle_preview_audio(
                PreviewAudioCommand(audio_id=request.audio_id, data=data)
            )
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")

    def StopPreviewAudio(self, request, context=None):
        try:
            from audio_service.application.commands import StopPreviewAudioCommand
            result = self.cmd_handler.handle_stop_preview_audio(
                StopPreviewAudioCommand(audio_id=request.audio_id)
            )
            return self._wrap(result)
        except Exception as e:
            return e2e_pb.AudioConfigResponse(success=False, message=str(e), data="")


__all__ = [
    "AudioServiceServicer",
    "PlaybackServiceServicer",
    "AudioConfigServiceServicer",
]
