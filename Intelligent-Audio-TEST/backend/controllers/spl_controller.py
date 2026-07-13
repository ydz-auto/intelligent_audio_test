from flask import request,current_app
from backend.models.models import SPLMapping, PlaybackDevice, Audio, CalibrationHistory
from backend.models.database import db
from backend.utils.web.response import success_response, error_response
from backend.utils.web.error_codes import ErrorCode
from backend.utils.web.log_handler import log_not_emit
from backend.utils.common.task_utils import has_running_e2e_tasks
from backend.schemas.common import IdData
from backend.schemas.spl import (
    PlayTestToneData,
    SplByDeviceData,
    SplByDeviceItem,
    SplCalibrationResult,
    SplHistoryData,
    SplHistoryItem,
    SplMappingItem,
    SplMappingListData,
    SplStatsData,
    StopTestToneData,
    TestToneDeviceItem,
    SPLMappingQueryRequest,
    SPLMappingCreateRequest,
    SPLMappingUpdateRequest,
    PlayTestToneRequest,
    StopTestToneRequest,
)
from datetime import datetime, timezone, timedelta
from backend.utils.common.query_utils import now_cst
import time

class SPLController:
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
        
        query = SPLMapping.query
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
        if not mapping:
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

    # 创建新的 SPL 映射记录
    @staticmethod
    def create():
        req_data = SPLMappingCreateRequest.model_validate(request.get_json())
        
        device_id = req_data.device_id
        device_type = req_data.device_type
        
        if device_id is None and device_type is None:
            return error_response("必须提供 device_id 或 device_type 之一", code=ErrorCode.INVALID_PARAMS)
        
        try:
            calibration_data = req_data.calibration_data
            calibration_status = req_data.calibration_status

            log_not_emit('DEBUG', 'spl_controller', f'创建映射 - calibration_data: {calibration_data}, calibration_status: {calibration_status}, data: {req_data}', category='spl')
            
            if calibration_data and isinstance(calibration_data, dict) and 'points' in calibration_data:
                valid_points = []
                validation_errors = []
                for i, point in enumerate(calibration_data['points']):
                    if not isinstance(point, dict):
                        continue
                    
                    gain_offset_value = point.get('gainOffset') if point.get('gainOffset') is not None else point.get('gain_offset')
                    digital_gain_value = point.get('digital_gain') if point.get('digital_gain') is not None else point.get('gain')
                    
                    if gain_offset_value is None and digital_gain_value is None:
                        continue
                    
                    if gain_offset_value is None and digital_gain_value is not None:
                        gain_offset_value = (float(digital_gain_value) - 50) * 0.24
                    
                    base_level_value = point.get('baseLevel') if point.get('baseLevel') is not None else point.get('base_level', -30)
                    
                    max_gain_offset = 25
                    if gain_offset_value > max_gain_offset:
                        validation_errors.append(f"增益点 {i+1}: 增益偏移 ({gain_offset_value} dB) 超过最大值 (+{max_gain_offset} dB)，最终电平不能大于 -5 dBFS")
                        gain_offset_value = max_gain_offset
                    
                    normalized_point = {
                        'spl': point.get('spl'),
                        'gainOffset': gain_offset_value,
                        'baseLevel': base_level_value,
                        'finalLevel': -30 + (gain_offset_value if gain_offset_value else 0),
                    }
                    if digital_gain_value is not None:
                        normalized_point['digital_gain'] = digital_gain_value
                    
                    valid_points.append(normalized_point)
                
                if validation_errors:
                    return error_response("; ".join(validation_errors), code=ErrorCode.INVALID_PARAMS)
                
                calibration_data['points'] = valid_points
                
                if len(valid_points) > 0:
                    calibration_status = 'calibrated'
            else:
                calibration_data = {'points': []}
            
            target_spl = req_data.target_spl
            
            if not target_spl and calibration_data and calibration_data['points']:
                target_spl = calibration_data['points'][0]['spl']
            
            digital_gain = None
            
            new_mapping = SPLMapping(
                name=req_data.name,
                description=req_data.description,
                device_id=device_id,
                device_type=device_type,
                distance=req_data.distance or 1.0,
                target_spl=target_spl,
                digital_gain=digital_gain,
                test_frequency=req_data.test_frequency or 1000,
                calibration_status=calibration_status or 'uncalibrated',
                calibration_data=calibration_data
            )
            db.session.add(new_mapping)
            db.session.flush()

            if device_id:
                device = db.session.get(PlaybackDevice, device_id)
                if device:
                    device.current_spl_mapping_id = new_mapping.id
                    log_not_emit('DEBUG', 'spl_controller', f'创建设备 {device_id} 的映射关联: current_spl_mapping_id = {new_mapping.id}', category='spl')
            
            db.session.commit()
            return success_response(IdData(id=new_mapping.id), "SPL 映射记录创建成功", http_code=201)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)

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
        if not mapping:
            return error_response("未找到映射记录", code=ErrorCode.NOT_FOUND, http_code=404)
        return success_response(mapping.calibration_data)

    # 更新 SPL 映射信息
    @staticmethod
    def update(mapping_id):
        mapping = db.session.get(SPLMapping, mapping_id)
        if not mapping:
            return error_response("未找到 SPL 映射记录", code=ErrorCode.NOT_FOUND, http_code=404)
        
        req_data = SPLMappingUpdateRequest.model_validate(request.get_json())
        
        try:
            env_params_changed = False
            distance = req_data.distance
            test_frequency = req_data.test_frequency
            
            if distance is not None and distance != mapping.distance:
                env_params_changed = True
            if test_frequency is not None and test_frequency != mapping.test_frequency:
                env_params_changed = True

            field_map = {
                'name': 'name',
                'description': 'description',
                'device_id': 'device_id',
                'device_type': 'device_type',
                'distance': 'distance',
                'target_spl': 'target_spl',
                'digital_gain': 'digital_gain',
                'test_frequency': 'test_frequency',
                'calibration_status': 'calibration_status'
            }
            
            data = req_data.model_dump(exclude_none=True)
            
            for field_name, attr_name in field_map.items():
                if field_name in data:
                    setattr(mapping, attr_name, data[field_name])
            
            calibration_data = req_data.calibration_data
            if calibration_data is not None:
                if isinstance(calibration_data, dict) and 'points' in calibration_data:
                    valid_points = []
                    validation_errors = []
                    for i, point in enumerate(calibration_data['points']):
                        if not isinstance(point, dict):
                            continue
                        
                        gain_offset_value = point.get('gainOffset') if point.get('gainOffset') is not None else point.get('gain_offset')
                        digital_gain_value = point.get('digital_gain') if point.get('digital_gain') is not None else point.get('gain')
                        
                        if gain_offset_value is None and digital_gain_value is None:
                            continue
                        
                        if gain_offset_value is None and digital_gain_value is not None:
                            gain_offset_value = (float(digital_gain_value) - 50) * 0.24
                        
                        base_level_value = point.get('baseLevel') if point.get('baseLevel') is not None else point.get('base_level', -30)
                        
                        max_gain_offset = 25
                        if gain_offset_value > max_gain_offset:
                            validation_errors.append(f"增益点 {i+1}: 增益偏移 ({gain_offset_value} dB) 超过最大值 (+{max_gain_offset} dB)，最终电平不能大于 -5 dBFS")
                            gain_offset_value = max_gain_offset
                        
                        normalized_point = {
                            'spl': point.get('spl'),
                            'gainOffset': gain_offset_value,
                            'baseLevel': base_level_value,
                            'finalLevel': -30 + (gain_offset_value if gain_offset_value else 0),
                        }
                        if digital_gain_value is not None:
                            normalized_point['digital_gain'] = digital_gain_value
                        
                        valid_points.append(normalized_point)
                    
                    if validation_errors:
                        return error_response("; ".join(validation_errors), code=ErrorCode.INVALID_PARAMS)
                    
                    calibration_data['points'] = valid_points
                    
                    if len(valid_points) > 0:
                        mapping.calibration_status = 'calibrated'
                    mapping.calibration_data = calibration_data
                else:
                    mapping.calibration_data = {'points': []}
            
            if env_params_changed:
                mapping.calibration_status = 'uncalibrated'
                mapping.calibration_data = None

            is_current = req_data.is_current
            new_device_id = req_data.device_id
            
            if new_device_id is not None and new_device_id != mapping.device_id:
                old_device_id = mapping.device_id
                if old_device_id:
                    old_device = db.session.get(PlaybackDevice, old_device_id)
                    if old_device and old_device.current_spl_mapping_id == mapping.id:
                        old_device.current_spl_mapping_id = None
                
                if new_device_id:
                    new_device = db.session.get(PlaybackDevice, new_device_id)
                    if new_device:
                        if is_current or (is_current is None and new_device.current_spl_mapping_id is None):
                            new_device.current_spl_mapping_id = mapping.id
            
            elif is_current is not None:
                device = db.session.get(PlaybackDevice, mapping.device_id)
                if device:
                    if is_current:
                        device.current_spl_mapping_id = mapping.id
                    elif device.current_spl_mapping_id == mapping.id:
                        device.current_spl_mapping_id = None

            mapping.updated_at = now_cst()
            db.session.commit()
            return success_response(None, "SPL 映射记录更新成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)

    # 删除 SPL 映射记录
    @staticmethod
    def delete(mapping_id):
        mapping = db.session.get(SPLMapping, mapping_id)
        if not mapping:
            return error_response("未找到 SPL 映射记录", code=ErrorCode.NOT_FOUND, http_code=404)
        
        try:
            # 清理播放设备中的 current_spl_mapping_id 引用
            if mapping.device_id:
                device = db.session.get(PlaybackDevice, mapping.device_id)
                if device and device.current_spl_mapping_id == mapping.id:
                    device.current_spl_mapping_id = None
                    device.updated_at = now_cst()
            
            # 如果存在多设备关联同一映射的情况（虽然目前逻辑是 1:1 或 N:1），也可以通过 query 清理
            PlaybackDevice.query.filter_by(current_spl_mapping_id=mapping.id).update({
                'current_spl_mapping_id': None,
                'updated_at': now_cst()
            })

            db.session.delete(mapping)
            db.session.commit()
            return success_response(None, "SPL 映射记录已删除")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)
            
    # 执行 SPL 校准流程
    @staticmethod
    def calibrate(mapping_id):
        mapping = db.session.get(SPLMapping, mapping_id)
        if not mapping:
            return error_response("未找到映射记录", code=ErrorCode.NOT_FOUND, http_code=404)
        
        # 1. 环境准备 (略)
        # 2. 模拟自动扫描流程
        try:
            from backend.utils.web.log_handler import log_and_emit
            
            log_and_emit('info', 'SPL_CALIBRATION', f'开始校准映射: {mapping.id} - {mapping.name}', category='spl', task_id=None, device_id=mapping.device_id)
            
            # 模拟扫描不同增益点
            scan_points = []
            for gain in [1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
                # 模拟测量值，假设 Gain 100 时 SPL 为 90dB，Gain 1 时为 40dB，线性增长
                measured_spl = 40 + (gain - 1) * (90 - 40) / (100 - 1)
                scan_points.append({"gain": gain, "spl": round(measured_spl, 2)})
                log_and_emit('info', 'SPL_CALIBRATION', f'校准点测量完成: 增益={gain}, SPL={round(measured_spl, 2)}dB', category='spl', task_id=None, device_id=mapping.device_id)
                time.sleep(0.1) # 模拟测量耗时

            # 3. 数据处理
            mapping.calibration_data = {"points": scan_points}
            mapping.calibration_status = 'calibrated'
            
            # 记录历史
            history = CalibrationHistory(
                mapping_id=mapping.id,
                calibration_data=mapping.calibration_data,
                distance=mapping.distance,
                test_frequency=mapping.test_frequency
            )
            db.session.add(history)
            
            mapping.updated_at = now_cst()
            db.session.commit()
            
            log_and_emit('info', 'SPL_CALIBRATION', f'校准完成: {mapping.id} - {mapping.name}', category='spl', task_id=None, device_id=mapping.device_id)
            
            return success_response(SplCalibrationResult(id=mapping.id, calibration_status=mapping.calibration_status), "校准成功")
        except Exception as e:
            db.session.rollback()
            try:
                from backend.utils.web.log_handler import log_and_emit
                log_and_emit('error', 'SPL_CALIBRATION', f'校准失败: {str(e)}', category='spl', task_id=None, device_id=mapping.device_id)
            except:
                pass
            return error_response(str(e), code=ErrorCode.CALIBRATION_FAILED)

    # 获取 SPL 统计信息
    @staticmethod
    def get_stats():
        try:
            total = SPLMapping.query.count()
            calibrated = SPLMapping.query.filter_by(calibration_status='calibrated').count()
            uncalibrated = total - calibrated
            associated_devices = db.session.query(SPLMapping.device_id).distinct().count()
            
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
            mappings = SPLMapping.query.filter_by(device_id=device_id).order_by(SPLMapping.created_at.desc()).all()
            
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

    # 播放测试音（改为播放指定的音频文件）
    @staticmethod
    def play_test_tone(mapping_id=None):
        if has_running_e2e_tasks():
            return error_response("当前有待执行的E2E测试任务，不允许使用后端扬声器播放", code=ErrorCode.FORBIDDEN)
        
        req_data = PlayTestToneRequest.model_validate(request.get_json() or {})
        
        gain_value = req_data.gain_value or 50
        gain_offset = req_data.gain_offset
        target_spl = req_data.target_spl
        if target_spl is None:
            target_spl = 65
        unique_id_raw = req_data.unique_id
        unique_id = str(unique_id_raw).strip() if unique_id_raw is not None else None
        if unique_id == "":
            unique_id = None
        
        try:
            from backend.services.audio.audio_engine import audio_service
            from backend.models.models import PlaybackDevice
            import wave
            import os
            
            # 使用静态资源路径下的音频文件
            sample_audio = os.path.join(current_app.config.get('AUDIO_STORAGE_PATH'), 'test.wav')
            
            
            if not os.path.exists(sample_audio):
                return error_response(f"音频文件不存在: {sample_audio}", code=ErrorCode.NOT_FOUND)
            
            # 获取音频时长
            with wave.open(sample_audio, 'rb') as wf:
                duration = wf.getnframes() / float(wf.getframerate())
            
            # 使用 -30dBFS 作为标准参考电平
            reference_dbfs = -30.0
            
            # 计算增益偏移 dB
            # 如果提供了 gain_offset，直接使用；否则从 gain_value 计算
            if gain_offset is not None:
                gain_offset_db = float(gain_offset)
            else:
                gain_offset_db = (gain_value - 50) * 0.24
            
            # 最终期望输出电平 = -30dBFS + 增益偏移 dB
            final_dbfs = reference_dbfs + gain_offset_db
            
            # 由于音频引擎内部会自动将音频归一化到 -30dBFS，
            # 这里传入的 linear_gain 应该是相对于 -30dBFS 的线性增益倍数，即直接由 gain_offset_db 算出
            linear_gain = 10 ** (gain_offset_db / 20)
            
            devices_to_use = []
            if unique_id:
                # 从数据库查找设备，而非直接创建对象
                device = PlaybackDevice.query.filter_by(device_unique_id=unique_id, is_deleted=0).first()
                if device:
                    devices_to_use.append(device)
                else:
                    # 如果数据库中找不到，返回错误
                    return error_response(f"找不到设备: {unique_id}", code=ErrorCode.NOT_FOUND)
            else:
                # 如果没有提供 unique_id，从数据库查找设备
                devices = PlaybackDevice.query.filter_by(is_deleted=0).limit(10).all()
                devices_to_use = devices if devices else []
            
            if not devices_to_use:
                # 如果没有可用设备，返回错误
                 return error_response("没有找到可用的播放设备", code=ErrorCode.NOT_FOUND)

            
            results = []
            for device in devices_to_use:
                device_name = getattr(device, 'name', '未知设备')
                device_unique_id = getattr(device, 'device_unique_id', '')
                channel_index = getattr(device, 'channel_index', 0)
                
                final_gain = linear_gain
                
                device_index = 0
                if device_unique_id:
                    device_index = audio_service.get_device_index(device_unique_id)
                    if device_index is None:
                        continue
                
                player_type = f'test_tone_{getattr(device, "id", "default")}'
                audio_service.play_audio(
                    task_id=f"test_tone_{device_index}_{int(target_spl)}",
                    file_path=sample_audio,
                    device_index=device_index,
                    channel_index=channel_index,
                    gain=final_gain,
                    loop=True,
                    player_type=player_type,
                    offset=0
                )
                
                results.append(
                    TestToneDeviceItem(
                        device=device_name,
                        gain_db=round(gain_offset_db, 2),
                        final_dbfs=round(final_dbfs, 2),
                        target_spl=target_spl,
                    )
                )
            
            if not results:
                return error_response("没有找到可用的播放设备", code=ErrorCode.NOT_FOUND)
            
            return success_response(
                PlayTestToneData(devices=results, duration=round(duration, 2)),
                f"测试音频已在 {len(results)} 个设备上播放",
            )
        except Exception as e:
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)
    
    @staticmethod
    def stop_test_tone():
        try:
            req_data = StopTestToneRequest.model_validate(request.get_json() or {})
            
            unique_id_raw = req_data.unique_id
            unique_id = str(unique_id_raw).strip() if unique_id_raw is not None else None
            if unique_id == "":
                unique_id = None
            
            from backend.services.audio.audio_engine import audio_service
            
            if unique_id:
                device_index = audio_service.get_device_index(unique_id)
                if device_index is not None:
                    task_id_pattern = f"test_tone_{device_index}_*"
                    stopped = audio_service.stop_task_audio_by_pattern(task_id_pattern, 'test_tone_*')
                    if stopped > 0:
                        return success_response(StopTestToneData(stopped_count=stopped), f"已停止 {stopped} 个测试音任务")
                    else:
                        return success_response(StopTestToneData(stopped_count=0), "没有正在播放的测试音")
                else:
                    return error_response("设备未找到", code=ErrorCode.NOT_FOUND)
            else:
                stopped = audio_service.stop_task_audio_by_pattern('test_tone_*', 'test_tone_*')
                return success_response(StopTestToneData(stopped_count=stopped), f"已停止 {stopped} 个测试音任务")
        except Exception as e:
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)
