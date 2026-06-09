# 05 — mock_adapter voice_llm

> **所属步骤**：04_执行测试 → api_adapter  
> **改造类型**：修改  
> **涉及文件**：`api_adaper_service/adapters/mock_adapter.py`

---

## 背景

voice_llm 对话模式需要 mock 适配器模拟多轮对话响应，支持文本输入和音频输入，返回模拟的 ASR 文本和翻译结果。

现有 `MockAdapter` 仅支持帧级音频流式传输的 mock，不支持对话模式。

---

## 改造内容

### 1. 新增 `MockDialogAdapter`

```python
"""Mock dialog adapter for voice_llm multi-round testing."""

import time
import random
from typing import Optional
from utils.logger import logger


class MockDialogAdapter:
    """
    voice_llm 对话模式 mock 适配器。

    模拟多轮对话的请求-响应行为，
    根据输入文本返回预设的 ASR 和翻译结果。
    """

    # 预设对话响应
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
        self.vendor_config = vendor_config or {}
        self.connected = True
        self._round_counter = {}  # session_id -> round count

    def send_request(
        self,
        task_id: str,
        session_id: str,
        input_type: str,
        input_data: str | bytes,
        source_lang: str = 'zh',
        target_lang: str = 'en',
        context: Optional[list] = None,
    ) -> dict:
        """模拟对话请求"""
        # 获取轮次计数
        if session_id not in self._round_counter:
            self._round_counter[session_id] = 0
        round_idx = self._round_counter[session_id]
        self._round_counter[session_id] += 1

        # 生成模拟响应
        zh_responses = self.MOCK_RESPONSES['zh']
        en_responses = self.MOCK_RESPONSES['en']

        asr_text = zh_responses[round_idx % len(zh_responses)]
        trans_text = en_responses[round_idx % len(en_responses)]

        # 如果是文本输入，ASR 直接返回输入文本
        if input_type == 'text' and isinstance(input_data, str):
            asr_text = input_data

        # 模拟延迟（200ms - 800ms）
        simulated_latency = random.uniform(0.2, 0.8)
        time.sleep(simulated_latency)

        logger.info(
            f'Mock dialog: session={session_id}, round={round_idx}, '
            f'input_type={input_type}, latency={simulated_latency:.2f}s'
        )

        return {
            'asr_text': asr_text,
            'trans_text': trans_text,
            'session_id': session_id,
            'latency': round(simulated_latency, 3),
            'raw_response': {
                'mock': True,
                'round': round_idx,
                'input_type': input_type,
            },
        }

    def destroy_session(self, session_id: str):
        """清理会话计数"""
        self._round_counter.pop(session_id, None)
```

### 2. 适配器选择逻辑

```python
# main.py → select_adapter()
def select_adapter(vendor, vendor_config, is_dialog=False):
    if vendor == 'mock':
        if is_dialog:
            return MockDialogAdapter(vendor_config)
        return MockAdapter(vendor_config)
    elif vendor_config.get('protocol') == 'http':
        return HttpAdapter(vendor_config)
    else:
        return WebSocketAdapter(vendor_config)
```

### 3. 预设响应策略

| 策略 | 说明 |
|------|------|
| 轮转 | 按轮次编号取模选择预设响应 |
| 回声 | 文本输入时 ASR 返回输入文本 |
| 随机延迟 | 200-800ms 模拟真实延迟 |

### 4. Mock 响应质量

- ASR 文本：文本输入直接返回输入内容，音频输入返回预设中文句子
- 翻译文本：返回预设英文翻译
- 延迟：随机 200-800ms，模拟真实 LLM 响应时间
- 会话隔离：每个 session_id 维护独立的轮次计数

---

## 不变部分

- 现有 `MockAdapter`（帧级 mock）不变
- `WebSocketAdapter` 不变
- 适配器接口规范不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `01_voice_llm_HTTP适配器` | HttpAdapter 接口对齐 |
| `03_create_task对话模式` | 调用 send_request |
