# -*- coding: utf-8 -*-
"""E2E 测试命令处理器。

命令处理器是应用层的核心：接收命令，委托给已有的 core/ 模块
（e2e_service / e2e_executor）完成实际 IO，并使用领域服务
E2EOrchestrator 维护领域对象的状态。

依赖方向：application -> domain + core（已有实现）
"""

from typing import Dict, Optional

from e2e_test_service.application.commands.e2e_commands import (
    StartE2ETestCommand,
    StopE2ETestCommand,
    RecordAudioCommand,
)
from e2e_test_service.domain.services import E2EOrchestrator


class StartE2ETestHandler:
    """处理 StartE2ETestCommand

    委托给已有的 e2e_service.start_e2e_case()（core/e2e_service.py），
    同时通过 E2EOrchestrator 维护领域会话状态。
    """

    def __init__(self, e2e_service=None):
        # 懒加载 e2e_service 单例，避免循环导入
        self._e2e_service = e2e_service

    @property
    def e2e_service(self):
        if self._e2e_service is None:
            from e2e_test_service.application.services.e2e_service import e2e_service
            self._e2e_service = e2e_service
        return self._e2e_service

    def handle(self, command: StartE2ETestCommand) -> Dict:
        """执行启动 E2E 测试命令"""
        session = E2EOrchestrator.create_session(
            task_id=command.task_id,
            tc_rel_id=command.tc_rel_id,
        )
        E2EOrchestrator.start(session)

        # 委托给已有的 core 模块执行实际 IO
        result = self.e2e_service.start_e2e_case(
            command.task_id, command.tc_rel_id
        )

        E2EOrchestrator.finish(
            session,
            success=result.get('success', False),
            error_message=result.get('message'),
        )

        return {
            'success': result.get('success', False),
            'task_id': command.task_id,
            'tc_rel_id': command.tc_rel_id,
            'message': result.get('message', ''),
            'session_status': session.status,
        }


class StopE2ETestHandler:
    """处理 StopE2ETestCommand

    委托给已有的 e2e_service.stop_e2e_case()（core/e2e_service.py）。
    """

    def __init__(self, e2e_service=None):
        self._e2e_service = e2e_service

    @property
    def e2e_service(self):
        if self._e2e_service is None:
            from e2e_test_service.application.services.e2e_service import e2e_service
            self._e2e_service = e2e_service
        return self._e2e_service

    def handle(self, command: StopE2ETestCommand) -> Dict:
        """执行停止 E2E 测试命令"""
        result = self.e2e_service.stop_e2e_case(command.task_id)
        return {
            'success': result.get('success', False),
            'task_id': command.task_id,
            'message': result.get('message', ''),
        }


class RecordAudioHandler:
    """处理 RecordAudioCommand

    委托给已有的 audio_service（audio/audio_engine.py）执行音频播放/采集，
    并通过统一存储上传采集结果。
    """

    def __init__(self, audio_service=None, storage_client=None):
        self._audio_service = audio_service
        self._storage_client = storage_client

    @property
    def audio_service(self):
        if self._audio_service is None:
            from e2e_test_service.infrastructure.acl import AudioAclRepositoryImpl
            repo = AudioAclRepositoryImpl()
            class _AudioServiceProxy:
                play_audio = staticmethod(lambda **kw: repo.play_audio(**kw))
            self._audio_service = _AudioServiceProxy()
        return self._audio_service

    @property
    def storage_client(self):
        if self._storage_client is None:
            from shared.infrastructure.storage import storage
            self._storage_client = storage
        return self._storage_client

    def handle(self, command: RecordAudioCommand) -> Dict:
        """执行音频录制命令"""
        try:
            # 构造播放配置，委托给已有 audio_service
            play_config = {
                'task_id': command.task_id,
                'device_index': command.device_index,
                'channel_index': command.channel_index,
                'gain': command.gain,
                'loop': command.loop,
            }
            self.audio_service.play_audio(
                file_path=command.audio_file_path,
                play_config=play_config,
            )

            # 上传采集的音频到存储
            oss_key = f"{command.task_id}/{command.tc_rel_id}/{command.device_id}/audio.wav"
            file_path = self.storage_client.save_file(
                command.audio_file_path,
                'audios',
                oss_key,
            )

            return {
                'success': True,
                'task_id': command.task_id,
                'device_id': command.device_id,
                'audio_key': file_path,
            }
        except Exception as e:
            return {
                'success': False,
                'task_id': command.task_id,
                'device_id': command.device_id,
                'error': str(e),
            }
