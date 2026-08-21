"""API 单轮任务执行：端点设置、健康检查、创建任务、等待完成、获取结果、删除任务"""
import time
import os
import json
import random

from backend.utils.clients.api_driver import APIDriver
from backend.utils.algorithm.field_mapper import get_field_mapper
from backend.utils.common.config_manager import config_manager


class APITaskRunner:
    """API 单轮任务执行器"""

    def __init__(self, executor):
        self._executor = executor

    @property
    def _log(self):
        return self._executor._log

    def setup_endpoints(self, task_id, tc_rel_id, case_name, api_config, current_app):
        """设置 API 端点和负载均衡"""
        api_paths = current_app.config.get('API_PATHS', {
            'health': '/health',
            'status': '/api/status',
            'create_task': '/api/create_task',
            'get_status': '/api/get_status/{task_id}',
            'get_frame_results': '/api/get_frame_results/{task_id}',
            'get_final_result': '/api/get_final_result/{task_id}',
            'delete_task': '/api/delete_task/{task_id}'
        })

        base_urls = []
        endpoints = api_config.api_endpoints if hasattr(api_config, 'api_endpoints') and api_config.api_endpoints else []
        main_url = api_config.endpoint if hasattr(api_config, 'endpoint') and api_config.endpoint else ''

        if main_url:
            base_urls = [main_url.rstrip('/')]
        elif endpoints:
            base_urls = [ep.get('endpoint', '').rstrip('/') for ep in endpoints if ep.get('endpoint')]
        else:
            base_urls = ['']

        engine = self._executor.execution_engine
        with engine.api_entry_lock:
            for url in base_urls:
                if url not in engine.api_entry_status:
                    engine.api_entry_status[url] = {'available': True, 'fail_count': 0}

        def select_base_url():
            with engine.api_entry_lock:
                available_urls = [url for url in base_urls
                                  if engine.api_entry_status.get(url, {}).get('available', True)]
                if not available_urls:
                    available_urls = base_urls
                return random.choice(available_urls) if available_urls else None

        def release_base_url(url):
            pass

        return api_paths, select_base_url, release_base_url

    def health_check(self, task_id, case_name, audio, api_config, api_specific_config, api_paths, select_base_url, release_base_url):
        """执行健康检查"""
        self._executor._handle_control(task_id)
        context = {
            "case_name": case_name,
            "audio_id": audio.get('id') if audio else None,
            "asr_ref": audio.get('asr_text', '') if audio else "",
            "timestamp": int(time.time())
        }

        audio_file_path = audio.get('file_path', '') if audio else ''
        if audio_file_path:
            audio_file_path = os.path.normpath(audio_file_path)

        if not audio or not os.path.exists(audio_file_path):
            error_msg = f"音频文件不存在: {audio_file_path}"
            self._log('ERROR', error_msg, task_id, api_config=api_config)
            raise Exception(error_msg)

        health_url = None
        main_url = api_config.endpoint if hasattr(api_config, 'endpoint') and api_config.endpoint else ''
        selected_url_for_health = None

        if main_url and main_url.startswith('http'):
            health_url = f"{main_url.rstrip('/')}{api_paths['health']}"
        else:
            selected_url_for_health = select_base_url()
            if selected_url_for_health and selected_url_for_health.startswith('http'):
                health_url = f"{selected_url_for_health.rstrip('/')}{api_paths['health']}"
            else:
                health_url = api_paths['health']

        self._log('INFO', f"执行健康检查: {health_url}", task_id, api_config=api_config)

        try:
            health_driver = APIDriver(api_config, api_specific_config, endpoint=health_url)
            health_result = health_driver.execute({}, method='GET')
            if not health_result['success']:
                status_code = health_result.get('status_code', 0)
                if status_code in [404, 405]:
                    self._log('WARNING', f"健康检查路径不存在({status_code})，跳过: {health_url}", task_id, api_config=api_config)
                else:
                    error_msg = f"健康检查失败: {health_result['error']}"
                    self._log('ERROR', error_msg, task_id, api_config=api_config)
                    raise Exception(error_msg)
            else:
                health_data = health_result.get('json', {})
                health_status = health_data.get('status', '')
                if health_status and health_status not in ('healthy', 'success'):
                    raise Exception(f"健康检查失败: 服务状态异常 - {health_status}")
                self._log('INFO', f"健康检查成功，服务状态: {health_status or 'ok'}", task_id, api_config=api_config)
        finally:
            if selected_url_for_health:
                release_base_url(selected_url_for_health)

        return context

    def create_task(self, task_id, audio, api_config, api_specific_config, api_paths, select_base_url, release_base_url, algorithm_type='translation'):
        """创建 API 任务"""
        self._executor._handle_control(task_id)
        selected_url = select_base_url()
        create_task_url = f"{selected_url}{api_paths['create_task']}"
        self._log('INFO', f"创建任务: {create_task_url}", task_id, api_config=api_config)

        try:
            create_task_driver = APIDriver(api_config, api_specific_config, endpoint=create_task_url)

            audio_path = audio.get('file_path')
            if audio_path:
                audio_path = os.path.normpath(audio_path)

            vendor = api_specific_config.get('vendor')
            if not vendor and hasattr(api_config, 'vendor') and api_config.vendor:
                vendor = api_config.vendor
            if not vendor and hasattr(api_config, 'meta') and isinstance(api_config.meta, dict):
                vendor = api_config.meta.get('vendor')
            if not vendor:
                vendor = "volc_ast"

            endpoints = []
            if hasattr(api_config, 'api_endpoints') and api_config.api_endpoints:
                endpoints = [ep for ep in api_config.api_endpoints if ep.get('endpoint')]

            max_process = getattr(api_config, 'default_max_process', None) or config_manager.get_value('api_executor', 'default_max_process', 5)
            max_timeout = getattr(api_config, 'max_timeout', 30) or 30

            field_mapper = get_field_mapper()
            case_config = api_specific_config.get('case_config', {})

            create_task_data = field_mapper.build_create_task_data(
                algorithm_type=algorithm_type,
                case_config=case_config,
                audio_path=audio_path,
                vendor=vendor,
                max_process=max_process,
                max_timeout=max_timeout,
                endpoints=endpoints
            )

            if 'audio_path' not in create_task_data:
                create_task_data['audio_path'] = audio_path

            self._log(level='DEBUG', content=f"创建任务请求数据: {json.dumps(create_task_data, ensure_ascii=False)}",
                      task_id=task_id, api_config=api_config)

            create_task_result = create_task_driver.execute(create_task_data)

            result_for_log = create_task_result.copy()
            if 'raw_response' in result_for_log and isinstance(result_for_log['raw_response'], str):
                try:
                    result_for_log['raw_response'] = json.loads(result_for_log['raw_response'])
                except Exception:
                    pass

            self._log(level='DEBUG', content=f"创建任务响应结果: {json.dumps(result_for_log, ensure_ascii=False)}",
                      task_id=task_id, api_config=api_config)

            if not create_task_result['success']:
                biz_code = create_task_result.get('biz_code')
                biz_msg = create_task_result.get('biz_msg')
                if biz_code is not None:
                    error_msg = f"创建任务失败: BizError[{biz_code}] - {biz_msg}"
                elif create_task_result['error']:
                    error_msg = f"创建任务失败: {create_task_result['error']}"
                else:
                    error_msg = f"创建任务失败: HTTP {create_task_result['status_code']} - {create_task_result['raw_response']}"
                self._log('ERROR', error_msg, task_id, api_config=api_config)
                raise Exception(error_msg)

            api_task_id = create_task_result.get('json', {}).get('data', {}).get('task_id')
            if not api_task_id:
                error_msg = "创建任务成功，但未返回task_id"
                self._log('ERROR', error_msg, task_id, api_config=api_config)
                raise Exception(error_msg)

            self._log('INFO', f"创建任务成功，task_id: {api_task_id}", task_id, api_config=api_config)
            return api_task_id
        finally:
            release_base_url(selected_url)

    def wait_for_completion(self, task_id, api_task_id, api_config, api_specific_config, api_paths,
                            select_base_url, release_base_url, current_app, total_audio_duration):
        """异步轮询等待任务完成"""
        dynamic_max_wait_time = total_audio_duration * 1.5
        default_max_wait_time = current_app.config.get('API_MAX_WAIT_TIME', 43200)
        max_wait_time = min(dynamic_max_wait_time, default_max_wait_time)
        poll_interval = current_app.config.get('API_POLL_INTERVAL', 5)
        max_wait_time = max(max_wait_time, 30)
        max_wait_time = max(max_wait_time, poll_interval * 2)
        start_wait_time = time.time()
        task_status = 'running'

        self._log(level='INFO',
                  content=f"开始等待任务 {api_task_id} 完成，最大等待时间: {max_wait_time}秒，轮询间隔: {poll_interval}秒",
                  task_id=task_id, api_config=api_config)

        while True:
            self._executor._handle_control(task_id)
            elapsed_time = time.time() - start_wait_time
            if elapsed_time > max_wait_time:
                error_msg = f"任务 {api_task_id} 执行超时，已等待 {elapsed_time:.0f}秒"
                self._log('ERROR', error_msg, task_id, api_config=api_config)
                raise Exception(error_msg)

            selected_url = select_base_url()
            get_status_url = f"{selected_url}{api_paths['get_status'].replace('{task_id}', api_task_id)}"

            try:
                self._log(level='INFO',
                          content=f"查询任务状态: {get_status_url} (已等待: {elapsed_time:.0f}秒)",
                          task_id=task_id, api_config=api_config)
                get_status_driver = APIDriver(api_config, api_specific_config, endpoint=get_status_url)
                get_status_result = get_status_driver.execute({'task_id': api_task_id}, method='GET')

                if not get_status_result['success']:
                    biz_code = get_status_result.get('biz_code')
                    biz_msg = get_status_result.get('biz_msg')
                    status_code = get_status_result.get('status_code', 0)

                    if biz_code is not None:
                        error_msg = f"查询任务状态失败: BizError[{biz_code}] - {biz_msg}"
                    elif get_status_result['error']:
                        error_msg = f"查询任务状态失败: {get_status_result['error']}"
                    else:
                        error_msg = f"查询任务状态失败: HTTP {status_code} - {get_status_result['raw_response']}"

                    if status_code in [400, 404, 500] or biz_code in [400, 404]:
                        self._log('ERROR', f"查询任务状态永久失败，终止等待: {error_msg}", task_id, api_config=api_config)
                        raise Exception(f"任务 {api_task_id} 查询失败: {error_msg}")
                    else:
                        self._log('WARNING', f"查询任务状态失败，将重试: {error_msg}", task_id, api_config=api_config)
                        continue

                status_data = get_status_result.get('json', {}).get('data', {})
                if not status_data:
                    status_data = get_status_result.get('json', {})
                task_status = status_data.get('status', 'running')
                progress = status_data.get('progress', 0)

                self._log(level='INFO',
                          content=f"任务 {api_task_id} 状态: {task_status}, 进度: {progress}%",
                          task_id=task_id, api_config=api_config)

                if task_status in ['completed', 'success', 'failed', 'error', 'pending']:
                    break
            finally:
                release_base_url(selected_url)

            self._log(level='INFO', content=f"等待 {poll_interval} 秒后再次查询任务状态", task_id=task_id)
            sleep_end = time.time() + poll_interval
            while time.time() < sleep_end:
                self._executor._handle_control(task_id)
                time.sleep(min(0.5, sleep_end - time.time()))

        if task_status in ['failed', 'error', 'pending']:
            error_msg = f"任务 {api_task_id} 执行失败，状态: {task_status}"
            self._log('ERROR', error_msg, task_id=task_id)
            return start_wait_time, False, error_msg

        return start_wait_time, True, None

    def get_final_result(self, task_id, api_task_id, api_config, api_specific_config, api_paths, select_base_url, release_base_url):
        """查询最终结果"""
        self._executor._handle_control(task_id)
        self._log(level='INFO', content=f"任务 {api_task_id} 执行完成，开始查询最终结果",
                  task_id=task_id, api_config=api_config)

        selected_url = select_base_url()
        get_final_result_url = f"{selected_url}{api_paths['get_final_result'].replace('{task_id}', api_task_id)}"
        self._log(level='INFO', content=f"查询最终结果: {get_final_result_url}",
                  task_id=task_id, api_config=api_config)

        try:
            driver = APIDriver(api_config, api_specific_config, endpoint=get_final_result_url)
            final_result_result = driver.execute({'task_id': api_task_id}, method='GET')
            if not final_result_result['success']:
                biz_code = final_result_result.get('biz_code')
                biz_msg = final_result_result.get('biz_msg')
                if biz_code is not None:
                    error_msg = f"查询最终结果失败: BizError[{biz_code}] - {biz_msg}"
                elif final_result_result['error']:
                    error_msg = f"查询最终结果失败: {final_result_result['error']}"
                else:
                    error_msg = f"查询最终结果失败: HTTP {final_result_result['status_code']} - {final_result_result['raw_response']}"
                self._log('ERROR', error_msg, task_id, api_config=api_config)
                raise Exception(error_msg)

            self._log('INFO', "查询最终结果成功", task_id, api_config=api_config)
            return final_result_result
        finally:
            release_base_url(selected_url)

    def get_frame_results(self, task_id, api_task_id, api_config, api_specific_config, api_paths, select_base_url, release_base_url):
        """查询帧结果（可选，仅用于调试）"""
        try:
            selected_url = select_base_url()
            url = f"{selected_url}{api_paths['get_frame_results'].replace('{task_id}', api_task_id)}"
            self._log('INFO', f"查询帧结果: {url}", task_id, api_config=api_config)
            driver = APIDriver(api_config, api_specific_config, endpoint=url)
            result = driver.execute({'page': 1, 'page_size': 5}, method='GET')
            if result['success']:
                count = len(result.get('json', {}).get('data', []))
                self._log('INFO', f"查询帧结果成功，共获取 {count} 帧", task_id, api_config=api_config)
            else:
                self._log('WARNING', f"查询帧结果失败 (非致命): {result['error']}", task_id, api_config=api_config)
        except Exception as e:
            self._log('WARNING', f"查询帧结果异常 (非致命): {str(e)}", task_id, api_config=api_config)
        finally:
            release_base_url(selected_url)

    def delete_task(self, task_id, api_task_id, api_config, api_specific_config, api_paths, select_base_url, release_base_url):
        """删除远程任务"""
        try:
            selected_url = select_base_url()
            url = f"{selected_url}{api_paths['delete_task'].replace('{task_id}', api_task_id)}"
            self._log('INFO', f"删除远程任务: {url}", task_id, api_config=api_config)
            driver = APIDriver(api_config, api_specific_config, endpoint=url)
            result = driver.execute({}, method='DELETE')
            if result['success']:
                self._log('INFO', f"删除远程任务成功: {api_task_id}", task_id, api_config=api_config)
            else:
                self._log('WARNING', f"删除远程任务失败 (非致命): {result.get('error')}", task_id, api_config=api_config)
        except Exception as e:
            self._log('WARNING', f"删除远程任务异常 (非致命): {str(e)}", task_id, api_config=api_config)
        finally:
            release_base_url(selected_url)

    def extract_final_result(self, task_id, final_result_result, algorithm_type='translation'):
        """提取最终结果 — 使用字段映射器动态获取字段"""
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
                self._log('WARNING', f"解析raw_response失败: {str(e)}", task_id=task_id)

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
        return algo_results, latency
