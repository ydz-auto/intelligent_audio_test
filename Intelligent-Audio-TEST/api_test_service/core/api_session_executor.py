"""API 多轮会话执行：会话创建、多轮循环、上下文管理、结果聚合"""
import time
import json
import logging
import uuid
import requests as http_requests
from datetime import timezone, timedelta

from shared.utils.dto_utils import dto_to_dict
from shared.utils.status_constants import ExecutionStatus
from api_test_service.infrastructure.acl import (
    TaskDataAclRepositoryImpl,
    AudioConfigAclRepositoryImpl,
    AlgorithmQueryAclRepositoryImpl,
    AdapterAclRepositoryImpl,
    EvaluationAclRepositoryImpl,
)
from api_test_service.core.session_context import SessionContext
from api_test_service.clients.api_driver import APIDriver

# 跨服务出站 gRPC 经 ACL 仓储（返回 DTO），不返回 raw dict
_task_data_acl = TaskDataAclRepositoryImpl()
_audio_acl = AudioConfigAclRepositoryImpl()
_algo_acl = AlgorithmQueryAclRepositoryImpl()
_adapter_acl = AdapterAclRepositoryImpl()
_evaluation_acl = EvaluationAclRepositoryImpl()

logger = logging.getLogger(__name__)


class APISessionExecutor:
    """API 多轮会话执行器"""

    def __init__(self, executor):
        self._executor = executor

    @property
    def _log(self):
        return self._executor._log

    def execute(self, task_id, tc_rel_id, data, case_config):
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
                    round_results
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
                    logger.debug("销毁 session 失败 (api_id=%s)", api_id, exc_info=True)

        return True

    def _run_rounds(self, task_id, tc_rel_id, rounds, api_config, api_specific_config,
                    session, case_algorithm_params, algorithm_type,
                    round_results):
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
                algorithm_type=algorithm_type,
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
        """提交多轮会话评估

        通过 ACL 仓储调用 evaluation_service 的 EvaluationService.EvaluateCase。
        """
        full_case_params = {
            'algorithm_params': case_algorithm_params or {},
            'reference_params': case_config.get('reference_params', {}),
            'algorithm_type': algorithm_type
        }
        all_params = dto_to_dict(_algo_acl.extract_case_all_params(full_case_params)) or {}
        eval_params = all_params.get('evaluation', {}) if isinstance(all_params, dict) else {}
        eval_params['algorithm_type'] = algorithm_type
        eval_params['test_type'] = 'api'

        # 通过 ACL 仓储调用 evaluation_service 的 EvaluateCase
        _evaluation_acl.submit_evaluate_case(
            task_id=task_id,
            result_id=result_id,
            test_case_id=test_case_id,
            algorithm_result=aggregated.get('algorithm_result', {}),
            eval_params=eval_params,
        )

        self._log(level='INFO', category='evaluation',
                  content=f"API {api_id} 用例 {case_name} 多轮会话完成，已提交评估",
                  task_id=task_id, api_id=api_id)

    def _update_tc_rel_running(self, tc_rel_id, utc_plus_8, task_id):
        """更新 TaskCase 状态为 running

        通过 ACL 仓储查询 TaskCase，若状态为 pending/queued 则更新为 running。
        """
        try:
            tcs = [dto_to_dict(d) for d in _task_data_acl.get_task_case_by_ids(task_id)]
            tc_rel = next((tc for tc in tcs if tc.get('id') == tc_rel_id), None)
            if not tc_rel:
                self._log(level='WARNING', content=f"找不到 TaskCase: {tc_rel_id}", task_id=task_id)
                return
            if tc_rel.get('execution_status') not in [ExecutionStatus.PENDING, ExecutionStatus.QUEUED]:
                return

            test_case_id = tc_rel.get('test_case_id')
            if not test_case_id:
                self._log(level='WARNING', content=f"TaskCase {tc_rel_id} 无 test_case_id", task_id=task_id)
                return

            _task_data_acl.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                execution_status=ExecutionStatus.RUNNING,
            )
            self._executor.execution_engine._emit_progress(task_id, force=True)
        except Exception as e:
            self._log(level='WARNING', content=f"更新 TaskCase 状态失败: {e}", task_id=task_id)

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
        """查询音频文件路径（通过 ACL 仓储调用 audio_service.AudioConfigService.GetAudio）"""
        try:
            audio_data = dto_to_dict(_audio_acl.get_audio(audio_id)) or {}
            return audio_data.get('file_path', '')
        except Exception as e:
            self._log(level='WARNING', content=f"查询 Audio {audio_id} 失败: {e}")
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
                            algorithm_type, total_rounds=None):
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
                    api_config, timeout, input_text, input_type, start_time
                )
            else:
                return self._send_direct(
                    task_id, round_number, api_config, meta, rendered_headers,
                    rendered_body, timeout, input_text, input_type, start_time
                )
        except Exception as e:
            latency = time.time() - start_time
            self._log('ERROR', f"Round {round_number} failed: {e}", task_id=task_id)
            return {'round_number': round_number, 'input': input_text, 'output': '',
                    'latency': round(latency, 3), 'error': str(e), 'success': False}

    def _send_via_adapter(self, task_id, algorithm_type, session, round_number, total_rounds,
                          rendered_headers, rendered_body, api_specific_config, meta,
                          api_config, timeout, input_text, input_type, start_time):
        """通过 ACL 仓储调用 adapter 发送请求"""
        from shared.proto import adapter_service_pb2 as adapter_pb

        vendor = api_specific_config.get('vendor', meta.get('vendor', ''))
        vendor_config = {
            'api_url': self._get_vendor_api_url(api_config),
            'headers': rendered_headers,
            'timeout': session.session_timeout,
        }

        # Determine input_data: text content or audio path
        input_type_val = input_type or 'text'
        actual_input = input_text if input_type_val == 'text' else ''

        # Parse translation direction for source/target lang
        translation_direction = api_specific_config.get('translation_direction', '')
        source_lang, target_lang = 'zh', 'en'
        if translation_direction:
            if '2en' in translation_direction:
                source_lang = translation_direction.split('2')[0] or 'zh'
                target_lang = 'en'
            elif '2zh' in translation_direction:
                source_lang = translation_direction.split('2')[0] or 'en'
                target_lang = 'zh'

        req = adapter_pb.SendRoundRequest(
            task_type=algorithm_type,
            session_id=session.session_id,
            round=round_number,
            total_rounds=total_rounds,
            vendor=vendor,
            vendor_config=json.dumps(vendor_config, ensure_ascii=False, default=str),
            context=json.dumps(session.get_context(), ensure_ascii=False, default=str),
            context_for_request=json.dumps(session.get_context_for_request(), ensure_ascii=False, default=str),
            input_data=actual_input,
            input_type=input_type_val,
            source_lang=source_lang,
            target_lang=target_lang,
            algorithm_params=json.dumps(api_specific_config.get('algorithm_params', []), ensure_ascii=False, default=str),
            case_algorithm_params=json.dumps(api_specific_config.get('case_algorithm_params', {}), ensure_ascii=False, default=str),
            translation_direction=translation_direction,
            rendered_body=json.dumps(rendered_body, ensure_ascii=False, default=str),
            rendered_headers=json.dumps(rendered_headers, ensure_ascii=False, default=str),
            timeout=timeout,
        )

        self._log('DEBUG', f"Sending round {round_number} to adapter via gRPC", task_id=task_id)

        round_dto = _adapter_acl.send_round(req)
        task_result = dto_to_dict(round_dto) or {}

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
