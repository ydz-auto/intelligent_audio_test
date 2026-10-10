# -*- coding: utf-8 -*-
"""Realtime 多轮流式会话执行器（INT-61）

与 APISessionExecutor 平级的第三类执行器，由 APIExecutor 按 device_type
运行时分发（websocket_api → 本执行器，http_api → APISessionExecutor 不变）。

实例内闭环：WS 长连接与帧状态封闭在接单实例内存中；会话亲和经
RealtimeSessionRegistry（session:bind:{task_id}）记录 task → 实例绑定，
双副本下同会话粘同实例，绑定实例失联自动重路由。

流式双通道：frame（逐帧归一化事件）+ summary（会话汇总）经
RealtimeStreamPublisher 推送（REPORT_EVENTS 领域事件 + sse_events SSE 桥）。

混音渲染（INT-82 接线）：多源时间轴混音在 audio_service RenderAudioStream
进程内完成（08 设计文档 §7.1）；本执行器经 RoundRenderService → ACL 端口
「组装请求 + 消费 chunk」，逐 chunk 推送 WS 并按 chunk 时长 sleep 模拟实时速率，
不得直调 gRPC stub。

SPL 对称：推送增益与 AI 输出实测口径均经 ApiRmsSplService（被测 API 数字域
RMS→SPL 映射），与 E2E/API 结果对称可比。

评估异步：summary 落库后提交 evaluation_service 评估队列，不阻塞会话收尾。
"""
import io
import logging
import time
import wave

from shared.models.common_enums import RealtimeRoundMode
from shared.utils.config_manager import config_manager
from shared.utils.api_key_provider import resolver_from_config
from api_test_service.application.round_render_service import RoundRenderService
from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
from api_test_service.infrastructure.acl import (
    AudioRenderACLRepositoryImpl,
    EvaluationAclRepositoryImpl,
)
from api_test_service.infrastructure.messaging import RealtimeStreamPublisher
from api_test_service.infrastructure.vendor_ws import RealtimeWSClient
from api_test_service.infrastructure.persistence.api_rms_spl_repository import (
    ApiRmsSplRepositoryImpl,
)
from shared.utils.realtime_session_registry import RealtimeSessionRegistry

logger = logging.getLogger(__name__)

# 跨服务出站 gRPC 经 ACL 仓储（返回 DTO），不返回 raw dict
_evaluation_acl = EvaluationAclRepositoryImpl()

# 密钥链解析器（UC-0901 扩展流程 3a）：case_config → meta → env
# OPENAI_API_KEY 逐级回退，各级键名经 config_manager secrets 段配置
_key_resolver = resolver_from_config(config_manager.get_value)


class RealtimeSessionExecutor:
    """Realtime API 多轮流式会话执行器"""

    def __init__(self, executor):
        self._executor = executor
        self._spl_repo = ApiRmsSplRepositoryImpl()
        self._spl_service = ApiRmsSplService(self._spl_repo)
        # 混音渲染经 ACL 端口出站（RenderService 消费链路，INT-82 接线）
        self._render_service = RoundRenderService(
            AudioRenderACLRepositoryImpl(), spl_repo=self._spl_repo)
        self._publisher = RealtimeStreamPublisher()
        self._session_registry = RealtimeSessionRegistry(
            bind_ttl_seconds=int(config_manager.get_value(
                'realtime_session', 'bind_ttl_seconds', 3600)))
        self._frame_seq = 0

    @property
    def _log(self):
        return self._executor._log

    # ── 配置化参数（无魔法数字）──
    def _cfg(self, key, default):
        return config_manager.get_value('realtime_session', key, default)

    # ── 执行入口 ──
    def execute(self, task_id, tc_rel_id, data, case_config) -> bool:
        case_name = data['case_name']
        test_case_id = data['test_case_id']
        algorithm_type = data.get('algorithm_type', 'voice_llm')
        api_configs = data['api_configs']

        rounds = case_config.get('rounds') or []
        session_config = case_config.get('session', {})
        chunk_ms = int(self._cfg('chunk_duration_ms', 100))

        self._log(level='INFO',
                  content=f"开始 Realtime 流式会话执行: {case_name}, 共 {len(rounds)} 轮, "
                          f"chunk={chunk_ms}ms",
                  task_id=task_id, test_case_id=test_case_id)

        for api_config in api_configs:
            self._executor._handle_control(task_id)
            api_id = api_config.id

            max_process = getattr(api_config, 'default_max_process', None) or \
                config_manager.get_value('api_executor', 'default_max_process', 5)
            if not self._executor._concurrency.acquire(api_id, task_id, tc_rel_id,
                                                       max_process=max_process):
                self._log(level='ERROR', content=f"API {api_id} 执行权获取失败，跳过",
                          task_id=task_id, api_id=api_id)
                continue

            try:
                self._execute_for_api(task_id, tc_rel_id, data, case_config,
                                      api_config, rounds, session_config, chunk_ms)
            finally:
                self._executor._concurrency.release(api_id, task_id)

        return True

    def _execute_for_api(self, task_id, tc_rel_id, data, case_config,
                         api_config, rounds, session_config, chunk_ms):
        """单 API 的 Realtime 会话：绑定亲和 → WS 连接 → 多轮 → 聚合落库 → 评估"""
        api_id = api_config.id
        test_case_id = data['test_case_id']
        algorithm_type = data.get('algorithm_type', 'voice_llm')

        # 会话亲和：绑定 task → 本实例（双副本同会话粘同实例）
        instance_id, bound = self._session_registry.bind(task_id)
        self._log(level='INFO',
                  content=f"Realtime 会话亲和绑定: instance={instance_id}, "
                          f"redis_bound={bound}",
                  task_id=task_id, api_id=api_id)

        client = None
        session_id = f"rt-{task_id}-{api_id}"
        dst_sample_rate = int((getattr(api_config, 'meta', None) or {})
                              .get('audio_config', {}).get('sample_rate', 24000))
        try:
            url = self._resolve_ws_url(api_config)
            headers = self._resolve_ws_headers(
                api_config,
                case_api_key=self._case_level_key(
                    data.get('api_specific_config'), case_config))
            client = RealtimeWSClient(
                url, headers=headers,
                vendor=(getattr(api_config, 'vendor', None) or 'openai'),
                event_listener=lambda frame: self._on_frame(
                    task_id, test_case_id, session_id, frame),
                chunk_duration_ms=chunk_ms,
            )
            if not client.connect():
                raise ConnectionError(f"Realtime WS 连接失败: {url}")

            session_cfg = self._build_session_config(api_config, session_config)
            if not client.pre_process(session_cfg):
                raise ConnectionError("Realtime 会话配置未确认（session.updated 超时）")

            round_results = []
            all_success = True
            session_ai_audio = bytearray()
            for round_idx, round_config in enumerate(rounds):
                if not isinstance(round_config, dict):
                    continue
                self._executor._handle_control(task_id)
                round_number = round_config.get('round_number', round_idx + 1)
                self._executor.execution_engine.update_case_round_progress(
                    task_id, tc_rel_id, round_idx, len(rounds))
                # 轮次边界重置（连接跨轮保持，状态按轮归零，会话级音频由本执行器拼接）
                client.reset_round_state()
                try:
                    result = self._execute_round(
                        client, api_config, round_config, round_number,
                        len(rounds), task_id, case_config)
                except Exception as e:
                    import traceback
                    self._log(level='ERROR',
                              content=f"Realtime 第 {round_number} 轮异常: {e}\n"
                                      f"{traceback.format_exc()}",
                              task_id=task_id, api_id=api_id)
                    result = {'round_number': round_number, 'success': False,
                              'error': str(e)}
                result.setdefault('round_number', round_number)
                round_output = client.output
                session_ai_audio += round_output['audio']
                result['frame_count'] = len(round_output['frame_results'])
                round_results.append(result)
                if not result.get('success'):
                    all_success = False

            aggregated = self._aggregate(round_results, bytes(session_ai_audio),
                                         api_config)
            aggregated['ai_wav'] = self._save_ai_audio(
                bytes(session_ai_audio), task_id, api_id,
                sample_rate=dst_sample_rate)
            # AI 输出音频归档路径并入 algorithm_result，随结果落库与评估入参下发
            aggregated['algorithm_result']['ai_wav'] = aggregated['ai_wav']
            result_id = self._executor._result_processor.create_multi_round_test_result(
                task_id=task_id, test_case_id=test_case_id, api_config_id=api_id,
                algorithm_type=algorithm_type, aggregated=aggregated,
                success=all_success)
            aggregated['result_id'] = result_id

            # summary 通道推送（会话汇总落库后）
            self._publisher.publish_summary(
                task_id, test_case_id, session_id=session_id,
                summary={
                    'success': all_success,
                    'round_count': aggregated.get('round_count', 0),
                    'total_latency': aggregated.get('total_latency', 0),
                    'avg_latency': aggregated.get('algorithm_result', {}).get('avg_latency', 0),
                    'barge_in_total': aggregated.get('algorithm_result', {}).get('barge_in_total', 0),
                    'barge_in_success_rate': aggregated.get('algorithm_result', {}).get('barge_in_success_rate', 0),
                    'ai_output_rms_dbfs': aggregated.get('ai_output_rms_dbfs'),
                    'ai_output_spl_db': aggregated.get('ai_output_spl_db'),
                    'rounds': aggregated.get('algorithm_result', {}).get('rounds', []),
                })

            if result_id and all_success:
                self._submit_evaluation(task_id, result_id, test_case_id,
                                        case_config, data, algorithm_type,
                                        aggregated, api_id)

            self._refresh_progress(task_id)
            return all_success
        except Exception as e:
            import traceback
            error_msg = f"API {api_id} Realtime 会话执行异常: {e}"
            self._log(level='ERROR', content=f"{error_msg}\n{traceback.format_exc()}",
                      task_id=task_id, api_id=api_id)
            self._executor._result_processor.update_task_case_failure(
                task_id, tc_rel_id, error_msg)
            return False
        finally:
            if client is not None:
                client.close()
            self._session_registry.release(task_id)

    # ── 轮次执行 ──
    def _execute_round(self, client, api_config, round_config, round_number,
                       total_rounds, task_id, case_config) -> dict:
        mode = RealtimeRoundMode.INTERRUPTION if round_config.get('is_interruption') \
            else RealtimeRoundMode.NORMAL
        if mode == RealtimeRoundMode.INTERRUPTION:
            return self._execute_interruption_round(
                client, api_config, round_config, round_number, task_id, case_config)
        return self._execute_normal_round(
            client, api_config, round_config, round_number, task_id, case_config)

    def _execute_normal_round(self, client, api_config, round_config,
                              round_number, task_id, case_config) -> dict:
        """正常轮：流式推送混音音频（RenderAudioStream 消费链路）→ commit → 等 AI 完整回复"""
        start_time = time.time()
        chunk_ms = int(self._cfg('chunk_duration_ms', 100))
        ai_start_timeout = float(self._cfg('ai_start_timeout_seconds', 25))
        ai_complete_timeout = float(self._cfg('ai_complete_timeout_seconds', 60))

        input_chunk_count = 0
        # 混音渲染经 ACL（多源时间轴混音在 audio_service 进程内，08 设计文档 §7.1）；
        # chunk 恒定时长，逐 chunk 推送 + sleep 模拟实时速率
        chunks = self._render_service.stream_round_chunks(
            api_config, round_config, case_config, task_id)
        for chunk in chunks:
            if chunk.sequence < 0 and chunk.message:
                # ACL 失败收敛终止帧（gRPC 异常 / 渲染失败）：轮次失败，不静默吞掉
                return {'round_number': round_number, 'success': False,
                        'error': f'混音渲染失败: {chunk.message}'}
            self._executor._handle_control(task_id)
            client.send_audio_chunk(chunk.data_b64)
            input_chunk_count += 1
            time.sleep(chunk_ms / 1000.0)

        client.commit_input()
        complete = client.wait_ai_complete(start_timeout=ai_start_timeout,
                                           end_timeout=ai_complete_timeout)
        latency = round(time.time() - start_time, 3)
        output = client.output

        result = {
            'round_number': round_number,
            'mode': RealtimeRoundMode.NORMAL.value,
            'success': bool(complete and output['ai_complete']),
            'latency': latency,
            'input_chunk_count': input_chunk_count,
            'output_audio_size': len(output['audio']),
            'answer_text': output['text'],
            'first_frame_latency_ms': output['latency_ms'],
            'frame_count': len(output['frame_results']),
            'error': None if complete else 'AI 回复未在超时内完成',
        }
        result.update(self._collect_eval_fields(round_config, output))
        return result

    def _execute_interruption_round(self, client, api_config, round_config,
                                    round_number, task_id, case_config) -> dict:
        """打断轮（barge-in）：等 AI 开始 → 推打断混音音频 → 检测打断 → 等新回复"""
        start_time = time.time()
        chunk_ms = int(self._cfg('chunk_duration_ms', 100))
        ai_start_timeout = float(self._cfg('ai_start_timeout_seconds', 25))
        ai_complete_timeout = float(self._cfg('ai_complete_timeout_seconds', 60))
        barge_in_window = float(self._cfg('barge_in_window_seconds', 5))
        interrupt_delay_ms = float(
            round_config.get('interruption_delay_ms')
            or self._cfg('interruption_delay_ms', 1000))

        # ① 等 AI 开始说话
        ai_started = client.wait_ai_speaking(start_timeout=ai_start_timeout)
        before_size = len(client.output['audio'])
        if not ai_started:
            return {'round_number': round_number,
                    'mode': RealtimeRoundMode.INTERRUPTION.value,
                    'success': False, 'error': 'AI 未开始说话，无法打断',
                    'latency': round(time.time() - start_time, 3)}

        # ② 等 AI 说一会儿再打断
        time.sleep(interrupt_delay_ms / 1000.0)

        # ③ 流式推送打断音频（RenderAudioStream 消费链路）+ commit
        chunks = self._render_service.stream_round_chunks(
            api_config, round_config, case_config, task_id)
        client.mark_commit()
        for chunk in chunks:
            if chunk.sequence < 0 and chunk.message:
                return {'round_number': round_number,
                        'mode': RealtimeRoundMode.INTERRUPTION.value,
                        'success': False,
                        'error': f'混音渲染失败: {chunk.message}',
                        'latency': round(time.time() - start_time, 3)}
            self._executor._handle_control(task_id)
            client.send_audio_chunk(chunk.data_b64)
            time.sleep(chunk_ms / 1000.0)
        client.commit_input()

        # ④ barge-in 检测窗口：等 user_speech_started / response_cancelled
        deadline = time.time() + barge_in_window
        while time.time() < deadline:
            event = client.recv(timeout=0.5)
            etype = event.get('type')
            if etype in ('user_speech_started', 'response_cancelled'):
                break
            if etype == 'connection_closed':
                break

        at_window_end_size = len(client.output['audio'])
        barge_in_detected = client.output['barge_in_detected']

        # ⑤ 打断成功则等 AI 重新回复
        renewed = False
        if barge_in_detected:
            renewed = client.wait_ai_complete(start_timeout=ai_start_timeout,
                                              end_timeout=ai_complete_timeout)

        # 打断后音频量 = 重新回复部分（整轮累计扣除打断窗口结束时已有量）
        after_size = max(len(client.output['audio']) - at_window_end_size, 0)

        latency = round(time.time() - start_time, 3)
        result = {
            'round_number': round_number,
            'mode': RealtimeRoundMode.INTERRUPTION.value,
            'success': bool(barge_in_detected and renewed),
            'latency': latency,
            'barge_in_detected': barge_in_detected,
            'barge_in_latency_ms': client.output['barge_in_latency_ms'],
            'interruption_delay_ms': interrupt_delay_ms,
            'ai_response_before_interrupt_size': before_size,
            'ai_response_after_interrupt_size': after_size,
            'ai_renewed': renewed,
            'answer_text': client.output['text'],
            'error': None if (barge_in_detected and renewed) else '打断未生效或 AI 未重新回复',
        }
        result.update(self._collect_eval_fields(round_config, client.output))
        return result

    # ── 帧推送（frame 通道，客户端解析回调在执行线程触发）──
    def _on_frame(self, task_id, test_case_id, session_id, frame: dict):
        """帧监听：逐帧推送 frame 通道（轻量载荷，不含原始音频）"""
        self._frame_seq += 1
        try:
            self._publisher.publish_frame(
                task_id=task_id, test_case_id=test_case_id,
                session_id=session_id, round_number=0,
                seq=self._frame_seq, frame=frame)
        except Exception:
            logger.debug("frame 通道推送失败", exc_info=True)

    # ── 聚合与落库 ──
    def _aggregate(self, round_results, session_ai_audio: bytes, api_config) -> dict:
        """会话聚合：延迟统计 + barge-in 统计 + 会话级 AI 输出 SPL 口径实测"""
        total_latency = sum(r.get('latency', 0) for r in round_results)
        success_count = sum(1 for r in round_results if r.get('success'))
        total_count = len(round_results)

        interrupt_rounds = [r for r in round_results
                            if r.get('mode') == RealtimeRoundMode.INTERRUPTION.value]
        barge_in_total = len(interrupt_rounds)
        barge_in_success = sum(1 for r in interrupt_rounds if r.get('barge_in_detected'))

        spl_service = self._spl_service
        ai_rms_dbfs = spl_service.calculate_rms_dbfs(session_ai_audio) \
            if session_ai_audio else None
        mapping = None
        try:
            mapping = self._spl_repo.get_default_mapping(api_config.id)
        except Exception:
            logger.debug("查询 SPL 映射失败，按基准口径计算", exc_info=True)
        ai_spl = spl_service.rms_dbfs_to_spl(ai_rms_dbfs, mapping) if ai_rms_dbfs is not None else None

        first_frame_latencies = [
            r.get('first_frame_latency_ms') for r in round_results
            if r.get('first_frame_latency_ms') is not None
        ]

        algorithm_result = {
            'round_count': total_count,
            'success_count': success_count,
            'total_latency': round(total_latency, 3),
            'avg_latency': round(total_latency / total_count, 3) if total_count else 0,
            'barge_in_total': barge_in_total,
            'barge_in_success': barge_in_success,
            'barge_in_success_rate': round(barge_in_success / barge_in_total, 3) if barge_in_total else 0,
            'rounds': round_results,
            'first_frame_latency_ms': first_frame_latencies[0] if first_frame_latencies else None,
        }
        # 实测口径并入 algorithm_result：落库（TestResult）与评估入参均只消费
        # algorithm_result，顶层同名字段仅供 SSE summary 通道（对称可比，§AC3）
        algorithm_result['ai_output_rms_dbfs'] = ai_rms_dbfs
        algorithm_result['ai_output_spl_db'] = ai_spl
        return {
            'success': success_count == total_count,
            'algorithm_result': algorithm_result,
            'total_latency': round(total_latency, 3),
            'round_count': total_count,
            'session_summary': {
                'session_id': f"rt-{api_config.id}",
                'frame_count': sum(r.get('frame_count', 0) for r in round_results),
            },
            'ai_output_rms_dbfs': ai_rms_dbfs,
            'ai_output_spl_db': ai_spl,
        }

    def _save_ai_audio(self, output_audio: bytes, task_id, api_id,
                       sample_rate: int = 24000) -> str:
        """AI 输出 PCM → wav → 存储归档（audios/{task}/realtime），返回存储路径"""
        if not output_audio:
            return ''
        try:
            buf = io.BytesIO()
            with wave.open(buf, 'wb') as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sample_rate)
                w.writeframes(output_audio)
            from shared.infrastructure.storage import storage
            key = f"{task_id}/{api_id}/realtime/ai_output_{int(time.time() * 1000)}.wav"
            return storage.save_bytes(buf.getvalue(), 'audios', key,
                                      content_type='audio/wav') or ''
        except Exception:
            logger.debug("保存 AI 输出音频失败", exc_info=True)
            return ''

    # ── 评估提交（异步入队，不阻塞会话）──
    def _submit_evaluation(self, task_id, result_id, test_case_id, case_config,
                           data, algorithm_type, aggregated, api_id):
        """提交评估：复用多轮会话评估入参链路，test_type 沿用 api（评估引擎不动）"""
        case_algorithm_params = data.get('case_algorithm_params')
        full_case_params = {
            'algorithm_params': case_algorithm_params or {},
            'reference_params': case_config.get('reference_params', {}),
            'algorithm_type': algorithm_type,
        }
        from shared.utils.dto_utils import dto_to_dict
        from api_test_service.infrastructure.acl import AlgorithmQueryAclRepositoryImpl
        all_params = dto_to_dict(
            AlgorithmQueryAclRepositoryImpl().extract_case_all_params(full_case_params)) or {}
        eval_params = all_params.get('evaluation', {}) if isinstance(all_params, dict) else {}
        eval_params['algorithm_type'] = algorithm_type
        eval_params['test_type'] = 'api'

        _evaluation_acl.submit_evaluate_case(
            task_id=task_id,
            result_id=result_id,
            test_case_id=test_case_id,
            algorithm_result=aggregated.get('algorithm_result', {}),
            eval_params=eval_params,
        )
        self._log(level='INFO', category='evaluation',
                  content=f"API {api_id} Realtime 会话完成，已提交评估队列",
                  task_id=task_id, api_id=api_id)

    # ── 辅助 ──
    @staticmethod
    def _resolve_ws_url(api_config) -> str:
        """解析 WS 连接地址：api_endpoints 优先 ws://wss://，回退 api_url 同规则"""
        endpoints = list(getattr(api_config, 'api_endpoints', None) or [])
        for ep in endpoints:
            url = (ep.get('endpoint') or '') if isinstance(ep, dict) else str(ep)
            if url.startswith(('ws://', 'wss://')):
                return url
        url = getattr(api_config, 'endpoint', None) or ''
        if url.startswith(('ws://', 'wss://')):
            return url
        raise ValueError(
            f"API {getattr(api_config, 'id', '?')} 未配置 WebSocket 端点"
            "（需 ws:// 或 wss:// 前缀）")

    @staticmethod
    def _case_level_key(api_specific_config, case_config) -> str:
        """密钥链 case 层候选：用例 api 段优先，回退用例顶层（键名可配置）"""
        case_key = _key_resolver.case_key
        if isinstance(api_specific_config, dict):
            value = api_specific_config.get(case_key)
            if value:
                return value
        if isinstance(case_config, dict):
            return case_config.get(case_key) or ''
        return ''

    @staticmethod
    def _resolve_ws_headers(api_config, case_api_key='') -> dict:
        """解析 WS 握手头（_build_connect_headers 语义）：meta.ws_headers
        直传 + 密钥链 case_config → meta → env（UC-0901 扩展流程 3a，
        禁止硬编码密钥）；显式 Authorization 头优先，不覆盖"""
        meta = getattr(api_config, 'meta', None) or {}
        headers = dict(meta.get('ws_headers') or {})
        api_key = _key_resolver.resolve(case_value=case_api_key, meta=meta)
        if api_key and not any(k.lower() == 'authorization' for k in headers):
            headers['Authorization'] = f'Bearer {api_key}'
        return headers

    @staticmethod
    def _build_session_config(api_config, session_config) -> dict:
        """会话配置（session.update 载荷）：VAD/音频格式/voice 全配置化"""
        meta = getattr(api_config, 'meta', None) or {}
        merged = dict(meta.get('session_config') or {})
        merged.update(session_config or {})
        audio_cfg = meta.get('audio_config') or {}
        merged.setdefault('input_audio_format', 'pcm16')
        merged.setdefault('input_audio_sample_rate', audio_cfg.get('sample_rate', 24000))
        return merged

    @staticmethod
    def _collect_eval_fields(round_config, output) -> dict:
        """评估入参字段：query/answer/original_topic（打断轮）"""
        fields = {
            'query': round_config.get('query', ''),
            'question': round_config.get('question', round_config.get('query', '')),
            'correct_answer': round_config.get('correct_answer', ''),
            'answer': output.get('text', ''),
        }
        if round_config.get('original_topic'):
            fields['original_topic'] = round_config['original_topic']
        return fields

    def _refresh_progress(self, task_id):
        """会话收尾：刷新进度（状态回写由 result_processor 统一负责）"""
        try:
            self._executor.execution_engine._emit_progress(task_id, force=True)
        except Exception:
            logger.debug("刷新进度失败", exc_info=True)
