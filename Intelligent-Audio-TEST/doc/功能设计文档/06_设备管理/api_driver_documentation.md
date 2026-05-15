# API Driver 文档

## 概述

`api_driver.py` 是一个 API 驱动程序，用于封装 API 调用逻辑、参数渲染及响应解析。它支持 HTTP 和 WebSocket 协议，能够处理单次响应和流式响应，并提供了灵活的配置和参数渲染机制。

## 核心功能

1. **统一 API 调用接口**：支持 HTTP 和 WebSocket 协议
2. **参数渲染**：支持基于上下文数据的占位符替换
3. **响应解析**：支持单次响应和流式响应的解析
4. **配置合并**：支持 API 级和用例级配置的合并
5. **灵活的映射机制**：支持自定义 ASR、翻译等字段的映射路径

## 类结构

### APIDriver

#### 初始化方法

```python
def __init__(self, api_config, case_config=None, endpoint=None):
    # api_config: API 模型实例 (包含 max_timeout 等配置)
    # case_config: 用例级特定配置 (如特定的 body_template, headers)
    # endpoint: 可选的端点 URL (优先使用此值，否则使用 api_config.endpoint)
```

#### 主要方法

1. **execute**：执行 API 调用并解析结果
2. **_render_payload**：根据上下文渲染请求 Payload
3. **_replace_placeholders**：替换字符串中的 `{{key}}` 占位符
4. **_parse_response**：解析响应结果
5. **_extract_by_path**：从字典/列表中根据路径提取值

## 工作流程

### 1. 输入解析与处理

#### 配置合并

APIDriver 会合并 API 级和用例级的配置，优先级为：用例级配置 > API 级配置。

- **端点 URL**：优先使用构造函数传入的 `endpoint`，否则使用 `api_config.endpoint`
- **请求方法**：优先使用 `case_config.method`，否则使用 `meta.method`，默认值为 `POST`
- **Headers**：合并 `meta.headers` 和 `case_config.headers`
- **请求体模板**：优先使用 `case_config.body_template`，否则使用 `meta.body_template` 或 `meta.body`

#### 参数渲染

1. **模板类型处理**：
   - **字典模板**：遍历字典，替换字符串值中的占位符，然后合并上下文数据
   - **字符串模板**：替换占位符后，尝试解析为 JSON 对象
   - **其他类型**：直接返回

2. **占位符替换**：
   - 支持 `{{key}}` 格式的占位符
   - 从上下文数据中查找对应的值进行替换
   - 支持嵌套路径替换

#### 示例

```python
# 模板
template = {
    "text": "{{input_text}}",
    "session_id": "{{session_id}}"
}

# 上下文数据
context = {
    "input_text": "Hello, world!",
    "session_id": "123456"
}

# 渲染结果
result = {
    "text": "Hello, world!",
    "session_id": "123456"
}
```

### 2. Header 处理

#### 合并逻辑

```python
# 合并 Headers
headers = {**self.meta.get('headers', {}), **self.case_config.get('headers', {})}
```

- 用例级 Headers 会覆盖 API 级 Headers 中同名的键
- 支持所有 HTTP 标准 Headers
- 支持自定义 Headers

#### 示例

```python
# API 级 Headers
meta_headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer token123"
}

# 用例级 Headers
case_headers = {
    "Authorization": "Bearer token456",
    "X-Custom-Header": "custom-value"
}

# 合并结果
merged_headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer token456",  # 用例级覆盖了 API 级
    "X-Custom-Header": "custom-value"
}
```

### 3. API 调用

#### 协议自动选择

APIDriver 会根据端点 URL 的协议自动选择调用方式：
- `ws://` 或 `wss://`：WebSocket 调用
- 其他：HTTP 调用

#### HTTP 调用

通过 `api_client._call_http` 方法实现，支持 GET、POST 及其他 HTTP 方法，支持文件上传。

#### WebSocket 调用

通过 `api_client._call_websocket` 方法实现，支持：
1. 初始 JSON 数据发送
2. 流式音频文件发送
3. 持续响应接收
4. 会话结束标志检测

### 4. 响应解析

#### 单次响应解析（HTTP）

1. 提取响应状态码、延迟和原始响应
2. 尝试解析 JSON 响应
3. 根据映射配置提取 ASR、翻译等字段
4. 返回结构化结果

#### 流式响应解析（WebSocket）

1. 聚合所有接收到的消息
2. 根据映射配置提取每条消息的 ASR、翻译等字段
3. 根据 `append_mode` 配置决定如何聚合结果：
   - `append_mode=True`：当语句结束时，将结果追加到最终列表
   - `append_mode=False`：保留最新的结果
4. 检测会话结束标志
5. 返回结构化结果

#### 字段映射

| 配置项 | 描述 | 默认值 |
|--------|------|--------|
| asr_mapping | ASR 结果映射路径 | asr_result |
| trans_mapping | 翻译结果映射路径 | translation_result |
| sentence_end_mapping | 语句结束标志映射路径 | is_sentence_end |
| session_end_mapping | 会话结束标志映射路径 | session_finished |

#### 路径提取规则

支持 `.` 分隔的路径，如：
- `result.asr`：提取 `result` 字典中的 `asr` 字段
- `items.0.text`：提取 `items` 列表中第 0 个元素的 `text` 字段

## WebSocket 调用详解

### 1. 连接建立

```python
ws = websocket.create_connection(endpoint, timeout=timeout, header=headers)
```

### 2. 数据发送

#### 初始配置数据发送

```python
if data:
    if isinstance(data, (dict, list)):
        ws.send(json.dumps(data))
    else:
        ws.send(str(data))
```

#### 流式音频发送

```python
if stream_audio and audio_path and os.path.exists(audio_path):
    chunk_size = meta.get('chunk_size', 4096)
    with open(audio_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk: break
            ws.send_binary(chunk)
            # 控制发送速率，模拟真实流式
            sleep_time = meta.get('chunk_interval', 0.02)
            if sleep_time > 0:
                time.sleep(sleep_time)
```

#### 结束标志发送

```python
eos_message = meta.get('eos_message')
if eos_message:
    ws.send(json.dumps(eos_message) if isinstance(eos_message, dict) else str(eos_message))
```

### 3. 响应接收与处理

```python
for _ in range(max_responses):
    try:
        msg = ws.recv()
        if not msg: break
        all_responses.append(msg)
        # 尝试解析 JSON 并检查结束标志
        try:
            msg_json = json.loads(msg)
            last_json = msg_json
            # 如果配置了结束标志路径，则检查
            if session_end_path:
                if APIClient._extract_by_path(msg_json, session_end_path) is True:
                    break
        except:
            pass
    except websocket.WebSocketTimeoutException:
        break
    except Exception as e:
        error = f"Recv error: {str(e)}"
        break
```

## 配置选项

### API 级配置（api_config.meta）

| 配置项 | 类型 | 描述 |
|--------|------|------|
| endpoint | str | API 端点 URL |
| method | str | 请求方法（GET/POST/PUT/DELETE 等） |
| headers | dict | HTTP 头信息 |
| body_template | dict/str | 请求体模板 |
| body | dict | 请求体（当 body_template 不存在时使用） |
| asr_mapping | str | ASR 结果映射路径 |
| trans_mapping | str | 翻译结果映射路径 |
| sentence_end_mapping | str | 语句结束标志映射路径 |
| session_end_mapping | str | 会话结束标志映射路径 |
| append_mode | bool | 是否追加模式聚合结果 |
| stream_audio | bool | 是否流式发送音频 |
| chunk_size | int | 音频分块大小 |
| chunk_interval | float | 音频分块发送间隔（秒） |
| eos_message | dict/str | 结束标志消息 |
| recv_timeout | float | 接收单条消息的超时（秒） |
| max_responses | int | 最大接收消息数 |

### 用例级配置（case_config）

| 配置项 | 类型 | 描述 |
|--------|------|------|
| method | str | 请求方法 |
| headers | dict | HTTP 头信息 |
| body_template | dict/str | 请求体模板 |

## 输出格式

### execute 方法返回值

```python
{
    "success": bool,          # API 调用是否成功
    "latency": int,           # 延迟（毫秒）
    "status_code": int,       # HTTP 状态码（WebSocket 为 200 或 500）
    "raw_response": str,      # 原始响应
    "error": str,             # 错误信息（如果有）
    "asr": str,               # ASR 结果
    "trans": str,             # 翻译结果
    "is_sentence_end": bool,  # 是否为语句结束
    "is_session_end": bool    # 是否为会话结束
}
```

## 使用示例

### 基本用法

```python
# 创建 API 配置
api_config = {
    "meta": {
        "endpoint": "http://api.example.com/recognize",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer token123"
        },
        "body_template": {
            "text": "{{input_text}}",
            "lang": "{{lang}}"
        },
        "asr_mapping": "result.asr",
        "trans_mapping": "result.trans"
    },
    "max_timeout": 30
}

# 创建用例配置
case_config = {
    "headers": {
        "X-Custom-Header": "custom-value"
    }
}

# 创建 APIDriver 实例
driver = APIDriver(api_config, case_config)

# 执行 API 调用
context_data = {
    "input_text": "Hello, world!",
    "lang": "en"
}

result = driver.execute(context_data)

# 输出结果
print(result)
```

### WebSocket 用法

```python
# 创建 API 配置（WebSocket）
api_config = {
    "meta": {
        "endpoint": "ws://api.example.com/ws/recognize",
        "asr_mapping": "asr_result",
        "trans_mapping": "translation_result",
        "session_end_mapping": "session_finished",
        "append_mode": True,
        "stream_audio": True,
        "chunk_size": 4096,
        "chunk_interval": 0.02
    },
    "max_timeout": 60
}

# 创建 APIDriver 实例
driver = APIDriver(api_config)

# 执行 WebSocket 调用
context_data = {
    "session_id": "123456"
}

# 假设我们有一个音频文件需要发送
files = None
result = driver.execute(context_data, files=None)

# 输出结果
print(result)
```

## 注意事项

1. **WebSocket 依赖**：使用 WebSocket 功能需要安装 `websocket-client` 库
2. **超时设置**：建议根据实际情况调整超时设置，特别是对于音频流式传输
3. **路径映射**：确保映射路径与实际 API 响应格式匹配
4. **结束标志**：对于 WebSocket 调用，建议配置明确的会话结束标志
5. **资源管理**：APIDriver 会自动关闭 WebSocket 连接，无需手动管理

## 扩展建议

1. 支持更多的占位符格式（如 `${key}`）
2. 支持更复杂的模板渲染引擎（如 Jinja2）
3. 增加请求重试机制
4. 支持更多的认证方式
5. 增加响应验证功能

## 结论

APIDriver 提供了一个灵活、强大的 API 调用框架，支持 HTTP 和 WebSocket 协议，能够处理各种复杂的 API 调用场景。通过合理配置，可以轻松适应不同的 API 服务，提高测试脚本的可维护性和扩展性。