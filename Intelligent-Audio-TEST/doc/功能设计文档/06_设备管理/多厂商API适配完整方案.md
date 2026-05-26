# 多厂商语音/LLM API适配完整方案

## 文档信息

| 项目 | 内容 |
|------|------|
| 版本 | v2.0 |
| 创建日期 | 2026-05-25 |
| 更新日期 | 2026-05-25 |
| 状态 | 设计阶段 |

---

## 1. 概述

### 1.1 背景

当前系统已有完整的API测试框架：
- **API配置管理**: 通过数据库存储API配置（API Model）
- **API调用驱动**: `api_driver.py` 封装调用逻辑
- **底层协议支持**: `api_client.py` 支持HTTP/WebSocket

需要扩展支持国内外主流语音识别、语音翻译、大语言模型等API，实现统一的适配层。

### 1.2 核心设计原则

1. **配置集中管理**: 所有API配置由主服务统一管理，存储在数据库中
2. **适配器无状态**: 适配器不持有配置，每次调用时由主服务传递完整配置
3. **协议透明**: 主服务不关心具体协议细节，由适配器处理
4. **结果标准化**: 所有适配器返回统一格式的结果

### 1.3 支持的厂商

#### 1.3.1 直连厂商

| 区域 | 厂商 | 服务类型 |
|------|------|----------|
| 国内 | 火山引擎 | ASR/AST/实时语音对话 |
| 国内 | 阿里云百炼 | ASR/LLM/语音翻译 |
| 国内 | 腾讯云 | ASR |
| 国内 | 百度智能云 | ASR |
| 海外 | OpenAI | ASR(Whisper)/LLM(GPT)/Realtime |
| 海外 | Google | Gemini Live/Speech-to-Text |
| 海外 | Azure | Speech Services |
| 海外 | AWS | Transcribe/Polly |

#### 1.3.2 LLM API中转站

中转站使用OpenAI兼容的API格式，**配置方式与直连OpenAI完全相同**，只需更换`endpoint`和`api_key`。

| 中转站 | 端点 (base_url) | 特点 |
|--------|-----------------|------|
| 讯星API | `https://az.gptplus5.com/v1` | 支持GPT-4/Claude/Gemini |
| OpenAI-SB | `https://api.openai-sb.com/v1` | GPT系列 |
| API2D | `https://api2d.com/v1` | GPT-4/Claude |
| CloseAI | `https://api.closeai-proxy.xyz/v1` | GPT系列 |
| 自建中转 | 自定义域名 | 自定义 |

**核心设计:**
- 中转站**复用OpenAI适配器**，无需单独开发
- 只需在API配置中更换`api_url`为中转站地址
- 请求格式、响应格式完全兼容
- **无需代理**，直接访问

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              主服务系统 (Intelligent-Audio-TEST)                 │
│                                    backend/                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────┐ │
│  │                            数据层 (Database)                               │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐           │ │
│  │  │     API 表      │  │   TestCase 表   │  │   凭据管理      │           │ │
│  │  │  - id          │  │  - config       │  │  (环境变量)     │           │ │
│  │  │  - name        │  │  - algorithm_   │  │                 │           │ │
│  │  │  - vendor      │  │    params       │  │  VOLC_APP_KEY   │           │ │
│  │  │  - api_url     │  │  - reference_   │  │  VOLC_ACCESS_KEY│           │ │
│  │  │  - meta (JSON) │  │    params       │  │  ALIYUN_API_KEY │           │ │
│  │  │  - api_        │  │                 │  │  OPENAI_API_KEY │           │ │
│  │  │    endpoints   │  │                 │  │  ...            │           │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘           │ │
│  └───────────────────────────────────────────────────────────────────────────┘ │
│                                        │                                        │
│                                        ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────────┐ │
│  │                            控制层 (Controllers)                            │ │
│  │                                                                            │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │ │
│  │  │  APIController (api_controller.py)                                  │  │ │
│  │  │  - get_all()      : 获取API列表                                     │  │ │
│  │  │  - get_one()      : 获取单个API详情                                 │  │ │
│  │  │  - create()       : 创建API配置                                     │  │ │
│  │  │  - update()       : 更新API配置                                     │  │ │
│  │  │  - delete()       : 删除API配置                                     │  │ │
│  │  │  - test_connection(): 测试API连接                                   │  │ │
│  │  └─────────────────────────────────────────────────────────────────────┘  │ │
│  │                                        │                                   │ │
│  │                                        ▼                                   │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │ │
│  │  │  ExecutionController (execution_controller.py)                      │  │ │
│  │  │  - execute_task()   : 执行测试任务                                  │  │ │
│  │  │  - execute_case()   : 执行单个用例                                  │  │ │
│  │  │  - build_execution_config(): 构建执行配置 ★核心方法★               │  │ │
│  │  └─────────────────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────────────────┘ │
│                                        │                                        │
│                                        ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────────┐ │
│  │                            驱动层 (Utils)                                  │ │
│  │                                                                            │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │ │
│  │  │  APIDriver (api_driver.py)                                          │  │ │
│  │  │  - execute()           : 执行API调用                                │  │ │
│  │  │  - _render_payload()   : 渲染请求参数                               │  │ │
│  │  │  - _parse_response()   : 解析响应结果                               │  │ │
│  │  │                                                                       │  │ │
│  │  │  ★ 现有实现: 直接调用 api_client ★                                  │  │ │
│  │  │  ★ 扩展实现: 调用 AdapterFactory ★                                  │  │ │
│  │  └─────────────────────────────────────────────────────────────────────┘  │ │
│  │                                        │                                   │ │
│  │                                        ▼                                   │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │ │
│  │  │  APIClient (api_client.py)                                          │  │ │
│  │  │  - call()              : 统一调用入口                               │  │ │
│  │  │  - _call_http()        : HTTP调用                                   │  │ │
│  │  │  - _call_websocket()   : WebSocket调用                              │  │ │
│  │  └─────────────────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────────────────┘ │
│                                        │                                        │
└────────────────────────────────────────┼────────────────────────────────────────┘
                                         │
                                         │ 传递 ExecutionConfig
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              适配器服务 (api_adaper_service)                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────┐ │
│  │                          适配器工厂 (AdapterFactory)                       │ │
│  │                                                                            │ │
│  │  create(vendor, api_type) → Adapter实例                                   │ │
│  │  execute(config) → APIResponse                                            │ │
│  └───────────────────────────────────────────────────────────────────────────┘ │
│                                        │                                        │
│         ┌──────────────────────────────┼──────────────────────────────┐        │
│         ▼                              ▼                              ▼        │
│  ┌─────────────┐               ┌─────────────┐               ┌─────────────┐  │
│  │ ASRAdapter  │               │ ASTAdapter  │               │ LLMAdapter  │  │
│  │   (基类)    │               │   (基类)    │               │   (基类)    │  │
│  └──────┬──────┘               └──────┬──────┘               └──────┬──────┘  │
│         │                              │                              │        │
│         ▼                              ▼                              ▼        │
│  ┌───────────────────────────────────────────────────────────────────────────┐ │
│  │                          厂商适配器 (Vendor Adapters)                      │ │
│  │                                                                            │ │
│  │  ★ 适配器不持有配置，每次调用接收完整配置 ★                               │ │
│  │  ★ 适配器只负责协议转换和API调用 ★                                        │ │
│  │                                                                            │ │
│  │  国内厂商:                                                                 │ │
│  │  ├─ VolcASRAdapter      (火山引擎流式ASR)                                 │ │
│  │  ├─ VolcASTAdapter      (火山引擎端到端语音翻译)                          │ │
│  │  ├─ BailianASRAdapter   (阿里云百炼ASR)                                   │ │
│  │  └─ QwenASTAdapter      (通义千问语音翻译)                                │ │
│  │                                                                            │ │
│  │  海外厂商:                                                                 │ │
│  │  ├─ WhisperAdapter      (OpenAI Whisper)                                  │ │
│  │  ├─ GPTAdapter          (OpenAI GPT)                                      │ │
│  │  ├─ GeminiAdapter       (Google Gemini)                                   │ │
│  │  └─ AzureSpeechAdapter  (Azure Speech)                                    │ │
│  └───────────────────────────────────────────────────────────────────────────┘ │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 配置数据流

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              完整配置数据流                                       │
└──────────────────────────────────────────────────────────────────────────────────┘

┌─────────────┐
│  前端请求   │
│ POST /api/  │
│ tasks/execute│
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  1. 主服务加载数据                                                               │
│                                                                                 │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐                   │
│  │  API Model    │    │ TestCase Model│    │   凭据管理    │                   │
│  │  (数据库)     │    │  (数据库)     │    │  (环境变量)   │                   │
│  │               │    │               │    │               │                   │
│  │ - id: 1       │    │ - id: "tc_01" │    │ VOLC_APP_KEY  │                   │
│  │ - name: "火山  │    │ - config: {...}│   │ VOLC_ACCESS_  │                   │
│  │   引擎ASR"    │    │ - algorithm_  │    │   KEY         │                   │
│  │ - vendor:     │    │   params: {...}│   │ ...           │                   │
│  │   "volcengine"│    │ - reference_  │    │               │                   │
│  │ - api_url:    │    │   params: {...}│   │               │                   │
│  │   "wss://..." │    │               │    │               │                   │
│  │ - meta: {     │    │               │    │               │                   │
│  │   protocol,   │    │               │    │               │                   │
│  │   auth_type,  │    │               │    │               │                   │
│  │   headers,    │    │               │    │               │                   │
│  │   body_temp,  │    │               │    │               │                   │
│  │   mappings... │    │               │    │               │                   │
│  │ }             │    │               │    │               │                   │
│  │ - api_        │    │               │    │               │                   │
│  │   endpoints:[ │    │               │    │               │                   │
│  │   {endpoint,  │    │               │    │               │                   │
│  │    max_timeout│    │               │    │               │                   │
│  │    ...}       │    │               │    │               │                   │
│  │   ]           │    │               │    │               │                   │
│  └───────┬───────┘    └───────┬───────┘    └───────┬───────┘                   │
│          │                    │                    │                           │
│          └────────────────────┼────────────────────┘                           │
│                               ▼                                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  2. 构建 ExecutionConfig                                                 │   │
│  │                                                                          │   │
│  │  execution_config = {                                                    │   │
│  │      # 基础信息                                                          │   │
│  │      "api_id": 1,                                                        │   │
│  │      "vendor": "volcengine",                                             │   │
│  │      "api_type": "asr",                                                  │   │
│  │                                                                          │   │
│  │      # 端点配置 (从 api_endpoints 选择)                                  │   │
│  │      "endpoint": "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel",  │   │
│  │      "max_timeout": 30,                                                  │   │
│  │      "max_process": 5,                                                   │   │
│  │      "max_audio_duration": 60,                                           │   │
│  │                                                                          │   │
│  │      # 元数据 (从 API.meta)                                              │   │
│  │      "meta": {                                                           │   │
│  │          "protocol": "websocket",                                        │   │
│  │          "auth_type": "header",                                          │   │
│  │          "headers": {                                                    │   │
│  │              "X-Api-App-Key": "{{app_key}}",                             │   │
│  │              "X-Api-Access-Key": "{{access_key}}",                       │   │
│  │              "X-Api-Resource-Id": "volc.seedasr.sauc.duration"           │   │
│  │          },                                                              │   │
│  │          "body_template": {                                              │   │
│  │              "user": {"uid": "{{uid}}"},                                 │   │
│  │              "audio": {                                                  │   │
│  │                  "format": "{{audio_format}}",                           │   │
│  │                  "rate": 16000                                           │   │
│  │              },                                                          │   │
│  │              "request": {"model_name": "bigmodel"}                       │   │
│  │          },                                                              │   │
│  │          "asr_mapping": "result.text",                                   │   │
│  │          "session_end_mapping": "is_end",                                │   │
│  │          "chunk_size": 3200,                                             │   │
│  │          "chunk_interval": 0.1                                           │   │
│  │      },                                                                  │   │
│  │                                                                          │   │
│  │      # 认证凭据 (从环境变量)                                              │   │
│  │      "credentials": {                                                    │   │
│  │          "app_key": "xxx",                                               │   │
│  │          "access_key": "yyy"                                             │   │
│  │      },                                                                  │   │
│  │                                                                          │   │
│  │      # 测试参数 (从 TestCase 合并)                                       │   │
│  │      "test_params": {                                                    │   │
│  │          "audio_path": "/data/audio/test.wav",                           │   │
│  │          "audio_format": "wav",                                          │   │
│  │          "language": "zh-CN",                                            │   │
│  │          "enable_punc": true,                                            │   │
│  │          "uid": "test_user_001"                                          │   │
│  │      },                                                                  │   │
│  │                                                                          │   │
│  │      # 代理配置 (海外厂商)                                               │   │
│  │      "proxy": null                                                       │   │
│  │  }                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  3. 调用适配器执行                                                               │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  AdapterFactory.execute(execution_config)                               │   │
│  │                                                                          │   │
│  │  # 3.1 根据vendor和api_type选择适配器                                    │   │
│  │  adapter = AdapterFactory.create("volcengine", "asr")                   │   │
│  │  # → VolcASRAdapter 实例                                                │   │
│  │                                                                          │   │
│  │  # 3.2 执行适配器                                                        │   │
│  │  result = adapter.execute(execution_config)                             │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                        │
│                                        ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  4. 适配器内部执行流程 (VolcASRAdapter)                                  │   │
│  │                                                                          │   │
│  │  def execute(config):                                                    │   │
│  │      # 4.1 验证配置                                                      │   │
│  │      self._validate_config(config)                                       │   │
│  │                                                                          │   │
│  │      # 4.2 建立WebSocket连接                                             │   │
│  │      headers = self._build_headers(config)                               │   │
│  │      ws = websocket.connect(config.endpoint, headers=headers)            │   │
│  │                                                                          │   │
│  │      # 4.3 发送初始请求 (full client request)                            │   │
│  │      init_request = self._render_body(config)                            │   │
│  │      ws.send(init_request)                                               │   │
│  │                                                                          │   │
│  │      # 4.4 发送音频分片                                                   │   │
│  │      for chunk in read_audio_chunks(config.test_params['audio_path']):   │   │
│  │          ws.send_binary(chunk)                                           │   │
│  │          sleep(config.meta['chunk_interval'])                            │   │
│  │                                                                          │   │
│  │      # 4.5 发送结束标志                                                   │   │
│  │      ws.send(eos_message)                                                │   │
│  │                                                                          │   │
│  │      # 4.6 接收响应并解析                                                 │   │
│  │      results = []                                                        │   │
│  │      while True:                                                         │   │
│  │          msg = ws.recv()                                                 │   │
│  │          parsed = self._parse_message(msg)                               │   │
│  │          results.append(parsed)                                          │   │
│  │          if parsed.get('is_session_end'):                                │   │
│  │              break                                                       │   │
│  │                                                                          │   │
│  │      # 4.7 关闭连接                                                       │   │
│  │      ws.close()                                                          │   │
│  │                                                                          │   │
│  │      # 4.8 返回标准化结果                                                 │   │
│  │      return APIResponse(                                                 │   │
│  │          success=True,                                                   │   │
│  │          vendor="volcengine",                                            │   │
│  │          api_type="asr",                                                 │   │
│  │          result=ASRResult(text="识别结果", ...),                         │   │
│  │          latency=LatencyStats(...)                                       │   │
│  │      )                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  5. 主服务处理结果                                                               │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  # 5.1 保存测试结果到数据库                                               │   │
│  │  test_result = TestResult(                                               │   │
│  │      task_id=task_id,                                                    │   │
│  │      test_case_id=case_id,                                               │   │
│  │      api_id=api_id,                                                      │   │
│  │      algorithm_result=result.result.to_dict(),                           │   │
│  │      response_time=result.latency.total_latency_ms                       │   │
│  │  )                                                                       │   │
│  │  db.session.add(test_result)                                             │   │
│  │                                                                          │   │
│  │  # 5.2 返回给前端                                                         │   │
│  │  return {                                                                │   │
│  │      "success": True,                                                    │   │
│  │      "result": {                                                         │   │
│  │          "text": "识别结果文本",                                         │   │
│  │          "latency_ms": 1234                                              │   │
│  │      }                                                                   │   │
│  │  }                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 数据模型设计

### 3.1 现有数据库模型 (API表)

```python
# backend/models/models.py (现有)

class API(db.Model):
    """API 配置模型"""
    __tablename__ = 'apis'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)           # API名称
    vendor = Column(String(50))                          # 厂商标识 (volcengine, aliyun, openai等)
    api_url = Column(String(512))                        # 主入口URL
    description = Column(Text)                           # 描述
    status = Column(String(20), default='online')        # 状态
    meta = Column(JSON, nullable=False)                  # ★ 元数据配置 (核心) ★
    algorithm_type = Column(String(50))                  # 算法类型 (asr, ast, llm, tts)
    max_process = Column(Integer, default=5)             # 最大并发数
    max_timeout = Column(Integer, default=30)            # 最大超时时间
    max_audio_duration = Column(Integer, default=60)     # 最大音频时长
    api_endpoints = Column(JSON, default=list)           # ★ 端点列表 (核心) ★
    # ... 其他字段
```

### 3.2 API.meta 字段结构

```json
{
    "protocol": "websocket",
    "auth_type": "header",
    "method": "POST",
    
    "headers": {
        "X-Api-App-Key": "{{app_key}}",
        "X-Api-Access-Key": "{{access_key}}",
        "X-Api-Resource-Id": "volc.seedasr.sauc.duration"
    },
    
    "body_template": {
        "user": {"uid": "{{uid}}"},
        "audio": {
            "format": "{{audio_format}}",
            "rate": 16000,
            "bits": 16,
            "channel": 1
        },
        "request": {
            "model_name": "bigmodel",
            "enable_itn": true,
            "enable_punc": true
        }
    },
    
    "response_mappings": {
        "asr_mapping": "result.text",
        "trans_mapping": "result.translation",
        "error_code_mapping": "code",
        "error_msg_mapping": "message",
        "session_end_mapping": "is_session_end",
        "sentence_end_mapping": "is_sentence_end"
    },
    
    "streaming": {
        "chunk_size": 3200,
        "chunk_interval": 0.1,
        "eos_message": {"type": "end"}
    },
    
    "adapter_specific": {
        "use_protobuf": false,
        "binary_protocol": false,
        "custom_handler": null
    }
}
```

### 3.3 API.api_endpoints 字段结构

```json
[
    {
        "endpoint": "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel",
        "name": "主节点",
        "max_process": 5,
        "max_timeout": 30,
        "max_audio_duration": 60,
        "status": "online",
        "health_score": 100,
        "priority": 0,
        "description": "火山引擎流式ASR主节点"
    },
    {
        "endpoint": "wss://openspeech-backup.bytedance.com/api/v3/sauc/bigmodel",
        "name": "备用节点",
        "max_process": 3,
        "max_timeout": 60,
        "max_audio_duration": 120,
        "status": "online",
        "health_score": 95,
        "priority": 1,
        "description": "火山引擎流式ASR备用节点"
    }
]
```

### 3.4 ExecutionConfig 执行配置

```python
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime

@dataclass
class ExecutionConfig:
    """
    执行配置 - 由主服务构建并传递给适配器
    
    这是适配器接收的唯一配置对象，包含执行API调用所需的所有信息。
    适配器不应存储此配置，仅在execute()调用期间使用。
    """
    
    # ========== 基础信息 ==========
    api_id: int                                    # API ID (数据库主键)
    vendor: str                                    # 厂商标识
    api_type: str                                  # API类型 (asr, ast, llm, tts, realtime)
    
    # ========== 端点配置 ==========
    endpoint: str                                  # API端点URL
    max_timeout: int = 30                          # 最大超时时间(秒)
    max_process: int = 5                           # 最大并发数
    max_audio_duration: int = 60                   # 最大音频时长(秒)
    
    # ========== 元数据 (从API.meta获取) ==========
    meta: Dict[str, Any] = field(default_factory=dict)
    
    # ========== 认证凭据 (从密钥管理服务获取) ==========
    credentials: Dict[str, str] = field(default_factory=dict)
    
    # ========== 测试参数 (从测试用例获取) ==========
    test_params: Dict[str, Any] = field(default_factory=dict)
    
    # ========== 代理配置 (海外API) ==========
    proxy: Optional[str] = None
    
    # ========== 回调配置 ==========
    callbacks: Dict[str, Callable] = field(default_factory=dict)
    
    # ========== 执行上下文 ==========
    task_id: Optional[int] = None                  # 任务ID
    test_case_id: Optional[str] = None             # 测试用例ID
    execution_id: Optional[str] = None             # 执行ID (用于追踪)
```

### 3.5 APIResponse 响应模型

```python
@dataclass
class ASRResult:
    """语音识别结果"""
    text: str                                      # 识别文本
    is_final: bool = False                         # 是否最终结果
    confidence: float = 0.0                        # 置信度
    start_time: int = 0                            # 开始时间
    end_time: int = 0                              # 结束时间
    language: str = ""                             # 识别语言
    speaker_id: str = ""                           # 说话人ID
    emotion: str = ""                              # 情绪
    words: List[dict] = field(default_factory=list)
    raw_response: dict = None

@dataclass
class TranslationResult:
    """语音翻译结果"""
    source_text: str                               # 源语言文本
    target_text: str                               # 目标语言文本
    source_lang: str                               # 源语言
    target_lang: str                               # 目标语言
    audio_data: bytes = None                       # TTS音频
    raw_response: dict = None

@dataclass
class LLMResult:
    """大语言模型结果"""
    content: str                                   # 回复内容
    role: str = "assistant"
    model: str = ""
    finish_reason: str = ""
    usage: dict = field(default_factory=dict)
    raw_response: dict = None

@dataclass
class LatencyStats:
    """时延统计"""
    request_start_time: datetime = None
    request_end_time: datetime = None
    total_latency_ms: float = 0                    # 总时延
    first_byte_latency_ms: float = 0               # 首字节时延
    last_byte_latency_ms: float = 0                # 尾字节时延
    asr_first_char_ms: float = None                # ASR首字时延
    asr_last_char_ms: float = None                 # ASR尾字时延

@dataclass
class APIResponse:
    """统一API响应"""
    success: bool                                  # 是否成功
    vendor: str                                    # 厂商
    api_type: str                                  # API类型
    result: Any = None                             # 结果对象
    latency: LatencyStats = None                   # 时延统计
    error_code: str = ""                           # 错误码
    error_message: str = ""                        # 错误信息
    request_id: str = ""                           # 请求ID
    raw_response: dict = None                      # 原始响应
```

---

## 4. 主服务实现

### 4.1 执行配置构建器

**文件**: `backend/utils/execution_config_builder.py` (新增)

```python
"""
执行配置构建器

职责: 从数据库加载配置，合并测试参数，构建完整的ExecutionConfig
"""
import os
from typing import Dict, Any, Optional
from dataclasses import asdict

from backend.models.models import API, TestCase
from backend.utils.execution_config import ExecutionConfig


class ExecutionConfigBuilder:
    """
    执行配置构建器
    
    从多个数据源合并配置，构建完整的ExecutionConfig对象
    """
    
    # 厂商凭据映射 (环境变量名 -> 凭据字段)
    VENDOR_CREDENTIALS_MAP = {
        'volcengine': {
            'app_key': 'VOLC_APP_KEY',
            'access_key': 'VOLC_ACCESS_KEY',
            'api_key': 'VOLC_API_KEY',
        },
        'aliyun': {
            'api_key': 'ALIYUN_API_KEY',
        },
        'tencent': {
            'secret_id': 'TENCENT_SECRET_ID',
            'secret_key': 'TENCENT_SECRET_KEY',
        },
        'baidu': {
            'api_key': 'BAIDU_API_KEY',
            'secret_key': 'BAIDU_SECRET_KEY',
        },
        'openai': {
            'api_key': 'OPENAI_API_KEY',
        },
        'google': {
            'api_key': 'GOOGLE_API_KEY',
        },
        'azure': {
            'subscription_key': 'AZURE_SUBSCRIPTION_KEY',
            'region': 'AZURE_REGION',
        },
        'aws': {
            'access_key_id': 'AWS_ACCESS_KEY_ID',
            'secret_access_key': 'AWS_SECRET_ACCESS_KEY',
            'region': 'AWS_REGION',
        },
    }
    
    # 需要代理的海外厂商
    OVERSEAS_VENDORS = ['openai', 'google', 'azure', 'aws']
    
    @classmethod
    def build(
        cls,
        api: API,
        test_case: Optional[TestCase] = None,
        test_params: Optional[Dict[str, Any]] = None,
        task_id: Optional[int] = None,
        execution_id: Optional[str] = None,
    ) -> ExecutionConfig:
        """
        构建执行配置
        
        Args:
            api: API模型实例
            test_case: 测试用例模型实例 (可选)
            test_params: 运行时测试参数 (可选)
            task_id: 任务ID
            execution_id: 执行ID
            
        Returns:
            ExecutionConfig: 完整的执行配置
        """
        # 1. 选择端点
        endpoint_config = cls._select_endpoint(api)
        
        # 2. 获取凭据
        credentials = cls._get_credentials(api.vendor)
        
        # 3. 合并测试参数
        merged_params = cls._merge_test_params(test_case, test_params)
        
        # 4. 获取代理
        proxy = cls._get_proxy(api.vendor)
        
        # 5. 构建ExecutionConfig
        config = ExecutionConfig(
            api_id=api.id,
            vendor=api.vendor,
            api_type=api.algorithm_type,
            
            endpoint=endpoint_config['endpoint'],
            max_timeout=endpoint_config.get('max_timeout', api.max_timeout),
            max_process=endpoint_config.get('max_process', api.max_process),
            max_audio_duration=endpoint_config.get('max_audio_duration', api.max_audio_duration),
            
            meta=api.meta or {},
            credentials=credentials,
            test_params=merged_params,
            proxy=proxy,
            
            task_id=task_id,
            test_case_id=test_case.id if test_case else None,
            execution_id=execution_id,
        )
        
        return config
    
    @classmethod
    def _select_endpoint(cls, api: API) -> Dict[str, Any]:
        """
        选择API端点
        
        策略: 
        1. 优先选择状态为online的端点
        2. 按优先级排序 (priority越小越优先)
        3. 按健康分数排序 (health_score越高越优先)
        """
        if not api.api_endpoints:
            return {
                'endpoint': api.api_url,
                'max_timeout': api.max_timeout,
                'max_process': api.max_process,
                'max_audio_duration': api.max_audio_duration,
            }
        
        # 筛选在线端点
        online_endpoints = [
            ep for ep in api.api_endpoints
            if ep.get('status', 'online') == 'online'
        ]
        
        if not online_endpoints:
            # 如果没有在线端点，使用第一个
            online_endpoints = api.api_endpoints
        
        # 按优先级和健康分数排序
        sorted_endpoints = sorted(
            online_endpoints,
            key=lambda x: (x.get('priority', 0), -x.get('health_score', 100))
        )
        
        return sorted_endpoints[0]
    
    @classmethod
    def _get_credentials(cls, vendor: str) -> Dict[str, str]:
        """获取厂商凭据"""
        credential_map = cls.VENDOR_CREDENTIALS_MAP.get(vendor, {})
        credentials = {}
        
        for field_name, env_name in credential_map.items():
            value = os.getenv(env_name)
            if value:
                credentials[field_name] = value
        
        return credentials
    
    @classmethod
    def _merge_test_params(
        cls,
        test_case: Optional[TestCase],
        runtime_params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        合并测试参数
        
        优先级: runtime_params > test_case.algorithm_params > test_case.config
        """
        params = {}
        
        # 1. 从测试用例config获取基础参数
        if test_case and test_case.config:
            config = test_case.config
            # 提取音频相关参数
            if 'audio' in config:
                params['audio_path'] = config['audio'].get('file_path')
                params['audio_format'] = config['audio'].get('format', 'wav')
        
        # 2. 从测试用例algorithm_params获取算法参数
        if test_case and test_case.algorithm_params:
            params.update(test_case.algorithm_params)
        
        # 3. 从运行时参数覆盖
        if runtime_params:
            params.update(runtime_params)
        
        return params
    
    @classmethod
    def _get_proxy(cls, vendor: str) -> Optional[str]:
        """获取代理配置"""
        if vendor in cls.OVERSEAS_VENDORS:
            return os.getenv('HTTP_PROXY') or os.getenv('HTTPS_PROXY')
        return None
```

### 4.2 API Driver 扩展

**文件**: `backend/utils/api_driver.py` (修改)

```python
import time
import json
from backend.utils.api_client import api_client
from backend.utils.execution_config_builder import ExecutionConfigBuilder
from backend.utils.execution_config import ExecutionConfig

class APIDriver:
    """
    API 驱动程序：封装 API 调用逻辑、参数渲染及响应解析
    
    支持两种模式:
    1. 通用模式: 直接调用 api_client (现有逻辑)
    2. 适配器模式: 调用 AdapterFactory (新增逻辑)
    """
    
    def __init__(self, api_config, case_config=None, endpoint=None):
        """
        :param api_config: API 模型实例
        :param case_config: 用例级特定配置
        :param endpoint: 可选的端点 URL
        """
        self.api_config = api_config
        self.endpoint = endpoint or (api_config.endpoint if hasattr(api_config, 'endpoint') else None)
        self.meta = api_config.meta or {}
        self.case_config = case_config or {}
        
    def execute(self, context_data, files=None, method=None):
        """
        执行 API 调用并解析结果
        
        根据配置自动选择调用模式:
        - 如果 meta 中指定了 adapter，使用适配器模式
        - 否则使用通用模式
        """
        # 检查是否使用适配器模式
        adapter_type = self.meta.get('adapter_type')
        
        if adapter_type:
            return self._execute_with_adapter(context_data)
        else:
            return self._execute_generic(context_data, files, method)
    
    def _execute_generic(self, context_data, files=None, method=None):
        """通用模式执行 (现有逻辑)"""
        # ... 现有的 execute 逻辑 ...
        pass
    
    def _execute_with_adapter(self, context_data):
        """
        适配器模式执行 (新增逻辑)
        
        使用 AdapterFactory 调用厂商特定的适配器
        """
        from api_adaper_service.services.adapter_factory import AdapterFactory
        
        # 1. 构建 ExecutionConfig
        config = ExecutionConfig(
            api_id=self.api_config.id,
            vendor=self.api_config.vendor,
            api_type=self.api_config.algorithm_type,
            endpoint=self.endpoint,
            max_timeout=self.api_config.max_timeout,
            max_process=self.api_config.max_process,
            max_audio_duration=self.api_config.max_audio_duration,
            meta=self.meta,
            credentials=self._get_credentials(),
            test_params=context_data,
        )
        
        # 2. 调用适配器
        response = AdapterFactory.execute(config)
        
        # 3. 转换为统一格式
        return {
            "success": response.success,
            "latency": response.latency.total_latency_ms if response.latency else 0,
            "status_code": 200 if response.success else 500,
            "raw_response": response.raw_response,
            "error": response.error_message if not response.success else None,
            "json": response.raw_response,
            "asr": response.result.text if response.result else "",
            "trans": "",
        }
    
    def _get_credentials(self):
        """获取凭据"""
        import os
        vendor = self.api_config.vendor
        
        credentials_map = {
            'volcengine': {
                'app_key': os.getenv('VOLC_APP_KEY'),
                'access_key': os.getenv('VOLC_ACCESS_KEY'),
            },
            'aliyun': {
                'api_key': os.getenv('ALIYUN_API_KEY'),
            },
            'openai': {
                'api_key': os.getenv('OPENAI_API_KEY'),
            },
        }
        
        return credentials_map.get(vendor, {})
```

### 4.3 执行控制器修改

**文件**: `backend/controllers/execution_controller.py` (修改)

```python
from backend.models.models import API, TestCase, Task, TestResult
from backend.models.database import db
from backend.utils.execution_config_builder import ExecutionConfigBuilder
from api_adaper_service.services.adapter_factory import AdapterFactory

class ExecutionController:
    """执行控制器"""
    
    @staticmethod
    def execute_single_case(task_id: int, test_case_id: str, api_id: int):
        """
        执行单个测试用例
        
        流程:
        1. 加载数据
        2. 构建配置
        3. 调用适配器
        4. 保存结果
        """
        # 1. 加载数据
        task = Task.query.get(task_id)
        test_case = TestCase.query.get(test_case_id)
        api = API.query.get(api_id)
        
        if not all([task, test_case, api]):
            return {'success': False, 'error': '数据不存在'}
        
        # 2. 构建执行配置
        execution_config = ExecutionConfigBuilder.build(
            api=api,
            test_case=test_case,
            task_id=task_id,
            execution_id=f"{task_id}_{test_case_id}_{api_id}",
        )
        
        # 3. 调用适配器执行
        result = AdapterFactory.execute(execution_config)
        
        # 4. 保存结果
        test_result = TestResult(
            task_id=task_id,
            test_case_id=test_case_id,
            api_id=api_id,
            algorithm_type=api.algorithm_type,
            execution_status='completed' if result.success else 'failed',
            response_time=result.latency.total_latency_ms if result.latency else 0,
            algorithm_result=result.result.to_dict() if result.result else {},
            error_message=result.error_message if not result.success else None,
        )
        db.session.add(test_result)
        db.session.commit()
        
        return {
            'success': result.success,
            'result': result.result.to_dict() if result.result else {},
            'latency_ms': result.latency.total_latency_ms if result.latency else 0,
            'error': result.error_message if not result.success else None,
        }
```

---

## 5. 适配器服务实现

### 5.1 适配器基类

**文件**: `api_adaper_service/adapters/base/base_adapter.py`

```python
"""
适配器基类

设计原则:
1. 适配器不持有任何配置状态
2. 所有配置通过execute()方法传入
3. 适配器只负责协议转换和API调用
4. 每次执行都是独立的，无状态依赖
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass

from api_adaper_service.models.execution_config import ExecutionConfig
from api_adaper_service.models.api_response import APIResponse, LatencyStats


class BaseAdapter(ABC):
    """
    适配器基类
    
    所有厂商适配器必须继承此类并实现 _do_execute 方法
    """
    
    # 类属性 - 子类必须覆盖
    vendor: str = ""                    # 厂商标识
    api_type: str = ""                  # API类型
    
    def __init__(self):
        """
        初始化适配器 - 不接收任何配置参数
        
        适配器实例可以被复用，但每次执行时必须传入完整配置
        """
        self._current_config: Optional[ExecutionConfig] = None
        self._callbacks: Dict[str, Callable] = {}
    
    def execute(self, config: ExecutionConfig) -> APIResponse:
        """
        执行API调用 - 主入口方法
        
        Args:
            config: 完整的执行配置
            
        Returns:
            APIResponse: 统一格式的响应结果
        """
        self._current_config = config
        self._callbacks = config.callbacks or {}
        
        latency = LatencyStats()
        latency.request_start_time = datetime.now()
        
        try:
            # 1. 验证配置
            self._validate_config(config)
            
            # 2. 执行具体逻辑
            result = self._do_execute(config)
            
            # 3. 计算时延
            latency.request_end_time = datetime.now()
            latency.total_latency_ms = (latency.request_end_time - latency.request_start_time).total_seconds() * 1000
            result.latency = latency
            
            return result
            
        except Exception as e:
            latency.request_end_time = datetime.now()
            latency.total_latency_ms = (latency.request_end_time - latency.request_start_time).total_seconds() * 1000
            
            return APIResponse(
                success=False,
                vendor=config.vendor,
                api_type=config.api_type,
                error_code='EXECUTION_ERROR',
                error_message=str(e),
                latency=latency
            )
        finally:
            self._current_config = None
    
    @abstractmethod
    def _do_execute(self, config: ExecutionConfig) -> APIResponse:
        """
        执行具体API调用逻辑 - 子类必须实现
        
        Args:
            config: 执行配置
            
        Returns:
            APIResponse: 响应结果
        """
        pass
    
    def _validate_config(self, config: ExecutionConfig):
        """验证配置有效性"""
        if not config.endpoint:
            raise ValueError("endpoint is required")
        
        # 子类可覆盖添加更多验证
        self._validate_credentials(config)
    
    def _validate_credentials(self, config: ExecutionConfig):
        """验证凭据"""
        required = self.get_required_credentials()
        for field in required:
            if field not in config.credentials or not config.credentials[field]:
                raise ValueError(f"Missing required credential: {field}")
    
    def _trigger_callback(self, callback_type: str, *args, **kwargs):
        """触发回调"""
        if callback_type in self._callbacks:
            self._callbacks[callback_type](*args, **kwargs)
    
    @classmethod
    @abstractmethod
    def get_supported_features(cls) -> List[str]:
        """获取支持的特性列表"""
        pass
    
    @classmethod
    @abstractmethod
    def get_required_credentials(cls) -> List[str]:
        """获取必需的凭据字段"""
        pass
```

### 5.2 ASR适配器基类

**文件**: `api_adaper_service/adapters/base/asr_adapter.py`

```python
from abc import abstractmethod
from typing import List

from api_adaper_service.adapters.base.base_adapter import BaseAdapter
from api_adaper_service.models.execution_config import ExecutionConfig
from api_adaper_service.models.api_response import APIResponse, ASRResult


class ASRAdapter(BaseAdapter):
    """
    语音识别适配器基类
    
    所有ASR适配器继承此类
    """
    
    api_type = "asr"
    
    def _do_execute(self, config: ExecutionConfig) -> APIResponse:
        """执行ASR识别"""
        audio_path = config.test_params.get('audio_path')
        
        if not audio_path:
            return APIResponse(
                success=False,
                vendor=config.vendor,
                api_type=self.api_type,
                error_code='MISSING_AUDIO',
                error_message='audio_path is required in test_params'
            )
        
        # 根据协议选择执行方式
        protocol = config.meta.get('protocol', 'http')
        
        if protocol in ['websocket', 'websocket_protobuf']:
            return self._execute_streaming(config)
        else:
            return self._execute_file(config)
    
    @abstractmethod
    def _execute_streaming(self, config: ExecutionConfig) -> APIResponse:
        """执行流式识别"""
        pass
    
    @abstractmethod
    def _execute_file(self, config: ExecutionConfig) -> APIResponse:
        """执行文件识别"""
        pass
    
    @classmethod
    def get_supported_features(cls) -> List[str]:
        """ASR支持的特性"""
        return [
            'streaming',
            'punctuation',
            'itn',
            'speaker_diarization',
            'emotion_detection',
            'language_identification',
            'hot_words',
        ]
```

### 5.3 火山引擎ASR适配器

**文件**: `api_adaper_service/adapters/volcengine/volc_asr_adapter.py`

```python
"""
火山引擎流式语音识别适配器

参考文档: https://www.volcengine.com/docs/6561/1354869
"""
import time
import json
import uuid
import os
from typing import List
import websocket

from api_adaper_service.adapters.base.asr_adapter import ASRAdapter
from api_adaper_service.models.execution_config import ExecutionConfig
from api_adaper_service.models.api_response import APIResponse, ASRResult, LatencyStats


class VolcASRAdapter(ASRAdapter):
    """
    火山引擎流式语音识别适配器
    
    协议: WebSocket
    认证: Header (X-Api-App-Key, X-Api-Access-Key, X-Api-Resource-Id)
    """
    
    vendor = "volcengine"
    
    # 资源ID
    RESOURCE_ID_DURATION = "volc.seedasr.sauc.duration"
    RESOURCE_ID_CONCURRENT = "volc.seedasr.sauc.concurrent"
    
    @classmethod
    def get_required_credentials(cls) -> List[str]:
        """必需凭据"""
        return ['app_key', 'access_key']
    
    def _execute_streaming(self, config: ExecutionConfig) -> APIResponse:
        """执行流式识别"""
        audio_path = config.test_params.get('audio_path')
        
        # 1. 构建请求头
        headers = self._build_headers(config)
        
        # 2. 建立WebSocket连接
        ws = None
        all_results = []
        latency = LatencyStats()
        
        try:
            ws = websocket.create_connection(
                config.endpoint,
                header=headers,
                timeout=config.max_timeout
            )
            
            latency.first_byte_latency_ms = 0
            
            # 3. 发送初始请求
            init_request = self._build_init_request(config)
            ws.send(json.dumps(init_request, ensure_ascii=False))
            
            # 4. 发送音频分片
            chunk_size = config.meta.get('streaming', {}).get('chunk_size', 3200)
            chunk_interval = config.meta.get('streaming', {}).get('chunk_interval', 0.1)
            
            with open(audio_path, 'rb') as f:
                # 跳过WAV头 (44字节)
                if audio_path.endswith('.wav'):
                    f.read(44)
                
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    
                    ws.send(chunk, websocket.ABNF.OPCODE_BINARY)
                    time.sleep(chunk_interval)
            
            # 5. 发送结束标志
            eos_message = config.meta.get('streaming', {}).get('eos_message', {})
            if eos_message:
                ws.send(json.dumps(eos_message, ensure_ascii=False))
            
            # 6. 接收响应
            session_end_mapping = config.meta.get('response_mappings', {}).get('session_end_mapping', 'is_session_end')
            asr_mapping = config.meta.get('response_mappings', {}).get('asr_mapping', 'result.text')
            
            ws.settimeout(5)
            
            while True:
                try:
                    msg = ws.recv()
                    if not msg:
                        break
                    
                    try:
                        msg_json = json.loads(msg)
                        
                        # 提取ASR结果
                        text = self._extract_by_path(msg_json, asr_mapping)
                        if text:
                            all_results.append(text)
                        
                        # 检查会话结束
                        if self._extract_by_path(msg_json, session_end_mapping):
                            break
                            
                    except json.JSONDecodeError:
                        pass
                        
                except websocket.WebSocketTimeoutException:
                    break
            
            # 7. 关闭连接
            ws.close()
            
        except Exception as e:
            if ws:
                ws.close()
            return APIResponse(
                success=False,
                vendor=config.vendor,
                api_type=self.api_type,
                error_code='CONNECTION_ERROR',
                error_message=str(e)
            )
        
        # 8. 构建结果
        final_text = ''.join(all_results)
        
        return APIResponse(
            success=True,
            vendor=config.vendor,
            api_type=self.api_type,
            result=ASRResult(
                text=final_text,
                is_final=True,
            ),
            latency=latency
        )
    
    def _execute_file(self, config: ExecutionConfig) -> APIResponse:
        """执行文件识别 (录音文件识别API)"""
        import requests
        
        audio_path = config.test_params.get('audio_path')
        
        # 1. 提交任务
        submit_url = config.meta.get('file_api', {}).get('submit_url', 
            config.endpoint.replace('/submit', '/submit'))
        
        headers = self._build_headers(config)
        
        # 构建请求体
        body = {
            "user": {"uid": config.test_params.get('uid', 'test_user')},
            "audio": {
                "url": config.test_params.get('audio_url'),  # 需要提供可访问的URL
                "format": config.test_params.get('audio_format', 'wav'),
            },
            "request": {
                "model_name": "bigmodel",
            }
        }
        
        response = requests.post(submit_url, headers=headers, json=body, timeout=config.max_timeout)
        
        if response.status_code != 200:
            return APIResponse(
                success=False,
                vendor=config.vendor,
                api_type=self.api_type,
                error_code='SUBMIT_ERROR',
                error_message=f"Submit failed: {response.status_code}"
            )
        
        # 2. 轮询查询结果
        task_id = response.headers.get('X-Api-Request-Id')
        query_url = config.meta.get('file_api', {}).get('query_url',
            config.endpoint.replace('/submit', '/query'))
        
        # ... 轮询逻辑 ...
        
        return APIResponse(
            success=True,
            vendor=config.vendor,
            api_type=self.api_type,
            result=ASRResult(text="", is_final=True)
        )
    
    def _build_headers(self, config: ExecutionConfig) -> dict:
        """构建请求头"""
        resource_id = config.meta.get('resource_id', self.RESOURCE_ID_DURATION)
        
        return {
            "X-Api-App-Key": config.credentials.get('app_key', ''),
            "X-Api-Access-Key": config.credentials.get('access_key', ''),
            "X-Api-Resource-Id": resource_id,
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }
    
    def _build_init_request(self, config: ExecutionConfig) -> dict:
        """构建初始请求"""
        body_template = config.meta.get('body_template', {})
        
        # 渲染模板
        request = {}
        for key, value in body_template.items():
            if isinstance(value, dict):
                request[key] = {}
                for k, v in value.items():
                    if isinstance(v, str) and v.startswith('{{') and v.endswith('}}'):
                        param_name = v[2:-2].strip()
                        request[key][k] = config.test_params.get(param_name, v)
                    else:
                        request[key][k] = v
            else:
                request[key] = value
        
        return request
    
    def _extract_by_path(self, data, path: str):
        """从字典中根据路径提取值"""
        if not path or not data:
            return None
        try:
            for key in path.split('.'):
                if isinstance(data, dict):
                    data = data.get(key)
                elif isinstance(data, list) and key.isdigit():
                    data = data[int(key)]
                else:
                    return None
            return data
        except:
            return None
```

### 5.4 适配器工厂

**文件**: `api_adaper_service/services/adapter_factory.py`

```python
"""
适配器工厂

职责:
1. 管理适配器注册表
2. 根据vendor和api_type创建适配器实例
3. 提供便捷的执行方法
"""
from typing import Dict, Type, Optional, List

from api_adaper_service.adapters.base.base_adapter import BaseAdapter
from api_adaper_service.models.execution_config import ExecutionConfig
from api_adaper_service.models.api_response import APIResponse


class AdapterFactory:
    """
    适配器工厂
    
    使用注册模式管理所有适配器
    """
    
    # 适配器注册表: {"{vendor}_{api_type}": AdapterClass}
    _registry: Dict[str, Type[BaseAdapter]] = {}
    
    @classmethod
    def register(cls, vendor: str, api_type: str, adapter_class: Type[BaseAdapter]):
        """
        注册适配器
        
        Args:
            vendor: 厂商标识
            api_type: API类型
            adapter_class: 适配器类
        """
        key = f"{vendor}_{api_type}"
        cls._registry[key] = adapter_class
    
    @classmethod
    def create(cls, vendor: str, api_type: str) -> BaseAdapter:
        """
        创建适配器实例
        
        注意: 此方法只创建适配器实例，不传入任何配置
        配置通过adapter.execute(config)方法传入
        
        Args:
            vendor: 厂商标识
            api_type: API类型
            
        Returns:
            适配器实例
            
        Raises:
            ValueError: 不支持的厂商或API类型
        """
        key = f"{vendor}_{api_type}"
        if key not in cls._registry:
            available = list(cls._registry.keys())
            raise ValueError(f"Unsupported adapter: {key}. Available: {available}")
        
        return cls._registry[key]()
    
    @classmethod
    def execute(cls, config: ExecutionConfig) -> APIResponse:
        """
        便捷方法: 创建适配器并执行
        
        Args:
            config: 执行配置
            
        Returns:
            API响应结果
        """
        adapter = cls.create(config.vendor, config.api_type)
        return adapter.execute(config)
    
    @classmethod
    def list_adapters(cls) -> List[str]:
        """列出所有已注册的适配器"""
        return list(cls._registry.keys())
    
    @classmethod
    def get_adapter_info(cls, vendor: str, api_type: str) -> Optional[Dict]:
        """
        获取适配器信息
        
        Returns:
            {'vendor': ..., 'api_type': ..., 'features': [...], 'required_credentials': [...]}
        """
        key = f"{vendor}_{api_type}"
        if key not in cls._registry:
            return None
        
        adapter_class = cls._registry[key]
        return {
            'vendor': vendor,
            'api_type': api_type,
            'features': adapter_class.get_supported_features(),
            'required_credentials': adapter_class.get_required_credentials()
        }


def auto_register_adapters():
    """
    自动注册所有适配器
    
    在应用启动时调用此函数
    """
    # 国内厂商
    from api_adaper_service.adapters.volcengine.volc_asr_adapter import VolcASRAdapter
    from api_adaper_service.adapters.volcengine.volc_ast_adapter import VolcASTAdapter
    from api_adaper_service.adapters.aliyun.bailian_asr_adapter import BailianASRAdapter
    from api_adaper_service.adapters.aliyun.qwen_ast_adapter import QwenASTAdapter
    
    # 海外厂商
    from api_adaper_service.adapters.openai.whisper_adapter import WhisperAdapter
    from api_adaper_service.adapters.openai.gpt_adapter import GPTAdapter
    from api_adaper_service.adapters.google.gemini_adapter import GeminiAdapter
    from api_adaper_service.adapters.azure.azure_speech_adapter import AzureSpeechAdapter
    
    # 注册火山引擎
    AdapterFactory.register("volcengine", "asr", VolcASRAdapter)
    AdapterFactory.register("volcengine", "ast", VolcASTAdapter)
    
    # 注册阿里云
    AdapterFactory.register("aliyun", "asr", BailianASRAdapter)
    AdapterFactory.register("aliyun", "ast", QwenASTAdapter)
    
    # 注册OpenAI
    AdapterFactory.register("openai", "asr", WhisperAdapter)
    AdapterFactory.register("openai", "llm", GPTAdapter)
    
    # 注册Google
    AdapterFactory.register("google", "realtime", GeminiAdapter)
    
    # 注册Azure
    AdapterFactory.register("azure", "asr", AzureSpeechAdapter)


# 应用启动时自动注册
auto_register_adapters()
```

---

## 6. 文件结构

```
Intelligent-Audio-TEST/
├── backend/
│   ├── models/
│   │   ├── models.py                    # 现有: API Model
│   │   └── database.py
│   │
│   ├── controllers/
│   │   ├── api_controller.py            # 现有: API配置管理
│   │   └── execution_controller.py      # 修改: 执行控制器
│   │
│   ├── utils/
│   │   ├── api_client.py                # 现有: 底层协议调用
│   │   ├── api_driver.py                # 修改: 扩展适配器模式
│   │   ├── execution_config_builder.py  # 新增: 配置构建器
│   │   └── ...
│   │
│   └── blueprints/
│       └── api_bp.py                    # 现有: API路由
│
└── api_adaper_service/                   # 适配器服务 (新增)
    │
    ├── adapters/
    │   ├── __init__.py
    │   │
    │   ├── base/
    │   │   ├── __init__.py
    │   │   ├── base_adapter.py           # 基类
    │   │   ├── asr_adapter.py            # ASR基类
    │   │   ├── ast_adapter.py            # AST基类
    │   │   ├── llm_adapter.py            # LLM基类
    │   │   └── realtime_adapter.py       # 实时对话基类
    │   │
    │   ├── volcengine/                    # 火山引擎
    │   │   ├── __init__.py
    │   │   ├── volc_asr_adapter.py
    │   │   └── volc_ast_adapter.py
    │   │
    │   ├── aliyun/                        # 阿里云
    │   │   ├── __init__.py
    │   │   ├── bailian_asr_adapter.py
    │   │   └── qwen_ast_adapter.py
    │   │
    │   ├── openai/                        # OpenAI
    │   │   ├── __init__.py
    │   │   ├── whisper_adapter.py
    │   │   └── gpt_adapter.py
    │   │
    │   ├── google/                        # Google
    │   │   ├── __init__.py
    │   │   └── gemini_adapter.py
    │   │
    │   ├── azure/                         # Azure
    │   │   ├── __init__.py
    │   │   └── azure_speech_adapter.py
    │   │
    │   └── mock_adapter.py               # Mock适配器
    │
    ├── models/
    │   ├── __init__.py
    │   ├── execution_config.py           # ExecutionConfig
    │   └── api_response.py               # APIResponse等
    │
    ├── services/
    │   ├── __init__.py
    │   └── adapter_factory.py            # 适配器工厂
    │
    ├── protocols/
    │   ├── __init__.py
    │   ├── websocket_handler.py          # WebSocket处理
    │   └── protobuf_handler.py           # Protobuf处理
    │
    └── __init__.py
```

---

## 7. API配置示例

### 7.1 火山引擎ASR配置

```json
{
    "name": "火山引擎流式ASR",
    "vendor": "volcengine",
    "api_url": "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel",
    "algorithm_type": "asr",
    "meta": {
        "adapter_type": "volcengine_asr",
        "protocol": "websocket",
        "auth_type": "header",
        "resource_id": "volc.seedasr.sauc.duration",
        
        "headers": {
            "X-Api-App-Key": "{{app_key}}",
            "X-Api-Access-Key": "{{access_key}}",
            "X-Api-Resource-Id": "{{resource_id}}"
        },
        
        "body_template": {
            "user": {"uid": "{{uid}}"},
            "audio": {
                "format": "{{audio_format}}",
                "rate": 16000,
                "bits": 16,
                "channel": 1,
                "language": "{{language}}"
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": true,
                "enable_punc": true
            }
        },
        
        "response_mappings": {
            "asr_mapping": "result.text",
            "session_end_mapping": "is_session_end"
        },
        
        "streaming": {
            "chunk_size": 3200,
            "chunk_interval": 0.1
        }
    },
    
    "api_endpoints": [
        {
            "endpoint": "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel",
            "name": "主节点",
            "max_timeout": 30,
            "max_process": 5
        }
    ]
}
```

### 7.2 阿里云百炼ASR配置

```json
{
    "name": "阿里云百炼实时ASR",
    "vendor": "aliyun",
    "api_url": "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
    "algorithm_type": "asr",
    "meta": {
        "adapter_type": "aliyun_asr",
        "protocol": "websocket",
        "auth_type": "bearer",
        
        "headers": {
            "Authorization": "Bearer {{api_key}}"
        },
        
        "body_template": {
            "model": "fun-asr-realtime",
            "format": "{{audio_format}}",
            "sample_rate": 16000
        },
        
        "response_mappings": {
            "asr_mapping": "output.sentence.text",
            "session_end_mapping": "output.sentence.end_time"
        },
        
        "streaming": {
            "chunk_size": 3200,
            "chunk_interval": 0.1
        }
    }
}
```

### 7.3 OpenAI Whisper配置

```json
{
    "name": "OpenAI Whisper",
    "vendor": "openai",
    "api_url": "https://api.openai.com/v1/audio/transcriptions",
    "algorithm_type": "asr",
    "meta": {
        "adapter_type": "openai_asr",
        "protocol": "http",
        "auth_type": "bearer",
        "method": "POST",
        
        "headers": {
            "Authorization": "Bearer {{api_key}}"
        },
        
        "body_template": {
            "model": "whisper-1",
            "language": "{{language}}"
        },
        
        "response_mappings": {
            "asr_mapping": "text"
        },
        
        "requires_proxy": true
    }
}
```

### 7.4 LLM API中转站配置

**核心原则: 中转站复用OpenAI适配器，只需更换endpoint**

#### 7.4.1 直连OpenAI配置

```json
{
    "name": "OpenAI GPT-4 (直连)",
    "vendor": "openai",
    "api_url": "https://api.openai.com/v1/chat/completions",
    "algorithm_type": "llm",
    "meta": {
        "adapter_type": "openai_llm",
        "protocol": "http",
        "auth_type": "bearer",
        "method": "POST",
        "requires_proxy": true,
        
        "headers": {
            "Authorization": "Bearer {{api_key}}",
            "Content-Type": "application/json"
        },
        
        "body_template": {
            "model": "{{model}}",
            "messages": "{{messages}}",
            "temperature": 0.7,
            "max_tokens": 2048
        },
        
        "response_mappings": {
            "content_mapping": "choices[0].message.content",
            "usage_mapping": "usage"
        }
    }
}
```

#### 7.4.2 讯星API中转站配置 (只需改endpoint和api_key)

```json
{
    "name": "讯星API-GPT4",
    "vendor": "openai",
    "api_url": "https://az.gptplus5.com/v1/chat/completions",
    "algorithm_type": "llm",
    "meta": {
        "adapter_type": "openai_llm",
        "protocol": "http",
        "auth_type": "bearer",
        "method": "POST",
        "requires_proxy": false,
        
        "headers": {
            "Authorization": "Bearer {{api_key}}",
            "Content-Type": "application/json"
        },
        
        "body_template": {
            "model": "{{model}}",
            "messages": "{{messages}}",
            "temperature": 0.7,
            "max_tokens": 2048
        },
        
        "response_mappings": {
            "content_mapping": "choices[0].message.content",
            "usage_mapping": "usage"
        }
    }
}
```

#### 7.4.3 配置对比

| 配置项 | 直连OpenAI | 中转站 | 说明 |
|--------|------------|--------|------|
| `vendor` | `openai` | `openai` | **相同**，复用同一适配器 |
| `api_url` | `api.openai.com` | 中转站域名 | **唯一区别** |
| `api_key` | OpenAI官方Key | 中转站Key | **唯一区别** |
| `body_template` | 相同 | 相同 | 请求格式兼容 |
| `response_mappings` | 相同 | 相同 | 响应格式兼容 |
| `requires_proxy` | `true` | `false` | 中转站无需代理 |

### 7.5 中转站与直连对比

| 特性 | 直连OpenAI | 中转站 |
|------|------------|--------|
| 端点 | `api.openai.com` | 中转站域名 |
| 需要代理 | ✅ 是 | ❌ 否 |
| 响应速度 | 较慢(需代理) | 较快 |
| 稳定性 | 依赖代理 | 较稳定 |
| 费用 | 官方价格 | 可能有折扣 |
| 适配器 | OpenAIAdapter | **复用OpenAIAdapter** |

### 7.6 OpenAI适配器 (同时支持直连和中转站)

**文件**: `api_adaper_service/adapters/openai/openai_adapter.py`

```python
"""
OpenAI适配器

支持:
- 直连OpenAI (需要代理)
- 所有OpenAI兼容的中转站 (无需代理)

只需更换endpoint即可切换
"""
import time
import json
import requests
from typing import List

from api_adaper_service.adapters.base.llm_adapter import LLMAdapter
from api_adaper_service.models.execution_config import ExecutionConfig
from api_adaper_service.models.api_response import APIResponse, LLMResult, LatencyStats


class OpenAIAdapter(LLMAdapter):
    """
    OpenAI适配器
    
    同时支持直连和中转站，配置方式完全相同
    """
    
    vendor = "openai"
    api_type = "llm"
    
    @classmethod
    def get_required_credentials(cls) -> List[str]:
        return ['api_key']
    
    def _execute_chat(self, config: ExecutionConfig, 
                      messages: List[dict], 
                      model: str) -> APIResponse:
        """执行对话"""
        
        latency = LatencyStats()
        latency.request_start_time = datetime.now()
        
        try:
            headers = {
                "Authorization": f"Bearer {config.credentials.get('api_key')}",
                "Content-Type": "application/json"
            }
            
            body = {
                "model": model,
                "messages": messages,
                "temperature": config.test_params.get('temperature', 0.7),
                "max_tokens": config.test_params.get('max_tokens', 2048),
                "stream": config.test_params.get('stream', False)
            }
            
            # 根据requires_proxy决定是否使用代理
            proxies = None
            if config.meta.get('requires_proxy', False) and config.proxy:
                proxies = {"http": config.proxy, "https": config.proxy}
            
            response = requests.post(
                config.endpoint,
                headers=headers,
                json=body,
                timeout=config.max_timeout,
                proxies=proxies
            )
            
            latency.first_byte_latency_ms = response.elapsed.total_seconds() * 1000
            
            if response.status_code != 200:
                return APIResponse(
                    success=False,
                    vendor=config.vendor,
                    api_type=self.api_type,
                    error_code=str(response.status_code),
                    error_message=response.text,
                    latency=latency
                )
            
            result = response.json()
            latency.request_end_time = datetime.now()
            latency.total_latency_ms = (latency.request_end_time - latency.request_start_time).total_seconds() * 1000
            
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            usage = result.get('usage', {})
            
            return APIResponse(
                success=True,
                vendor=config.vendor,
                api_type=self.api_type,
                result=LLMResult(
                    content=content,
                    model=model,
                    usage=usage,
                    raw_response=result
                ),
                latency=latency,
                raw_response=result
            )
            
        except Exception as e:
            latency.request_end_time = datetime.now()
            latency.total_latency_ms = (latency.request_end_time - latency.request_start_time).total_seconds() * 1000
            
            return APIResponse(
                success=False,
                vendor=config.vendor,
                api_type=self.api_type,
                error_code='REQUEST_ERROR',
                error_message=str(e),
                latency=latency
            )
    
    @classmethod
    def get_supported_features(cls) -> List[str]:
        return ['streaming', 'function_calling', 'vision']
```

### 7.7 适配器注册

```python
# 中转站复用OpenAI适配器，无需单独注册
# 只需在API配置中更换api_url即可

AdapterFactory.register("openai", "llm", OpenAIAdapter)
```

---

## 8. 调用时序图

```
┌─────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  前端   │     │ APIController│     │ ExecutionCtrl│     │ AdapterFactory│    │ VendorAdapter│
└────┬────┘     └──────┬───────┘     └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
     │                 │                    │                    │                    │
     │ POST /execute   │                    │                    │                    │
     │────────────────>│                    │                    │                    │
     │                 │                    │                    │                    │
     │                 │ 查询API配置         │                    │                    │
     │                 │ (数据库)           │                    │                    │
     │                 │                    │                    │                    │
     │                 │ execute_single_case│                    │                    │
     │                 │───────────────────>│                    │                    │
     │                 │                    │                    │                    │
     │                 │                    │ build(config)      │                    │
     │                 │                    │ ──────────────────>│                    │
     │                 │                    │                    │                    │
     │                 │                    │                    │ create(vendor,     │
     │                 │                    │                    │ api_type)          │
     │                 │                    │                    │───────────────────>│
     │                 │                    │                    │                    │
     │                 │                    │                    │ adapter实例        │
     │                 │                    │                    │<───────────────────│
     │                 │                    │                    │                    │
     │                 │                    │ execute(config)    │                    │
     │                 │                    │ ──────────────────>│                    │
     │                 │                    │                    │                    │
     │                 │                    │                    │ _do_execute(config)│
     │                 │                    │                    │───────────────────>│
     │                 │                    │                    │                    │
     │                 │                    │                    │                    │ 调用厂商API
     │                 │                    │                    │                    │ ─────────>
     │                 │                    │                    │                    │
     │                 │                    │                    │                    │ 响应结果
     │                 │                    │                    │                    │ <─────────
     │                 │                    │                    │                    │
     │                 │                    │                    │ APIResponse        │
     │                 │                    │                    │<───────────────────│
     │                 │                    │                    │                    │
     │                 │                    │ APIResponse        │                    │
     │                 │                    │<────────────────── │                    │
     │                 │                    │                    │                    │
     │                 │ 保存结果到数据库    │                    │                    │
     │                 │<───────────────────│                    │                    │
     │                 │                    │                    │                    │
     │ 响应结果        │                    │                    │                    │
     │<────────────────│                    │                    │                    │
     │                 │                    │                    │                    │
```

---

## 9. 实现计划

### 阶段一: 基础框架 (1周)

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 创建ExecutionConfig模型 | `api_adaper_service/models/execution_config.py` | P0 |
| 创建APIResponse模型 | `api_adaper_service/models/api_response.py` | P0 |
| 创建适配器基类 | `api_adaper_service/adapters/base/base_adapter.py` | P0 |
| 创建ASR适配器基类 | `api_adaper_service/adapters/base/asr_adapter.py` | P0 |
| 创建适配器工厂 | `api_adaper_service/services/adapter_factory.py` | P0 |
| 创建配置构建器 | `backend/utils/execution_config_builder.py` | P0 |

### 阶段二: 国内厂商适配器 (2周)

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 火山引擎ASR适配器 | `adapters/volcengine/volc_asr_adapter.py` | P0 |
| 火山引擎AST适配器 | `adapters/volcengine/volc_ast_adapter.py` | P0 |
| 阿里云百炼ASR适配器 | `adapters/aliyun/bailian_asr_adapter.py` | P0 |
| 通义千问语音翻译适配器 | `adapters/aliyun/qwen_ast_adapter.py` | P1 |

### 阶段三: 海外厂商适配器 (1周)

| 任务 | 文件 | 优先级 |
|------|------|--------|
| OpenAI Whisper适配器 | `adapters/openai/whisper_adapter.py` | P1 |
| OpenAI GPT适配器 | `adapters/openai/gpt_adapter.py` | P1 |
| Google Gemini适配器 | `adapters/google/gemini_adapter.py` | P2 |
| Azure Speech适配器 | `adapters/azure/azure_speech_adapter.py` | P2 |

### 阶段四: 集成测试 (1周)

| 任务 | 优先级 |
|------|--------|
| 主服务与适配器集成 | P0 |
| 端到端测试 | P0 |
| 性能测试 | P1 |
| 文档完善 | P1 |

---

## 10. 总结

本方案的核心设计:

1. **配置集中管理**: 所有API配置存储在数据库的API表中，通过`meta`字段存储协议特定配置
2. **适配器无状态**: 适配器不持有配置，每次调用时由主服务传递`ExecutionConfig`
3. **统一接口**: 所有适配器继承`BaseAdapter`，实现`execute(config)`方法
4. **工厂模式**: `AdapterFactory`根据`vendor`和`api_type`创建适配器实例
5. **标准化结果**: 所有适配器返回`APIResponse`，包含统一的结果结构和时延统计

这种设计使得:
- 新增厂商适配器只需实现一个类并注册
- 主服务代码不需要修改
- 配置完全由数据库管理，便于动态调整
- 支持复杂的协议（如WebSocket+Protobuf）
