# -*- coding: utf-8 -*-
"""Mock dialog adapter for voice_llm multi-round testing.

Simulates multi-round dialog request-response behavior with
preset ASR and translation responses, echo-mode for text input,
and random latency.
"""

import time
import random
from typing import Optional

from api_adapter_service.adapters.base import BaseAdapter
from api_adapter_service.utils.logger import logger


class MockDialogAdapter(BaseAdapter):
    """
    voice_llm dialog mode mock adapter.

    Simulates multi-round dialog with:
    - Preset ASR and translation responses (round-robin)
    - Echo mode: text input returns input as ASR text
    - Random latency: 200-800ms
    - Per-session round counter
    """

    MOCK_RESPONSES = {
        'zh': [
            '你好，有什么可以帮助你的？',
            '好的，我明白了。',
            '今天的天气不错。',
            '让我帮你查一下。',
            '已经为你设置好了。',
            '抱歉，我没有听懂，请再说一遍。',
            '好的，正在为你处理。',
            '还有其他需要帮助的吗？',
        ],
        'en': [
            'Hello, how can I help you?',
            'OK, I understand.',
            'The weather is nice today.',
            'Let me check that for you.',
            'It has been set up for you.',
            "Sorry, I didn't catch that. Could you repeat?",
            'OK, processing your request.',
            'Is there anything else I can help with?',
        ],
    }

    def __init__(self, vendor_config: dict = None):
        super().__init__(vendor_config or {})
        self.connected = True
        self._round_counter: dict = {}  # session_id -> round count

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
        """Simulate a dialog request."""
        # Round counter per session
        if session_id not in self._round_counter:
            self._round_counter[session_id] = 0
        idx = self._round_counter[session_id]
        self._round_counter[session_id] += 1

        # Select preset responses
        zh_responses = self.MOCK_RESPONSES['zh']
        en_responses = self.MOCK_RESPONSES['en']

        asr_text = zh_responses[idx % len(zh_responses)]
        trans_text = en_responses[idx % len(en_responses)]

        # Echo mode: text input -> ASR returns input text
        if input_type == 'text' and isinstance(input_data, str) and input_data:
            asr_text = input_data

        # Simulated latency (200ms - 800ms)
        simulated_latency = random.uniform(0.2, 0.8)
        time.sleep(simulated_latency)

        logger.info(
            f'Mock dialog: session={session_id}, round={round_number}, '
            f'input_type={input_type}, latency={simulated_latency:.2f}s'
        )

        return {
            'asr_text': asr_text,
            'trans_text': trans_text,
            'output': asr_text,
            'session_id': session_id,
            'latency': round(simulated_latency, 3),
            'raw_response': {
                'mock': True,
                'round': round_number,
                'input_type': input_type,
            },
        }

    def destroy_session(self, session_id: str):
        """Clean up session counter."""
        self._round_counter.pop(session_id, None)
