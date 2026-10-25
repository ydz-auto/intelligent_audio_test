# -*- coding: utf-8 -*-
"""gRPC 流式道执行策略（INT-1789 / A1）。

B0（INT-1798）把执行道收敛为两条：`streaming` / `non_streaming`。本文件是
**流式道内**的 gRPC 策略，不新增第三条道：

- `server_stream` → **按事件**切轮：一次请求，每条响应消息 = 一轮（A0 §4.1
  「streaming（按事件：SSE / gRPC server-stream）」）；
- `bidi` → **按轮次**切轮：会话内每个配置轮发一条请求消息，收到语句结束
  （`meta.is_sentence_end_mapping`，缺省 `is_sentence_end`）或会话结束
  （`meta.is_session_end_mapping`，缺省 `session_finished`）即轮次结束，
  轮次结果字段与 WS realtime 同构。

多轮聚合、结果落库、评估提交直接复用 `APISessionExecutor`（同一份实现，
不复制节奏/聚合逻辑）。
"""
from __future__ import annotations

import logging
import time

from shared.utils.dto_utils import dto_to_dict
from shared.utils.error_mapping import ERROR_SOURCE_CONFIG, ERROR_SOURCE_GRPC
from shared.utils.path_extractor import extract_by_path

from api_test_service.core.api_session_executor import APISessionExecutor
from api_test_service.infrastructure.adapters import vendor_adapter_registry
from api_test_service.infrastructure.adapters.transport.grpc_client import (
    EVENT_END_STREAM,
    EVENT_ERROR,
    EVENT_HEARTBEAT,
    EVENT_MESSAGE,
    GrpcCallError,
    GrpcProtoError,
)

logger = logging.getLogger(__name__)


class GrpcStreamExecutor(APISessionExecutor):
    """流式道 gRPC 策略（server_stream 按事件 / bidi 按轮次）。"""

    # 轮次内等待单条事件的超时（秒级轮询，轮次总时长由 deadline 兜底）
    RECV_TIMEOUT_SECONDS = 5.0

    @property
    def _log(self):
        return self._executor._log

    # ── 入口：覆盖轮次循环，其余（聚合/落库/评估）复用父类 ──
    def _run_rounds(self, task_id, tc_rel_id, rounds, api_config, api_specific_config,
                    session, case_algorithm_params, algorithm_type,
                    round_results, case_config=None):
        if not rounds:
            # 空 rounds（用例详情取不到等）不能落成「零请求 + 成功」：gRPC 一次
            # 调用即一轮（server_stream / bidi 的会话至少发一条请求消息），按
            # 1 轮执行并留痕，与线性道「无多轮配置 = 单轮」同口径。
            self._log(level='WARNING',
                      content="用例未配置轮次（rounds 为空），gRPC 流式道按 1 轮执行",
                      task_id=task_id, api_id=getattr(api_config, 'id', None))
            rounds = [{}]

        field_mappings = dto_to_dict(
            self._algo_acl().get_field_mappings(
                algorithm_type, api_id=getattr(api_config, 'id', None))) or {}

        try:
            adapter = vendor_adapter_registry.create_from_config(
                api_config, api_specific_config, task_id=task_id)
            method_kind = adapter.method_kind
        except GrpcProtoError as exc:
            # 配置错误（proto 缺失 / 方法不存在 / method_kind 不符）定用例失败，
            # 不静默降级到别的协议或别的执行道。
            self._log(level='ERROR',
                      content=f"gRPC 配置错误，用例失败: {exc}",
                      task_id=task_id, api_id=getattr(api_config, 'id', None))
            round_results.append({
                'round_number': 1, 'success': False, 'error': f'gRPC 配置错误: {exc}',
                'output': {}, 'answer_text': '', 'latency': 0,
                'error_source': ERROR_SOURCE_CONFIG, 'biz_code': 400,
            })
            return False

        try:
            if method_kind == 'unary':
                # unary = 非流式道（A0 / B0：道只由 apis.streaming 决定）。走到这里
                # 说明 `streaming=true` 与 `meta.grpc.method_kind=unary` 互相矛盾，
                # 按配置错误判用例失败，不静默当成 bidi 会话跑（否则首轮「成功」、
                # 后几轮莫名其妙失败，错误归因错）。
                message = ('gRPC method_kind=unary 属非流式道，与 streaming=true 矛盾'
                           '（元数据：unary 走非流式道，server_stream / bidi 走流式道）')
                self._log(level='ERROR', content=message, task_id=task_id,
                          api_id=getattr(api_config, 'id', None))
                for index, round_config in enumerate(rounds or [{}]):
                    round_number = (round_config.get('round_number', index + 1)
                                    if isinstance(round_config, dict) else index + 1)
                    round_results.append(self._failure_round(
                        round_number,
                        {'biz_code': 400, 'biz_msg': message, 'error_source': ERROR_SOURCE_CONFIG},
                        message, 0))
                return False
            if method_kind == 'server_stream':
                return self._run_event_rounds(
                    task_id, tc_rel_id, rounds, adapter, api_config,
                    session, field_mappings, algorithm_type, round_results)
            return self._run_session_rounds(
                task_id, tc_rel_id, rounds, adapter, api_config,
                api_specific_config, session, field_mappings, algorithm_type,
                round_results, case_algorithm_params, case_config)
        finally:
            try:
                adapter.close()
            except Exception:
                logger.debug("关闭 gRPC 适配器失败", exc_info=True)

    def _algo_acl(self):
        """算法 ACL（与父类同源实现；测试替身可注入）。"""
        from api_test_service.infrastructure.acl import AlgorithmQueryAclRepositoryImpl

        return AlgorithmQueryAclRepositoryImpl()

    # ── server-stream：按事件切轮 ──
    def _run_event_rounds(self, task_id, tc_rel_id, rounds, adapter, api_config,
                          session, field_mappings, algorithm_type, round_results):
        api_id = getattr(api_config, 'id', None)
        first_round = next((r for r in rounds if isinstance(r, dict)), {})
        context = self._round_context(
            session, first_round, round_number=1, total_rounds=1,
            api_config=api_config)
        self._log(level='INFO',
                  content=f"gRPC server_stream 按事件切轮：一次请求，消息逐条成轮"
                          f"（用例配置 {len(rounds)} 轮仅取首轮作请求上下文）",
                  task_id=task_id, api_id=api_id)
        started = time.time()
        try:
            call_result = adapter.call_server_stream(context)
        except GrpcCallError as exc:
            round_results.append(self._failure_round(
                1, exc.fields, str(exc), time.time() - started))
            return False
        except GrpcProtoError as exc:
            round_results.append(self._failure_round(
                1, {'biz_code': 400, 'biz_msg': str(exc), 'error_source': ERROR_SOURCE_CONFIG},
                str(exc), time.time() - started))
            return False

        events = [e for e in (call_result.get('events') or [])
                  if e.get('event_type') == EVENT_MESSAGE]
        if not events:
            round_results.append(self._failure_round(
                1, {'biz_code': 500, 'biz_msg': 'server_stream 未返回任何消息',
                    'error_source': ERROR_SOURCE_GRPC},
                'server_stream 未返回任何消息', time.time() - started))
            return False

        for index, event in enumerate(events):
            round_number = index + 1
            payload = event.get('payload') or {}
            round_result = {
                'round_number': round_number,
                'mode': 'event',
                'success': True,
                'latency': 0,   # 逐事件耗时不可分；整体耗时落首轮与聚合
                'answer_text': self._text_of(payload, adapter),
                'output_audio_path': None,
                'output_audio_size': 0,
                'frame_count': 1,
                'event_seq': event.get('seq'),
                'raw_response': payload,
                'error': None,
            }
            if index == 0:
                round_result['latency'] = round(
                    call_result.get('latency_ms', 0) / 1000.0, 3)
            # `raw_response` 是传输件的归一 payload（`MessageToDict` 结果），
            # 不是适配器 execute 结果的 `{json: ...}` 形状——按直连口径提取
            # （unwrap=False 等价 vendor_response=raw_response）。反过来会让
            # field_path 在 None 上取值，轮次 output 恒空。
            self._attach_api_output_fields(
                round_result, field_mappings, algorithm_type, task_id,
                unwrap_execute_result=False)
            round_results.append(round_result)
            self._log(level='INFO',
                      content=f"server_stream 事件 {round_number}/{len(events)} "
                              f"→ 轮次 {round_number}，payload={self._brief(payload)}",
                      task_id=task_id, api_id=api_id)
        return True

    # ── bidi：按轮次切轮 ──
    def _run_session_rounds(self, task_id, tc_rel_id, rounds, adapter, api_config,
                            api_specific_config, session, field_mappings,
                            algorithm_type, round_results, case_algorithm_params,
                            case_config):
        api_id = getattr(api_config, 'id', None)
        meta = getattr(api_config, 'meta', None) or {}
        sentence_end_path = meta.get('is_sentence_end_mapping', 'is_sentence_end')
        session_end_path = meta.get('is_session_end_mapping', 'session_finished')

        first_round = next((r for r in rounds if isinstance(r, dict)), {})
        open_context = self._round_context(
            session, first_round, round_number=1, total_rounds=max(len(rounds), 1),
            api_config=api_config)
        try:
            grpc_session = adapter.open_bidi_session(open_context)
        except (GrpcCallError, GrpcProtoError) as exc:
            fields = getattr(exc, 'fields', None) or {
                'biz_code': 400, 'biz_msg': str(exc), 'error_source': ERROR_SOURCE_CONFIG}
            for index, round_config in enumerate(rounds or [{}]):
                round_number = (round_config.get('round_number', index + 1)
                                if isinstance(round_config, dict) else index + 1)
                round_results.append(self._failure_round(
                    round_number, fields, str(exc), 0))
            return False
        # bidi 的 deadline 是**会话总预算**：`GrpcBidiSession` 建立 stream 时
        # 一次性把 `meta.grpc.deadline_ms` 交给 gRPC（协议不支持会话内改）。
        # 轮内等待因此按剩余预算收敛，避免最后一轮还按完整 deadline 空转、
        # 到点先被外层流 deadline 掐断。
        session_deadline_at = time.time() + max(adapter.deadline_ms() / 1000.0, 1.0)
        all_ok = True
        try:
            for round_idx, round_config in enumerate(rounds):
                if not isinstance(round_config, dict):
                    continue
                self._executor._handle_control(task_id)
                round_number = round_config.get('round_number', round_idx + 1)
                context = self._round_context(
                    session, round_config, round_number=round_number,
                    total_rounds=len(rounds), api_config=api_config)
                round_result = self._run_bidi_round(
                    task_id, grpc_session, adapter, context, round_config,
                    round_number, sentence_end_path, session_end_path,
                    session_deadline_at=session_deadline_at)
                # 同 server_stream：`raw_response` 是归一 payload（无 `json`
                # 包装），unwrap=True 会让 field_path 提取不到 → output 恒空。
                self._attach_api_output_fields(
                    round_result, field_mappings, algorithm_type, task_id,
                    unwrap_execute_result=False)
                round_results.append(round_result)
                if not round_result.get('success'):
                    all_ok = False
                self._log(level='INFO',
                          content=f"bidi 轮次 {round_number}/{len(rounds)} "
                                  f"success={round_result.get('success')} "
                                  f"events={round_result.get('frame_count')} "
                                  f"latency={round_result.get('latency')}s",
                          task_id=task_id, api_id=api_id)
        finally:
            try:
                grpc_session.close()
            except Exception:
                logger.debug("关闭 bidi 会话失败", exc_info=True)
        return all_ok

    def _run_bidi_round(self, task_id, grpc_session, adapter, context, round_config,
                        round_number, sentence_end_path, session_end_path,
                        session_deadline_at=None) -> dict:
        """bidi 单轮：发请求消息 → 收到语句/会话结束。

        `session_deadline_at` 是会话总预算的绝对时间点（由
        `_run_session_rounds` 传入）：轮内空等上限取「完整 deadline」与
        「会话剩余预算」的较小者。
        """
        started = time.time()
        body = adapter.build_body(context)
        try:
            grpc_session.send(body)
        except GrpcCallError as exc:
            return self._failure_round(round_number, exc.fields, str(exc),
                                       time.time() - started)
        except (GrpcProtoError, ValueError) as exc:
            return self._failure_round(
                round_number,
                {'biz_code': 400, 'biz_msg': str(exc), 'error_source': ERROR_SOURCE_CONFIG},
                str(exc), time.time() - started)

        events = []
        payloads = []
        first_event_latency_ms = None
        error_fields = None
        deadline_s = adapter.deadline_ms() / 1000.0
        round_deadline_at = started + max(deadline_s, 1.0)
        if session_deadline_at is not None:
            round_deadline_at = min(round_deadline_at, session_deadline_at)
        while True:
            self._executor._handle_control(task_id)
            event = grpc_session.recv(timeout=self.RECV_TIMEOUT_SECONDS)
            event_type = event.get('event_type')
            if event_type == EVENT_HEARTBEAT:
                # 空转不算失败：轮次总时长由 meta.grpc.deadline_ms 兜底
                if time.time() > round_deadline_at:
                    error_fields = {'biz_code': 504, 'biz_msg': 'DEADLINE_EXCEEDED',
                                    'error_source': ERROR_SOURCE_GRPC, 'raw_code': 4}
                    break
                continue
            events.append(event)
            payload = event.get('payload') or {}
            if event_type == EVENT_MESSAGE:
                if first_event_latency_ms is None:
                    first_event_latency_ms = int((time.time() - started) * 1000)
                payloads.append(payload)
                if extract_by_path(payload, session_end_path) is True:
                    break
                if extract_by_path(payload, sentence_end_path) is True:
                    break
            elif event_type == EVENT_ERROR:
                error_fields = dict(payload)
                break
            elif event_type == EVENT_END_STREAM:
                break

        latency = round(time.time() - started, 3)
        if error_fields:
            return self._failure_round(round_number, error_fields,
                                       error_fields.get('biz_msg') or 'gRPC 会话错误',
                                       latency,
                                       frame_count=len(events),
                                       first_frame_latency_ms=first_event_latency_ms)
        if not payloads:
            return self._failure_round(
                round_number,
                {'biz_code': 504, 'biz_msg': '无消息即断开（end_stream）',
                 'error_source': ERROR_SOURCE_GRPC, 'raw_code': None},
                'bidi 会话在收到任何消息前结束', latency,
                frame_count=len(events))

        # 轮次原始响应取最后一条消息（与 WS realtime 的 output 口径一致：
        # 轮次汇总文本由归一 payload 抽取，评估取值走 field_path 声明）
        last_payload = payloads[-1]
        combined_text = ''.join(
            self._text_of(p, adapter) for p in payloads if self._text_of(p, adapter))
        return {
            'round_number': round_number,
            'mode': 'normal',
            'success': True,
            'latency': latency,
            'input_chunk_count': 0,
            'input_interrupted': False,
            'output_audio_size': 0,
            'answer_text': combined_text,
            'first_frame_latency_ms': first_event_latency_ms,
            'frame_count': len(events),
            'event_count': len(payloads),
            'raw_response': last_payload,
            'error': None,
        }

    # ── 公共小件 ──
    def _round_context(self, session, round_config, round_number, total_rounds,
                       api_config=None):
        context = {
            'session_id': session.session_id,
            'round_number': round_number,
            'total_rounds': total_rounds,
            'context_history': session.get_context(),
            'context_for_request': session.get_context_for_request(),
            'timestamp': int(time.time()),
        }
        for param in (round_config.get('algorithm_params') or []):
            field_code = param.get('field_code')
            if field_code and field_code not in context:
                context[field_code] = param.get('field_value', '')
                if field_code == 'input_text':
                    context['input_text'] = param.get('field_value', '')
        return context

    @staticmethod
    def _text_of(payload, adapter) -> str:
        asr, trans = adapter._extract_text(payload)
        return asr or trans or ''

    @staticmethod
    def _brief(payload) -> str:
        try:
            text = str(payload)
        except Exception:
            text = '<payload>'
        return text if len(text) <= 300 else text[:300] + '…'

    @staticmethod
    def _failure_round(round_number, fields, error, latency,
                       frame_count=0, first_frame_latency_ms=None) -> dict:
        return {
            'round_number': round_number,
            'mode': 'normal',
            'success': False,
            'latency': latency,
            'input_chunk_count': 0,
            'input_interrupted': False,
            'output_audio_size': 0,
            'answer_text': '',
            'first_frame_latency_ms': first_frame_latency_ms,
            'frame_count': frame_count,
            'raw_response': None,
            'error': error,
            'biz_code': fields.get('biz_code'),
            'biz_msg': fields.get('biz_msg'),
            'error_source': fields.get('error_source'),
            'raw_code': fields.get('raw_code'),
            'output': {},
        }
