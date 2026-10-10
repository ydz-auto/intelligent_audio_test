# -*- coding: utf-8 -*-
"""被测 API RMS→SPL 映射持久化仓储实现（INT-61 读侧 / UC-0902 写侧）

本服务 owned 表 api_rms_spl_mappings；映射默认项由 apis.rms_spl_mapping_id 指定。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from api_test_service.domain.entities.api_rms_spl_mapping import (
    ApiRmsSplMapping,
    CalibrationPoint,
)
from api_test_service.domain.repositories.api_rms_spl_repository_abc import (
    ApiRmsSplRepository,
)
from shared.models.common_enums import CalibrationStatus
from shared.utils.query_utils import now_cst

logger = logging.getLogger(__name__)


def _po_to_entity(po) -> Optional[ApiRmsSplMapping]:
    """PO → 领域实体（infrastructure 层唯一转换点）"""
    if po is None:
        return None
    points_data = (po.calibration_data or {}).get('points', [])
    points = [
        CalibrationPoint(
            target_spl=p.get('target_spl', 0.0),
            gain_linear=p.get('gain_linear', 1.0),
            rms_dbfs=p.get('rms_dbfs'),
        )
        for p in points_data if isinstance(p, dict)
    ]
    return ApiRmsSplMapping(
        id=po.id,
        api_id=po.api_id,
        name=po.name or '',
        vendor=po.vendor or '',
        protocol=po.protocol or 'websocket',
        reference_spl=po.reference_spl,
        reference_gain_linear=po.reference_gain_linear,
        calibration_status=po.calibration_status,
        calibration_points=points,
        min_gain_linear=po.min_gain_linear,
        max_gain_linear=po.max_gain_linear,
        deleted=bool(po.deleted),
    )


def _entity_to_po_fields(mapping: ApiRmsSplMapping) -> dict:
    """领域实体 → PO 字段（calibration_points 打包为 JSON）"""
    return {
        'api_id': mapping.api_id,
        'name': mapping.name,
        'vendor': mapping.vendor,
        'protocol': mapping.protocol,
        'reference_spl': mapping.reference_spl,
        'reference_gain_linear': mapping.reference_gain_linear,
        'calibration_status': mapping.calibration_status,
        'calibration_data': {
            'points': [
                {
                    'target_spl': p.target_spl,
                    'gain_linear': p.gain_linear,
                    'rms_dbfs': p.rms_dbfs,
                }
                for p in mapping.calibration_points
            ]
        },
        'min_gain_linear': mapping.min_gain_linear,
        'max_gain_linear': mapping.max_gain_linear,
    }


class ApiRmsSplRepositoryImpl(ApiRmsSplRepository):
    """api_rms_spl_mappings 表仓储实现"""

    def get_default_mapping(self, api_id) -> Optional[ApiRmsSplMapping]:
        from shared.models.database import get_db_session
        from api_test_service.infrastructure.persistence.models.api_models import (
            API,
            ApiRmsSplMappingPO,
        )

        session = get_db_session()
        try:
            api = session.query(API).filter(API.id == int(api_id), API.deleted.is_(False)).first()
            po = None
            if api is not None and api.rms_spl_mapping_id:
                po = (
                    session.query(ApiRmsSplMappingPO)
                    .filter(
                        ApiRmsSplMappingPO.id == api.rms_spl_mapping_id,
                        ApiRmsSplMappingPO.deleted.is_(False),
                    )
                    .first()
                )
            if po is None:
                po = (
                    session.query(ApiRmsSplMappingPO)
                    .filter(
                        ApiRmsSplMappingPO.api_id == int(api_id),
                        ApiRmsSplMappingPO.deleted.is_(False),
                    )
                    .order_by(ApiRmsSplMappingPO.created_at.desc())
                    .first()
                )
            return _po_to_entity(po)
        except Exception as e:
            logger.warning(f"查询 API {api_id} 的 RMS→SPL 映射失败: {e}")
            return None
        finally:
            session.close()

    def get_mapping(self, mapping_id) -> Optional[ApiRmsSplMapping]:
        from shared.models.database import get_db_session
        from api_test_service.infrastructure.persistence.models.api_models import (
            ApiRmsSplMappingPO,
        )

        session = get_db_session()
        try:
            po = (
                session.query(ApiRmsSplMappingPO)
                .filter(
                    ApiRmsSplMappingPO.id == int(mapping_id),
                    ApiRmsSplMappingPO.deleted.is_(False),
                )
                .first()
            )
            return _po_to_entity(po)
        except Exception as e:
            logger.warning(f"查询 RMS→SPL 映射 {mapping_id} 失败: {e}")
            return None
        finally:
            session.close()

    # ==================== UC-0902 写侧 ====================

    def create_mapping(self, data: dict) -> ApiRmsSplMapping:
        from shared.models.database import get_db_session
        from api_test_service.infrastructure.persistence.models.api_models import (
            ApiRmsSplMappingPO,
        )

        session = get_db_session()
        try:
            po = ApiRmsSplMappingPO(
                api_id=int(data['api_id']),
                name=data.get('name') or '',
                description=data.get('description'),
                vendor=data.get('vendor'),
                protocol=data.get('protocol') or 'websocket',
                reference_spl=data.get('reference_spl', 65.0),
                reference_gain_linear=data.get('reference_gain_linear', 1.0),
                calibration_status=data.get('calibration_status')
                or data.get('calibrationStatus')
                or CalibrationStatus.UNCALIBRATED.value,
                calibration_data=data.get('calibration_data') or {},
                min_gain_linear=data.get('min_gain_linear', 0.001),
                max_gain_linear=data.get('max_gain_linear', 10.0),
            )
            session.add(po)
            session.commit()
            return _po_to_entity(po)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_mapping(self, mapping_id, data: dict) -> Optional[ApiRmsSplMapping]:
        from shared.models.database import get_db_session
        from api_test_service.infrastructure.persistence.models.api_models import (
            ApiRmsSplMappingPO,
        )

        session = get_db_session()
        try:
            po = (
                session.query(ApiRmsSplMappingPO)
                .filter(
                    ApiRmsSplMappingPO.id == int(mapping_id),
                    ApiRmsSplMappingPO.deleted.is_(False),
                )
                .first()
            )
            if po is None:
                return None
            for key, value in data.items():
                if hasattr(po, key):
                    setattr(po, key, value)
            session.commit()
            return _po_to_entity(po)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_mapping(self, mapping_id) -> bool:
        from shared.models.database import get_db_session
        from api_test_service.infrastructure.persistence.models.api_models import (
            ApiRmsSplMappingPO,
        )

        session = get_db_session()
        try:
            po = (
                session.query(ApiRmsSplMappingPO)
                .filter(
                    ApiRmsSplMappingPO.id == int(mapping_id),
                    ApiRmsSplMappingPO.deleted.is_(False),
                )
                .first()
            )
            if po is None:
                return False
            po.deleted = True
            po.deleted_at = now_cst()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_mappings(self, page: int = 1, per_page: int = 10,
                      api_id=None, calibration_status=None) -> dict:
        from shared.models.database import get_db_session
        from api_test_service.infrastructure.persistence.models.api_models import (
            ApiRmsSplMappingPO,
        )

        session = get_db_session()
        try:
            query = session.query(ApiRmsSplMappingPO).filter(
                ApiRmsSplMappingPO.deleted.is_(False)
            )
            if api_id is not None:
                query = query.filter(ApiRmsSplMappingPO.api_id == int(api_id))
            if calibration_status:
                query = query.filter(ApiRmsSplMappingPO.calibration_status == calibration_status)
            total = query.count()
            items = (
                query.order_by(ApiRmsSplMappingPO.created_at.desc())
                .offset((max(int(page), 1) - 1) * int(per_page))
                .limit(int(per_page))
                .all()
            )
            pages = (total + int(per_page) - 1) // int(per_page) if per_page else 1
            return {
                'items': [_po_to_entity(po) for po in items],
                'total': total,
                'page': int(page),
                'per_page': int(per_page),
                'pages': pages,
            }
        finally:
            session.close()

    def list_by_api(self, api_id) -> List[ApiRmsSplMapping]:
        from shared.models.database import get_db_session
        from api_test_service.infrastructure.persistence.models.api_models import (
            ApiRmsSplMappingPO,
        )

        session = get_db_session()
        try:
            items = (
                session.query(ApiRmsSplMappingPO)
                .filter(
                    ApiRmsSplMappingPO.api_id == int(api_id),
                    ApiRmsSplMappingPO.deleted.is_(False),
                )
                .order_by(ApiRmsSplMappingPO.created_at.desc())
                .all()
            )
            return [_po_to_entity(po) for po in items]
        finally:
            session.close()
