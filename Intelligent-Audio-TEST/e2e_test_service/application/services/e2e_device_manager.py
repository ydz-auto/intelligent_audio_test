"""E2E 设备管理：设备查询、初始化、预处理、后处理、环境设备

所有 gRPC 调用委托给 infrastructure/acl/ 下的 ACL 仓储。
"""
import time
import threading

from e2e_test_service.infrastructure.acl import (
    AudioAclRepositoryImpl,
    DeviceAclRepositoryImpl,
    EnvDeviceAclRepositoryImpl,
    TaskDataAclRepositoryImpl,
)


class E2EDeviceManager:
    """E2E 设备管理器"""

    def __init__(self, executor):
        self._executor = executor
        self._device_repo = DeviceAclRepositoryImpl()
        self._audio_repo = AudioAclRepositoryImpl()
        self._task_data_repo = TaskDataAclRepositoryImpl()

    @property
    def _log(self):
        return self._executor._log

    def get_device_info(self, task_id, case_config):
        """查询任务关联的设备，组装 device_info_list"""
        # 通过 ACL 仓储查询 TaskDevice 关联记录
        task_device_relations = self._task_data_repo.get_task_devices(task_id)
        device_ids = [rel.device_id for rel in task_device_relations if rel.device_id]
        if not device_ids:
            return {'success': False, 'error': "没有可用的测试设备"}

        # 通过 ACL 仓储查询 device_service 的设备数据
        device_repo = DeviceAclRepositoryImpl()
        devices = device_repo.get_devices_by_ids(device_ids)

        device_info_list = []
        for dev in devices:
            # driver 对象不再跨进程返回，仅保留设备元数据
            # 驱动操作（initialize/pre_process/post_process/teardown）通过 gRPC CreateDriver(action=...) 调用
            prompt_path, prompt_name = self._get_prompt_audio_info(
                dev.needs_prompt_audio, dev.prompt_config
            )
            device_info_list.append({
                "device_id": dev.id, "device_sn": dev.serial_number or dev.ip,
                "device_name": dev.name, "system": dev.system,
                "keywords": dev.keywords,
                "prompt_audio_path": prompt_path, "prompt_audio_name": prompt_name,
                "needs_prompt_audio": dev.needs_prompt_audio
            })

        return {'success': True, 'data': {'device_info_list': device_info_list}}

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

        # 通过 ACL 仓储查询 audio_service 的提示音频
        audio_repo = AudioAclRepositoryImpl()
        audio = audio_repo.get_prompt_audio(int(audio_id))
        if audio:
            return audio.file_path, audio.name
        return None, None

    def initialize_devices(self, device_info_list, task_id, test_case_id=None, **kwargs):
        """并行初始化所有设备（通过 gRPC DeviceService.CreateDriver action=initialize）"""
        extra_params = {}
        round_algo_params = kwargs.pop('round_algo_params', None)
        if round_algo_params:
            extra_params.update(round_algo_params)

        pool = self._executor.execution_engine.device_control_pool
        results = []
        lock = threading.Lock()
        futures = []

        def init_device(info):
            ok = False
            err = None
            try:
                ok = self._device_repo.create_driver(task_id, [{
                'action': 'initialize',
                'system': info.get('system'),
                'keywords': info.get('keywords'),
                'device_sn': info.get('device_sn'),
                'test_case_id': test_case_id,
                'kwargs': extra_params,
                }])
                if not ok:
                    err = "Initialize returned False（常见根因：hypium/devicetest 包未安装 → UiDriver=None → 无法获取驱动，详见驱动层日志）"
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
        """并行预处理设备（通过 gRPC DeviceService.CreateDriver action=pre_process）

        Returns:
            bool: 所有设备预处理是否全部成功；任一失败返回 False
        """
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
            future = pool.submit(
                self._device_repo.create_driver,
                task_id,
                [{
                    'action': 'pre_process',
                    'device_sn': info.get('device_sn'),
                    'test_case_id': test_case_id,
                    'kwargs': extra_params,
                }],
            )
            futures.append(future)
        success = True
        for future in futures:
            try:
                future.result(timeout=60)
            except Exception as e:
                success = False
                self._log(level='ERROR', content=f"设备预处理失败: {e}", task_id=task_id, test_case_id=test_case_id)
        return success

    def post_process_devices(self, device_info_list, task_id, test_case_id=None, **kwargs):
        """并行后处理设备（通过 gRPC DeviceService.CreateDriver action=post_process）

        Returns:
            bool: 所有设备后处理是否全部成功；任一失败返回 False
        """
        extra_params = kwargs.get('extra_params', {})
        pool = self._executor.execution_engine.device_control_pool
        futures = []
        for info in device_info_list:
            future = pool.submit(
                self._device_repo.create_driver,
                task_id,
                [{
                    'action': 'post_process',
                    'device_sn': info.get('device_sn'),
                    'test_case_id': test_case_id,
                    'kwargs': extra_params,
                }],
            )
            futures.append(future)
        success = True
        for future in futures:
            try:
                future.result(timeout=300)
            except Exception as e:
                success = False
                self._log(level='ERROR', content=f"设备后处理失败: {e}", task_id=task_id, test_case_id=test_case_id)
        return success

    def teardown_devices(self, device_info_list, task_id, test_case_id=None, **kwargs):
        """并行 teardown 所有设备驱动（通过 gRPC DeviceService.CreateDriver action=teardown）

        Returns:
            bool: 所有设备 teardown 是否全部成功；任一失败返回 False
        """
        extra_params = kwargs.get('extra_params', {})
        pool = self._executor.execution_engine.device_control_pool
        futures = []
        for info in device_info_list:
            future = pool.submit(
                self._device_repo.create_driver,
                task_id,
                [{
                    'action': 'teardown',
                    'device_sn': info.get('device_sn'),
                    'test_case_id': test_case_id,
                    'kwargs': extra_params,
                }],
            )
            futures.append(future)
        success = True
        for future in futures:
            try:
                future.result(timeout=60)
            except Exception as e:
                success = False
                self._log(level='ERROR', content=f"设备 teardown 失败: {e}", task_id=task_id, test_case_id=test_case_id)
        return success

    def play_prompt_audio(self, device_info_list, task_id, device_index, playback_dev, main_gain):
        """播放提示音频"""
        prompt_info = next((info for info in device_info_list if info["prompt_audio_path"]), None)
        if prompt_info:
            # 通过 ACL 仓储播放音频
            self._audio_repo.play_audio(
                task_id=task_id, file_path=prompt_info["prompt_audio_path"],
                device_index=device_index, channel_index=playback_dev.channel_index if playback_dev else 0,
                gain=main_gain, player_type='dry'
            )

    def setup_env_devices_for_round(self, round_algo_params, task_id):
        """设置本轮环境设备（导轨等），返回状态列表供 teardown 恢复。"""
        _ENV_DEVICE_PARAM_MAP = {
            'rail_distance': ('rail', lambda v: {'distance_cm': float(v)}),
        }

        env_states = []
        for param_key, (device_type, build_settings) in _ENV_DEVICE_PARAM_MAP.items():
            value = round_algo_params.get(param_key)
            if value is None:
                continue
            try:
                # 通过 ACL 仓储控制环境设备
                dev = EnvDeviceAclRepositoryImpl(device_type)
                if dev.is_available():
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
