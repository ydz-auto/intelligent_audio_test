# -*- coding: utf-8 -*-
"""SPL 映射查询 Service（读侧）。

将 spl_controller 中的查询读侧函数迁移为 SPLQueryService 的静态方法。
保留原有逻辑，不改业务。
"""
from api_gateway.infrastructure.request_adapter import request
from shared.models.models import SPLMapping, PlaybackDevice, CalibrationHistory
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.error_codes import ErrorCode
from api_gateway.schemas.spl import (
    SplByDeviceData,
    SplByDeviceItem,
    SplHistoryData,
    SplHistoryItem,
    SplMappingItem,
    SplMappingListData,
    SplStatsData,
    SPLMappingQueryRequest,
)


class SPLQueryService:
    # ========== 查询读侧 ==========

    # 获取所有 SPL 映射配置
    @staticmethod
    def get_all():
        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        req_data = SPLMappingQueryRequest.model_validate(query_params_dict)

        keyword = req_data.keyword or req_data.search
        calibration_status = req_data.calibration_status
        page = req_data.page or 1
        per_page = req_data.per_page or 10
        device_id = req_data.device_id

        query = SPLMapping.query.filter(SPLMapping.deleted == False)
        if keyword:
            query = query.filter(
                (SPLMapping.name.ilike(f"%{keyword}%")) |
                (SPLMapping.description.ilike(f"%{keyword}%"))
            )
        if calibration_status and calibration_status != 'undefined' and calibration_status != 'all':
            query = query.filter_by(calibration_status=calibration_status)
        if device_id:
            query = query.filter_by(device_id=device_id)

        pagination = query.order_by(SPLMapping.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
        mappings = pagination.items

        data = []
        for mapping in mappings:
            device = db.session.get(PlaybackDevice, mapping.device_id)
            is_current = False
            if device and device.current_spl_mapping_id == mapping.id:
                is_current = True

            data.append(
                SplMappingItem(
                    id=mapping.id,
                    name=mapping.name,
                    description=mapping.description,
                    device_id=mapping.device_id,
                    device={"id": device.id, "name": device.name} if device else None,
                    device_name=device.name if device else "未知设备",
                    device_model=device.model if device else None,
                    device_type=mapping.device_type,
                    distance=mapping.distance,
                    target_spl=mapping.target_spl,
                    digital_gain=mapping.digital_gain,
                    calibration_status=mapping.calibration_status,
                    test_frequency=mapping.test_frequency,
                    calibration_data=mapping.calibration_data,
                    is_current=is_current,
                    created_at=mapping.created_at.isoformat() if mapping.created_at else None,
                    updated_at=mapping.updated_at.isoformat() if mapping.updated_at else None,
                )
            )

        return success_response(
            SplMappingListData(
                items=data,
                total=pagination.total,
                page=page,
                per_page=per_page,
                pages=pagination.pages,
            )
        )

    # 获取单个映射详情
    @staticmethod
    def get_one(mapping_id):
        mapping = db.session.get(SPLMapping, mapping_id)
        if not mapping or mapping.deleted:
            return error_response("未找到 SPL 映射记录", code=ErrorCode.NOT_FOUND, http_code=404)

        device = db.session.get(PlaybackDevice, mapping.device_id)

        is_current = False
        if device and device.current_spl_mapping_id == mapping.id:
            is_current = True

        return success_response(
            SplMappingItem(
                id=mapping.id,
                name=mapping.name,
                description=mapping.description,
                device_id=mapping.device_id,
                device={"id": device.id, "name": device.name} if device else None,
                device_name=device.name if device else "未知设备",
                device_model=device.model if device else None,
                device_type=mapping.device_type,
                distance=mapping.distance,
                target_spl=mapping.target_spl,
                digital_gain=mapping.digital_gain,
                calibration_status=mapping.calibration_status,
                test_frequency=mapping.test_frequency,
                calibration_data=mapping.calibration_data,
                is_current=is_current,
                created_at=mapping.created_at.isoformat() if mapping.created_at else None,
                updated_at=mapping.updated_at.isoformat() if mapping.updated_at else None,
            )
        )

    # 获取校准历史
    @staticmethod
    def get_history(mapping_id):
        history = CalibrationHistory.query.filter_by(mapping_id=mapping_id).order_by(CalibrationHistory.created_at.desc()).all()
        data = []
        for h in history:
            data.append(
                SplHistoryItem(
                    id=h.id,
                    calibration_data=h.calibration_data,
                    distance=h.distance,
                    test_frequency=h.test_frequency,
                    created_at=h.created_at.isoformat() if h.created_at else None,
                )
            )
        return success_response(SplHistoryData(items=data, total=len(data)))

    # 获取详细校准数据 (最新)
    @staticmethod
    def get_calibration_data(mapping_id):
        mapping = db.session.get(SPLMapping, mapping_id)
        if not mapping or mapping.deleted:
            return error_response("未找到映射记录", code=ErrorCode.NOT_FOUND, http_code=404)
        return success_response(mapping.calibration_data)

    # 获取 SPL 统计信息
    @staticmethod
    def get_stats():
        try:
            total = SPLMapping.query.filter(SPLMapping.deleted == False).count()
            calibrated = SPLMapping.query.filter_by(calibration_status='calibrated', deleted=False).count()
            uncalibrated = total - calibrated
            associated_devices = db.session.query(SPLMapping.device_id).filter(SPLMapping.deleted == False).distinct().count()

            return success_response(
                SplStatsData(
                    total=total,
                    calibrated=calibrated,
                    uncalibrated=uncalibrated,
                    associated_devices=associated_devices,
                )
            )
        except Exception as e:
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)

    # 按设备ID获取SPL映射列表
    @staticmethod
    def get_by_device(device_id):
        try:
            mappings = SPLMapping.query.filter_by(device_id=device_id, deleted=False).order_by(SPLMapping.created_at.desc()).all()

            data = []
            for mapping in mappings:
                data.append(
                    SplByDeviceItem(
                        id=mapping.id,
                        name=mapping.name,
                        description=mapping.description,
                        device_id=mapping.device_id,
                        device_type=mapping.device_type,
                        distance=mapping.distance,
                        target_spl=mapping.target_spl,
                        calibration_status=mapping.calibration_status,
                        created_at=mapping.created_at.isoformat() if mapping.created_at else None,
                        updated_at=mapping.updated_at.isoformat() if mapping.updated_at else None,
                    )
                )

            return success_response(SplByDeviceData(items=data, total=len(data)))
        except Exception as e:
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)
