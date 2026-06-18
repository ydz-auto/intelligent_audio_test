# -*- coding: utf-8 -*-
"""Flask routes for api_adapter_service.

Key endpoints:
- POST /api/v1/tasks            — dialog task (synchronous, called by api_executor)
- POST /api/create_dialog_task  — async dialog task creation
- GET  /api/get_status/<task_id> — query task status
- GET  /api/get_final_result/<task_id> — query task result
- GET  /health                   — health check
"""

import uuid
import threading
from flask import Blueprint, request, jsonify

from api_adapter_service.services.session_store import session_store
from api_adapter_service.services.task_manager import task_manager
from api_adapter_service.adapters.factory import select_adapter
from api_adapter_service.utils.config import config
from api_adapter_service.utils.logger import logger

api_bp = Blueprint('api', __name__)


# ── Health ──────────────────────────────────────────────────────────

@api_bp.route('/health')
def api_health():
    return jsonify({
        'status': 'healthy',
        'service': 'api_adapter_service',
        'dialog_sessions': session_store.get_session_count(),
        'total_tasks': task_manager.get_task_count(),
        'supported_modes': ['streaming', 'dialog'],
    })


# ── Synchronous dialog task (called by api_executor) ────────────────

@api_bp.route('/api/v1/tasks', methods=['POST'])
def api_v1_create_task():
    """
    Synchronous dialog task endpoint.

    Called by the main backend's api_executor for each round of a
    multi-round voice_llm session.

    Request body (from api_executor._send_round_request):
    {
        "task_type": "voice_llm",
        "session_id": "uuid",
        "round": 1,
        "total_rounds": 3,
        "input": {"type": "text", "text": "hello"},
        "context": [{"role": "user", "content": "..."}, ...],
        "context_for_request": [...],
        "algorithm_params": [...],
        "case_algorithm_params": {...},
        "translation_direction": "zh2en",
        "vendor": "voice_llm",
        "vendor_config": {"api_url": "...", "headers": {...}, "timeout": 60}
    }

    Response:
    {
        "output_content": "...",
        "output_audio_path": null,
        "response_metrics": {"latency": 0.5},
        "asr_text": "...",
        "trans_text": "..."
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'code': 4000, 'msg': 'request body is required'}), 400

    session_id = data.get('session_id')
    if not session_id:
        return jsonify({'code': 4000, 'msg': 'session_id is required'}), 400

    round_idx = data.get('round', 0)
    total_rounds = data.get('total_rounds', 1)
    task_type = data.get('task_type', 'voice_llm')
    vendor = data.get('vendor', 'mock')
    input_data = data.get('input', {})
    context = data.get('context', [])
    context_for_request = data.get('context_for_request', [])
    algorithm_params = data.get('algorithm_params', [])
    case_algorithm_params = data.get('case_algorithm_params', {})
    translation_direction = data.get('translation_direction')
    vendor_config_override = data.get('vendor_config', {})

    # Parse input
    input_type = input_data.get('type', 'text')
    input_text = input_data.get('text', '')
    input_audio_path = input_data.get('audio_path')

    # Determine actual input
    if input_type == 'audio' and input_audio_path:
        actual_input = input_audio_path
    else:
        actual_input = input_text

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

    try:
        # Select adapter
        adapter = select_adapter(vendor, merged_config, is_dialog=True)

        # Send request
        result = adapter.send_request(
            task_id=task_id,
            session_id=session_id,
            input_type=input_type,
            input_data=actual_input,
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
            input_text=input_text if input_type == 'text' else f'[audio:{input_audio_path}]',
            output_text=output_text,
            latency=result.get('latency', 0),
        )

        # Store round result
        task_manager.add_round_result(task_id, round_idx, result)
        task_manager.update_task_status(task_id, 'completed')

        # Return response to api_executor
        return jsonify({
            'code': 0,
            'msg': 'success',
            'task_id': task_id,
            'output_content': output_text,
            'output': output_text,
            'asr_text': result.get('asr_text', ''),
            'trans_text': result.get('trans_text', ''),
            'output_audio_path': result.get('raw_response', {}).get('output_audio_path'),
            'response_metrics': {
                'latency': result.get('latency', 0),
            },
        })

    except Exception as e:
        logger.error(f'Task processing failed: {e}', exc_info=True)
        task_manager.update_task_status(task_id, 'failed', str(e))
        return jsonify({
            'code': 5000,
            'msg': f'Task processing failed: {str(e)}',
            'task_id': task_id,
        }), 500


# ── Async dialog task creation ──────────────────────────────────────

@api_bp.route('/api/create_dialog_task', methods=['POST'])
def api_create_dialog_task():
    """
    Async dialog task creation.

    Request body:
    {
        "session_id": "sess-001",
        "round": 0,
        "input_type": "text",
        "input_data": "hello",
        "source_lang": "zh",
        "target_lang": "en",
        "vendor": "voice_llm",
        "context": [...]
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'code': 4000, 'msg': 'request body is required'}), 400

    session_id = data.get('session_id')
    if not session_id:
        return jsonify({'code': 4000, 'msg': 'session_id is required'}), 400

    task_id = str(uuid.uuid4())

    task_data = {
        'task_id': task_id,
        'session_id': session_id,
        'round': data.get('round', 0),
        'input_type': data.get('input_type', 'text'),
        'input_data': data.get('input_data', ''),
        'vendor': data.get('vendor', 'mock'),
        'source_lang': data.get('source_lang', 'zh'),
        'target_lang': data.get('target_lang', 'en'),
        'status': 'processing',
    }

    task_manager.create_task(task_id, session_id=session_id, vendor=task_data['vendor'])

    thread = threading.Thread(
        target=_process_dialog_task,
        args=(task_data,),
        daemon=True,
    )
    thread.start()

    return jsonify({
        'code': 0,
        'msg': 'success',
        'data': {'task_id': task_id, 'session_id': session_id},
    })


def _process_dialog_task(task):
    """Background processing for async dialog task."""
    task_id = task['task_id']
    session_id = task['session_id']

    try:
        task_manager.update_task_status(task_id, 'processing')

        context = session_store.get_context(session_id)

        vendor = task['vendor']
        vendor_config = config.get_vendor_config(vendor)
        adapter = select_adapter(vendor, vendor_config, is_dialog=True)

        result = adapter.send_request(
            task_id=task_id,
            session_id=session_id,
            input_type=task['input_type'],
            input_data=task['input_data'],
            source_lang=task['source_lang'],
            target_lang=task['target_lang'],
            context=context,
        )

        session_store.add_round(
            session_id=session_id,
            round_idx=task['round'],
            input_text=task['input_data'] if task['input_type'] == 'text' else '',
            output_text=result.get('asr_text', ''),
            latency=result.get('latency', 0),
        )

        task_manager.add_round_result(task_id, task['round'], result)
        task_manager.update_task_status(task_id, 'completed')

    except Exception as e:
        logger.error(f'Dialog task failed: {e}', exc_info=True)
        task_manager.update_task_status(task_id, 'failed', str(e))


# ── Status / Result queries ─────────────────────────────────────────

@api_bp.route('/api/get_status/<task_id>')
def api_get_status(task_id):
    """Query task status."""
    task = task_manager.get_task(task_id)
    if not task:
        return jsonify({'code': 4004, 'msg': 'task not found'}), 404

    return jsonify({
        'code': 0,
        'data': {
            'task_id': task_id,
            'status': task['status'],
            'error_message': task.get('error_message'),
        },
    })


@api_bp.route('/api/get_final_result/<task_id>')
def api_get_final_result(task_id):
    """Query final result (dialog or streaming)."""
    result = task_manager.get_final_result(task_id)
    if not result:
        return jsonify({'code': 4004, 'msg': 'result not found'}), 404

    return jsonify({
        'code': 0,
        'data': result,
    })


# ── Session management ──────────────────────────────────────────────

@api_bp.route('/api/sessions', methods=['GET'])
def api_list_sessions():
    """List active sessions."""
    return jsonify({
        'code': 0,
        'data': {
            'active_count': session_store.get_session_count(),
        },
    })


@api_bp.route('/api/sessions/<session_id>', methods=['DELETE'])
def api_destroy_session(session_id):
    """Destroy a session."""
    session_store.destroy_session(session_id)
    return jsonify({
        'code': 0,
        'msg': f'session {session_id} destroyed',
    })
