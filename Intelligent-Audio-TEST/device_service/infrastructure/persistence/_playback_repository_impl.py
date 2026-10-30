# -*- coding: utf-8 -*-
"""PlaybackRepository - 播放设备仓储实现（从 device_repository.py 拆分，P4-5 大文件拆分）。

P5+DOMAIN: 通过 PO ↔ Entity 显式转换，仓储方法返回 domain entities
（PlaybackDeviceAggregate），聚合根不再持有 ORM 引用。
"""
from typing import Dict, List, Optional

from shared.models.database import get_db_session
from device_service.infrastructure.persistence.models import (
    PlaybackDevice,
    PlaybackSpeakerGroup,
    PlaybackSpeakerGroupItem,
)
from device_service.domain.entities import (
    PlaybackDeviceAggregate,
    PlaybackSpeakerGroupAggregate,
    PlaybackSpeakerGroupItemEntity,
)
from device_service.domain.repositories import PlaybackRepositoryInterface
from device_service.infrastructure.persistence._device_converters import (
    _now,
    _playback_po_to_entity,
    _speaker_group_po_to_entity,
    _speaker_item_po_to_entity,
)
from device_service.infrastructure.persistence._device_serializers import (
    _playback_to_dict,
)
from device_service.infrastructure.persistence._lab_resolver import resolve_lab_names


class PlaybackRepository(PlaybackRepositoryInterface):
    """播放设备仓储

    P5+DOMAIN: 通过 PO ↔ Entity 显式转换，仓储方法返回 domain entities
    （PlaybackDeviceAggregate），聚合根不再持有 ORM 引用。
    """

    def create_playback_device(self, data: dict) -> PlaybackDeviceAggregate:
        """创建播放设备，返回 PlaybackDeviceAggregate 聚合根。"""
        from shared.infrastructure.user_context import get_current_user_id
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
            lab_id=data.get('lab_id'),
            created_by_user_id=get_current_user_id(),
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
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        device = session.get(PlaybackDevice, device_id)
        if not device:
            return None
        for key, value in update_fields.items():
            setattr(device, key, value)
        device.updated_at = _now()
        device.updated_by_user_id = get_current_user_id()
        session.commit()
        return _playback_po_to_entity(device)

    def get_playback_device(self, device_id: int) -> Optional[PlaybackDeviceAggregate]:
        """按 ID 查询播放设备，返回 PlaybackDeviceAggregate。"""
        session = get_db_session()
        po = session.query(PlaybackDevice).filter_by(id=device_id, is_deleted=0).first()
        if po is None:
            return None
        lab_names = resolve_lab_names([po.lab_id]) if po.lab_id else {}
        return _playback_po_to_entity(po, lab_name=lab_names.get(po.lab_id))

    def delete_playback_device(self, device_id: int) -> bool:
        """软删除播放设备"""
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        device = session.query(PlaybackDevice).filter_by(id=device_id, is_deleted=0).first()
        if not device:
            return False
        device.is_deleted = 1
        device.deleted_by_user_id = get_current_user_id()
        device.updated_at = _now()
        session.commit()
        return True

    def list_playback_devices(self, page: int = 1, per_page: int = 10,
                              keyword: str = None, device_type: str = None,
                              lab_id: int = None) -> dict:
        """分页查询播放设备列表。

        返回 dict（含 items/total/page 等字段），items 为 PlaybackDevice PO 的序列化 dict。
        lab_id 按实验室过滤（INT-493 §4.2），lab_name 经 laboratories 表解析后随 items 返回。
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
        if lab_id:
            query = query.filter(PlaybackDevice.lab_id == lab_id)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        items = [_playback_to_dict(d) for d in pagination.items]
        self._fill_lab_names(items)
        return {
            'items': items,
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages,
        }

    @staticmethod
    def _fill_lab_names(items: List[dict]) -> None:
        """批量回填 items 中 lab_id 对应的 lab_name（laboratories 表，INT-493 §4.2）。"""
        lab_ids = [item['lab_id'] for item in items if item.get('lab_id')]
        if not lab_ids:
            return
        names = resolve_lab_names(lab_ids)
        for item in items:
            if item.get('lab_id') is not None:
                item['lab_name'] = names.get(item['lab_id'])

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

    # ---- 逻辑音箱组（N 个实验室里位置相同的音箱互相对应）----

    @staticmethod
    def _group_with_items(session, group_po):
        items = session.query(PlaybackSpeakerGroupItem).filter_by(
            group_id=group_po.id).order_by(PlaybackSpeakerGroupItem.lab_id.asc()).all()
        return _speaker_group_po_to_entity(group_po, items)

    def list_playback_speaker_groups(self, keyword: str = None) -> List[PlaybackSpeakerGroupAggregate]:
        """逻辑音箱组列表（含组内各实验室对应设备）"""
        session = get_db_session()
        query = session.query(PlaybackSpeakerGroup)
        if keyword:
            query = query.filter(PlaybackSpeakerGroup.name.like(f'%{keyword}%'))
        return [self._group_with_items(session, po)
                for po in query.order_by(PlaybackSpeakerGroup.id.asc()).all()]

    def get_playback_speaker_group(self, group_id: int) -> Optional[PlaybackSpeakerGroupAggregate]:
        session = get_db_session()
        po = session.get(PlaybackSpeakerGroup, int(group_id))
        return self._group_with_items(session, po) if po else None

    def create_playback_speaker_group(self, name: str, description: str = None) -> PlaybackSpeakerGroupAggregate:
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        po = PlaybackSpeakerGroup(
            name=name,
            description=description,
            created_by_user_id=get_current_user_id(),
        )
        session.add(po)
        session.commit()
        return _speaker_group_po_to_entity(po)

    def update_playback_speaker_group(self, group_id: int,
                                      data: dict) -> Optional[PlaybackSpeakerGroupAggregate]:
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        po = session.get(PlaybackSpeakerGroup, int(group_id))
        if po is None:
            return None
        if data.get('name'):
            po.name = data['name']
        if 'description' in data:
            po.description = data.get('description')
        po.updated_by_user_id = get_current_user_id()
        po.updated_at = _now()
        session.commit()
        return self._group_with_items(session, po)

    def delete_playback_speaker_group(self, group_id: int) -> bool:
        """删除逻辑音箱组（连同组内条目；组是纯映射配置）"""
        session = get_db_session()
        po = session.get(PlaybackSpeakerGroup, int(group_id))
        if po is None:
            return False
        session.query(PlaybackSpeakerGroupItem).filter_by(group_id=po.id).delete()
        session.delete(po)
        session.commit()
        return True

    def upsert_playback_speaker_group_item(self, group_id: int, lab_id: int,
                                           playback_device_id: int) -> PlaybackSpeakerGroupItemEntity:
        """设置逻辑音箱在指定实验室对应的设备（同组同实验室唯一）"""
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        po = session.query(PlaybackSpeakerGroupItem).filter_by(
            group_id=int(group_id), lab_id=int(lab_id)).first()
        if po is None:
            po = PlaybackSpeakerGroupItem(
                group_id=int(group_id),
                lab_id=int(lab_id),
                playback_device_id=int(playback_device_id),
                created_by_user_id=get_current_user_id(),
            )
            session.add(po)
        else:
            po.playback_device_id = int(playback_device_id)
            po.updated_by_user_id = get_current_user_id()
            po.updated_at = _now()
        session.commit()
        return _speaker_item_po_to_entity(po)

    def delete_playback_speaker_group_item(self, group_id: int, lab_id: int) -> bool:
        session = get_db_session()
        deleted = session.query(PlaybackSpeakerGroupItem).filter_by(
            group_id=int(group_id), lab_id=int(lab_id)).delete()
        session.commit()
        return deleted > 0

    def resolve_playback_speaker_device(self, source_device_id: int,
                                        target_lab_id: int) -> Optional[int]:
        """解析：源音箱 → 所属逻辑组 → 目标实验室在该组的设备（执行链热路径）"""
        session = get_db_session()
        source = session.query(PlaybackSpeakerGroupItem).filter_by(
            playback_device_id=int(source_device_id)).first()
        if source is None:
            return None
        target = session.query(PlaybackSpeakerGroupItem).filter_by(
            group_id=source.group_id, lab_id=int(target_lab_id)).first()
        return target.playback_device_id if target else None

    def resolve_playback_speaker_group_device(self, group_id: int,
                                              target_lab_id: int) -> Optional[int]:
        """解析：逻辑音箱组 → 目标实验室在该组的设备（用例直接关联逻辑音箱）"""
        session = get_db_session()
        item = session.query(PlaybackSpeakerGroupItem).filter_by(
            group_id=int(group_id), lab_id=int(target_lab_id)).first()
        return item.playback_device_id if item else None
