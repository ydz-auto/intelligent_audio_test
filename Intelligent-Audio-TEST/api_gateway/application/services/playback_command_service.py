import logging
import threading
import os

from sqlalchemy import cast, String
from api_gateway.infrastructure.request_adapter import request
from api_gateway.config.config import Config
from shared.models.models import PlaybackDevice
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.log_handler import log_not_emit
from shared.infrastructure.storage import storage
# 跨服务调用：通过 gRPC AudioService 调用音频引擎
from api_gateway.infrastructure.grpc_proxies import AudioService, audio_service
from shared.utils.task_utils import has_running_e2e_tasks
from api_gateway.schemas.common import IdData, StatusData
from api_gateway.schemas.playback import (
    PlaybackTestData,
    PlaybackCreateSchema,
    PlaybackUpdateSchema,
    PlaybackTestSchema,
    PlaybackAssociateSplSchema,
)
from shared.utils.query_utils import now_cst

logger = logging.getLogger(__name__)

# 全局音频服务单例，确保驱动不被重复初始化
audio_service = AudioService()
# 用于存储测试播放的停止事件 {device_id: stop_event}
test_stop_events = {}


class PlaybackCommandService:
    """播放设备写操作 Service（CRUD + 测试播放控制）。"""

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
            from shared.models.models import TestCase
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

        from shared.models.models import SPLMapping
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

            sample_audio = os.path.join(Config.AUDIO_STORAGE_PATH, 'test.wav')

            audio_name = os.path.basename(sample_audio)
            if audio_id:
                from shared.models.models import Audio
                audio = db.session.get(Audio, audio_id)
                if audio and not audio.deleted:
                    try:
                        sample_audio = storage.load_file(audio.file_path)
                        audio_name = audio.name
                    except Exception:
                        pass

            if not os.path.isabs(sample_audio):
                sample_audio = os.path.join(os.getcwd(), sample_audio)

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
                    # 通过 gRPC AudioService 计算 SPL 到增益的映射
                    from api_gateway.infrastructure.grpc_proxies import spl_service
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

            PlaybackCommandService._log(
                level='INFO',
                category='DeviceTest',
                source=f'Device:{device.name}',
                content=f"已启动音频驱动播放: {audio_name}, 设备索引: {device_index}, 通道: {device.channel_index},增益: {round(gain, 4)}",
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
            PlaybackCommandService._log(
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
