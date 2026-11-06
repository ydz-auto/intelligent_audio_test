# -*- coding: utf-8 -*-
"""audio_service.AudioConfigService ACL 仓储 — gRPC 实现。"""
from __future__ import annotations

import json as _json
import logging
from typing import Dict, Optional

from report_service.domain.dto import AudioDTO
from report_service.domain.repositories.acl.audio_acl_repository import (
    AudioConfigAclRepository,
)
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            logger.debug("附加 result_data 到 DTO 失败", exc_info=True)
    return dto


class AudioConfigAclRepositoryImpl(AudioConfigAclRepository):
    """audio_service.AudioConfigService 跨域只读查询 gRPC 实现。"""

    def get_audio(self, audio_id) -> Optional[AudioDTO]:
        from shared.clients.grpc_clients import get_audio_config_service_stub
        from shared.proto import e2e_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_audio_config_service_stub()
            resp = stub.GetAudio(e2e_pb.GetAudioRequest(audio_id=int(audio_id)))
            if not resp.success:
                return None
            data = _loads(resp.data, None)
            return _attach(dict_to_dto(data, AudioDTO), data)
        except Exception as e:
            logger.warning("get_audio gRPC failed: %s", e)
            return None

    def get_audios_by_ids(self, audio_ids) -> Dict[int, AudioDTO]:
        if not audio_ids:
            return {}
        from shared.clients.grpc_clients import get_audio_config_service_stub
        from shared.proto import e2e_service_pb2 as e2e_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_audio_config_service_stub()
            resp = stub.GetAudiosByIds(e2e_pb.GetAudiosByIdsRequest(
                data=_json.dumps({'ids': list(audio_ids)}, ensure_ascii=False, default=str),
            ))
            if not resp.success:
                return {}
            data = _loads(resp.data, {})
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get('items', []) or data.get('list', [])
            else:
                items = []
            result_map: Dict[int, AudioDTO] = {}
            for a in items:
                if not isinstance(a, dict):
                    continue
                aid = a.get('id')
                if aid is not None:
                    try:
                        result_map[int(aid)] = _attach(dict_to_dto(a, AudioDTO), a)
                    except Exception:
                        logger.debug("Audio id 转换失败: %r", aid, exc_info=True)
            return result_map
        except Exception as e:
            logger.warning("get_audios_by_ids gRPC failed: %s", e)
            return {}
