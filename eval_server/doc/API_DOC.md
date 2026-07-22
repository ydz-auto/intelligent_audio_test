# eval_server API 接口文档

## 1. 服务概述

音频评估维度计算服务，支持 WER、SER、CPWER、TCPWER、STM_WER、DER、LLM Judge、小艺指标(xiaoyi_metrics) 的计算。服务采用异步任务处理模式，支持并发控制、状态查询、分布式调度、文件上传和动态配置。

### 1.1 基础信息

- 服务名称：evaluation-dimension-service
- 基础URL：`http://localhost:{port}`
- 默认端口：5001
- 支持的请求格式：JSON / multipart/form-data
- 认证方式：无（开发环境）

### 1.2 支持的任务类型

| task_type | 说明 | 必填字段 | 请求方式 |
|-----------|------|---------|---------|
| wer | 词错误率 | asr_ref, asr_result | JSON |
| ser | 句错误率 | asr_ref, asr_result | JSON |
| cpwer | 连接词错误率 | ref_stm, hyp_stm | JSON |
| tcpwer | 时间约束词错误率 | ref_stm, hyp_stm | JSON |
| stm_wer | 基于 STM 的 WER | ref_stm, hyp_stm | JSON |
| der | 说话人分离错误率 | rttm_ref, stm_ref, rttm_res, stm_res | JSON |
| llm_judge | LLM 语义评分 | answer, correct_answer | JSON |
| xiaoyi_metrics | 小艺指标(tor+false_takeover+takeover_latency) | record_path, pause, first_frame_ms, end_ms | multipart |

---

## 2. API 接口

### 2.1 健康检查

- **方法**：GET
- **URL**：`/health`
- **参数**：无

**响应示例：**
```json
{
  "status": "healthy",
  "service": "wer-ser-calculator",
  "role": "master",
  "supported_task_types": ["wer", "ser", "cpwer", "tcpwer", "stm_wer", "der", "llm_judge", "xiaoyi_metrics"],
  "local": {
    "max_concurrency": 10,
    "current_concurrency": 2,
    "available_concurrency": 8
  }
}
```

---

### 2.2 创建评估任务（JSON）

- **方法**：POST
- **URL**：`/api/create_task`
- **Content-Type**：application/json

**通用参数：**

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| task_type | string | 否 | 任务类型，默认 wer |
| endpoints | array | 否 | 远程端点列表，不传则本地处理 |
| normalize | bool | 否 | 是否文本正则化，默认 false |

**WER/SER 请求示例：**
```json
{
  "task_type": "wer",
  "asr_ref": "今天天气不错",
  "asr_result": "今天天气不措",
  "source_lang": "zh"
}
```

**DER 请求示例：**
```json
{
  "task_type": "der",
  "rttm_ref": {"json": [{"speaker": "spk1", "start": 0.0, "duration": 1.0}]},
  "stm_ref": {"json": [{"file_id": "rec1", "channel": "1", "speaker": "spk1", "start": 0.0, "end": 1.0, "text": "hello"}]},
  "rttm_res": {"json": [{"speaker": "spk1", "start": 0.0, "duration": 1.0}]},
  "stm_res": {"json": [{"file_id": "rec1", "channel": "1", "speaker": "spk1", "start": 0.0, "end": 1.0, "text": "hello"}]}
}
```

**LLM Judge 请求示例：**
```json
{
  "task_type": "llm_judge",
  "answer": "北京是中国的首都",
  "correct_answer": "中国的首都是北京",
  "query": "中国的首都是哪个城市？",
  "model": "gpt-4",
  "prompt": "评估回答的准确性和相关性"
}
```

---

### 2.3 创建评估任务（文件上传）

- **方法**：POST
- **URL**：`/api/create_task_upload`
- **Content-Type**：multipart/form-data

用于需要上传音频文件的任务（如 xiaoyi_metrics）。文件字段会被提取为 multipart 上传，payload 中对应路径替换为 `__MULTIPART__:field_name` 占位符，eval_server 收到后保存文件并替换为实际路径。

**xiaoyi_metrics 请求示例：**

```bash
curl -X POST http://localhost:5001/api/create_task_upload \
  -F "task_type=xiaoyi_metrics" \
  -F "record_file=@audio.wav" \
  -F "first_frame_ms=1700000000000" \
  -F "end_ms=1700000005000" \
  -F "offset_ms=40" \
  -F 'pause=[{"text":"","timestamp":[1.0,2.0]}]'
```

**xiaoyi_metrics 参数说明：**

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| task_type | string | 是 | 固定为 `xiaoyi_metrics` |
| record_file | file | 是 | wav 录音文件（multipart 上传） |
| pause | json string | 是 | 停顿区间数据 `[{"text":"","timestamp":[start,end]}]` |
| first_frame_ms | int | 是 | 录屏首帧时刻（毫秒 Unix 时间戳） |
| end_ms | int | 是 | 音频播放结束时刻（毫秒 Unix 时间戳） |
| offset_ms | int | 否 | 时延补偿，默认 40 |

---

### 2.4 创建任务响应

所有创建任务的响应格式统一：

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "task_id": "task_abc123",
    "status_url": "http://localhost:5001/api/get_status/task_abc123",
    "final_result_url": "http://localhost:5001/api/get_final_result/task_abc123",
    "task_type": "xiaoyi_metrics",
    "msg": "任务已创建，正在本地处理"
  }
}
```

---

### 2.5 获取任务状态

- **方法**：GET
- **URL**：`/api/get_status/{task_id}`

**响应示例：**
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "task_id": "task_1234567890",
    "status": "completed",
    "task_type": "xiaoyi_metrics",
    "created_at": "2026-07-22 10:00:00",
    "started_at": "2026-07-22 10:00:01",
    "completed_at": "2026-07-22 10:00:30",
    "error_msg": ""
  }
}
```

**status 取值：** `pending` / `processing` / `completed` / `failed`

---

### 2.6 获取最终评估结果

- **方法**：GET
- **URL**：`/api/get_final_result/{task_id}`

**状态码：**
- 200：成功获取结果
- 202：任务正在处理中
- 404：任务不存在
- 500：任务失败

**WER 响应示例：**
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "task_id": "task_123",
    "status": "completed",
    "task_type": "wer",
    "result": {
      "wer": 0.25,
      "errors": 1,
      "length": 4,
      "insertions": 0,
      "deletions": 0,
      "substitutions": 1
    },
    "completed_at": "2026-07-22 10:00:02"
  }
}
```

**xiaoyi_metrics 响应示例：**
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "task_id": "task_456",
    "status": "completed",
    "task_type": "xiaoyi_metrics",
    "result": {
      "tor": {
        "per_pause": [0, 1],
        "takeover_count": 1,
        "total_pauses": 2,
        "tor": 0.5
      },
      "false_takeover": {
        "tor": 0,
        "n_words": 0,
        "duration": 0.0,
        "total_pauses": 2,
        "hit_words": [],
        "details": [...]
      },
      "takeover_latency": {
        "takeover_latency_ms": 350,
        "first_frame_ms": 1700000000000,
        "first_word_begin_ms": 150,
        "model_first_word_ms": 1700000000150,
        "end_ms": 1700000005000,
        "offset_ms": 40,
        "audio_end_with_offset_ms": 1700000005040,
        "message": "OK"
      }
    },
    "completed_at": "2026-07-22 10:00:30"
  }
}
```

---

## 3. 分布式调度

### 3.1 配置远程端点

```bash
curl -X POST http://localhost:5001/api/endpoints \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://localhost:5002",
    "name": "worker-1",
    "capabilities": {"wer": {"max_process": 5}}
  }'
```

### 3.2 创建分布式任务

在 `create_task` 请求中传入 `endpoints` 参数：

```json
{
  "task_type": "wer",
  "asr_ref": "今天天气不错",
  "asr_result": "今天天气不措",
  "endpoints": [{"endpoint": "http://localhost:5002"}]
}
```

### 3.3 动态调整并发

```bash
curl -X PUT "http://localhost:5001/api/endpoints/http://localhost:5002/concurrency/wer" \
  -H "Content-Type: application/json" \
  -d '{"max_process": 10}'
```

### 3.4 查看并发状态

```bash
curl http://localhost:5001/api/status
```

---

## 4. 错误码

| 错误码 | 描述 | HTTP 状态码 |
|--------|------|-------------|
| 0 | 成功 | 200 |
| 3000 | 业务逻辑错误（任务不存在、状态异常） | 400 |
| 3001 | 并发已满 | 429 |
| 4000 | 参数验证错误 | 400 |
| 5000 | 服务器内部错误 | 500 |

---

## 5. 版本信息

- **版本**：2.0.0
- **更新日期**：2026-07-22
- **更新内容**：
  - 新增 llm_judge 任务类型（LLM 语义评分）
  - 新增 xiaoyi_metrics 任务类型（tor + false_takeover + takeover_latency）
  - 新增 `/api/create_task_upload` 接口支持 multipart 文件上传
  - ASR 结果通过返回值传递，不读写中间 JSON 文件
  - 三个小艺子指标共享一次 ASR 推理结果
