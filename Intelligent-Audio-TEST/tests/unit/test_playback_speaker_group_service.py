# -*- coding: utf-8 -*-
"""逻辑音箱组（device_service 应用层）：N 个实验室的音箱互相对应。

校验口径：组名唯一；组内条目要求设备属于该实验室、且未被其他逻辑组占用。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace
from unittest.mock import MagicMock

from device_service.application.commands.playback_speaker_command_service import (
    PlaybackSpeakerCommandService,
)
from device_service.application.queries.playback_speaker_query_service import (
    PlaybackSpeakerQueryService,
)


def _group(group_id=1, name='设备正面（0.5m+0°）', items=None):
    return SimpleNamespace(
        id=group_id, name=name,
        items=items or [],
        to_dict=lambda: {'id': group_id, 'name': name,
                         'items': [item.to_dict() for item in (items or [])]},
    )


def _repo(groups=None):
    groups = groups if groups is not None else [_group()]
    repo = MagicMock()
    repo.list_playback_speaker_groups.return_value = groups
    repo.get_playback_speaker_group.side_effect = lambda group_id: next(
        (group for group in groups if group.id == int(group_id)), None)
    repo.create_playback_speaker_group.return_value = _group(2, '新逻辑音箱')
    repo.update_playback_speaker_group.side_effect = lambda group_id, data: _group(
        int(group_id), data.get('name') or groups[0].name)
    repo.delete_playback_speaker_group.return_value = True
    repo.upsert_playback_speaker_group_item.return_value = SimpleNamespace(
        to_dict=lambda: {'group_id': 1, 'lab_id': 39, 'playback_device_id': 21})
    repo.delete_playback_speaker_group_item.return_value = True
    repo.get_playback_device.side_effect = lambda device_id: SimpleNamespace(
        id=device_id, lab_id=38 if device_id == 5 else 39)
    repo.resolve_playback_speaker_device.return_value = 21
    return repo


class TestSpeakerGroupCommand:

    def test_create_group(self):
        service = PlaybackSpeakerCommandService(repo=_repo(groups=[]))
        result = service.create_group({'name': '设备正面'})
        assert result['success'] is True
        assert result['data']['name'] == '新逻辑音箱'

    def test_create_duplicate_name_rejected(self):
        service = PlaybackSpeakerCommandService(repo=_repo())
        result = service.create_group({'name': '设备正面（0.5m+0°）'})
        assert result['code'] == 409

    def test_create_without_name_rejected(self):
        service = PlaybackSpeakerCommandService(repo=_repo(groups=[]))
        assert service.create_group({'name': '  '})['code'] == 400

    def test_set_item_ok(self):
        service = PlaybackSpeakerCommandService(repo=_repo())
        result = service.set_item(1, 39, 21)
        assert result['success'] is True
        assert result['data']['playback_device_id'] == 21

    def test_set_item_device_not_in_lab(self):
        service = PlaybackSpeakerCommandService(repo=_repo())
        # 设备 5 属于实验室 38，却要塞进实验室 39
        result = service.set_item(1, 39, 5)
        assert result['code'] == 400
        assert '不属于' in result['message']

    def test_set_item_device_used_by_other_group(self):
        used = SimpleNamespace(id=1, lab_id=39, playback_device_id=21,
                               to_dict=lambda: {'lab_id': 39, 'playback_device_id': 21})
        other = _group(2, '另一只音箱', [used])
        repo = _repo(groups=[_group(1), other])
        service = PlaybackSpeakerCommandService(repo=repo)
        result = service.set_item(1, 39, 21)
        assert result['code'] == 409
        assert '占用' in result['message']

    def test_delete_missing_group_404(self):
        repo = _repo()
        repo.delete_playback_speaker_group.return_value = False
        service = PlaybackSpeakerCommandService(repo=repo)
        assert service.delete_group(999)['code'] == 404


class TestSpeakerGroupQuery:

    def test_list_groups(self):
        service = PlaybackSpeakerQueryService(repo=_repo())
        result = service.list_groups()
        assert result['success'] is True
        assert result['data'][0]['name'] == '设备正面（0.5m+0°）'

    def test_resolve(self):
        service = PlaybackSpeakerQueryService(repo=_repo())
        assert service.resolve(5, 39)['data']['target_device_id'] == 21
