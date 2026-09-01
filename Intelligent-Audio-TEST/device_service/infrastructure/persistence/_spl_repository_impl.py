# -*- coding: utf-8 -*-
"""SPL 映射仓储实现（从 device_repository.py 拆分，P4-5 大文件拆分）。

SPLRepository：SPL 映射 / 校准历史仓储。

P5+DOMAIN: 通过 PO ↔ Entity 显式转换，仓储方法返回 domain entities
（SPLMappingEntity / CalibrationHistoryEntity），聚合根不再持有 ORM 引用。
"""
from typing import List, Optional

from shared.models.database import get_db_session
from device_service.infrastructure.persistence.models import (
    PlaybackDevice,
    SPLMapping,
    CalibrationHistory,
)
from device_service.domain.entities import (
    PlaybackDeviceAggregate,
    SPLMappingEntity,
    CalibrationHistoryEntity,
)
from device_service.domain.repositories import SPLRepositoryInterface
from device_service.infrastructure.persistence._device_converters import (
    _now,
    _spl_mapping_po_to_entity,
    _calibration_history_po_to_entity,
)
from device_service.infrastructure.persistence._device_serializers import (
    _spl_mapping_to_dict,
)


class SPLRepository(SPLRepositoryInterface):
    """SPL 映射仓储

    P5+DOMAIN: 通过 PO ↔ Entity 显式转换，仓储方法返回 domain entities
    （SPLMappingEntity / CalibrationHistoryEntity），聚合根不再持有 ORM 引用。
    """

    def create_spl_mapping(self, data: dict) -> SPLMappingEntity:
        """创建 SPL 映射，返回 SPLMappingEntity 实体。"""
        session = get_db_session()
        new_mapping = SPLMapping(
            name=data['name'],
            description=data.get('description'),
            device_id=data.get('device_id'),
            device_type=data.get('device_type'),
            distance=data.get('distance') or 1.0,
            target_spl=data.get('target_spl'),
            digital_gain=data.get('digital_gain'),
            test_frequency=data.get('test_frequency') or 1000,
            calibration_status=data.get('calibration_status') or 'uncalibrated',
            calibration_data=data.get('calibration_data'),
        )
        session.add(new_mapping)
        session.flush()
        return _spl_mapping_po_to_entity(new_mapping)

    def update_spl_mapping(self, mapping_id: int, update_fields: dict) -> Optional[SPLMappingEntity]:
        """更新 SPL 映射字段，返回更新后的 SPLMappingEntity。"""
        session = get_db_session()
        mapping = session.get(SPLMapping, mapping_id)
        if not mapping or mapping.deleted:
            return None
        for key, value in update_fields.items():
            setattr(mapping, key, value)
        mapping.updated_at = _now()
        session.commit()
        return _spl_mapping_po_to_entity(mapping)

    def get_spl_mapping(self, mapping_id: int) -> Optional[SPLMappingEntity]:
        """按 ID 查询 SPL 映射，返回 SPLMappingEntity。"""
        session = get_db_session()
        po = session.get(SPLMapping, mapping_id)
        if po is None:
            return None
        return _spl_mapping_po_to_entity(po)

    def delete_spl_mapping(self, mapping_id: int) -> bool:
        """软删除 SPL 映射"""
        session = get_db_session()
        mapping = session.get(SPLMapping, mapping_id)
        if not mapping or mapping.deleted:
            return False
        now = _now()
        mapping.deleted = True
        mapping.deleted_at = now
        mapping.updated_at = now
        session.commit()
        return True

    def list_spl_mappings(self, page: int = 1, per_page: int = 10, keyword: str = None,
                         calibration_status: str = None, device_id: int = None) -> dict:
        """分页查询 SPL 映射列表。

        返回 dict（含 items/total/page 等字段），items 为 SPLMapping PO 的序列化 dict。
        """
        session = get_db_session()
        query = session.query(SPLMapping).filter(SPLMapping.deleted == False)  # noqa: E712
        if keyword:
            query = query.filter(
                (SPLMapping.name.ilike(f"%{keyword}%")) |
                (SPLMapping.description.ilike(f"%{keyword}%"))
            )
        if calibration_status and calibration_status != 'undefined' and calibration_status != 'all':
            query = query.filter_by(calibration_status=calibration_status)
        if device_id:
            query = query.filter_by(device_id=device_id)

        pagination = query.order_by(SPLMapping.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return {
            'items': [_spl_mapping_to_dict(m) for m in pagination.items],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages,
        }

    def get_spl_mapping_dict(self, mapping_id: int) -> Optional[dict]:
        """按 ID 查询 SPL 映射并返回 dict（含关联设备信息）"""
        session = get_db_session()
        mapping = session.get(SPLMapping, mapping_id)
        if not mapping or mapping.deleted:
            return None
        device = None
        if mapping.device_id:
            device = session.get(PlaybackDevice, mapping.device_id)
        return _spl_mapping_to_dict(mapping, device)

    def get_calibration_history(self, mapping_id: int) -> List[dict]:
        """获取校准历史（返回 dict 列表，兼容上层序列化）"""
        session = get_db_session()
        history = session.query(CalibrationHistory).filter_by(
            mapping_id=mapping_id
        ).order_by(CalibrationHistory.created_at.desc()).all()
        return [
            {
                'id': h.id,
                'calibration_data': h.calibration_data,
                'distance': h.distance,
                'test_frequency': h.test_frequency,
                'created_at': h.created_at.isoformat() if h.created_at else None,
            }
            for h in history
        ]

    def get_spl_stats(self) -> dict:
        """获取 SPL 统计信息"""
        session = get_db_session()
        total = session.query(SPLMapping).filter(SPLMapping.deleted == False).count()  # noqa: E712
        calibrated = session.query(SPLMapping).filter_by(
            calibration_status='calibrated', deleted=False
        ).count()
        uncalibrated = total - calibrated
        associated_devices = session.query(SPLMapping.device_id).filter(
            SPLMapping.deleted == False  # noqa: E712
        ).distinct().count()
        return {
            'total': total,
            'calibrated': calibrated,
            'uncalibrated': uncalibrated,
            'associated_devices': associated_devices,
        }

    def get_spl_by_device(self, device_id: int) -> List[dict]:
        """按设备 ID 查询 SPL 映射列表（返回 dict 列表）"""
        session = get_db_session()
        mappings = session.query(SPLMapping).filter_by(
            device_id=device_id, deleted=False
        ).order_by(SPLMapping.created_at.desc()).all()
        return [
            {
                'id': m.id,
                'name': m.name,
                'description': m.description,
                'device_id': m.device_id,
                'device_type': m.device_type,
                'distance': m.distance,
                'target_spl': m.target_spl,
                'calibration_status': m.calibration_status,
                'created_at': m.created_at.isoformat() if m.created_at else None,
                'updated_at': m.updated_at.isoformat() if m.updated_at else None,
            }
            for m in mappings
        ]

    def create_calibration_history(self, mapping_id: int, calibration_data, distance, test_frequency) -> CalibrationHistoryEntity:
        """创建校准历史记录，返回 CalibrationHistoryEntity 实体。"""
        session = get_db_session()
        history = CalibrationHistory(
            mapping_id=mapping_id,
            calibration_data=calibration_data,
            distance=distance,
            test_frequency=test_frequency,
        )
        session.add(history)
        session.commit()
        return _calibration_history_po_to_entity(history)

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

    def get_playback_device(self, device_id: int) -> Optional[PlaybackDeviceAggregate]:
        """获取播放设备（用于关联检查），返回 PlaybackDeviceAggregate。"""
        session = get_db_session()
        po = session.get(PlaybackDevice, device_id)
        if po is None:
            return None
        return _playback_po_to_entity(po)

    # ========== 跨域只读查询（CaseAlgorithmParam / AlgorithmReferenceParam）==========
    # 通过 gRPC 调用 algorithm_service.ListCaseParams / ListReferenceParams，
    # 返回 dict 列表；gRPC 不可用时回退直连 PO。

    def list_case_algorithm_params(self, algorithm_type: str):
        """查询指定算法类型的用例参数列表（返回 dict 列表）。

        通过 gRPC 调用 algorithm_service.ListCaseParams，替代直连
        CaseAlgorithmParam PO；gRPC 不可用时回退直连。
        """
        from device_service.infrastructure.acl.algorithm_definition_acl_repository import algorithm_definition_acl_repository
        return algorithm_definition_acl_repository.list_case_params(algorithm_type)

    def list_algorithm_reference_params(self, algorithm_type: str):
        """查询指定算法类型的引用参数列表（返回 dict 列表）。

        通过 gRPC 调用 algorithm_service.ListReferenceParams，替代直连
        AlgorithmReferenceParam PO；gRPC 不可用时返回空列表。
        """
        from device_service.infrastructure.acl.algorithm_definition_acl_repository import algorithm_definition_acl_repository
        return algorithm_definition_acl_repository.list_reference_params(algorithm_type)

    def commit(self):
        """提交事务"""
        get_db_session().commit()

    def rollback(self):
        """回滚事务"""
        get_db_session().rollback()

    def flush(self):
        """flush session"""
        get_db_session().flush()
