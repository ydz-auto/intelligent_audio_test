"""API 多轮会话执行：会话创建、多轮循环、上下文管理、结果聚合"""
import time
import json
import uuid
import requests as http_requests
from datetime import datetime, timezone, timedelta

from shared.models.models import TaskCase, Audio
from shared.models.database import db
from task_service.core.session_context import SessionContext
from task_service.clients.api_driver import APIDriver
from shared.utils.config_manager import config_manager


class APISessionExecutor:
    """API 多轮会话执行器"""

    def __init__(self, executor):
        self._executor = executor

    @property
    def _log(self):
        return self._executor._log

    def execute(self, app, task_id, tc_rel_id, data, case_config):
        """多轮会话执行（配置驱动，不绑定算法类型）"""
        case_name = data['case_name']
        test_case_id = data['test_case_id']
        algorithm_type = data.get('algorithm_type', 'voice_llm')
        api_configs = data['api_configs']
        api_specific_config = data['api_specific_config']
        case_algorithm_params = data.get('case_algorithm_params')

        rounds = case_config.get('rounds', [])
        session_config = case_config.get('session', {})
        session_timeout = session_config.get('sessionTimeout', 60)
        context_mode = session_config.get('contextMode', 'full')
        max_history_rounds = session_config.get('maxHistoryRounds', 5)

        adapter_base_url = config_manager.get_value('api_adapter', 'base_url', 'http://localhost:8000')
        utc_plus_8 = timezone(timedelta(hours=8))

        self._log(level='INFO',
                  content=f"开始多轮会话执行: {case_name}, 共 {len(rounds)} 轮, "
                          f"timeout={session_timeout}s, context_mode={context_mode}",
                  task_id=task_id, test_case_id=test_case_id)

        for api_config in api_configs:
            self._executor._handle_control(task_id)
            api_id = api_config.id

            max_process = getattr(api_config, 'default_max_process', 5) or 5
            if not self._executor._concurrency.acquire(api_id, task_id, tc_rel_id, max_process=max_process):
                self._log(level='ERROR', content=f"API {api_id} 执行权获取失败，跳过",
                          task_id=task_id, api_id=api_id)
                continue

            self._update_tc_rel_running(tc_rel_id, utc_plus_8, task_id)

            try:
                session = SessionContext(
                    session_id=str(uuid.uuid4()),
                    config={'session_timeout': session_timeout,
                            'context_mode': context_mode,
                            'max_history_rounds': max_history_rounds}
                )
                self._log(level='INFO', content=f"创建会话 {session.session_id} 用于 API {api_id}",
                          task_id=task_id, api_id=api_id)

                round_results = []
                all_rounds_success = self._run_rounds(
                    task_id, tc_rel_id, rounds, api_config, api_specific_config,
                    session, case_algorithm_params, algorithm_type,
                    adapter_base_url, round_results
                )

                aggregated = self._aggregate_round_results(round_results, session)
                result_id = self._executor._result_processor.create_multi_round_test_result(
                    task_id=task_id, test_case_id=test_case_id, api_config_id=api_id,
                    algorithm_type=algorithm_type, aggregated=aggregated, success=all_rounds_success
                )

                if result_id and all_rounds_success:
                    self._submit_evaluation(task_id, result_id, test_case_id, case_name,
                                           case_config, case_algorithm_params,
                                           algorithm_type, aggregated, api_id)

            except Exception as e:
                import traceback
                error_msg = f"API {api_id} 多轮会话执行异常: {str(e)}"
                self._log(level='ERROR', content=f"{error_msg}\n{traceback.format_exc()}",
                          task_id=task_id, api_id=api_id)
                self._executor._result_processor.update_task_case_failure(task_id, tc_rel_id, error_msg, utc_plus_8)
            finally:
                self._executor._concurrency.release(api_id, task_id)
                try:
                    if 'session' in locals():
                        session.destroy()
                except Exception:
                    pass

        return True

    def _run_rounds(self, task_id, tc_rel_id, rounds, api_config, api_specific_config,
                    session, case_algorithm_params, algorithm_type,
                    adapter_base_url, round_results):
        """执行多轮循环，返回 all_rounds_success"""
        all_rounds_success = True

        for round_idx, round_config in enumerate(rounds):
            if not isinstance(round_config, dict):
                continue

            self._executor._handle_control(task_id)
            round_number = round_config.get('round_number', round_idx + 1)

            self._executor.execution_engine.update_case_round_progress(
                task_id, tc_rel_id, round_idx, len(rounds)
            )

            self._log(level='INFO', content=f"执行第 {round_number}/{len(rounds)} 轮",
                      task_id=task_id, api_id=api_config.id)

            round_result = self._send_round_request(
                task_id=task_id, api_config=api_config,
                api_specific_config=api_specific_config, session=session,
                round_number=round_number, round_config=round_config,
                case_algorithm_params=case_algorithm_params,
                algorithm_type=algorithm_type, adapter_base_url=adapter_base_url,
                total_rounds=len(rounds)
            )

            if round_result and not round_result.get('error'):
                input_text = round_result.get('input', '')
                output_text = round_result.get('output', '')
                session.add_history(round_number, input_text, output_text)
                session.add_round_result(round_result)
                round_results.append(round_result)
                self._log(level='INFO',
                          content=f"第 {round_number} 轮完成, latency={round_result.get('latency', 0):.2f}s",
                          task_id=task_id, api_id=api_config.id)
            else:
                error_msg = round_result.get('error', '未知错误') if round_result else '请求返回空结果'
                self._log(level='ERROR', content=f"第 {round_number} 轮失败: {error_msg}",
                          task_id=task_id, api_id=api_config.id)
                round_results.append(round_result or {
                    'round_number': round_number, 'error': error_msg, 'success': False
                })
                all_rounds_success = False

        return all_rounds_success

    def _submit_evaluation(self, task_id, result_id, test_case_id, case_name,
                           case_config, case_algorithm_params,
                           algorithm_type, aggregated, api_id):
        """提交多轮会话评估"""
        from task_service.evaluation.evaluation_service import evaluation_service
        from task_service.algorithm.case_parameter_extractor import CaseParameterExtractor

        full_case_params = {
            'algorithm_params': case_algorithm_params or {},
            'reference_params': case_config.get('reference_params', {}),
            'algorithm_type': algorithm_type
        }
        eval_params = CaseParameterExtractor.get_evaluation_params(
            case_config=full_case_params,
            algorithm_result=aggregated.get('algorithm_result', {}),
            test_type='api'
        )
        eval_params['algorithm_type'] = algorithm_type
        eval_params['test_type'] = 'api'

        evaluation_service.evaluate_case(
            task_id, result_id, test_case_id,
            aggregated.get('algorithm_result', {}),
            **eval_params
        )

        self._log(level='INFO', category='evaluation',
                  content=f"API {api_id} 用例 {case_name} 多轮会话完成，已提交评估",
                  task_id=task_id, api_id=api_id)

    def _update_tc_rel_running(self, tc_rel_id, utc_plus_8, task_id):
        """更新 TaskCase 状态为 running"""
        local_db_session = db.session()
        try:
            tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
            if tc_rel and tc_rel.execution_status in ['pending', 'queued']:
                tc_rel.execution_status = 'running'
                if not tc_rel.started_at:
                    tc_rel.started_at = datetime.now(utc_plus_8)
                local_db_session.commit()
                self._executor.execution_engine._emit_progress(task_id, force=True)
        except Exception as e:
            self._log(level='WARNING', content=f"更新 TaskCase 状态失败: {e}", task_id=task_id)
            local_db_session.rollback()
        finally:
            local_db_session.close()

    def _build_round_context(self, session, round_number, round_config, total_rounds,
                             case_algorithm_params, algorithm_type, audio=None, case_name=''):
        """构建单轮上下文"""
        round_algo_params = round_config.get('algorithm_params', [])

        input_text = ''
        for param in round_algo_params:
            fc = param.get('field_code', '')
            fv = param.get('field_value', '')
            if fc == 'input_text':
                input_text = fv

        input_audio_path = self._get_round_audio_path(round_config)

        context = {
            'session_id': session.session_id,
            'round_number': round_number,
            'total_rounds': total_rounds,
            'context_history': session.get_context(),
            'context_for_request': session.get_context_for_request(),
            'input_text': input_text,
            'input_audio': input_audio_path,
            'algorithm_type': algorithm_type,
            'case_name': case_name,
            'timestamp': int(time.time()),
        }

        for param in round_algo_params:
            fc = param.get('field_code', '')
            fv = param.get('field_value', '')
            if fc and fc not in context:
                context[fc] = fv

        return context

    def _get_round_audio_path(self, round_config):
        """从 round_config 获取音频路径"""
        audios = round_config.get('audios', [])
        if isinstance(audios, list) and audios:
            first_audio = audios[0] if isinstance(audios[0], dict) else {}
            audio_id = first_audio.get('audio_id')
            if audio_id:
                return self._query_audio_path(audio_id)

        audio_id = round_config.get('audio_id')
        if audio_id:
            return self._query_audio_path(audio_id)
        return ''

    def _query_audio_path(self, audio_id):
        """查询音频文件路径"""
        local_db_session = db.session()
        try:
            audio_obj = local_db_session.query(Audio).get(audio_id)
            if audio_obj:
                return audio_obj.file_path
        finally:
            local_db_session.close()
        return ''

    def _get_vendor_api_url(self, api_config):
        """获取供应商 API URL"""
        if hasattr(api_config, 'api_endpoints') and api_config.api_endpoints:
            for ep in api_config.api_endpoints:
                if ep.get('endpoint'):
                    return ep['endpoint']
        if hasattr(api_config, 'api_url'):
            return api_config.api_url
        return None

    def _send_round_request(self, task_id, api_config, api_specific_config, session,
                            round_number, round_config, case_algorithm_params,
                            algorithm_type, adapter_base_url, total_rounds=None):
        """发送单轮请求"""
        if total_rounds is None:
            total_rounds = round_number

        context_data = self._build_round_context(
            session=session, round_number=round_number, round_config=round_config,
            total_rounds=total_rounds, case_algorithm_params=case_algorithm_params,
            algorithm_type=algorithm_type, case_name=''
        )

        driver = APIDriver(api_config, api_specific_config, task_id=task_id)
        rendered_headers, rendered_body = driver.render_request_parts(context_data)

        meta = api_config.meta or {}
        use_adapter = meta.get('use_adapter', True)
        timeout = session.session_timeout + 10

        input_text = context_data.get('input_text', '')
        input_type = round_config.get('input_type', 'text')
        start_time = time.time()

        try:
            if use_adapter:
                return self._send_via_adapter(
                    task_id, algorithm_type, session, round_number, total_rounds,
                    rendered_headers, rendered_body, api_specific_config, meta,
                    api_config, adapter_base_url, timeout, input_text, input_type, start_time
                )
            else:
                return self._send_direct(
                    task_id, round_number, api_config, meta, rendered_headers,
                    rendered_body, timeout, input_text, input_type, start_time
                )
        except http_requests.Timeout:
            latency = time.time() - start_time
            self._log('WARNING', f"Round {round_number} timeout ({session.session_timeout}s)", task_id=task_id)
            return {'round_number': round_number, 'input': input_text, 'output': '',
                    'latency': round(latency, 3), 'error': 'timeout', 'success': False}
        except http_requests.RequestException as e:
            latency = time.time() - start_time
            self._log('ERROR', f"Round {round_number} failed: {e}", task_id=task_id)
            return {'round_number': round_number, 'input': input_text, 'output': '',
                    'latency': round(latency, 3), 'error': str(e), 'success': False}

    def _send_via_adapter(self, task_id, algorithm_type, session, round_number, total_rounds,
                          rendered_headers, rendered_body, api_specific_config, meta,
                          api_config, adapter_base_url, timeout, input_text, input_type, start_time):
        """通过 adapter 发送请求"""
        adapter_request = {
            'task_type': algorithm_type,
            'session_id': session.session_id,
            'round': round_number,
            'total_rounds': total_rounds,
            'rendered_body': rendered_body,
            'rendered_headers': rendered_headers,
            'context': session.get_context(),
            'context_for_request': session.get_context_for_request(),
            'vendor': api_specific_config.get('vendor', meta.get('vendor', '')),
            'vendor_config': {
                'api_url': self._get_vendor_api_url(api_config),
                'headers': rendered_headers,
                'timeout': session.session_timeout
            }
        }

        adapter_url = f"{adapter_base_url.rstrip('/')}/api/v1/tasks"
        self._log('DEBUG', f"Sending round {round_number} to adapter: {adapter_url}", task_id=task_id)

        response = http_requests.post(adapter_url, json=adapter_request, timeout=timeout)
        response.raise_for_status()
        task_result = response.json()

        latency = time.time() - start_time
        output_text = task_result.get('output_content', task_result.get('output', ''))

        return {
            'round_number': round_number, 'input': input_text, 'input_type': input_type,
            'output': output_text, 'output_audio_path': task_result.get('output_audio_path'),
            'latency': round(latency, 3), 'response_metrics': task_result.get('response_metrics', {}),
            'success': True, 'raw_response': task_result
        }

    def _send_direct(self, task_id, round_number, api_config, meta, rendered_headers,
                     rendered_body, timeout, input_text, input_type, start_time):
        """直接发送请求到供应商"""
        vendor_url = self._get_vendor_api_url(api_config)
        endpoint = rendered_body.get('endpoint', vendor_url) if isinstance(rendered_body, dict) else vendor_url

        self._log('DEBUG', f"Sending round {round_number} directly to vendor: {endpoint}", task_id=task_id)

        method = meta.get('method', 'POST').upper()
        response = http_requests.request(
            method=method, url=endpoint, headers=rendered_headers,
            json=rendered_body if method != 'GET' else None,
            params=rendered_body if method == 'GET' else None,
            timeout=timeout
        )
        response.raise_for_status()
        task_result = response.json()

        latency = time.time() - start_time
        output_text = task_result.get('output_content', task_result.get('output', ''))

        return {
            'round_number': round_number, 'input': input_text, 'input_type': input_type,
            'output': output_text, 'latency': round(latency, 3),
            'success': True, 'raw_response': task_result
        }

    def _aggregate_round_results(self, round_results, session):
        """汇总多轮会话结果"""
        total_latency = sum(r.get('latency', 0) for r in round_results)
        success_count = sum(1 for r in round_results if r.get('success', False))
        total_count = len(round_results)

        all_outputs = [r.get('output', '') for r in round_results if r.get('output')]
        combined_output = ' '.join(all_outputs)

        algorithm_result = {
            'text_output': combined_output,
            'round_count': total_count,
            'success_count': success_count,
            'total_latency': round(total_latency, 3),
            'avg_latency': round(total_latency / total_count, 3) if total_count > 0 else 0,
            'session_id': session.session_id,
            'rounds': round_results
        }

        return {
            'success': success_count == total_count,
            'algorithm_result': algorithm_result,
            'total_latency': total_latency,
            'round_count': total_count,
            'session_summary': session.get_summary()
        }
