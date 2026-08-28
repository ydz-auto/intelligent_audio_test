"""
播放配置构建器。

从 PlaybackOrchestrator 拆出的配置构建逻辑，包括：
- 干声解析与配置构建
- 噪声配置构建
- 干扰人配置构建
- 预览场景的分类逻辑

所有函数接收 audio_service 和 log_fn 参数，不依赖 PlaybackOrchestrator 实例。
"""

from shared.utils.log_handler import log_not_emit

import logging

logger = logging.getLogger(__name__)


def _get_playback_device_via_grpc(device_id):
    """通过 ACL 仓储从 device_service 获取 PlaybackDevice 数据（返回 dict 或 None）。

    PlaybackDevice 归属 device_service，audio_service 不再直连 PO。
    """
    try:
        from audio_service.infrastructure.acl.playback_acl_repository import (
            PlaybackConfigACLRepositoryImpl,
        )
        _playback_acl = PlaybackConfigACLRepositoryImpl()
        return _playback_acl.get_playback_device(device_id)
    except Exception:
        return None


def _find_playback_device_by_unique_id(device_unique_id):
    """通过 ACL 仓储 ListPlaybackDevices 按 device_unique_id 查找（返回 dict 或 None）。"""
    try:
        from audio_service.infrastructure.acl.playback_acl_repository import (
            PlaybackConfigACLRepositoryImpl,
        )
        _playback_acl = PlaybackConfigACLRepositoryImpl()
        return _playback_acl.find_playback_device_by_unique_id(device_unique_id)
    except Exception:
        return None


def _resolve_audio_file_path(audio_info, audio_obj=None):
    """从 audio_info 或 Audio 对象中解析音频文件路径"""
    path = audio_info.get('path') or audio_info.get('file_path')
    if path:
        return path
    if audio_obj and getattr(audio_obj, 'file_path', None):
        return audio_obj.file_path
    return None


def _resolve_preloaded_path(audio_local_paths, audio_id, target_rate):
    """从预下载嵌套映射解析本地路径。

    映射结构: {audio_id: {target_rate: local_path, "original": local_path}}
    gRPC JSON 往返后 key 为字符串，故同时兼容 int/str 形式的 audio_id 与 target_rate。

    Returns:
        本地文件路径字符串，未命中返回 None。
    """
    if not audio_local_paths or audio_id is None:
        return None
    # 外层：audio_id 可能是 int 或 str
    paths = audio_local_paths.get(audio_id)
    if paths is None:
        paths = audio_local_paths.get(str(audio_id))
    if not paths:
        return None
    # 内层：target_rate 精确匹配（兼容 int/str）
    if target_rate is not None:
        hit = paths.get(target_rate)
        if hit is None:
            hit = paths.get(str(target_rate))
        if hit:
            return hit
    # 原始文件兜底（缓存 miss 时回退原文件，播放侧运行时重采样）
    return paths.get('original') or paths.get(None) or paths.get('null')


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
        from audio_service.infrastructure.audio.spl_service import spl_service
        return spl_service.spl_to_gain(spl_mapping_id, target_spl, app=app)
    except Exception:
        return 1.0


def resolve_dry_audios(audios, round_config=None):
    """从 audios 列表解析出 [(audio_config, audio_obj), ...]，仅保留干声。"""
    from audio_service.infrastructure.persistence.audio_repository import AudioRepository
    _repo = AudioRepository()

    result = []
    for audio_config in audios or []:
        audio_id = audio_config.get('audio_id')
        if not audio_id:
            continue
        try:
            audio_obj = _repo.get_audio(audio_id)
        except Exception:
            audio_obj = None
        if not audio_obj or getattr(audio_obj, 'audio_type', None) == 'noise':
            continue
        result.append((audio_config, audio_obj))

    result.sort(key=lambda x: x[0].get('play_order', 0))
    return result


def _find_playback_device_by_name(dev_name):
    """通过 ACL 仓储 ListPlaybackDevices 按 name 查找（返回 dict 或 None）。"""
    try:
        from audio_service.infrastructure.acl.playback_acl_repository import (
            PlaybackConfigACLRepositoryImpl,
        )
        _playback_acl = PlaybackConfigACLRepositoryImpl()
        return _playback_acl.find_playback_device_by_name(dev_name)
    except Exception:
        return None


def _find_audio_by_name(audio_name):
    """通过 AudioRepository 按 name/original_filename 查找音频对象。"""
    try:
        from audio_service.infrastructure.persistence.audio_repository import AudioRepository
        _repo = AudioRepository()
        return _repo.find_audio_by_name(audio_name)
    except Exception:
        return None


def build_noise_info(round_config, case_config):
    """解析本轮噪声 audio_info + 噪声设备列表。

    优先级：case 级（整个用例）背景噪声 > round 级（轮次内）背景噪声。
    当 case 级存在且有效时，round 级背景噪声不播放。
    """
    from audio_service.infrastructure.persistence.audio_repository import AudioRepository
    _repo = AudioRepository()

    def _resolve_bg_noise(bg_noise):
        """解析单个 background_noise 配置块，返回 (noise_audio, noise_spl, noise_devices)。"""
        if not bg_noise:
            return None, 0, []

        noise_audio = None
        noise_spl = bg_noise.get('spl', 0) or 0
        audio_id = bg_noise.get('audio_id')
        if audio_id:
            try:
                noise_audio = _repo.get_audio(audio_id)
            except Exception:
                noise_audio = None
        # 兼容统一标注文件：audio 字段为文件名（字符串），按 name/original_filename 查库
        if not noise_audio:
            _audio_name = bg_noise.get('audio') or bg_noise.get('audio_name') or ''
            if _audio_name:
                try:
                    noise_audio = _repo.find_audio_by_name(_audio_name)
                except Exception:
                    noise_audio = None

        # 兼容两种设备字段：device_ids（ID 列表）或 playback_device_names（名称列表）
        device_ids = bg_noise.get('device_ids') or []
        device_names = bg_noise.get('playback_device_names') or bg_noise.get('device_names') or []
        # 单设备兼容：playback_device_name（单个字符串）
        if not device_names:
            _single_name = bg_noise.get('playback_device_name') or bg_noise.get('device_name')
            if _single_name:
                device_names = [_single_name]
        noise_devices = []
        for did in device_ids:
            dev = None
            try:
                if isinstance(did, str):
                    # 先尝试作为主键 ID 查询（若为纯数字字符串）
                    try_num = int(did)
                    dev = _get_playback_device_via_grpc(try_num)
                    if dev and dev.get('is_deleted'):
                        dev = None
                    if not dev:
                        dev = _find_playback_device_by_unique_id(did)
                else:
                    dev = _get_playback_device_via_grpc(did)
            except (ValueError, TypeError):
                dev = _find_playback_device_by_unique_id(did)
            except Exception:
                dev = None
            if dev:
                noise_devices.append(dev)
        # 按设备名查表
        for dev_name in device_names:
            if not dev_name:
                continue
            try:
                dev = _find_playback_device_by_name(dev_name)
                if dev:
                    noise_devices.append(dev)
            except Exception:
                pass

        return noise_audio, noise_spl, noise_devices

    # 优先 case 级（整个用例）背景噪声；不存在时回退 round 级（轮次内）背景噪声
    case_bg = case_config.get('background_noise') if case_config else None
    if case_bg:
        noise_audio, noise_spl, noise_devices = _resolve_bg_noise(case_bg)
        if noise_audio and noise_devices:
            return ({'spl': noise_spl, 'audio_id': getattr(noise_audio, 'id', None)},
                    noise_audio), noise_devices

    # round 级背景噪声
    round_bg = round_config.get('background_noise')
    noise_audio, noise_spl, noise_devices = _resolve_bg_noise(round_bg)
    if noise_audio and noise_devices:
        return ({'spl': noise_spl, 'audio_id': getattr(noise_audio, 'id', None)},
                noise_audio), noise_devices
    return None, noise_devices


def build_dry_configs(dry_audios_info, audio_service, task_id=None, audio_local_paths=None):
    """
    构建主讲人 audio_to_play 配置。

    playback_device_id 指向 PlaybackDevice 表主键，直接从 DB 加载 ORM 对象。

    Args:
        audio_local_paths: 准备阶段预下载的 {audio_id: {target_rate: local_path}} 嵌套映射，
            有映射时按设备 target_rate 取本地文件，不再走 OSS。

    Returns:
        (configs, playback_devices_map)
    """
    from audio_service.infrastructure.persistence.audio_repository import AudioRepository
    _repo = AudioRepository()

    playback_devices_map = {}
    configs = []

    for audio_config, audio_obj in dry_audios_info:
        audio_id = audio_config.get('audio_id')
        playback_dev_id = audio_config.get('playback_device_id')
        if not playback_dev_id:
            continue

        # 通过 gRPC 从 device_service 获取 PlaybackDevice 数据
        dev_obj = _get_playback_device_via_grpc(playback_dev_id)
        if not dev_obj:
            _log('WARNING',
                 f'主讲人音频 (audio_id={audio_id}) '
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
                 f'主讲人音频 (audio_id={audio_id}) '
                 f'无法获取设备索引 (unique_id={dev_unique_id})，跳过',
                 task_id=task_id)
            continue

        # 优先使用预下载的本地路径（嵌套映射，按设备 target_rate 查询）
        target_rate = audio_service.get_device_sample_rate(dev_unique_id) if dev_unique_id else None
        file_path = _resolve_preloaded_path(audio_local_paths, audio_id, target_rate)
        if not file_path:
            file_path = getattr(audio_obj, 'file_path', None) or audio_config.get('file_path')
        if not file_path:
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


def build_noise_play_configs(noise_audio_info, noise_devices, audio_service,
                             audio_local_paths=None):
    """构建噪声 audio_to_play 配置列表。"""
    if not noise_audio_info or not noise_devices:
        return []

    n_config, n_audio = noise_audio_info
    noise_audio_id = n_config.get('audio_id') if n_config else None
    # 不同噪声设备可能采样率不同，按设备 target_rate 取本地文件
    fallback_file_path = (
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

        # 优先使用预下载的本地路径（嵌套映射，按设备 target_rate 查询）
        target_rate = audio_service.get_device_sample_rate(dev_unique_id) if dev_unique_id else None
        file_path = _resolve_preloaded_path(audio_local_paths, noise_audio_id, target_rate) or fallback_file_path

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


def build_interferer_configs(task_id, interferer_config, audio_service,
                             audio_local_paths=None):
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

    from audio_service.infrastructure.persistence.audio_repository import AudioRepository
    _repo = AudioRepository()

    audio_to_play = []

    for idx, interferer in enumerate(interferer_config):
        if not isinstance(interferer, dict):
            continue

        # 兼容两种存储结构：
        # - 嵌套（前端 syncStructuredFields 生成）：{audio:{id,name}, device:{id}, start_delay, ...}
        # - 扁平（algorithm_params 独立列原样存储）：{audio_id, audio_name, playback_device_id, start_delay, ...}
        # - 扁平名称（统一标注文件导入）：{audio:"文件名.wav", playback_device_name:"设备名", spl, ...}
        audio_info = interferer.get('audio')
        device_cfg = interferer.get('device')
        # 字符串 audio（文件名）不是嵌套结构，需走扁平分支
        if not isinstance(audio_info, dict):
            audio_info = None
        if not isinstance(device_cfg, dict):
            device_cfg = None
        if not audio_info or not audio_info.get('id') and not audio_info.get('name'):
            _aid = interferer.get('audio_id')
            _aname = interferer.get('audio_name') or ''
            # 兼容统一标注文件的 audio 字段（文件名字符串）
            if not _aid and not _aname and isinstance(interferer.get('audio'), str):
                _aname = interferer.get('audio')
            if _aid or _aname:
                audio_info = {
                    'id': _aid,
                    'name': _aname,
                }
        if not device_cfg or not device_cfg.get('id'):
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

        # 通过 gRPC 从 device_service 获取 PlaybackDevice 数据
        playback_dev_id = device_cfg.get('id')
        dev_obj = _get_playback_device_via_grpc(playback_dev_id)
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

        # 优先使用预下载的本地路径（嵌套映射，按设备 target_rate 查询）
        interferer_audio_id = audio_info.get('id') or audio_info.get('audio_id')
        target_rate = audio_service.get_device_sample_rate(device_unique_id) if device_unique_id else None
        file_path = _resolve_preloaded_path(audio_local_paths, interferer_audio_id, target_rate)
        if not file_path:
            file_path = _resolve_audio_file_path(audio_info)
            if not file_path and audio_info.get('id'):
                try:
                    audio_obj = _repo.get_audio(audio_info['id'])
                    if audio_obj:
                        file_path = audio_obj.file_path
                except Exception:
                    logger.debug("通过仓储查询干扰人音频文件路径失败: audio_id=%s", audio_info.get('id'), exc_info=True)

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
    from audio_service.infrastructure.persistence.audio_repository import AudioRepository
    _repo = AudioRepository()

    dry_audios_info = []
    noise_case_audio_info = None

    for audio_config in audio_configs or []:
        audio_id = audio_config.get('audio_id')
        if not audio_id:
            continue
        try:
            audio = _repo.get_audio(audio_id)
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
            dev = _get_playback_device_via_grpc(pid)
            if dev:
                dry_devices.append(dev)
                device_ids_seen.add(pid)

    noise_audio = None
    noise_spl = 0
    if noise_case_audio_info:
        n_ca, n_audio = noise_case_audio_info
        noise_audio = n_audio
        noise_spl = n_ca.get('spl', 0)
    elif case_config and case_config.get('background_noise'):
        bg = case_config['background_noise']
        audio_id = bg.get('audio_id')
        if audio_id:
            try:
                noise_audio = _repo.get_audio(audio_id)
            except Exception:
                noise_audio = None
        # 兼容文件名
        if not noise_audio:
            _audio_name = bg.get('audio') or bg.get('audio_name') or ''
            if _audio_name:
                try:
                    noise_audio = _repo.find_audio_by_name(_audio_name)
                except Exception:
                    noise_audio = None
        noise_spl = bg.get('spl', 0)

    device_ids = []
    device_names = []
    if case_config:
        bg = case_config.get('background_noise') or {}
        device_ids = bg.get('device_ids', [])
        device_names = bg.get('playback_device_names') or bg.get('device_names') or []
        if not device_names:
            _single = bg.get('playback_device_name') or bg.get('device_name')
            if _single:
                device_names = [_single]

    all_noise_devices = []
    for did in device_ids:
        try:
            if isinstance(did, str):
                dev = _find_playback_device_by_unique_id(did)
            else:
                dev = _get_playback_device_via_grpc(did)
        except Exception:
            dev = None
        if dev:
            all_noise_devices.append(dev)
    for dev_name in device_names:
        if not dev_name:
            continue
        try:
            dev = _find_playback_device_by_name(dev_name)
            if dev:
                all_noise_devices.append(dev)
        except Exception:
            pass

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
        from audio_service.infrastructure.acl.algorithm_acl_repository import (
            AlgorithmACLRepositoryImpl,
        )
        _algo_acl = AlgorithmACLRepositoryImpl()
        params = _algo_acl.normalize_algorithm_params(case_config.get('algorithm_params', {}))
        value = params.get('overlap_rate', 0)
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0


def extract_overlap_time(case_config):
    if not case_config:
        return 0
    try:
        from audio_service.infrastructure.acl.algorithm_acl_repository import (
            AlgorithmACLRepositoryImpl,
        )
        _algo_acl = AlgorithmACLRepositoryImpl()
        params = _algo_acl.normalize_algorithm_params(case_config.get('algorithm_params', {}))
        value = params.get('overlap_time', 0)
        return max(0.0, float(value))
    except Exception:
        return 0


def _log(level, content, task_id=None, **kwargs):
    log_not_emit(level, 'playback_orchestrator', content, task_id=task_id, category='audio')
