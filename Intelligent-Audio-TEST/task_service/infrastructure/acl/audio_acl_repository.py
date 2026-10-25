# -*- coding: utf-8 -*-
"""audio_service 防腐层仓储 — gRPC ACL 适配层。

封装 task_service 对 audio_service 的跨域 gRPC 调用，
消除 infrastructure/persistence / read_models 层对
shared.clients.grpc_clients 的直接依赖。

相关 stub：
- shared.clients.grpc_clients.get_audio_config_service_stub

proto：shared/proto/audio_service_pb2
"""
import json
import logging
from typing import Dict, Optional

from shared.utils.grpc_json import loads as _loads

_logger = logging.getLogger(__name__)


class AudioAclRepository:
    """audio_service 防腐层仓储（gRPC ACL 适配层）。"""

    def get_audio_by_id(self, audio_id) -> Optional[dict]:
        """按 ID 查询单个音频，返回 dict（含 id/name/duration 等字段）。

        封装 audio_service.AudioConfigService.GetAudio RPC，
        失败时返回 None（仅日志告警）。
        """
        if not audio_id:
            return None
        from shared.clients.grpc_clients import get_audio_config_service_stub
        from shared.proto import audio_service_pb2 as e2e_pb
        try:
            stub = get_audio_config_service_stub()
            resp = stub.GetAudio(e2e_pb.GetAudioRequest(audio_id=audio_id))
            if resp.success and resp.data:
                return _loads(resp.data, {})
        except Exception as e:
            _logger.warning("GetAudio gRPC 异常 (audio_id=%s): %s", audio_id, e)
        return None

    def get_audio_durations(self, audio_ids, session=None) -> Dict[int, float]:
        """按 ID 集合批量取音频时长（秒），返回 {audio_id: duration}。

        INT-1625：候选/用例列表只需 `duration` 一个标量。`GetAudiosByIds` 在
        audio_service 内部逐音频查标签 + 标注（N+1），真实库 337 个音频实测
        22.8s、199 个用例 27.9s，是挑选候选慢聚合的主因之一。改共享库窄字段
        只读投影（口径同 RPC：`audios.deleted = FALSE`；先例见模块
        `_read_projection`）。

        失败返回空 dict（仅日志告警），调用方按「无时长」降级。
        """
        ids = [int(a) for a in (audio_ids or []) if a is not None]
        if not ids:
            return {}
        from shared.models.database import get_db_session
        from task_service.infrastructure.acl._read_projection import fetch_rows
        session = session or get_db_session()
        rows = fetch_rows(
            session,
            'SELECT id, duration FROM audios WHERE id IN :ids AND deleted = FALSE',
            ids,
        )
        return {int(r[0]): r[1] for r in rows if r[1] is not None}

    def list_audios_by_ids(self, audio_ids) -> Dict:
        """按 ID 集合批量查询音频，返回 {id: audio_dict} 映射。

        封装 audio_service.AudioConfigService.GetAudiosByIds RPC，
        失败时返回空 dict（仅日志告警）。
        """
        if not audio_ids:
            return {}
        from shared.clients.grpc_clients import get_audio_config_service_stub
        from shared.proto import audio_service_pb2 as e2e_pb
        try:
            stub = get_audio_config_service_stub()
            resp = stub.GetAudiosByIds(e2e_pb.GetAudiosByIdsRequest(
                data=json.dumps({'ids': list(audio_ids)}),
            ))
            if not resp.success:
                _logger.warning("GetAudiosByIds gRPC 失败: %s", resp.message)
                return {}
            payload = _loads(resp.data, {}) if resp.data else {}
        except Exception as e:
            _logger.warning("GetAudiosByIds gRPC 异常: %s", e)
            return {}

        items = payload.get('items', []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []
        result = {}
        for item in items:
            if isinstance(item, dict) and item.get('id') is not None:
                result[item['id']] = item
        return result

    def list_audios(self, query: dict) -> dict:
        """查询音频列表（分页 + 过滤）。

        封装 audio_service.AudioConfigService.ListAudios RPC。
        失败时返回空 dict。
        """
        from shared.clients.grpc_clients import get_audio_config_service_stub
        from shared.proto import audio_service_pb2 as e2e_pb
        try:
            stub = get_audio_config_service_stub()
            resp = stub.ListAudios(e2e_pb.ListAudiosRequest(
                data=json.dumps(query or {}, ensure_ascii=False, default=str),
            ))
            if not resp.success:
                return {}
            return _loads(resp.data, {}) or {}
        except Exception as e:
            _logger.warning("ListAudios gRPC 异常: %s", e)
            return {}

    def get_audio_config_stub(self):
        """获取 AudioConfigService gRPC stub。

        封装 shared.clients.grpc_clients.get_audio_config_service_stub，
        供需要直接调用 stub 的场景使用。
        """
        from shared.clients.grpc_clients import get_audio_config_service_stub
        return get_audio_config_service_stub()

    def update_audio_visibility(self, audio_id, visibility) -> bool:
        """经 gRPC 同步音频可见性（INT-464 跟随用例同步）。

        封装 audio_service.AudioConfigService.UpdateAudioVisibility RPC
        （内部通道，不对外暴露端点）。返回是否成功；失败仅日志告警，
        不抛出——用例建/改主流程不受音频同步失败影响。
        """
        if not audio_id:
            return False
        from shared.clients.grpc_clients import get_audio_config_service_stub
        from shared.proto import audio_service_pb2 as e2e_pb
        try:
            stub = get_audio_config_service_stub()
            resp = stub.UpdateAudioVisibility(e2e_pb.UpdateAudioVisibilityRequest(
                audio_id=int(audio_id), visibility=str(visibility),
            ))
            if resp.success:
                return True
            _logger.warning("UpdateAudioVisibility gRPC 失败 (audio_id=%s, visibility=%s): %s",
                            audio_id, visibility, resp.message)
        except Exception as e:
            _logger.warning("UpdateAudioVisibility gRPC 异常 (audio_id=%s, visibility=%s): %s",
                            audio_id, visibility, e)
        return False


# 模块级单例
audio_acl_repository = AudioAclRepository()
