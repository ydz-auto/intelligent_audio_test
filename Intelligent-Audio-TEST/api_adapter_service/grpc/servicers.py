# -*- coding: utf-8 -*-
"""
api_adapter_service gRPC servicer 实现。

将 gRPC RPC 方法委托给已有业务类：
- AdapterServiceServicer -> session_store / task_manager / select_adapter

约定：
- 复杂参数通过 JSON string 传递，方法内 json.loads 解析
- 返回结果通过 JSON string 封装到 data 字段
- 所有方法用 try/except 包裹，异常返回 success=False
"""

import uuid

from shared.proto import adapter_service_pb2 as adapter_pb
from shared.proto import adapter_service_pb2_grpc as adapter_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

from api_adapter_service.services.session_store import session_store
from api_adapter_service.services.task_manager import task_manager
from api_adapter_service.adapters.factory import select_adapter
from api_adapter_service.utils.config import config
from api_adapter_service.utils.logger import logger


class AdapterServiceServicer(adapter_grpc.AdapterServiceServicer):
    """API Adapter 服务 gRPC servicer，委托给 adapter / session_store / task_manager"""

    def SendRound(self, request, context=None):
        """发送单轮请求（同步）

        对应原 Flask 路由 POST /api/v1/tasks 的业务逻辑：
        解析 proto 字段 -> 合并 vendor config -> 调用 adapter.send_request -> 序列化结果
        """
        try:
            session_id = request.session_id
            if not session_id:
                return adapter_pb.SendRoundResponse(
                    success=False, message='session_id is required', data='',
                )

            round_idx = request.round
            total_rounds = request.total_rounds
            task_type = request.task_type or 'voice_llm'
            vendor = request.vendor or 'mock'

            input_type = request.input_type or 'text'
            input_data = request.input_data or ''
            context = _loads(request.context, [])
            context_for_request = _loads(request.context_for_request, [])
            algorithm_params = _loads(request.algorithm_params, [])
            case_algorithm_params = _loads(request.case_algorithm_params, {})
            translation_direction = request.translation_direction or ''
            vendor_config_override = _loads(request.vendor_config, {})

            # Parse translation direction for source/target lang
            source_lang, target_lang = 'zh', 'en'
            if translation_direction:
                if '2en' in translation_direction:
                    source_lang = translation_direction.split('2')[0] or 'zh'
                    target_lang = 'en'
                elif '2zh' in translation_direction:
                    source_lang = translation_direction.split('2')[0] or 'en'
                    target_lang = 'zh'

            # Create internal task_id
            task_id = str(uuid.uuid4())

            # Merge vendor config: base config from application.yml + override from request
            base_vendor_config = config.get_vendor_config(vendor)
            merged_config = {**base_vendor_config}
            if vendor_config_override:
                if vendor_config_override.get('api_url'):
                    merged_config['base_url'] = vendor_config_override['api_url']
                if vendor_config_override.get('headers'):
                    merged_config['headers'] = vendor_config_override['headers']
                if vendor_config_override.get('timeout'):
                    merged_config['timeout'] = vendor_config_override['timeout']

            # Ensure session exists in session_store
            session_config = base_vendor_config.get('session', {})
            session_store.ensure_session(
                session_id=session_id,
                task_id=task_id,
                context_mode=session_config.get('context_mode', 'full'),
                max_history_rounds=session_config.get('max_history_rounds', 10),
                session_timeout=session_config.get('session_timeout', 60),
            )

            # Register task
            task_manager.create_task(
                task_id,
                session_id=session_id,
                round=round_idx,
                vendor=vendor,
                task_type=task_type,
            )
            task_manager.update_task_status(task_id, 'processing')

            # Select adapter
            adapter = select_adapter(vendor, merged_config, is_dialog=True)

            # Send request
            result = adapter.send_request(
                task_id=task_id,
                session_id=session_id,
                input_type=input_type,
                input_data=input_data,
                source_lang=source_lang,
                target_lang=target_lang,
                context=context,
                context_for_request=context_for_request,
                algorithm_params=algorithm_params,
                case_algorithm_params=case_algorithm_params,
                translation_direction=translation_direction,
                round_number=round_idx,
                total_rounds=total_rounds,
                task_type=task_type,
            )

            # Update session store
            output_text = result.get('asr_text', '') or result.get('output', '')
            session_store.add_round(
                session_id=session_id,
                round_idx=round_idx,
                input_text=input_data if input_type == 'text' else f'[audio:{input_data}]',
                output_text=output_text,
                latency=result.get('latency', 0),
            )

            # Store round result
            task_manager.add_round_result(task_id, round_idx, result)
            task_manager.update_task_status(task_id, 'completed')

            # Build response data (对应原 Flask 响应字段)
            response_data = {
                'task_id': task_id,
                'output_content': output_text,
                'output': output_text,
                'asr_text': result.get('asr_text', ''),
                'trans_text': result.get('trans_text', ''),
                'output_audio_path': result.get('raw_response', {}).get('output_audio_path'),
                'response_metrics': {
                    'latency': result.get('latency', 0),
                },
            }

            return adapter_pb.SendRoundResponse(
                success=True,
                message='success',
                data=_dumps(response_data),
            )

        except Exception as e:
            logger.error(f'SendRound processing failed: {e}', exc_info=True)
            try:
                task_manager.update_task_status(task_id, 'failed', str(e))
            except Exception:
                pass
            return adapter_pb.SendRoundResponse(
                success=False, message=f'Task processing failed: {str(e)}', data='',
            )

    def Health(self, request, context=None):
        """健康检查"""
        try:
            return adapter_pb.HealthResponse(
                healthy=True,
                service='api_adapter_service',
                active_sessions=session_store.get_session_count(),
                total_tasks=task_manager.get_task_count(),
            )
        except Exception as e:
            return adapter_pb.HealthResponse(
                healthy=False, service='api_adapter_service',
                active_sessions=0, total_tasks=0,
            )
