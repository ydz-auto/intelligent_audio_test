# 01 — voice_llm HTTP 适配器

> **所属步骤**：04_执行测试 → api_adapter  
> **改造类型**：新增  
> **涉及文件**：`api_adaper_service/adapters/http_adapter.py`（新建）

---

## 背景

voice_llm 被测 API 通常采用 HTTP REST 协议（而非现有 WebSocket 流式音频），支持文本输入或音频文件上传。现有适配器（`WebSocketAdapter`、`MockAdapter`）基于帧级音频流式传输，不适用于 HTTP 请求-响应模式。

需要新增 `HttpAdapter` 实现 voice_llm 的 HTTP REST 交互。

---

## 改造内容

### 1. 新文件 `http_adapter.py`

```python
"""HTTP REST adapter for voice_llm API interaction."""

import requests
import json
import time
from typing import Optional
from utils.logger import logger


class HttpAdapter:
    """
    voice_llm HTTP REST 适配器。

    与 WebSocket 适配器的区别：
    - 请求-响应模式（非流式帧传输）
    - 支持文本和音频两种输入
    - 维护 session_id 实现多轮对话
    - 单次请求返回完整结果
    """

    def __init__(self, vendor_config: dict):
        self.base_url = vendor_config.get('base_url', '')
        self.headers = vendor_config.get('headers', {})
        self.timeout = vendor_config.get('timeout', 60)
        self.result_parser = vendor_config.get('result_parser', {})
        self.connected = False

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
        """
        发送 HTTP 请求到 voice_llm API。

        Args:
            task_id: 任务 ID
            session_id: 会话 ID（多轮对话）
            input_type: 'text' 或 'audio'
            input_data: 文本字符串或音频 bytes
            context: 上下文历史列表

        Returns:
            {
                "asr_text": "...",
                "trans_text": "...",
                "latency": 1.5,
                "raw_response": {...}
            }
        """
        url = f'{self.base_url}/chat'
        headers = {**self.headers, 'X-Session-Id': session_id}

        if input_type == 'text':
            payload = self._build_text_payload(
                session_id, input_data, source_lang, target_lang, context
            )
            start_time = time.time()
            response = requests.post(
                url, json=payload, headers=headers, timeout=self.timeout
            )
        else:
            # 音频输入：multipart/form-data
            files, data = self._build_audio_payload(
                session_id, input_data, source_lang, target_lang, context
            )
            start_time = time.time()
            response = requests.post(
                url, files=files, data=data, headers=headers, timeout=self.timeout
            )

        latency = time.time() - start_time
        response.raise_for_status()

        result = self._parse_response(response.json())
        result['latency'] = round(latency, 3)

        return result
```

### 2. 文本请求 payload

```python
def _build_text_payload(self, session_id, text, source_lang, target_lang, context):
    return {
        'session_id': session_id,
        'input': {
            'type': 'text',
            'text': text,
        },
        'source_lang': source_lang,
        'target_lang': target_lang,
        'context': context or [],
    }
```

### 3. 音频请求 payload

```python
def _build_audio_payload(self, session_id, audio_bytes, source_lang, target_lang, context):
    files = {
        'audio': ('audio.wav', audio_bytes, 'audio/wav'),
    }
    data = {
        'session_id': session_id,
        'input_type': 'audio',
        'source_lang': source_lang,
        'target_lang': target_lang,
        'context': json.dumps(context or []),
    }
    return files, data
```

### 4. 响应解析

```python
def _parse_response(self, response_data):
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

    return {
        'asr_text': extract(response_data, parser.get('asr_text_path', ''), ''),
        'trans_text': extract(response_data, parser.get('trans_text_path', ''), ''),
        'session_id': extract(response_data, parser.get('session_id_path', ''), ''),
        'raw_response': response_data,
    }
```

### 5. 适配器选择逻辑

```python
# main.py → process_audio_task()
def select_adapter(vendor, vendor_config):
    if vendor == 'mock':
        return MockAdapter(vendor_config)
    elif vendor_config.get('protocol') == 'http':
        return HttpAdapter(vendor_config)
    else:
        return WebSocketAdapter(vendor_config)
```

### 6. 与现有适配器的接口对比

| 方法 | WebSocketAdapter | HttpAdapter | MockAdapter |
|------|-----------------|-------------|-------------|
| `connect()` | 建立 WS 连接 | 无（HTTP 无状态） | 设置 connected=True |
| `send_frame()` | 发送音频帧 | N/A | 生成 mock 响应 |
| `send_request()` | N/A | 发送 HTTP 请求 | N/A |
| `close()` | 关闭 WS | 无 | 设置 connected=False |

---

## 不变部分

- WebSocketAdapter 不变
- 现有帧级流式传输不变
- TaskManager 基础结构不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `06_application_yml配置扩展` | vendor 配置 |
| `03_create_task对话模式` | 任务创建入口 |
