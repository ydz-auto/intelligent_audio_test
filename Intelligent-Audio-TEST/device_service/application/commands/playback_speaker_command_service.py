# -*- coding: utf-8 -*-
"""逻辑音箱组 Command 应用服务（写侧）。

N 个实验室里位置相同的音箱互相对应：一个逻辑音箱组内，每个实验室各挂一台
实体播放设备。用例里配置的是某个实验室的音箱，执行时按「源音箱 → 逻辑组 →
执行实验室的对应设备」换绑。

校验口径：
- 组名必填且唯一；
- 组内条目要求目标设备存在、属于该实验室、且未被其他逻辑组占用。
"""
import logging

from device_service.domain.repositories import PlaybackRepositoryInterface

logger = logging.getLogger(__name__)


class PlaybackSpeakerCommandService:
    """逻辑音箱组（写侧）"""

    def __init__(self, repo: PlaybackRepositoryInterface = None):
        if repo is None:
            from device_service.infrastructure.persistence.device_repository import playback_repository
            repo = playback_repository
        self.repo = repo

    def create_group(self, data: dict) -> dict:
        name = (data.get('name') or '').strip()
        if not name:
            return {'success': False, 'message': '逻辑音箱名称不能为空', 'data': None, 'code': 400}
        if any(group.name == name for group in self.repo.list_playback_speaker_groups(name)):
            return {'success': False, 'message': '逻辑音箱名称已存在', 'data': None, 'code': 409}
        try:
            group = self.repo.create_playback_speaker_group(name, data.get('description'))
            return {'success': True, 'message': '逻辑音箱已创建',
                    'data': group.to_dict(), 'code': 200}
        except Exception as e:
            logger.error("create speaker group 失败: %s", e)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def update_group(self, group_id: int, data: dict) -> dict:
        group = self.repo.get_playback_speaker_group(int(group_id))
        if not group:
            return {'success': False, 'message': '未找到逻辑音箱', 'data': None, 'code': 404}
        name = (data.get('name') or '').strip()
        if name and name != group.name:
            if any(item.name == name for item in self.repo.list_playback_speaker_groups(name)):
                return {'success': False, 'message': '逻辑音箱名称已存在',
                        'data': None, 'code': 409}
            data = {**data, 'name': name}
        try:
            updated = self.repo.update_playback_speaker_group(int(group_id), data)
            return {'success': True, 'message': '逻辑音箱已更新',
                    'data': updated.to_dict() if updated else None, 'code': 200}
        except Exception as e:
            logger.error("update speaker group 失败: %s", e)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def delete_group(self, group_id: int) -> dict:
        try:
            if not self.repo.delete_playback_speaker_group(int(group_id)):
                return {'success': False, 'message': '未找到逻辑音箱', 'data': None, 'code': 404}
            return {'success': True, 'message': '逻辑音箱已删除', 'data': None, 'code': 200}
        except Exception as e:
            logger.error("delete speaker group 失败: %s", e)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def set_item(self, group_id: int, lab_id: int, playback_device_id: int) -> dict:
        """设置逻辑音箱在指定实验室对应的播放设备"""
        if not group_id or not lab_id or not playback_device_id:
            return {'success': False, 'message': '逻辑音箱/实验室/播放设备均不能为空',
                    'data': None, 'code': 400}
        group = self.repo.get_playback_speaker_group(int(group_id))
        if not group:
            return {'success': False, 'message': '未找到逻辑音箱', 'data': None, 'code': 404}

        device = self.repo.get_playback_device(int(playback_device_id))
        if not device:
            return {'success': False, 'message': '未找到播放设备', 'data': None, 'code': 404}
        if device.lab_id != int(lab_id):
            return {'success': False, 'message': '播放设备不属于该实验室',
                    'data': None, 'code': 400}

        for other in self.repo.list_playback_speaker_groups():
            if other.id == int(group_id):
                continue
            if any(item.playback_device_id == int(playback_device_id) for item in other.items):
                return {'success': False,
                        'message': f'播放设备已被逻辑音箱「{other.name}」占用',
                        'data': None, 'code': 409}

        try:
            item = self.repo.upsert_playback_speaker_group_item(
                int(group_id), int(lab_id), int(playback_device_id))
            return {'success': True, 'message': '对应设备已保存',
                    'data': item.to_dict(), 'code': 200}
        except Exception as e:
            logger.error("set speaker group item 失败: %s", e)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def delete_item(self, group_id: int, lab_id: int) -> dict:
        try:
            if not self.repo.delete_playback_speaker_group_item(int(group_id), int(lab_id)):
                return {'success': False, 'message': '未找到对应关系', 'data': None, 'code': 404}
            return {'success': True, 'message': '对应设备已移除', 'data': None, 'code': 200}
        except Exception as e:
            logger.error("delete speaker group item 失败: %s", e)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


playback_speaker_command_service = PlaybackSpeakerCommandService()
