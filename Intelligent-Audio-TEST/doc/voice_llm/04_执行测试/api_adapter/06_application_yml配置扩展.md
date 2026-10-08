# 06 — application.yml 配置扩展

> **所属步骤**：04_执行测试 → api_adapter  
> **改造类型**：修改  
> **涉及文件**：`api_adaper_service/config/application.yml`

---

## 背景

voice_llm 被测 API 使用 HTTP REST 协议，需要在 `application.yml` 中配置 voice_llm vendor 的 HTTP 端点、认证信息、响应解析规则等。

---

## 改造内容

### 1. 新增 voice_llm vendor 配置

```yaml
# application.yml 新增

vendor:
  # ... 现有 volc_ast, mock 配置不变 ...

  # voice_llm HTTP vendor 配置
  voice_llm:
    protocol: http
    base_url: "${VOICE_LLM_API_BASE:http://localhost:9000}"
    headers:
      Authorization: "Bearer ${VOICE_LLM_API_KEY:}"
      Content-Type: "application/json"
    timeout: 60
    result_parser:
      asr_text_path: "result.asr_text"
      trans_text_path: "result.trans_text"
      session_id_path: "session_id"
    session:
      context_mode: "full"          # "full" | "sliding_window"
      max_history_rounds: 10
      session_timeout: 120
    concurrency:
      max_concurrent_sessions: 5
```

### 2. 完整配置结构

```yaml
server:
  host: "0.0.0.0"
  port: 8000
  dev_mode: false
  workers: 2
  max_concurrency: 100
  task_concurrency:
    zh2en: 20
    en2zh: 20
    default: 10
    dialog: 10          # 新增：对话模式并发限制

audio:
  frame_duration_ms: 80
  sample_rate: 16000
  channels: 1
  bit_depth: 16
  frame_send_interval_ms: 10

websocket:
  reconnect_max: 5
  result_recv_timeout: 30
  connect_timeout: 10
  no_heartbeat: true

vendor:
  volc_ast:
    ws_url: "${VOLC_WS_URL:}"
    # ... 现有配置 ...

  mock:
    ws_url: "mock://localhost"
    # ... 现有配置 ...

  voice_llm:                          # 新增
    protocol: http
    base_url: "${VOICE_LLM_API_BASE:http://localhost:9000}"
    headers:
      Authorization: "Bearer ${VOICE_LLM_API_KEY:}"
      Content-Type: "application/json"
    timeout: 60
    result_parser:
      asr_text_path: "result.asr_text"
      trans_text_path: "result.trans_text"
      session_id_path: "session_id"
    session:
      context_mode: "full"
      max_history_rounds: 10
      session_timeout: 120
    concurrency:
      max_concurrent_sessions: 5

result:
  max_frame_count: 100000
  task_expire_minutes: 60
  default_page_size: 1000
```

### 3. 配置字段说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `protocol` | string | `http` | 协议类型 |
| `base_url` | string | — | API 基础 URL |
| `headers` | dict | — | HTTP 请求头 |
| `timeout` | int | 60 | 请求超时（秒） |
| `result_parser.asr_text_path` | string | — | ASR 文本的 JSON 路径 |
| `result_parser.trans_text_path` | string | — | 翻译文本的 JSON 路径 |
| `session.context_mode` | string | `full` | 上下文模式 |
| `session.max_history_rounds` | int | 10 | 滑动窗口轮数 |
| `session.session_timeout` | int | 120 | 会话超时（秒） |
| `concurrency.max_concurrent_sessions` | int | 5 | 最大并发会话数 |

### 4. 环境变量覆盖

| 环境变量 | 配置项 |
|---------|--------|
| `VOICE_LLM_API_BASE` | `vendor.voice_llm.base_url` |
| `VOICE_LLM_API_KEY` | `vendor.voice_llm.headers.Authorization` |

### 5. Health 端点适配

```python
@app.route('/health')
def api_health():
    return jsonify({
        'status': 'healthy',
        'service': 'audio-executor',
        'no_heartbeat': True,
        'frame_duration_ms': config.get('audio.frame_duration_ms', 80),
        'current_concurrency': len(process_threads),
        'max_concurrency': config.get('server.max_concurrency', 100),
        'dialog_sessions': session_store.get_session_count(),  # 新增
        'supported_modes': ['streaming', 'dialog'],            # 新增
    })
```

---

## 不变部分

- 现有 `volc_ast` 和 `mock` 配置不变
- `server`、`audio`、`websocket`、`result` 配置不变
- 环境变量覆盖机制不变

---

## 依赖关系

| 依赖文档 | 说明 |
|---------|------|
| `01_voice_llm_HTTP适配器` | 使用 vendor 配置 |
| `02_会话状态管理` | 使用 session 配置 |
