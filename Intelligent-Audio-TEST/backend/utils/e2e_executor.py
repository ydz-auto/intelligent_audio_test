import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from backend.models.models import Audio, PlaybackDevice, Device, TaskCase, TaskDevice, PromptAudioRelation, utc8now
from backend.models.database import db
from backend.utils.audio_engine import audio_service
from backend.utils.spl_service import spl_service
from backend.device_driver import device_driver_factory, register_task_events
from backend.algorithm.field_mapper import get_field_mapper
from backend.utils.base_executor import BaseExecutor

E2E_RESULT_COLLECTION_WAIT_TIME = float(os.environ.get('E2E_RESULT_COLLECTION_WAIT_TIME', '3.0'))


class E2EExecutor(BaseExecutor):
    def __init__(self, execution_engine):
        super().__init__(execution_engine)
        self.current_device_id = None
        self._playback_timestamps = {}
        
    def _extend_log(self, task_id, **kwargs):
        """E2E 扩展日志字段"""
        device_id = kwargs.get('device_id')
        final_device_id = device_id or getattr(self._thread_ctx, 'current_device_id', None) or self.current_device_id
        self.current_device_id = final_device_id
        return {}

    def execute_e2e_case(self, task_id, tc_rel_id):
        """
        执行E2E测试用例
        """
        # 记录方法开始执行
        self._log(
            level='DEBUG',
            content=f"E2E用例执行方法开始: task_id={task_id}, tc_rel_id={tc_rel_id}",
            task_id=task_id,
            test_case_id=None
        )
        
        # 验证参数
        if not task_id or not tc_rel_id:
            error_msg = "任务ID和测试用例关联ID不能为空"
            self._log(
                level='ERROR',
                content=f"E2E 用例执行失败: {error_msg}",
                task_id=task_id,
                test_case_id=None
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
        case_name = data['case_name']
        case_config = data['case_config']
        case_reference_params = data.get('case_reference_params', {})
        case_algorithm_params = data.get('case_algorithm_params', {})
        test_case_id = data['test_case_id']
        tc_rel_id = data['tc_rel_id']
        algorithm_type = data.get('algorithm_type', 'translation')
        task_name = data.get('task_name')
        
        field_mapper = get_field_mapper()
        case_fields = field_mapper.get_case_fields(algorithm_type)
        
        case_field_values = {}
        for config_key in case_fields.keys():
            case_field_values[config_key] = data.get(config_key)
        
        self.current_case_field_values = case_field_values
        
        # 设置当前用例ID，供日志方法使用
        self.current_test_case_id = test_case_id
        self._thread_ctx.current_test_case_id = test_case_id
        
        try:
            # 记录开始执行E2E用例
            self._log(
                level='INFO',
                content=f"开始执行E2E用例: {case_name}",
                task_id=task_id,
                test_case_id=test_case_id
            )
            
            self._handle_control(task_id)
            
            # 设置执行状态为running
            self._update_tc_rel_status(tc_rel_id, execution_status='running')
            
            # 处理音频配置
            from backend.utils.audio_engine import prepare_audio_playback_info
            local_db_session = db.session()
            try:
                audios = case_config.get('audios', [])
                e2e_audios = [audio for audio in audios if audio.get('test_type') == 'e2e' and audio.get('audio_id')]
                if not e2e_audios:
                    error_msg = "未配置有效的 E2E 测试音频"
                    self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message=error_msg)
                    return False
                
                playback_info = prepare_audio_playback_info(e2e_audios, case_config, local_db_session)
                if not playback_info:
                    error_msg = "没有可用的干声音频"
                    self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message=error_msg)
                    return False
                
                dry_audios_info = playback_info['dry_audios_info']
                dry_devices = playback_info['dry_devices']
                noise_audio_info = playback_info['noise_audio_info']
                noise_devices = playback_info['noise_devices']
                
                if not dry_audios_info:
                    error_msg = "没有可用的干声音频"
                    self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message=error_msg)
                    return False
                
                main_audio_config = dry_audios_info[0][0]
                playback_dev = dry_devices[0] if dry_devices else None
                if not playback_dev:
                    error_msg = "没有可用的播放设备"
                    self._update_tc_rel_status(tc_rel_id, execution_status='failed', status='failed', error_message=error_msg)
                    return False
            finally:
                local_db_session.close()
            
            device_result = self._get_device_info(task_id, case_config)
            if not device_result['success']:
                error_msg = device_result.get('error', '设备信息获取失败')
                # 更新状态为失败
                self._update_tc_rel_status(
                    tc_rel_id, 
                    execution_status='failed',
                    status='failed',
                    error_message=error_msg
                )
                return False
            
            device_data = device_result['data']
            device_info_list = device_data['device_info_list']
            
            if not algorithm_type or algorithm_type == 'translation':
                algorithm_type = case_config.get('algorithm_type', algorithm_type)
            
            self.current_extra_params = self._execute_extra_params(algorithm_type, case_field_values, include_format_strings=True)
            
            stop_event, pause_event = self._get_control_events(task_id)
            
            register_task_events(task_id, stop_event, pause_event)
            
            device_driver_factory.register_task_devices(task_id, device_info_list)
            
            for info in device_info_list:
                if info.get("driver"):
                    info["driver"].set_task_id(task_id)
                    info["driver"].set_test_case_id(test_case_id)
            
            self._initialize_devices(device_info_list, case_name, task_id, test_case_id=test_case_id, algorithm_type=algorithm_type)
            
            self._execute_audio_playback(
                task_id, case_name, playback_dev, main_audio_config, main_gain=1.0,
                device_index=audio_service.get_device_index(playback_dev.device_unique_id),
                device_info_list=device_info_list,
                dry_audios_info=dry_audios_info,
                dry_devices=dry_devices,
                noise_audio_info=noise_audio_info,
                noise_devices=noise_devices,
                case_config=case_config,
                algorithm_type=algorithm_type,
                test_case_id=test_case_id
            )
            
            self._post_process_devices(device_info_list, case_name, task_id, test_case_id=test_case_id)
            
            time.sleep(E2E_RESULT_COLLECTION_WAIT_TIME)
            collect_result = self._collect_results(
                task_id, device_info_list, 
                algorithm_type=algorithm_type,
                case_name=case_name,
                test_case_id=test_case_id,
                task_name=task_name,
                case_reference_params=case_reference_params
            )
            
            if isinstance(collect_result, tuple):
                all_results, adjusted_case_ref_params = collect_result
            else:
                all_results = collect_result
                adjusted_case_ref_params = None
            
            if adjusted_case_ref_params:
                self._log(level='DEBUG', content=f"[execute_e2e_case] adjusted_case_ref_params types: {list(adjusted_case_ref_params.keys())}", task_id=task_id, test_case_id=test_case_id)
            
            # 调试：接收到的结果
            self._log(
                level='DEBUG',
                content=f"[e2e_executor] received all_results id={id(all_results)}, raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:10] if all_results else 'empty'}",
                task_id=task_id,
                test_case_id=test_case_id
            )

            # 直接调用 _process_results，由其内部统一调用 build_evaluation_params 构建评估参数
            # 不再手动收集 eval_inputs，与 API 执行器保持一致
            success = self._process_results(
                task_id, case_name, tc_rel_id, test_case_id, all_results, case_config,
                case_reference_params=case_reference_params,
                case_algorithm_params=case_algorithm_params,
                algorithm_type=algorithm_type,
                adjusted_case_reference_params=adjusted_case_ref_params
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
                    "device_id": dev.id, "device_connect_id": dev.serial_number or dev.ip,
                    "device_name": dev.name, "driver": driver,
                    "prompt_audio_path": prompt_path, "prompt_audio_name": prompt_name,
                    "needs_prompt_audio": dev.needs_prompt_audio
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
    
    def _execute_audio_playback(self, task_id, case_name, playback_dev, main_audio_config, main_gain, device_index, 
                                device_info_list, dry_audios_info, dry_devices, noise_audio_info, noise_devices, case_config, 
                                test_case_id=None, **kwargs):
        algorithm_type = kwargs.get('algorithm_type', 'translation')
        
        extra_params = getattr(self, 'current_extra_params', {}) or self._execute_extra_params(algorithm_type, kwargs, include_format_strings=True)
        
        devices_needing_prompt = [info for info in device_info_list if info.get("needs_prompt_audio", False)]
        devices_not_needing_prompt = [info for info in device_info_list if not info.get("needs_prompt_audio", False)]
        
        if devices_needing_prompt:
            self._pre_process_devices(devices_needing_prompt, case_name, task_id, "播放提示音前", test_case_id=test_case_id, extra_params=extra_params)
        
        self._play_prompt_audio(device_info_list, case_name, task_id, device_index, playback_dev, main_gain)
        
        if devices_not_needing_prompt:
            self._pre_process_devices(devices_not_needing_prompt, case_name, task_id, "播放提示音后", test_case_id=test_case_id, extra_params=extra_params)
        
        from backend.algorithm.case_parameter_extractor import CaseParameterExtractor
        overlap_time = CaseParameterExtractor.get_overlap_time(case_config) if case_config else 0
        overlap_rate = CaseParameterExtractor.get_overlap_rate(case_config) if case_config else 0
        
        from backend.utils.audio_engine import execute_audio_playback
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
            stop_noise_after_dry=True
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
    
    def _pre_process_devices(self, device_info_list, case_name, task_id, phase, test_case_id=None, **kwargs):
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
                    info.get("device_connect_id"),
                    test_case_id=test_case_id,
                    **extra_params
                )
                futures.append(future)
        for future in futures:
            try:
                future.result(timeout=60)
            except Exception as e:
                self._log(level='ERROR', content=f"设备预处理失败: {e}", task_id=task_id, test_case_id=test_case_id)

    def _post_process_devices(self, device_info_list, case_name, task_id, test_case_id=None, **kwargs):
        extra_params = kwargs.get('extra_params', {})
        pool = self.execution_engine.device_control_pool
        futures = []
        for info in device_info_list:
            if info["driver"] and hasattr(info["driver"], "post_process"):
                future = pool.submit(
                    info["driver"].post_process,
                    info.get("device_connect_id"),
                    test_case_id=test_case_id,
                    **extra_params
                )
                futures.append(future)
        for future in futures:
            try:
                future.result(timeout=60)
            except Exception as e:
                self._log(level='ERROR', content=f"设备后处理失败: {e}", task_id=task_id, test_case_id=test_case_id)
    
    def _play_prompt_audio(self, device_info_list, case_name, task_id, device_index, playback_dev, main_gain):
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
    
    def _collect_results(self, task_id, device_info_list, **kwargs):
        from backend.utils.device_result_collector import get_device_result_collector
        
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
            task_id, device_info_list, extra_params, 
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
    
    def _initialize_devices(self, device_info_list, case_name, task_id, test_case_id=None, **kwargs):
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
                    ok = info["driver"].initialize(info.get("device_connect_id") or info["device_id"], test_case_id=test_case_id, **extra_params)
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
                        case_algorithm_params=case_algorithm_params
                    )
            
            return execution_success
        finally:
            local_db_session.close()
    
    def _log_case_result(self, task_id, case_name, res, ref_fields, **kwargs):
        algorithm_type = kwargs.pop('algorithm_type', 'translation')
        
        log_content = f"E2E 用例 {case_name}: " + self._get_result_mapper().build_case_result_log(algorithm_type, res, ref_fields, **kwargs)
        
        self._log(level='INFO' if res.get('success', False) else 'WARNING', content=log_content, task_id=task_id, test_case_id=kwargs.pop('test_case_id', None), device_id=res.get('device_id'))
