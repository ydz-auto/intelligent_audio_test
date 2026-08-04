import logging
import re

from api_gateway.infrastructure.request_adapter import request
from shared.models.models import PlaybackDevice
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.log_handler import log_not_emit
from shared.utils.query_utils import now_cst
from api_gateway.schemas.playback import (
    PlaybackDeviceItem,
    PlaybackDeviceListData,
    PlaybackScanItem,
    PlaybackStatusItem,
)
# 跨服务调用：通过 gRPC AudioService 调用音频引擎
from api_gateway.infrastructure.grpc_proxies import AudioService, audio_service

logger = logging.getLogger(__name__)


class PlaybackQueryService:
    """播放设备查询读侧 Service。"""

    @staticmethod
    def _log(level, content, task_id=None, test_case_id=None, api_id=None, category='execution', module='Playback', **kwargs):
        """统一日志记录方法"""
        log_not_emit(
            level=level,
            module=module,
            content=content,
            category=category,
            source='backend',
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

    # 检查所有播放设备状态
    @staticmethod
    def check_status():
        try:
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
