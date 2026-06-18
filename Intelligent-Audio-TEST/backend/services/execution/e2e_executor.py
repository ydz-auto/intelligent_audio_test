import json
import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from backend.models.models import Audio, PlaybackDevice, Device, TaskCase, TaskDevice, PromptAudioRelation, TestResult, TestResultDimension, Dimension, utc8now
from backend.models.database import db
from backend.services.audio.audio_engine import audio_service
from backend.services.audio.spl_service import spl_service
from backend.utils.device_driver import device_driver_factory, register_task_events
from backend.utils.algorithm.field_mapper import get_field_mapper
from backend.services.execution.base_executor import BaseExecutor

E2E_RESULT_COLLECTION_WAIT_TIME = float(os.environ.get('E2E_RESULT_COLLECTION_WAIT_TIME', '3.0'))


class E2EExecutor(BaseExecutor):
    def __init__(self, execution_engine):
        super().__init__(execution_engine)
        self._playback_timestamps = {}
        
    def execute_e2e_case(self, task_id, tc_rel_id):
        """
        执行E2E测试用例
        """
        # 记录方法开始执行
        self._log(
            level='DEBUG',
            content=f"E2E用例执行方法开始: task_id={task_id}, tc_rel_id={tc_rel_id}",
            task_id=task_id
        )
        
        # 验证参数
        if not task_id or not tc_rel_id:
            error_msg = "任务ID和测试用例关联ID不能为空"
            self._log(
                level='ERROR',
                content=f"E2E 用例执行失败: {error_msg}",
                task_id=task_id
            )
            # 如果有tc_rel_id，更新状态为失败
            if tc_rel_id:
                self._update_tc_rel_status(
                    tc_rel_id, 
                    execution_status='failed',
                    status='failed',
                    error_message=error_msg
                )
            return False
        
        # 获取基础数据
        data_result = self._validate_and_get_data(task_id, tc_rel_id)
        if not data_result['success']:
            error_msg = data_result.get('error', '获取基础数据失败')
            # 更新状态为失败
            self._update_tc_rel_status(
                tc_rel_id, 
                execution_status='failed',
                status='failed',
                error_message=error_msg
            )
            return False
        
        data = data_result['data']
        
        # rounds-as-top-level 执行
        return self._execute_e2e_with_rounds(task_id, tc_rel_id, data)
    
    def _execute_e2e_with_rounds(self, task_id, tc_rel_id, data):
        """
        新格式执行：支持多轮（rounds）的 E2E 执行
        每轮独立设置设备环境、播放音频、收集结果
        """
        case_name = data['case_name']
        case_config = data['case_config']
        case_reference_params = data.get('case_reference_params', [])
        test_case_id = data['test_case_id']
        algorithm_type = data.get('algorithm_type', 'translation')
        tc_rel_id = data['tc_rel_id']
        
        field_mapper = get_field_mapper()
        case_fields = field_mapper.get_case_fields(algorithm_type)
        
        case_field_values = {}
        for config_key in case_fields.keys():
            case_field_values[config_key] = data.get(config_key)
        
        self.current_case_field_values = case_field_values
        self.current_test_case_id = test_case_id
        self._thread_ctx.current_test_case_id = test_case_id
        
        rounds = case_config.get('rounds', [])
        
        try:
            self._log(
                level='INFO',
                content=f"开始执行E2E用例（rounds格式，共{len(rounds)}轮）: {case_name}",
                task_id=task_id,
                test_case_id=test_case_id
            )
            
            self._handle_control(task_id)
            self._update_tc_rel_status(tc_rel_id, execution_status='running')
            
            stop_event, pause_event = self._get_control_events(task_id)
            register_task_events(task_id, stop_event, pause_event)
            
            # ── 循环外：一次性设备准备 ──
            device_result = self._get_device_info(task_id, case_config)
            if not device_result['success']:
                error_msg = f"设备信息获取失败: {device_result.get('error')}"
                self._log(level='ERROR', content=error_msg, task_id=task_id, test_case_id=test_case_id)
                self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message=error_msg)
                return False
            
            device_info_list = device_result['data']['device_info_list']
            
            self.current_extra_params = self._execute_extra_params(algorithm_type, case_field_values, include_format_strings=True)
            
            device_driver_factory.register_task_devices(task_id, device_info_list)
            
            for info in device_info_list:
                if info.get("driver"):
                    info["driver"].set_task_id(task_id)
                    info["driver"].set_test_case_id(test_case_id)
                    info["driver"].set_device_id(info["device_id"])
            
            self._initialize_devices(device_info_list, task_id, test_case_id=test_case_id, algorithm_type=algorithm_type)
            
            # 声纹注册（循环前一次性执行）
            voiceprint_config = case_config.get('voiceprint_config', {})
            if voiceprint_config.get('enabled'):
                if not self._register_voiceprint(task_id, case_config, device_info_list):
                    self._log(level='ERROR', content='声纹注册失败，中止测试', task_id=task_id, test_case_id=test_case_id)
                    self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message='声纹注册失败')
                    return False
            
            # ── 多轮循环 ──
            all_round_results = []
            last_adjusted_ref_params = None
            
            for round_idx, round_config in enumerate(rounds):
                if not isinstance(round_config, dict):
                    continue
                
                round_number = round_config.get('roundNumber', round_idx + 1)
                
                self.execution_engine.update_case_round_progress(
                    task_id, tc_rel_id, round_idx, len(rounds)
                )
                
                self._log(
                    level='INFO',
                    content=f"执行第 {round_number} 轮",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
                
                # 合并 round_config 到临时 config（供 prepare_audio_playback_info 使用）
                round_case_config = case_config.copy()
                round_case_config['audios'] = round_config.get('audios', [])
                round_case_config['background_noise'] = round_config.get('backgroundNoise')
                if round_config.get('algorithmParams'):
                    round_case_config['algorithm_params'] = round_config['algorithmParams']
                
                # 处理本轮音频配置
                from backend.services.audio.audio_engine import prepare_audio_playback_info
                local_db_session = db.session()
                try:
                    audios = round_case_config.get('audios', [])
                    e2e_audios = [audio for audio in audios if audio.get('audio_id')]
                    if not e2e_audios:
                        self._log(level='WARNING', content=f"第 {round_number} 轮未配置有效音频，跳过", task_id=task_id, test_case_id=test_case_id)
                        continue
                    
                    playback_info = prepare_audio_playback_info(e2e_audios, round_case_config, local_db_session)
                    if not playback_info:
                        self._log(level='WARNING', content=f"第 {round_number} 轮没有可用的干声音频，跳过", task_id=task_id, test_case_id=test_case_id)
                        continue
                    
                    dry_audios_info = playback_info['dry_audios_info']
                    dry_devices = playback_info['dry_devices']
                    noise_audio_info = playback_info['noise_audio_info']
                    noise_devices = playback_info['noise_devices']
                    
                    if not dry_audios_info:
                        continue
                    
                    main_audio_config = dry_audios_info[0][0]
                    playback_dev = dry_devices[0] if dry_devices else None
                    if not playback_dev:
                        continue
                finally:
                    local_db_session.close()
                
                # 提取本轮算法参数
                from backend.utils.algorithm.case_parameter_extractor import _normalize_algorithm_params
                round_algo_params = _normalize_algorithm_params(round_config.get('algorithmParams', []))
                
                # 导轨控制
                rail_distance = round_algo_params.get('railDistance')
                rail_controller = None
                if rail_distance is not None:
                    try:
                        from backend.utils.env_device.rail import RailEnvDevice
                        rail_controller = RailEnvDevice()
                        if rail_controller.is_available():
                            rail_controller.move_rail(float(rail_distance))
                            self._log(level='INFO', content=f"导轨已移动到 {rail_distance}cm", task_id=task_id)
                        else:
                            rail_controller = None
                    except Exception as e:
                        self._log(level='WARNING', content=f"导轨控制失败: {e}", task_id=task_id)
                        rail_controller = None
                
                # 构建干扰人音频配置（如有）
                interferer_audio_configs = self._build_interferer_configs(
                    task_id, round_config.get('interferers', []), device_info_list
                )
                
                # pre_process（含音量设置）
                volume_level = round_algo_params.get('volumeLevel')
                original_volumes = {}
                if volume_level is not None:
                    for info in device_info_list:
                        driver = info.get('driver')
                        device_sn = info.get('device_sn')
                        if driver and device_sn:
                            try:
                                original_volumes[device_sn] = driver.get_volume(device_sn)
                                driver.set_volume(device_sn, int(volume_level))
                                self._log(level='INFO', content=f"设备 {device_sn} 音量已设为 {volume_level}", task_id=task_id)
                            except Exception as e:
                                self._log(level='WARNING', content=f"设备 {device_sn} 音量控制失败: {e}", task_id=task_id)
                
                # 播放音频（内部调用 pre_process）
                self._execute_audio_playback(
                    task_id, playback_dev, main_audio_config, main_gain=1.0,
                    device_index=audio_service.get_device_index(playback_dev.device_unique_id),
                    device_info_list=device_info_list,
                    dry_audios_info=dry_audios_info,
                    dry_devices=dry_devices,
                    noise_audio_info=noise_audio_info,
                    noise_devices=noise_devices,
                    case_config=round_case_config,
                    algorithm_type=algorithm_type,
                    test_case_id=test_case_id,
                    extra_audio_configs=interferer_audio_configs
                )
                
                # post_process（含音量恢复）
                self._post_process_devices(device_info_list, task_id, test_case_id=test_case_id)
                
                if original_volumes:
                    for device_sn, original_vol in original_volumes.items():
                        if original_vol < 0:
                            continue
                        for info in device_info_list:
                            if info.get('device_sn') == device_sn:
                                try:
                                    info['driver'].set_volume(device_sn, original_vol)
                                except Exception as e:
                                    self._log(level='WARNING', content=f"设备 {device_sn} 音量恢复失败: {e}", task_id=task_id)
                
                # 等待并检测打断事件
                interruption_events = self._wait_and_detect_interruption(
                    task_id, device_info_list, round_algo_params, E2E_RESULT_COLLECTION_WAIT_TIME
                )
                
                # 收集本轮结果
                collect_result = self._collect_results(
                    task_id, test_case_id, device_info_list,
                    algorithm_type=algorithm_type,
                    case_reference_params=case_reference_params
                )
                
                if isinstance(collect_result, tuple):
                    round_results, adjusted_case_ref_params = collect_result
                    if adjusted_case_ref_params:
                        last_adjusted_ref_params = adjusted_case_ref_params
                else:
                    round_results = collect_result
                
                # 附加打断事件到本轮结果
                if interruption_events:
                    for r in (round_results if isinstance(round_results, list) else [round_results]):
                        r['interruption_events'] = interruption_events
                
                # 为每轮结果标记 round_number，供评估阶段透传 (0-indexed)
                tagged_results = round_results if isinstance(round_results, list) else [round_results]
                for r in tagged_results:
                    r['round_number'] = round_idx
                all_round_results.extend(tagged_results)
                
                # 导轨复位
                if rail_controller:
                    try:
                        rail_controller.reset_rail()
                    except Exception as e:
                        self._log(level='WARNING', content=f"导轨复位失败: {e}", task_id=task_id)
            
            if not all_round_results:
                error_msg = "所有轮次均未产生有效结果"
                self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message=error_msg)
                return False
            
            # 合并所有轮的结果进行处理
            success = self._process_results(
                task_id, case_name, tc_rel_id, test_case_id, all_round_results, case_config,
                case_reference_params=case_reference_params,
                case_algorithm_params=data.get('case_algorithm_params'),
                algorithm_type=algorithm_type,
                adjusted_case_reference_params=last_adjusted_ref_params
            )
            
            return success
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            error_msg = f"用例执行异常: {str(e)}"
            self._log(level='ERROR', content=f"用例 {case_name} 执行异常: {str(e)}\n{error_trace}", task_id=task_id, test_case_id=getattr(self, 'current_test_case_id', None))
            self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message=error_msg)
            return False
    

    

    
    def _get_device_info(self, task_id, case_config):
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
                    dev.needs_prompt_audio, dev.prompt_config, case_config, device_id=dev.id
                )
                device_info_list.append({
                    "device_id": dev.id, "device_sn": dev.serial_number or dev.ip,
                    "device_name": dev.name, "driver": driver,
                    "prompt_audio_path": prompt_path, "prompt_audio_name": prompt_name,
                    "needs_prompt_audio": dev.needs_prompt_audio,
                    "device_unique_id": dev.device_unique_id,
                    "channel_index": dev.channel_index or 0,
                    "current_spl_mapping_id": dev.current_spl_mapping_id
                })

            return {'success': True, 'data': {'device_info_list': device_info_list}}
        finally:
            local_db_session.close()
    
    def _get_prompt_audio_info(self, needs_prompt_audio, prompt_config, case_config, device_id=None):
        """
        获取提示音频信息 (支持多维度关联查询)
        
        Args:
            needs_prompt_audio: 是否需要提示音频
            prompt_config: 提示音频配置
            case_config: 测试用例配置 (包含 algorithm_type, translation_direction, source_language, target_language)
            device_id: 设备ID
            
        Returns:
            tuple: (prompt_audio_path, prompt_audio_name)
        """
        if not needs_prompt_audio or not prompt_config:
            return None, None
        
        direction_str = case_config.get('translation_direction')
        algo_type = case_config.get('algorithm_type')
        source_lang = case_config.get('source_language')
        target_lang = case_config.get('target_language')
        
        local_db_session = db.session()
        try:
            query = local_db_session.query(PromptAudioRelation, Audio).join(
                Audio, PromptAudioRelation.audio_id == Audio.id
            ).filter(
                PromptAudioRelation.deleted == False,
                Audio.deleted == False,
                Audio.audio_type == 'prompt'
            )
            
            relation = None
            
            conditions_list = [
                (device_id is not None and direction_str is not None and algo_type is not None, 
                 PromptAudioRelation.device_id == device_id, 
                 PromptAudioRelation.translation_direction == direction_str,
                 PromptAudioRelation.algorithm_type == algo_type),
                (device_id is not None and direction_str is not None, 
                 PromptAudioRelation.device_id == device_id, 
                 PromptAudioRelation.translation_direction == direction_str),
                (device_id is not None and source_lang and target_lang and algo_type is not None,
                 PromptAudioRelation.device_id == device_id,
                 PromptAudioRelation.source_language == source_lang,
                 PromptAudioRelation.target_language == target_lang,
                 PromptAudioRelation.algorithm_type == algo_type),
                (device_id is not None and source_lang and target_lang,
                 PromptAudioRelation.device_id == device_id,
                 PromptAudioRelation.source_language == source_lang,
                 PromptAudioRelation.target_language == target_lang),
                (device_id is not None and algo_type is not None, 
                 PromptAudioRelation.device_id == device_id, 
                 PromptAudioRelation.algorithm_type == algo_type),
                (device_id is not None, 
                 PromptAudioRelation.device_id == device_id),
            ]
            
            for condition in conditions_list:
                if condition[0] is True and len(condition) == 1:
                    temp_query = query.order_by(PromptAudioRelation.priority.desc())
                    relation = temp_query.first()
                    break
                elif condition[0]:
                    temp_query = query
                    for c in condition[1:]:
                        temp_query = temp_query.filter(c)
                    temp_query = temp_query.order_by(PromptAudioRelation.priority.desc())
                    relation = temp_query.first()
                    if relation:
                        break
            
            if relation:
                audio = relation[1] if isinstance(relation, tuple) else relation
                return audio.file_path, audio.name
            
            return None, None
        finally:
            local_db_session.close()
    
    def _execute_audio_playback(self, task_id, playback_dev, main_audio_config, main_gain, device_index, 
                                device_info_list, dry_audios_info, dry_devices, noise_audio_info, noise_devices, case_config, 
                                test_case_id=None, **kwargs):
        algorithm_type = kwargs.get('algorithm_type', 'translation')
        
        extra_params = getattr(self, 'current_extra_params', {}) or self._execute_extra_params(algorithm_type, kwargs, include_format_strings=True)
        
        devices_needing_prompt = [info for info in device_info_list if info.get("needs_prompt_audio", False)]
        devices_not_needing_prompt = [info for info in device_info_list if not info.get("needs_prompt_audio", False)]
        
        if devices_needing_prompt:
            self._pre_process_devices(devices_needing_prompt, task_id, test_case_id=test_case_id, extra_params=extra_params)
        
        self._play_prompt_audio(device_info_list, task_id, device_index, playback_dev, main_gain)
        
        if devices_not_needing_prompt:
            self._pre_process_devices(devices_not_needing_prompt, task_id, test_case_id=test_case_id, extra_params=extra_params)
        
        from backend.utils.algorithm.case_parameter_extractor import CaseParameterExtractor
        overlap_time = CaseParameterExtractor.get_overlap_time(case_config) if case_config else 0
        overlap_rate = CaseParameterExtractor.get_overlap_rate(case_config) if case_config else 0
        
        from backend.services.audio.audio_engine import execute_audio_playback
        extra_audio_configs = kwargs.get('extra_audio_configs', [])
        playback_result = execute_audio_playback(
            task_id=task_id,
            dry_audios_info=dry_audios_info,
            noise_audio_info=noise_audio_info,
            noise_devices=noise_devices,
            dry_devices=dry_devices,
            overlap_rate=overlap_rate,
            overlap_time=overlap_time,
            global_offset=0,
            loop=False,
            audio_service=audio_service,
            wait_for_completion=True,
            stop_noise_after_dry=True,
            extra_audio_configs=extra_audio_configs
        )
        
        audio_timelines = []
        if isinstance(playback_result, dict) and 'audio_timelines' in playback_result:
            audio_timelines = playback_result['audio_timelines']
        
        for i, timeline in enumerate(audio_timelines):
            if timeline.get('is_noise', False):
                continue
            
            audio_config = timeline.get('config', {})
            audio_obj = timeline.get('audio', {})
            audio_id = audio_obj.id if hasattr(audio_obj, 'id') else None
            
            if task_id in self._playback_timestamps and audio_id:
                self._playback_timestamps[task_id]['audio_play_times'].append({
                    'audio_id': audio_id,
                    'play_order': audio_config.get('play_order', 0),
                    'actual_time': timeline.get('actual_play_time', time.time()),
                    'actual_start_offset': timeline.get('start', 0),
                    'is_overlap': True if overlap_rate and overlap_rate > 0 else False,
                    'overlap_rate': overlap_rate,
                    'overlap_time': overlap_time
                })
    
    def _pre_process_devices(self, device_info_list, task_id, test_case_id=None, **kwargs):
        extra_params = kwargs.get('extra_params', {})
        record_start_time = time.time()
        self._playback_timestamps[task_id] = {
            'record_start_time': record_start_time,
            'audio_play_times': [],
            'theory_offsets': {}
        }
        pool = self.execution_engine.device_control_pool
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

    def _post_process_devices(self, device_info_list, task_id, test_case_id=None, **kwargs):
        extra_params = kwargs.get('extra_params', {})
        pool = self.execution_engine.device_control_pool
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
    
    def _play_prompt_audio(self, device_info_list, task_id, device_index, playback_dev, main_gain):
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
    
    def _collect_results(self, task_id, test_case_id, device_info_list, **kwargs):
        from backend.services.device.device_result_collector import get_device_result_collector
        
        algorithm_type = kwargs.get('algorithm_type', 'translation')
        extra_params = self._execute_extra_params(algorithm_type, kwargs, include_format_strings=True)
        
        playback_timestamps = self._playback_timestamps.get(task_id)
        if playback_timestamps:
            audio_offsets = self._calculate_actual_offset(task_id, playback_timestamps)
            case_ref_params = kwargs.get('case_reference_params')
            self._log(level='DEBUG', content=f"[_collect_results] audio_offsets count={len(audio_offsets) if audio_offsets else 0}, case_reference_params={'found' if case_ref_params else 'None'}", task_id=task_id)
            if audio_offsets:
                offset_values = [v['offset'] for v in audio_offsets.values()]
                if offset_values:
                    actual_offset = offset_values[0]
                    self._log(level='INFO', content=f"计算实际时间戳偏移: {actual_offset:.3f}s (共{len(audio_offsets)}个播放)", task_id=task_id)
                    extra_params['playback_time_offsets'] = audio_offsets
                    extra_params['reference_params'] = case_ref_params
        
        collector = get_device_result_collector()
        
        def log_callback(level, content, task_id, device_id):
            self._log(level=level, content=content, task_id=task_id, device_id=device_id)
        
        all_results = collector.collect_raw_results(
            task_id, test_case_id, device_info_list, extra_params, 
            log_callback=log_callback, **kwargs
        )
        
        adjusted_ref_params = None
        if all_results and isinstance(all_results, list):
            for res in all_results:
                if 'adjusted_reference_params' in res:
                    result_type = res.get('result_type', 'e2e')
                    if adjusted_ref_params is None:
                        adjusted_ref_params = {}
                    adjusted_ref_params[result_type] = res['adjusted_reference_params']
        
        if adjusted_ref_params:
            self._log(level='DEBUG', content=f"[_collect_results] found adjusted_reference_params: {list(adjusted_ref_params.keys())}", task_id=task_id)
        
        self._log(
            level='DEBUG',
            content=f"[e2e_executor] before return _collect_results: all_results id={id(all_results)}, raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:10] if all_results else 'empty'}",
            task_id=task_id
        )

        result_to_return = all_results
        if adjusted_ref_params:
            result_to_return = (all_results, adjusted_ref_params)
        
        self._log(
            level='DEBUG',
            content=f"[e2e_executor] returning: result_to_return id={id(result_to_return)}, raw_keys[0]={list(result_to_return[0][0].get('raw_results', {}).keys())[:10] if result_to_return else 'empty'}",
            task_id=task_id
        )
        
        return result_to_return
    
    def _calculate_actual_offset(self, task_id, playback_timestamps):
        record_start_time = playback_timestamps.get('record_start_time')
        audio_play_times = playback_timestamps.get('audio_play_times', [])
        
        if not record_start_time or not audio_play_times:
            return {}
        
        audio_offsets = {}
        
        for play_time in audio_play_times:
            audio_id = play_time.get('audio_id')
            if not audio_id:
                continue
            
            play_order = play_time.get('play_order', 0)
            actual_time = play_time.get('actual_time', record_start_time)
            
            theory_offset = play_time.get('actual_start_offset', 0.0)
            
            actual_offset = actual_time - record_start_time - theory_offset
            
            key = f"{audio_id}_{play_order}"
            audio_offsets[key] = {
                'audio_id': audio_id,
                'play_order': play_order,
                'offset': actual_offset
            }
            
            self._log(
                level='DEBUG',
                content=f"时间戳分析: audio_id={audio_id}, play_order={play_order}, record_start={record_start_time:.3f}, actual_play={actual_time:.3f}, theory_offset={theory_offset:.3f}, actual_offset={actual_offset:.3f}",
                task_id=task_id
            )
        
        return audio_offsets
    
    def _initialize_devices(self, device_info_list, task_id, test_case_id=None, **kwargs):
        algorithm_type = kwargs.get('algorithm_type', 'translation')
        
        extra_params = self._execute_extra_params(algorithm_type, kwargs, include_format_strings=True)
        
        pool = self.execution_engine.device_control_pool
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
        if failed: raise RuntimeError(f"设备初始化失败: {'; '.join([f'{r.get('device_name')}: {r.get('error')}' for r in failed])}")

    def _register_voiceprint(self, task_id, case_config, device_info_list):
        """
        播放声纹注册音频并等待注册完成。

        触发条件: case_config.voiceprint_config.enabled = true
        与算法类型无关，是 E2E 测试的通用能力。

        Returns:
            True  注册成功 / 不需要注册
            False 注册失败（应中止后续轮次）
        """
        vp_config = case_config.get('voiceprint_config', {})
        if not vp_config.get('enabled'):
            return True  # 无需注册

        audio_info = vp_config.get('audio', {})
        device_cfg = vp_config.get('device', {})
        spl = vp_config.get('spl')
        wait_time_ms = int(vp_config.get('waitTime', 3000))

        audio_id = audio_info.get('id')
        device_id = device_cfg.get('id')

        if not audio_id or not device_id:
            self._log(level='WARNING', content='声纹注册配置不完整 (缺少 audio.id 或 device.id)，跳过',
                      task_id=task_id)
            return True

        # 查找注册设备对应的 driver
        target_info = None
        for dev in device_info_list:
            if dev['device_id'] == device_id:
                target_info = dev
                break

        if target_info is None:
            self._log(level='ERROR',
                      content=f'声纹注册设备 (id={device_id}, name={device_cfg.get("name")}) 未找到',
                      task_id=task_id)
            return False

        driver = target_info.get('driver')
        device_sn = target_info.get('device_sn')

        # 从数据库获取音频文件路径
        audio_obj = db.session.get(Audio, audio_id)
        if not audio_obj or not audio_obj.file_path:
            self._log(level='ERROR',
                      content=f'声纹注册音频 (id={audio_id}) 不存在或无文件路径',
                      task_id=task_id)
            return False

        original_volume = None
        try:
            # 保存原始音量并设置注册音量
            if driver and device_sn and spl:
                try:
                    original_volume = driver.get_volume(device_sn)
                    driver.set_volume(device_sn, int(spl))
                    self._log(level='INFO',
                              content=f'声纹注册: 设备 {device_sn} 音量已设为 {spl}',
                              task_id=task_id)
                except Exception as e:
                    self._log(level='WARNING',
                              content=f'声纹注册: 音量控制失败: {e}',
                              task_id=task_id)

            # 通过 audio_service 播放注册音频
            device_unique_id = target_info.get('device_unique_id')
            channel_index = target_info.get('channel_index', 0)
            device_index = audio_service.get_device_index(device_unique_id) if device_unique_id else 0

            if device_index is None:
                self._log(level='ERROR',
                          content=f'声纹注册: 无法获取设备索引 (unique_id={device_unique_id})',
                          task_id=task_id)
                return False

            audio_config = {
                'file': audio_obj.file_path,
                'device_index': device_index,
                'channel': channel_index,
                'gain': 1.0,
                'delay': 0,
                'is_noise': False,
                'loop': False,
            }

            self._log(level='INFO',
                      content=f'开始声纹注册: 播放 {audio_info.get("name", audio_obj.file_path)}',
                      task_id=task_id)

            audio_service.play_overlap(
                task_id=task_id,
                audio_configs=[audio_config],
                overlap_time=0,
                overlap_rate=0,
                offset=0,
                loop=False,
            )

            # 等待注册完成
            wait_seconds = wait_time_ms / 1000.0
            time.sleep(wait_seconds)

            self._log(level='INFO',
                      content=f'声纹注册完成 (等待 {wait_seconds}s)',
                      task_id=task_id)
            return True

        except Exception as e:
            self._log(level='ERROR',
                      content=f'声纹注册失败: {e}',
                      task_id=task_id)
            return False

        finally:
            # 恢复原始音量
            if original_volume is not None and driver and device_sn:
                try:
                    driver.set_volume(device_sn, original_volume)
                except Exception:
                    pass

    def _build_interferer_configs(self, task_id, interferer_config, device_info_list):
        """
        将干扰人配置转为 audio_to_play 格式，供 play_overlap 使用。
        输出格式与 execute_audio_playback 中的 audio_to_play 完全一致。

        Args:
            task_id: 任务ID
            interferer_config: 干扰人配置列表 (round_config.interferers)
            device_info_list: 可用设备信息列表

        Returns:
            list[dict]: audio_to_play 格式的列表
        """
        if not interferer_config:
            return []

        from flask import current_app
        app = None
        try:
            app = current_app._get_current_object()
        except RuntimeError:
            pass

        audio_to_play = []

        for idx, interferer in enumerate(interferer_config):
            if not isinstance(interferer, dict):
                continue

            audio_info = interferer.get('audio')
            device_cfg = interferer.get('device')
            spl = interferer.get('spl')
            start_delay_ms = interferer.get('startDelay', 0)
            loop = interferer.get('loop', False)

            if not audio_info or not device_cfg:
                self._log(level='WARNING',
                          content=f'干扰人 {idx} 配置不完整 (缺少 audio 或 device)，跳过',
                          task_id=task_id)
                continue

            # 查找干扰人设备
            target_info = None
            device_id = device_cfg.get('id')
            for dev in device_info_list:
                if dev['device_id'] == device_id:
                    target_info = dev
                    break

            if target_info is None:
                self._log(level='WARNING',
                          content=f'干扰人 {idx} 设备 (id={device_id}, name={device_cfg.get("name")}) 未找到，跳过',
                          task_id=task_id)
                continue

            device_unique_id = target_info.get('device_unique_id')
            channel_index = target_info.get('channel_index', 0)
            device_index = audio_service.get_device_index(device_unique_id) if device_unique_id else None

            if device_index is None:
                self._log(level='WARNING',
                          content=f'干扰人 {idx} 无法获取设备索引 (unique_id={device_unique_id})，跳过',
                          task_id=task_id)
                continue

            # SPL → 软件增益（与噪声/干声使用相同机制）
            gain = 1.0
            spl_mapping_id = target_info.get('current_spl_mapping_id')
            if spl_mapping_id and spl:
                try:
                    from backend.services.audio.spl_service import spl_service
                    gain = spl_service.spl_to_gain(spl_mapping_id, spl, app=app)
                except Exception:
                    gain = 1.0

            # 获取音频文件路径
            file_path = audio_info.get('path', '')
            if not file_path and audio_info.get('id'):
                audio_obj = db.session.get(Audio, audio_info['id'])
                if audio_obj:
                    file_path = audio_obj.file_path

            if not file_path:
                self._log(level='WARNING',
                          content=f'干扰人 {idx} 音频文件路径为空，跳过',
                          task_id=task_id)
                continue

            audio_to_play.append({
                'file': file_path,
                'device_index': device_index,
                'channel': channel_index,
                'gain': gain,
                'delay': start_delay_ms / 1000.0,   # ms → s
                'is_noise': bool(loop),              # loop=true → 循环播放
                'loop': bool(loop),
            })

        if audio_to_play:
            self._log(level='INFO',
                      content=f'构建了 {len(audio_to_play)} 个干扰人音频配置',
                      task_id=task_id)

        return audio_to_play

    def _wait_and_detect_interruption(self, task_id, device_info_list, algo_params, wait_time):
        """等待并检测打断事件"""
        enabled = algo_params.get('interruptionEnabled', 'false')
        if isinstance(enabled, str):
            enabled = enabled.lower() in ('true', '1', 'yes')
        if not enabled:
            time.sleep(wait_time)
            return []

        sensitivity = float(algo_params.get('interruptionSensitivity', '0.5'))
        events = []
        poll_interval = 0.1
        elapsed = 0.0
        while elapsed < wait_time:
            time.sleep(poll_interval)
            elapsed += poll_interval
            for info in device_info_list:
                driver = info.get('driver')
                device_sn = info.get('device_sn')
                if driver and device_sn:
                    try:
                        result = driver.detect_interruption(device_sn, sensitivity)
                        if result:
                            events.append(result)
                    except Exception:
                        pass
        return events

    def _process_results(self, task_id, case_name, tc_rel_id, test_case_id, all_results, case_config=None,
                        case_reference_params=None, case_algorithm_params=None, adjusted_case_reference_params=None, **kwargs):
        """处理E2E测试结果 - 使用统一字段映射
        """
        algorithm_type = kwargs.get('algorithm_type', 'translation')
        
        if adjusted_case_reference_params:
            self._log(level='DEBUG', content=f"[_process_results] using adjusted_case_reference_params: type={type(adjusted_case_reference_params)}", task_id=task_id)
            if isinstance(adjusted_case_reference_params, list):
                adjusted_ref_dict = {}
                for item in adjusted_case_reference_params:
                    if isinstance(item, dict):
                        code = item.get('code')
                        if code:
                            adjusted_ref_dict[code] = item
                self._log(level='DEBUG', content=f"[_process_results] adjusted_ref_dict keys: {list(adjusted_ref_dict.keys())}", task_id=task_id)
                case_reference_params = adjusted_ref_dict
            else:
                case_reference_params = adjusted_case_reference_params

        is_multi_round = any(r.get('round_number') is not None for r in all_results) if all_results else False
        self._log(level='DEBUG', content=f"[_process_results] is_multi_round={is_multi_round}", task_id=task_id)

        local_db_session = db.session()
        try:
            tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
            if not tc_rel: return False
            
            if not all_results:
                tc_rel.execution_status = 'failed'
                tc_rel.evaluation_status = 'failed'
                tc_rel.status = 'failed'
                tc_rel.error_message = "没有采集到设备结果"
                tc_rel.completed_at = utc8now()
                local_db_session.commit()
                return False

            extra_params = self._execute_extra_params(algorithm_type, kwargs, include_format_strings=True)
            kwargs.update(extra_params)

            if is_multi_round:
                execution_success = all(
                    r.get('raw_results', {}).get('success', False) for r in all_results
                )

                algo_result = self._build_e2e_algorithm_result(task_id, all_results, case_config, algorithm_type)

                first_result = all_results[0] if all_results else {}
                device_id = first_result.get('device_id')

                latency_values = []
                for r in all_results:
                    lat = r.get('response_time') or r.get('latency')
                    if lat is not None:
                        try:
                            latency_values.append(float(lat))
                        except (ValueError, TypeError):
                            pass
                avg_response_time = round(sum(latency_values) / len(latency_values), 4) if latency_values else 0

                result_id = self._save_result(
                    task_id=task_id,
                    test_case_id=test_case_id,
                    result_data={'multi_round': True, 'total_rounds': algo_result.get('total_rounds', 0)},
                    algo_result=algo_result,
                    algorithm_type=algorithm_type,
                    device_id=device_id,
                    api_id=None,
                    execution_status='completed' if execution_success else 'failed',
                    response_time=avg_response_time,
                    error_message=None if execution_success else "多轮测试存在失败轮次"
                )

                self._log(
                    level='DEBUG',
                    content=f"[_process_results] 多轮保存单条结果 result_id={result_id}, device_id={device_id}, total_rounds={algo_result.get('total_rounds')}, execution_success={execution_success}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )

                tc_rel.execution_status = 'completed' if execution_success else 'failed'
                if not execution_success:
                    tc_rel.evaluation_status = 'failed'
                    tc_rel.status = 'failed'
                    tc_rel.completed_at = utc8now()
                else:
                    tc_rel.status = 'pending'
                local_db_session.commit()

                if execution_success:
                    rounds_by_index = {}
                    for r in all_results:
                        rn = r.get('round_number', 0)
                        if rn not in rounds_by_index:
                            rounds_by_index[rn] = []
                        rounds_by_index[rn].append(r)

                    def extract_value(val):
                        if isinstance(val, dict) and 'value' in val:
                            return val.get('value', '')
                        return val

                    ref_fields = {}
                    for field_key, field_value in kwargs.items():
                        if field_value:
                            ref_fields[field_key] = extract_value(field_value)

                    for round_idx in sorted(rounds_by_index.keys()):
                        round_results = rounds_by_index[round_idx]
                        primary = round_results[0] if round_results else {}

                        self._log_case_result(
                            task_id, case_name, primary, ref_fields,
                            algorithm_type=algorithm_type, test_case_id=test_case_id
                        )

                        round_algo_result = {}
                        mapped_output_keys = get_field_mapper().get_mapped_device_output_field_keys(algorithm_type)
                        for key in mapped_output_keys:
                            if primary.get(key):
                                round_algo_result[key] = primary[key]

                        self._evaluate_result(
                            task_id=task_id,
                            result_id=result_id,
                            test_case_id=test_case_id,
                            algo_result=round_algo_result,
                            case_config=case_config or {},
                            case_reference_params=case_reference_params,
                            algorithm_type=algorithm_type,
                            test_type='e2e',
                            case_algorithm_params=case_algorithm_params,
                            round_number=round_idx
                        )

                return execution_success
            else:
                result = super()._process_results(
                    task_id=task_id,
                    test_case_id=test_case_id,
                    all_results=all_results,
                    case_config=case_config,
                    case_reference_params=case_reference_params,
                    algorithm_type=algorithm_type,
                    device_id_field='device_id',
                    api_id_field='api_id'
                )
                
                execution_success = result['execution_success']
                all_eval_items = result['all_eval_items']
                case_params = result['case_params']
                
                tc_rel.execution_status = 'completed' if execution_success else 'failed'
                if not execution_success:
                    tc_rel.evaluation_status = 'failed'
                    tc_rel.status = 'failed'
                    tc_rel.completed_at = utc8now()
                else:
                    tc_rel.status = 'pending'
                    if not all_eval_items:
                        tc_rel.evaluation_status = 'completed'
                local_db_session.commit()
                
                if execution_success and all_eval_items:
                    def extract_value(val):
                        if isinstance(val, dict) and 'value' in val:
                            return val.get('value', '')
                        return val
                    
                    ref_fields = {}
                    for field_key, field_value in kwargs.items():
                        if field_value:
                            ref_fields[field_key] = extract_value(field_value)
                    
                    for item in all_eval_items:
                        self._log_case_result(task_id, case_name, item['res'], ref_fields, algorithm_type=algorithm_type, test_case_id=item['test_case_id'])
                    
                    for item in all_eval_items:
                        algo_result = item['res']
                        
                        self._evaluate_result(
                            task_id=task_id,
                            result_id=item['result_id'],
                            test_case_id=item['test_case_id'],
                            algo_result=algo_result,
                            case_config=case_params,
                            case_reference_params=case_reference_params,
                            algorithm_type=algorithm_type,
                            test_type='e2e',
                            case_algorithm_params=case_algorithm_params,
                            round_number=item.get('round_number')
                        )
                
                return execution_success
        finally:
            local_db_session.close()
    
    def _log_case_result(self, task_id, case_name, res, ref_fields, **kwargs):
        algorithm_type = kwargs.pop('algorithm_type', 'translation')
        
        log_content = f"E2E 用例 {case_name}: " + self._get_result_mapper().build_case_result_log(algorithm_type, res, ref_fields, **kwargs)
        
        self._log(level='INFO' if res.get('success', False) else 'WARNING', content=log_content, task_id=task_id, test_case_id=kwargs.pop('test_case_id', None), device_id=res.get('device_id'))

    def _build_e2e_algorithm_result(self, task_id, all_round_results, case_config, algorithm_type):
        rounds_by_index = {}
        for r in all_round_results:
            rn = r.get('round_number', 0)
            if rn not in rounds_by_index:
                rounds_by_index[rn] = []
            rounds_by_index[rn].append(r)

        case_rounds = case_config.get('rounds', [])
        rounds_list = []
        latency_values = []
        interruption_count = 0

        for round_idx in sorted(rounds_by_index.keys()):
            round_results = rounds_by_index[round_idx]
            primary = round_results[0] if round_results else {}

            round_config = case_rounds[round_idx] if round_idx < len(case_rounds) else {}
            audios = round_config.get('audios', [])
            first_audio = audios[0] if audios else {}

            audio_name = first_audio.get('audio_name') or first_audio.get('name', '')
            audio_path = first_audio.get('audio_path') or first_audio.get('path', '')

            asr_text = primary.get('asr_text', '')
            device_raw = primary.get('raw_results', {})

            interruption = primary.get('interruption_events')
            if interruption:
                interruption_count += 1

            latency = primary.get('response_time') or primary.get('latency')
            if latency is not None:
                try:
                    latency_values.append(float(latency))
                except (ValueError, TypeError):
                    pass

            wait_time = round_config.get('waitTime', 5000)
            if wait_time is None:
                wait_time = 5000

            rounds_list.append({
                'round': round_idx,
                'input': {
                    'audio_name': audio_name,
                    'audio_path': audio_path,
                    'type': 'audio',
                },
                'output': {
                    'asr_text': asr_text,
                    'device_raw': device_raw,
                },
                'interruption': interruption if interruption else None,
                'latency': latency,
                'wait_time': wait_time,
                'evaluation': {},
            })

        avg_latency = None
        if latency_values:
            avg_latency = round(sum(latency_values) / len(latency_values), 4)

        aggregated = {
            'avg_latency': avg_latency,
            'interruption_count': interruption_count,
            'avg_wer': None,
            'avg_llm_judge': None,
        }

        result = {
            'test_type': 'e2e',
            'algorithm_type': algorithm_type,
            'total_rounds': len(rounds_list),
            'rounds': rounds_list,
            'aggregated': aggregated,
        }

        self._log(
            level='DEBUG',
            content=f"[_build_e2e_algorithm_result] 构建 E2E 算法结果: total_rounds={len(rounds_list)}, avg_latency={avg_latency}, interruption_count={interruption_count}",
            task_id=task_id
        )

        return result

    def _update_algorithm_result_evaluation(self, task_id, result_id):
        local_db_session = db.session()
        try:
            test_result = local_db_session.query(TestResult).filter(
                TestResult.id == result_id
            ).first()
            if not test_result:
                self._log(level='ERROR', content=f"[_update_algorithm_result_evaluation] TestResult 不存在: result_id={result_id}", task_id=task_id)
                return

            algo_result = test_result.algorithm_result
            if isinstance(algo_result, str):
                try:
                    algo_result = json.loads(algo_result)
                except (json.JSONDecodeError, TypeError):
                    algo_result = {}
            if not isinstance(algo_result, dict):
                algo_result = {}

            dim_results = local_db_session.query(TestResultDimension).filter(
                TestResultDimension.test_result_id == result_id
            ).all()

            round_evals = {}
            for dr in dim_results:
                if dr.round_number is None:
                    continue
                dim_obj = local_db_session.query(Dimension).get(dr.dimension_id) if dr.dimension_id else None
                dim_key = dim_obj.name if dim_obj else str(dr.dimension_id)
                dim_key_lower = dim_key.lower().replace(' ', '_').replace('-', '_')
                if dr.round_number not in round_evals:
                    round_evals[dr.round_number] = {}
                if dr.evaluation_status == 'completed' and dr.score is not None:
                    round_evals[dr.round_number][dim_key_lower] = dr.score

            rounds_list = algo_result.get('rounds', [])
            for round_idx, eval_data in round_evals.items():
                if round_idx < len(rounds_list):
                    rounds_list[round_idx]['evaluation'] = eval_data

            all_wer = []
            all_llm_judge = []
            for rd in rounds_list:
                ev = rd.get('evaluation', {})
                if 'wer' in ev and ev['wer'] is not None:
                    try:
                        all_wer.append(float(ev['wer']))
                    except (ValueError, TypeError):
                        pass
                if 'llm_judge' in ev and ev['llm_judge'] is not None:
                    try:
                        all_llm_judge.append(float(ev['llm_judge']))
                    except (ValueError, TypeError):
                        pass

            aggregated = algo_result.get('aggregated', {})
            aggregated['avg_wer'] = round(sum(all_wer) / len(all_wer), 4) if all_wer else None
            aggregated['avg_llm_judge'] = round(sum(all_llm_judge) / len(all_llm_judge), 4) if all_llm_judge else None

            algo_result['rounds'] = rounds_list
            algo_result['aggregated'] = aggregated
            test_result.algorithm_result = json.dumps(algo_result, ensure_ascii=False)
            local_db_session.commit()

            self._log(
                level='INFO',
                content=f"[_update_algorithm_result_evaluation] 更新完成: result_id={result_id}, avg_wer={aggregated.get('avg_wer')}, avg_llm_judge={aggregated.get('avg_llm_judge')}",
                task_id=task_id
            )
        except Exception as e:
            local_db_session.rollback()
            self._log(
                level='ERROR',
                content=f"[_update_algorithm_result_evaluation] 更新失败: result_id={result_id}, error={str(e)}",
                task_id=task_id
            )
        finally:
            local_db_session.close()
