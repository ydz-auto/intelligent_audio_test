# -*- coding: utf-8 -*-
"""PlaybackRepository - 播放设备仓储实现（从 device_repository.py 拆分，P4-5 大文件拆分）。

P5+DOMAIN: 通过 PO ↔ Entity 显式转换，仓储方法返回 domain entities
（PlaybackDeviceAggregate），聚合根不再持有 ORM 引用。
"""
from typing import Dict, List, Optional

from shared.models.database import get_db_session
from device_service.infrastructure.persistence.models import PlaybackDevice
from device_service.domain.entities import PlaybackDeviceAggregate
from device_service.domain.repositories import PlaybackRepositoryInterface
from device_service.infrastructure.persistence._device_converters import (
    _now,
    _playback_po_to_entity,
)
from device_service.infrastructure.persistence._device_serializers import (
    _playback_to_dict,
)


class PlaybackRepository(PlaybackRepositoryInterface):
    """播放设备仓储

    P5+DOMAIN: 通过 PO ↔ Entity 显式转换，仓储方法返回 domain entities
    （PlaybackDeviceAggregate），聚合根不再持有 ORM 引用。
    """

    def create_playback_device(self, data: dict) -> PlaybackDeviceAggregate:
        """创建播放设备，返回 PlaybackDeviceAggregate 聚合根。"""
        session = get_db_session()
        new_device = PlaybackDevice(
            name=data['name'],
            model=data['model'],
            device_type=data['device_type'],
            sample_rate=data['sample_rate'],
            channel_index=data.get('channel_index', 0),
            device_unique_id=data['device_unique_id'],
            description=data.get('description'),
            status=data.get('status', 'online'),
        )
        session.add(new_device)
        session.commit()
        return _playback_po_to_entity(new_device)

    def find_playback_by_unique_and_channel(self, device_unique_id: str, channel_index: int) -> Optional[PlaybackDeviceAggregate]:
        """按唯一标识和通道索引查找未删除的播放设备，返回 PlaybackDeviceAggregate。"""
        session = get_db_session()
        po = session.query(PlaybackDevice).filter_by(
            device_unique_id=device_unique_id,
            channel_index=channel_index,
            is_deleted=0,
        ).first()
        if po is None:
            return None
        return _playback_po_to_entity(po)

    def update_playback_device(self, device_id: int, update_fields: dict) -> Optional[PlaybackDeviceAggregate]:
        """更新播放设备字段，返回更新后的 PlaybackDeviceAggregate。"""
        session = get_db_session()
        device = session.get(PlaybackDevice, device_id)
        if not device:
            return None
        for key, value in update_fields.items():
            setattr(device, key, value)
        device.updated_at = _now()
        session.commit()
        return _playback_po_to_entity(device)

    def get_playback_device(self, device_id: int) -> Optional[PlaybackDeviceAggregate]:
        """按 ID 查询播放设备，返回 PlaybackDeviceAggregate。"""
        session = get_db_session()
        po = session.query(PlaybackDevice).filter_by(id=device_id, is_deleted=0).first()
        if po is None:
            return None
        return _playback_po_to_entity(po)

    def delete_playback_device(self, device_id: int) -> bool:
        """软删除播放设备"""
        session = get_db_session()
        device = session.query(PlaybackDevice).filter_by(id=device_id, is_deleted=0).first()
        if not device:
            return False
        device.is_deleted = 1
        device.updated_at = _now()
        session.commit()
        return True

    def list_playback_devices(self, page: int = 1, per_page: int = 10,
                              keyword: str = None, device_type: str = None) -> dict:
        """分页查询播放设备列表。

        返回 dict（含 items/total/page 等字段），items 为 PlaybackDevice PO 的序列化 dict。
        """
        session = get_db_session()
        query = session.query(PlaybackDevice).filter_by(is_deleted=0)

        if keyword:
            query = query.filter(
                (PlaybackDevice.name.like(f'%{keyword}%')) |
                (PlaybackDevice.model.like(f'%{keyword}%')) |
                (PlaybackDevice.device_unique_id.like(f'%{keyword}%')) |
                (PlaybackDevice.description.like(f'%{keyword}%'))
            )
        if device_type:
            query = query.filter(PlaybackDevice.device_type == device_type)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return {
            'items': [_playback_to_dict(d) for d in pagination.items],
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages,
        }

    def check_playback_in_testcases(self, device_id: int) -> int:
        """检查播放设备是否被测试用例引用"""
        from device_service.infrastructure.acl.testcase_acl_repository import testcase_acl_repository
        return testcase_acl_repository.check_playback_in_testcases(device_id)

    def update_playback_device_spl_ref(self, device_id: int, spl_mapping_id) -> bool:
        """更新播放设备的 current_spl_mapping_id 引用"""
        session = get_db_session()
        device = session.get(PlaybackDevice, device_id)
        if not device:
            return False
        device.current_spl_mapping_id = spl_mapping_id
        device.updated_at = _now()
        session.commit()
        return True

    def get_all_playback_devices(self) -> List[PlaybackDeviceAggregate]:
        """获取所有未删除播放设备，返回 PlaybackDeviceAggregate 列表。"""
        session = get_db_session()
        pos = session.query(PlaybackDevice).filter_by(is_deleted=0).all()
        return [_playback_po_to_entity(po) for po in pos]

    def find_playback_by_unique_id(self, unique_id: str) -> Optional[PlaybackDeviceAggregate]:
        """按 device_unique_id 查找播放设备，返回 PlaybackDeviceAggregate。"""
        session = get_db_session()
        po = session.query(PlaybackDevice).filter_by(
            device_unique_id=unique_id, is_deleted=0
        ).first()
        if po is None:
            return None
        return _playback_po_to_entity(po)

    def find_playback_limit(self, limit: int = 10) -> List[PlaybackDeviceAggregate]:
        """获取前 N 个播放设备，返回 PlaybackDeviceAggregate 列表。"""
        session = get_db_session()
        pos = session.query(PlaybackDevice).filter_by(is_deleted=0).limit(limit).all()
        return [_playback_po_to_entity(po) for po in pos]

    def batch_update_playback_status(self, status_map: Dict[int, str]) -> int:
        """批量更新播放设备状态"""
        session = get_db_session()
        updated = 0
        now = _now()
        for device_id, new_status in status_map.items():
            device = session.get(PlaybackDevice, device_id)
            if device:
                device.status = new_status
                device.updated_at = now
                updated += 1
        session.commit()
        return updated

    # ========== 批量查询（供 application 层替代直接 PO 查询）==========

    def list_playback_devices_by_unique_ids(self, unique_ids: List[str]) -> List[PlaybackDeviceAggregate]:
        """按 device_unique_id 列表批量查询播放设备。

        供 audio_preview_service 替代 session.query(PlaybackDevice).filter(...).first() 循环。
        """
        session = get_db_session()
        if not unique_ids:
            return []
        pos = session.query(PlaybackDevice).filter(
            PlaybackDevice.device_unique_id.in_(unique_ids),
            PlaybackDevice.is_deleted == 0,
        ).all()
        return [_playback_po_to_entity(po) for po in pos]

    def list_playback_devices_by_ids(self, device_ids: List) -> List[PlaybackDeviceAggregate]:
        """按 ID 列表批量查询播放设备（id 为 int 或 str 均可）。

        供 audio_preview_service 替代 session.get(PlaybackDevice, device_id) 循环。
        """
        session = get_db_session()
        if not device_ids:
            return []
        # 统一转为字符串用于 device_unique_id 查询；若为 int 则按 id 查
        int_ids = [d for d in device_ids if isinstance(d, int)]
        str_ids = [d for d in device_ids if isinstance(d, str)]
        result: List[PlaybackDeviceAggregate] = []

        if int_ids:
            pos = session.query(PlaybackDevice).filter(
                PlaybackDevice.id.in_(int_ids),
                PlaybackDevice.is_deleted == 0,
            ).all()
            result.extend(_playback_po_to_entity(po) for po in pos)

        if str_ids:
            pos = session.query(PlaybackDevice).filter(
                PlaybackDevice.device_unique_id.in_(str_ids),
                PlaybackDevice.is_deleted == 0,
            ).all()
            result.extend(_playback_po_to_entity(po) for po in pos)

        return result

    def get_all_playback_device_name_to_id_map(self) -> Dict[str, int]:
        """查询所有播放设备的 name → id 映射（用于从标注解析 playback_device_name）。

        供 audio_testcase_creation_service 替代直接 query PlaybackDevice PO。
        """
        session = get_db_session()
        pos = session.query(PlaybackDevice).filter_by(is_deleted=0).all()
        result: Dict[str, int] = {}
        for d in pos:
            result.setdefault(d.name, d.id)
        return result

    def find_default_dry_playback_device(self) -> Optional[PlaybackDeviceAggregate]:
        """查询第一个 device_type='dry' 的播放设备（用于 e2e 默认回填）。

        供 audio_testcase_creation_service 替代直接 query PlaybackDevice PO。
        """
        session = get_db_session()
        po = session.query(PlaybackDevice).filter_by(
            device_type='dry', is_deleted=0
        ).first()
        return _playback_po_to_entity(po) if po else None

    def clear_playback_spl_refs(self, mapping_id: int) -> int:
        """清理播放设备中引用此 mapping 的 current_spl_mapping_id"""
        session = get_db_session()
        count = session.query(PlaybackDevice).filter_by(
            current_spl_mapping_id=mapping_id
        ).update({
            'current_spl_mapping_id': None,
            'updated_at': _now(),
        })
        session.commit()
        return count
