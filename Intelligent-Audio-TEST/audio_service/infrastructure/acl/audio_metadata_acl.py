# -*- coding: utf-8 -*-
"""音频元数据访问 ACL（服务器 / 执行机双角色）。

audio 拆分后同一份播放代码跑在两种角色上，元数据来源按 ``AUDIO_ROLE`` 切换：

- ``server``：服务器容器，直连本地仓储（同进程，零 RPC 开销）；
- ``agent``：执行机宿主，不持有 DB，全部经服务器数据面 ``AudioConfigService``：
  - get_audio / get_audios_by_ids → GetAudiosByIds（宿主语境，免可见性过滤）
  - find_audio_by_name            → ResolveAudioByName（同语义）
  - record_playback_history       → RecordPlaybackHistory（幂等键 + 失败本地落盘重试）

执行机只额外需要 Redis（服务注册 / 设备锁 / 停止位），不碰 DB 与 COS 凭据。
"""
import logging
import os

logger = logging.getLogger(__name__)

AUDIO_ROLE_SERVER = 'server'
AUDIO_ROLE_AGENT = 'agent'


def is_agent_role() -> bool:
    """当前进程是否以执行机（硬件面）角色运行。"""
    role = (os.environ.get('AUDIO_ROLE') or AUDIO_ROLE_SERVER).strip().lower()
    return role == AUDIO_ROLE_AGENT


class AudioMeta:
    """远端音频元数据的属性对象。

    播放链路历史上直接使用 ``AudioAggregate`` 实体属性（file_path / duration / ...），
    这里保持同名属性，避免 agent 侧为“远端对象”再写一套分支。
    """

    __slots__ = (
        'id', 'filename', 'original_filename', 'file_path', 'duration',
        'sample_rate', 'channels', 'bitrate', 'audio_type', 'format',
        'asr_text', 'md5', 'size', 'deleted',
    )

    def __init__(self, data: dict):
        data = data or {}
        self.id = data.get('id')
        self.filename = data.get('name') or data.get('filename') or ''
        self.original_filename = data.get('original_filename') or self.filename
        self.file_path = data.get('file_path') or ''
        self.duration = data.get('duration') or 0
        self.sample_rate = data.get('sample_rate')
        self.channels = data.get('channels')
        self.bitrate = data.get('bitrate')
        self.audio_type = data.get('audio_type') or data.get('type')
        self.format = data.get('format')
        self.asr_text = data.get('asr_text')
        self.md5 = data.get('md5')
        self.size = data.get('size')
        self.deleted = bool(data.get('deleted', False))

    @property
    def name(self):
        return self.filename

    @property
    def audio_format(self):
        return self.format


class AudioMetadataProvider:
    """按角色在本地仓储与服务器 gRPC 之间切换的元数据访问器。"""

    def __init__(self, repo=None):
        self._repo = repo

    @property
    def repo(self):
        """本地仓储（仅 server 角色使用；agent 角色不触发 DB 初始化）。"""
        if self._repo is None:
            from audio_service.infrastructure.persistence.audio_repository import audio_repository
            self._repo = audio_repository
        return self._repo

    # ---------- 读 ----------

    def get_audio(self, audio_id):
        if not is_agent_role():
            return self.repo.get_audio(audio_id)
        return _remote_get_audio(audio_id)

    def get_audio_with_deleted(self, audio_id):
        if not is_agent_role():
            return self.repo.get_audio_with_deleted(audio_id)
        # 远端批量通道只返回未删除音频：试听对已删除音频的语义同样是“音频不存在”
        return _remote_get_audio(audio_id)

    def get_audios_by_ids(self, audio_ids):
        ids = [int(aid) for aid in (audio_ids or []) if str(aid).isdigit()]
        if not ids:
            return []
        if not is_agent_role():
            return self.repo.get_audios_by_ids(ids)
        result = []
        for audio_id in ids:
            meta = _remote_get_audio(audio_id)
            if meta is not None:
                result.append(meta)
        return result

    def find_audio_by_name(self, name):
        if not name:
            return None
        if not is_agent_role():
            return self.repo.find_audio_by_name(name)
        return _remote_find_by_name(name)

    # ---------- 写 ----------

    def record_playback_history(self, data: dict) -> None:
        if not is_agent_role():
            self.repo.record_playback_history(data)
            self.repo.commit()
            return
        from audio_service.infrastructure.acl.playback_history_queue import (
            submit_playback_history,
        )
        submit_playback_history(data)


def _remote_get_audio(audio_id):
    from shared.clients.grpc_clients import get_audio_config_service_stub
    from shared.proto import audio_service_pb2 as audio_pb
    from shared.utils.grpc_json import dumps, loads

    try:
        resp = get_audio_config_service_stub().GetAudiosByIds(
            audio_pb.GetAudiosByIdsRequest(data=dumps({'ids': [int(audio_id)]})))
    except Exception:
        logger.error("gRPC 获取音频元数据失败 audio_id=%s", audio_id, exc_info=True)
        return None
    if not resp.success or not resp.data:
        return None
    items = loads(resp.data, []) or []
    return AudioMeta(items[0]) if items else None


def _remote_find_by_name(name):
    from shared.clients.grpc_clients import get_audio_config_service_stub
    from shared.proto import audio_service_pb2 as audio_pb
    from shared.utils.grpc_json import dumps, loads

    try:
        resp = get_audio_config_service_stub().ResolveAudioByName(
            audio_pb.ResolveAudioByNameRequest(data=dumps({'names': [name]})))
    except Exception:
        logger.error("gRPC 按名称解析音频失败 name=%s", name, exc_info=True)
        return None
    if not resp.success or not resp.data:
        return None
    items = loads(resp.data, []) or []
    return AudioMeta(items[0]) if items else None


# 模块级单例（各播放链路共用）
audio_metadata = AudioMetadataProvider()
