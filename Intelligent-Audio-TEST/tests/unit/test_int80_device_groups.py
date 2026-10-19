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
    """内存设备分组仓储（INT-832：支持 parent_id 嵌套 / move / 子树删除）"""

    def __init__(self):
        self.groups = {}
        self.members = {}  # group_id -> set(device_id)
        self.existing_device_ids = {1, 2, 3}
        self._seq = 0

    def _add(self, group_id, name, parent_id=None, description='', group_type='test',
             member_device_ids=None):
        self.groups[group_id] = DeviceGroupEntity(
            id=group_id, name=name, parent_id=parent_id, description=description,
            group_type=group_type, member_device_ids=list(member_device_ids or []))
        self.members[group_id] = set()

    def create_group(self, data, member_device_ids=None):
        self._seq += 1
        group_id = data.get('id') or f'g{self._seq}'
        # 对齐真实仓储语义：初始成员过滤不存在/已删除设备
        valid_ids = sorted(int(did) for did in (member_device_ids or [])
                           if int(did) in self.existing_device_ids)
        self._add(group_id, data['name'], parent_id=data.get('parent_id'),
                  description=data.get('description', ''),
                  group_type=data.get('group_type', 'test'),
                  member_device_ids=valid_ids)
        for did in valid_ids:
            self.members[group_id].add(did)
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

    def get_group_by_name(self, name, parent_id=None):
        for group in self.groups.values():
            if group.name == name and group.parent_id == parent_id:
                return group
        return None

    def delete_group(self, group_id, cascade=False):
        if group_id not in self.groups:
            return False
        child_count = sum(1 for g in self.groups.values() if g.parent_id == group_id)
        if (self.members.get(group_id) or child_count) and not cascade:
            return False
        subtree = self.get_descendant_group_ids(group_id) + [group_id]
        for gid in subtree:
            self.groups.pop(gid, None)
            self.members.pop(gid, None)
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

    def get_descendant_group_ids(self, group_id):
        descendants = []
        frontier = [group_id]
        seen = {group_id}
        while frontier:
            children = [g.id for g in self.groups.values() if g.parent_id in frontier]
            frontier = []
            for cid in children:
                if cid not in seen:
                    seen.add(cid)
                    descendants.append(cid)
                    frontier.append(cid)
        return descendants

    def move_group(self, group_id, parent_id, updated_by_user_id=None):
        group = self.groups.get(group_id)
        if not group:
            return None
        group.parent_id = parent_id or None
        return group


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

    def test_create_filters_nonexistent_members(self, command, repo):
        """审计修复：初始成员不写悬空行，device_count 取实际成员数"""
        result = command.create({'name': '混入幽灵', 'device_ids': [1, 99999]})
        assert result['success'] is True
        group_id = result['data']['id']
        assert repo.members[group_id] == {1}
        assert result['data']['device_count'] == 1


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


class TestNestedCreate:
    """INT-832：嵌套创建 + 按父级作用域重名校验"""

    def test_create_child_under_parent(self, command):
        root = command.create({'name': '根组'})['data']
        child = command.create({'name': '子组', 'parent_id': root['id']})['data']
        assert child['parent_id'] == root['id']
        assert root['parent_id'] is None

    def test_list_includes_parent_id(self, command, query):
        root = command.create({'name': '根组'})['data']
        command.create({'name': '子组', 'parent_id': root['id']})
        result = query.get_all()
        by_name = {item['name']: item for item in result['data']['items']}
        assert by_name['根组']['parent_id'] is None
        assert by_name['子组']['parent_id'] == root['id']

    def test_same_name_different_parent_allowed(self, command):
        root_a = command.create({'name': 'A'})['data']
        root_b = command.create({'name': 'B'})['data']
        r1 = command.create({'name': '同名', 'parent_id': root_a['id']})
        r2 = command.create({'name': '同名', 'parent_id': root_b['id']})
        assert r1['success'] is True
        assert r2['success'] is True

    def test_duplicate_name_same_parent_rejected(self, command):
        root = command.create({'name': 'A'})['data']
        command.create({'name': '子组', 'parent_id': root['id']})
        result = command.create({'name': '子组', 'parent_id': root['id']})
        assert result['success'] is False
        assert '已存在' in result['message']

    def test_root_duplicate_name_rejected(self, command):
        command.create({'name': '同名'})
        result = command.create({'name': '同名'})
        assert result['success'] is False

    def test_create_parent_missing_404(self, command):
        result = command.create({'name': '子组', 'parent_id': 'no-such-group'})
        assert result['success'] is False
        assert result['code'] == 404

    def test_update_moves_parent_scope(self, command, repo):
        root_a = command.create({'name': 'A'})['data']
        root_b = command.create({'name': 'B'})['data']
        group = command.create({'name': 'X', 'parent_id': root_a['id']})['data']
        # B 下已有同名 'X' → 把 group 移到 B 下被拒（局部唯一）
        command.create({'name': 'X', 'parent_id': root_b['id']})
        result = command.update(group['id'], {'parent_id': root_b['id']})
        assert result['success'] is False
        # 改名后再移到 B 下成功
        result = command.update(group['id'], {'name': 'X2', 'parent_id': root_b['id']})
        assert result['success'] is True
        assert repo.groups[group['id']].parent_id == root_b['id']

    def test_update_parent_missing_404(self, command):
        group = command.create({'name': 'X'})['data']
        result = command.update(group['id'], {'parent_id': 'no-such-group'})
        assert result['success'] is False
        assert result['code'] == 404


class TestMoveGroup:
    """INT-832：移动分组（含环检测、父存在性、新父级重名）"""

    def test_move_to_other_group_success(self, command, repo):
        root = command.create({'name': '根组'})['data']
        child = command.create({'name': '子组'})['data']
        result = command.move(child['id'], root['id'])
        assert result['success'] is True
        assert repo.groups[child['id']].parent_id == root['id']

    def test_move_to_root_success(self, command, repo):
        root = command.create({'name': '根组'})['data']
        child = command.create({'name': '子组', 'parent_id': root['id']})['data']
        result = command.move(child['id'], '')
        assert result['success'] is True
        assert repo.groups[child['id']].parent_id is None

    def test_move_to_self_cycle_400(self, command):
        group = command.create({'name': 'g'})['data']
        result = command.move(group['id'], group['id'])
        assert result['success'] is False
        assert result['code'] == 400

    def test_move_to_descendant_cycle_400(self, command):
        root = command.create({'name': '根组'})['data']
        child = command.create({'name': '子组', 'parent_id': root['id']})['data']
        grand = command.create({'name': '孙组', 'parent_id': child['id']})['data']
        # 把根组移到自己的孙子组下 → 成环
        result = command.move(root['id'], grand['id'])
        assert result['success'] is False
        assert result['code'] == 400

    def test_move_parent_missing_404(self, command):
        group = command.create({'name': 'g'})['data']
        result = command.move(group['id'], 'no-such-group')
        assert result['success'] is False
        assert result['code'] == 404

    def test_move_missing_group_404(self, command):
        assert command.move('nope', '')['code'] == 404

    def test_move_name_conflict_under_new_parent_400(self, command):
        root = command.create({'name': '根组'})['data']
        other = command.create({'name': '同名', 'parent_id': root['id']})['data']
        moving = command.create({'name': '同名'})['data']
        result = command.move(moving['id'], root['id'])
        assert result['success'] is False
        assert result['code'] == 400
        assert other['id'] != moving['id']

    def test_move_keeps_members(self, command, repo):
        root = command.create({'name': '根组'})['data']
        child = command.create({'name': '子组', 'device_ids': [1, 2]})['data']
        command.move(child['id'], root['id'])
        assert repo.members[child['id']] == {1, 2}


class TestDeleteSubtree:
    """INT-832：删除父分组 —— cascade 语义"""

    def test_delete_group_with_children_requires_cascade(self, command, repo):
        root = command.create({'name': '根组'})['data']
        command.create({'name': '子组', 'parent_id': root['id']})
        result = command.delete(root['id'], cascade=False)
        assert result['success'] is False
        assert root['id'] in repo.groups

    def test_delete_cascade_removes_subtree(self, command, repo):
        root = command.create({'name': '根组'})['data']
        child = command.create({'name': '子组', 'parent_id': root['id']})['data']
        grand = command.create({'name': '孙组', 'parent_id': child['id'], 'device_ids': [1]})['data']
        result = command.delete(root['id'], cascade=True)
        assert result['success'] is True
        for gid in (root['id'], child['id'], grand['id']):
            assert gid not in repo.groups
            assert gid not in repo.members
