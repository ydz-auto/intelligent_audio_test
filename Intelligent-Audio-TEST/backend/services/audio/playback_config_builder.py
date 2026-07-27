"""
播放配置构建器。

从 PlaybackOrchestrator 拆出的配置构建逻辑，包括：
- 干声解析与配置构建
- 噪声配置构建
- 干扰人配置构建
- 预览场景的分类逻辑

所有函数接收 audio_service 和 log_fn 参数，不依赖 PlaybackOrchestrator 实例。
"""

from backend.services.audio.audio_engine import log_not_emit


def _resolve_audio_file_path(audio_info, audio_obj=None):
    """从 audio_info 或 Audio 对象中解析音频文件路径"""
    path = audio_info.get('path') or audio_info.get('file_path')
    if path:
        return path
    if audio_obj and getattr(audio_obj, 'file_path', None):
        return audio_obj.file_path
    return None


def find_device_obj(device_id, devices):
    """在设备列表中按 device_id 或 id 查找设备对象。

    Args:
        device_id: 设备标识（字符串 device_unique_id 或数字主键 id）
        devices: 设备列表，元素可为 dict 或 ORM 对象

    Returns:
        匹配的设备对象，未找到返回 None
    """
    if not devices:
        return None
    for dev in devices:
        # dict 形式
        if isinstance(dev, dict):
            if dev.get('device_id') == device_id or dev.get('id') == device_id:
                return dev
        # ORM 对象形式
        else:
            dev_uid = getattr(dev, 'device_unique_id', None)
            dev_pk = getattr(dev, 'id', None)
            if dev_uid == device_id or dev_pk == device_id:
                return dev
    return None


def resolve_spl_gain(spl_mapping_id, target_spl, app=None):
    """通过 SPL mapping 把声压级转成软件增益。"""
    if not spl_mapping_id:
        return 1.0
    try:
        from backend.services.audio.spl_service import spl_service
        return spl_service.spl_to_gain(spl_mapping_id, target_spl, app=app)
    except Exception:
        return 1.0


def resolve_dry_audios(audios, round_config=None):
    """从 audios 列表解析出 [(audio_config, audio_obj), ...]，仅保留干声。"""
    from backend.models import db
    from backend.models.models import Audio

    result = []
    for audio_config in audios or []:
        audio_id = audio_config.get('audio_id')
        if not audio_id:
            continue
        try:
            audio_obj = db.session.get(Audio, audio_id)
        except Exception:
            audio_obj = None
        if not audio_obj or getattr(audio_obj, 'audio_type', None) == 'noise':
            continue
        result.append((audio_config, audio_obj))

    result.sort(key=lambda x: x[0].get('play_order', 0))
    return result


def build_noise_info(round_config, case_config):
    """解析本轮噪声 audio_info + 噪声设备列表。"""
    from backend.models import db
    from backend.models.models import Audio, PlaybackDevice

    # 兼容 round 级 / case 级
    bg_noise = round_config.get('background_noise') or {}
    if not bg_noise and case_config:
        bg_noise = case_config.get('background_noise') or {}

    noise_audio = None
    noise_spl = 0
    audio_id = bg_noise.get('audio_id')
    if audio_id:
        try:
            noise_audio = db.session.get(Audio, audio_id)
        except Exception:
            noise_audio = None
        noise_spl = bg_noise.get('spl', 0)

    device_ids = bg_noise.get('device_ids') or []
    noise_devices = []
    for did in device_ids:
        dev = None
        try:
            # 字符串既可能是主键 ID 也可能是 device_unique_id，先按主键查，再按 unique_id 查
            if isinstance(did, str):
                # 先尝试作为主键 ID 查询（若为纯数字字符串）
                try_num = int(did)
                dev = db.session.get(PlaybackDevice, try_num)
                if dev and getattr(dev, 'is_deleted', 0):
                    dev = None
                if not dev:
                    dev = PlaybackDevice.query.filter_by(
                        device_unique_id=did, is_deleted=0
                    ).first()
            else:
                dev = db.session.get(PlaybackDevice, did)
        except (ValueError, TypeError):
            # 非数字字符串，按 device_unique_id 查
            try:
                dev = PlaybackDevice.query.filter_by(
                    device_unique_id=did, is_deleted=0
                ).first()
            except Exception:
                dev = None
        except Exception:
            dev = None
        if dev:
            noise_devices.append(dev)

    if noise_audio and noise_devices:
        return ({'spl': noise_spl, 'audio_id': getattr(noise_audio, 'id', None)},
                noise_audio), noise_devices
    return None, noise_devices


def build_dry_configs(dry_audios_info, audio_service, task_id=None):
    """
    构建主讲人 audio_to_play 配置。

    playback_device_id 指向 PlaybackDevice 表主键，直接从 DB 加载 ORM 对象。

    Returns:
        (configs, playback_devices_map)
    """
    from backend.models import db
    from backend.models.models import PlaybackDevice

    playback_devices_map = {}
    configs = []

    for audio_config, audio_obj in dry_audios_info:
        file_path = getattr(audio_obj, 'file_path', None) or audio_config.get('file_path')
        if not file_path:
            continue

        playback_dev_id = audio_config.get('playback_device_id')
        if not playback_dev_id:
            continue

        # 从 DB 加载 PlaybackDevice ORM 对象
        dev_obj = None
        try:
            dev_obj = db.session.get(PlaybackDevice, playback_dev_id)
        except Exception:
            dev_obj = None
        if not dev_obj:
            _log('WARNING',
                 f'主讲人音频 (audio_id={audio_config.get("audio_id")}) '
                 f'播放设备 (id={playback_dev_id}) 未找到，跳过',
                 task_id=task_id)
            continue

        dev_id = dev_obj.id if hasattr(dev_obj, 'id') else dev_obj.get('id')
        dev_unique_id = (
            dev_obj.device_unique_id if hasattr(dev_obj, 'device_unique_id')
            else dev_obj.get('device_unique_id')
        )
        channel_index = (
            dev_obj.channel_index if hasattr(dev_obj, 'channel_index')
            else dev_obj.get('channel_index', 0)
        )
        spl_mapping_id = (
            dev_obj.current_spl_mapping_id if hasattr(dev_obj, 'current_spl_mapping_id')
            else dev_obj.get('current_spl_mapping_id')
        )
        device_index = audio_service.get_device_index(dev_unique_id) if dev_unique_id else None
        if device_index is None:
            _log('WARNING',
                 f'主讲人音频 (audio_id={audio_config.get("audio_id")}) '
                 f'无法获取设备索引 (unique_id={dev_unique_id})，跳过',
                 task_id=task_id)
            continue

        gain = resolve_spl_gain(spl_mapping_id, audio_config.get('spl', 65.0))

        if dev_id not in playback_devices_map:
            playback_devices_map[dev_id] = {
                'device_obj': dev_obj,
                'device_index': device_index,
                'channel_index': channel_index,
                'gain': 1.0,
                'name': dev_obj.name if hasattr(dev_obj, 'name') else dev_obj.get('name', ''),
                'current_spl_mapping_id': spl_mapping_id,
            }

        configs.append({
            'file': file_path,
            'device_index': device_index,
            'channel': channel_index,
            'gain': gain,
            'offset': 0,
            'duration': getattr(audio_obj, 'duration', 0) or 0,
            'play_order': audio_config.get('play_order', 0),
            'loop': False,
            'is_noise': False,
            'type': 'dry',
            'audio_id': audio_config.get('audio_id'),
        })

    return configs, playback_devices_map


def build_noise_play_configs(noise_audio_info, noise_devices, audio_service):
    """构建噪声 audio_to_play 配置列表。"""
    if not noise_audio_info or not noise_devices:
        return []

    n_config, n_audio = noise_audio_info
    file_path = (
        n_audio.file_path if hasattr(n_audio, 'file_path') else n_audio.get('file_path')
    )
    noise_spl = n_config.get('spl', 60) if n_config else 60

    configs = []
    for n_dev in noise_devices:
        dev_unique_id = (
            n_dev.device_unique_id if hasattr(n_dev, 'device_unique_id')
            else n_dev.get('device_unique_id')
        )
        channel_index = (
            n_dev.channel_index if hasattr(n_dev, 'channel_index')
            else n_dev.get('channel_index', 0)
        )
        spl_mapping_id = (
            n_dev.current_spl_mapping_id if hasattr(n_dev, 'current_spl_mapping_id')
            else n_dev.get('current_spl_mapping_id')
        )
        n_gain = resolve_spl_gain(spl_mapping_id, noise_spl)
        device_index = audio_service.get_device_index(dev_unique_id) if dev_unique_id else None
        if device_index is None:
            continue

        configs.append({
            'file': file_path,
            'device_index': device_index,
            'channel': channel_index,
            'gain': n_gain,
            'offset': 0,
            'duration': getattr(n_audio, 'duration', 0) or 0,
            'play_order': 0,
            'loop': True,
            'is_noise': True,
            'type': 'noise',
        })

    return configs


def build_interferer_configs(task_id, interferer_config, audio_service):
    """
    构建干扰人 audio_to_play 配置。

    语义：
    - type='interferer'：不参与主讲人交叠时间轴
    - is_noise=False：音频类型为人声
    - loop：控制是否循环播放（独立字段）
    - delay：保留 startDelay（ms 转 s）
    """
    if not interferer_config:
        return []

    from backend.models import db
    from backend.models.models import Audio, PlaybackDevice

    audio_to_play = []

    for idx, interferer in enumerate(interferer_config):
        if not isinstance(interferer, dict):
            continue

        # 兼容两种存储结构：
        # - 嵌套（前端 syncStructuredFields 生成）：{audio:{id,name}, device:{id}, start_delay, ...}
        # - 扁平（algorithm_params 独立列原样存储）：{audio_id, audio_name, playback_device_id, start_delay, ...}
        audio_info = interferer.get('audio')
        device_cfg = interferer.get('device')
        if not audio_info:
            _aid = interferer.get('audio_id')
            if _aid:
                audio_info = {
                    'id': _aid,
                    'name': interferer.get('audio_name') or '',
                }
        if not device_cfg:
            _did = interferer.get('playback_device_id')
            if _did:
                device_cfg = {'id': _did}

        spl = interferer.get('spl')
        # start_delay 兼容：嵌套结构里是毫秒，扁平结构里是秒
        start_delay_raw = interferer.get('start_delay', 0)
        loop = interferer.get('loop', False)

        if not audio_info or not device_cfg:
            _log('WARNING',
                 f'干扰人 {idx} 配置不完整 (缺少 audio 或 device)，跳过',
                 task_id=task_id)
            continue

        # device_cfg.id 指向 PlaybackDevice 主键，直接从 DB 加载
        playback_dev_id = device_cfg.get('id')
        dev_obj = None
        try:
            dev_obj = db.session.get(PlaybackDevice, playback_dev_id)
        except Exception:
            dev_obj = None
        if not dev_obj:
            _log('WARNING',
                 f'干扰人 {idx} 播放设备 (id={playback_dev_id}, name={device_cfg.get("name")}) 未找到，跳过',
                 task_id=task_id)
            continue

        device_unique_id = getattr(dev_obj, 'device_unique_id', None)
        channel_index = getattr(dev_obj, 'channel_index', 0)
        device_index = (
            audio_service.get_device_index(device_unique_id) if device_unique_id else None
        )
        if device_index is None:
            _log('WARNING',
                 f'干扰人 {idx} 无法获取设备索引 (unique_id={device_unique_id})，跳过',
                 task_id=task_id)
            continue

        spl_mapping_id = getattr(dev_obj, 'current_spl_mapping_id', None)
        gain = resolve_spl_gain(spl_mapping_id, spl) if spl_mapping_id and spl else 1.0

        file_path = _resolve_audio_file_path(audio_info)
        if not file_path and audio_info.get('id'):
            try:
                audio_obj = db.session.get(Audio, audio_info['id'])
                if audio_obj:
                    file_path = audio_obj.file_path
            except Exception:
                pass

        if not file_path:
            _log('WARNING',
                 f'干扰人 {idx} 音频文件路径为空，跳过',
                 task_id=task_id)
            continue

        # 判断单位：嵌套结构（syncStructuredFields）的 startDelay 是毫秒，扁平结构是秒
        # 启发式：> 100 认为是毫秒，否则是秒
        if start_delay_raw > 100:
            delay_s = start_delay_raw / 1000.0
        else:
            delay_s = start_delay_raw

        audio_to_play.append({
            'file': file_path,
            'device_index': device_index,
            'channel': channel_index,
            'gain': gain,
            'delay': delay_s,
            'loop': bool(loop),
            'is_noise': False,
            'type': 'interferer',
        })

    if audio_to_play:
        _log('INFO',
             f'构建了 {len(audio_to_play)} 个干扰人音频配置',
             task_id=task_id)

    return audio_to_play


def prepare_preview_playback_info(audio_configs, case_config):
    """为 preview 场景分类干声/噪声音频及设备。"""
    from backend.models import db
    from backend.models.models import Audio, PlaybackDevice

    dry_audios_info = []
    noise_case_audio_info = None

    for audio_config in audio_configs or []:
        audio_id = audio_config.get('audio_id')
        if not audio_id:
            continue
        try:
            audio = db.session.get(Audio, audio_id)
        except Exception:
            audio = None
        if not audio:
            continue
        if getattr(audio, 'audio_type', None) == 'noise':
            noise_case_audio_info = (audio_config, audio)
        else:
            dry_audios_info.append((audio_config, audio))

    if not dry_audios_info:
        return [], None, [], []

    dry_audios_info.sort(key=lambda x: x[0].get('play_order', 0))

    device_ids_seen = set()
    dry_devices = []
    for audio_config, _ in dry_audios_info:
        pid = audio_config.get('playback_device_id')
        if pid and pid not in device_ids_seen:
            try:
                dev = db.session.get(PlaybackDevice, pid)
            except Exception:
                dev = None
            if dev:
                dry_devices.append(dev)
                device_ids_seen.add(pid)

    noise_audio = None
    noise_spl = 0
    if noise_case_audio_info:
        n_ca, n_audio = noise_case_audio_info
        noise_audio = n_audio
        noise_spl = n_ca.get('spl', 0)
    elif case_config and case_config.get('background_noise', {}).get('audio_id'):
        bg = case_config['background_noise']
        try:
            noise_audio = db.session.get(Audio, bg['audio_id'])
        except Exception:
            noise_audio = None
        noise_spl = bg.get('spl', 0)

    device_ids = []
    if case_config:
        device_ids = (case_config.get('background_noise') or {}).get('device_ids', [])

    all_noise_devices = []
    for did in device_ids:
        try:
            if isinstance(did, str):
                dev = PlaybackDevice.query.filter_by(
                    device_unique_id=did, is_deleted=0
                ).first()
            else:
                dev = db.session.get(PlaybackDevice, did)
        except Exception:
            dev = None
        if dev:
            all_noise_devices.append(dev)

    noise_audio_info = None
    if noise_audio and all_noise_devices:
        noise_audio_info = (
            {'spl': noise_spl, 'audio_id': getattr(noise_audio, 'id', None)},
            noise_audio,
        )

    return dry_audios_info, noise_audio_info, dry_devices, all_noise_devices


def extract_overlap_rate(case_config):
    if not case_config:
        return 0
    try:
        from backend.utils.algorithm.case_parameter_extractor import CaseParameterExtractor
        return CaseParameterExtractor.get_overlap_rate(case_config)
    except Exception:
        return 0


def extract_overlap_time(case_config):
    if not case_config:
        return 0
    try:
        from backend.utils.algorithm.case_parameter_extractor import CaseParameterExtractor
        return CaseParameterExtractor.get_overlap_time(case_config)
    except Exception:
        return 0


def _log(level, content, task_id=None, **kwargs):
    log_not_emit(level, 'playback_orchestrator', content, task_id=task_id, category='audio')
