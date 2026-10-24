"""API 多轮会话执行：会话创建、多轮循环、上下文管理、结果聚合"""
import time
import json
import logging
import uuid
import requests as http_requests
from datetime import timezone, timedelta

from shared.utils.dto_utils import dto_to_dict
from shared.utils.status_constants import ExecutionStatus, EvaluationStatus
from shared.utils.query_utils import now_cst
from shared.utils.config_manager import config_manager
from shared.utils.api_key_provider import resolver_from_config
from api_test_service.application.round_render_service import RoundRenderService
from api_test_service.domain.entities.api import resolve_audio_sample_rate
from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
from api_test_service.infrastructure.acl import (
    TaskDataAclRepositoryImpl,
    AudioConfigAclRepositoryImpl,
    AudioRenderACLRepositoryImpl,
    AlgorithmQueryAclRepositoryImpl,
    EvaluationAclRepositoryImpl,
)
from api_test_service.infrastructure.persistence.api_rms_spl_repository import (
    ApiRmsSplRepositoryImpl,
)
from api_test_service.core.session_context import SessionContext
from api_test_service.infrastructure.adapters import vendor_adapter_registry

# 跨服务出站 gRPC 经 ACL 仓储（返回 DTO），不返回 raw dict
_task_data_acl = TaskDataAclRepositoryImpl()
_algo_acl = AlgorithmQueryAclRepositoryImpl()
_evaluation_acl = EvaluationAclRepositoryImpl()

# 密钥链解析器（UC-0901 扩展流程 3a）：各级键名/环境变量名经
# config_manager secrets 段配置，默认 case_config.api_key → meta.api_key
# → env OPENAI_API_KEY 逐级回退
_key_resolver = resolver_from_config(config_manager.get_value)

logger = logging.getLogger(__name__)


class APISessionExecutor:
    """API 多轮会话执行器"""

    def __init__(self, executor):
        self._executor = executor
        # 混音渲染经 ACL 端口出站（RenderService 消费链路，INT-82 接线）
        self._render_service = RoundRenderService(
            AudioRenderACLRepositoryImpl(), spl_repo=ApiRmsSplRepositoryImpl(),
            audio_acl=AudioConfigAclRepositoryImpl())
        # 输出侧实测口径（INT-300 F3 对称补齐）：与 RealtimeSessionExecutor
        # 同源服务对（被测 API 数字域 RMS→SPL），AI 输出音频落库证据
        self._spl_repo = ApiRmsSplRepositoryImpl()
        self._spl_service = ApiRmsSplService(self._spl_repo)

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

            # INT-305：用例被移除（执行中删除）→ 本用例静默收敛
            _is_removed = getattr(self._executor, '_is_case_removed', None)
            if _is_removed and _is_removed(task_id, test_case_id):
                self._log(level='INFO', content=f"用例 {case_name} 已被移除，中断会话执行",
                          task_id=task_id, test_case_id=test_case_id)
                return False

            api_id = api_config.id

            # 并发参数配置化：api_config 未配置时回退到 config_manager 默认值
            max_process = getattr(api_config, 'default_max_process', None) or config_manager.get_value('api_executor', 'default_max_process', 5)
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
                    round_results, case_config
                )

                aggregated = self._aggregate_round_results(
                    round_results, session, api_config=api_config, task_id=task_id)
                result_id = self._executor._result_processor.create_multi_round_test_result(
                    task_id=task_id, test_case_id=test_case_id, api_config_id=api_id,
                    algorithm_type=algorithm_type, aggregated=aggregated, success=all_rounds_success
                )

                if result_id and all_rounds_success:
                    # INT-123：评估提交失败不降级执行终态——执行已完成的事实
                    # 保留在 execution_status，失败由 evaluation_status 终态
                    # 承载（对齐 INT-107/INT-115 评估侧终态口径），不再把整例
                    # 打成 execution failed
                    try:
                        self._submit_evaluation(task_id, result_id, test_case_id, case_name,
                                               case_config, case_algorithm_params,
                                               algorithm_type, aggregated, api_id)
                    except Exception as eval_err:
                        self._finalize_evaluation_submit_failure(
                            task_id, test_case_id, api_id, eval_err)

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

    def _finalize_evaluation_submit_failure(self, task_id, test_case_id, api_id, eval_err):
        """评估提交失败收口（INT-123）：不动 execution_status，仅补评估终态

        execution_status 已由 create_multi_round_test_result 写为 COMPLETED，
        此处只把 evaluation_status 置 FAILED 并留痕原因，复合状态由
        task_service 按 derive_task_case_status(completed, failed) 推导，
        保留"执行成功、评估失败"的事实边界。
        """
        import traceback
        error_msg = f"API {api_id} 多轮会话评估提交失败: {eval_err}"
        self._log(level='ERROR', content=f"{error_msg}\n{traceback.format_exc()}",
                  task_id=task_id, test_case_id=test_case_id, api_id=api_id)
        try:
            _task_data_acl.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                evaluation_status=EvaluationStatus.FAILED,
                error_message=error_msg,
            )
        except Exception as status_err:
            self._log(level='WARNING',
                      content=f"评估失败终态回写失败: {status_err}",
                      task_id=task_id, test_case_id=test_case_id, api_id=api_id)

    def _run_rounds(self, task_id, tc_rel_id, rounds, api_config, api_specific_config,
                    session, case_algorithm_params, algorithm_type,
                    round_results, case_config=None):
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
                algorithm_type=algorithm_type, case_config=case_config,
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
        # 算法服务不可达时 ACL 回退 ExtractedCaseParamsDTO()（evaluation=None），
        # 键存在但值为 None，get 默认值不生效 → 显式 None 兜底（INT-119）
        eval_params = (all_params.get('evaluation') or {}) if isinstance(all_params, dict) else {}
        if not eval_params:
            # INT-118：评估参数提取为空（算法服务失败 / 该算法类型无 evaluation
            # param mappings）显式告警，评估降级可观察，不再静默空参提交
            self._log(level='WARNING', category='evaluation',
                      content=f"用例 {case_name} 评估参数提取为空"
                              f"（算法服务不可达或算法类型 {algorithm_type} 无 evaluation param mappings），"
                              f"评估将以空参数提交",
                      task_id=task_id, test_case_id=test_case_id, api_id=api_id)
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
                started_at=now_cst().isoformat(),
            )
            self._executor.execution_engine._emit_progress(task_id, force=True)
        except Exception as e:
            self._log(level='WARNING', content=f"更新 TaskCase 状态失败: {e}", task_id=task_id)

    def _build_round_context(self, session, round_number, round_config, total_rounds,
                             case_algorithm_params, algorithm_type, case_name='',
                             api_config=None, case_config=None, task_id=None):
        """构建单轮上下文"""
        round_algo_params = round_config.get('algorithm_params', [])

        input_text = ''
        for param in round_algo_params:
            fc = param.get('field_code', '')
            fv = param.get('field_value', '')
            if fc == 'input_text':
                input_text = fv

        input_audio_path = self._get_round_audio_path(
            api_config, round_config, case_config, task_id, round_number)

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

    def _get_round_audio_path(self, api_config, round_config, case_config,
                              task_id, round_number):
        """轮次音频路径：整段混音（RenderAudioFile 经 ACL）产物落存储后引用。

        仅当轮次配置了音频内容时触发混音；混音 6 步全部发生在
        RenderService 消费链路内，渲染失败抛错由轮次级收敛为轮次失败，
        不静默回退原始音频路径。
        """
        audios = [a for a in (round_config.get('audios') or [])
                  if isinstance(a, dict) and a.get('audio_id')]
        if not audios and not round_config.get('audio_id'):
            return ''   # 纯文本轮：无音频内容，不经混音链路
        rendered = self._render_service.render_round_file_to_storage(
            api_config, round_config, case_config, task_id,
            name_hint=f'round_{round_number}')
        if rendered is None or not rendered.get('path'):
            raise ValueError(
                f"第 {round_number} 轮混音渲染失败（RenderAudioFile 无产物）")
        return rendered['path']

    def _get_vendor_endpoint(self, api_config):
        """获取供应商 API endpoint（api_endpoints 首个非空 endpoint，INT-1361 api_url 移除后唯一来源）"""
        if hasattr(api_config, 'api_endpoints') and api_config.api_endpoints:
            for ep in api_config.api_endpoints:
                if ep.get('endpoint'):
                    return ep['endpoint']
        return None

    def _send_round_request(self, task_id, api_config, api_specific_config, session,
                            round_number, round_config, case_algorithm_params,
                            algorithm_type, case_config=None, total_rounds=None):
        """发送单轮请求"""
        if total_rounds is None:
            total_rounds = round_number

        input_text = ''
        input_type = round_config.get('input_type', 'text')
        start_time = time.time()

        try:
            # 混音渲染（RenderAudioFile 经 ACL）与请求组装纳入轮次级失败收敛：
            # 渲染失败/模板异常定轮次失败，不中断整个用例
            context_data = self._build_round_context(
                session=session, round_number=round_number, round_config=round_config,
                total_rounds=total_rounds, case_algorithm_params=case_algorithm_params,
                algorithm_type=algorithm_type, case_name='', api_config=api_config,
                case_config=case_config, task_id=task_id
            )
            input_text = context_data.get('input_text', '')

            # 厂商适配器经注册表分发（INT-62）：上层只见 ApiVendorAdapter Port。
            # INT-1176：驱动按会话缓存（MockVendorAdapter 每会话轮次计数等会话态
            # 跨轮保留，对齐 MockDialogAdapter 每会话计数），首轮创建后复用
            driver = getattr(session, '_embedded_driver', None)
            if driver is None:
                driver = vendor_adapter_registry.create_from_config(
                    api_config, api_specific_config, task_id=task_id)
                session._embedded_driver = driver
            rendered_headers, rendered_body = driver.render_request_parts(context_data)

            meta = api_config.meta or {}
            use_adapter = meta.get('use_adapter', True)
            timeout = session.session_timeout + 10

            # 密钥链 case 层候选（UC-0901 扩展流程 3a）：用例 api 段
            # （api_specific_config）优先，回退用例顶层；键名可配置
            case_cfg_key = _key_resolver.case_key
            case_api_key = ''
            if isinstance(api_specific_config, dict):
                case_api_key = api_specific_config.get(case_cfg_key) or ''
            if not case_api_key and isinstance(case_config, dict):
                case_api_key = case_config.get(case_cfg_key) or ''

            if use_adapter:
                return self._send_via_adapter(
                    task_id, algorithm_type, session, round_number, total_rounds,
                    rendered_headers, rendered_body, api_specific_config, meta,
                    api_config, input_text, input_type, start_time,
                    input_audio_path=context_data.get('input_audio', ''),
                    case_api_key=case_api_key,
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
        except Exception as e:
            # gRPC deadline 超时同样归类为 timeout（adapter 路径）
            if type(e).__name__ == 'DeadlineExceeded' or 'DEADLINE_EXCEEDED' in str(e):
                latency = time.time() - start_time
                self._log('WARNING', f"Round {round_number} timeout ({session.session_timeout}s)", task_id=task_id)
                return {'round_number': round_number, 'input': input_text, 'output': '',
                        'latency': round(latency, 3), 'error': 'timeout', 'success': False}
            latency = time.time() - start_time
            self._log('ERROR', f"Round {round_number} failed: {e}", task_id=task_id)
            return {'round_number': round_number, 'input': input_text, 'output': '',
                    'latency': round(latency, 3), 'error': str(e), 'success': False}

    def _send_via_adapter(self, task_id, algorithm_type, session, round_number, total_rounds,
                          rendered_headers, rendered_body, api_specific_config, meta,
                          api_config, input_text, input_type, start_time,
                          input_audio_path='', case_api_key=''):
        """通过内嵌适配器 execute 发送请求（INT-1169/1176 迁移）。

        api_adapter_service 删除后 use_adapter=True 默认路径不再经 gRPC
        AdapterService.SendRound，改为调用本服务内嵌驱动的
        execute_voice_llm_chat（对齐 HttpAdapter voice_llm chat 请求/响应
        契约：URL=/chat 拼接、rendered_headers 合入 + X-Session-Id、text
        json / audio multipart payload、session_timeout 显式超时、
        result_parser 解析）。round 结果 dict 字段（output / output_audio_path /
        response_metrics / raw_response）与迁移前不变。
        """
        # 音频轮次必须携带混音产物引用（SendRoundRequest.input_data 约定：
        # text 内容 或 audio_path，adapter 侧经统一存储层读取）。
        # 缺失时定轮次失败，不静默空发送（INT-71 正确性缺陷修复）。
        input_type_val = input_type or 'text'
        if input_type_val == 'text':
            actual_input = input_text
        else:
            actual_input = input_audio_path or ''
            if not actual_input:
                raise ValueError(
                    f"第 {round_number} 轮 input_type={input_type_val} "
                    f"但无音频输入（混音产物缺失），拒绝空音频发送")

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

        # 内嵌适配器分发（INT-62/INT-497）：与渲染同源驱动实例（会话级缓存）。
        # adapter_class / vendor_adapter / vendor 映射经
        # registry.dimensions_from_config 统一解析（未知 adapter_class 报错，
        # vendor='mock' 无显式配置兜底 MOCK，INT-1170 审计项 3）
        driver = getattr(session, '_embedded_driver', None)
        if driver is None:
            driver = vendor_adapter_registry.create_from_config(
                api_config, api_specific_config, task_id=task_id)

        execute_result = driver.execute_voice_llm_chat(
            session_id=session.session_id,
            input_type=input_type_val,
            input_data=actual_input,
            source_lang=source_lang,
            target_lang=target_lang,
            context=session.get_context(),
            context_for_request=session.get_context_for_request(),
            algorithm_params=api_specific_config.get('algorithm_params', []),
            case_algorithm_params=api_specific_config.get('case_algorithm_params', {}),
            translation_direction=translation_direction,
            round_number=round_number,
            total_rounds=total_rounds,
            task_type=algorithm_type,
            headers=rendered_headers,
            timeout=session.session_timeout,
        )

        self._log('DEBUG', f"Sending round {round_number} via embedded adapter",
                  task_id=task_id)

        latency = time.time() - start_time
        output_text = (execute_result.get('asr')
                       or execute_result.get('trans')
                       or execute_result.get('output', ''))

        success = execute_result.get('success', True)
        round_result = {
            'round_number': round_number, 'input': input_text, 'input_type': input_type,
            'output': output_text,
            'output_audio_path': (execute_result.get('raw_response') or {})
                .get('output_audio_path'),
            'latency': round(latency, 3),
            'response_metrics': {'latency': round(latency, 3)},
            'success': success,
            'raw_response': execute_result,
        }
        if not success:
            # HTTP 失败/超时被 api_client 吞为 success=False + error（对齐迁移前
            # HttpAdapter.raise_for_status 抛 + servicer except → SendRoundResponse
            # success=False → ACL RuntimeError → 失败轮含 error 字段语义）。
            # _run_rounds 仅以 error 键判失败，缺此映射会把失败轮计入成功路径、
            # all_rounds_success=True、用例终态 COMPLETED 且照提评估（INT-1176 审计缺陷 A）。
            round_result['error'] = (
                execute_result.get('error')
                or (f"HTTP {execute_result.get('status_code')}"
                    if execute_result.get('status_code') else '请求失败'))
        return round_result

    def _send_direct(self, task_id, round_number, api_config, meta, rendered_headers,
                     rendered_body, timeout, input_text, input_type, start_time):
        """直接发送请求到供应商"""
        vendor_url = self._get_vendor_endpoint(api_config)
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

    def _aggregate_round_results(self, round_results, session, api_config=None,
                                 task_id=None):
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

        aggregated = {
            'success': success_count == total_count,
            'algorithm_result': algorithm_result,
            'total_latency': total_latency,
            'round_count': total_count,
            'session_summary': session.get_summary()
        }
        # 输出侧实测口径（INT-300 F3 三口径对称补齐）：http_api 多轮会话与
        # Realtime（realtime_session_executor._aggregate）同源——adapter 回传的
        # 输出音频引用（raw_response.output_audio_path 契约）逐轮收集，按轮次
        # 顺序拼接后实测 RMS → SPL；实测值并入 algorithm_result（落库与评估
        # 入参消费 algorithm_result），顶层同名字段供 SSE/查询侧对称可比
        rms_dbfs, spl_db, ai_wav = self._compute_output_spl_evidence(
            round_results, api_config=api_config, task_id=task_id)
        aggregated['ai_output_rms_dbfs'] = rms_dbfs
        aggregated['ai_output_spl_db'] = spl_db
        aggregated['ai_wav'] = ai_wav
        algorithm_result['ai_output_rms_dbfs'] = rms_dbfs
        algorithm_result['ai_output_spl_db'] = spl_db
        algorithm_result['ai_wav'] = ai_wav
        return aggregated

    def _compute_output_spl_evidence(self, round_results, api_config=None,
                                     task_id=None):
        """AI 输出音频实测口径（与 Realtime 对称）：返回 (rms_dbfs, spl_db, ai_wav)。

        数据源为内嵌执行回传的轮次级输出音频存储引用（rounds[].output_audio_path，
        契约见内嵌 execute raw_response.output_audio_path）。任一轮缺引用
        或读档失败时对应轮跳过；全缺时三项均为 None（无输出音频 = 无证据，
        不阻塞结果落库）。读档经统一存储层（oss:// / local:// 同构解析）。
        """
        pcm_parts = []
        for r in sorted(round_results,
                        key=lambda x: self._round_sort_key(x.get('round_number'))):
            ref = r.get('output_audio_path') if isinstance(r, dict) else None
            if not ref:
                continue
            try:
                from shared.infrastructure.storage import storage
                # 逐轮剥容器头（INT-300 审计修复）：轮次归档引用指向完整
                # wav 文件，直接 join 会把各轮 RIFF 头拼进 PCM —— 读侧
                # wave.readframes 只停在第一个 data chunk，第 2 轮起被静默
                # 丢弃（实测 RMS 偏差数十 dB）。裸 PCM 引用（Realtime 风格
                # 归档）经 unwrap 原样透传不受影响。
                pcm_parts.append(self._spl_service.unwrap_container_pcm(
                    storage.load_bytes(ref)))
            except Exception:
                logger.warning("读取 AI 输出音频失败（跳过该轮实测证据）: %s",
                               ref, exc_info=True)

        if not pcm_parts:
            return None, None, None
        pcm = b''.join(pcm_parts)
        ai_rms = self._spl_service.calculate_rms_dbfs(pcm)
        api_id = getattr(api_config, 'id', None)
        try:
            mapping = self._spl_repo.get_default_mapping(api_id)
        except Exception:
            logger.debug("查询 SPL 映射失败，按基准口径计算", exc_info=True)
            mapping = None
        ai_spl = self._spl_service.rms_dbfs_to_spl(ai_rms, mapping)
        return ai_rms, ai_spl, self._save_ai_output_wav(
            pcm, api_id=api_id, task_id=task_id,
            sample_rate=self._resolve_output_sample_rate(api_config))

    @staticmethod
    def _round_sort_key(round_number):
        """轮次排序键：宽松取整（gRPC JSON 往返后可能为 str），异常值按 0。"""
        try:
            return int(str(round_number))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _resolve_output_sample_rate(api_config):
        """AI 输出 wav 采样率：api.audio_config.sample_rate，缺省 24000（回退默认）。

        INT-1771：与 Realtime / 轮次渲染共用 domain 层 resolve_audio_sample_rate，
        顶层列优先、列空时 meta.audio_config 存量兼容。
        """
        return resolve_audio_sample_rate(api_config)

    def _save_ai_output_wav(self, pcm: bytes, api_id=None, task_id=None,
                            sample_rate: int = 24000) -> 'str | None':
        """AI 输出音频归档（对齐 Realtime ai_wav 口径）：wav 容器落存储。"""
        if not pcm:
            return None
        try:
            import io
            import time as _time
            import wave

            buf = io.BytesIO()
            with wave.open(buf, 'wb') as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(int(sample_rate))
                w.writeframes(pcm)
            from shared.infrastructure.storage import storage
            key = (f"{task_id or 'api'}/{api_id or 'api'}/api_session/"
                   f"ai_output_{int(_time.time() * 1000)}.wav")
            return storage.save_bytes(buf.getvalue(), 'audios', key,
                                      content_type='audio/wav') or None
        except Exception:
            logger.debug("保存 AI 输出音频失败", exc_info=True)
            return None
