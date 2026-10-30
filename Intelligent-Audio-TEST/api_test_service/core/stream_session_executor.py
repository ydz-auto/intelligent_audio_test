# -*- coding: utf-8 -*-
"""流式道「按事件切轮」执行器（A2 / INT-1790）。

流式道内策略之一（B0 / INT-1798 §3.1）：与 `RealtimeSessionExecutor`（按轮次，
WS 会话）平级，由 `APIExecutor.streaming_strategy(protocol)` 按协议能力声明选出。
本执行器承载 `event_rounds` 能力：**SSE**（`text/event-stream`）与 **HTTP
chunked 流**（`protocol=http` + `streaming=true`，一行一个 JSON 帧）。

分工（不要在别处重复实现）：
- 分帧 / 归一事件 / 空闲超时 / 重连 / 终止条件 → `transport/sse_client.py`；
- 事件 → 轮次切分（句子边界，零声明退化为一条 message 一轮）→
  `domain/services/stream_round_splitter.py`；
- 轮次评估字段（field_path + param_mappings + transform_type）→
  `core/eval_output_collector.py`；
- 落库与评估入队复用多轮会话链路（`APIResultProcessor.create_multi_round_test_result`
  + `core/evaluation_submitter.py`），与 WS 会话同口径。

本执行器不推送 frame/summary 通道（被测 SSE 没有 AI 语音输出，平台实时流由
Realtime 会话独占），也不做音频输入推流——A2 范围是「一问多回、客户端只读」。
"""
import json
import logging
import time
from shared.infrastructure.base_executor import TaskStopSignal
from shared.utils.config_manager import config_manager
from shared.utils.api_key_provider import (
    endpoint_rotation_key,
    resolver_from_config,
)
from api_test_service.core.eval_output_collector import collect_round_eval_fields
from api_test_service.core.evaluation_submitter import submit_case_evaluation
from api_test_service.domain.services.stream_round_splitter import (
    StreamRoundSplitter,
)
from api_test_service.infrastructure.adapters.transport import HttpStreamClient

logger = logging.getLogger(__name__)

# 密钥链解析器（UC-0901 扩展流程 3a）：case_config → meta → env 逐级回退
_key_resolver = resolver_from_config(config_manager.get_value)

# 默认请求方法：SSE 走 GET（EventSource 语义），chunked 流走 POST（与 HTTP 链一致）
DEFAULT_METHODS = {'sse': 'GET', 'http': 'POST'}

DEFAULT_MAX_RECONNECT_ATTEMPTS = 2


def _int_or(value, default: int) -> int:
    """`meta.sse` 数值键兜底：显式 `null` → 默认；合法值 `0` 原样保留。

    A2 终审 F1：原写法 `int(raw.get(key, 默认))` 遇到显式 `null` 直接
    `TypeError`（写侧放行、执行侧不可用），`or 默认` 又会把 `0` 吞成默认。
    """
    return default if value is None else int(value)


class StreamSessionExecutor:
    """流式道「按事件」策略执行器（SSE / HTTP chunked）"""

    def __init__(self, executor):
        self._executor = executor

    @property
    def _log(self):
        return self._executor._log

    # ── 执行入口 ──
    def execute(self, task_id, tc_rel_id, data, case_config) -> bool:
        case_name = data['case_name']
        test_case_id = data['test_case_id']
        api_configs = data['api_configs']

        self._log(level='INFO',
                  content=f"开始流式（按事件）执行: {case_name}, "
                          f"protocol={data.get('protocol')}, "
                          f"共 {len(api_configs)} 个 API",
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
                                      api_config)
            finally:
                self._executor._concurrency.release(api_id, task_id)
        return True

    def _execute_for_api(self, task_id, tc_rel_id, data, case_config, api_config):
        api_id = api_config.id
        test_case_id = data['test_case_id']
        algorithm_type = data.get('algorithm_type', 'translation')
        protocol = str(data.get('protocol') or 'sse').lower()

        client = None
        try:
            url, endpoint_obj = self._resolve_stream_endpoint(api_config)
            headers = self._resolve_headers(
                api_config, case_config, data.get('api_specific_config'),
                endpoint_obj)
            body = self._render_request_body(api_config, case_config, data,
                                            protocol)
            sse_cfg = self._sse_config(api_config)
            method = (case_config.get('method') or (api_config.meta or {}).get('method')
                      or DEFAULT_METHODS.get(protocol, 'GET'))

            client = self._build_client(
                api_config, url, method, headers, body, sse_cfg,
                abort_check=self._abort_check(task_id, test_case_id))
            if not client.connect():
                error_msg = (f"流式连接失败: {client.biz_msg or client.error}"
                             f"（error_source={client.error_source}, "
                             f"biz_code={client.biz_code}）")
                self._log(level='ERROR', content=error_msg,
                          task_id=task_id, api_id=api_id)
                self._finalize(task_id, tc_rel_id, test_case_id, api_config,
                               algorithm_type, [], error_msg=error_msg)
                return False

            rounds, stream_error, case_removed = self._consume_stream(
                client, api_config, test_case_id, task_id, data, algorithm_type)
            # INT-305 同口径（A2 终审 F3）：用例在执行中被移除 → 静默收敛，
            # 不落结果、不发 CASE_FAILED。退避期间命中移除时传输层只会报
            # 「reconnect aborted by control signal」，故出错后再确认一次。
            if not case_removed and stream_error and self._case_removed(
                    task_id, test_case_id):
                self._log(level='INFO',
                          content="用例已被移除，中断流式执行（退避期间）",
                          task_id=task_id, test_case_id=test_case_id)
                case_removed = True
            if case_removed:
                return False
            all_success = (not stream_error and bool(rounds)
                           and all(r.get('success') for r in rounds))
            if not rounds and not stream_error:
                stream_error = '未收到任何流式消息（end_stream 前无 message 事件）'
            self._finalize(task_id, tc_rel_id, test_case_id, api_config,
                           algorithm_type, rounds, error_msg=stream_error,
                           all_success=all_success, client=client, data=data,
                           case_config=case_config)
            return all_success
        except Exception as e:
            import traceback
            error_msg = f"API {api_id} 流式执行异常: {e}"
            self._log(level='ERROR', content=f"{error_msg}\n{traceback.format_exc()}",
                      task_id=task_id, api_id=api_id)
            self._executor._result_processor.update_task_case_failure(
                task_id, tc_rel_id, error_msg)
            return False
        finally:
            if client is not None:
                client.close()

    # ── 读流 → 切轮 ──
    def _consume_stream(self, client, api_config, test_case_id, task_id,
                        data, algorithm_type):
        """读归一事件直到 end_stream。

        返回 ``(round_results, stream_error, case_removed)``：命中用例移除时
        ``case_removed=True`` 且 ``stream_error`` 保持 ``None``——移除不是流式
        失败，由调用方按 INT-305 静默收敛（不落库、不发 CASE_FAILED）。
        """
        splitter = StreamRoundSplitter(getattr(api_config, 'meta', None) or {})
        rounds = []
        stream_error = None
        session_end = False
        request_start = time.time()

        while True:
            self._executor._handle_control(task_id)
            if self._case_removed(task_id, test_case_id):
                self._log(level='INFO',
                          content="用例已被移除，中断流式执行",
                          task_id=task_id, test_case_id=test_case_id)
                return rounds, None, True
            event = client.recv()
            event_type = event.get('event_type')
            if event_type == 'message':
                closed = splitter.feed(event.get('payload'), ts=event.get('ts'))
                for draft in closed:
                    rounds.append(self._build_round(
                        draft, len(rounds), api_config, algorithm_type,
                        request_start))
                if closed and closed[-1].session_end:
                    session_end = True
                    break
            elif event_type == 'error':
                payload = event.get('payload') or {}
                stream_error = (f"流式错误[{payload.get('code')}]: "
                                f"{payload.get('message')}")
                self._log(level='ERROR', content=stream_error,
                          task_id=task_id, api_id=api_config.id)
                break
            elif event_type == 'end_stream':
                break
            # heartbeat：重连 / keep-alive，不切轮
        if not session_end:
            for draft in splitter.flush():
                rounds.append(self._build_round(
                    draft, len(rounds), api_config, algorithm_type, request_start))
        return rounds, stream_error, False

    def _case_removed(self, task_id, test_case_id) -> bool:
        """非抛出版用例移除检测（INT-305；鸭子类型替身缺该口时视为未移除）"""
        checker = getattr(self._executor, '_is_case_removed', None)
        if not callable(checker):
            return False
        return bool(checker(task_id, test_case_id))

    def _build_round(self, draft, idx, api_config, algorithm_type,
                     request_start) -> dict:
        """轮次草稿 → ``rounds[i]``（output 子字典走统一评估字段收集）"""
        output = self._round_output(draft)
        latency = (round(draft.last_ts - draft.first_ts, 3)
                   if draft.first_ts is not None and draft.last_ts is not None else 0)
        success = draft.biz_code is None
        result = {
            'round_number': idx + 1,
            'mode': 'event_rounds',
            'success': success,
            'latency': latency,
            'event_count': draft.event_count,
            'answer_text': draft.text,
            'asr': draft.asr,
            'trans': draft.trans,
            'sentence_end': draft.sentence_end,
            'session_end': draft.session_end,
            'first_event_latency_ms': int(
                (draft.first_ts - request_start) * 1000)
            if draft.first_ts is not None else None,
            'biz_code': draft.biz_code,
            'biz_msg': draft.biz_msg,
            'error': (f"BizError[{draft.biz_code}]: {draft.biz_msg or 'Unknown Error'}"
                      if draft.biz_code is not None else None),
        }
        result['output'] = collect_round_eval_fields(
            output, algorithm_type=algorithm_type,
            api_id=getattr(api_config, 'id', None),
            text_output=draft.text, log=self._log_eval_output)
        return result

    @staticmethod
    def _round_output(draft) -> dict:
        """轮次输出 dict：合并轮内各事件 payload 顶层键，再加规范文本键。

        规范键（text / asr / trans / event_count）最后写入，优先级最高：
        `field_path` 取 ``text`` 时不会取到厂商 payload 里的同名偶然字段。
        """
        merged = {}
        for payload in draft.payloads:
            if isinstance(payload, dict):
                merged.update(payload)
        merged.update({
            'text': draft.text,
            'asr': draft.asr,
            'trans': draft.trans,
            'event_count': draft.event_count,
        })
        return merged

    # ── 落库 / 评估 ──
    def _finalize(self, task_id, tc_rel_id, test_case_id, api_config,
                  algorithm_type, rounds, *, error_msg=None,
                  all_success=False, client=None, data=None, case_config=None):
        aggregated = self._aggregate(rounds, client, all_success, error_msg)
        result_id = self._executor._result_processor.create_multi_round_test_result(
            task_id=task_id, test_case_id=test_case_id,
            api_config_id=getattr(api_config, 'id', None),
            algorithm_type=algorithm_type, aggregated=aggregated,
            success=all_success, tc_rel_id=tc_rel_id)
        aggregated['result_id'] = result_id
        if result_id and all_success:
            submit_case_evaluation(
                task_id=task_id, result_id=result_id, test_case_id=test_case_id,
                algorithm_result=aggregated.get('algorithm_result', {}),
                case_algorithm_params=(data or {}).get('case_algorithm_params'),
                reference_params=(case_config or {}).get('reference_params', {}),
                algorithm_type=algorithm_type,
                device_type=(data or {}).get('device_type'),
                api_id=getattr(api_config, 'id', None),
                log=lambda level, msg: self._log(level=level, content=msg,
                                                 task_id=task_id,
                                                 api_id=getattr(api_config, 'id', None)))
        self._refresh_progress(task_id)
        return aggregated

    @staticmethod
    def _aggregate(rounds, client, all_success, error_msg) -> dict:
        """轮次聚合：与 WS 会话对齐的 algorithm_result 形状（供评估侧消费）"""
        total_latency = sum(r.get('latency', 0) for r in rounds)
        success_count = sum(1 for r in rounds if r.get('success'))
        total_count = len(rounds)
        client_output = client.output if client is not None else {}
        first_latencies = [r.get('first_event_latency_ms') for r in rounds
                           if r.get('first_event_latency_ms') is not None]
        algorithm_result = {
            'round_count': total_count,
            'success_count': success_count,
            'total_latency': round(total_latency, 3),
            'avg_latency': round(total_latency / total_count, 3) if total_count else 0,
            'rounds': rounds,
            'first_event_latency_ms': first_latencies[0] if first_latencies else None,
            'event_count': client_output.get('event_count', 0),
            'line_mode': client_output.get('line_mode'),
            'status_code': client_output.get('status_code'),
            'biz_code': client_output.get('biz_code'),
            'error_source': client_output.get('error_source'),
        }
        return {
            'success': bool(all_success),
            'error': error_msg,
            'algorithm_result': algorithm_result,
            'total_latency': round(total_latency, 3),
            'round_count': total_count,
            'session_summary': {
                'mode': 'event_rounds',
                'line_mode': client_output.get('line_mode'),
                'status_code': client_output.get('status_code'),
                'event_count': client_output.get('event_count', 0),
                'retry_count': client_output.get('retry_count', 0),
            },
        }

    # ── 传输对象 ──
    @staticmethod
    def _build_client(api_config, url, method, headers, body,
                      sse_cfg, abort_check=None) -> HttpStreamClient:
        return HttpStreamClient(
            url,
            method=method,
            headers=headers,
            body=body,
            timeout=getattr(api_config, 'max_timeout', None) or 30,
            idle_timeout_ms=sse_cfg['idle_timeout_ms'],
            max_duration_ms=sse_cfg.get('max_duration_ms'),
            reconnect_enabled=sse_cfg['reconnect_enabled'],
            retry_ms=sse_cfg['retry_ms'],
            max_reconnect_attempts=sse_cfg['max_reconnect_attempts'],
            proxy_type=getattr(api_config, 'proxy_type', None),
            proxy_url=getattr(api_config, 'proxy_url', None),
            # 分帧模式自动判定：text/event-stream → SSE，其余 → chunked 兜底
            mode='auto',
            # 事件名键（A2 返工 P3-1）：写侧校验与文档声明可用，执行侧按配置写入
            event_name_field=sse_cfg['event_name_field'],
            # 退避等待期间的控制回询（A2 返工 P3-2）：停止 / 用例移除即中断
            abort_check=abort_check,
        )

    def _abort_check(self, task_id, test_case_id):
        """退避等待期间的停止 / 用例移除回询（非抛出，命中即中断等待）。

        复用执行器既有控制口（`_handle_control` 处理暂停 / 停止 / 分布式标志），
        但把 `TaskStopSignal` 收敛成布尔——命中后传输层直接以 `error` 收尾，
        不再回到主循环等待下一次 `_handle_control`（A2 终审 F3 注释修正）；
        停止语义仍由执行器的既有停止路径决定，这里不改写。
        """
        executor = self._executor
        handle_control = getattr(executor, '_handle_control', None)
        is_removed = getattr(executor, '_is_case_removed', None)

        def _check() -> bool:
            if callable(handle_control):
                try:
                    handle_control(task_id)
                except TaskStopSignal:
                    return True
            if callable(is_removed) and is_removed(task_id, test_case_id):
                return True
            return False

        return _check

    @staticmethod
    def _sse_config(api_config) -> dict:
        """`meta.sse` 配置 + 默认值（A0 §3.5 ④）：空闲超时缺省取 max_timeout。

        显式 `null` 与「键未提交」同义，一律取默认值（与写侧校验口径一致，
        A2 终审 F1）；用 `is None` 判定而非 `or`，让合法值 `0` 不被默认值吞掉。
        """
        meta = getattr(api_config, 'meta', None) or {}
        raw = meta.get('sse') if isinstance(meta.get('sse'), dict) else {}
        default_idle_ms = int((getattr(api_config, 'max_timeout', None) or 30) * 1000)
        return {
            'event_name_field': raw.get('event_name_field') or 'event',
            'idle_timeout_ms': _int_or(raw.get('idle_timeout_ms'), default_idle_ms),
            'retry_ms': _int_or(raw.get('retry_ms'), 1000),
            'reconnect_enabled': bool(raw.get('reconnect_enabled', False)),
            'max_reconnect_attempts': _int_or(
                raw.get('max_reconnect_attempts'),
                DEFAULT_MAX_RECONNECT_ATTEMPTS),
            'max_duration_ms': (int(raw['max_duration_ms'])
                                if raw.get('max_duration_ms') else None),
        }

    @staticmethod
    def _resolve_stream_endpoint(api_config):
        """解析流式端点：api_endpoints 中首个 http(s) 端点，回退主 endpoint。

        返回 (url, endpoint_obj)；endpoint_obj 用于端点级密钥池轮换（INT-1177）。
        """
        for ep in (getattr(api_config, 'api_endpoints', None) or []):
            url = (ep.get('endpoint') or '') if isinstance(ep, dict) else str(ep)
            if url.startswith(('http://', 'https://')):
                return url, (ep if isinstance(ep, dict) else {'endpoint': url})
        url = str(getattr(api_config, 'endpoint', None) or '')
        if not url:
            raise ValueError(
                f"API {getattr(api_config, 'id', '?')} 未配置 HTTP 端点"
                "（流式协议需 http:// 或 https:// 端点）")
        return url, None

    @staticmethod
    def _resolve_headers(api_config, case_config, api_specific_config,
                         endpoint_obj) -> dict:
        """请求头：meta.headers + 用例头，按密钥链注入 Bearer。

        与 ApiDriverAdapter._merge_headers 同口径（case 段优先、端点级 api_keys
        池轮换、显式 Authorization 头不覆盖），只为不绕注册表直取适配器而在此
        复用同一解析器（UC-0901 扩展流程 3a）。
        """
        meta = getattr(api_config, 'meta', None) or {}
        case_headers = (case_config or {}).get('headers') \
            if isinstance(case_config, dict) else None
        headers = {**(meta.get('headers') or {}), **(case_headers or {})}
        case_key = _key_resolver.case_key
        case_value = ''
        if isinstance(api_specific_config, dict):
            case_value = api_specific_config.get(case_key) or ''
        if not case_value and isinstance(case_config, dict):
            case_value = case_config.get(case_key) or ''
        api_key = _key_resolver.resolve_rotating(
            rotation_key=endpoint_rotation_key(
                getattr(api_config, 'id', None),
                (endpoint_obj or {}).get('endpoint', '') or ''),
            endpoint=endpoint_obj, case_value=case_value, meta=meta,
        )
        if api_key and not any(k.lower() == 'authorization' for k in headers):
            headers['Authorization'] = f'Bearer {api_key}'
        return headers

    def _render_request_body(self, api_config, case_config, data, protocol):
        """请求载荷：GET 用 `meta.sse.params` / 用例 `params`，其余用 body 模板。

        模板占位符沿用 `{{key}}` 语法（与 ApiDriverAdapter._replace_placeholders
        一致），可用键 = 用例名 / 用例 id / 任务 id / 轮次上下文。
        """
        meta = getattr(api_config, 'meta', None) or {}
        context = {
            'case_name': data.get('case_name', ''),
            'test_case_id': data.get('test_case_id', ''),
            'task_id': data.get('task_id', ''),
        }
        sse_cfg = meta.get('sse') if isinstance(meta.get('sse'), dict) else {}
        if protocol == 'sse':
            params = (case_config.get('params') if isinstance(case_config, dict)
                      else None) or sse_cfg.get('params')
            return self._render_payload(params, context) if params else None
        template = ((case_config.get('body_template') if isinstance(case_config, dict)
                     else None)
                    or meta.get('body_template') or meta.get('body'))
        return self._render_payload(template, context) if template else None

    @classmethod
    def _render_payload(cls, template, context):
        if isinstance(template, dict):
            return {k: (cls._replace_placeholders(v, context)
                        if isinstance(v, str) else v)
                    for k, v in template.items()}
        if isinstance(template, str):
            rendered = cls._replace_placeholders(template, context)
            try:
                return json.loads(rendered)
            except (json.JSONDecodeError, TypeError):
                return {'raw_body': rendered}
        return template

    @staticmethod
    def _replace_placeholders(text, context):
        if not isinstance(text, str):
            return text
        for key, value in context.items():
            text = text.replace('{{' + str(key) + '}}', str(value))
        return text

    # ── 辅助 ──
    def _log_eval_output(self, level, message):
        """评估映射兜底日志（走执行器 _log，替身无执行器时退模块日志）"""
        executor = getattr(self, '_executor', None)
        log_fn = getattr(executor, '_log', None)
        if callable(log_fn):
            log_fn(level=level, content=message)
        else:
            logger.log(logging.getLevelName(level)
                       if isinstance(level, str) else level, message)

    def _refresh_progress(self, task_id):
        try:
            self._executor.execution_engine._emit_progress(task_id, force=True)
        except Exception:
            logger.debug("刷新进度失败", exc_info=True)
