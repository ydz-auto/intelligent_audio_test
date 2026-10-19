# -*- coding: utf-8 -*-
"""设备分组 Command 应用服务（写侧，INT-80）。

按 CQRS 拆分：写操作（create/update/delete/add_devices/remove_devices）。
返回 dict（{success, message, data, code}），由 servicer 层包装为 gRPC 响应。

注意：这是【设备】分组（device_service 域），区别于用例分组 group_bp
（task_service 域的 test_case_groups）。
"""
import logging

from device_service.domain.repositories import DeviceGroupRepositoryInterface
from shared.utils.log_handler import log_not_emit

logger = logging.getLogger(__name__)


class DeviceGroupCommandService:
    """设备分组 Command 应用服务"""

    def __init__(self, repo: DeviceGroupRepositoryInterface = None):
        if repo is None:
            from device_service.infrastructure.persistence.device_group_repository import device_group_repository
            repo = device_group_repository
        self.repo = repo

    @staticmethod
    def _log(level, content, **kwargs):
        kwargs.pop('category', None)  # category 固定 device，忽略调用方重复传参
        log_not_emit(level=level, module='DeviceGroup', content=content,
                     category='device', source='backend', **kwargs)

    @staticmethod
    def _validate_group_type(group_type) -> str:
        from shared.models.common_enums import DeviceGroupType
        allowed = {t.value for t in DeviceGroupType}
        return group_type if group_type in allowed else 'test'

    def create(self, data: dict) -> dict:
        try:
            name = str(data.get('name') or '').strip()
            if not name:
                return {'success': False, 'message': '分组名称不能为空', 'data': None, 'code': 400}
            parent_id = data.get('parent_id') or None
            if parent_id is not None:
                parent = self.repo.get_group(parent_id)
                if not parent:
                    return {'success': False, 'message': '父分组不存在或已删除', 'data': None, 'code': 404}
                if parent_id == data.get('id'):
                    return {'success': False, 'message': '父分组不能是分组自身', 'data': None, 'code': 400}
            if self.repo.get_group_by_name(name, parent_id=parent_id):
                return {'success': False, 'message': f"已存在名为 '{name}' 的设备分组", 'data': None, 'code': 400}
            member_ids = data.get('device_ids') or []
            group = self.repo.create_group({
                'name': name,
                'parent_id': parent_id,
                'description': data.get('description') or '',
                'group_type': self._validate_group_type(data.get('group_type')),
                'created_by_user_id': data.get('created_by_user_id'),
            }, member_device_ids=member_ids)
            # 仓储已过滤不存在/已删除设备，device_count 取实际写入的成员数
            actual_count = len(group.member_device_ids)
            self._log('INFO', f"创建设备分组: {name} (id={group.id}, 设备数={actual_count})",
                      category='device')
            return {
                'success': True,
                'message': '设备分组创建成功',
                'data': {**group.to_dict(), 'device_count': actual_count},
                'code': 201,
            }
        except Exception as e:
            logger.exception("创建设备分组失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def update(self, group_id: str, data: dict) -> dict:
        try:
            group = self.repo.get_group(group_id)
            if not group:
                return {'success': False, 'message': '未找到设备分组', 'data': None, 'code': 404}
            update_fields = {}
            # 先确定目标父级（重名作用域）；未传 parent_id 则保持原父级
            new_parent_id = group.parent_id
            if data.get('parent_id') is not None:
                target_parent = data['parent_id'] or None
                if target_parent is not None:
                    parent = self.repo.get_group(target_parent)
                    if not parent:
                        return {'success': False, 'message': '父分组不存在或已删除', 'data': None, 'code': 404}
                    if target_parent == group_id:
                        return {'success': False, 'message': '父分组不能是分组自身', 'data': None, 'code': 400}
                new_parent_id = target_parent
                update_fields['parent_id'] = target_parent
            # 组名（含未改名的移动）须在目标父级作用域内唯一（决策 3 局部唯一）
            target_name = group.name
            if data.get('name') is not None:
                new_name = str(data['name']).strip()
                if not new_name:
                    return {'success': False, 'message': '分组名称不能为空', 'data': None, 'code': 400}
                target_name = new_name
                update_fields['name'] = new_name
            existing = self.repo.get_group_by_name(target_name, parent_id=new_parent_id)
            if existing and existing.id != group_id:
                return {'success': False, 'message': f"已存在名为 '{target_name}' 的设备分组", 'data': None, 'code': 400}
            if data.get('description') is not None:
                update_fields['description'] = data['description']
            if data.get('group_type') is not None:
                update_fields['group_type'] = self._validate_group_type(data['group_type'])
            if data.get('updated_by_user_id') is not None:
                update_fields['updated_by_user_id'] = data['updated_by_user_id']
            updated = self.repo.update_group(group_id, update_fields)
            self._log('INFO', f"更新设备分组: {group_id} 字段={list(update_fields)}", category='device')
            return {
                'success': True,
                'message': '设备分组更新成功',
                'data': updated.to_dict() if updated else None,
                'code': 200,
            }
        except Exception as e:
            logger.exception("更新设备分组失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def delete(self, group_id: str, cascade: bool = False) -> dict:
        try:
            group = self.repo.get_group(group_id)
            if not group:
                return {'success': False, 'message': '未找到设备分组', 'data': None, 'code': 404}
            deleted = self.repo.delete_group(group_id, cascade=cascade)
            if not deleted:
                return {
                    'success': False,
                    'message': '该分组下存在设备或子分组，无法删除（可使用 cascade=true 将设备移出分组、子分组一并删除后删除）',
                    'data': None,
                    'code': 400,
                }
            self._log('INFO', f"删除设备分组: {group.name} (id={group_id}, cascade={cascade})",
                      category='device')
            return {'success': True, 'message': '设备分组已删除', 'data': None, 'code': 200}
        except Exception as e:
            logger.exception("删除设备分组失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def move(self, group_id: str, parent_id: str, updated_by_user_id=None) -> dict:
        """移动分组到新父级（INT-832）。

        parent_id 为空串/None 表示移到根。环检测查整条后代链：
        目标父分组不能是自身或自身任意后代。
        """
        try:
            group = self.repo.get_group(group_id)
            if not group:
                return {'success': False, 'message': '未找到设备分组', 'data': None, 'code': 404}
            target_parent = parent_id or None
            if target_parent is not None:
                parent = self.repo.get_group(target_parent)
                if not parent:
                    return {'success': False, 'message': '父分组不存在或已删除', 'data': None, 'code': 404}
                if target_parent == group_id:
                    return {'success': False, 'message': '父分组不能是分组自身', 'data': None, 'code': 400}
                descendants = self.repo.get_descendant_group_ids(group_id)
                if target_parent in descendants:
                    return {'success': False, 'message': '父分组不能是分组的后代分组（会形成环）',
                            'data': None, 'code': 400}
            # 移动到新父级后，组名须在新父级作用域内保持唯一（决策 3 局部唯一）
            existing = self.repo.get_group_by_name(group.name, parent_id=target_parent)
            if existing and existing.id != group_id:
                return {'success': False,
                        'message': f"目标父分组下已存在名为 '{group.name}' 的子分组",
                        'data': None, 'code': 400}
            updated = self.repo.move_group(group_id, target_parent, updated_by_user_id=updated_by_user_id)
            self._log('INFO', f"移动设备分组: {group.name} (id={group_id}, parent_id={target_parent})",
                      category='device')
            return {
                'success': True,
                'message': '设备分组移动成功',
                'data': updated.to_dict() if updated else None,
                'code': 200,
            }
        except Exception as e:
            logger.exception("移动设备分组失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def add_devices(self, group_id: str, device_ids: list) -> dict:
        try:
            group = self.repo.get_group(group_id)
            if not group:
                return {'success': False, 'message': '未找到设备分组', 'data': None, 'code': 404}
            if not device_ids:
                return {'success': False, 'message': 'device_ids 不能为空', 'data': None, 'code': 400}
            added = self.repo.add_devices(group_id, device_ids)
            self._log('INFO', f"分组添加设备: {group.name} 请求={len(device_ids)} 新增={added}",
                      category='device')
            return {
                'success': True,
                'message': f'成功添加 {added} 个设备到分组',
                'data': {'group_id': group_id, 'added': added},
                'code': 200,
            }
        except Exception as e:
            logger.exception("分组添加设备失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def remove_devices(self, group_id: str, device_ids: list) -> dict:
        try:
            group = self.repo.get_group(group_id)
            if not group:
                return {'success': False, 'message': '未找到设备分组', 'data': None, 'code': 404}
            if not device_ids:
                return {'success': False, 'message': 'device_ids 不能为空', 'data': None, 'code': 400}
            removed = self.repo.remove_devices(group_id, device_ids)
            self._log('INFO', f"分组移除设备: {group.name} 请求={len(device_ids)} 移除={removed}",
                      category='device')
            return {
                'success': True,
                'message': f'成功从分组移除 {removed} 个设备',
                'data': {'group_id': group_id, 'removed': removed},
                'code': 200,
            }
        except Exception as e:
            logger.exception("分组移除设备失败")
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


device_group_command_service = DeviceGroupCommandService()
