# 多厂商语音/LLM API适配方案

## 文档信息

| 项目 | 内容 |
|------|------|
| 版本 | v1.0 |
| 创建日期 | 2026-05-25 |
| 作者 | AI Assistant |
| 状态 | 设计阶段 |

---

## 1. 概述

### 1.1 背景

当前API测试系统 (`api_adaper_service`) 已实现基础的WebSocket适配器和Mock适配器，需要扩展支持国内外主流语音识别、语音翻译、大语言模型等API，实现统一的适配层，支持API性能测试、对比测试和健康监控。

### 1.2 目标

1. **统一接口**: 屏蔽不同厂商API的差异，提供统一的调用接口
2. **多厂商支持**: 支持国内(火山引擎、阿里云、腾讯云、百度)和海外(OpenAI、Google、Azure、AWS)主流厂商
3. **多协议支持**: 支持HTTP REST、WebSocket、WebSocket+Protobuf、gRPC等多种协议
4. **可扩展性**: 采用适配器模式，便于新增厂商适配
5. **测试友好**: 支持Mock模式，便于测试和开发

### 1.3 范围

| API类型 | 说明 | 优先级 |
|---------|------|--------|
| ASR (语音识别) | 语音转文本 | P0 |
| AST (语音翻译) | 语音到语音翻译 | P0 |
| LLM (大语言模型) | 文本对话生成 | P1 |
| TTS (语音合成) | 文本转语音 | P1 |
| Realtime (实时语音对话) | 语音到语音实时对话 | P1 |

---

## 2. 厂商API调研

### 2.1 国内厂商

#### 2.1.1 火山引擎 (字节跳动)

| 服务名称 | 接口地址 | 协议 | 认证方式 |
|----------|----------|------|----------|
| 录音文件识别 | `https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit` | HTTP POST | X-Api-Key |
| 流式语音识别 | `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel` | WebSocket | X-Api-App-Key + X-Api-Access-Key |
| 端到端语音翻译 | `wss://openspeech.bytedance.com/api/v1/ast/v2` | WebSocket + Protobuf | app_key + access_key |
| 实时语音对话 | `wss://openspeech.bytedance.com/api/v3/realtime/dialogue` | WebSocket + Protobuf | X-Api-App-ID + X-Api-Access-Key |

**关键特性:**
- 支持方言识别: 上海话、闽南语、粤语、四川话、陕西话
- 支持情绪检测、性别检测、语种识别
- 支持热词、敏感词过滤、二遍识别
- 资源ID: `volc.seedasr.sauc.duration` (小时版), `volc.seedasr.sauc.concurrent` (并发版)

**二进制协议格式:**
```
| Byte 0 | Protocol Version (4bit) | Header Size (4bit) |
| Byte 1 | Message Type (4bit) | Flags (4bit) |
| Byte 2 | Serialization (4bit) | Compression (4bit) |
| Byte 3 | Reserved (8bit) |
| Byte 4-7 | Payload Size (4字节, 大端) |
| Payload | 实际数据 |
```

**消息类型:**
- `0b0001` (1): Full-client request (包含请求参数)
- `0b0010` (2): Audio-only request (仅音频数据)
- `0b1001` (9): Full-server response (服务端响应)
- `0b1011` (11): Audio-only response (服务端音频)
- `0b1111` (15): Error (错误信息)

#### 2.1.2 阿里云百炼

| 服务名称 | 接口地址 | 协议 | 认证方式 |
|----------|----------|------|----------|
| 实时语音识别 | `wss://dashscope.aliyuncs.com/api-ws/v1/inference` | WebSocket | API Key |
| 通义千问LLM | `https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation` | HTTP POST | API Key |
| 实时语音翻译 | WebSocket流式 | WebSocket | API Key |

**关键特性:**
- 支持模型: `fun-asr-realtime`, `paraformer-realtime-v2`, `qwen-asr-realtime`
- 支持18种语言翻译
- 8种TTS声音可选 (Cherry, Nofish, Sunny, Jada, Dylan, Peter, Eric, Kiki)
- 支持PCM/WAV/Opus/Speex/AAC/AMR格式
- SDK: `dashscope` Python SDK

**音频要求:**
- 采样率: 8000Hz 或 16000Hz
- 格式: PCM (16bit, 单声道)
- 分片大小: 建议3200字节 (100ms)

#### 2.1.3 腾讯云

| 服务名称 | 接口地址 | 协议 | 认证方式 |
|----------|----------|------|----------|
| 实时语音识别 | `wss://asr.cloud.tencent.com/asr/v2/realtime` | WebSocket | 签名认证 |
| 录音文件识别 | `https://asr.cloud.tencent.com/v1/recognition` | HTTP POST | 签名认证 |

#### 2.1.4 百度智能云

| 服务名称 | 接口地址 | 协议 | 认证方式 |
|----------|----------|------|----------|
| 实时语音识别 | `wss://vop.baidu.com/realtime_asr` | WebSocket | API Key + Secret Key |
| 短语音识别 | `https://vop.baidu.com/server_api` | HTTP POST | Access Token |

### 2.2 海外厂商

#### 2.2.1 OpenAI

| 服务名称 | 接口地址 | 协议 | 认证方式 |
|----------|----------|------|----------|
| Whisper ASR | `https://api.openai.com/v1/audio/transcriptions` | HTTP POST | Bearer Token |
| GPT-4 LLM | `https://api.openai.com/v1/chat/completions` | HTTP POST | Bearer Token |
| Realtime API | `wss://api.openai.com/v1/realtime` | WebSocket | Bearer Token |

**关键特性:**
- Whisper支持99种语言
- Realtime API支持语音到语音实时对话
- 模型: `whisper-1`, `gpt-4o`, `gpt-4-turbo`, `gpt-3.5-turbo`
- **需要代理访问 (中国大陆)**

**Whisper请求示例:**
```python
import openai

audio_file = open("audio.mp3", "rb")
transcript = openai.Audio.transcribe(
    model="whisper-1",
    file=audio_file,
    language="zh"
)
```

#### 2.2.2 Google

| 服务名称 | 接口地址 | 协议 | 认证方式 |
|----------|----------|------|----------|
| Gemini Live API | WebSocket | WebSocket | API Key |
| Speech-to-Text | `https://speech.googleapis.com/v1/speech:recognize` | HTTP POST | OAuth2 |
| Text-to-Speech | `https://texttospeech.googleapis.com/v1/text:synthesize` | HTTP POST | OAuth2 |

**关键特性:**
- Gemini 3.5 多模态实时对话 API
- 支持24种语言TTS
- **需要代理访问 (中国大陆)**

#### 2.2.3 Azure Speech Services

| 服务名称 | 接口地址 | 协议 | 认证方式 |
|----------|----------|------|----------|
| Speech-to-Text | `wss://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1` | WebSocket | Subscription Key |
| Text-to-Speech | `https://{region}.tts.speech.microsoft.com/cognitiveservices/v1` | HTTP POST | Subscription Key |

**关键特性:**
- 企业级服务，稳定性高
- 支持自定义语音模型
- **需要代理访问 (中国大陆)**

#### 2.2.4 AWS

| 服务名称 | 接口地址 | 协议 | 认证方式 |
|----------|----------|------|----------|
| Transcribe | `https://transcribe.{region}.amazonaws.com` | HTTP/WebSocket | AWS Signature v4 |
| Polly (TTS) | `https://polly.{region}.amazonaws.com` | HTTP POST | AWS Signature v4 |

---

## 3. 系统架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          主服务系统 (Intelligent-Audio-TEST)                 │
│                                  backend/                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      API 配置管理层 (主服务)                          │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │   │
│  │  │   API Model     │  │  API Endpoint   │  │   API Meta      │     │   │
│  │  │   (数据库表)     │  │   (端点配置)     │  │   (元数据配置)   │     │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘     │   │
│  │           │                    │                    │               │   │
│  │           └────────────────────┼────────────────────┘               │   │
│  │                                ▼                                    │   │
│  │                    ┌─────────────────────┐                          │   │
│  │                    │   API Controller    │                          │   │
│  │                    │   api_controller.py │                          │   │
│  │                    └─────────────────────┘                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    │ 传递完整API配置                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      API Driver Layer                                │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │   │
│  │  │   api_driver.py │  │   api_client.py │  │  api_executor.py│     │   │
│  │  │   (驱动封装)     │  │   (协议调用)     │  │   (执行引擎)     │     │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    │ 调用适配器                              │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Adapter Factory                                 │   │
│  │                    adapter_factory.py                                │   │
│  │                                                                      │   │
│  │    输入: api_config (从主服务传递)                                    │   │
│  │    输出: 具体厂商适配器实例                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│         ┌──────────────────────────┼──────────────────────────┐            │
│         ▼                          ▼                          ▼            │
│  ┌─────────────┐           ┌─────────────┐           ┌─────────────┐      │
│  │ ASRAdapter  │           │ ASTAdapter  │           │ LLMAdapter  │      │
│  │   (基类)    │           │   (基类)    │           │   (基类)    │      │
│  └─────────────┘           └─────────────┘           └─────────────┘      │
│         │                          │                          │            │
│         ▼                          ▼                          ▼            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Vendor Adapters (适配器层)                      │   │
│  │                                                                      │   │
│  │  ★ 适配器不持有配置，所有配置由主服务传递                              │   │
│  │  ★ 适配器只负责协议转换和API调用                                      │   │
│  │                                                                      │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  国内厂商:                                                            │   │
│  │  ├─ volc_asr_adapter.py      (火山引擎流式ASR)                       │   │
│  │  ├─ volc_ast_adapter.py      (火山引擎端到端语音翻译)                │   │
│  │  ├─ bailian_asr_adapter.py   (阿里云百炼ASR)                        │   │
│  │  └─ qwen_ast_adapter.py      (通义千问语音翻译)                      │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  海外厂商:                                                            │   │
│  │  ├─ whisper_adapter.py       (OpenAI Whisper)                       │   │
│  │  ├─ gpt_adapter.py           (OpenAI GPT)                           │   │
│  │  ├─ gemini_adapter.py        (Google Gemini)                        │   │
│  │  └─ azure_speech_adapter.py  (Azure Speech)                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 配置管理架构

**核心原则: 所有API配置由主服务统一管理，适配器不持有配置状态**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           主服务配置管理                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      数据库层 (PostgreSQL)                           │   │
│  │                                                                      │   │
│  │  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐       │   │
│  │  │   api 表      │    │ api_endpoints │    │  api_meta     │       │   │
│  │  │               │    │    (JSON)     │    │   (JSON)      │       │   │
│  │  │ - id          │    │               │    │               │       │   │
│  │  │ - name        │    │ [             │    │ {             │       │   │
│  │  │ - vendor      │────│   {endpoint}, │────│   protocol,   │       │   │
│  │  │ - api_url     │    │   {endpoint}  │    │   auth_type,  │       │   │
│  │  │ - status      │    │ ]             │    │   headers,    │       │   │
│  │  │ - meta (JSON) │    └───────────────┘    │   ...         │       │   │
│  │  │ - ...         │                         │ }             │       │   │
│  │  └───────────────┘                         └───────────────┘       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      API Model (ORM模型)                             │   │
│  │                                                                      │   │
│  │  class API(db.Model):                                               │   │
│  │      id = db.Column(db.Integer, primary_key=True)                   │   │
│  │      name = db.Column(db.String(100))                               │   │
│  │      vendor = db.Column(db.String(50))      # 厂商标识              │   │
│  │      api_url = db.Column(db.String(500))    # 主URL                 │   │
│  │      meta = db.Column(db.JSON)              # 元数据配置            │   │
│  │      api_endpoints = db.Column(db.JSON)     # 端点列表              │   │
│  │      algorithm_type = db.Column(db.String)  # 算法类型              │   │
│  │      ...                                                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      API Controller                                  │   │
│  │                                                                      │   │
│  │  def execute_api_test(api_id, test_params):                         │   │
│  │      # 1. 从数据库加载API配置                                        │   │
│  │      api_config = API.query.get(api_id)                             │   │
│  │                                                                      │   │
│  │      # 2. 构建完整配置对象                                            │   │
│  │      execution_config = {                                            │   │
│  │          'vendor': api_config.vendor,                                │   │
│  │          'api_type': api_config.algorithm_type,                      │   │
│  │          'endpoint': select_endpoint(api_config),                    │   │
│  │          'meta': api_config.meta,                                    │   │
│  │          'credentials': get_credentials(api_config.vendor),          │   │
│  │          'test_params': test_params                                  │   │
│  │      }                                                               │   │
│  │                                                                      │   │
│  │      # 3. 调用适配器执行                                              │   │
│  │      adapter = AdapterFactory.create(execution_config)               │   │
│  │      result = adapter.execute()                                      │   │
│  │                                                                      │   │
│  │      return result                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 核心组件职责

| 组件 | 职责 | 位置 | 配置来源 |
|------|------|------|----------|
| **API Model** | 数据库模型，存储API配置 | `backend/models/models.py` | 数据库 |
| **API Controller** | API配置CRUD、测试执行入口 | `backend/controllers/api_controller.py` | 从数据库加载 |
| **API Driver** | 封装适配器调用，参数渲染 | `backend/utils/api_driver.py` | 从Controller接收 |
| **API Client** | 底层协议调用(HTTP/WS) | `backend/utils/api_client.py` | 从Driver接收 |
| **Adapter Factory** | 根据配置创建适配器实例 | `api_adaper_service/services/adapter_factory.py` | 从主服务接收 |
| **Vendor Adapter** | 厂商特定协议处理 | `api_adaper_service/adapters/` | **不持有配置，每次调用传入** |

### 3.4 数据流设计

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              完整调用流程                                     │
└──────────────────────────────────────────────────────────────────────────────┘

用户请求
    │
    ▼
┌─────────────┐     ┌─────────────────────────────────────────────────────┐
│ API测试页面  │────▶│  POST /api/test/execute                             │
└─────────────┘     │  Body: { api_id, test_case_id, params }             │
                    └─────────────────────────────────────────────────────┘
                                        │
                                        ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  API Controller                                      │
                    │  1. 查询API配置 (api_id → API Model)                 │
                    │  2. 查询测试用例 (test_case_id → TestCase Model)     │
                    │  3. 合并配置: api_config + test_case + params        │
                    └─────────────────────────────────────────────────────┘
                                        │
                                        │ execution_config = {
                                        │   vendor: "volcengine",
                                        │   api_type: "asr",
                                        │   endpoint: "wss://...",
                                        │   meta: { ... },
                                        │   credentials: { app_key, access_key },
                                        │   audio_path: "...",
                                        │   ...
                                        │ }
                                        ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  API Driver                                          │
                    │  1. 根据vendor和api_type选择适配器                    │
                    │  2. 渲染请求参数 (模板替换)                            │
                    │  3. 调用适配器                                        │
                    └─────────────────────────────────────────────────────┘
                                        │
                                        ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  Adapter Factory                                     │
                    │  adapter = factory.create(execution_config)          │
                    └─────────────────────────────────────────────────────┘
                                        │
                                        ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  Vendor Adapter (如 VolcASRAdapter)                  │
                    │  - 不存储配置                                        │
                    │  - 使用传入的config执行API调用                        │
                    │  - 返回标准化结果                                     │
                    └─────────────────────────────────────────────────────┘
                                        │
                                        ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  厂商API (如 火山引擎ASR)                            │
                    └─────────────────────────────────────────────────────┘
                                        │
                                        ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  结果返回                                            │
                    │  { success, result, latency, error, ... }            │
                    └─────────────────────────────────────────────────────┘
```

### 3.5 配置传递机制

```python
# 主服务调用适配器的配置传递方式

class APIController:
    def execute_test(self, api_id: int, test_params: dict):
        # 1. 从数据库加载API配置
        api_model = API.query.get(api_id)
        
        # 2. 获取凭据 (从环境变量或密钥管理服务)
        credentials = self._get_credentials(api_model.vendor)
        
        # 3. 选择端点 (负载均衡/优先级)
        endpoint = self._select_endpoint(api_model.api_endpoints)
        
        # 4. 构建执行配置 (完整配置对象)
        execution_config = {
            # 基础信息
            'api_id': api_model.id,
            'vendor': api_model.vendor,
            'api_type': api_model.algorithm_type,
            
            # 端点配置
            'endpoint': endpoint['endpoint'],
            'max_timeout': endpoint.get('max_timeout', 30),
            'max_process': endpoint.get('max_process', 5),
            
            # 元数据 (协议特定配置)
            'meta': api_model.meta or {},
            
            # 认证凭据
            'credentials': credentials,
            
            # 测试参数
            'test_params': test_params,
            
            # 音频路径 (如适用)
            'audio_path': test_params.get('audio_path'),
        }
        
        # 5. 调用API Driver执行
        driver = APIDriver(execution_config)
        result = driver.execute()
        
        return result


class APIDriver:
    def __init__(self, config: dict):
        self.config = config  # 不存储，仅本次执行使用
        
    def execute(self):
        # 根据vendor和api_type获取适配器
        adapter = AdapterFactory.create(
            vendor=self.config['vendor'],
            api_type=self.config['api_type'],
            config=self.config  # 完整配置传递给适配器
        )
        
        # 执行并返回结果
        return adapter.execute()
```

---

## 4. 接口设计

### 4.1 枚举定义

```python
from enum import Enum

class APIType(Enum):
    """API类型枚举"""
    ASR = "asr"                    # 语音识别
    TTS = "tts"                    # 语音合成
    AST = "ast"                    # 语音翻译
    LLM = "llm"                    # 大语言模型
    REALTIME = "realtime"          # 实时语音对话

class ProtocolType(Enum):
    """协议类型枚举"""
    HTTP = "http"                  # HTTP REST
    WEBSOCKET = "websocket"        # WebSocket (JSON)
    WEBSOCKET_PROTOBUF = "websocket_protobuf"  # WebSocket + Protobuf
    GRPC = "grpc"                  # gRPC

class AuthType(Enum):
    """认证类型枚举"""
    API_KEY = "api_key"            # API Key (Header或Query)
    BEARER = "bearer"              # Bearer Token
    HEADER = "header"              # 自定义Header
    SIGNATURE = "signature"        # 签名认证
    OAUTH2 = "oauth2"              # OAuth2

class VendorRegion(Enum):
    """厂商区域枚举"""
    CN = "cn"                      # 中国大陆
    GLOBAL = "global"              # 全球 (需代理)
```

### 4.2 数据模型

```python
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

@dataclass
class AudioConfig:
    """音频配置"""
    format: str = "wav"            # pcm, wav, mp3, ogg, opus
    sample_rate: int = 16000       # 8000, 16000
    bits: int = 16                 # 16, 32
    channel: int = 1               # 1=mono, 2=stereo
    codec: str = "raw"             # raw, opus

@dataclass
class VendorConfig:
    """厂商配置"""
    vendor: str                    # 厂商标识
    name: str                      # 厂商名称
    region: VendorRegion           # 区域
    api_type: APIType              # API类型
    protocol: ProtocolType         # 协议类型
    endpoint: str                  # 接口地址
    auth_type: AuthType            # 认证类型
    auth_fields: List[str] = field(default_factory=list)  # 认证字段
    requires_proxy: bool = False   # 是否需要代理
    models: List[str] = field(default_factory=list)       # 支持的模型
    features: List[str] = field(default_factory=list)     # 支持的特性
    audio_formats: List[str] = field(default_factory=list) # 支持的音频格式
    sample_rates: List[int] = field(default_factory=list)  # 支持的采样率

@dataclass
class ASRResult:
    """语音识别结果"""
    text: str                              # 识别文本
    is_final: bool = False                 # 是否最终结果
    confidence: float = 0.0                # 置信度
    start_time: int = 0                    # 开始时间
    end_time: int = 0                      # 结束时间
    language: str = ""                     # 识别语言
    speaker_id: str = ""                   # 说话人ID
    emotion: str = ""                      # 情绪
    gender: str = ""                       # 性别
    words: List[dict] = field(default_factory=list)  # 词级时间戳
    raw_response: dict = None              # 原始响应

@dataclass
class TranslationResult:
    """语音翻译结果"""
    source_text: str                       # 源语言文本 (ASR结果)
    target_text: str                       # 目标语言文本 (翻译结果)
    source_lang: str                       # 源语言
    target_lang: str                       # 目标语言
    audio_data: bytes = None               # TTS音频数据
    audio_format: str = "wav"              # 音频格式
    raw_response: dict = None              # 原始响应

@dataclass
class LLMResult:
    """大语言模型结果"""
    content: str                           # 回复内容
    role: str = "assistant"                # 角色
    model: str = ""                        # 使用的模型
    finish_reason: str = ""                # 结束原因
    usage: dict = field(default_factory=dict)  # Token使用量
    raw_response: dict = None              # 原始响应

@dataclass
class LatencyStats:
    """时延统计"""
    request_start_time: datetime = None    # 请求开始时间
    request_end_time: datetime = None      # 请求结束时间
    first_byte_latency_ms: float = 0       # 首字节时延
    last_byte_latency_ms: float = 0        # 尾字节时延
    total_latency_ms: float = 0            # 总时延
    asr_first_char_ms: float = None        # ASR首字时延
    asr_last_char_ms: float = None         # ASR尾字时延
    trans_first_char_ms: float = None      # 翻译首字时延
    trans_last_char_ms: float = None       # 翻译尾字时延
    tts_first_byte_ms: float = None        # TTS首字节时延
    tts_last_byte_ms: float = None         # TTS尾字节时延

@dataclass
class APIResponse:
    """统一API响应"""
    success: bool                          # 是否成功
    vendor: str                            # 厂商
    api_type: APIType                      # API类型
    result: Any = None                     # 结果 (ASRResult/TranslationResult/LLMResult)
    latency: LatencyStats = None           # 时延统计
    error_code: str = ""                   # 错误码
    error_message: str = ""                # 错误信息
    request_id: str = ""                   # 请求ID
    raw_response: dict = None              # 原始响应
```

### 4.3 执行配置模型

**核心原则: 适配器每次执行时接收完整配置，不持有任何配置状态**

```python
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class ExecutionConfig:
    """
    执行配置 - 由主服务构建并传递给适配器
    
    这是适配器接收的唯一配置对象，包含执行API调用所需的所有信息。
    适配器不应存储此配置，仅在execute()调用期间使用。
    """
    # ========== 基础信息 ==========
    api_id: int                           # API ID (数据库主键)
    vendor: str                           # 厂商标识 (volcengine, aliyun, openai等)
    api_type: str                         # API类型 (asr, ast, llm, tts, realtime)
    
    # ========== 端点配置 ==========
    endpoint: str                         # API端点URL
    max_timeout: int = 30                 # 最大超时时间(秒)
    max_process: int = 5                  # 最大并发数
    max_audio_duration: int = 60          # 最大音频时长(秒)
    
    # ========== 元数据配置 (从API.meta获取) ==========
    meta: Dict[str, Any] = field(default_factory=dict)
    # meta字段示例:
    # {
    #     'protocol': 'websocket',           # 协议类型
    #     'auth_type': 'header',             # 认证类型
    #     'method': 'POST',                  # HTTP方法
    #     'headers': { ... },                # 请求头模板
    #     'body_template': { ... },          # 请求体模板
    #     'asr_mapping': 'result.text',      # ASR结果提取路径
    #     'trans_mapping': 'result.translation',  # 翻译结果提取路径
    #     'session_end_mapping': 'is_end',   # 会话结束标志路径
    #     'chunk_size': 3200,                # 音频分片大小
    #     'chunk_interval': 0.1,             # 分片间隔(秒)
    #     ...
    # }
    
    # ========== 认证凭据 (从密钥管理服务获取) ==========
    credentials: Dict[str, str] = field(default_factory=dict)
    # credentials字段示例:
    # 火山引擎: {'app_key': 'xxx', 'access_key': 'xxx'}
    # 阿里云: {'api_key': 'xxx'}
    # OpenAI: {'api_key': 'xxx'}
    # Azure: {'subscription_key': 'xxx', 'region': 'eastasia'}
    
    # ========== 测试参数 (从测试用例获取) ==========
    test_params: Dict[str, Any] = field(default_factory=dict)
    # test_params字段示例:
    # {
    #     'audio_path': '/path/to/audio.wav',  # 音频文件路径
    #     'text': '要翻译的文本',               # 文本输入(LLM/TTS)
    #     'source_lang': 'zh',                  # 源语言
    #     'target_lang': 'en',                  # 目标语言
    #     'model': 'whisper-1',                 # 模型选择
    #     'language': 'zh-CN',                  # ASR语言
    #     'enable_punc': True,                  # 启用标点
    #     'enable_itn': True,                   # 启用ITN
    #     ...
    # }
    
    # ========== 代理配置 (海外API) ==========
    proxy: Optional[str] = None            # 代理地址 (http://host:port)
    
    # ========== 回调配置 ==========
    callbacks: Dict[str, Any] = field(default_factory=dict)
    # callbacks字段示例:
    # {
    #     'on_message': callback_func,  # 消息回调
    #     'on_error': callback_func,    # 错误回调
    #     'on_complete': callback_func,  # 完成回调
    # }
```

### 4.4 适配器基类

```python
from abc import ABC, abstractmethod
from typing import Optional, Callable, Dict, Any

class BaseAdapter(ABC):
    """
    适配器基类
    
    设计原则:
    1. 适配器不持有任何配置状态
    2. 所有配置通过execute()方法传入
    3. 适配器只负责协议转换和API调用
    4. 每次执行都是独立的，无状态依赖
    """
    
    # 类属性 - 厂商标识 (子类必须覆盖)
    vendor: str = ""
    api_type: str = ""
    
    def __init__(self):
        """
        初始化适配器 - 不接收任何配置参数
        
        适配器实例可以被复用，但每次执行时必须传入完整配置。
        """
        self._current_config: Optional[ExecutionConfig] = None
        self._callbacks: Dict[str, Callable] = {}
        
    def execute(self, config: ExecutionConfig) -> APIResponse:
        """
        执行API调用 - 主入口方法
        
        Args:
            config: 完整的执行配置 (由主服务构建并传入)
            
        Returns:
            APIResponse: 统一格式的响应结果
        """
        self._current_config = config
        self._callbacks = config.callbacks or {}
        
        try:
            # 1. 验证配置
            self._validate_config(config)
            
            # 2. 建立连接
            self._connect(config)
            
            # 3. 执行具体逻辑 (子类实现)
            result = self._do_execute(config)
            
            # 4. 返回结果
            return result
            
        except Exception as e:
            return APIResponse(
                success=False,
                vendor=config.vendor,
                api_type=config.api_type,
                error_code='EXECUTION_ERROR',
                error_message=str(e)
            )
        finally:
            # 5. 清理资源
            self._cleanup()
            self._current_config = None
    
    @abstractmethod
    def _do_execute(self, config: ExecutionConfig) -> APIResponse:
        """
        执行具体API调用逻辑 (子类必须实现)
        
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
        if not config.credentials:
            raise ValueError("credentials is required")
            
    def _connect(self, config: ExecutionConfig):
        """建立连接 (子类可覆盖)"""
        pass
    
    def _cleanup(self):
        """清理资源 (子类可覆盖)"""
        pass
    
    def _trigger_callback(self, callback_type: str, *args, **kwargs):
        """触发回调"""
        if callback_type in self._callbacks:
            self._callbacks[callback_type](*args, **kwargs)
    
    @classmethod
    @abstractmethod
    def get_supported_features(cls) -> List[str]:
        """
        获取支持的特性列表
        
        Returns:
            特性列表，如 ['streaming', 'punctuation', 'speaker_diarization']
        """
        pass
    
    @classmethod
    @abstractmethod
    def get_required_credentials(cls) -> List[str]:
        """
        获取必需的凭据字段
        
        Returns:
            凭据字段列表，如 ['app_key', 'access_key']
        """
        pass
            
    @abstractmethod
    def health_check(self) -> bool:
        """
        健康检查
        
        Returns:
            服务是否健康
        """
        pass
```

### 4.5 ASR适配器接口

```python
class ASRAdapter(BaseAdapter):
    """
    语音识别适配器基类
    
    所有配置通过execute()方法传入，适配器不持有配置状态。
    """
    
    api_type = "asr"
    
    def _do_execute(self, config: ExecutionConfig) -> APIResponse:
        """
        执行ASR识别
        
        根据config中的参数执行语音识别，支持:
        - 流式识别 (WebSocket)
        - 文件识别 (HTTP)
        """
        audio_path = config.test_params.get('audio_path')
        if not audio_path:
            return APIResponse(
                success=False,
                vendor=config.vendor,
                api_type=self.api_type,
                error_code='MISSING_AUDIO',
                error_message='audio_path is required in test_params'
            )
        
        # 判断协议类型
        protocol = config.meta.get('protocol', 'http')
        
        if protocol in ['websocket', 'websocket_protobuf']:
            return self._execute_streaming(config)
        else:
            return self._execute_file(config)
    
    @abstractmethod
    def _execute_streaming(self, config: ExecutionConfig) -> APIResponse:
        """执行流式识别 (子类实现)"""
        pass
    
    @abstractmethod
    def _execute_file(self, config: ExecutionConfig) -> APIResponse:
        """执行文件识别 (子类实现)"""
        pass
    
    @classmethod
    def get_supported_features(cls) -> List[str]:
        """ASR支持的特性"""
        return ['streaming', 'punctuation', 'itn', 'speaker_diarization', 
                'emotion_detection', 'language_identification']
```

### 4.6 AST适配器接口

```python
class ASTAdapter(BaseAdapter):
    """
    语音翻译适配器基类
    
    所有配置通过execute()方法传入，适配器不持有配置状态。
    """
    
    api_type = "ast"
    
    def _do_execute(self, config: ExecutionConfig) -> APIResponse:
        """
        执行语音翻译
        
        从config中获取必要参数:
        - audio_path: 音频文件路径
        - source_lang: 源语言
        - target_lang: 目标语言
        """
        audio_path = config.test_params.get('audio_path')
        source_lang = config.test_params.get('source_lang', 'zh')
        target_lang = config.test_params.get('target_lang', 'en')
        
        if not audio_path:
            return APIResponse(
                success=False,
                vendor=config.vendor,
                api_type=self.api_type,
                error_code='MISSING_AUDIO',
                error_message='audio_path is required in test_params'
            )
        
        return self._execute_translation(config, audio_path, source_lang, target_lang)
    
    @abstractmethod
    def _execute_translation(self, config: ExecutionConfig, 
                             audio_path: str, 
                             source_lang: str, 
                             target_lang: str) -> APIResponse:
        """执行翻译 (子类实现)"""
        pass
    
    @classmethod
    def get_supported_features(cls) -> List[str]:
        """AST支持的特性"""
        return ['asr', 'translation', 'tts', 'streaming']
```

### 4.7 LLM适配器接口

```python
class LLMAdapter(BaseAdapter):
    """
    大语言模型适配器基类
    
    所有配置通过execute()方法传入，适配器不持有配置状态。
    """
    
    api_type = "llm"
    
    def _do_execute(self, config: ExecutionConfig) -> APIResponse:
        """
        执行LLM对话
        
        从config中获取必要参数:
        - messages: 对话消息列表
        - model: 模型选择
        """
        messages = config.test_params.get('messages', [])
        model = config.test_params.get('model')
        
        if not messages:
            return APIResponse(
                success=False,
                vendor=config.vendor,
                api_type=self.api_type,
                error_code='MISSING_MESSAGES',
                error_message='messages is required in test_params'
            )
        
        return self._execute_chat(config, messages, model)
    
    @abstractmethod
    def _execute_chat(self, config: ExecutionConfig, 
                      messages: List[dict], 
                      model: str) -> APIResponse:
        """执行对话 (子类实现)"""
        pass
    
    @classmethod
    def get_supported_features(cls) -> List[str]:
        """LLM支持的特性"""
        return ['streaming', 'function_calling', 'vision']
```

### 4.8 适配器工厂

```python
from typing import Dict, Type, Optional

class AdapterFactory:
    """
    适配器工厂
    
    职责:
    1. 管理适配器注册表
    2. 根据vendor和api_type创建适配器实例
    3. 不持有任何配置，配置由调用方传入
    """
    
    # 适配器注册表: {"{vendor}_{api_type}": AdapterClass}
    _registry: Dict[str, Type[BaseAdapter]] = {}
    
    @classmethod
    def register(cls, vendor: str, api_type: str, adapter_class: Type[BaseAdapter]):
        """
        注册适配器
        
        Args:
            vendor: 厂商标识 (volcengine, aliyun, openai等)
            api_type: API类型 (asr, ast, llm, tts, realtime)
            adapter_class: 适配器类
        """
        key = f"{vendor}_{api_type}"
        cls._registry[key] = adapter_class
        
    @classmethod
    def create(cls, vendor: str, api_type: str) -> BaseAdapter:
        """
        创建适配器实例
        
        注意: 此方法只创建适配器实例，不传入任何配置。
        配置通过adapter.execute(config)方法传入。
        
        Args:
            vendor: 厂商标识
            api_type: API类型
            
        Returns:
            适配器实例 (未初始化配置)
            
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
            config: 执行配置 (包含vendor, api_type等)
            
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


# ==================== 自动注册 ====================
def auto_register_adapters():
    """
    自动注册所有适配器
    
    在应用启动时调用此函数，扫描adapters目录并注册所有适配器。
    """
    # 国内厂商
    from adapters.volcengine.volc_asr_adapter import VolcASRAdapter
    from adapters.volcengine.volc_ast_adapter import VolcASTAdapter
    from adapters.aliyun.bailian_asr_adapter import BailianASRAdapter
    from adapters.aliyun.qwen_ast_adapter import QwenASTAdapter
    
    # 海外厂商
    from adapters.openai.whisper_adapter import WhisperAdapter
    from adapters.openai.gpt_adapter import GPTAdapter
    from adapters.google.gemini_adapter import GeminiAdapter
    from adapters.azure.azure_speech_adapter import AzureSpeechAdapter
    
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
```

### 4.9 主服务调用示例

```python
# backend/controllers/api_controller.py

from backend.models.models import API
from backend.utils.api_driver import APIDriver
from api_adaper_service.services.adapter_factory import AdapterFactory, ExecutionConfig

class APIController:
    
    def execute_test(self, api_id: int, test_case_id: int = None, params: dict = None):
        """
        执行API测试
        
        流程:
        1. 从数据库加载API配置
        2. 从密钥管理服务获取凭据
        3. 构建ExecutionConfig
        4. 调用AdapterFactory执行
        """
        # 1. 加载API配置
        api_model = API.query.get(api_id)
        if not api_model:
            return {'success': False, 'error': 'API not found'}
        
        # 2. 获取凭据 (从环境变量或密钥管理服务)
        credentials = self._get_credentials(api_model.vendor)
        
        # 3. 选择端点 (负载均衡/优先级)
        endpoint_config = self._select_endpoint(api_model)
        
        # 4. 合并测试参数
        test_params = params or {}
        if test_case_id:
            test_case = TestCase.query.get(test_case_id)
            test_params.update(test_case.params or {})
        
        # 5. 构建执行配置
        execution_config = ExecutionConfig(
            api_id=api_model.id,
            vendor=api_model.vendor,
            api_type=api_model.algorithm_type,
            endpoint=endpoint_config['endpoint'],
            max_timeout=endpoint_config.get('max_timeout', 30),
            max_process=endpoint_config.get('max_process', 5),
            max_audio_duration=endpoint_config.get('max_audio_duration', 60),
            meta=api_model.meta or {},
            credentials=credentials,
            test_params=test_params,
            proxy=self._get_proxy(api_model.vendor),
        )
        
        # 6. 执行测试
        result = AdapterFactory.execute(execution_config)
        
        # 7. 保存结果并返回
        self._save_result(api_id, test_case_id, result)
        
        return {
            'success': result.success,
            'result': result.result,
            'latency': result.latency,
            'error': result.error_message if not result.success else None
        }
    
    def _get_credentials(self, vendor: str) -> dict:
        """获取厂商凭据"""
        import os
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
            'azure': {
                'subscription_key': os.getenv('AZURE_SUBSCRIPTION_KEY'),
                'region': os.getenv('AZURE_REGION', 'eastasia'),
            },
        }
        return credentials_map.get(vendor, {})
    
    def _get_proxy(self, vendor: str) -> str:
        """获取代理配置 (海外厂商需要)"""
        overseas_vendors = ['openai', 'google', 'azure', 'aws']
        if vendor in overseas_vendors:
            return os.getenv('HTTP_PROXY') or os.getenv('HTTPS_PROXY')
        return None
```
        pass
    
    @abstractmethod
    def start_translation(self, source_lang: str, target_lang: str, **kwargs) -> bool:
        """
        开始流式翻译会话
        
        Args:
            source_lang: 源语言
            target_lang: 目标语言
            
        Returns:
            是否成功开始
        """
        pass
    
    @abstractmethod
    def send_audio_chunk(self, chunk: bytes) -> bool:
        """
        发送音频分片
        
        Args:
            chunk: 音频分片数据
            
        Returns:
            是否发送成功
        """
        pass
    
    @abstractmethod
    def receive_result(self) -> Optional[TranslationResult]:
        """
        接收翻译结果 (非阻塞)
        
        Returns:
            翻译结果，无结果返回None
        """
        pass
    
    @abstractmethod
    def stop_translation(self) -> TranslationResult:
        """
        停止翻译并获取最终结果
        
        Returns:
            最终翻译结果
        """
        pass
```

### 4.6 LLM适配器接口

```python
class LLMAdapter(BaseAdapter):
    """大语言模型适配器基类"""
    
    api_type = APIType.LLM
    
    @abstractmethod
    def chat(self, messages: List[dict], **kwargs) -> LLMResult:
        """
        对话接口
        
        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            **kwargs: 其他参数 (model, temperature, max_tokens等)
            
        Returns:
            模型回复
        """
        pass
    
    @abstractmethod
    def stream_chat(self, messages: List[dict], callback: Callable[[str], None], 
                    **kwargs):
        """
        流式对话
        
        Args:
            messages: 消息列表
            callback: 流式回调函数
            **kwargs: 其他参数
        """
        pass
    
    @abstractmethod
    def get_models(self) -> List[str]:
        """
        获取支持的模型列表
        
        Returns:
            模型列表
        """
        pass
```

### 4.7 适配器工厂

```python
from typing import Dict, Type

class AdapterFactory:
    """适配器工厂"""
    
    _registry: Dict[str, Type[BaseAdapter]] = {}
    
    @classmethod
    def register(cls, vendor: str, api_type: APIType, adapter_class: Type[BaseAdapter]):
        """
        注册适配器
        
        Args:
            vendor: 厂商标识
            api_type: API类型
            adapter_class: 适配器类
        """
        key = f"{vendor}_{api_type.value}"
        cls._registry[key] = adapter_class
        
    @classmethod
    def create(cls, vendor: str, api_type: APIType, 
               config: VendorConfig, credentials: dict) -> BaseAdapter:
        """
        创建适配器实例
        
        Args:
            vendor: 厂商标识
            api_type: API类型
            config: 厂商配置
            credentials: 认证凭据
            
        Returns:
            适配器实例
            
        Raises:
            ValueError: 不支持的厂商或API类型
        """
        key = f"{vendor}_{api_type.value}"
        if key not in cls._registry:
            raise ValueError(f"Unsupported adapter: {key}")
            
        return cls._registry[key](config, credentials)
    
    @classmethod
    def list_adapters(cls) -> List[str]:
        """
        列出所有已注册的适配器
        
        Returns:
            适配器列表
        """
        return list(cls._registry.keys())


# 自动注册适配器
def auto_register():
    """自动注册所有适配器"""
    from adapters.volcengine.volc_asr_adapter import VolcASRAdapter
    from adapters.volcengine.volc_ast_adapter import VolcASTAdapter
    from adapters.aliyun.bailian_asr_adapter import BailianASRAdapter
    from adapters.aliyun.qwen_llm_adapter import QwenLLMAdapter
    from adapters.openai.whisper_adapter import WhisperAdapter
    from adapters.openai.gpt_adapter import GPTAdapter
    from adapters.google.gemini_adapter import GeminiAdapter
    from adapters.azure.azure_speech_adapter import AzureSpeechAdapter
    
    # 火山引擎
    AdapterFactory.register("volcengine", APIType.ASR, VolcASRAdapter)
    AdapterFactory.register("volcengine", APIType.AST, VolcASTAdapter)
    
    # 阿里云
    AdapterFactory.register("aliyun", APIType.ASR, BailianASRAdapter)
    AdapterFactory.register("aliyun", APIType.LLM, QwenLLMAdapter)
    
    # OpenAI
    AdapterFactory.register("openai", APIType.ASR, WhisperAdapter)
    AdapterFactory.register("openai", APIType.LLM, GPTAdapter)
    
    # Google
    AdapterFactory.register("google", APIType.REALTIME, GeminiAdapter)
    
    # Azure
    AdapterFactory.register("azure", APIType.ASR, AzureSpeechAdapter)
```

---

## 5. 厂商适配器实现规范

### 5.1 火山引擎流式ASR适配器

**文件**: `adapters/volcengine/volc_asr_adapter.py`

```python
class VolcASRAdapter(ASRAdapter):
    """火山引擎流式语音识别适配器"""
    
    vendor = "volcengine"
    api_type = APIType.ASR
    protocol = ProtocolType.WEBSOCKET
    
    WS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
    RESOURCE_ID_DURATION = "volc.seedasr.sauc.duration"
    RESOURCE_ID_CONCURRENT = "volc.seedasr.sauc.concurrent"
    
    def __init__(self, config: VendorConfig, credentials: dict):
        super().__init__(config, credentials)
        self.app_key = credentials.get('app_key')
        self.access_key = credentials.get('access_key')
        self.resource_id = credentials.get('resource_id', self.RESOURCE_ID_DURATION)
        self.ws = None
        self.sequence = 0
        self.results = []
        
    def _build_protocol_header(self, message_type: int, flags: int,
                                serialization: int = 1, compression: int = 0) -> bytes:
        """构建二进制协议头"""
        byte0 = (0b0001 << 4) | 0b0001
        byte1 = (message_type << 4) | flags
        byte2 = (serialization << 4) | compression
        byte3 = 0x00
        return bytes([byte0, byte1, byte2, byte3])
        
    def connect(self, **kwargs) -> bool:
        headers = {
            "X-Api-App-Key": self.app_key,
            "X-Api-Access-Key": self.access_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Connect-Id": str(uuid.uuid4())
        }
        # WebSocket连接实现...
        
    def start_recognition(self, audio_config: AudioConfig, **kwargs) -> bool:
        # 发送full client request
        request = {
            "user": {"uid": kwargs.get('uid', 'test_user')},
            "audio": {
                "format": audio_config.format,
                "rate": audio_config.sample_rate,
                "bits": audio_config.bits,
                "channel": audio_config.channel,
                "language": kwargs.get('language', 'zh-CN')
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": kwargs.get('enable_itn', True),
                "enable_punc": kwargs.get('enable_punc', True),
                "enable_ddc": kwargs.get('enable_ddc', False),
                "result_type": kwargs.get('result_type', 'full')
            }
        }
        # 发送请求...
        
    def send_audio(self, audio_data: bytes) -> bool:
        # 发送audio only request
        header = self._build_protocol_header(
            message_type=0b0010,  # Audio-only request
            flags=0b0001 if self.sequence >= 0 else 0b0011
        )
        payload_size = len(audio_data).to_bytes(4, 'big')
        # 发送...
        self.sequence += 1
```

### 5.2 火山引擎AST适配器

**文件**: `adapters/volcengine/volc_ast_adapter.py`

```python
class VolcASTAdapter(ASTAdapter):
    """火山引擎端到端语音翻译适配器"""
    
    vendor = "volcengine"
    api_type = APIType.AST
    protocol = ProtocolType.WEBSOCKET_PROTOBUF
    
    def __init__(self, config: VendorConfig, credentials: dict):
        super().__init__(config, credentials)
        self.app_key = credentials.get('app_key')
        self.access_key = credentials.get('access_key')
        self.resource_id = credentials.get('resource_id', 'volc.ast')
        
    def translate(self, audio_path: str, source_lang: str, target_lang: str,
                  **kwargs) -> TranslationResult:
        """
        执行语音翻译 (基于Protobuf协议)
        
        参考: 第三方/ast_python_client/ast_python/ast_demo_zh2en.py
        """
        # 1. 读取音频文件
        audio_chunks = self._read_audio_chunks(audio_path, chunk_size=3200)
        
        # 2. 建立WebSocket连接
        # 3. 发送StartSession事件
        # 4. 发送音频分片
        # 5. 接收ASR和翻译结果
        # 6. 发送FinishSession事件
        # 7. 返回结果
        pass
```

### 5.3 阿里云百炼ASR适配器

**文件**: `adapters/aliyun/bailian_asr_adapter.py`

```python
class BailianASRAdapter(ASRAdapter):
    """阿里云百炼实时语音识别适配器"""
    
    vendor = "aliyun"
    api_type = APIType.ASR
    protocol = ProtocolType.WEBSOCKET
    
    WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
    
    def __init__(self, config: VendorConfig, credentials: dict):
        super().__init__(config, credentials)
        self.api_key = credentials.get('api_key')
        self.model = config.models[0] if config.models else 'fun-asr-realtime'
        
    def connect(self, **kwargs) -> bool:
        # 使用DashScope SDK或原生WebSocket
        pass
        
    def start_recognition(self, audio_config: AudioConfig, **kwargs) -> bool:
        # 参考: 第三方/qwen_api/main.py
        pass
```

### 5.4 OpenAI Whisper适配器

**文件**: `adapters/openai/whisper_adapter.py`

```python
class WhisperAdapter(ASRAdapter):
    """OpenAI Whisper语音识别适配器"""
    
    vendor = "openai"
    api_type = APIType.ASR
    protocol = ProtocolType.HTTP
    
    API_URL = "https://api.openai.com/v1/audio/transcriptions"
    
    def __init__(self, config: VendorConfig, credentials: dict):
        super().__init__(config, credentials)
        self.api_key = credentials.get('api_key')
        self.model = credentials.get('model', 'whisper-1')
        self.proxy = credentials.get('proxy')  # 代理设置
        
    def connect(self, **kwargs) -> bool:
        # HTTP协议无需建立连接
        self.connected = True
        return True
        
    def transcribe_file(self, audio_path: str, **kwargs) -> ASRResult:
        """转录音频文件"""
        import requests
        
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        with open(audio_path, 'rb') as f:
            files = {"file": f}
            data = {
                "model": self.model,
                "language": kwargs.get('language'),
                "response_format": kwargs.get('response_format', 'json')
            }
            data = {k: v for k, v in data.items() if v is not None}
            
            proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
            
            start_time = time.time()
            response = requests.post(
                self.API_URL, 
                headers=headers,
                files=files, 
                data=data, 
                proxies=proxies,
                timeout=kwargs.get('timeout', 60)
            )
            latency = time.time() - start_time
            
        if response.status_code == 200:
            result = response.json()
            return ASRResult(
                text=result.get('text', ''),
                is_final=True,
                language=result.get('language', ''),
                raw_response=result
            )
        else:
            raise Exception(f"Whisper API error: {response.status_code} - {response.text}")
```

---

## 6. 配置管理

### 6.1 厂商配置文件

**文件**: `config/vendors.yml`

```yaml
version: "1.0"
updated_at: "2026-05-25"

vendors:
  # ==================== 国内厂商 ====================
  volcengine:
    name: "火山引擎"
    name_en: "Volcengine"
    region: cn
    description: "字节跳动旗下云服务平台"
    website: "https://www.volcengine.com"
    console: "https://console.volcengine.com/speech"
    
    services:
      asr_streaming:
        name: "流式语音识别"
        name_en: "Streaming ASR"
        api_type: asr
        protocol: websocket
        endpoint: "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
        auth_type: header
        auth_fields:
          - name: "X-Api-App-Key"
            key: "app_key"
            description: "应用ID"
          - name: "X-Api-Access-Key"
            key: "access_key"
            description: "访问密钥"
          - name: "X-Api-Resource-Id"
            key: "resource_id"
            description: "资源ID"
            default: "volc.seedasr.sauc.duration"
        models:
          - id: "volc.seedasr.sauc.duration"
            name: "豆包流式语音识别2.0 (小时版)"
          - id: "volc.seedasr.sauc.concurrent"
            name: "豆包流式语音识别2.0 (并发版)"
        audio_formats: [pcm, wav, ogg, mp3]
        sample_rates: [16000]
        features:
          - id: "speaker_diarization"
            name: "说话人分离"
            param: "enable_speaker_info"
          - id: "emotion_detection"
            name: "情绪检测"
            param: "enable_emotion_detection"
          - id: "gender_detection"
            name: "性别检测"
            param: "enable_gender_detection"
          - id: "language_identification"
            name: "语种识别"
            param: "enable_lid"
          - id: "hot_words"
            name: "热词"
            param: "boosting_table_name"
        languages:
          - code: "zh-CN"
            name: "普通话"
            dialects:
              - code: "shanghai"
                name: "上海话"
              - code: "minnan"
                name: "闽南语"
              - code: "cantonese"
                name: "粤语"
              - code: "sichuan"
                name: "四川话"
              - code: "shaanxi"
                name: "陕西话"
          - code: "en-US"
            name: "英语"
          - code: "ja-JP"
            name: "日语"
          - code: "ko-KR"
            name: "韩语"
            
      asr_file:
        name: "录音文件识别"
        name_en: "File ASR"
        api_type: asr
        protocol: http
        endpoint_submit: "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
        endpoint_query: "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
        auth_type: header
        auth_fields:
          - name: "X-Api-Key"
            key: "api_key"
            description: "API密钥"
          - name: "X-Api-Resource-Id"
            key: "resource_id"
            description: "资源ID"
            default: "volc.seedasr.auc"
        models:
          - id: "volc.seedasr.auc"
            name: "豆包录音文件识别模型2.0"
          - id: "volc.bigasr.auc"
            name: "豆包录音文件识别模型1.0"
        audio_formats: [wav, mp3, ogg, raw]
        max_file_size: 524288000  # 512MB
        max_duration: 28800       # 8小时
        
      ast:
        name: "端到端语音翻译"
        name_en: "AST (Speech-to-Speech Translation)"
        api_type: ast
        protocol: websocket_protobuf
        endpoint: "wss://openspeech.bytedance.com/api/v1/ast/v2"
        auth_type: header
        auth_fields:
          - name: "X-Api-App-Key"
            key: "app_key"
          - name: "X-Api-Access-Key"
            key: "access_key"
          - name: "X-Api-Resource-Id"
            key: "resource_id"
            default: "volc.ast"
        features:
          - id: "asr"
            name: "语音识别"
          - id: "translation"
            name: "翻译"
          - id: "tts"
            name: "语音合成"
        modes:
          - id: "s2s"
            name: "语音到语音"
          - id: "s2t"
            name: "语音到文本"
        language_pairs:
          - source: "zh"
            target: "en"
            name: "中译英"
          - source: "en"
            target: "zh"
            name: "英译中"
            
      realtime:
        name: "实时语音对话"
        name_en: "Realtime Dialogue"
        api_type: realtime
        protocol: websocket_protobuf
        endpoint: "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
        auth_type: header
        auth_fields:
          - name: "X-Api-App-ID"
            key: "app_id"
          - name: "X-Api-Access-Key"
            key: "access_key"
          - name: "X-Api-Resource-Id"
            key: "resource_id"
            default: "volc.speech.dialog"
        voices:
          - id: "zh_female_vv_jupiter_bigtts"
            name: "vv"
            description: "活泼灵动的女声"
          - id: "zh_female_xiaohe_jupiter_bigtts"
            name: "xiaohe"
            description: "甜美活泼的女声(台湾口音)"
          - id: "zh_male_yunzhou_jupiter_bigtts"
            name: "yunzhou"
            description: "清爽沉稳的男声"
          - id: "zh_male_xiaotian_jupiter_bigtts"
            name: "xiaotian"
            description: "清爽磁性的男声"

  aliyun:
    name: "阿里云"
    name_en: "Alibaba Cloud"
    region: cn
    description: "阿里云计算平台"
    website: "https://www.aliyun.com"
    console: "https://bailian.console.aliyun.com"
    
    services:
      asr_realtime:
        name: "百炼实时语音识别"
        name_en: "Bailian Realtime ASR"
        api_type: asr
        protocol: websocket
        endpoint: "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
        endpoint_intl: "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"
        auth_type: api_key
        auth_fields:
          - name: "Authorization"
            key: "api_key"
            format: "Bearer {api_key}"
        models:
          - id: "fun-asr-realtime"
            name: "Fun-ASR实时版"
          - id: "paraformer-realtime-v2"
            name: "Paraformer实时版v2"
          - id: "qwen-asr-realtime"
            name: "Qwen-ASR实时版"
        audio_formats: [pcm, wav, opus, speex, aac, amr]
        sample_rates: [8000, 16000]
        
      qwen_llm:
        name: "通义千问"
        name_en: "Qwen LLM"
        api_type: llm
        protocol: http
        endpoint: "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
        auth_type: api_key
        models:
          - id: "qwen-turbo"
            name: "通义千问-Turbo"
          - id: "qwen-plus"
            name: "通义千问-Plus"
          - id: "qwen-max"
            name: "通义千问-Max"
            
      qwen_ast:
        name: "通义千问实时语音翻译"
        name_en: "Qwen Live Translate"
        api_type: ast
        protocol: websocket
        endpoint: "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
        auth_type: api_key
        models:
          - id: "qwen3-livetranslate-flash-realtime"
            name: "Qwen3实时语音翻译"
        languages:
          - code: "en"
            name: "英语"
          - code: "zh"
            name: "中文"
          - code: "ja"
            name: "日语"
          - code: "ko"
            name: "韩语"
          - code: "ru"
            name: "俄语"
          - code: "fr"
            name: "法语"
          - code: "de"
            name: "德语"
          - code: "es"
            name: "西班牙语"
          - code: "pt"
            name: "葡萄牙语"
          - code: "it"
            name: "意大利语"
          - code: "yue"
            name: "粤语"
        voices:
          - id: "Cherry"
            name: "Cherry"
            description: "女声"
          - id: "Nofish"
            name: "Nofish"
            description: "男声"
          - id: "Sunny"
            name: "晴儿"
            description: "四川女声"
          - id: "Jada"
            name: "阿珍"
            description: "上海女声"
          - id: "Dylan"
            name: "晓东"
            description: "北京男声"
          - id: "Peter"
            name: "李彼得"
            description: "天津男声"
          - id: "Eric"
            name: "程川"
            description: "四川男声"
          - id: "Kiki"
            name: "阿清"
            description: "粤语女声"

  # ==================== 海外厂商 ====================
  openai:
    name: "OpenAI"
    name_en: "OpenAI"
    region: global
    requires_proxy: true
    description: "OpenAI API服务"
    website: "https://openai.com"
    console: "https://platform.openai.com"
    
    services:
      whisper:
        name: "Whisper语音识别"
        name_en: "Whisper ASR"
        api_type: asr
        protocol: http
        endpoint: "https://api.openai.com/v1/audio/transcriptions"
        auth_type: bearer
        auth_fields:
          - name: "Authorization"
            key: "api_key"
            format: "Bearer {api_key}"
        models:
          - id: "whisper-1"
            name: "Whisper v1"
        audio_formats: [mp3, mp4, mpeg, mpga, m4a, wav, webm]
        languages: 99
        max_file_size: 26214400  # 25MB
        
      gpt:
        name: "GPT大语言模型"
        name_en: "GPT LLM"
        api_type: llm
        protocol: http
        endpoint: "https://api.openai.com/v1/chat/completions"
        auth_type: bearer
        models:
          - id: "gpt-4o"
            name: "GPT-4o"
          - id: "gpt-4-turbo"
            name: "GPT-4 Turbo"
          - id: "gpt-3.5-turbo"
            name: "GPT-3.5 Turbo"
            
      realtime:
        name: "Realtime API"
        name_en: "Realtime Voice API"
        api_type: realtime
        protocol: websocket
        endpoint: "wss://api.openai.com/v1/realtime"
        auth_type: bearer
        models:
          - id: "gpt-4o-realtime-preview"
            name: "GPT-4o Realtime"

  google:
    name: "Google"
    name_en: "Google Cloud"
    region: global
    requires_proxy: true
    description: "Google Cloud AI服务"
    website: "https://cloud.google.com"
    
    services:
      gemini_live:
        name: "Gemini实时对话"
        name_en: "Gemini Live API"
        api_type: realtime
        protocol: websocket
        auth_type: api_key
        models:
          - id: "gemini-2.0-flash-live-001"
            name: "Gemini 2.0 Flash Live"
            
      speech_to_text:
        name: "语音识别"
        name_en: "Speech-to-Text"
        api_type: asr
        protocol: http
        endpoint: "https://speech.googleapis.com/v1/speech:recognize"
        auth_type: oauth2

  azure:
    name: "Azure"
    name_en: "Microsoft Azure"
    region: global
    requires_proxy: true
    description: "微软Azure认知服务"
    website: "https://azure.microsoft.com"
    
    services:
      speech:
        name: "Azure语音服务"
        name_en: "Azure Speech Services"
        api_type: asr
        protocol: websocket
        endpoint_template: "wss://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
        auth_type: subscription_key
        auth_fields:
          - name: "Ocp-Apim-Subscription-Key"
            key: "subscription_key"
          - name: "Ocp-Apim-Subscription-Region"
            key: "region"
        regions:
          - id: "eastasia"
            name: "东亚"
          - id: "southeastasia"
            name: "东南亚"
          - id: "westus"
            name: "美国西部"
```

### 6.2 凭据配置文件

**文件**: `config/credentials.yml` (添加到.gitignore)

```yaml
version: "1.0"
updated_at: "2026-05-25"

credentials:
  volcengine:
    app_key: "${VOLC_APP_KEY}"
    access_key: "${VOLC_ACCESS_KEY}"
    api_key: "${VOLC_API_KEY}"
    
  aliyun:
    api_key: "${ALIYUN_API_KEY}"
    
  openai:
    api_key: "${OPENAI_API_KEY}"
    proxy: "${OPENAI_PROXY}"
    
  google:
    api_key: "${GOOGLE_API_KEY}"
    proxy: "${GOOGLE_PROXY}"
    
  azure:
    subscription_key: "${AZURE_SUBSCRIPTION_KEY}"
    region: "${AZURE_REGION}"
    proxy: "${AZURE_PROXY}"
```

---

## 7. 文件结构

```
api_adaper_service/
├── adapters/
│   ├── __init__.py
│   │
│   ├── base/
│   │   ├── __init__.py
│   │   ├── base_adapter.py          # 适配器基类
│   │   ├── asr_adapter.py           # ASR适配器基类
│   │   ├── ast_adapter.py           # AST适配器基类
│   │   ├── tts_adapter.py           # TTS适配器基类
│   │   ├── llm_adapter.py           # LLM适配器基类
│   │   └── realtime_adapter.py      # 实时对话适配器基类
│   │
│   ├── volcengine/                   # 火山引擎
│   │   ├── __init__.py
│   │   ├── volc_asr_adapter.py       # 流式ASR
│   │   ├── volc_asr_file_adapter.py  # 录音文件识别
│   │   ├── volc_ast_adapter.py       # 端到端语音翻译
│   │   └── volc_realtime_adapter.py  # 实时语音对话
│   │
│   ├── aliyun/                       # 阿里云
│   │   ├── __init__.py
│   │   ├── bailian_asr_adapter.py    # 百炼ASR
│   │   ├── qwen_llm_adapter.py       # 通义千问LLM
│   │   └── qwen_ast_adapter.py       # 通义千问语音翻译
│   │
│   ├── tencent/                      # 腾讯云
│   │   ├── __init__.py
│   │   └── tencent_asr_adapter.py
│   │
│   ├── baidu/                        # 百度智能云
│   │   ├── __init__.py
│   │   └── baidu_asr_adapter.py
│   │
│   ├── openai/                       # OpenAI
│   │   ├── __init__.py
│   │   ├── whisper_adapter.py        # Whisper ASR
│   │   ├── gpt_adapter.py            # GPT LLM
│   │   └── openai_realtime_adapter.py
│   │
│   ├── google/                       # Google
│   │   ├── __init__.py
│   │   ├── gemini_adapter.py
│   │   └── google_speech_adapter.py
│   │
│   ├── azure/                        # Azure
│   │   ├── __init__.py
│   │   └── azure_speech_adapter.py
│   │
│   ├── aws/                          # AWS
│   │   ├── __init__.py
│   │   ├── transcribe_adapter.py
│   │   └── polly_adapter.py
│   │
│   └── mock_adapter.py               # Mock测试适配器
│
├── protocols/
│   ├── __init__.py
│   ├── http_protocol.py              # HTTP协议处理
│   ├── websocket_protocol.py         # WebSocket协议处理
│   ├── protobuf_protocol.py          # Protobuf协议处理
│   └── volc_binary_protocol.py       # 火山引擎二进制协议
│
├── config/
│   ├── application.yml               # 应用配置
│   ├── vendors.yml                   # 厂商配置
│   ├── credentials.yml.example       # 凭据配置示例
│   └── credentials.yml               # 凭据配置 (gitignore)
│
├── services/
│   ├── __init__.py
│   ├── adapter_factory.py            # 适配器工厂
│   ├── audio_processor.py            # 音频处理器
│   ├── task_manager.py               # 任务管理器
│   └── latency_tracker.py            # 时延追踪器
│
├── utils/
│   ├── __init__.py
│   ├── config.py                     # 配置加载
│   ├── logger.py                     # 日志工具
│   ├── proxy_manager.py              # 代理管理
│   └── audio_utils.py                # 音频工具
│
├── app/
│   ├── __init__.py
│   └── main.py                       # 主程序入口
│
├── tests/
│   ├── __init__.py
│   ├── test_adapter_factory.py
│   ├── test_volc_asr.py
│   ├── test_bailian_asr.py
│   └── test_whisper.py
│
├── protos/                           # Protobuf定义文件
│   └── volcengine/
│       └── ast/
│           ├── ast_service.proto
│           └── events.proto
│
├── requirements.txt
├── .env.example
└── README.md
```

---

## 8. 实现计划

### 8.1 阶段一: 基础框架 (1周)

| 任务 | 优先级 | 预估时间 |
|------|--------|----------|
| 创建适配器基类和接口定义 | P0 | 1天 |
| 实现适配器工厂 | P0 | 0.5天 |
| 实现配置管理 (vendors.yml加载) | P0 | 0.5天 |
| 实现协议处理器 (HTTP/WebSocket) | P0 | 1天 |
| 实现Mock适配器完善 | P0 | 0.5天 |
| 单元测试框架 | P0 | 0.5天 |

### 8.2 阶段二: 国内厂商适配器 (2周)

| 任务 | 优先级 | 预估时间 |
|------|--------|----------|
| 火山引擎流式ASR适配器 | P0 | 2天 |
| 火山引擎录音文件识别适配器 | P0 | 1天 |
| 火山引擎AST适配器 | P0 | 2天 |
| 阿里云百炼ASR适配器 | P0 | 2天 |
| 通义千问LLM适配器 | P1 | 1天 |
| 通义千问语音翻译适配器 | P1 | 1天 |
| 集成测试 | P0 | 1天 |

### 8.3 阶段三: 海外厂商适配器 (1周)

| 任务 | 优先级 | 预估时间 |
|------|--------|----------|
| OpenAI Whisper适配器 | P1 | 1天 |
| OpenAI GPT适配器 | P1 | 0.5天 |
| Google Gemini适配器 | P2 | 1天 |
| Azure Speech适配器 | P2 | 1天 |
| 代理管理实现 | P1 | 0.5天 |
| 集成测试 | P1 | 1天 |

### 8.4 阶段四: 完善和优化 (1周)

| 任务 | 优先级 | 预估时间 |
|------|--------|----------|
| 错误处理和重试机制 | P1 | 1天 |
| 时延统计完善 | P1 | 1天 |
| API健康监控 | P2 | 1天 |
| 文档完善 | P1 | 1天 |
| 性能测试和优化 | P2 | 1天 |

---

## 9. 测试策略

### 9.1 单元测试

```python
# tests/test_adapter_factory.py
def test_adapter_factory_registration():
    """测试适配器注册"""
    assert "volcengine_asr" in AdapterFactory.list_adapters()
    assert "aliyun_asr" in AdapterFactory.list_adapters()
    assert "openai_asr" in AdapterFactory.list_adapters()

def test_adapter_factory_create():
    """测试适配器创建"""
    adapter = AdapterFactory.create(
        vendor="volcengine",
        api_type=APIType.ASR,
        config=mock_config,
        credentials=mock_credentials
    )
    assert adapter.vendor == "volcengine"
    assert adapter.api_type == APIType.ASR
```

### 9.2 集成测试

```python
# tests/test_volc_asr.py
@pytest.mark.integration
def test_volc_asr_streaming():
    """测试火山引擎流式ASR"""
    config = load_vendor_config("volcengine", "asr_streaming")
    credentials = load_credentials("volcengine")
    
    adapter = VolcASRAdapter(config, credentials)
    assert adapter.connect()
    
    audio_config = AudioConfig(format="wav", sample_rate=16000)
    assert adapter.start_recognition(audio_config)
    
    # 发送测试音频
    with open("test_audio.wav", "rb") as f:
        audio_data = f.read()
    
    result = adapter.transcribe_file("test_audio.wav")
    assert result.text != ""
    assert result.is_final == True
```

### 9.3 Mock测试

```python
# tests/test_mock_adapter.py
def test_mock_adapter_asr():
    """测试Mock ASR适配器"""
    adapter = MockAdapter(mock_config, {})
    assert adapter.connect()
    
    result = adapter.transcribe_file("test.wav")
    assert result.text != ""
    assert result.is_final == True
```

---

## 10. 风险和注意事项

### 10.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 火山引擎Protobuf协议复杂 | 高 | 参考现有demo代码，逐步实现 |
| 海外API代理稳定性 | 中 | 实现多代理切换和重试机制 |
| API版本变更 | 中 | 配置化设计，便于更新 |
| 并发性能 | 中 | 使用异步IO，连接池管理 |

### 10.2 安全注意事项

1. **密钥管理**: 所有API密钥通过环境变量或加密配置文件管理
2. **敏感数据**: 测试音频和结果数据需要脱敏处理
3. **代理安全**: 海外API代理需要验证安全性
4. **日志脱敏**: 日志中不记录敏感信息

### 10.3 合规注意事项

1. **数据出境**: 海外API调用涉及数据出境，需遵守相关法规
2. **API使用条款**: 遵守各厂商API使用条款
3. **测试数据**: 使用合规的测试音频数据

---

## 11. 附录

### 11.1 参考文档

- [火山引擎语音识别大模型API](https://www.volcengine.com/docs/6561/1354868)
- [火山引擎流式语音识别API](https://www.volcengine.com/docs/6561/1354869)
- [火山引擎端到端实时语音大模型API](https://www.volcengine.com/docs/6561/1594356)
- [阿里云百炼实时语音识别](https://help.aliyun.com/zh/model-studio/real-time-speech-recognition-user-guide)
- [OpenAI Whisper API](https://platform.openai.com/docs/guides/speech-to-text)
- [Google Gemini API](https://ai.google.dev/gemini-api)
- [Azure Speech Services](https://learn.microsoft.com/azure/ai-services/speech-service/)

### 11.2 术语表

| 术语 | 说明 |
|------|------|
| ASR | Automatic Speech Recognition，自动语音识别 |
| TTS | Text-to-Speech，文本转语音 |
| AST | Automatic Speech Translation，自动语音翻译 |
| LLM | Large Language Model，大语言模型 |
| RTF | Real-time Factor，实时因子 (处理时长/音频时长) |
| ITN | Inverse Text Normalization，逆文本规范化 |
| VAD | Voice Activity Detection，语音活动检测 |
