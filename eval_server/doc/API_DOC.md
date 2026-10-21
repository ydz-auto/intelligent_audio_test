# eval_server API 接口文档

## 1. 服务概述

音频评估维度计算服务，支持 WER、SER、CPWER、TCPWER、STM_WER、DER、小艺指标（xiaoyi_metrics / turn_taking / turn_eval / interruption_metrics / non_interactive_latency / noise_latency / env_judge / reject_judge）的计算。服务采用异步任务处理模式，支持并发控制、排队执行、事件化回调、分布式调度、文件上传和动态配置。

### 1.1 基础信息

- 服务名称：evaluation-dimension-service
- 基础URL：`http://localhost:{port}`
- 默认端口：8888（config.yaml `port` 配置，启动可用 `--port` 覆盖）
- 支持的请求格式：JSON / multipart/form-data
- 认证方式：无（开发环境）

### 1.2 支持的任务类型

| task_type | 说明 | 必填字段 | 请求方式 |
|-----------|------|---------|---------|
| wer | 词错误率 | asr_ref, asr_hyp | JSON |
| ser | 句错误率 | asr_ref, asr_hyp | JSON |
| cpwer | 连接词错误率 | ref_stm, hyp_stm | JSON |
| tcpwer | 时间约束词错误率 | ref_stm, hyp_stm | JSON |
| stm_wer | 基于 STM 的 WER | ref_stm, hyp_stm | JSON |
| der | 说话人分离错误率 | rttm_ref, stm_ref, rttm_hyp, stm_hyp（旧名 rttm_res/stm_res 兼容） | JSON |
| xiaoyi_metrics | 小艺全域编排（统一共享 ASR + 跨域聚合） | user_wav / ai_wav 至少一个 | JSON / multipart |
| turn_taking | 话轮接管（tor + false_takeover + takeover_latency + reply_quality + high_freq_*） | user_wav / ai_wav | JSON / multipart |
| tor | 接话率 | user_wav, ai_wav | JSON |
| false_takeover | 误接管率 | ai_wav | JSON |
| takeover_latency | 接管时延 | user_wav, ai_wav | JSON |
| high_freq_turn_taking | 高频轮换每轮回复时延 | user_wav, ai_wav | JSON |
| high_freq_llm_judge | 高频轮换 LLM 裁判 | ai_wav + rounds | JSON |
| reply_quality | 单轮回复质量 LLM 评分 | ai_wav | JSON |
| turn_eval | 逐轮三分类（误解管/接管/未接管）+ 接管时延 + 回复质量 | user_wav / ai_wav | JSON |
| interruption_metrics | 打断指标 v2（用例类型 + 行为数量 + 响应/回复时延 + LLM 评分/停止遵从） | rounds[]（逐轮 user_asr/model_asr 或双路 wav） | JSON |
| non_interactive_latency | 非交互意图时延 | user_wav, ai_wav | JSON |
| noise_latency | 噪声打断时延 | ai_wav, start_ms, end_ms, pcm_first_ms | JSON |
| env_judge | 环境理解裁判 | user_wav, ai_wav, played_audios, correctAnswer | JSON |
| reject_judge | 拒识裁判（行为分类 + rate 评级） | ai_wav | JSON |

> `supported_task_types` 由注册表动态生成（`app/services/calculators/__init__.py`），新增 Calculator 自动出现在 `/health` 中。

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
  "supported_task_types": ["wer", "ser", "cpwer", "tcpwer", "stm_wer", "der", "xiaoyi_metrics", "turn_taking", "tor", "false_takeover", "takeover_latency", "high_freq_turn_taking", "high_freq_llm_judge", "reply_quality", "turn_eval", "interruption_metrics", "non_interactive_latency", "noise_latency", "env_judge", "reject_judge"],
  "concurrency": {
    "wer": {"max_concurrency": 100, "current_concurrency": 2, "available": 98}
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
| task_id | string | 否 | 调用方任务 ID（回显用） |
| callback_url | string | 否 | 完成/失败后事件化回调 URL（替代轮询），失败指数退避重试 3 次 |
| normalize | bool | 否 | 是否文本正则化，默认 false |
| source_lang | string | 否 | 源语言（wer/ser 文本归一化用） |
| target_lang | string | 否 | 目标语言 |
| translate_direct | string | 否 | 翻译方向（兼容 `translation_direction` 命名） |
| collar | float | 否 | tcpwer 时间约束（秒），默认 0.0；der 默认 0.5 |
| skip_overlap | bool | 否 | 是否跳过重叠区（der 用），默认 false |

> 除 `task_type` / `endpoints` / `task_id` 外的其余字段全部透传为 `task_params`，
> 各 Calculator 的 `validate()` 负责校验；`rounds[]` 多轮模式下 WER 系列会把同名扁平字段按轮拼接为单条文本。

**WER/SER 请求示例：**
```json
{
  "task_type": "wer",
  "asr_ref": "今天天气不错",
  "asr_hyp": "今天天气不措",
  "source_lang": "zh"
}
```

**CPWER/TCPWER/STM_WER 请求示例：**
```json
{
  "task_type": "cpwer",
  "ref_stm": "file1 1 speakerA 0.0 1.0 <o> hello world",
  "hyp_stm": "file1 1 speakerA 0.0 1.0 <o> hello word"
}
```

**DER 请求示例：**
```json
{
  "task_type": "der",
  "rttm_ref": {"json": [{"speaker": "spk1", "start": 0.0, "duration": 1.0}]},
  "stm_ref": {"json": [{"file_id": "rec1", "channel": "1", "speaker": "spk1", "start": 0.0, "end": 1.0, "text": "hello"}]},
  "rttm_hyp": {"json": [{"speaker": "spk1", "start": 0.0, "duration": 1.0}]},
  "stm_hyp": {"json": [{"file_id": "rec1", "channel": "1", "speaker": "spk1", "start": 0.0, "end": 1.0, "text": "hello"}]}
}
```

**turn_taking 请求示例（域内编排，双路音频路径或 rounds[]）：**
```json
{
  "task_type": "turn_taking",
  "user_wav": "/path/to/cap_client_process_out.wav",
  "ai_wav": "/path/to/cap_client_ec_out.wav",
  "sub_tasks": ["tor", "false_takeover", "takeover_latency", "reply_quality"]
}
```

**turn_eval 请求示例（逐轮三分类）：**
```json
{
  "task_type": "turn_eval",
  "rounds": [
    {
      "query": "帮我订一张明天的机票",
      "user_wav": "/path/to/round0_user.wav",
      "ai_wav": "/path/to/round0_ai.wav",
      "played_audios": [{"audio_path": "/path/to/round0_user_clean.wav"}]
    },
    {
      "query": "那后天呢",
      "user_wav": "/path/to/round1_user.wav",
      "ai_wav": "/path/to/round1_ai.wav"
    }
  ]
}
```

**interruption_metrics 请求示例（v2：rounds 逐轮标记，兼容单轮平铺 user_asr/model_asr）：**
```json
{
  "task_type": "interruption_metrics",
  "interruption_rounds": [1],
  "rounds": [
    {
      "is_interruption": true,
      "query": "打断一下",
      "user_asr": [{"text": "打断一下", "timestamp": [3.6, 4.0]}],
      "model_asr": [{"text": "回答中", "timestamp": [2.5, 3.8]}, {"text": "怎么了", "timestamp": [4.8, 5.4]}],
      "played_audios": ["case1_round1_user.wav"]
    },
    {
      "is_return_to_topic": true,
      "query": "回到刚才的话题",
      "user_asr": [{"text": "回到刚才的话题", "timestamp": [6.0, 6.8]}],
      "model_asr": [{"text": "好的继续", "timestamp": [7.2, 8.0]}]
    }
  ]
}
```

**reject_judge 请求示例（拒识裁判）：**
```json
{
  "task_type": "reject_judge",
  "ai_wav": "/path/to/model_reply.wav",
  "user_wav": "/path/to/user_channel.wav",
  "rounds": [
    {"is_reject": true, "ai_wav": "/path/to/r0_ai.wav", "user_wav": "/path/to/r0_user.wav", "timing": "回复过程中"},
    {"is_reject": false, "ai_wav": "/path/to/r1_ai.wav", "user_wav": "/path/to/r1_user.wav"}
  ]
}
```

**env_judge 请求示例（环境理解）：**
```json
{
  "task_type": "env_judge",
  "ai_wav": "/path/to/model_reply.wav",
  "user_wav": "/path/to/user_channel.wav",
  "played_audios": [{"audio_path": "/path/to/doorbell.wav"}],
  "correctAnswer": "门铃",
  "env_type": 0,
  "model": "qwen-omni"
}
```

**non_interactive_latency 请求示例：**
```json
{
  "task_type": "non_interactive_latency",
  "user_wav": "/path/to/user.wav",
  "ai_wav": "/path/to/model.wav"
}
```

**noise_latency 请求示例：**
```json
{
  "task_type": "noise_latency",
  "ai_wav": "/path/to/model.wav",
  "start_ms": 500,
  "end_ms": 1500,
  "pcm_first_ms": 100
}
```

#### played_audios（被播放音频）约定

小艺类指标（turn_taking / turn_eval / interruption_metrics / env_judge / xiaoyi_metrics）的 `played_audios` 表示**本轮被设备播放的干净音源**（环境声 / 用户问题原音），用于 FFT 互相关对齐精修：

- **取值形态**（三选一，`_resolve_played_audio_path` 统一解析）：
  - `list[dict]`：`[{"audio_path": "/path/to/xxx.wav"}, ...]`（平台主服务下发的主流形态）
  - 单个 dict / 纯字符串路径
- **对齐链路**：`shared/audio_alignment.generate_aligned_clean_audio(user_wav, played_audios)` 把干净音源 FFT 互相关对齐到劣化录制的 user_wav，生成干净版音频 + 对齐段（`segments`，含 `source` / `offset_s` / `clean_duration_s`）
- **用途**：
  - `takeover_latency` / `false_takeover`：用对齐结果精修用户段边界，时延更准
  - `turn_eval` 多轮合并：按对齐段 `source` 文件名归属 turn 到真实轮次
  - `interruption_metrics`：FFT 定位每轮用户窗口（`locate_fft_window`）
  - `env_judge`：定位环境声在 user_wav 中的起止时间戳
- **multipart 上传**：`rounds[i].played_audios` 内部可用 `__MULTIPART__:field_name` 占位符，`create_task_upload` 递归还原为落盘路径

---

### 2.3 创建评估任务（文件上传）

- **方法**：POST
- **URL**：`/api/create_task_upload`
- **Content-Type**：multipart/form-data

用于需要上传音频/视频文件的任务。文件字段会被提取为 multipart 上传：

- **文本文件**（.txt/.stm/.rttm/.json/.csv/.srt/.vtt/.xml/.tsv）：读取内容为字符串
- **二进制文件**（.wav/.mp4 等）：保存到上传目录，task_params 中使用文件路径
- `rounds` / `played_audios` 等 JSON 字符串字段中可用 `__MULTIPART__:field_name` 占位符，eval_server 收到后保存文件并**递归还原**占位符为实际路径（任意嵌套层级，如 `rounds_0_played_audios_0_audio_path`）

**上传处理流程：**

1. 表单字段（除 `task_type` / `endpoints` / `task_id`）全部写入 `task_params`（multipart 标量均为字符串）
2. 文件字段按扩展名分类：文本 → 内容字符串；二进制 → 保存到 `UPLOAD_DIR/{storage_id}/`，路径写入 `task_params`
3. `rounds` 字段若是 JSON 字符串则解析为 list，并递归还原内部 `__MULTIPART__` 占位符
4. 顶层其他 JSON 字符串字段（如 `played_audios`）同样解析并还原占位符后回写
5. **小艺类任务**（xiaoyi_metrics / turn_taking / takeover_latency / interruption_metrics / env_judge）：把 `rounds` 最后一轮的字段（`record_file` / `user_wav` / `ai_wav` / `played_audios` / `pause` / `first_frame_ms` / `start_ms` / `input` / `input_lastword` / `offset_ms` / `correctAnswer` / `env_type`）提升到顶层，供校验与计算取值

**turn_taking 请求示例：**

```bash
curl -X POST http://localhost:8888/api/create_task_upload \
  -F "task_type=turn_taking" \
  -F "user_wav=@cap_client_process_out.wav" \
  -F "ai_wav=@cap_client_ec_out.wav"
```

**turn_taking 参数说明：**

| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| task_type | string | 是 | 固定为 `turn_taking`（或其他支持文件的任务类型） |
| user_wav | file | 否 | 用户通道 wav 录音（multipart 上传） |
| ai_wav | file | 否 | AI 回复通道 wav 录音（multipart 上传） |
| rounds | string | 否 | JSON 字符串形式的多轮数据（内部可含 `__MULTIPART__` 占位符） |

---

### 2.4 创建任务响应

所有创建任务的响应格式统一：

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "eval_task_id": "task_abc123",
    "task_id": "caller_task_id",
    "status_url": "http://localhost:8888/api/get_status/task_abc123",
    "final_result_url": "http://localhost:8888/api/get_final_result/task_abc123",
    "task_type": "wer",
    "msg": "任务已创建，正在本地处理"
  }
}
```

**并发已满（排队）时**，响应多一个 `queued: true` 字段，任务进入 pending 队列由后台 worker 按限制排队执行：

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "eval_task_id": "task_abc123",
    "task_id": "caller_task_id",
    "status_url": "http://localhost:8888/api/get_status/task_abc123",
    "final_result_url": "http://localhost:8888/api/get_final_result/task_abc123",
    "task_type": "wer",
    "queued": true,
    "msg": "评估全局并发(100)已满，任务已进入排队等待"
  }
}
```

---

### 2.5 获取任务状态

- **方法**：GET
- **URL**：`/api/get_status/{eval_task_id}`

**响应示例：**
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "eval_task_id": "task_1234567890",
    "task_id": "caller_task_id",
    "status": "completed",
    "task_type": "wer",
    "created_at": "2026-07-22 10:00:00",
    "started_at": "2026-07-22 10:00:01",
    "completed_at": "2026-07-22 10:00:30",
    "error_msg": ""
  }
}
```

**status 取值：** `pending`（排队中） / `processing` / `completed` / `failed` / `canceled`（已取消）

---

### 2.6 获取最终评估结果

- **方法**：GET
- **URL**：`/api/get_final_result/{eval_task_id}`

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
    "eval_task_id": "task_123",
    "task_id": "caller_task_id",
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

**turn_taking 响应示例：**
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "eval_task_id": "task_456",
    "status": "completed",
    "task_type": "turn_taking",
    "result": {
      "tor": {"tor": 1, "n_words": 1, "duration": 1.0, "user_last_word_end_s": 3.2, "message": "OK"},
      "false_takeover": {"tor": 0, "n_words": 0, "duration": 0.0, "llm_eval": {"false_takeover": 0, "reason": "..."}},
      "takeover_latency": {"takeover_latency_ms": 350, "user_last_word_end_ms": 3200, "ai_first_word_start_ms": 3550, "message": "OK"},
      "reply_quality": {"score": 4.5, "reason": "..."},
      "interaction_text": "query [0:03; 0:03]...\nanswer [0:03; 0:04]...\n"
    },
    "completed_at": "2026-07-22 10:00:30"
  }
}
```

> 若 `false_takeover.tor == 1`（检测到抢话），`tor` 与 `takeover_latency` 置 null（不适用）。

**turn_eval 响应示例：**
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "eval_task_id": "task_789",
    "status": "completed",
    "task_type": "turn_eval",
    "result": {
      "turn_classification": {
        "summary": "正常接管2，未接管1，误解管0",
        "normal_takeover_count": 2, "no_takeover_count": 1, "false_takeover_count": 0,
        "total_turns": 3,
        "takeover_rate": 0.6667, "no_takeover_rate": 0.3333, "false_takeover_rate": 0.0,
        "turns": [
          {"turn_index": 0, "round_number": 0, "classification": "TAKEOVER", "takeover_latency_ms": 320, "reply_quality": {"score": 4.5}, "user_start_s": 0.5, "user_end_s": 2.1, "ai_start_s": 2.5, "ai_end_s": 4.0}
        ]
      },
      "tor": {"tor": 1, "message": "OK"},
      "false_takeover": {"tor": 0, "reason": "..."},
      "takeover_latency": {"takeover_latency_ms": 320, "takeover_latency_avg_ms": 340.5},
      "reply_quality": {"score": 4.5, "reply_quality_avg_score": 4.3},
      "interaction_text": "...",
      "per_round": [{"round_number": 0, "turn_classification": {"summary": "...", "normal_takeover_count": 2, "..."}, "tor": {"..."}, "false_takeover": {"..."}, "takeover_latency": {"..."}, "reply_quality": {"..."}}]
    },
    "completed_at": "2026-07-22 10:00:30"
  }
}
```

**interruption_metrics 响应示例（v2，节选；结果包装在 `interruption` 键下）：**
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "eval_task_id": "task_321",
    "task_type": "interruption_metrics",
    "result": {
      "interruption": {
        "case_type": "topic_resume_single",
        "success_count": 1, "failure_count": 0, "inquiry_count": 0,
        "response_latency_avg_ms": 320.0, "reply_latency_avg_ms": 850.0,
        "round_details": [{"round": 1, "behavior": "回复", "response_latency_ms": 320.0, "...": "..."}]
      },
      "per_round": [
        {"round_number": 0, "message": "跳过: 非计时轮(无打断时序)"},
        {"round_number": 1, "interruption": {"success_count": 1, "failure_count": 0, "inquiry_count": 0,
         "response_latency_avg_ms": 320.0, "reply_latency_avg_ms": 850.0, "reply_content_score": 4.5}}
      ]
    }
  }
}
```

`per_round[]` 位于 result 顶层（与维度包 `interruption` 同级，整体评估返回逐轮结果方案 §4.2），为逐轮投影（`build_per_round`，零额外 LLM 调用；TaskService 检测到原生产出即跳过默认逐轮切片重跑）：每轮元素带 `round_number`，字段名与整体 spec 同名，平台按维度 field_path（`interruption.*`）提取后覆盖逐轮 TestResultDimension；无时序/LLM 降级的轮为 `{round_number, message}` 跳过项，平台不覆盖。用例级字段（case_type/行为计数/聚合值）不投影。

**reject_judge 响应示例：**
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "eval_task_id": "task_654",
    "status": "completed",
    "task_type": "reject_judge",
    "result": {
      "rate": "拒识成功",
      "rate_success": 1, "rate_inquiry": 0, "rate_failure": 0,
      "behavior_respond": 0, "behavior_recover": 1,
      "behavior_uncertain": 0, "behavior_irrelevant": 0, "behavior_silent": 0,
      "n_reject_rounds": 2,
      "n_rate_success": 2, "n_rate_inquiry": 0, "n_rate_failure": 0,
      "per_round": [
        {"round_number": 0, "rate_success": 1, "n_rate_success": 1, "...": "..."},
        {"round_number": 1, "rate_success": 1, "n_rate_success": 1, "...": "..."}
      ],
      "message": "OK"
    }
  }
}
```

---

### 2.7 删除任务

- **方法**：DELETE
- **URL**：`/api/delete_task/{eval_task_id}`
- **说明**：删除任务及其结果文件

### 2.8 取消任务

- **方法**：DELETE
- **URL**：`/api/cancel_task/{eval_task_id}`
- **说明**：标记为 canceled（不删除文件）。排队中任务后台不再启动；计算中任务完成后跳过写结果与回调。幂等。

### 2.9 并发状态查询

- **方法**：GET
- **URL**：`/api/status`

返回本地全局并发、各维度并发、各远程端点并发：

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "local": {"max_concurrency": 100, "current_concurrency": 2, "available_concurrency": 98},
    "dimension": {"wer": {"max": 100, "current": 2, "available": 98}},
    "worker_concurrency": {"http://localhost:5002": {"current": 0, "max": 1, "available": 1, "by_task_type": {}}}
  }
}
```

---

## 3. 分布式调度

### 3.1 配置远程端点

```bash
curl -X POST http://localhost:8888/api/endpoints \
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
  "asr_hyp": "今天天气不措",
  "endpoints": [{"endpoint": "http://localhost:5002"}]
}
```

### 3.3 动态调整并发

```bash
curl -X PUT "http://localhost:8888/api/endpoints/http://localhost:5002/concurrency/wer" \
  -H "Content-Type: application/json" \
  -d '{"max_process": 10}'
```

### 3.4 端点管理

| 方法 | URL | 说明 |
|------|-----|------|
| GET | `/api/endpoints` | 列出所有端点 |
| POST | `/api/endpoints` | 创建端点 |
| GET | `/api/endpoints/{url}` | 获取端点详情 |
| PUT | `/api/endpoints/{url}` | 更新端点 |
| DELETE | `/api/endpoints/{url}` | 删除端点 |

---

## 4. 错误码

| 错误码 | 描述 | HTTP 状态码 |
|--------|------|-------------|
| 0 | 成功 | 200 |
| 3000 | 业务逻辑错误（任务不存在、状态异常） | 400 |
| 3001 | 并发已满 | 429 |
| 4000 | 参数验证错误 | 400 |
| 5000 | 服务器内部错误 | 500 |

> 任务创建时并发满**不再返回 3001**，而是创建为 pending 排队任务（响应带 `queued: true`），由后台 worker 按限制排队执行。

---

## 5. 版本信息

- **版本**：3.1.0
- **更新日期**：2026-10-14
- **更新内容**：
  - 重构为策略模式 + 注册表架构，`calculate()` 和 `api.py` 不再需要 if-elif 链
  - 新增 `BaseCalculator` 基类，统一 `validate → prepare_params → calculate` 模板方法 + 单轮/多轮公共方法
  - 按域分子包：wer / der / xiaoyi_metrics（shared / turn_taking / turn_eval / interruptibility / rejection_scene_awareness / env_judge）
  - 新增 task_type：`xiaoyi_metrics`（全域编排）、`turn_eval`（逐轮三分类）、`reply_quality`（回复质量评分）、`high_freq_turn_taking` / `high_freq_llm_judge`（高频轮换）、`reject_judge`（拒识裁判）；`interruption_judge` 并入 interruption_metrics v2（进程内直调裁判）
  - 新增 `/api/create_task_upload` 接口支持 multipart 文件上传 + `__MULTIPART__` 占位符递归还原
  - 新增 `/api/delete_task` / `/api/cancel_task` / `/api/endpoints` 增删改查 / `callback_url` 事件化回调
  - 并发满自动排队（后台 worker 消费），不再 429 拒绝
  - LLM 统一入口 `shared/llm_client.py:call_llm` + JSONL 审计日志；OSS `oss://` 路径下载支持
  - 配置迁移为 config.yaml（结构）+ .env（密钥/覆盖），默认端口 8888
  - ASR 结果通过返回值传递，不读写中间 JSON 文件
