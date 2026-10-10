# -*- coding: utf-8 -*-
"""INT-80 专项：设备分组（device_groups）命令/查询服务。

覆盖：
- 创建：成功（含初始成员）、重名拒绝、空名拒绝、group_type 归一
- 更新：改名重名拒绝、未知分组 404
- 删除：含成员未 cascade 拒绝、cascade 通过、未知分组 404
- 成员增删：幂等添加（跳过已存在/不存在设备）、移除计数
- 列表：分页 + device_count 统计
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from device_service.application.commands.device_group_command_service import DeviceGroupCommandService
from device_service.application.queries.device_group_query_service import DeviceGroupQueryService
from device_service.domain.entities import DeviceGroupEntity


class FakeDeviceGroupRepository:
    """内存设备分组仓储"""

    def __init__(self):
        self.groups = {}
        self.members = {}  # group_id -> set(device_id)
        self.existing_device_ids = {1, 2, 3}
        self._seq = 0

    def _add(self, group_id, name, description='', group_type='test'):
        self.groups[group_id] = DeviceGroupEntity(
            id=group_id, name=name, description=description, group_type=group_type)
        self.members[group_id] = set()

    def create_group(self, data, member_device_ids=None):
        self._seq += 1
        group_id = data.get('id') or f'g{self._seq}'
        self._add(group_id, data['name'], data.get('description', ''),
                  data.get('group_type', 'test'))
        for did in (member_device_ids or []):
            self.members[group_id].add(int(did))
        return self.groups[group_id]

    def update_group(self, group_id, update_fields):
        group = self.groups.get(group_id)
        if not group:
            return None
        for key, value in update_fields.items():
            setattr(group, key, value)
        return group

    def get_group(self, group_id):
        return self.groups.get(group_id)

    def get_group_by_name(self, name):
        for group in self.groups.values():
            if group.name == name:
                return group
        return None

    def delete_group(self, group_id, cascade=False):
        if group_id not in self.groups:
            return False
        if self.members.get(group_id) and not cascade:
            return False
        del self.groups[group_id]
        self.members.pop(group_id, None)
        return True

    def list_groups(self, page=1, per_page=100, keyword=None, group_type=None):
        items = [g for g in self.groups.values()
                 if (not keyword or keyword in g.name)
                 and (not group_type or g.group_type == group_type)]
        counts = self.count_group_devices([g.id for g in items])
        return {
            'items': [{**g.to_dict(), 'device_count': counts.get(g.id, 0)} for g in items],
            'total': len(items), 'page': page, 'per_page': per_page, 'pages': 1,
        }

    def add_devices(self, group_id, device_ids):
        if group_id not in self.groups:
            return 0
        added = 0
        for did in device_ids:
            did = int(did)
            if did not in self.existing_device_ids:
                continue
            if did in self.members[group_id]:
                continue
            self.members[group_id].add(did)
            added += 1
        return added

    def remove_devices(self, group_id, device_ids):
        if group_id not in self.members:
            return 0
        removed = 0
        for did in device_ids:
            did = int(did)
            if did in self.members[group_id]:
                self.members[group_id].discard(did)
                removed += 1
        return removed

    def count_group_devices(self, group_ids):
        return {gid: len(self.members.get(gid, set())) for gid in group_ids}

    def get_group_device_ids(self, group_id):
        return sorted(self.members.get(group_id, set()))


@pytest.fixture
def repo():
    return FakeDeviceGroupRepository()


@pytest.fixture
def command(repo):
    return DeviceGroupCommandService(repo=repo)


@pytest.fixture
def query(repo):
    return DeviceGroupQueryService(repo=repo)


class TestCreateGroup:
    def test_create_success_with_members(self, command, repo):
        result = command.create({'name': '产线A', 'device_ids': [1, 2]})
        assert result['success'] is True
        assert result['code'] == 201
        group_id = result['data']['id']
        assert repo.members[group_id] == {1, 2}

    def test_create_duplicate_name_rejected(self, command):
        command.create({'name': '产线A'})
        result = command.create({'name': '产线A'})
        assert result['success'] is False
        assert '已存在' in result['message']

    def test_create_empty_name_rejected(self, command):
        result = command.create({'name': '  '})
        assert result['success'] is False

    def test_create_invalid_group_type_normalized(self, command):
        result = command.create({'name': 'g', 'group_type': 'unknown-type'})
        assert result['success'] is True
        assert result['data']['group_type'] == 'test'


class TestUpdateDeleteGroup:
    def test_update_rename(self, command):
        group_id = command.create({'name': '旧名'})['data']['id']
        result = command.update(group_id, {'name': '新名', 'description': 'd'})
        assert result['success'] is True

    def test_update_rename_conflict(self, command):
        command.create({'name': 'A'})
        group_b = command.create({'name': 'B'})['data']['id']
        result = command.update(group_b, {'name': 'A'})
        assert result['success'] is False

    def test_update_missing_group_404(self, command):
        assert command.update('nope', {'name': 'x'})['code'] == 404

    def test_delete_with_members_requires_cascade(self, command, repo):
        group_id = command.create({'name': 'g', 'device_ids': [1]})['data']['id']
        result = command.delete(group_id, cascade=False)
        assert result['success'] is False
        assert group_id in repo.groups
        result = command.delete(group_id, cascade=True)
        assert result['success'] is True
        assert group_id not in repo.groups
        assert group_id not in repo.members

    def test_delete_empty_group_no_cascade_needed(self, command):
        group_id = command.create({'name': 'g'})['data']['id']
        assert command.delete(group_id)['success'] is True


class TestMembership:
    def test_add_devices_skips_existing_and_missing(self, command, repo):
        group_id = command.create({'name': 'g', 'device_ids': [1]})['data']['id']
        result = command.add_devices(group_id, [1, 2, 999])
        assert result['success'] is True
        assert result['data']['added'] == 1
        assert repo.members[group_id] == {1, 2}

    def test_add_devices_missing_group_404(self, command):
        assert command.add_devices('nope', [1])['code'] == 404

    def test_remove_devices(self, command, repo):
        group_id = command.create({'name': 'g', 'device_ids': [1, 2]})['data']['id']
        result = command.remove_devices(group_id, [1, 3])
        assert result['success'] is True
        assert result['data']['removed'] == 1
        assert repo.members[group_id] == {2}


class TestQueries:
    def test_get_all_with_counts(self, command, query):
        command.create({'name': 'g1', 'device_ids': [1, 2]})
        command.create({'name': 'g2'})
        result = query.get_all()
        assert result['success'] is True
        counts = {item['name']: item['device_count'] for item in result['data']['items']}
        assert counts == {'g1': 2, 'g2': 0}

    def test_get_one_missing_404(self, query):
        assert query.get_one('nope')['code'] == 404
