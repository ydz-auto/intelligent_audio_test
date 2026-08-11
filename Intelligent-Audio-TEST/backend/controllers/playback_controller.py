from flask import request, current_app
from sqlalchemy import cast, String
from backend.models.models import PlaybackDevice
from backend.models.database import db
from backend.utils.web.response import success_response, error_response
from backend.utils.web.log_handler import log_not_emit
from backend.services.audio.audio_engine import AudioService
from backend.utils.common.task_utils import has_running_e2e_tasks
from backend.schemas.common import IdData, StatusData
from backend.schemas.playback import PlaybackDeviceItem, PlaybackDeviceListData, PlaybackScanItem, PlaybackStatusItem, PlaybackTestData
from backend.schemas.playback import PlaybackCreateSchema, PlaybackUpdateSchema, PlaybackTestSchema, PlaybackAssociateSplSchema
from datetime import datetime, timezone, timedelta
from backend.utils.common.query_utils import now_cst
import threading
import logging
import os

logger = logging.getLogger(__name__)

# 导入全局app实例，用于在线程中创建应用上下文
from backend.app import app

# 全局音频服务单例，确保驱动不被重复初始化
audio_service = AudioService()
# 用于存储测试播放的停止事件 {device_id: stop_event}
test_stop_events = {}

class PlaybackController:
    @staticmethod
    def _log(level, content, task_id=None, test_case_id=None, api_id=None, category='execution', module='Playback', **kwargs):
        """统一日志记录方法"""
        log_not_emit(
            level=level,
            module=module,
            content=content,
            category=category,
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs
        )

    # 获取所有播放设备
    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        keyword = request.args.get('keyword')
        device_type = request.args.get('type')

        query = PlaybackDevice.query.filter_by(is_deleted=0)

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
        devices = pagination.items

        data = []
        for device in devices:
            data.append(
                PlaybackDeviceItem(
                    id=device.id,
                    name=device.name,
                    model=device.model,
                    device_type=device.device_type,
                    sample_rate=device.sample_rate,
                    channel_index=device.channel_index,
                    device_unique_id=device.device_unique_id,
                    description=device.description,
                    status=device.status,
                    current_spl_mapping_id=device.current_spl_mapping_id,
                    created_at=device.created_at.isoformat() if device.created_at else None,
                    updated_at=device.updated_at.isoformat() if device.updated_at else None,
                )
            )
        
        return success_response(
            PlaybackDeviceListData(
                items=data,
                total=pagination.total,
                page=pagination.page,
                per_page=pagination.per_page,
                pages=pagination.pages,
            )
        )

    # 获取单个播放设备详情
    @staticmethod
    def get_one(device_id):
        device = PlaybackDevice.query.filter_by(id=device_id, is_deleted=0).first()
        if not device:
            return error_response("未找到播放设备", 404)
        
        return success_response(
            PlaybackDeviceItem(
                id=device.id,
                name=device.name,
                model=device.model,
                device_type=device.device_type,
                sample_rate=device.sample_rate,
                channel_index=device.channel_index,
                device_unique_id=device.device_unique_id,
                description=device.description,
                status=device.status,
                current_spl_mapping_id=device.current_spl_mapping_id,
                created_at=device.created_at.isoformat() if device.created_at else None,
                updated_at=device.updated_at.isoformat() if device.updated_at else None,
            )
        )

    @staticmethod
    def scan():
        """扫描可用的物理播放通道，并过滤掉已注册的设备"""
        try:
            # 1. 获取物理设备列表
            physical_devices = audio_service.get_all_physical_devices()
            
            # 2. 获取已注册的设备 (根据 unique_id 和 channel_index 组合判断)
            registered = PlaybackDevice.query.filter_by(is_deleted=0).all()
            registered_keys = set([f"{d.device_unique_id}_{d.channel_index}" for d in registered])
            
            # 3. 过滤出未注册的设备
            scanned_results = []
            for dev in physical_devices:
                key = f"{dev['unique_id']}_{dev['channel_index']}"
                if key not in registered_keys:
                    scanned_results.append(
                        PlaybackScanItem(
                            name=dev['name'],
                            model=f"Hardware Channel ({dev['host_api']})",
                            device_unique_id=dev['unique_id'],
                            channel_index=dev['channel_index'],
                            sample_rate=dev['sample_rate'],
                            type="dry",
                            status="online",
                        )
                    )
            
            return success_response(scanned_results, f"成功扫描到 {len(scanned_results)} 个新通道")
        except Exception as e:
            return error_response(f"扫描失败: {str(e)}")

    # 添加新的播放设备
    @staticmethod
    def create():
        json_data = request.get_json(silent=True)
        if json_data is None:
            return error_response("请求正文必须是有效的 JSON 格式且不能为空", 400)
        
        try:
            validated_data = PlaybackCreateSchema.model_validate(json_data)
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)
        
        try:
            device_unique_id = validated_data.device_unique_id
            channel_index = validated_data.channel_index
            
            existing_device = PlaybackDevice.query.filter_by(
                device_unique_id=device_unique_id,
                channel_index=channel_index
            ).first()
            
            if existing_device:
                if existing_device.is_deleted == 1:
                    existing_device.is_deleted = 0
                    existing_device.name = validated_data.name
                    existing_device.model = validated_data.model
                    existing_device.device_type = validated_data.device_type
                    existing_device.sample_rate = validated_data.sample_rate
                    existing_device.description = validated_data.description
                    existing_device.status = validated_data.status
                    existing_device.updated_at = now_cst()
                    
                    db.session.commit()
                    return success_response(IdData(id=existing_device.id), "已恢复已删除的播放设备", http_code=201)
                else:
                    return error_response("该播放设备已存在！请检查设备唯一标识和通道索引。")
            
            new_device = PlaybackDevice(
                name=validated_data.name,
                model=validated_data.model,
                device_type=validated_data.device_type,
                sample_rate=validated_data.sample_rate,
                channel_index=channel_index,
                device_unique_id=device_unique_id,
                description=validated_data.description,
                status=validated_data.status
            )
            db.session.add(new_device)
            db.session.commit()
            return success_response(IdData(id=new_device.id), "播放设备添加成功", http_code=201)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 更新播放设备信息
    @staticmethod
    def update(device_id):
        device = db.session.get(PlaybackDevice, device_id)
        if not device:
            return error_response("未找到播放设备", 404)

        json_data = request.get_json(silent=True)
        if json_data is None:
            return error_response("请求正文必须是有效的 JSON 格式且不能为空", 400)

        try:
            validated_data = PlaybackUpdateSchema.model_validate(json_data)
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        try:
            validated_dict = validated_data.model_dump(by_alias=True, exclude_none=True)
            
            for json_key, attr_name in [
                ('name', 'name'),
                ('model', 'model'),
                ('deviceType', 'device_type'),
                ('sampleRate', 'sample_rate'),
                ('channelIndex', 'channel_index'),
                ('deviceUniqueId', 'device_unique_id'),
                ('description', 'description'),
                ('status', 'status'),
                ('currentSplMappingId', 'current_spl_mapping_id')
            ]:
                if json_key in validated_dict:
                    setattr(device, attr_name, validated_dict[json_key])
            
            device.updated_at = now_cst()
            db.session.commit()
            return success_response(None, "播放设备信息更新成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 删除播放设备
    @staticmethod
    def delete(device_id):
        device = PlaybackDevice.query.filter_by(id=device_id, is_deleted=0).first()
        if not device:
            return error_response("未找到播放设备", 404)

        try:
            # 检查关联解除：在 test_case.config.audios 中，若有引用此播放设备的配置，提示用户
            from backend.models.models import TestCase
            usage_count = TestCase.query.filter(
                TestCase.deleted == False,
                cast(TestCase.config, String).like(f'%"playback_device_id": "{device_id}"%')
            ).count()
            if usage_count > 0:
                return error_response(f"无法删除：该设备正被 {usage_count} 个测试用例配置引用，请先修改相关配置", 400)

            # 逻辑删除
            device.is_deleted = 1
            device.updated_at = now_cst()
            db.session.commit()
            return success_response(None, "播放设备已删除 (逻辑删除)")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 关联 SPL 映射
    @staticmethod
    def associate_spl(device_id):
        device = db.session.get(PlaybackDevice, device_id)
        if not device:
            return error_response("未找到播放设备", 404)

        json_data = request.get_json(silent=True)
        if json_data is None:
            return error_response("请求正文必须是有效的 JSON 格式且不能为空", 400)

        try:
            validated_data = PlaybackAssociateSplSchema.model_validate(json_data)
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        spl_mapping_id = validated_data.spl_mapping_id
        
        from backend.models.models import SPLMapping
        mapping = db.session.get(SPLMapping, spl_mapping_id)
        if not mapping:
            return error_response("未找到 SPL 映射记录", 404)

        if mapping.device_id and mapping.device_id != device_id:
            return error_response(f"SPL 映射设备不匹配: 映射属于设备 ID {mapping.device_id}", 400)
        
        if mapping.device_type and mapping.device_type != device.device_type:
            return error_response(f"SPL 映射类型不匹配: 映射类型为 {mapping.device_type}, 设备类型为 {device.device_type}", 400)

        try:
            device.current_spl_mapping_id = spl_mapping_id
            device.updated_at = now_cst()
            db.session.commit()
            return success_response(None, "SPL 映射关联成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 测试播放设备
    @staticmethod
    def test(device_id):
        if has_running_e2e_tasks():
            return error_response("当前有待执行的E2E测试任务，不允许使用后端扬声器播放", 403)
        
        device = db.session.get(PlaybackDevice, device_id)
        if not device:
            return error_response("未找到播放设备", 404)
        
        json_data = request.get_json(silent=True) or {}
        try:
            validated_data = PlaybackTestSchema.model_validate(json_data)
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)
        
        try:
            audio_id = validated_data.audio_id
            spl = validated_data.spl
            
            sample_audio = os.path.join(current_app.config.get('AUDIO_STORAGE_PATH'), 'test.wav')
            
            audio_name = os.path.basename(sample_audio)
            if audio_id:
                from backend.models.models import Audio
                audio = db.session.get(Audio, audio_id)
                if audio and not audio.deleted and os.path.exists(audio.file_path):
                    sample_audio = audio.file_path
                    audio_name = audio.name
            
            if not os.path.isabs(sample_audio):
                sample_audio = os.path.join(app.root_path,  sample_audio)
            
            if not os.path.exists(sample_audio):
                return error_response(f"音频文件不存在: {sample_audio}。请先确保音频文件存在。")

            device_index = audio_service.get_device_index(device.device_unique_id)
            if device_index is None:
                device.status = "offline"
                db.session.commit()
                return error_response(f"无法定位物理设备: {device.device_unique_id}，设备已标记为离线")
            
            if device.status != "online":
                device.status = "online"
                db.session.commit()
            
            gain = 1.0
            if spl and device.current_spl_mapping_id:
                try:
                    from backend.services.audio.spl_service import spl_service
                    gain = spl_service.spl_to_gain(device.current_spl_mapping_id, spl)
                except Exception:
                    pass

            task_id = f"test_{device_id}"
            player_type = device.device_type or 'dry'
            
            audio_service.play_audio(
                task_id=task_id,
                file_path=sample_audio,
                device_index=device_index,
                channel_index=device.channel_index,
                gain=gain,
                loop=True,
                player_type=player_type
            )
            
            stop_event = threading.Event()
            test_stop_events[device_id] = stop_event

            PlaybackController._log(
                level='INFO',
                category='DeviceTest',
                content=f"已启动音频驱动播放: {audio_name}, Device:{device.name},设备索引: {device_index}, 通道: {device.channel_index},增益: {round(gain, 4)}",
                playback_device_id=device_id
            )

            return success_response(
                PlaybackTestData(
                    device=device.name,
                    audio=audio_name,
                    status="testing",
                    device_index=device_index,
                    channel_index=device.channel_index,
                    gain=round(gain, 4),
                ),
                f"已在设备 {device.name} 上开始测试播放",
            )
        except Exception as e:
            db.session.rollback()
            logging.error(f"Device test error: {str(e)}", exc_info=True)
            return error_response(f"测试播放失败: {str(e)}")

    # 停止测试
    @staticmethod
    def stop_test(device_id):
        device = db.session.get(PlaybackDevice, device_id)
        if not device:
            return error_response("未找到播放设备", 404)
        
        try:
            # 1. 安全地获取请求体数据（如果需要）
            # 使用silent=True避免JSON解析错误
            data = request.get_json(silent=True) or {}
            
            # 2. 使用与play_audio相同的task_id格式停止播放
            # 格式：preview_{audio_id} 或 test_{device_id}
            task_id = f"test_{device_id}"
            
            # 3. 调用audio_service停止任务音频
            audio_service.stop_task_audio(task_id)
            
            # 4. 触发本地停止事件（兼容原有逻辑）
            stop_event = test_stop_events.get(device_id)
            if stop_event:
                stop_event.set()
                test_stop_events.pop(device_id, None)
            
            # 5. 写入日志
            PlaybackController._log(
                level='INFO',
                category='DeviceTest',
                source=f'Device:{device.name}',
                content=f"测试播放已手动停止",
                playback_device_id=device_id
            )

            return success_response(StatusData(id=device.id, status="online"), "测试音播放已停止")
        except Exception as e:
            db.session.rollback()
            logging.error(f"Stop device test error: {str(e)}", exc_info=True)
            return error_response(f"停止测试失败: {str(e)}")
    
    # 检查所有播放设备状态
    @staticmethod
    def check_status():
        try:
            import re
            
            def normalize_unique_id(uid):
                """规范化设备唯一标识，移除动态枚举索引"""
                if not uid:
                    return uid
                # 匹配 (数字- 设备名) 格式，移除数字和短横线
                # 例如: "Analog (3+4) (2- RME Fireface UCX II) [Ch 1]" -> "Analog (3+4) (RME Fireface UCX II) [Ch 1]"
                return re.sub(r'\((\d+)-\s+', '(', uid)
            
            # 获取所有播放设备，确保包含所有设备
            devices = PlaybackDevice.query.filter_by(is_deleted=0).all()
            
            # 获取所有物理设备列表（已过滤为Windows WASAPI设备）
            physical_devices = audio_service.get_all_physical_devices()
            
            results = []
            current_time = now_cst()
            
            # 创建一个字典，用于存储每个设备应该更新的状态
            device_status_map = {}
            
            # 创建一个映射，用于快速查找物理设备信息
            # 同时保存原始unique_id和规范化后的unique_id
            physical_device_info = {dev['unique_id']: dev['device_index'] for dev in physical_devices}
            # 添加规范化后的映射
            for dev in physical_devices:
                normalized = normalize_unique_id(dev['unique_id'])
                if normalized != dev['unique_id']:
                    physical_device_info[normalized] = dev['device_index']
            
            physical_device_ids = set(physical_device_info.keys())
            log_not_emit('DEBUG', 'playback_controller', f'Physical devices: {physical_device_ids}', category='playback')
            
            # 遍历所有设备，检查是否在线
            for device in devices:
                # 先尝试精确匹配
                device_unique_id = device.device_unique_id
                is_online = device_unique_id in physical_device_ids
                
                # 如果精确匹配失败，尝试规范化匹配
                if not is_online:
                    normalized_id = normalize_unique_id(device_unique_id)
                    log_not_emit('DEBUG', 'playback_controller', f'Trying normalized match: {normalized_id}', category='playback')
                    is_online = normalized_id in physical_device_ids
                    if is_online:
                        device_unique_id = normalized_id
                
                log_not_emit('DEBUG', 'playback_controller', f'Checking device: {device.device_unique_id}, is online: {is_online}', category='playback')
                
                # 获取设备索引（仅当设备在线时）
                device_index = physical_device_info.get(device_unique_id)
                
                # 确定新状态
                new_status = "online" if is_online else "offline"
                
                # 保存设备ID和对应的新状态
                device_status_map[device.id] = new_status
                
                results.append(
                    PlaybackStatusItem(
                        id=device.id,
                        name=device.name,
                        unique_id=device.device_unique_id,
                        status=new_status,
                        device_index=device_index,
                    )
                )
            
            # 批量提交更新，提高性能
            if device_status_map:
                updated_count = 0
                try:
                    # 逐个更新每个设备的状态
                    for device_id, new_status in device_status_map.items():
                        update_device = db.session.get(PlaybackDevice, device_id)
                        if update_device:
                            update_device.status = new_status
                            update_device.updated_at = current_time
                            updated_count += 1
                    
                    # 提交事务
                    db.session.commit()
                except Exception as commit_error:
                    db.session.rollback()
                    logging.error(f"提交设备状态更新时出错: {str(commit_error)}", exc_info=True)
            
            return success_response(results, "设备状态检查完成")
        except Exception as e:
            db.session.rollback()
            logging.error(f"检查设备状态时出错: {str(e)}", exc_info=True)
            return error_response(str(e))
