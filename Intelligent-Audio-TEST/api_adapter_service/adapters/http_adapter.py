# -*- coding: utf-8 -*-
"""HTTP REST adapter for voice_llm API interaction.

Unlike the WebSocket adapter (frame-level audio streaming), HttpAdapter
uses a request-response model supporting both text and audio inputs,
maintains session_id for multi-round dialog, and returns complete results
per request.
"""

import json
import time
import requests
from typing import Optional

from api_adapter_service.adapters.base import BaseAdapter
from api_adapter_service.utils.logger import logger


class HttpAdapter(BaseAdapter):
    """
    voice_llm HTTP REST adapter.

    Differences from WebSocket adapter:
    - Request-response (not streaming frames)
    - Text and audio input
    - session_id for multi-round dialog
    - Single request returns complete result
    """

    def __init__(self, vendor_config: dict):
        super().__init__(vendor_config)
        self.base_url = vendor_config.get('base_url', vendor_config.get('api_url', ''))
        self.headers = dict(vendor_config.get('headers', {}))
        self.timeout = vendor_config.get('timeout', 60)
        self.result_parser = vendor_config.get('result_parser', {})

    def send_request(
        self,
        task_id: str,
        session_id: str,
        input_type: str,
        input_data,
        source_lang: str = 'zh',
        target_lang: str = 'en',
        context: Optional[list] = None,
        context_for_request: Optional[list] = None,
        algorithm_params: Optional[list] = None,
        case_algorithm_params: Optional[dict] = None,
        translation_direction: Optional[str] = None,
        round_number: int = 0,
        total_rounds: int = 1,
        task_type: str = 'voice_llm',
    ) -> dict:
        """
        Send HTTP request to voice_llm API.

        Args:
            task_id: Task ID
            session_id: Session ID for multi-round dialog
            input_type: 'text' or 'audio'
            input_data: Text string or audio bytes
            source_lang: Source language
            target_lang: Target language
            context: Context history (role/content pairs)
            context_for_request: Formatted context for the API request
            algorithm_params: Per-round algorithm parameters
            case_algorithm_params: Case-level algorithm parameters
            translation_direction: Translation direction string
            round_number: Current round number
            total_rounds: Total round count
            task_type: Algorithm type identifier

        Returns:
            {
                "asr_text": "...",
                "trans_text": "...",
                "output": "...",
                "latency": 1.5,
                "raw_response": {...}
            }
        """
        url = f'{self.base_url.rstrip("/")}/chat'
        headers = {**self.headers, 'X-Session-Id': session_id}

        if input_type == 'text':
            payload = self._build_text_payload(
                session_id, input_data, source_lang, target_lang,
                context_for_request or context,
                algorithm_params, case_algorithm_params,
                translation_direction, round_number, total_rounds, task_type,
            )
            start_time = time.time()
            response = requests.post(
                url, json=payload, headers=headers, timeout=self.timeout,
            )
        else:
            files, data = self._build_audio_payload(
                session_id, input_data, source_lang, target_lang,
                context_for_request or context,
                algorithm_params, case_algorithm_params,
                translation_direction, round_number, total_rounds, task_type,
            )
            start_time = time.time()
            # Remove Content-Type for multipart (requests sets it automatically)
            multipart_headers = {k: v for k, v in headers.items()
                                 if k.lower() != 'content-type'}
            response = requests.post(
                url, files=files, data=data,
                headers=multipart_headers, timeout=self.timeout,
            )

        latency = time.time() - start_time
        response.raise_for_status()

        result = self._parse_response(response.json())
        result['latency'] = round(latency, 3)

        logger.info(
            f'HttpAdapter: task={task_id}, session={session_id}, '
            f'round={round_number}, latency={result["latency"]}s'
        )

        return result

    # ── Payload builders ────────────────────────────────────────

    def _build_text_payload(self, session_id, text, source_lang, target_lang,
                            context, algorithm_params, case_algorithm_params,
                            translation_direction, round_number, total_rounds,
                            task_type):
        return {
            'session_id': session_id,
            'task_type': task_type,
            'round': round_number,
            'total_rounds': total_rounds,
            'input': {
                'type': 'text',
                'text': text,
            },
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translation_direction': translation_direction,
            'context': context or [],
            'algorithm_params': algorithm_params or [],
            'case_algorithm_params': case_algorithm_params or {},
        }

    def _build_audio_payload(self, session_id, audio_data, source_lang, target_lang,
                             context, algorithm_params, case_algorithm_params,
                             translation_direction, round_number, total_rounds,
                             task_type):
        audio_bytes = audio_data if isinstance(audio_data, bytes) else b''
        files = {
            'audio': ('audio.wav', audio_bytes, 'audio/wav'),
        }
        data = {
            'session_id': session_id,
            'task_type': task_type,
            'round': str(round_number),
            'total_rounds': str(total_rounds),
            'input_type': 'audio',
            'source_lang': source_lang,
            'target_lang': target_lang,
            'translation_direction': translation_direction or '',
            'context': json.dumps(context or []),
            'algorithm_params': json.dumps(algorithm_params or []),
            'case_algorithm_params': json.dumps(case_algorithm_params or {}),
        }
        return files, data

    # ── Response parser ─────────────────────────────────────────

    def _parse_response(self, response_data: dict) -> dict:
        parser = self.result_parser

        def extract(data, path, default=''):
            if not path:
                return default
            keys = path.split('.')
            value = data
            for key in keys:
                if isinstance(value, dict):
                    value = value.get(key)
                else:
                    return default
            return value if value is not None else default

        asr_text = extract(response_data, parser.get('asr_text_path', ''), '')
        trans_text = extract(response_data, parser.get('trans_text_path', ''), '')
        session_id = extract(response_data, parser.get('session_id_path', ''), '')

        # Fallback: try common field names if parser paths are empty
        if not asr_text:
            asr_text = (response_data.get('asr_text')
                        or response_data.get('output_content')
                        or response_data.get('output', ''))
        if not trans_text:
            trans_text = (response_data.get('trans_text')
                          or response_data.get('translation', ''))

        return {
            'asr_text': asr_text,
            'trans_text': trans_text,
            'output': asr_text or trans_text or response_data.get('output', ''),
            'session_id': session_id,
            'raw_response': response_data,
        }
