# -*- coding: utf-8 -*-
"""逻辑音箱组 Query 应用服务（读侧）。

- list / get：管理端查看「逻辑音箱 → 各实验室对应设备」
- resolve：执行链热路径，按（源音箱, 执行实验室）解析目标音箱
"""
import logging

from device_service.domain.repositories import PlaybackRepositoryInterface

logger = logging.getLogger(__name__)


class PlaybackSpeakerQueryService:
    """逻辑音箱组（读侧）"""

    def __init__(self, repo: PlaybackRepositoryInterface = None):
        if repo is None:
            from device_service.infrastructure.persistence.device_repository import playback_repository
            repo = playback_repository
        self.repo = repo

    def list_groups(self, keyword: str = None) -> dict:
        try:
            groups = self.repo.list_playback_speaker_groups(keyword)
            return {'success': True, 'message': 'Success',
                    'data': [group.to_dict() for group in groups], 'code': 200}
        except Exception as e:
            logger.error("list speaker groups 失败: %s", e)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def get_group(self, group_id: int) -> dict:
        try:
            group = self.repo.get_playback_speaker_group(int(group_id))
            if not group:
                return {'success': False, 'message': '未找到逻辑音箱', 'data': None, 'code': 404}
            return {'success': True, 'message': 'Success',
                    'data': group.to_dict(), 'code': 200}
        except Exception as e:
            logger.error("get speaker group 失败: %s", e)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def resolve(self, source_device_id: int, target_lab_id: int) -> dict:
        """解析目标音箱；未配置对应关系时 target_device_id 为 None（调用方回退）"""
        try:
            target_device_id = self.repo.resolve_playback_speaker_device(
                int(source_device_id), int(target_lab_id))
            return {'success': True, 'message': 'Success',
                    'data': {'target_device_id': target_device_id}, 'code': 200}
        except Exception as e:
            logger.error("resolve speaker device 失败: %s", e)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def resolve_group(self, group_id: int, target_lab_id: int) -> dict:
        """用例直接关联逻辑音箱：组 + 执行实验室 → 该实验室对应设备"""
        try:
            group = self.repo.get_playback_speaker_group(int(group_id))
            if not group:
                return {'success': False, 'message': '未找到逻辑音箱', 'data': None, 'code': 404}
            target_device_id = self.repo.resolve_playback_speaker_group_device(
                int(group_id), int(target_lab_id))
            return {'success': True, 'message': 'Success',
                    'data': {'group_name': group.name,
                             'target_device_id': target_device_id}, 'code': 200}
        except Exception as e:
            logger.error("resolve speaker group device 失败: %s", e)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


playback_speaker_query_service = PlaybackSpeakerQueryService()
