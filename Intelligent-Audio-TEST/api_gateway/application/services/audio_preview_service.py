import logging
from pydantic import ValidationError
from api_gateway.infrastructure.request_adapter import request
from shared.models.models import Audio
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.task_utils import has_running_e2e_tasks
from api_gateway.schemas.audio import BatchPlaybackRequest

logger = logging.getLogger(__name__)


class AudioPreviewService:
    # 试听音频 (前端或后端播放)
    @staticmethod
    def preview(audio_id):
        if has_running_e2e_tasks():
            return error_response("当前有待执行的E2E测试任务，不允许使用后端扬声器播放", code=403)

        # 尝试两种可能性：1. 直接作为音频ID查找 2. 作为测试用例ID查找
        try:
            # 1. 首先尝试作为音频ID查找
            audio = db.session.get(Audio, audio_id)

            if not audio or audio.deleted:
                # 2. 如果不是音频ID，尝试作为测试用例ID查找
                from shared.models.models import TestCase
                test_case = db.session.get(TestCase, audio_id)

                if test_case and not test_case.deleted:
                    # 从测试用例配置中提取音频ID
                    config = test_case.config or {}
                    audios = config.get('audios', [])
                    if audios:
                        # 取第一个音频作为预览音频
                        audio_item = audios[0]
                        actual_audio_id = audio_item.get('audio_id')
                        if actual_audio_id:
                            audio = db.session.get(Audio, actual_audio_id)
        except Exception as e:
            import logging
            logging.error(f"Error resolving audio for preview: {str(e)}", exc_info=True)

        if not audio or audio.deleted:
            return error_response("音频不存在", 404)

        try:
            validated = BatchPlaybackRequest.model_validate(request.get_json() or {})
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        playback_device_id = validated.playback_device_id
        playback_device_ids = validated.playback_device_ids or []
        device_unique_ids = validated.device_unique_ids or []

        spl = validated.spl
        offset = validated.offset

        # 统一处理设备ID，确保playback_device_ids是数组
        if playback_device_id:
            playback_device_ids = [playback_device_id] + playback_device_ids

        # 去重
        playback_device_ids = list(set(playback_device_ids))
        device_unique_ids = list(set(device_unique_ids))

        # 无论是否提供设备ID，都使用后端硬件播放
        try:
            # 跨服务调用：通过 gRPC AudioService 调用音频引擎
            from api_gateway.infrastructure.grpc_proxies import audio_service
            from shared.models.models import PlaybackDevice, SPLMapping

            # 设备信息
            device_names = []
            gains = []

            # 确定要使用的设备列表，统一处理所有音频类型
            devices_to_use = []

            if device_unique_ids:
                # 如果前端指定了deviceUniqueIds，使用指定的设备
                for device_uid in device_unique_ids:
                    device = PlaybackDevice.query.filter_by(device_unique_id=device_uid, is_deleted=0).first()
                    if device:
                        devices_to_use.append(device)
            elif playback_device_ids:
                # 兼容旧版，使用playback_device_ids，同时支持扫描设备格式
                for device_id in playback_device_ids:
                    device = None
                    # 扫描设备使用 device_name（字符串），数据库设备使用数字ID
                    if isinstance(device_id, str):
                        # 扫描设备格式：使用 device_unique_id 查询
                        device = PlaybackDevice.query.filter_by(device_unique_id=device_id, is_deleted=0).first()
                    else:
                        # 数据库ID格式：通过主键查询
                        device = db.session.get(PlaybackDevice, device_id)

                    if device and not device.is_deleted:
                        devices_to_use.append(device)
            else:
                # 如果前端没有指定设备，使用默认设备
                default_device = type('obj', (object,), {
                    'name': '默认设备',
                    'device_unique_id': '',
                    'channel_index': 0,
                    'current_spl_mapping_id': None
                })
                devices_to_use.append(default_device)

            # 循环处理所有设备
            for device in devices_to_use:
                device_name = device.name
                device_unique_id = getattr(device, 'device_unique_id', '')
                channel_index = getattr(device, 'channel_index', 0)
                gain = 1.0

                # 计算音量/增益
                if spl and getattr(device, 'current_spl_mapping_id', None):
                    # 通过 gRPC AudioService 计算 SPL 到增益的映射
                    from api_gateway.infrastructure.grpc_proxies import spl_service
                    gain = spl_service.spl_to_gain(device.current_spl_mapping_id, spl)

                # 获取物理设备索引
                device_index = 0
                if device_unique_id:
                    device_index = audio_service.get_device_index(device_unique_id)
                    if device_index is None:
                        continue  # 跳过无法定位的设备，继续处理其他设备

                # 触发播放指令，统一播放器类型命名
                player_type = f'ch_{getattr(device, "id", "default")}'
                audio_service.play_audio(
                    task_id=f"preview_{audio.id}_{getattr(device, 'id', 'default')}",
                    file_path=audio.file_path,
                    device_index=device_index,
                    channel_index=channel_index,
                    gain=gain,
                    player_type=player_type,
                    offset=offset
                )

                device_names.append(device_name)
                gains.append(round(gain, 4))

            if not device_names:
                return error_response("没有找到可用的播放设备", 404)

            # 构建响应，兼容旧版和新版前端
            response_data = {
                "audio": audio.name,
                "duration": audio.duration
            }

            # 兼容旧版前端，保留device和gain字段
            if device_names:
                response_data["device"] = device_names[0]
                response_data["gain"] = gains[0]

            # 新版前端使用devices和gains数组
            response_data["devices"] = device_names
            response_data["gains"] = gains

            return success_response(
                response_data,
                f"已在 {len(device_names)} 个设备上开始试听"
            )
        except Exception as e:
            import logging
            logging.error(f"Audio preview error: {str(e)}", exc_info=True)
            return error_response(f"硬件播放失败: {str(e)}")

    # 停止音频试听
    @staticmethod
    def stop_preview(audio_id):
        try:
            # 跨服务调用：通过 gRPC AudioService 调用音频引擎
            from api_gateway.infrastructure.grpc_proxies import audio_service

            # 解析实际的音频ID（与preview方法相同的逻辑）
            actual_audio_id = audio_id

            try:
                # 1. 首先尝试作为音频ID查找
                audio = db.session.get(Audio, audio_id)

                if not audio or audio.deleted:
                    # 2. 如果不是音频ID，尝试作为测试用例ID查找
                    from shared.models.models import TestCase
                    test_case = db.session.get(TestCase, audio_id)

                    if test_case and not test_case.deleted:
                        # 从测试用例配置中提取音频ID
                        config = test_case.config or {}
                        audios = config.get('audios', [])
                        if audios:
                            # 取第一个音频作为预览音频
                            audio_item = audios[0]
                            resolved_audio_id = audio_item.get('audio_id')
                            if resolved_audio_id:
                                actual_audio_id = resolved_audio_id
            except Exception as e:
                import logging
                logging.error(f"Error resolving audio for stop_preview: {str(e)}", exc_info=True)

            # 构建task_id前缀
            task_id_prefix = f"preview_{actual_audio_id}"

            # 使用前缀匹配所有相关的task_id，而不是精确匹配
            import logging
            logging.debug(f"Stopping preview for audio_id: {audio_id}, actual_audio_id: {actual_audio_id}, task_id_prefix: {task_id_prefix}")
            logging.debug(f"Active players before: {list(audio_service.active_players.keys())}")

            # 遍历所有活跃的播放器，停止所有匹配前缀的任务
            stopped_tasks = []
            for task_id in list(audio_service.active_players.keys()):
                if task_id.startswith(task_id_prefix):
                    audio_service.stop_task_audio(task_id)
                    stopped_tasks.append(task_id)

            logging.debug(f"Active players after: {list(audio_service.active_players.keys())}")
            logging.debug(f"Stopped tasks: {stopped_tasks}")

            if stopped_tasks:
                return success_response(None, f"音频试听已停止，共停止了 {len(stopped_tasks)} 个任务")
            else:
                return success_response(None, f"没有找到正在播放的任务")
        except Exception as e:
            import logging
            logging.error(f"Stop audio preview error: {str(e)}", exc_info=True)
            return error_response(f"停止试听失败: {str(e)}")
