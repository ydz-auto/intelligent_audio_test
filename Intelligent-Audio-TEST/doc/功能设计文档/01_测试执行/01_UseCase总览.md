# UseCase 总览

> 版本：v3.0 | 日期：2026-09-10 | 状态：最终方案

---

## 0.1 核心模型：用例无关执行方式

> **核心原则**：用例是纯数据（`case_config` + `algorithm_params`），不区分类型。
> 被测设备类型决定执行方式。一个任务里可以混跑 E2E + API + Realtime。

```
用例 (TestCase)
  ├── case_config (JSON)     ← 纯数据，不绑定执行方式
  └── algorithm_params (独立列)

任务 (Task)
  ├── 关联用例 (TaskCase[])  ← 每个 TaskCase 关联一个被测设备
  └── 被测设备 (TaskDevice[]) ← 设备类型决定执行方式
         │
         ├── 物理设备（音箱/手机）→ E2EExecutor
         ├── HTTP API            → APISessionExecutor (HttpAPIAdapter/HttpStreamAdapter)
         └── WebSocket API       → RealtimeSessionExecutor (RealtimeAPIAdapter)
```

**用户操作流程**：
1. 导入音频 → 生成用例（`case_config` + `algorithm_params`），不选类型
2. 创建任务 → 关联用例 + 关联被测设备（可同时选物理设备 + 多个 API）
3. 执行 → 每个 TaskCase 按其关联的被测设备类型路由到对应 executor

**一个任务混跑示例**：
```
Task "全量回归"
  ├── TaskCase #1: 用例A × 设备(小翼音箱)   → E2EExecutor
  ├── TaskCase #2: 用例A × 设备(ChatGPT RT) → RealtimeSessionExecutor
  ├── TaskCase #3: 用例B × 设备(通义千问)   → APISessionExecutor
  └── TaskCase #4: 用例B × 设备(小翼音箱)   → E2EExecutor
```

## 0.2 调用模式（流式 vs 非实时）

> API 类被测设备支持流式和非实时两种调用模式，由 `case_config.stream` 或 API 配置决定。
> **流式 ≠ 只有 WebSocket**：HTTP 流式（SSE）也是流式协议之一，由 `case_config.protocol` 区分。

| 调用模式 | 协议 | 说明 | 输入 | 输出 | AI 说话检测 | 打断检测 |
|---|---|---|---|---|---|---|
| **非实时调用** | HTTP POST | 一次性发送完整音频，等完整响应 | 文件级 | 完整 JSON | HTTP 响应判断 | 不支持 |
| **流式调用** | SSE | HTTP 长连接，服务端逐条推送结果 | chunk 流式 | chunk 流式 | 事件驱动 | 支持 |
| **流式调用** | WebSocket | 全双工实时语音交互 | chunk 流式 | chunk 流式 | 事件驱动 | 支持 |

## 0.3 被测设备类型 × 执行方式

| 被测设备类型 | 协议 | Executor | 音频处理 | SPL 映射 | 调用模式 |
|:---:|:---:|---|---|---|---|
| 物理设备 | — | E2EExecutor | 物理播放 + PCM 抓取 | `device.spl_mapping_id` | — |
| HTTP API（非实时） | HTTP | APISessionExecutor | RenderAudioFile 整段混音 → 整文件 → POST | `api.rms_spl_mapping_id` | 非实时 |
| HTTP API（流式） | SSE | APISessionExecutor | RenderAudioStream 逐帧混音 → chunk → SSE 推送 | `api.rms_spl_mapping_id` | 流式 |
| WebSocket API | WebSocket | RealtimeSessionExecutor | RenderAudioStream 逐帧混音 → chunk → WS 全双工 | `api.rms_spl_mapping_id` | 流式 |

## 0.4 用例结构

> **核心原则**：用例只有一份结构，不区分 E2E/API/Realtime。
> 设备相关字段（`playback_device_id`、`device_ids`）在非 E2E 执行时被忽略。

```
case_config (TestCase.config 列，JSON)
├── rounds: [                          ← 多轮配置列表
│   {
│     ├── round_number: int            ← 轮次序号 (1-indexed)
│     ├── audios: [                    ← 本轮音频配置
│     │   {
│     │     ├── audio_id: string|int
│     │     ├── audio_name: string
│     │     ├── spl: float             ← 目标声压级 (可选, 不设则 gain=1.0)
│     │     ├── playback_device_id: string|int  ← E2E 用; API 类忽略
│     │     ├── play_order: int
│     │   }
│     │ ]
│     ├── background_noise: {          ← 轮次级背景噪声 (可选)
│     │   ├── audio_id / audio_name
│     │   ├── spl: float
│     │   ├── device_ids: [...]        ← E2E 用; API 类忽略
│     │   └── loop: bool
│     │ }
│     ├── evaluation: { enabled, dimensions[] }  ← 单轮评估配置
│     ├── is_interruption: bool        ← 打断标记轮
│     ├── stop_intent: bool            ← 停止指令标记
│     └── interferers: [               ← 干扰人列表 (通用)
│         { audio_id, spl, startDelay, loop }
│     ]
│   }
│ ]
├── dimensions: [                      ← 整体评估维度 (多轮聚合)
│   { id, name, weight, threshold }
│ ]
├── background_noise: {                ← case 级全局背景噪声 (跨所有轮次)
│   (同轮次级结构)
│ }
├── voiceprint_config: { enabled, audio, device, spl, waitTime }
├── algorithm_type: string             ← translation/asr/tts/voice_llm/...
├── original_topic: string             ← 打断测试原始话题
├── translation_direction: string      ← 翻译方向
├── source_language / target_language: string
└── [extra]: any                       ← extra='allow' 透传

独立列 (运行时合并为 case_config):
  test_cases.algorithm_params: [{ round_number, params: [{field_code, field_value}] }]
  test_cases.reference_params: [{ round_number, reference_params_path }]
```

**字段在不同执行方式下的使用情况**：

| 字段 | E2E | HTTP API | WebSocket API | 说明 |
|------|:---:|:---:|:---:|------|
| `audios[].spl` | ✓ | ✓ | ✓ | 完全相同，目标声压级 dB SPL |
| `audios[].playback_device_id` | ✓ | 忽略 | 忽略 | 仅 E2E 用 |
| `background_noise.device_ids` | ✓ | 忽略 | 忽略 | 仅 E2E 用 |
| `interferers[].startDelay` | ✓ | ✓ | ✓ | 完全相同 |
| `interferers[].spl` | ✓ | ✓ | ✓ | 完全相同 |
| `is_interruption` | ✓ | 不支持 | ✓ | HTTP 不支持 barge-in |
| `stop_intent` | ✓ | ✓ | ✓ | 完全相同 |
| `evaluation.dimensions` | ✓ | ✓ | ✓ | 完全相同 |
| `algorithm_params` | ✓ | ✓ | ✓ | 完全相同，独立列存储 |
| `voiceprint_config` | ✓ | ✓ | ✓ | 完全相同 |

## 0.4 被测 API 配置（音频参数 + adapter 选择）

> 被测 API 表（`API`）需要扩展音频参数和 adapter 选择字段。
> adapter 选择决定走哪个适配器类，音频参数决定 chunk 格式。

```json
// API 表配置示例
{
  "id": 1,
  "name": "ChatGPT Realtime",
  "vendor": "openai",
  "protocol": "websocket",
  "adapter_class": "OpenAIRealtimeAdapter",
  "rms_spl_mapping_id": 3,

  "audio_config": {
    "sample_rate": 24000,
    "bit_depth": 16,
    "channels": 1,
    "format": "pcm",
    "chunk_duration_ms": 100
  },

  "output_types": ["audio", "text"],

  "endpoints": [
    {"url": "wss://api.openai.com/v1/realtime", "priority": 1, "status": "online"}
  ]
}
```

**字段说明**：

| 字段 | 说明 | 取值 |
|------|------|------|
| `vendor` | 厂商标识 | `openai` / `volc` / `qwen` / `doubao` / ... |
| `protocol` | 传输协议 | `websocket` / `http` |
| `adapter_class` | 指定 adapter 类名 | `OpenAIRealtimeAdapter` / `HttpAPIAdapter` / `HttpStreamAdapter` / ... |
| `audio_config.sample_rate` | 采样率 | 8000 / 16000 / 24000 / 48000 |
| `audio_config.bit_depth` | 位深 | 8 / 16 / 24 / 32 |
| `audio_config.channels` | 通道数 | 1（单声道）/ 2（立体声） |
| `audio_config.format` | 音频格式 | `pcm` / `wav` / `mp3` / `opus` |
| `audio_config.chunk_duration_ms` | chunk 时长 | 20 / 40 / 100（默认 100） |
| `output_types` | API 输出类型列表 | `["audio", "text", "video", "image"]` 的子集 |

> **adapter 选择逻辑**：`APIAdapterFactory.get_adapter()` 优先按 `adapter_class` 指定类名创建，
> 未指定时按 `(protocol, vendor)` 自动匹配。

## 0.5 多模态输出

> API 和 Realtime API 的输出不只有音频，还可能是文本、视频、图片等。
> adapter 统一采集所有输出类型，executor 聚合后提交评估。

| 输出类型 | 来源 | adapter 采集 | 评估用途 |
|----------|------|-------------|----------|
| `audio` | AI 语音回复 | `adapter.ai_audio` (PCM chunks 拼接) | 语音质量 / 抢话 / 打断检测 |
| `text` | AI 文本回复 | `adapter.ai_text` (累积拼接) | 语义评估 / 翻译准确率 |
| `video` | AI 视频回复 | `adapter.ai_video_chunks` (视频帧序列) | 视频质量 / 表情评估 |
| `image` | AI 图片回复 | `adapter.ai_images` (图片 URL/base64 列表) | 图片质量 / 内容识别 |

**adapter 输出数据结构**：

```python
# BaseAPIAdapter 统一输出属性
class AdapterOutput:
    audio: bytes          # AI 音频 PCM（多 chunk 拼接）
    text: str             # AI 文本（多 token 累积）
    video_chunks: list    # AI 视频帧列表
    images: list          # AI 图片列表（URL 或 base64）
    event_log: list       # 事件时间线（用于延迟分析）
    latency_ms: int       # 首帧/首 token 延迟
```

**不同 adapter 支持的输出类型**：

| adapter | audio | text | video | image |
|---------|:---:|:---:|:---:|:---:|
| HttpAPIAdapter | — | ✓ | — | ✓ |
| HttpStreamAdapter | ✓ | ✓ | ✓ | ✓ |
| RealtimeAPIAdapter | ✓ | ✓ | ✓ | ✓ |

> 非实时 HTTP 调用通常是"发音频→收文本/图片"，无音频输出；
> 流式和全双工可以输出任意类型。

## 0.6 SPL 处理逻辑（三种情况）

> **关键**：用户在用例 `case_config.rounds[].audios[]` 里配的是**目标声压级（dB SPL）**，不是 RMS。
> 系统通过 SPL 映射把目标声压级转成数字增益，再应用到音频 RMS 上。
> 音频导入时不涉及 SPL，`Audio` 表无 SPL 字段。

```
用例 round.audios[] 配置了 spl（目标声压级 dB SPL）？
  │
  ├── 否 → gain=1.0，原始 RMS 不变，直接切 chunk 推送
  │        （不经过 RMS 补偿和 SPL 增益）
  │
  └── 是 → 查 SPL 映射（把目标声压级 → 数字增益 gain）
           │
           ├── task.type=e2e → SPLMappingService.spl_to_gain(device, spl)
           │                   → 物理设备声压校准（DB 查 SPLMapping）
           │
           └── task.type=http_api / realtime_api
                → ApiRmsSplService.spl_to_gain(api_id, spl)
                → 被测 API 灵敏度校准（DB 查 ApiRmsSplMapping）
                → gain × 原始 RMS = 目标声压
                → AudioStreamOrchestrator.route() 分发
                → 非实时: RenderAudioFile 整段混音 → 整文件
                → 流式/Realtime: RenderAudioStream 逐帧混音 → chunk
```

## 0.7 执行路由总流程图

```
           用户创建任务（选关联用例 + 被测设备）
                              │
                              ▼
                   for each TaskCase:
                              │
                              ▼
              TaskCase 关联的被测设备类型？
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
     物理设备             HTTP API           WebSocket API
          │                   │                   │
          ▼                   ▼                   ▼
  E2EExecutor         APISessionExecutor  RealtimeSessionExecutor
          │                   │                   │
  ┌───────────────┐   ┌──────┴──────┐            │
  │ 物理播放+PCM   │   │ 调用模式?    │            │
  │ SPLMappingService│  ├── 非实时   │            │
  │ 查 device      │  │  → HttpAPIAdapter         │
  │                │  │  → RenderAudioFile        │
  │ audio_driver   │  │    整段混音 → 整文件      │
  │ callback 混音  │  │  → 整文件 HTTP POST       │
  │                │  │  → 等完整 JSON            │
  │ device_driver  │  │  → 输出: text/image       │
  │ AI说话检测(PCM │  │                           │
  │ RMS 轮询)      │  └── 流式                    │
  │                │      → HttpStreamAdapter     │
  │ 录屏+UI检测    │      → RenderAudioStream     │
  └───────────────┘      │   逐帧混音 → chunk     │
                         │      → chunk → SSE     │
                         │      → 实时输入/输出    │
                         │      → 输出: audio/text/│
                         │                         │
                                          ┌───────┴───────────────┐
                                          │ APIAdapterFactory      │
                                          │   .get_adapter()       │
                                          │   → RealtimeAPIAdapter │
                                          │                        │
                                          │ adapter.initialize()   │
                                          │   → WS 连接 + recv 线程│
                                          │                        │
                                          │ adapter.pre_process()  │
                                          │   → session.update()   │
                                          │                        │
                                          │ for each round:        │
                                          │   ├── 合并噪声配置      │
                                          │   │  (轮次级>全局)      │
                                          │   ├── RenderAudioStream │
                                          │   │   逐帧流式混音       │
                                          │   │   → 有spl? → RMS补偿
                                          │   │     +SPL增益        │
                                          │   │   → 逐帧混音(主讲+干扰+噪声)
                                          │   │   → 100ms chunk     │
                                          │   ├── adapter.send()×N │
                                          │   ├── adapter.commit() │
                                          │   ├── is_interruption? │
                                          │   │   ├── 是 → 等AI开始说话
                                          │   │   │      → 推打断音频
                                          │   │   │      → 检测barge-in
                                          │   │   └── 否 → 等 AI 完整回复
                                          │   └── round_result     │
                                          │                        │
                                          │ _aggregate() → 存库    │
                                          │ _submit_evaluation()   │
                                          │ adapter.teardown()     │
                                          └────────────────────────┘
```

## 0.8 四种执行模式对比

| 维度 | HTTP API（非实时） | HTTP API（流式） | E2E | WebSocket API |
|------|:---:|:---:|:---:|:---:|
| 传输 | HTTP POST 请求/响应 | SSE 流式 | 物理播放 + PCM 抓取 | WebSocket 全双工流式 |
| 混音 | RenderAudioFile 整段混音（等所有音频齐了一次性混整段） | RenderAudioStream 逐帧流式混音（一边收 chunk 一边混） | PyAudio callback 实时混音 | RenderAudioStream 逐帧流式混音（一边收 chunk 一边混） |
| 格式适配 | AudioFormatAdapter | AudioFormatAdapter | 声卡/驱动负责 | AudioFormatAdapter |
| SPL 映射 | ApiRmsSplService (api_id→DB) | ApiRmsSplService (api_id→DB) | SPLMappingService (device→DB) | ApiRmsSplService (api_id→DB) |
| SPL 未配置 | gain=1.0 原始 RMS 不变 | gain=1.0 原始 RMS 不变 | gain=1.0 | gain=1.0 原始 RMS 不变 |
| AI 说话检测 | HTTP 响应判断 | SSE 事件驱动 | PCM RMS 轮询 + UI 控件 | WS 事件驱动 |
| 打断检测 | 不支持 | 支持（SSE 事件） | RMS + sleep 延迟 | 支持（speech_started/cancelled） |
| 多轮 | HTTP session_id | HTTP session_id | case 模式连续通话 | 同一 WebSocket 连接 |
| 噪声/干扰 | 混入整段混音缓冲（整文件） | 混入逐帧混音缓冲（随 chunk 推送） | 物理音箱播放 | 混入逐帧混音缓冲（随 chunk 推送） |
| 延迟测量 | HTTP 响应时间 | SSE 首事件时间戳 | 录屏首帧 + 时间戳 | 事件时间戳精确到 ms |
| 适配层 | HttpAPIAdapter | HttpStreamAdapter | device_driver | RealtimeAPIAdapter |
| 执行器 | APISessionExecutor | APISessionExecutor | E2EExecutor | RealtimeSessionExecutor |
| 评估入参 | answer + latency | answer + latency + first_frame_ms | user_wav + ai_wav + first_frame_ms | user_wav + ai_wav + first_frame_ms + event_log |
| 输出类型 | text, image | audio, text, video, image | audio (PCM) | audio, text, video, image |

## 0.9 UseCase：配置被测 API / Realtime 设备

> **场景**：用户需要新增一个被测 API（如 ChatGPT Realtime），配置其协议、adapter、音频参数、输出类型。
> 适用于 HTTP API（非实时/流式）和 WebSocket API（Realtime）两种。

### UC-0901：新增被测 API

```
Actor: 测试管理员
Precondition: 已登录系统，拥有 API 管理权限

Main Flow:
  1. 用户进入"被测 API 管理"页面
  2. 点击"新增 API"
  3. 填写基础信息
     ├── name: "ChatGPT Realtime"
     ├── vendor: openai
     ├── protocol: websocket
     ├── endpoints: [{url: "wss://api.openai.com/v1/realtime", priority: 1}]
     └── meta: {api_key: "sk-xxx", headers: {...}}
  4. 选择 adapter_class
     ├── 下拉列表可选: OpenAIRealtimeAdapter / HttpAPIAdapter / HttpStreamAdapter / ...
     └── 不选则按 (protocol, vendor) 自动匹配
  5. 配置 audio_config
     ├── sample_rate: 24000
     ├── bit_depth: 16
     ├── channels: 1
     ├── format: pcm
     └── chunk_duration_ms: 100
  6. 配置 output_types
     └── 勾选: [audio, text]（该 API 支持的输出类型）
  7. 关联 RMS SPL 映射（可选）
     └── 选择已校准的 api_rms_spl_mapping，不选则 gain=1.0
  8. 保存 → API 记录入库

Postcondition: API 表新增记录，含 adapter_class / audio_config / output_types / rms_spl_mapping_id
```

### UC-0902：配置 RMS SPL 映射

```
Actor: 测试管理员
Precondition: 已有被测 API 记录

Main Flow:
  1. 用户进入"API RMS SPL 映射"页面
  2. 选择被测 API
  3. 新建映射
     ├── name: "OpenAI Realtime 灵敏度校准"
     ├── reference_spl: 65.0
     ├── reference_gain_linear: 1.0
     └── calibration_data: {points: [{target_spl, gain_linear, rms_dbfs}, ...]}
  4. 执行校准（可选）
     ├── 发送已知 RMS 的音频到 API
     ├── 评估识别效果
     └── 记录校准点到 calibration_data
  5. 保存映射
  6. 在 API 编辑页关联此映射 → api.rms_spl_mapping_id

Postcondition: api_rms_spl_mappings 表新增记录，与 API 关联
```

### UC-0903：创建任务时关联被测设备

```
Actor: 测试执行人员
Precondition: 已有用例 + 已有被测 API/设备

Main Flow:
  1. 用户创建任务
  2. 关联用例（选多个用例）
  3. 为每个 TaskCase 选择被测设备
     ├── 用例A × 设备(小翼音箱)     → device_type=physical
     ├── 用例A × 设备(ChatGPT RT)  → device_type=websocket_api, device_id=api.id
     └── 用例B × 设备(通义千问)    → device_type=http_api, device_id=api.id
  4. 启动任务 → 系统按 device_type 路由到对应 executor

Postcondition: task_case_relations 表含 device_type + device_id，执行时按设备类型路由
```

## 0.10 UseCase：API Realtime Adaptor 模式

> **核心原则**：不同厂商的 Realtime API 返回事件字段各不相同，所有厂商特定字段的解读、映射、聚合
> 都由具体的 `RealtimeAPIAdapter` 子类负责。`RealtimeSessionExecutor` 只调用通用接口，不关心厂商字段。
>
> **帧结果 vs 最终结果**：Realtime 适配器需要保留**每帧结果**（逐 chunk 的中间状态）和**最终聚合结果**
> （完整回复），以支持延迟分析、barge-in 时序分析、多模态评估。

### UC-1001：厂商事件字段隔离

```
背景：
  OpenAI Realtime 返回的事件:
    response.audio.delta       → AI 音频增量（base64 PCM）
    response.audio.done        → AI 音频结束
    input_audio_buffer.speech_started → 用户开始说话
    response.cancelled          → AI 回复被取消（barge-in 成功）
    response.done              → AI 回复完整结束
    error                      → 错误事件

  其他厂商（如豆包/通义千问 Realtime）可能返回:
    audio_chunk                → AI 音频增量
    audio_complete             → AI 音频结束
    user_speech_start          → 用户开始说话
    response_interrupted       → 回复被中断
    response_finished          → 回复完整结束
    error_event                → 错误事件

  → 字段名、事件结构、payload 格式完全不同
  → 不能在 executor 里写死任何厂商特定字段
```

```
Actor: 系统（RealtimeSessionExecutor）
Precondition: adapter 已初始化，WebSocket 连接已建立

Main Flow:
  1. executor 调用 adapter.send(chunk, is_audio=True) 推送音频
  2. adapter 内部 _recv_loop 接收 WS 事件 → 放入 _event_queue
  3. executor 调用 adapter.recv() 或 adapter.post_process()
  4. adapter 从 _event_queue 取出原始事件
  5. adapter 调用 self._parse_event(event)  ← 子类实现
     ├── OpenAIRealtimeAdapter._parse_event:
     │     response.audio.delta → {"type": "ai_audio_delta", "delta": base64_decode(delta)}
     │     input_audio_buffer.speech_started → {"type": "user_speech_started"}
     │     response.cancelled → {"type": "response_cancelled"}
     │     response.done → {"type": "ai_audio_done"}
     │
     └── DoubaoRealtimeAdapter._parse_event: (假设)
           audio_chunk → {"type": "ai_audio_delta", "delta": base64_decode(chunk)}
           user_speech_start → {"type": "user_speech_started"}
           response_interrupted → {"type": "response_cancelled"}
           response_finished → {"type": "ai_audio_done"}

  6. _parse_event 返回归一化事件 → 基类写入统一属性
     ├── ai_audio_delta → _ai_audio_chunks.append(delta)
     ├── user_speech_started → barge_in_detected = True
     ├── response_cancelled → barge_in_detected = True
     └── ai_audio_done → _ai_complete = True

  7. executor 只看归一化后的通用事件类型，不关心原始厂商字段

Postcondition: 厂商特定字段解读完全隔离在子类 _parse_event 中
```

### UC-1002：保留帧结果和最终结果

```
Actor: 系统（RealtimeSessionExecutor）
Precondition: 适配器正在接收 AI 回复

Main Flow:
  1. adapter 接收每个事件时:
     ├── 原始事件 → 存入 _raw_event_log（完整保留，含时间戳）
     ├── 归一化事件 → 存入 _event_log（归一化后，含 type + 时间戳）
     └── AI 音频 delta → 追加到 _ai_audio_chunks（逐帧 PCM）

  2. 每帧结果（Frame Result）:
     ├── _ai_audio_chunks[i]  → 第 i 个音频帧（PCM bytes）
     ├── _frame_timestamps[i] → 第 i 帧到达时间戳（ms 精度）
     └── _frame_types[i]      → 第 i 帧事件类型（ai_audio_delta / user_speech_started / ...）

  3. 最终结果（Final Result）:
     ├── adapter.output.audio      → 所有帧拼接的完整 PCM（b''.join(_ai_audio_chunks)）
     ├── adapter.output.text      → 所有 token 累积的完整文本
     ├── adapter.output.video_chunks → 所有视频帧列表
     ├── adapter.output.images    → 所有图片列表
     ├── adapter.output.event_log  → 完整事件时间线（含每帧时间戳）
     ├── adapter.output.latency_ms → 首帧/首 token 延迟（从 commit 到第一个 ai_audio_delta）
     ├── adapter.barge_in_detected → 是否检测到 barge-in
     └── adapter.barge_in_latency_ms → barge-in 延迟（ms）

  4. executor 聚合时:
     ├── 逐帧结果 → 用于延迟分析、时序分析、barge-in 精确时间点
     └── 最终结果 → 用于语音质量评估、语义评估、多模态评估

  5. executor 不直接访问厂商字段
     ├── 不读 event["delta"]（OpenAI 特有）
     ├── 不读 event["audio_chunk"]（豆包特有）
     └── 只读 adapter.output.audio / adapter.output.latency_ms 等通用属性

Postcondition:
  ├── 每帧结果完整保留 → 支持帧级延迟分析
  ├── 最终结果完整聚合 → 支持端到端评估
  └── 厂商字段解读隔离在子类 → 新增厂商只需加子类
```

### UC-1003：新增厂商 Realtime 适配器

```
Actor: 开发人员
Precondition: 需要支持新的 Realtime API 厂商（如豆包 Realtime）

Main Flow:
  1. 继承 RealtimeAPIAdapter
     └── class DoubaoRealtimeAdapter(RealtimeAPIAdapter):
           vendor = "doubao"

  2. 实现四个抽象方法:
     ├── _build_connect_url()      → 豆包 WS URL + 认证参数
     ├── _build_connect_headers()  → 豆包认证头
     ├── _build_session_config()   → 豆包 session 配置
     └── _parse_event(event)       → 豆包事件 → 归一化事件映射

  3. _parse_event 职责:
     ├── 解析豆包特有字段 → 映射到统一事件类型
     │   audio_chunk → {"type": "ai_audio_delta", "delta": decode(audio_data)}
     │   user_speech_start → {"type": "user_speech_started"}
     │   response_interrupted → {"type": "response_cancelled"}
     │   response_finished → {"type": "ai_audio_done"}
     └── 将音频 delta 存入 self._ai_audio_chunks（帧结果）
     └── 记录帧时间戳到 self._frame_timestamps

  4. 注册到工厂:
     └── api_adapter_factory.register('websocket', 'doubao', DoubaoRealtimeAdapter)

  5. 在 API 表配置:
     └── adapter_class = "DoubaoRealtimeAdapter" （或 vendor="doubao" 自动匹配）

Postcondition:
  ├── 新厂商适配器只新增一个子类文件
  ├── executor / 基类 / 工厂无需修改
  └── 所有帧结果和最终结果通过基类统一属性输出
```

### 厂商适配职责矩阵

| 职责 | 基类 RealtimeAPIAdapter | 子类 (OpenAI/Doubao/...) | Executor |
|------|:---:|:---:|:---:|
| WebSocket 连接管理 | ✓ | — | — |
| 接收线程 + 事件队列 | ✓ | — | — |
| send / recv / post_process 通用逻辑 | ✓ | — | — |
| commit_input / create_response 通用指令 | ✓ | — | — |
| _build_connect_url | 抽象 | ✓ 实现 | — |
| _build_connect_headers | 抽象 | ✓ 实现 | — |
| _build_session_config | 抽象 | ✓ 实现 | — |
| _parse_event（厂商字段解读） | 抽象 | ✓ 实现 | — |
| 帧结果存储（_ai_audio_chunks / _frame_timestamps） | ✓ | — | — |
| 最终结果聚合（output 属性） | ✓ | — | — |
| barge_in_detected / barge_in_latency_ms | ✓ | — | — |
| 多轮循环 + 评估提交 | — | — | ✓ |
| 调用 adapter 通用接口 | — | — | ✓ |

> **关键**：executor 永远不直接访问 `event["delta"]`、`event["audio_chunk"]` 等厂商字段，
> 只通过 `adapter.output.audio`、`adapter.barge_in_detected` 等通用属性获取结果。
> 新增厂商只需实现四个抽象方法，零改动基类和 executor。

---
