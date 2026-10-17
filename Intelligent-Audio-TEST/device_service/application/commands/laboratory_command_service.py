# -*- coding: utf-8 -*-
"""实验室 Command 应用服务（写侧，INT-655 实验室管理）。

实现实验室 create/update/delete：
- create：code/name 必填，code 唯一（仓库重名校验，仅未删除行参与），
  status 枚举归一
- update：部分更新（仅校验 code 唯一性冲突与 status 枚举）
- delete：软删除（不级联解绑下属资源）

code 唯一性（INT-655 审计 P2）：软删记录不参与唯一性（部分唯一索引），
同 code 可在软删后复用；DB 层 IntegrityError（并发撞车/旧库未迁移）统一
映射为显式 409，不泄漏原始 SQL 报错。
"""
import logging

from sqlalchemy.exc import IntegrityError

from shared.models.common_enums import LaboratoryStatus
from device_service.domain.repositories import LaboratoryRepositoryInterface

logger = logging.getLogger(__name__)

_VALID_STATUS = {s.value for s in LaboratoryStatus}


class LaboratoryCommandService:
    """实验室 Command 应用服务"""

    def __init__(self, repo: LaboratoryRepositoryInterface = None):
        if repo is None:
            from device_service.infrastructure.persistence.laboratory_repository import laboratory_repository
            repo = laboratory_repository
        self.repo = repo

    def create(self, data: dict) -> dict:
        """创建实验室"""
        try:
            code = (data.get('code') or '').strip()
            name = (data.get('name') or '').strip()
            if not code:
                return {'success': False, 'message': '实验室代码 code 不能为空', 'data': None, 'code': 400}
            if not name:
                return {'success': False, 'message': '实验室名称 name 不能为空', 'data': None, 'code': 400}

            status = data.get('status') or 'active'
            if status not in _VALID_STATUS:
                return {
                    'success': False,
                    'message': f"状态 status 非法: {status!r}，合法值: {sorted(_VALID_STATUS)}",
                    'data': None, 'code': 400,
                }

            if self.repo.get_laboratory_by_code(code):
                return {'success': False, 'message': f'实验室代码 {code} 已存在', 'data': None, 'code': 409}

            lab = self.repo.create_laboratory({
                'code': code,
                'name': name,
                'building': data.get('building'),
                'floor': data.get('floor'),
                'room_number': data.get('room_number'),
                'description': data.get('description'),
                'status': status,
            })
            return {'success': True, 'message': '实验室创建成功', 'data': lab.to_dict(), 'code': 201}
        except IntegrityError as e:
            # DB 层唯一冲突（TOCTOU 并发 / 旧库未迁移仍带全表唯一约束）：映射为
            # 显式 409，不向客户端泄漏原始 SQL 报错（INT-655 审计 P2）
            logger.error("create laboratory integrity error: %s", e, exc_info=True)
            return {'success': False, 'message': f'实验室代码 {code} 已被占用', 'data': None, 'code': 409}
        except Exception as e:
            logger.error("create laboratory failed: %s", e, exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def update(self, lab_id: int, data: dict) -> dict:
        """更新实验室（部分更新）"""
        try:
            if not self.repo.get_laboratory(lab_id):
                return {'success': False, 'message': '未找到实验室', 'data': None, 'code': 404}

            update_fields = {}
            for key in ('name', 'building', 'floor', 'room_number', 'description'):
                if key in data:
                    update_fields[key] = data[key]
            if 'code' in data and data['code'] is not None:
                code = (data['code'] or '').strip()
                if not code:
                    return {'success': False, 'message': '实验室代码 code 不能为空', 'data': None, 'code': 400}
                existing = self.repo.get_laboratory_by_code(code)
                if existing and existing.id != lab_id:
                    return {'success': False, 'message': f'实验室代码 {code} 已存在', 'data': None, 'code': 409}
                update_fields['code'] = code
            if 'status' in data and data['status'] is not None:
                status = data['status']
                if status not in _VALID_STATUS:
                    return {
                        'success': False,
                        'message': f"状态 status 非法: {status!r}，合法值: {sorted(_VALID_STATUS)}",
                        'data': None, 'code': 400,
                    }
                update_fields['status'] = status

            if not update_fields:
                return {'success': False, 'message': '无可更新字段', 'data': None, 'code': 400}

            lab = self.repo.update_laboratory(lab_id, update_fields)
            if not lab:
                return {'success': False, 'message': '未找到实验室', 'data': None, 'code': 404}
            return {'success': True, 'message': '实验室更新成功', 'data': lab.to_dict(), 'code': 200}
        except IntegrityError as e:
            # DB 层唯一冲突（并发改 code 撞车 / 旧库未迁移仍带全表唯一约束）：显式 409
            logger.error("update laboratory integrity error: %s", e, exc_info=True)
            return {'success': False, 'message': '实验室代码已被占用', 'data': None, 'code': 409}
        except Exception as e:
            logger.error("update laboratory failed: %s", e, exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def delete(self, lab_id: int) -> dict:
        """删除实验室（软删除，不级联解绑）"""
        try:
            if not self.repo.delete_laboratory(lab_id):
                return {'success': False, 'message': '未找到实验室', 'data': None, 'code': 404}
            return {'success': True, 'message': '实验室已删除', 'data': None, 'code': 200}
        except Exception as e:
            logger.error("delete laboratory failed: %s", e, exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


# 模块级实例
laboratory_command_service = LaboratoryCommandService()
