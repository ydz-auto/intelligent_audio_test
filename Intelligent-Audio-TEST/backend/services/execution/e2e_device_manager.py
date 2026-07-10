"""E2E 设备管理：设备查询、初始化、预处理、后处理、环境设备"""
import time
import threading

from backend.models.models import Audio, Device, TaskDevice
from backend.models.database import db
from backend.services.audio.audio_engine import audio_service
from backend.utils.device_driver import device_driver_factory


class E2EDeviceManager:
    """E2E 设备管理器"""

    def __init__(self, executor):
        self._executor = executor

    @property
    def _log(self):
        return self._executor._log

    def get_device_info(self, task_id, case_config):
        """查询任务关联的设备，组装 device_info_list"""
        local_db_session = db.session()
        try:
            task_device_relations = local_db_session.query(TaskDevice).filter_by(task_id=task_id).all()
            device_ids = [rel.device_id for rel in task_device_relations]
            if not device_ids:
                return {'success': False, 'error': "没有可用的测试设备"}
            devices = local_db_session.query(Device).filter(Device.id.in_(device_ids)).all()

            device_info_list = []
            for dev in devices:
                driver = device_driver_factory.get_driver(dev.system, keywords=dev.keywords)
                prompt_path, prompt_name = self._get_prompt_audio_info(
                    dev.needs_prompt_audio, dev.prompt_config
                )
                device_info_list.append({
                    "device_id": dev.id, "device_sn": dev.serial_number or dev.ip,
                    "device_name": dev.name, "driver": driver,
                    "prompt_audio_path": prompt_path, "prompt_audio_name": prompt_name,
                    "needs_prompt_audio": dev.needs_prompt_audio
                })

            return {'success': True, 'data': {'device_info_list': device_info_list}}
        finally:
            local_db_session.close()

    def _get_prompt_audio_info(self, needs_prompt_audio, prompt_config):
        """获取提示音频信息 — 直接从 prompt_config 读取音频 ID"""
        if not needs_prompt_audio or not prompt_config:
            return None, None

        audio_id = None
        if isinstance(prompt_config, dict):
            for v in prompt_config.values():
                if v:
                    audio_id = v
                    break
        elif isinstance(prompt_config, (int, str)):
            audio_id = prompt_config

        if not audio_id:
            return None, None

        local_db_session = db.session()
        try:
            audio = local_db_session.query(Audio).filter(
                Audio.id == audio_id,
                Audio.deleted == False,
                Audio.audio_type == 'prompt'
            ).first()
            if audio:
                return audio.file_path, audio.name
            return None, None
        finally:
            local_db_session.close()

    def initialize_devices(self, device_info_list, task_id, test_case_id=None, **kwargs):
        """并行初始化所有设备"""
        algorithm_type = kwargs.get('algorithm_type', 'translation')
        extra_params = self._executor._execute_extra_params(algorithm_type, kwargs, include_format_strings=True)

        pool = self._executor.execution_engine.device_control_pool
        results = []
        lock = threading.Lock()
        futures = []

        def init_device(info):
            ok = False
            err = None
            try:
                if info["driver"]:
                    ok = info["driver"].initialize(info["device_sn"], task_id=task_id, test_case_id=test_case_id, **extra_params)
                    if not ok:
                        err = "Initialize returned False"
                else:
                    err = "Driver not available"
            except Exception as e:
                err = str(e)
            with lock:
                results.append({'success': ok, 'error': err, 'device_name': info["device_name"]})

        for info in device_info_list:
            future = pool.submit(init_device, info)
            futures.append(future)

        for future in futures:
            try:
                future.result(timeout=60)
            except Exception as e:
                self._log(level='ERROR', content=f"设备初始化超时或失败: {e}", task_id=task_id, test_case_id=test_case_id)

        failed = [r for r in results if not r['success']]
        if failed:
            raise RuntimeError(f"设备初始化失败: {'; '.join([f'{r.get('device_name')}: {r.get('error')}' for r in failed])}")

    def pre_process_devices(self, device_info_list, task_id, test_case_id=None, **kwargs):
        """并行预处理设备（启动录音 / 进入待录状态）"""
        extra_params = kwargs.get('extra_params', {})
        record_start_time = time.time()
        self._executor._playback_timestamps[task_id] = {
            'record_start_time': record_start_time,
            'audio_play_times': [],
            'theory_offsets': {}
        }
        pool = self._executor.execution_engine.device_control_pool
        futures = []
        for info in device_info_list:
            if info["driver"]:
                future = pool.submit(
                    info["driver"].pre_process,
                    info["device_sn"],
                    task_id=task_id,
                    test_case_id=test_case_id,
                    **extra_params
                )
                futures.append(future)
        for future in futures:
            try:
                future.result(timeout=60)
            except Exception as e:
                self._log(level='ERROR', content=f"设备预处理失败: {e}", task_id=task_id, test_case_id=test_case_id)

    def post_process_devices(self, device_info_list, task_id, test_case_id=None, **kwargs):
        """并行后处理设备"""
        extra_params = kwargs.get('extra_params', {})
        pool = self._executor.execution_engine.device_control_pool
        futures = []
        for info in device_info_list:
            if info["driver"] and hasattr(info["driver"], "post_process"):
                future = pool.submit(
                    info["driver"].post_process,
                    info["device_sn"],
                    task_id=task_id,
                    test_case_id=test_case_id,
                    **extra_params
                )
                futures.append(future)
        for future in futures:
            try:
                future.result(timeout=60)
            except Exception as e:
                self._log(level='ERROR', content=f"设备后处理失败: {e}", task_id=task_id, test_case_id=test_case_id)

    def play_prompt_audio(self, device_info_list, task_id, device_index, playback_dev, main_gain):
        """播放提示音频"""
        prompt_info = next((info for info in device_info_list if info["prompt_audio_path"]), None)
        if prompt_info:
            future = audio_service.play_audio(
                task_id=task_id, file_path=prompt_info["prompt_audio_path"],
                device_index=device_index, channel_index=playback_dev.channel_index if playback_dev else 0,
                gain=main_gain, player_type='dry'
            )
            try:
                future.result()
            except Exception as e:
                self._log(level='ERROR', content=f"提示音播放失败: {e}", task_id=task_id)

    def setup_env_devices_for_round(self, round_algo_params, task_id):
        """设置本轮环境设备（导轨等），返回状态列表供 teardown 恢复。"""
        from backend.utils.env_device import EnvDeviceFactory

        _ENV_DEVICE_PARAM_MAP = {
            'railDistance': ('rail', lambda v: {'distance_cm': float(v)}),
        }

        env_states = []
        for param_key, (device_type, build_settings) in _ENV_DEVICE_PARAM_MAP.items():
            value = round_algo_params.get(param_key)
            if value is None:
                continue
            try:
                dev = EnvDeviceFactory.create(device_type)
                if dev and dev.is_available():
                    state = dev.setup(build_settings(value))
                    env_states.append((dev, state))
                    self._log(level='INFO', content=f"环境设备 {device_type} 已设置: {param_key}={value}", task_id=task_id)
            except Exception as e:
                self._log(level='WARNING', content=f"环境设备 {device_type} 设置失败: {e}", task_id=task_id)
        return env_states

    def teardown_env_devices_for_round(self, env_states, task_id):
        """恢复本轮环境设备到 setup 前的状态。"""
        for dev, state in env_states:
            try:
                dev.teardown(state)
            except Exception as e:
                self._log(level='WARNING', content=f"环境设备 {dev.device_type} 恢复失败: {e}", task_id=task_id)
