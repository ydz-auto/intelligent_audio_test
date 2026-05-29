# -*- coding: utf-8 -*-
import time
import json
import os
import random
import threading
import queue
from threading import Lock
from datetime import datetime
from backend.models.models import TaskAPI, Audio, AudioAnnotation, TestCase, TaskCase, Task, API, TestResult, TranslationDirection
from backend.models.database import db
from backend.utils.api_driver import APIDriver
from backend.utils.config_manager import config_manager
from backend.algorithm.field_mapper import get_field_mapper
from backend.algorithm.reference_params_generator import ReferenceParamsGenerator
from backend.utils.base_executor import BaseExecutor

class APIExecutor(BaseExecutor):
    def __init__(self, execution_engine):
        super().__init__(execution_engine)
        self.api_semaphores = {}  # API信号量 {api_id: Semaphore}
        self.api_waiting_counts = {}  # API等待计数 {api_id: int}
        self.global_lock = Lock()
        self.task_locks = {}
        self.task_lock = Lock()
        self.completed_tasks = set()
        self.completed_tasks_lock = Lock()
        self.max_wait_time = config_manager.get_value('api_executor', 'max_wait_time', 300)
    
    def _get_task_lock(self, task_id):
        task_id_str = str(task_id)
        with self.task_lock:
            if task_id_str not in self.task_locks:
                self.task_locks[task_id_str] = Lock()
        return self.task_locks[task_id_str]
    
    def _cleanup_task_lock(self, task_id):
        task_id_str = str(task_id)
        with self.task_lock:
            if task_id_str in self.task_locks:
                del self.task_locks[task_id_str]
    
    def mark_task_completed(self, task_id):
        with self.completed_tasks_lock:
            self.completed_tasks.add(str(task_id))
        self._cleanup_task_lock(task_id)
    
    def cleanup_completed_tasks(self):
        with self.completed_tasks_lock:
            completed = list(self.completed_tasks)
            self.completed_tasks.clear()
        for task_id in completed:
            self._cleanup_task_lock(task_id)
    
    def _extend_log(self, task_id, **kwargs):
        """API 扩展日志字段"""
        api_config = kwargs.get('api_config')
        api_id = kwargs.get('api_id')
        
        final_api_id = api_id
        if not final_api_id:
            if api_config and hasattr(api_config, 'id'):
                final_api_id = api_config.id
            elif api_config and isinstance(api_config, dict):
                final_api_id = api_config.get('id')
        
        self.current_api_id = final_api_id
        return {}

    def _get_or_create_semaphore(self, api_id, max_process):
        """
        获取或创建API的信号量
        
        Args:
            api_id: API ID
            max_process: 最大并发数
            
        Returns:
            threading.Semaphore: API信号量
        """
        import threading
        with self.global_lock:
            if api_id not in self.api_semaphores:
                self.api_semaphores[api_id] = threading.Semaphore(max_process)
                self._log(
                    level='DEBUG',
                    content=f"为 API {api_id} 创建信号量，最大并发数: {max_process}",
                    task_id=None,
                    api_id=api_id
                )
            return self.api_semaphores[api_id]

    def _inc_waiting(self, api_id):
        with self.global_lock:
            self.api_waiting_counts[api_id] = self.api_waiting_counts.get(api_id, 0) + 1
            return self.api_waiting_counts[api_id]

    def _dec_waiting(self, api_id):
        with self.global_lock:
            current = self.api_waiting_counts.get(api_id, 0)
            if current <= 1:
                self.api_waiting_counts.pop(api_id, None)
                return 0
            self.api_waiting_counts[api_id] = current - 1
            return self.api_waiting_counts[api_id]

    def acquire_api_execution_right(self, api_id, task_id, current_test_case_id, max_process=5, timeout=None):
        wait_timeout = timeout or self.max_wait_time
        self._log(
            level='DEBUG',
            content=f"API {api_id} 开始执行测试用例: {current_test_case_id}",
            task_id=task_id,
            api_id=api_id
        )

        semaphore = self._get_or_create_semaphore(api_id, max_process)
        start_time = time.time()
        waiting_incremented = False
        
        try:
            acquired = semaphore.acquire(blocking=False)
            if acquired:
                self._log(
                    level='INFO',
                    content=f"成功获取 API {api_id} 的执行权 (无需等待)",
                    task_id=task_id,
                    api_id=api_id
                )
                return True
            
            waiting_now = self._inc_waiting(api_id)
            waiting_incremented = True
            self._log(
                level='DEBUG',
                content=f"API {api_id} 并发已满，进入等待队列 (等待数: {waiting_now})",
                task_id=task_id,
                api_id=api_id
            )

            while True:
                self._handle_control(task_id)

                elapsed_time = time.time() - start_time
                remaining_time = wait_timeout - elapsed_time
                if remaining_time <= 0:
                    self._dec_waiting(api_id)
                    waiting_incremented = False
                    self._log(
                        level='WARNING',
                        content=f"获取 API {api_id} 执行权超时，已等待 {elapsed_time:.1f}秒",
                        task_id=task_id,
                        api_id=api_id
                    )
                    return False

                try:
                    acquired = semaphore.acquire(blocking=True, timeout=min(0.5, remaining_time))
                    if acquired:
                        elapsed_time = time.time() - start_time
                        self._log(
                            level='INFO',
                            content=f"成功获取 API {api_id} 的执行权 (等待: {elapsed_time:.1f}秒)",
                            task_id=task_id,
                            api_id=api_id
                        )
                        return True
                except Exception as e:
                    self._dec_waiting(api_id)
                    waiting_incremented = False
                    self._log(
                        level='ERROR',
                        content=f"获取 API {api_id} 执行权时发生异常: {str(e)}",
                        task_id=task_id,
                        api_id=api_id
                    )
                    return False

        except Exception as outer_e:
            if waiting_incremented:
                self._dec_waiting(api_id)
            self._log(
                level='ERROR',
                content=f"获取 API {api_id} 执行权时发生外部异常: {str(outer_e)}",
                task_id=task_id,
                api_id=api_id
            )
            return False

    def release_api_execution_right(self, api_id, task_id):
        """
        释放API执行权
        
        Args:
            api_id: API ID
            task_id: 任务ID
        """
        if api_id in self.api_semaphores:
            try:
                self.api_semaphores[api_id].release()
                self._dec_waiting(api_id)
                self._log(
                    level='DEBUG',
                    content=f"释放 API {api_id} 的执行权",
                    task_id=task_id,
                    api_id=api_id
                )
            except ValueError:
                self._log(
                    level='WARNING',
                    content=f"尝试释放 API {api_id} 的执行权，但信号量已达到最大值",
                    task_id=task_id,
                    api_id=api_id
                )

    def _validate_and_get_data(self, app, task_id, tc_rel_id):
        if app is None:
            raise ValueError("app参数不能为空")

        self._handle_control(task_id)
        
        from flask import current_app
        from backend.models.database import db
        
        # 使用本地会话确保独立可靠的会话
        local_db_session = db.session()
        try:
            tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
            if not tc_rel:
                raise ValueError(f"找不到测试用例关联记录，ID: {tc_rel_id}")
            
            task = local_db_session.query(Task).get(task_id)
            if not task:
                raise ValueError(f"找不到任务，ID: {task_id}")
            
            case = local_db_session.query(TestCase).get(tc_rel.test_case_id)
            if not case:
                raise ValueError(f"找不到测试用例，ID: {tc_rel.test_case_id}")
            
            # 设置当前用例ID，供日志方法使用
            self.current_test_case_id = case.id
            self._thread_ctx.current_test_case_id = case.id
            
            # 记录开始执行API用例
            self._log('INFO', f"开始执行API用例: {case.name}", task_id)
            
            # 获取任务关联的所有API（而不是只获取第一个）
            task_apis = local_db_session.query(TaskAPI).filter_by(task_id=task_id).all()
            if not task_apis:
                # 如果没有关联的API，直接返回错误
                api_configs = []
            else:
                # 获取所有关联的API配置
                api_ids = [task_api.api_id for task_api in task_apis]
                api_configs = local_db_session.query(API).filter(API.id.in_(api_ids)).all()
            
            # 在会话关闭前，提取需要的属性到本地变量
            tc_rel_id = tc_rel.id
            tc_rel_test_case_id = tc_rel.test_case_id
            test_case_id = case.id
            case_name = case.name
            # 提取task.type到本地变量，避免后续会话关闭后访问分离对象
            task_type = task.type if task else 'api'  # 默认API测试
            # 提取 algorithm_type
            case_config = case.config or {}
            algorithm_type = case.algorithm_type if hasattr(case, 'algorithm_type') and case.algorithm_type else None
            if not algorithm_type:
                algorithm_type = case_config.get('algorithm_type')
            if not algorithm_type:
                algorithm_type = 'translation'
            
            # 处理API配置，转换为本地对象列表
            processed_api_configs = []
            for api_config in api_configs:
                # 重新创建api_config对象，避免使用分离的对象
                class MockAPIConfig:
                    def __init__(self, id, endpoint, api_endpoints, default_max_process, meta, max_timeout, vendor):
                        self.id = id
                        self.endpoint = endpoint  # 保持内部属性名不变，因为后续代码仍使用self.endpoint访问
                        self.api_endpoints = api_endpoints
                        self.default_max_process = default_max_process
                        self.meta = meta
                        self.max_timeout = max_timeout
                        self.vendor = vendor
                
                processed_api_config = MockAPIConfig(
                    id=api_config.id,
                    endpoint=api_config.api_url,
                    api_endpoints=api_config.api_endpoints or [],
                    default_max_process=api_config.default_max_process or 5,
                    meta=api_config.meta or {},
                    max_timeout=api_config.max_timeout or 30,
                    vendor=api_config.vendor or None
                )
                processed_api_configs.append(processed_api_config)
        finally:
            local_db_session.close()
        
        # 如果没有API配置，直接返回错误
        if not processed_api_configs:
            error_msg = "找不到API配置"
            local_db_session = db.session()
            try:
                # 重新获取tc_rel，确保在有效会话中
                tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
                if tc_rel:
                    from datetime import timezone, timedelta
                    utc_plus_8 = timezone(timedelta(hours=8))
                    # 更新所有状态字段
                    tc_rel.status = 'failed'
                    tc_rel.execution_status = 'failed'
                    tc_rel.started_at = datetime.now(utc_plus_8)
                    tc_rel.completed_at = datetime.now(utc_plus_8)
                    tc_rel.error_message = error_msg
                    local_db_session.commit()
            finally:
                local_db_session.close()
            self._log('ERROR', f"API 用例 {case_name} 执行失败: {error_msg}", task_id)
            return False, None
        
        # 重新获取会话，处理音频配置
        local_db_session = db.session()
        try:
            # 重新获取case对象，确保在有效会话中
            case = local_db_session.query(TestCase).get(tc_rel_test_case_id)
            if not case:
                error_msg = "找不到测试用例"
                self._log('ERROR', f"API 用例执行失败: {error_msg}", task_id)
                tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
                if tc_rel:
                    tc_rel.status = 'failed'
                    local_db_session.commit()
                return False, None
            
            # 从 config.audios 中获取音频配置
            config = case.config or {}
            audios = config.get('audios', [])
            
            # 使用已在会话关闭前提取的task_type变量，避免访问分离对象
            
            # 根据任务类型筛选对应测试类型的音频，并确保audio_id不为空
            if task_type == 'api':
                # API测试，仅筛选test_type为api的音频
                target_audios = [audio for audio in audios if audio.get('test_type') == 'api' and audio.get('audio_id')]
                expected_test_type = 'API'
            else:
                # E2E测试，仅筛选test_type为e2e的音频
                target_audios = [audio for audio in audios if audio.get('test_type') == 'e2e' and audio.get('audio_id')]
                expected_test_type = 'E2E'
            
            # 检查是否配置了对应类型的音频
            if not target_audios:
                error_msg = f"测试用例未配置有效的 {expected_test_type} 测试音频"
                self._log('ERROR', f"{expected_test_type} 用例 {case_name} 执行失败: {error_msg}", task_id)
                tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
                if tc_rel:
                    from datetime import timezone, timedelta
                    utc_plus_8 = timezone(timedelta(hours=8))
                    tc_rel.status = 'failed'
                    tc_rel.execution_status = 'failed'
                    tc_rel.completed_at = datetime.now(utc_plus_8)
                    tc_rel.error_message = error_msg
                    local_db_session.commit()
                return False, None
            
            audio = None
            audio_id = None
            audio_name = None
            audio_asr_text = ""
            audio_file_path = None
            total_audio_duration = 0.0  # 所有对应类型音频的总时长
            
            # 获取所有对应类型音频的总时长
            for audio_config in target_audios:
                audio_id = audio_config.get('audio_id')
                if audio_id:
                    audio_obj = local_db_session.query(Audio).get(audio_id)
                    if audio_obj:
                        total_audio_duration += audio_obj.duration
            
            # 获取第一个音频作为主要音频
            audio_config = target_audios[0]
            audio_id = audio_config.get('audio_id')
            if audio_id:
                audio = local_db_session.query(Audio).get(audio_id)
                if audio:
                    audio_name = audio.name
                    audio_asr_text = audio.asr_text or ""
                    audio_file_path = audio.file_path
                    self._log('INFO', f"使用音频文件: {audio_name if audio else '未知'}", task_id)
            
            # 检查音频对象是否成功获取
            if not audio:
                error_msg = f"找不到ID为 {audio_id} 的音频文件"
                self._log('ERROR', f"{expected_test_type} 用例 {case_name} 执行失败: {error_msg}", task_id)
                tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
                if tc_rel:
                    from datetime import timezone, timedelta
                    utc_plus_8 = timezone(timedelta(hours=8))
                    tc_rel.status = 'failed'
                    tc_rel.execution_status = 'failed'
                    tc_rel.completed_at = datetime.now(utc_plus_8)
                    tc_rel.error_message = error_msg
                    local_db_session.commit()
                return False, None
            
            self._log('DEBUG', f"API用例音频总时长: {total_audio_duration}秒", task_id)
            
            case_config = case.config or {}
            algorithm_params = case.algorithm_params or {}
            
            # 使用 field_mapper 动态获取翻译方向字段
            field_mapper = get_field_mapper()
            field_codes = field_mapper.get_reference_field_codes(algorithm_type)
            trans_direction_id_field = field_codes.get('trans_direction_id_field')
            trans_direction_field = field_codes.get('trans_direction_field')
            
            # 动态获取翻译方向ID
            td_id = None
            if trans_direction_id_field:
                td_id = algorithm_params.get(trans_direction_id_field) or case_config.get(trans_direction_id_field)
            
            # 根据音频ID和翻译方向查询正确的翻译文本 (从 AudioAnnotation 中获取)
            translation_obj = None
            if audio_id:
                annotations = local_db_session.query(AudioAnnotation).filter_by(audio_id=audio_id, deleted=False).all()
                if td_id:
                    for ann in annotations:
                        if ann.target_language:
                            direction = local_db_session.query(TranslationDirection).get(td_id)
                            if direction and ann.target_language == direction.target_language:
                                translation_obj = ann
                                break
                else:
                    for ann in annotations:
                        if ann.format == 'json' and ann.data:
                            translation_obj = ann
                            break
            
            api_specific_config = case_config.get('api', {})
            
            # 动态获取翻译方向
            translation_direction = None
            if td_id:
                translation_dir = local_db_session.query(TranslationDirection).get(td_id)
                if translation_dir:
                    translation_direction = f"{translation_dir.source_language}2{translation_dir.target_language}"
            # 如果没有从数据库获取，尝试从配置中获取
            if not translation_direction and trans_direction_field:
                translation_direction = algorithm_params.get(trans_direction_field) or case_config.get(trans_direction_field)
            
            # 重新获取任务对象，确保在有效会话中
            task = local_db_session.query(Task).get(task_id)
            if task and not api_specific_config and task.type == 'api':
                api_specific_config = case_config
            
            # 重新获取tc_rel对象，确保在有效会话中
            tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
            
            # 提取audio对象的属性到本地变量，避免返回分离对象
            audio_data = {
                'id': audio.id if audio else None,
                'name': audio_name,
                'asr_text': audio_asr_text,
                'file_path': audio_file_path
            } if audio else None
            
            # 只返回ID和必要的数据，不返回数据库对象，避免分离对象问题
            return True, {
                'tc_rel_id': tc_rel_id,
                'task_id': task_id,
                'test_case_id': test_case_id,
                'case_name': case_name,
                'algorithm_type': algorithm_type,
                'api_configs': processed_api_configs,  # 返回所有API配置列表
                'audio': audio_data,  # 返回audio_data字典而不是audio对象
                'api_specific_config': api_specific_config,
                'translation_direction': translation_direction,
                'current_app': current_app,
                'total_audio_duration': total_audio_duration,  # 返回所有API音频的总时长
                'case_algorithm_params': algorithm_params  # 用例算法参数
            }
        finally:
            local_db_session.close()
    
    def _setup_api_endpoints(self, task_id, tc_rel_id, case_name, api_config, current_app):
        """
        设置API端点
        """
        # 从配置文件获取API路径映射
        api_paths = current_app.config.get('API_PATHS', {
            'health': '/health',
            'status': '/api/status',
            'create_task': '/api/create_task',
            'get_status': '/api/get_status/{task_id}',
            'get_frame_results': '/api/get_frame_results/{task_id}',
            'get_final_result': '/api/get_final_result/{task_id}',
            'delete_task': '/api/delete_task/{task_id}'
        })
        
        # 从API配置中获取基础URL
        base_urls = []
        endpoints = api_config.api_endpoints if hasattr(api_config, 'api_endpoints') and api_config.api_endpoints else []
        
        # 优先使用 API 主地址作为入口 (api_url)
        main_url = api_config.endpoint if hasattr(api_config, 'endpoint') and api_config.endpoint else ''
        
        if main_url:
            # 如果配置了主地址，则将其作为唯一的入口
            base_urls = [main_url.rstrip('/')]
        elif endpoints:
            # 如果没有主地址，则将所有配置的端点都视为潜在的入口（Master 节点）
            # 不再在客户端筛选 "最优" 端点，因为服务端 api.py 会自行处理调度
            base_urls = [ep.get('endpoint', '').rstrip('/') for ep in endpoints if ep.get('endpoint')]
        else:
            # 没有任何配置时的极端兜底
            base_urls = ['']
        
        # 使用全局入口状态管理
        engine = self.execution_engine
        with engine.api_entry_lock:
            for url in base_urls:
                if url not in engine.api_entry_status:
                    engine.api_entry_status[url] = {'available': True, 'fail_count': 0}
        
        # 封装选择和释放逻辑
        def select_base_url():
            with engine.api_entry_lock:
                # 优先选择可用的
                available_urls = [url for url in base_urls if engine.api_entry_status.get(url, {}).get('available', True)]
                if not available_urls:
                    available_urls = base_urls
                return random.choice(available_urls) if available_urls else None
        
        def release_base_url(url):
            pass  # 服务端调度，无需客户端维护并发
        
        return api_paths, select_base_url, release_base_url
    
    def _health_check(self, task_id, case_name, audio, api_config, api_specific_config, api_paths, select_base_url, release_base_url):
        """
        执行健康检查阶段
        """
        self._handle_control(task_id)
        context = {
            "case_name": case_name,
            "audio_id": audio.get('id') if audio else None,
            "asr_ref": audio.get('asr_text', '') if audio else "",
            "timestamp": int(time.time())
        }
        
        # 检查音频文件是否存在
        audio_file_path = audio.get('file_path', '') if audio else ''
        if audio_file_path:
            audio_file_path = os.path.normpath(audio_file_path)
        
        if not audio or not os.path.exists(audio_file_path):
            error_msg = f"音频文件不存在: {audio_file_path}"
            self._log('ERROR', error_msg, task_id, api_config=api_config)
            raise Exception(error_msg)
        
        # 执行一次健康检查，使用主URL（HTTP）或者负载均衡选择的URL
        health_url = None
        main_url = api_config.endpoint if hasattr(api_config, 'endpoint') and api_config.endpoint else ''
        
        if main_url and main_url.startswith('http'):
            # 如果主URL是HTTP协议，则使用主URL拼接健康检查路径
            health_url = f"{main_url.rstrip('/')}{api_paths['health']}"
        else:
            # 如果主URL为空或不是HTTP，尝试从负载均衡器选择一个URL
            selected_url_for_health = select_base_url()
            if selected_url_for_health and selected_url_for_health.startswith('http'):
                health_url = f"{selected_url_for_health.rstrip('/')}{api_paths['health']}"
            else:
                # 如果负载均衡器也没选出HTTP URL，尝试直接使用api_paths中的配置
                health_url = api_paths['health']
            
        self._log('INFO', f"执行健康检查: {health_url}", task_id, api_config=api_config)
        
        try:
            health_driver = APIDriver(api_config, api_specific_config, endpoint=health_url)
            health_result = health_driver.execute({}, method='GET')
            if not health_result['success']:
                # 如果是404或405，可能是健康检查路径不匹配，暂时忽略健康检查失败
                # 因为有些API可能没有实现 /health 路径
                status_code = health_result.get('status_code', 0)
                if status_code in [404, 405]:
                    self._log('WARNING', f"健康检查路径不存在({status_code})，跳过健康检查: {health_url}", task_id, api_config=api_config)
                else:
                    error_msg = f"健康检查失败: {health_result['error']}"
                    self._log('ERROR', error_msg, task_id, api_config=api_config)
                    raise Exception(error_msg)
            else:
                health_data = health_result.get('json', {})
                health_status = health_data.get('status', '')
                if health_status and health_status != 'healthy' and health_status != 'success':
                    error_msg = f"健康检查失败: 服务状态异常 - {health_status}"
                    self._log('ERROR', error_msg, task_id, api_config=api_config)
                    raise Exception(error_msg)
                
                self._log('INFO', f"健康检查成功，服务状态: {health_status or 'ok'}", task_id, api_config=api_config)
        finally:
            # 只有当我们使用select_base_url选择的URL时，才需要release
            if 'selected_url_for_health' in locals() and selected_url_for_health:
                 release_base_url(selected_url_for_health)
        
        return context
    
    def _create_task(self, task_id, audio, api_config, api_specific_config, api_paths, select_base_url, release_base_url, translation_direction, algorithm_type='translation'):
        """
        创建API任务 - 使用字段映射器动态构建请求参数
        """
        self._handle_control(task_id)
        # 2. 创建任务 - 使用负载均衡选择URL
        selected_url = select_base_url()
        create_task_url = f"{selected_url}{api_paths['create_task']}"
        self._log('INFO', f"创建任务: {create_task_url}", task_id, api_config=api_config)
        
        try:
            create_task_driver = APIDriver(api_config, api_specific_config, endpoint=create_task_url)
            
            # 准备创建任务的请求数据
            audio_path = audio.get('file_path')
            if audio_path:
                import os
                # 规范化路径，确保在Windows下使用正确的路径分隔符，并解决混合斜杠问题
                audio_path = os.path.normpath(audio_path)
            
            # 获取供应商，优先级：用例特定配置 > API主记录字段 > API配置元数据 > 默认 volc_ast
            vendor = api_specific_config.get('vendor')
            if not vendor and hasattr(api_config, 'vendor') and api_config.vendor:
                vendor = api_config.vendor
            if not vendor and hasattr(api_config, 'meta') and isinstance(api_config.meta, dict):
                vendor = api_config.meta.get('vendor')
            if not vendor:
                vendor = "volc_ast"

            # 获取所有端点信息，用于分布式调度
            endpoints = []
            if hasattr(api_config, 'api_endpoints') and api_config.api_endpoints:
                # 过滤掉URL为空的端点
                endpoints = [ep for ep in api_config.api_endpoints if ep.get('endpoint')]
            

            # 获取并发控制参数
            max_process = api_config.default_max_process if hasattr(api_config, 'default_max_process') and api_config.default_max_process else 5
            max_timeout = api_config.max_timeout if hasattr(api_config, 'max_timeout') and api_config.max_timeout else 30
            
            # 使用字段映射器动态构建请求参数
            field_mapper = get_field_mapper()
            case_config = api_specific_config.get('case_config', {})
            
            create_task_data = field_mapper.build_create_task_data(
                algorithm_type=algorithm_type,
                case_config=case_config,
                audio_path=audio_path,
                translation_direction=translation_direction,
                vendor=vendor,
                max_process=max_process,
                max_timeout=max_timeout,
                endpoints=endpoints
            )
            
            # 确保必要字段存在（向后兼容）
            if 'audio_path' not in create_task_data:
                create_task_data['audio_path'] = audio_path
            if 'trans_direction' not in create_task_data and 'translation_direction' not in create_task_data:
                create_task_data['trans_direction'] = translation_direction
            
            self._log(
                level='DEBUG',
                content=f"创建任务请求数据: {json.dumps(create_task_data, ensure_ascii=False)}",
                task_id=task_id,
                api_config=api_config
            )
            
            create_task_result = create_task_driver.execute(create_task_data)

            # 预处理 raw_response，解码其中的 Unicode 转义
            result_for_log = create_task_result.copy()
            if 'raw_response' in result_for_log and isinstance(result_for_log['raw_response'], str):
                try:
                    result_for_log['raw_response'] = json.loads(result_for_log['raw_response'])
                except:
                    pass

            self._log(
                level='DEBUG',
                content=f"创建任务响应结果: {json.dumps(result_for_log, ensure_ascii=False)}",
                task_id=task_id,
                api_config=api_config
            )
            
            if not create_task_result['success']:
                # 构建更详细的错误信息，包含状态码、业务错误码和响应内容
                biz_code = create_task_result.get('biz_code')
                biz_msg = create_task_result.get('biz_msg')
                if biz_code is not None:
                    error_msg = f"创建任务失败: BizError[{biz_code}] - {biz_msg}"
                elif create_task_result['error']:
                    error_msg = f"创建任务失败: {create_task_result['error']}"
                else:
                    status_code = create_task_result['status_code']
                    raw_response = create_task_result['raw_response']
                    error_msg = f"创建任务失败: HTTP {status_code} - {raw_response}"
                self._log(
                    level='ERROR',
                    content=f"{error_msg}",
                    task_id=task_id,
                    api_config=api_config
                )
                raise Exception(error_msg)
            
            # 获取任务ID
            api_task_id = create_task_result.get('json', {}).get('data', {}).get('task_id')
            if not api_task_id:
                error_msg = "创建任务成功，但未返回task_id"
                self._log(
                    level='ERROR',
                    content=f"{error_msg}",
                    task_id=task_id,
                    api_config=api_config
                )
                raise Exception(error_msg)
            self._log(
                level='INFO',
                content=f"创建任务成功，task_id: {api_task_id}",
                task_id=task_id,
                api_config=api_config
            )
            
            return api_task_id
        finally:
            release_base_url(selected_url)
    
    def _wait_for_task_completion(self, task_id, api_task_id, api_config, api_specific_config, api_paths, select_base_url, release_base_url, current_app, total_audio_duration):
        """
        等待任务完成 - 实现异步轮询机制
        
        Args:
            total_audio_duration: float, 所有API干声音频的总时长（秒）
        """
        # 计算动态最大等待时间：音频总时长的1.5倍
        dynamic_max_wait_time = total_audio_duration * 1.5
        # 从配置文件读取默认最大等待时间
        default_max_wait_time = current_app.config.get('API_MAX_WAIT_TIME', 43200)
        # 取动态计算值和默认值的最小值，避免等待时间过长
        max_wait_time = min(dynamic_max_wait_time, default_max_wait_time)
        # 轮询间隔：从配置文件读取 (秒)，减少轮询间隔以加快响应速度
        poll_interval = current_app.config.get('API_POLL_INTERVAL', 5)
        # 确保最大等待时间至少是30秒（最短等待时间）
        max_wait_time = max(max_wait_time, 30)
        # 确保最大等待时间至少是轮询间隔的2倍
        max_wait_time = max(max_wait_time, poll_interval * 2)
        # 开始等待时间
        start_wait_time = time.time()
        # 任务状态
        task_status = 'running'
        
        self._log(
            level='INFO',
            content=f"开始等待任务 {api_task_id} 完成，最大等待时间: {max_wait_time}秒，轮询间隔: {poll_interval}秒",
            task_id=task_id,
            api_config=api_config
        )
        
        # 异步轮询任务状态
        while True:
            self._handle_control(task_id)
            # 检查是否超过最大等待时间
            elapsed_time = time.time() - start_wait_time
            if elapsed_time > max_wait_time:
                error_msg = f"任务 {api_task_id} 执行超时，已等待 {elapsed_time:.0f}秒，超过最大等待时间 {max_wait_time}秒"
                self._log(
                    level='ERROR',
                    content=f"{error_msg}",
                    task_id=task_id,
                    api_config=api_config
                )
                raise Exception(error_msg)
            
            # 查询任务状态 - 使用负载均衡选择URL
            selected_url = select_base_url()
            get_status_url = f"{selected_url}{api_paths['get_status'].replace('{task_id}', api_task_id)}"
            
            try:
                self._log(
                    level='INFO',
                    content=f"查询任务状态: {get_status_url} (已等待: {elapsed_time:.0f}秒)",
                    task_id=task_id,
                    api_config=api_config
                )
                get_status_driver = APIDriver(api_config, api_specific_config, endpoint=get_status_url)
                get_status_result = get_status_driver.execute({'task_id': api_task_id}, method='GET')
                
                if not get_status_result['success']:
                    # 构建更详细的错误信息，包含状态码、业务错误码和响应内容
                    biz_code = get_status_result.get('biz_code')
                    biz_msg = get_status_result.get('biz_msg')
                    status_code = get_status_result.get('status_code', 0)
                    
                    if biz_code is not None:
                        error_msg = f"查询任务状态失败: BizError[{biz_code}] - {biz_msg}"
                    elif get_status_result['error']:
                        error_msg = f"查询任务状态失败: {get_status_result['error']}"
                    else:
                        raw_response = get_status_result['raw_response']
                        error_msg = f"查询任务状态失败: HTTP {status_code} - {raw_response}"
                    
                    # 区分暂时失败和永久失败
                    # 永久失败：404 (任务不存在), 400 (参数错误), 500 (服务内部错误), 以及特定的业务错误码
                    if status_code in [400, 404, 500] or biz_code in [400, 404]:
                        # 永久失败，直接抛出异常
                        self._log(
                            level='ERROR',
                            content=f"查询任务状态永久失败，终止等待: {error_msg}",
                            task_id=task_id,
                            api_config=api_config
                        )
                        raise Exception(f"任务 {api_task_id} 查询失败: {error_msg}")
                    else:
                        # 暂时失败，记录警告并继续重试
                        self._log(
                            level='WARNING',
                            content=f"查询任务状态失败，将重试: {error_msg}",
                            task_id=task_id,
                            api_config=api_config
                        )
                        continue
                
                # 解析任务状态
                status_data = get_status_result.get('json', {}).get('data', {})
                # 兼容不同的响应格式
                if not status_data:
                    status_data = get_status_result.get('json', {})
                task_status = status_data.get('status', 'running')
                progress = status_data.get('progress', 0)
                
                self._log(
                    level='INFO',
                    content=f"任务 {api_task_id} 状态: {task_status},响应：{str(status_data)}, 进度: {progress}%",
                    task_id=task_id,
                    api_config=api_config
                )
                
                # 如果任务完成或失败，跳出循环
                if task_status in ['completed', 'success', 'failed', 'error', 'pending']:
                    break
            finally:
                # 释放URL资源，减少并发数计数
                release_base_url(selected_url)
            
            # 等待下一次轮询
            self._log(
                level='INFO',
                content=f"等待 {poll_interval} 秒后再次查询任务状态",
                task_id=task_id
            )
            sleep_end = time.time() + poll_interval
            while time.time() < sleep_end:
                self._handle_control(task_id)
                time.sleep(min(0.5, sleep_end - time.time()))
        
        # 检查任务最终状态
        if task_status in ['failed', 'error', 'pending']:
            error_msg = f"任务 {api_task_id} 执行失败，状态: {task_status}"
            self._log(
                level='ERROR',
                content=f"{error_msg}",
                task_id=task_id
            )
            # 不抛出异常，而是返回状态信息，让调用者决定如何处理
            # 同时返回开始等待时间，以便计算耗时
            return start_wait_time, False, error_msg
        
        return start_wait_time, True, None
    
    def _get_final_result(self, task_id, api_task_id, api_config, api_specific_config, api_paths, select_base_url, release_base_url):
        """
        查询最终结果
        """
        self._handle_control(task_id)
        self._log(
            level='INFO',
            content=f"任务 {api_task_id} 执行完成，开始查询最终结果",
            task_id=task_id,
            api_config=api_config
        )
        
        # 查询最终结果 - 使用负载均衡选择URL
        selected_url = select_base_url()
        get_final_result_url = f"{selected_url}{api_paths['get_final_result'].replace('{task_id}', api_task_id)}"
        self._log(
            level='INFO',
            content=f"查询最终结果: {get_final_result_url}",
            task_id=task_id,
            api_config=api_config
        )
        
        try:
            get_final_result_driver = APIDriver(api_config, api_specific_config, endpoint=get_final_result_url)
            final_result_result = get_final_result_driver.execute({'task_id': api_task_id}, method='GET')
            if not final_result_result['success']:
                # 构建更详细的错误信息，包含状态码、业务错误码和响应内容
                biz_code = final_result_result.get('biz_code')
                biz_msg = final_result_result.get('biz_msg')
                if biz_code is not None:
                    error_msg = f"查询最终结果失败: BizError[{biz_code}] - {biz_msg}"
                elif final_result_result['error']:
                    error_msg = f"查询最终结果失败: {final_result_result['error']}"
                else:
                    status_code = final_result_result['status_code']
                    raw_response = final_result_result['raw_response']
                    error_msg = f"查询最终结果失败: HTTP {status_code} - {raw_response}"
                self._log(
                    level='ERROR',
                    content=f"{error_msg}",
                    task_id=task_id,
                    api_config=api_config
                )
                raise Exception(error_msg)
            self._log(
                level='INFO',
                content=f"查询最终结果成功",
                task_id=task_id,
                api_config=api_config
            )
            
            return final_result_result
        finally:
            # 释放URL资源，减少并发数计数
            release_base_url(selected_url)
    
    def _get_frame_results(self, task_id, api_task_id, api_config, api_specific_config, api_paths, select_base_url, release_base_url):
        """
        查询帧结果（可选，仅用于调试）
        """
        try:
            selected_url = select_base_url()
            get_frame_results_url = f"{selected_url}{api_paths['get_frame_results'].replace('{task_id}', api_task_id)}"
            self._log(
                level='INFO',
                content=f"查询帧结果: {get_frame_results_url}",
                task_id=task_id,
                api_config=api_config
            )
            get_frame_results_driver = APIDriver(api_config, api_specific_config, endpoint=get_frame_results_url)
            get_frame_results_result = get_frame_results_driver.execute({'page': 1, 'page_size': 5}, method='GET')
            if get_frame_results_result['success']:
                self._log(
                    level='INFO',
                    content=f"查询帧结果成功，共获取 {len(get_frame_results_result.get('json', {}).get('data', []))} 帧",
                    task_id=task_id,
                    api_config=api_config
                )
            else:
                self._log(
                    level='WARNING',
                    content=f"查询帧结果失败 (非致命错误): {get_frame_results_result['error']}",
                    task_id=task_id,
                    api_config=api_config
                )
        except Exception as e:
            self._log(
                level='WARNING',
                content=f"查询帧结果异常 (非致命错误): {str(e)}",
                task_id=task_id,
                api_config=api_config
            )
        finally:
            # 释放URL资源，减少并发数计数
            release_base_url(selected_url)
    
    def _delete_task(self, task_id, api_task_id, api_config, api_specific_config, api_paths, select_base_url, release_base_url):
        """
        删除远程任务，释放资源
        """
        try:
            selected_url = select_base_url()
            delete_task_url = f"{selected_url}{api_paths['delete_task'].replace('{task_id}', api_task_id)}"
            self._log(
                level='INFO',
                content=f"删除远程任务: {delete_task_url}",
                task_id=task_id,
                api_config=api_config
            )
            delete_task_driver = APIDriver(api_config, api_specific_config, endpoint=delete_task_url)
            delete_task_result = delete_task_driver.execute({}, method='DELETE')
            if delete_task_result['success']:
                self._log(
                    level='INFO',
                    content=f"删除远程任务成功: {api_task_id}",
                    task_id=task_id,
                    api_config=api_config
                )
            else:
                self._log(
                    level='WARNING',
                    content=f"删除远程任务失败 (非致命错误): {delete_task_result.get('error')}",
                    task_id=task_id,
                    api_config=api_config
                )
        except Exception as e:
            self._log(
                level='WARNING',
                content=f"删除远程任务异常 (非致命错误): {str(e)}",
                task_id=task_id,
                api_config=api_config
            )
        finally:
            release_base_url(selected_url)
    
    def _extract_final_result(self, task_id, final_result_result, algorithm_type='translation'):
        """
        提取最终结果 - 使用字段映射器动态获取字段代码
        """
        field_mapper = get_field_mapper()
        field_codes = field_mapper.get_reference_field_codes(algorithm_type)
        output_field_keys = list(field_mapper.get_api_output_fields(algorithm_type).keys())
        
        output_field = field_codes.get('output_field')
        input_field = field_codes.get('input_field')

        final_json = final_result_result.get('json', {})
        final_data = final_json.get('data', {})
        
        if not final_data and final_result_result.get('raw_response'):
            try:
                import ast
                raw_json = ast.literal_eval(final_result_result['raw_response'])
                final_data = raw_json.get('data', {})
            except Exception as e:
                self._log(
                    level='WARNING',
                    content=f"解析raw_response失败: {str(e)}",
                    task_id=task_id
                )
        
        algo_results = {}
        
        for key in output_field_keys:
            if key in final_data:
                algo_results[key] = final_data[key]
            elif input_field and key == output_field:
                for candidate in [output_field, 'result']:
                    if candidate in final_data:
                        algo_results[key] = final_data[candidate]
                        break
        
        for key in output_field_keys:
            if key not in algo_results:
                algo_results[key] = ''
        
        latency = final_result_result['latency']
        
        result_list = [algo_results.get(key, '') for key in output_field_keys]
        while len(result_list) < 2:
            result_list.append('')
        
        # 返回动态字段名的结果字典
        result_dict = {}
        for i, key in enumerate(output_field_keys):
            if i < len(result_list):
                result_dict[key] = result_list[i]
        
        return result_dict, latency
    
    def _create_test_result(self, task_id, test_case_id, api_config_id, success, error_msg, algo_result_dict, latency, final_result_result, algorithm_type='translation'):
        """
        创建测试结果记录 - 使用字段映射器动态构建算法结果
        """
        field_mapper = get_field_mapper()
        field_codes = field_mapper.get_reference_field_codes(algorithm_type)
        output_field_keys = list(field_mapper.get_api_output_fields(algorithm_type).keys())
        
        parsed_result = {}
        
        self._log(
            level='DEBUG',
            category='database',
            content=f"开始创建测试结果记录: task_id={task_id}, test_case_id={test_case_id}, api_config_id={api_config_id}, success={success}",
            task_id=task_id,
            test_case_id=test_case_id,
            api_id=api_config_id
        )
        
        response_data = {
            "status_code": 200,
            "latency": latency,
            "raw_response": final_result_result.get('raw_response', '') if isinstance(final_result_result, dict) else '',
            "is_sentence_end": True,
            "is_session_end": True
        }
        
        try:
            response_time = int(latency) if latency is not None else None
        except (ValueError, TypeError):
            response_time = None

        algorithm_result = algo_result_dict if algo_result_dict else {}
        # 如果有其他算法结果，也一并放入
        if parsed_result:
            for key, value in parsed_result.items():
                if key not in algorithm_result and value is not None:
                    algorithm_result[key] = value

        result = TestResult(
            task_id=task_id,
            test_case_id=test_case_id,
            api_id=api_config_id,
            algorithm_type=algorithm_type,
            execution_status='completed' if success else 'failed',
            response_time=response_time,
            algorithm_result=algorithm_result if algorithm_result else None,
            result_data=response_data,
            error_message=error_msg
        )
        
        self._log(
            level='DEBUG',
            category='database',
            content=f"创建TestResult对象: {result.__dict__}",
            task_id=task_id,
            test_case_id=test_case_id,
            api_id=api_config_id
        )
        
        # 检查必填字段是否都有值
        self._log(
            level='DEBUG',
            category='database',
            content=f"TestResult必填字段检查: task_id={task_id}, test_case_id={test_case_id}, api_id={api_config_id}, result_data={response_data}",
            task_id=task_id,
            test_case_id=test_case_id,
            api_id=api_config_id
        )
        
        # 检查TestResult对象的属性
        self._log(
            level='DEBUG',
            category='database',
            content=f"TestResult对象属性: id={result.id}, execution_status={result.execution_status}, response_time={result.response_time}, result_data={result.result_data}",
            task_id=task_id,
            test_case_id=test_case_id,
            api_id=api_config_id
        )
        
        # 尝试使用SQLAlchemy的engine直接执行插入，绕开ORM会话管理
        from sqlalchemy import text
        from backend.models.database import db

        try:
            # 直接使用传入的 algo_result_dict
            algo_result = algo_result_dict if algo_result_dict else {}
            if parsed_result:
                for key, value in parsed_result.items():
                    if key not in algo_result and value is not None:
                        algo_result[key] = value

            # 直接使用SQL插入语句（PostgreSQL使用RETURNING id返回插入的ID）
            insert_sql = text("""
                INSERT INTO test_results (task_id, test_case_id, device_id, api_id, algorithm_type, execution_status, response_time, algorithm_result, execution_steps, result_data, error_message, created_at)
                VALUES (:task_id, :test_case_id, :device_id, :api_id, :algorithm_type, :execution_status, :response_time, :algorithm_result, :execution_steps, :result_data, :error_message, :created_at)
                RETURNING id
            """)

            # 准备参数
            # 使用utc8now函数，避免timezone未定义的问题
            from datetime import datetime
            from backend.models.models import utc8now
            import json
            params = {
                'task_id': task_id,
                'test_case_id': test_case_id,
                'device_id': None,
                'api_id': api_config_id,
                'algorithm_type': algorithm_type,
                'execution_status': 'completed' if success else 'failed',
                'response_time': response_time,
                'algorithm_result': json.dumps(algo_result) if algo_result else None,
                'execution_steps': '[]',  # 直接使用字符串
                'result_data': json.dumps(response_data),  # 转换为有效的JSON格式
                'error_message': error_msg,
                'created_at': utc8now()
            }
            
            self._log(
                level='DEBUG',
                category='database',
                content=f"执行SQL插入: {insert_sql}",
                task_id=task_id,
                test_case_id=test_case_id
            )
            
            # 执行插入（使用正确的SQLAlchemy连接方式和参数传递）
            with db.engine.connect() as conn:
                # 执行插入语句，使用字典方式传递参数，RETURNING id直接返回插入的ID
                result = conn.execute(insert_sql, params)
                # 从RETURNING子句获取插入的ID
                result_id = result.scalar()
                # 提交事务
                conn.commit()
                self._log(
                    level='DEBUG',
                    category='database',
                    content=f"SQL插入成功，result_id={result_id}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
                
                # 验证插入结果
                if result_id:
                    # 查询刚插入的记录
                    select_sql = text("SELECT * FROM test_results WHERE id = :id")
                    saved_result = conn.execute(select_sql, {"id": result_id}).fetchone()
                    if saved_result:
                        self._log(
                            level='DEBUG',
                            category='database',
                            content=f"验证成功: 测试结果已成功入库，id={saved_result.id}",
                            task_id=task_id,
                            test_case_id=test_case_id
                        )
                    else:
                        self._log(
                            level='ERROR',
                            category='database',
                            content=f"验证失败: 测试结果未成功入库，id={result_id}",
                            task_id=task_id,
                            test_case_id=test_case_id
                        )
                else:
                    self._log(
                        level='ERROR',
                        category='database',
                        content=f"SQL插入失败，未返回result_id",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    result_id = None
        except Exception as sql_error:
            import traceback
            sql_trace = traceback.format_exc()
            self._log(
                level='ERROR',
                category='database',
                content=f"SQL插入失败: {str(sql_error)}\n{sql_trace}",
                task_id=task_id,
                test_case_id=test_case_id
            )
            result_id = None
            
        # 同步更新task_case_relations表的状态
        # 注意：只更新execution_status，evaluation_status和status字段需要在维度评估完成后再更新
        update_session = db.session()
        try:
            tc_rel = update_session.query(TaskCase).filter_by(task_id=task_id, test_case_id=test_case_id).first()
            if tc_rel:
                # 根据success更新execution_status
                # 注意：这里不更新evaluation_status和status，让评估服务在评估完成后统一更新
                if tc_rel.execution_status not in ['stopped']:
                    tc_rel.execution_status = 'completed' if success else 'failed'
                update_session.commit()
                self._log(
                    level='DEBUG',
                    category='database',
                    content=f"同步更新task_case_relations表的execution_status: task_id={task_id}, test_case_id={test_case_id}, execution_status={'completed' if success else 'failed'}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )
                
                # 强制推送进度更新到前端（不包括统计信息，统计信息等评估完成后再更新）
                if self.execution_engine:
                    self.execution_engine._emit_progress(task_id, force=True)
        finally:
            update_session.close()
            
        # 关闭会话（如果还没有关闭）
        try:
            if 'update_session' in locals() and update_session.is_active:
                update_session.close()
        except:
            pass
        
        # DEBUG: 记录返回的 result_id 值和类型
        self._log(
            level='DEBUG',
            category='database',
            content=f"[DEBUG _create_test_result] 返回 result_id={result_id}, type={type(result_id)}, task_id={task_id}, test_case_id={test_case_id}",
            task_id=task_id,
            test_case_id=test_case_id
        )
        
        return result_id  # 返回result_id而不是整个result对象，避免分离对象问题
    
    def _evaluate_test_result(self, task_id, result_id, test_case_id, case_name, case_config, 
                             algo_result_dict, 
                             algorithm_type='translation', test_type='api'):
        """
        评估测试结果 - 使用统一字段映射
        
        使用 CaseParameterExtractor.get_evaluation_params() 统一构建评估参数，
        支持四种数据来源: case, reference, device, api
        
        Returns:
            bool: 评估结果，True表示评估通过，False表示评估失败
        """
        self._log(
            level='INFO',
            category='evaluation',
            content=f"开始评估API用例: {case_name}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        self._handle_control(task_id)
        
        from backend.utils.evaluation_service import evaluation_service

        self._handle_control(task_id)
        
        field_mapper = get_field_mapper()
        
        # 直接使用传入的 algo_result_dict
        algorithm_result = algo_result_dict if algo_result_dict else {}
        
        # 构建用例参数，包含 algorithm_params 和 reference_params
        case_params = case_config or {}
        algorithm_params = case_params.get('algorithm_params', case_params)
        
        # 获取参考参数结构
        reference_params = case_params.get('reference_params', {})
        
        # 合并用例参数
        full_case_params = {
            'algorithm_params': algorithm_params,
            'reference_params': reference_params
        }
        
        # 测试日志：验证数据流转（不推送到前端）
        from backend.utils.log_handler import log_and_emit as debug_log
        debug_log('INFO', 'api_executor', 
            f"[字段映射测试] case_params keys: {list(case_params.keys())}, "
            f"reference_params: {reference_params}", 
            category='debug', push_to_websocket=False)
        
        # 使用 CaseParameterExtractor 统一构建评估参数 (支持 case/device/api/reference 四种来源)
        from backend.algorithm.case_parameter_extractor import CaseParameterExtractor
        eval_params = CaseParameterExtractor.get_evaluation_params(
            case_config=full_case_params,
            algorithm_result=algorithm_result,
            test_type=test_type
        )
        
        # 测试日志：验证评估参数构建结果
        debug_log('INFO', 'api_executor',
            f"[字段映射测试] get_evaluation_params result: {eval_params}",
            category='debug', push_to_websocket=False)
        
        # 调用评估服务
        evaluation_service.evaluate_case(
            task_id, result_id, test_case_id,
            algorithm_result,
            algorithm_type=algorithm_type,
            **eval_params
        )
        
        self._log(
            level='INFO',
            category='evaluation',
            content=f"评估API用例已入队: {case_name}",
            task_id=task_id,
            test_case_id=test_case_id
        )
        
        return True
    
    def execute_api_case(self, app, task_id, tc_rel_id):
        try:
            with app.app_context():
                # 只在方法开始时记录一次日志，避免重复
                self._log(
                    level='DEBUG',
                    content=f"开始执行测试用例: {tc_rel_id}",
                    task_id=task_id
                )
                
                self._handle_control(task_id)

                # 立即更新测试用例状态为'running'，避免其他线程重复执行
                local_db_session = db.session()
                try:
                    claimed = local_db_session.query(TaskCase).filter(
                        TaskCase.id == tc_rel_id,
                        TaskCase.task_id == task_id,
                        TaskCase.execution_status.in_(['pending', 'queued'])
                    ).update(
                        {
                            TaskCase.execution_status: 'running'
                        },
                        synchronize_session=False
                    )
                    if claimed != 1:
                        local_db_session.rollback()
                        self._log(
                            level='DEBUG',
                            content=f"测试用例 {tc_rel_id} 已在执行或已完成，跳过重复执行",
                            task_id=task_id
                        )
                        return True
                    local_db_session.commit()
                    self.execution_engine._emit_progress(task_id, force=True)
                    self._log(
                        level='DEBUG',
                        content=f"测试用例 {tc_rel_id} 状态更新为 running",
                        task_id=task_id
                    )
                except Exception as e:
                    self._log(
                        level='WARNING',
                        content=f"更新测试用例状态失败: {str(e)}",
                        task_id=task_id
                    )
                finally:
                    local_db_session.close()
                
                task_lock = self._get_task_lock(task_id)
                with task_lock:
                    # 确保在应用上下文中执行
                    validate_result, data = self._validate_and_get_data(app, task_id, tc_rel_id)
                    if not validate_result:
                        # 验证失败，更新任务统计信息和进度
                        local_db_session = db.session()
                        try:
                            task = local_db_session.query(Task).get(task_id)
                            if task:
                                success_count = local_db_session.query(TaskCase).filter(
                                    TaskCase.task_id == task_id,
                                    TaskCase.status == 'completed'
                                ).count()
                                failed_count = local_db_session.query(TaskCase).filter_by(
                                    task_id=task_id,
                                    status='failed'
                                ).count()
                                task.completed_cases = success_count
                                task.failed_cases = failed_count
                                local_db_session.commit()
                                self.execution_engine._emit_progress(task, force=True)
                        finally:
                            local_db_session.close()
                        return False
                
                # 从返回数据中获取ID和必要信息
                tc_rel_id = data['tc_rel_id']
                task_id = data['task_id']
                test_case_id = data['test_case_id']
                case_name = data['case_name']
                algorithm_type = data.get('algorithm_type', 'translation')
                api_configs = data['api_configs']  # 获取所有API配置
                audio = data['audio']
                api_specific_config = data['api_specific_config']
                translation_direction = data['translation_direction']  # 获取翻译方向
                current_app = data['current_app']
                total_audio_duration = data['total_audio_duration']  # 获取所有API音频的总时长
                case_algorithm_params = data.get('case_algorithm_params')  # 用例算法参数

                # 根据算法类型重新获取参考文本
                case_config = {}
                local_db_session = db.session()
                try:
                    case_obj = local_db_session.query(TestCase).get(test_case_id)
                    if case_obj:
                        case_config = case_obj.config or {}
                finally:
                    local_db_session.close()
                
                # 使用本地会话获取数据库对象
                local_db_session = db.session()
                try:
                    # 重新获取所有必要的数据库对象
                    tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
                    task = local_db_session.query(Task).get(task_id)
                    case = local_db_session.query(TestCase).get(test_case_id)
                    
                    if not tc_rel or not task or not case:
                        error_msg = "找不到必要的数据库对象"
                        self._log(
                            level='ERROR',
                            content=f"API 用例 {case_name} 执行失败: {error_msg}",
                            task_id=task_id
                        )
                        # 如果tc_rel存在，更新其状态
                        if tc_rel:
                            from datetime import timezone, timedelta
                            utc_plus_8 = timezone(timedelta(hours=8))
                            tc_rel.status = 'failed'
                            tc_rel.execution_status = 'failed'
                            tc_rel.evaluation_status = 'failed'
                            tc_rel.started_at = datetime.now(utc_plus_8)
                            tc_rel.completed_at = datetime.now(utc_plus_8)
                            tc_rel.error_message = error_msg
                            local_db_session.commit()
                            # 更新任务统计信息
                            task = local_db_session.query(Task).get(task_id)
                            if task:
                                success_count = local_db_session.query(TaskCase).filter(
                                    TaskCase.task_id == task_id,
                                    TaskCase.status == 'completed'
                                ).count()
                                failed_count = local_db_session.query(TaskCase).filter_by(
                                    task_id=task_id,
                                    status='failed'
                                ).count()
                                task.completed_cases = success_count
                                task.failed_cases = failed_count
                                local_db_session.commit()
                                self.execution_engine._emit_progress(task, force=True)
                        return False
                    
                    # 遍历所有API配置，为每个API执行测试
                    api_count = len(api_configs)
                    self._log(
                        level='INFO',
                        content=f"开始执行 {api_count} 个API的测试用例: {case_name},{test_case_id}",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    
                    # 预先检查并更新 TaskCase 状态为 running（如果还不是的话）
                    if tc_rel and tc_rel.execution_status in ['pending', 'queued']:
                        from datetime import timezone, timedelta
                        utc_plus_8 = timezone(timedelta(hours=8))
                        tc_rel.execution_status = 'running'
                        if not tc_rel.started_at:
                            tc_rel.started_at = datetime.now(utc_plus_8)
                        local_db_session.commit()
                        self.execution_engine._emit_progress(task_id, force=True)

                    for api_config in api_configs:
                        self._handle_control(task_id)
                        api_id = api_config.id
                        
                        self._log(
                            level='DEBUG',
                            content=f"处理API {api_id}",
                            task_id=task_id,
                            api_id=api_id
                        )
                        
                        # 获取API执行权，根据API配置的并发限制进行控制
                        max_process = getattr(api_config, 'default_max_process', 5) or 5
                        if not self.acquire_api_execution_right(api_id, task_id, tc_rel_id, max_process=max_process):
                            # 获取执行权失败，跳过该API的测试
                            error_msg = f"API {api_id} 执行权获取失败，跳过测试"
                            self._log(
                                level='ERROR',
                                content=f"API 用例 {case_name} 执行失败: {error_msg}",
                                task_id=task_id,
                                api_id=api_id
                            )
                            continue
                        
                        # API执行权获取成功，执行测试
                        try:  # 主try块，用于释放API执行权
                            # 设置API端点和负载均衡器
                            api_paths, select_base_url, release_base_url = self._setup_api_endpoints(task_id, tc_rel_id, case_name, api_config, current_app)
                            if not api_paths:
                                # 端点设置失败，继续下一个API
                                error_msg = f"API {api_id} 端点设置失败"
                                self._log(
                                    level='ERROR',
                                    content=f"API 用例 {case_name} 执行失败: {error_msg}",
                                    task_id=task_id,
                                    api_id=api_id
                                )
                                continue
                            
                            # 执行健康检查
                            context = self._health_check(task_id, case_name, audio, api_config, api_specific_config, api_paths, select_base_url, release_base_url)
                        
                            # 使用统一的翻译方向变量（优先使用api_specific_config中的值，否则使用从case获取的值）
                            actual_translation_direction = api_specific_config.get('translation_direction') if api_specific_config.get('translation_direction') else translation_direction
                            
                            # 创建任务，传递翻译方向
                            api_task_id = self._create_task(task_id, audio, api_config, api_specific_config, api_paths, select_base_url, release_base_url, actual_translation_direction, algorithm_type)
                        
                            try:
                                # 等待任务完成
                                start_wait_time, task_success, task_error_msg = self._wait_for_task_completion(task_id, api_task_id, api_config, api_specific_config, api_paths, select_base_url, release_base_url, current_app, total_audio_duration)
                                
                                if not task_success:
                                    # 任务失败，设置失败状态并记录错误信息
                                    total_task_time = time.time() - start_wait_time
                                    success = False
                                    error_msg = task_error_msg
                                    algo_result_dict = {}
                                    latency = 0
                                    final_result_result = {}
                                    
                                    self._log(
                                        level='ERROR',
                                        content=f"API {api_config.id} 用例 {case_name} 执行失败，任务耗时: {total_task_time:.0f}秒，错误: {error_msg}",
                                        task_id=task_id,
                                        api_id=api_config.id
                                    )
                                else:
                                    # 任务成功，继续处理结果
                                    # 查询最终结果
                                    final_result_result = self._get_final_result(task_id, api_task_id, api_config, api_specific_config, api_paths, select_base_url, release_base_url)
                                    
                                    # 查询帧结果（可选，仅用于调试）
                                    self._get_frame_results(task_id, api_task_id, api_config, api_specific_config, api_paths, select_base_url, release_base_url)
                                    
                                    # 提取最终结果
                                    algo_result_dict, latency = self._extract_final_result(task_id, final_result_result, algorithm_type)
                                    
                                    # 计算总任务时间
                                    total_task_time = time.time() - start_wait_time
                                    success = True
                                    error_msg = None
                                    
                                    self._log(
                                        level='INFO',
                                        content=f"API {api_config.id} 用例 {case_name} 执行成功，任务耗时: {total_task_time:.0f}秒，API耗时: {latency}ms",
                                        task_id=task_id,
                                        api_id=api_config.id
                                    )
                                
                                # 创建测试结果记录
                                result_id = self._create_test_result(task_id, test_case_id, api_config.id, success, error_msg, algo_result_dict, latency, final_result_result, algorithm_type)
                                
                            finally:
                                # 删除远程任务，释放资源 (确保在 finally 块中执行，防止资源泄露)
                                if 'api_task_id' in locals() and api_task_id:
                                    self._delete_task(task_id, api_task_id, api_config, api_specific_config, api_paths, select_base_url, release_base_url)
                            
                            # 重新查询tc_rel对象，确保获取最新状态
                            tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
                            if tc_rel:
                                self._log(
                                    level='DEBUG',
                                    category='database',
                                    content=f"API {api_config.id} 用例 {case_name} 重新查询tc_rel后状态: execution_status={tc_rel.execution_status}, evaluation_status={tc_rel.evaluation_status}, status={tc_rel.status}",
                                    task_id=task_id
                                )
                            
                            # 只有执行成功且result_id有效时才提交异步评估
                            if success:
                                if result_id is None:
                                    self._log(
                                        level='ERROR',
                                        category='evaluation',
                                        content=f"API {api_config.id} 用例 {case_name} 评估失败: result_id为None",
                                        task_id=task_id,
                                        api_id=api_config.id
                                    )
                                    # 更新评估状态为failed
                                    if tc_rel:
                                        tc_rel.evaluation_status = 'failed'
                                        if tc_rel.status == 'pending':
                                            tc_rel.status = 'failed'
                                        local_db_session.commit()
                                else:
                                    # 直接使用 algo_result_dict
                                    self._evaluate_result(
                                        task_id=task_id,
                                        result_id=result_id,
                                        test_case_id=test_case_id,
                                        algo_result=algo_result_dict,
                                        case_config=case_config,
                                        algorithm_type=algorithm_type,
                                        test_type='api',
                                        case_algorithm_params=case_algorithm_params
                                    )
                                    
                                    self._log(
                                        level='INFO',
                                        category='evaluation',
                                        content=f"API {api_config.id} 用例 {case_name} 采集完成，已提交评估队列",
                                        task_id=task_id,
                                        api_id=api_config.id
                                    )
                                
                            # 记录用例结果到日志
                            # 使用与E2E一致的方式获取参考参数
                            # 构建参考参数字典，包含 case_config 中的所有参考参数
                            ref_fields = {}
                            
                            # 从 case_config 中提取参考参数
                            if case_config:
                                for key, value in case_config.items():
                                    if value is not None:
                                        ref_fields[key] = value
                            
                            # 从 case_algorithm_params 中提取参考参数
                            if case_algorithm_params:
                                if isinstance(case_algorithm_params, dict):
                                    for key, value in case_algorithm_params.items():
                                        if value is not None:
                                            ref_fields[key] = value
                            
                            # 使用 CaseParameterExtractor 获取动态参考参数
                            from backend.algorithm.case_parameter_extractor import CaseParameterExtractor
                            
                            # 构建评估参数，获取动态参考文本
                            full_case_params = {
                                'algorithm_params': case_algorithm_params or {},
                                'reference_params': case_config.get('reference_params', {}) if case_config else {},
                                'algorithm_type': algorithm_type
                            }
                            eval_params = CaseParameterExtractor.get_evaluation_params(
                                case_config=full_case_params,
                                algorithm_result=algo_result_dict if algo_result_dict else {},
                                test_type='api'
                            )
                            
                            # 将评估参数添加到 ref_fields
                            for key, value in eval_params.items():
                                if value is not None and key not in ref_fields:
                                    if isinstance(value, dict):
                                        ref_fields[key] = value.get('text', '')
                                    else:
                                        ref_fields[key] = value
                            
                            # 构建用于 _log_case_result 的结果对象
                            result_obj = {
                                'device_id': None,
                                'api_id': api_config.id,
                                'success': success,
                                'raw_results': {'success': success}
                            }
                            # 添加算法结果 - 直接使用 algo_result_dict
                            if algo_result_dict:
                                for key, value in algo_result_dict.items():
                                    result_obj[key] = value
                            
                            # 调用 _log_case_result 记录用例结果（包含参考文本）
                            self._log_case_result(task_id, case_name, result_obj, ref_fields, algorithm_type=algorithm_type, test_case_id=test_case_id)
                        except Exception as e:
                            success = False
                            import traceback
                            error_trace = traceback.format_exc()
                            error_msg = f"API {api_config.id} 执行异常: {str(e)}"
                            self._log(
                                level='ERROR',
                                category='execution',
                                content=f"API {api_config.id} 用例 {case_name} 执行失败: {error_msg}\n{error_trace}",
                                task_id=task_id,
                                api_id=api_config.id
                            )
                            
                            # 只更新execution_status为failed，evaluation_status和status在评估完成后更新
                            if tc_rel:
                                if tc_rel.execution_status not in ['stopped']:
                                    tc_rel.execution_status = 'failed'
                                if tc_rel.evaluation_status in ['queued', 'pending']:
                                    tc_rel.evaluation_status = 'completed'
                                    tc_rel.status = 'failed'
                                local_db_session.commit()
                        finally:  # 释放API执行权的finally块
                            # 释放API执行权，允许其他任务执行该API
                            self.release_api_execution_right(api_id, task_id)
                finally:
                    # 关闭主数据库会话
                    local_db_session.close()
                
                # 注意：最终状态更新（evaluation_status和status）由 EvaluationService 的 Worker 在评估完成后异步处理
                return True

        except Exception as e:
            # 捕获整个方法的异常
            import traceback
            error_trace = traceback.format_exc()
            error_msg = f"API 用例执行异常: {str(e)}"
            self._log(
                level='ERROR',
                category='execution',
                content=f"API 用例执行失败: {error_msg}\n{error_trace}",
                task_id=task_id if 'task_id' in locals() else None
            )
            return False
        finally:
            try:
                self._thread_ctx.current_test_case_id = None
            except Exception:
                pass
