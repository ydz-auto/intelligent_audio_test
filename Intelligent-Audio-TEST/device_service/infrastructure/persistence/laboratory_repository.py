# -*- coding: utf-8 -*-
"""LaboratoryRepository - 实验室仓储实现（INT-655 实验室管理）。

通过 shared.models.database.get_db_session() 的 scoped_session 访问数据库，
向上层（application/commands/laboratory_command_service、
application/queries/laboratory_query_service）提供领域可读的接口。

P5+DOMAIN：通过 PO ↔ Entity 显式转换，仓储方法返回 domain entities
（LaboratoryAggregate），聚合根不再持有 ORM 引用。

资源计数口径（实验室扩展功能设计.md §4.1/§5.4.1）：
- device_count：devices.lab_id = X 且未删除
- playback_device_count：playback_devices.lab_id = X 且未删除
- test_case_count：task_service test_cases.config JSONB 中 lab_id = X
  （跨域 gRPC 扫描，见 testcase_acl_repository.list_testcases）
"""
from typing import Dict, List, Optional

from shared.models.database import get_db_session
from device_service.infrastructure.persistence.models import (
    Laboratory,
    Device,
    PlaybackDevice,
)
from device_service.domain.entities import LaboratoryAggregate
from device_service.domain.repositories import LaboratoryRepositoryInterface
from device_service.infrastructure.persistence._device_converters import (
    _now,
    _laboratory_po_to_entity,
)


class LaboratoryRepository(LaboratoryRepositoryInterface):
    """实验室仓储实现"""

    def create_laboratory(self, data: dict) -> LaboratoryAggregate:
        """创建实验室，返回 LaboratoryAggregate。"""
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        lab = Laboratory(
            code=data['code'],
            name=data['name'],
            building=data.get('building'),
            floor=data.get('floor'),
            room_number=data.get('room_number'),
            description=data.get('description'),
            status=data.get('status') or 'active',
            created_by_user_id=get_current_user_id(),
        )
        session.add(lab)
        session.commit()
        return _laboratory_po_to_entity(lab)

    def update_laboratory(self, lab_id: int, update_fields: dict) -> Optional[LaboratoryAggregate]:
        """更新实验室字段，返回更新后的 LaboratoryAggregate；不存在返回 None。"""
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        lab = session.query(Laboratory).filter_by(id=lab_id, deleted=False).first()
        if not lab:
            return None
        for key, value in update_fields.items():
            if not hasattr(lab, key):
                continue
            setattr(lab, key, value)
        lab.updated_at = _now()
        lab.updated_by_user_id = get_current_user_id()
        session.commit()
        return _laboratory_po_to_entity(lab)

    def delete_laboratory(self, lab_id: int) -> bool:
        """逻辑删除实验室；不存在返回 False。

        软删语义：仅标记 deleted，不动下属设备/播放设备的 lab_id（解除归属由
        前端引导或后续任务处理，本卡不做级联）。
        """
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        lab = session.query(Laboratory).filter_by(id=lab_id, deleted=False).first()
        if not lab:
            return False
        lab.deleted = True
        lab.deleted_at = _now()
        lab.updated_by_user_id = get_current_user_id()
        lab.updated_at = _now()
        session.commit()
        return True

    def get_laboratory(self, lab_id: int) -> Optional[LaboratoryAggregate]:
        """按 ID 查询未删除实验室。"""
        session = get_db_session()
        po = session.query(Laboratory).filter_by(id=lab_id, deleted=False).first()
        if po is None:
            return None
        return _laboratory_po_to_entity(po)

    def get_laboratory_by_code(self, code: str) -> Optional[LaboratoryAggregate]:
        """按唯一 code 查询未删除实验室（重名校验）。"""
        session = get_db_session()
        po = session.query(Laboratory).filter_by(code=code, deleted=False).first()
        if po is None:
            return None
        return _laboratory_po_to_entity(po)

    def list_laboratories(self, page: int = 1, per_page: int = 10,
                          keyword: str = None, status: str = None) -> dict:
        """分页查询实验室列表（items 含 device_count/playback_device_count/test_case_count）。"""
        session = get_db_session()
        query = session.query(Laboratory).filter_by(deleted=False)

        if keyword:
            query = query.filter(
                (Laboratory.code.like(f'%{keyword}%')) |
                (Laboratory.name.like(f'%{keyword}%')) |
                (Laboratory.building.like(f'%{keyword}%'))
            )
        if status:
            query = query.filter(Laboratory.status == status)

        query = query.order_by(Laboratory.id.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        items = []
        lab_ids = [po.id for po in pagination.items]
        if lab_ids:
            device_counts = self.count_devices(lab_ids)
            playback_counts = self.count_playback_devices(lab_ids)
            testcase_counts = self.count_test_cases(lab_ids)
            for po in pagination.items:
                item = _laboratory_po_to_entity(po).to_dict()
                item['device_count'] = device_counts.get(po.id, 0)
                item['playback_device_count'] = playback_counts.get(po.id, 0)
                item['test_case_count'] = testcase_counts.get(po.id, 0)
                items.append(item)

        return {
            'items': items,
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages,
        }

    def count_devices(self, lab_ids: List[int]) -> Dict[int, int]:
        """统计各实验室的未删除被测设备数（devices.lab_id）。"""
        if not lab_ids:
            return {}
        session = get_db_session()
        rows = (
            session.query(Device.lab_id, Device.id)
            .filter(Device.lab_id.in_(lab_ids), Device.deleted == False)  # noqa: E712
            .all()
        )
        counts: Dict[int, int] = {}
        for lab_id, _device_id in rows:
            if lab_id is not None:
                counts[lab_id] = counts.get(lab_id, 0) + 1
        return counts

    def count_playback_devices(self, lab_ids: List[int]) -> Dict[int, int]:
        """统计各实验室的未删除播放设备数（playback_devices.lab_id）。"""
        if not lab_ids:
            return {}
        session = get_db_session()
        rows = (
            session.query(PlaybackDevice.lab_id, PlaybackDevice.id)
            .filter(PlaybackDevice.lab_id.in_(lab_ids), PlaybackDevice.is_deleted == 0)
            .all()
        )
        counts: Dict[int, int] = {}
        for lab_id, _device_id in rows:
            if lab_id is not None:
                counts[lab_id] = counts.get(lab_id, 0) + 1
        return counts

    def count_test_cases(self, lab_ids: List[int]) -> Dict[int, int]:
        """统计各实验室的用例数（task_service test_cases.config JSONB 中 lab_id，跨域 gRPC）。

        按现有 testcase_acl_repository.check_playback_in_testcases 的模式全量分页
        扫描用例 config，统计 config.lab_id ∈ lab_ids 的用例数。gRPC 不可用时
        返回空计数（与 check_playback_in_testcases 的降级语义一致）。
        """
        if not lab_ids:
            return {}
        from device_service.infrastructure.acl.testcase_acl_repository import testcase_acl_repository
        lab_set = set(int(x) for x in lab_ids)
        counts: Dict[int, int] = {}
        page = 1
        per_page = 100
        while True:
            data = testcase_acl_repository.list_testcases(page=page, per_page=per_page)
            if not isinstance(data, dict):
                return counts
            items = data.get('items', []) or []
            for tc in items:
                config = tc.get('config')
                if not isinstance(config, dict):
                    continue
                tc_lab = config.get('lab_id')
                if tc_lab is None:
                    continue
                try:
                    tc_lab_int = int(tc_lab)
                except (TypeError, ValueError):
                    continue
                if tc_lab_int in lab_set:
                    counts[tc_lab_int] = counts.get(tc_lab_int, 0) + 1
            total_pages = data.get('pages', 1)
            if page >= total_pages or not items:
                break
            page += 1
        return counts


# ========== 模块级单例（供 application 层依赖注入） ==========
laboratory_repository = LaboratoryRepository()
