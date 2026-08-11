# -*- coding: utf-8 -*-
"""音频 ACL 仓储

通过 gRPC 调用 audio_service 获取音频数据，
为 algorithm_service 的参考参数生成提供音频/标注数据。
迁移自 shared/algorithm/reference_params/audio_utils.py 的 gRPC 调用部分。
"""

from typing import Dict, List, Any, Optional

from algorithm_service.domain.dto import AudioDTO
from shared.utils.dto_utils import dict_to_dto
from shared.utils.log_handler import log_not_emit


class AudioACLRepository:
    """音频 ACL 仓储 - 通过 gRPC 调用 audio_service"""

    @staticmethod
    def fetch_audio_by_id(audio_id: int) -> Optional[AudioDTO]:
        """通过 gRPC 获取单个音频 AudioDTO"""
        try:
            from shared.clients.grpc_clients import get_audio_by_id
            data = get_audio_by_id(audio_id)
            return dict_to_dto(data, AudioDTO) if data else None
        except Exception as e:
            log_not_emit('ERROR', 'audio_acl_repository', f'fetch_audio_by_id failed: {e}', category='algorithm')
            return None

    @staticmethod
    def fetch_audios_by_ids(audio_ids: List[int]) -> Dict[int, AudioDTO]:
        """通过 gRPC 批量获取音频，返回 {audio_id: AudioDTO}"""
        try:
            from shared.clients.grpc_clients import get_audios_by_ids
            raw_map = get_audios_by_ids(audio_ids) or {}
            return {
                aid: dict_to_dto(item, AudioDTO)
                for aid, item in raw_map.items()
            }
        except Exception as e:
            log_not_emit('ERROR', 'audio_acl_repository', f'fetch_audios_by_ids failed: {e}', category='algorithm')
            return {}

    @staticmethod
    def fetch_annotations_by_audio_id(audio_id: int) -> List[Dict[str, Any]]:
        """通过 gRPC 获取音频的标注列表"""
        audio = AudioACLRepository.fetch_audio_by_id(audio_id)
        if audio:
            return audio.annotations or []
        return []

    @staticmethod
    def preload_audio_data(audio_ids: List[int]) -> Dict[str, Any]:
        """批量预加载音频数据（性能优化）

        Returns:
            {
                'audio_map': {audio_id: {...}},
                'annotation_map': {audio_id: [annotations]},
                'duration_map': {audio_id: duration},
            }
        """
        if not audio_ids:
            return {'audio_map': {}, 'annotation_map': {}, 'duration_map': {}}

        audio_map = {}
        annotation_map = {}
        duration_map = {}

        try:
            audio_map_raw = AudioACLRepository.fetch_audios_by_ids(audio_ids)
            for aid, item in audio_map_raw.items():
                audio_map[aid] = item
                duration_map[aid] = item.duration or 0.0
                anns = item.annotations or []
                annotation_map[aid] = anns if anns else []
        except Exception as e:
            log_not_emit('ERROR', 'audio_acl_repository', f'preload_audio_data failed: {e}', category='algorithm')

        log_not_emit('DEBUG', 'audio_acl_repository',
                     f'Preloaded {len(audio_map)} audios, {sum(len(v) for v in annotation_map.values())} annotations',
                     category='algorithm')

        return {
            'audio_map': audio_map,
            'annotation_map': annotation_map,
            'duration_map': duration_map,
        }


audio_acl_repository = AudioACLRepository()
