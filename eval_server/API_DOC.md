# 评估维度服务 (WER/SER/CPWER/TCPWER/STM_WER/DER) API 文档

## 1. 服务概述

该服务提供音频评估维度计算功能，支持 WER、SER、CPWER、TCPWER、STM_WER 和 DER 的计算。服务采用异步任务处理模式，支持并发控制、状态查询、分布式调度和动态配置。

### 1.1 架构设计

- **MVC 模式**：采用标准的 Model-View-Controller 架构，确保代码的可维护性和可扩展性。
- **本地/远程处理**：支持本地处理和分发到远程 Worker 节点处理。
- **两层并发控制**：
  - **本地并发**：限制单个服务实例同时处理的任务数量（默认 10）。
  - **远程端点并发**：限制分发到各远程 Worker 节点的任务数量。
- **动态配置**：支持通过 API 动态调整端点的并发限制，无需重启服务。
- **持久化存储**：使用 SQLite3 存储任务状态、结果和端点配置。

### 1.2 任务处理流程

```
客户端请求 POST /api/create_task
    ↓
┌──────────────────────────────────────┐
│  判断 endpoints 参数                   │
├──────────────────────────────────────┤
│  无 endpoints → 本地处理               │
│  有 endpoints → 分发到远程端点          │
└──────────────────────────────────────┘
```

## 2. 基础信息

- 服务名称：evaluation-dimension-service
- 基础URL：`http://localhost:{port}`
- 默认端口：5001
- 支持的请求格式：JSON
- 认证方式：无（开发环境）

## 3. API 接口

### 3.1 健康检查

#### 3.1.1 接口描述
用于检查服务是否正常运行，并返回当前服务的并发状态。

#### 3.1.2 请求信息
- **请求方法**：GET
- **请求URL**：`/health`
- **请求参数**：无

#### 3.1.3 响应信息
- **状态码**：200（健康）
- **响应格式**：JSON

#### 3.1.4 响应示例
```json
{
  "status": "healthy",
  "service": "wer-ser-calculator",
  "role": "master",
  "supported_task_types": ["wer", "ser", "cpwer", "tcpwer", "stm_wer", "der"],
  "local": {
    "max_concurrency": 10,
    "current_concurrency": 2,
    "available_concurrency": 8
  }
}
```

---

### 3.2 创建评估任务

#### 3.2.1 接口描述
创建一个新的评估任务，返回任务ID和查询URL。

**处理模式**：
- **本地处理**：不传 `endpoints` 参数时，任务在本地处理。
- **分布式调度**：传入 `endpoints` 参数时，任务分发到配置的远程端点处理。

**任务类型说明**：
- **WER (Word Error Rate)**：词错误率，用于评估 ASR 识别结果与参考文本之间的词错误率。
- **SER (Sentence Error Rate)**：句错误率，用于评估句子级别的识别准确率。
- **CPWER (Concatenated Per-utterance Word Error Rate)**：连接词错误率，用于评估多说话人场景。
- **TCPWER (Time-constrained CPWER)**：时间约束词错误率，用于评估带时间对齐的识别准确率。
- **STM_WER**：基于 STM 文件的词错误率计算。
- **DER (Diarization Error Rate)**：说话人分离错误率，用于评估说话人分离的准确性。

#### 3.2.2 请求信息
- **请求方法**：POST
- **请求URL**：`/api/create_task`
- **Content-Type**：application/json

**通用参数**：

| 参数名 | 类型 | 必填 | 描述 | 示例值 |
|--------|------|------|------|--------|
| task_type | string | 否 | 任务类型，可选值：`wer`, `ser`, `cpwer`, `tcpwer`, `stm_wer`, `der`。默认值：`wer` | `wer` |
| endpoints | array | 否 | 远程端点列表，用于分布式任务调度。不传则本地处理 | 见下方示例 |
| normalize | bool | 否 | 是否对文本进行正则化处理。默认 false | `true` |

**不同任务类型的必填字段**：

| 任务类型 | 必填字段 |
|----------|----------|
| wer | `asr_ref`, `asr_result` |
| ser | `asr_ref`, `asr_result` |
| cpwer | `ref_stm`, `hyp_stm` |
| tcpwer | `ref_stm`, `hyp_stm` |
| stm_wer | `ref_stm`, `hyp_stm` |
| der | `rttm_ref`, `stm_ref`, `rttm_res`, `stm_res` |

**WER/SER 字段说明**：

| 参数名 | 类型 | 必填 | 描述 | 示例值 |
|--------|------|------|------|--------|
| asr_ref | string/object | 是 | 参考文本（标准答案），支持字符串或 JSON 格式 | `今天天气不错` |
| asr_result | string/object | 是 | ASR 识别结果（待评估文本），支持字符串或 JSON 格式 | `今天天气不措` |
| source_lang | string | 否 | 源语言 | `zh` |
| target_lang | string | 否 | 目标语言 | `en` |
| translate_direct | string | 否 | 翻译方向 | `zh2en` |

**CPWER/TCPWER/STM_WER 字段说明**：

| 参数名 | 类型 | 必填 | 描述 | 示例值 |
|--------|------|------|------|--------|
| ref_stm | string/object | 是 | 参考 STM，支持以下格式：<br>1. STM 字符串<br>2. `{"text": "stm string"}`<br>3. `{"json": [...]}` | 见下方示例 |
| hyp_stm | string/object | 是 | 识别结果 STM，支持格式同上 | 见下方示例 |
| source_lang | string | 否 | 源语言 | `zh` |
| target_lang | string | 否 | 目标语言 | `en` |
| translate_direct | string | 否 | 翻译方向 | `zh2en` |
| collar | float | 否 | TCPWER 专用，时间对齐容差（秒），默认 0.0 | `0.5` |

**DER 字段说明**：

| 参数名 | 类型 | 必填 | 描述 | 示例值 |
|--------|------|------|------|--------|
| rttm_ref | string/object | 是 | 参考 RTTM，支持以下格式：<br>1. RTTM 字符串<br>2. `{"text": "rttm string"}`<br>3. `{"json": [...]}` | 见下方示例 |
| stm_ref | string/object | 是 | 参考 STM，支持格式同上 | 见下方示例 |
| rttm_res | string/object | 是 | 识别结果 RTTM，支持格式同上 | 见下方示例 |
| stm_res | string/object | 是 | 识别结果 STM，支持格式同上 | 见下方示例 |
| source_lang | string | 否 | 源语言 | `zh` |
| target_lang | string | 否 | 目标语言 | `en` |
| translate_direct | string | 否 | 翻译方向 | `zh2en` |
| collar | float | 否 | 时间对齐容差（秒），默认 0.5 | `0.5` |
| skip_overlap | bool | 否 | 是否跳过重叠语音计算，默认 False | `false` |

#### 3.2.3 请求示例

**WER 任务（纯文本）：**
```json
{
  "task_type": "wer",
  "asr_ref": "今天天气不错",
  "asr_result": "今天天气不措",
  "source_lang": "zh",
  "target_lang": "en",
  "translate_direct": "zh2en"
}
```

**CPWER 任务（STM JSON 格式）：**
```json
{
  "task_type": "cpwer",
  "ref_stm": {
    "json": [
      {"file_id": "rec1", "channel": "1", "speaker": "spk1", "start": 0.0, "end": 1.0, "text": "hello world"},
      {"file_id": "rec1", "channel": "1", "speaker": "spk2", "start": 1.0, "end": 2.0, "text": "test text"}
    ]
  },
  "hyp_stm": {
    "json": [
      {"file_id": "rec1", "channel": "1", "speaker": "spk1", "start": 0.0, "end": 1.0, "text": "hello world"},
      {"file_id": "rec1", "channel": "1", "speaker": "spk2", "start": 1.0, "end": 2.0, "text": "test"}
    ]
  },
  "normalize": true
}
```

**CPWER 任务（STM 字符串格式）：**
```json
{
  "task_type": "cpwer",
  "ref_stm": "rec1 1 spk1 0.0 1.0 <o> hello world\nrec1 1 spk2 1.0 2.0 <o> test text",
  "hyp_stm": "rec1 1 spk1 0.0 1.0 <o> hello world\nrec1 1 spk2 1.0 2.0 <o> test",
  "normalize": true
}
```

**DER 任务（RTTM/STM JSON 格式）：**
```json
{
  "task_type": "der",
  "rttm_ref": {
    "json": [
      {"speaker": "speaker1", "start": 0.0, "duration": 1.0},
      {"speaker": "speaker2", "start": 1.0, "duration": 2.0}
    ]
  },
  "stm_ref": {
    "json": [
      {"file_id": "rec1", "channel": "1", "speaker": "speaker1", "start": 0.0, "end": 1.0, "text": "hello"},
      {"file_id": "rec1", "channel": "1", "speaker": "speaker2", "start": 1.0, "end": 2.0, "text": "world"}
    ]
  },
  "rttm_res": {
    "json": [
      {"speaker": "speaker1", "start": 0.0, "duration": 1.0},
      {"speaker": "speaker1", "start": 1.0, "duration": 2.0}
    ]
  },
  "stm_res": {
    "json": [
      {"file_id": "rec1", "channel": "1", "speaker": "speaker1", "start": 0.0, "end": 1.0, "text": "hello"},
      {"file_id": "rec1", "channel": "1", "speaker": "speaker1", "start": 1.0, "end": 2.0, "text": "worl"}
    ]
  }
}
```

**响应示例：**
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "task_id": "task_abc123",
    "status_url": "http://localhost:5001/api/get_status/task_abc123",
    "final_result_url": "http://localhost:5001/api/get_final_result/task_abc123",
    "task_type": "cpwer",
    "msg": "任务已创建，正在本地处理"
  }
}
```

---

### 3.3 获取任务状态

#### 3.3.1 接口描述
获取指定任务的当前状态和基本信息。

#### 3.3.2 请求信息
- **请求方法**：GET
- **请求URL**：`/api/get_status/{task_id}`
- **路径参数**：
  - `task_id`：任务ID

#### 3.3.3 响应信息
- **状态码**：200（成功）/ 404（任务不存在）
- **响应格式**：JSON

#### 3.3.4 响应示例
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "task_id": "task_1234567890",
    "status": "completed",
    "task_type": "cpwer",
    "created_at": "2026-01-10 10:00:00",
    "started_at": "2026-01-10 10:00:01",
    "completed_at": "2026-01-10 10:00:02",
    "error_msg": ""
  }
}
```

---

### 3.4 获取最终评估结果

#### 3.4.1 接口描述
获取指定任务的最终评估计算结果。

#### 3.4.2 请求信息
- **请求方法**：GET
- **请求URL**：`/api/get_final_result/{task_id}`
- **路径参数**：
  - `task_id`：任务ID

#### 3.4.3 响应信息
- **状态码**：
  - 200：成功获取结果
  - 202：任务正在处理中
  - 404：任务不存在
  - 500：任务失败
- **响应格式**：JSON

#### 3.4.4 响应示例

**CPWER 响应示例：**
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "task_id": "task_1234567890",
    "status": "completed",
    "task_type": "cpwer",
    "result": {
      "cpwer": 0.25,
      "errors": 4,
      "length": 16,
      "insertions": 0,
      "deletions": 2,
      "substitutions": 2
    },
    "completed_at": "2026-01-10 10:00:02"
  }
}
```

**DER 响应示例：**
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "task_id": "task_der123",
    "status": "completed",
    "task_type": "der",
    "result": {
      "der": 0.1534,
      "missed_speech_rate": 0.05,
      "false_alarm_rate": 0.02,
      "speaker_error_rate": 0.08,
      "total_reference_time": 100.0,
      "collar": 0.5,
      "skip_overlap": false
    },
    "completed_at": "2026-01-10 10:00:02"
  }
}
```

---

## 4. 错误码说明

| 错误码 | 描述 | HTTP 状态码 |
|--------|------|-------------|
| 0 | 成功 | 200 |
| 3000 | 业务逻辑错误 (如: 任务不存在, 状态异常) | 400 |
| 3001 | 并发已满 (本地并发达到上限或远程端点无可用) | 429 |
| 4000 | 参数验证错误 | 400 |
| 5000 | 服务器内部错误 | 500 |

---

## 5. 版本信息

- **版本**：1.3.0
- **更新日期**：2026-03-19
- **更新内容**：
  - 新增 CPWER、TCPWER、STM_WER 任务类型支持
  - 支持 JSON 格式输入（优先于 STM/RTTM 字符串）
  - 支持文本正则化（中文使用 tn.chinese.normalizer，英文使用 nemo_text_processing）
  - JSON 输入时优先进行正则化再转换为 STM 格式
- **开发环境**：Python 3.10+, Flask 3.0+, SQLite3
