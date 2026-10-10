# -*- coding: utf-8 -*-
"""被测 API RMS→SPL 映射持久化仓储实现（INT-61）

本服务 owned 表 api_rms_spl_mappings；映射默认项由 apis.rms_spl_mapping_id 指定。
"""
from __future__ import annotations

import logging
from typing import Optional

from api_test_service.domain.entities.api_rms_spl_mapping import (
    ApiRmsSplMapping,
    CalibrationPoint,
)
from api_test_service.domain.repositories.api_rms_spl_repository_abc import (
    ApiRmsSplRepository,
)

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
