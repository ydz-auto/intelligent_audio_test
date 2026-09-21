# UseCase 总览

> 版本：v1.0（V9.7.31 适配版）| 日期：2026-09-10 | 状态：适配自 V9.7.10《01_UseCase总览》v3.0/v3.1
>
> 适配目标：将 V9.7.10 单体「测试执行 v3.0 设计」映射到 V9.7.31 的 DDD + CQRS + 微服务 + 分布式部署架构。
> 架构事实：12 微服务（api_gateway:5000 / task_service:5001 / e2e_test_service:5002 / api_test_service:5003（replicas:2）/ evaluation_service:5004 / api_adapter_service:5008 / audio_service（gRPC:50052）/ device_service（gRPC:50053）等）；服务间通信走 gRPC（`shared/proto` 11 个 proto + ACL 仓储模式）；无 MQ，事件走 Redis EventBus（`shared/utils/redis_pubsub.py`）。

---

## 0.0 UseCase 总览表

| UC | 名称 | 落位服务 | 入口（HTTP 网关路由 → gRPC/command） | 涉及领域事件（EventChannel / EventType） |
|---|---|---|---|---|
| UC-0901 | 被测 API 管理（CRUD + 连通性测试） | api_test_service:5003 | `api_gateway/routes/api_bp.py` → gRPC `APITestService.CreateAPIConfig / UpdateAPIConfig / DeleteAPIConfig / ListAPIConfigs / GetAPIConfig / TestAPIConnection` → application command/query | `CONFIG_EVENTS`（事件类型按需扩展，新增） |
| UC-0902 | RMS SPL 映射管理（校准） | api_test_service（聚合归属）+ audio_service（增益换算共享） | `/api/digital-spl` 蓝图（新增）→ gRPC `ApiRmsSplConfigService`（新增）→ application command | `CONFIG_EVENTS`；校准互斥走 `DistributedLock` |
| UC-0903 | 创建任务并关联被测设备 | task_service:5001 + device_service（gRPC:50053） | `api_gateway/routes/task_bp.py` → gRPC `TaskService` / `DeviceService` → application command | `TASK_EVENTS` / `TASK_CREATED`、`DEVICE_EVENTS` / `DEVICE_STATUS_CHANGED` |
| UC-1001 | 事件隔离（多任务并发） | 各执行服务（发布）+ api_gateway:5000（订阅转发） | Redis EventBus 频道按 task_id 隔离 → api_gateway 转 Socket.IO 房间（room=task_id） | `TASK_EVENTS` / `CASE_EVENTS`，频道名全部来自 `EventChannel` 枚举 |
| UC-1002 | 帧结果实时获取（frame/summary 双通道） | api_test_service（RealtimeSessionExecutor）→ api_gateway → 前端 | 执行内推送 → `CASE_EVENTS` 频道 → Socket.IO 房间 | `CASE_EVENTS` / `CASE_EXECUTION_COMPLETED`、`CASE_EVALUATION_COMPLETED` |
| UC-1003 | 新增厂商 Realtime 适配器 | api_test_service（适配器注册表；P3 由 api_adapter_service 并入） | 代码扩展：`APIAdapterFactory` 注册表注册，无 HTTP 入口 | — |

---

## 0.1 核心模型：用例无关执行方式

> **核心原则**（与源文档一致）：用例是纯数据（`case_config` + `algorithm_params`），不区分类型。
> 被测设备类型决定执行方式。一个任务里可以混跑 E2E + API + Realtime。
>
> 【适配说明】V9.7.31 中"被测设备类型"由 `task_case_relations.device_type` 列（新增）承载，语义取代源文档的 `device_type` 运行时推断；`TaskType` **不引入** `'realtime_api'`（语义由 `device_type` 取代），废弃 `task.type` / `test_type` 字段。

```
用例 (TestCase)                          ← task_service（task_service/infrastructure/persistence/models/testcase_models.py）
  ├── case_config (JSON)     ← 纯数据，不绑定执行方式
  └── algorithm_params (独立列)

任务 (Task)                              ← task_service（task_models.py，表 test_tasks）
  ├── 关联用例 (task_case_relations)      ← 已有 device_id 列（task_models.py L111），device_type 列（新增）
  └── 被测设备 (device_id + device_type)  ← 设备类型决定执行方式
         │
         ├── physical（物理设备）        → e2e_test_service:5002  E2EExecutor
         ├── http_api（HTTP API）        → api_test_service:5003  APISessionExecutor（HttpAPIAdapter/HttpStreamAdapter）
         └── websocket_api（WS API）     → api_test_service:5003  RealtimeSessionExecutor（RealtimeAPIAdapter）
```

**用户操作流程**：
1. 导入音频 → 生成用例（`case_config` + `algorithm_params`），不选类型
2. 创建任务 → 关联用例 + 关联被测设备（可同时选物理设备 + 多个 API）（UC-0903）
3. 执行 → task_service 调度器按 `task_case_relations.device_type` 路由：
   `task_service/core/execution_engine/mixins/task_dispatch.py` 的 `_dispatch_case_by_type`（L89）→ `_dispatch_api_case`（L96）/ `_dispatch_e2e_case`（L112），经 gRPC 分发到对应微服务

**一个任务混跑示例**：
```
Task "全量回归"（task_service 调度，逐 TaskCase 经 gRPC 分发）
  ├── TaskCase #1: 用例A × 设备(小翼音箱)    device_type=physical      → e2e_test_service E2EExecutor
  ├── TaskCase #2: 用例A × 设备(ChatGPT RT)  device_type=websocket_api → api_test_service RealtimeSessionExecutor
  ├── TaskCase #3: 用例B × 设备(通义千问)    device_type=http_api      → api_test_service APISessionExecutor
  └── TaskCase #4: 用例B × 设备(小翼音箱)    device_type=physical      → e2e_test_service E2EExecutor
```

> 【适配说明】执行器统一继承 `shared/infrastructure/base_executor/_base.py` 的 `BaseExecutor`（= ControlMixin + LoggingMixin + ParamsMixin + ResultsMixin + DbMixin 五 mixin），保证三类 executor 的控制（启停）、日志、参数、结果落库、DB 会话行为一致。

## 0.2 调用模式（流式 vs 非实时）

> API 类被测设备支持流式和非实时两种调用模式，由 `case_config.stream` 或 API 配置决定。（与源文档一致）

| 调用模式 | 说明 | 传输协议 | 输入 | 输出 | AI 说话检测 | 打断检测 |
|---|---|---|---|---|---|---|
| **非实时调用** | 一次性发送完整音频，等完整响应 | HTTP POST | 文件级 | 完整 JSON | 不需要 | 不支持 |
| **流式调用** | 实时输入 chunk，实时输出 chunk | SSE / WebSocket | chunk 流式 | chunk 流式 | 事件驱动 | 支持 |

## 0.3 被测设备类型 × 执行方式 × 落位服务

> 【适配说明】在源文档表格基础上增加"落位服务"与"SPL 服务"列，体现微服务归属。

| 被测设备类型（device_type） | Executor（落位服务） | 音频处理 | SPL 映射 | 调用模式 |
|:---:|---|---|---|---|
| `physical` | E2EExecutor（e2e_test_service:5002） | 物理播放（audio_service gRPC:50052）+ PCM 抓取 | `device.spl_mapping_id` → `audio_service/infrastructure/audio/spl_service.py` `SPLMappingService.spl_to_gain(mapping_id, target_spl)` | — |
| `http_api`（非实时） | APISessionExecutor（api_test_service:5003） | 整段混音（执行中一次性混好整段音频，RenderAudioFile unary 整文件返回后 POST） | `api.rms_spl_mapping_id` → ApiRmsSplService 多点插值 | 非实时 |
| `http_api`（流式） | APISessionExecutor（api_test_service:5003） | 混音 → chunk → SSE（混音下沉 audio_service，见 0.8） | `api.rms_spl_mapping_id` → ApiRmsSplService 多点插值 | 流式 |
| `websocket_api` | RealtimeSessionExecutor（api_test_service:5003） | 混音 → chunk → WS 全双工 | `api.rms_spl_mapping_id` → ApiRmsSplService 多点插值 | 流式 |

> `device_type` 枚举落位：后端 `shared/models/common_enums.py`（新增 `DeviceType`），前端 `frontend/src/domain/enums.ts`（新增 `DeviceType`；现状该文件仅有 TaskStatus/TaskType/TestType/ExecutionStatus/EvaluationStatus，无 DeviceType/OutputType/CalibrationStatus，均标（新增））。禁止魔法字符串。

## 0.4 用例结构

> **核心原则**（与源文档一致）：用例只有一份结构，不区分 E2E/API/Realtime。
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

**字段在不同执行方式下的使用情况**（与源文档一致）：

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

> 【适配说明】`algorithm_type` 等取值全部枚举化（后端 `shared/models/common_enums.py`，前端 `frontend/src/domain/enums.ts`），拒绝魔法字符串；密钥类字段（`meta.api_key`）遵循 OpenAI 密钥链：`case_config → meta → env OPENAI_API_KEY` 逐级回退，禁止落明文日志。

## 0.5 被测 API 配置（音频参数 + adapter 选择）

> 被测 API 表（`apis`，模型 `api_test_service/infrastructure/persistence/models/api_models.py` L15 `class API`）需要扩展音频参数和 adapter 选择字段。
> adapter 选择决定走哪个适配器类，音频参数决定 chunk 格式。

```json
// apis 表配置示例（DDD 聚合：API，归属 api_test_service）
{
  "id": 1,
  "name": "ChatGPT Realtime",
  "vendor": "openai",
  "protocol": "websocket",
  "adapter_class": "OpenAIRealtimeAdapter",
  "device_type": "websocket_api",
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

| 字段 | 说明 | 取值 | 现状 |
|------|------|------|------|
| `vendor` | 厂商标识 | `openai` / `volc` / `qwen` / `doubao` / ... | 已有列 |
| `protocol` | 传输协议 | `websocket` / `http` | 由 `api_endpoints`(JSON, 已有列) 承载，语义收敛 |
| `adapter_class` | 指定 adapter 类名 | `OpenAIRealtimeAdapter` / `HttpAPIAdapter` / `HttpStreamAdapter` / ... | （新增列） |
| `device_type` | 被测设备类型 | `websocket_api` / `http_api` | （新增列） |
| `audio_config.sample_rate` | 采样率 | 8000 / 16000 / 24000 / 48000 | （新增列，JSON） |
| `audio_config.bit_depth` | 位深 | 8 / 16 / 24 / 32 | （新增列，JSON） |
| `audio_config.channels` | 通道数 | 1（单声道）/ 2（立体声） | （新增列，JSON） |
| `audio_config.format` | 音频格式 | `pcm` / `wav` / `mp3` / `opus` | （新增列，JSON） |
| `audio_config.chunk_duration_ms` | chunk 时长 | 20 / 40 / 100（默认 100） | （新增列，JSON） |
| `output_types` | API 输出类型列表 | `["audio", "text", "video", "image"]` 的子集 | （新增列） |

> 【适配说明】`api_models.py` 现有列仅有 name / vendor / api_url / description / status / meta / algorithm_type / max_process / max_timeout / max_audio_duration / health_score / api_endpoints 等，**缺 `device_type` / `adapter_class` / `audio_config` / `output_types` 列，均标（新增）**；`rms_spl_mapping_id` 随 `api_rms_spl_mappings` 聚合（UC-0902）一并新增。
> **adapter 选择逻辑**：`APIAdapterFactory.get_adapter()` 优先按 `adapter_class` 指定类名创建，未指定时按 `(protocol, vendor)` 自动匹配。`APIAdapterFactory` 现位于 `api_adapter_service/adapters/factory.py`；按 P3 规划 api_adapter_service(5008) 下线并入 api_test_service，注册表随迁（见 UC-1003）。

## 0.6 多模态输出

> API 和 Realtime API 的输出不只有音频，还可能是文本、视频、图片等。
> adapter 统一采集所有输出类型，executor 聚合后提交评估。（与源文档一致）

| 输出类型 | 来源 | adapter 采集 | 评估用途 |
|----------|------|-------------|----------|
| `audio` | AI 语音回复 | `adapter.ai_audio` (PCM chunks 拼接) | 语音质量 / 抢话 / 打断检测 |
| `text` | AI 文本回复 | `adapter.ai_text` (累积拼接) | 语义评估 / 翻译准确率 |
| `video` | AI 视频回复 | `adapter.ai_video_chunks` (视频帧序列) | 视频质量 / 表情评估 |
| `image` | AI 图片回复 | `adapter.ai_images` (图片 URL/base64 列表) | 图片质量 / 内容识别 |

**adapter 输出数据结构**（与源文档一致）：

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

> 非实时 HTTP 调用通常是"发音频→收文本/图片"，无音频输出；流式和全双工可以输出任意类型。
> 【适配说明】`output_types` 取值枚举化：后端入 `shared/models/common_enums.py`，前端 `OutputType` 入 `frontend/src/domain/enums.ts`（新增）。

## 0.7 SPL 处理逻辑（三种情况）

> **关键**（与源文档一致）：用户在用例 `case_config.rounds[].audios[]` 里配的是**目标声压级（dB SPL）**，不是 RMS。
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
           ├── task_case_relations.device_type = physical
           │     → audio_service SPLMappingService.spl_to_gain(mapping_id, target_spl)
           │       （audio_service/infrastructure/audio/spl_service.py L34，DB 查 SPLMapping，物理设备声压校准）
           │
           └── task_case_relations.device_type = websocket_api / http_api（流式）
                 → ApiRmsSplService.spl_to_gain(api_id, spl)
                   （api_rms_spl_mappings 表（新增）多点插值，被测 API 灵敏度校准）
                 → gain × 原始 RMS = 目标声压
                 → 混音 → chunk
```

> 【适配说明】源文档分支条件 `task.type=e2e / task.type=realtime_api` 在 V9.7.31 **废弃**：`task.type` / `test_type` 字段整体废弃，`TaskType` 不引入 `'realtime_api'`，分支条件统一改为 `task_case_relations.device_type`（新增列），枚举入 `shared/models/common_enums.py`。

## 0.8 执行路由总流程图（V9.7.31 微服务版）

> 【适配说明】源文档为单体内路由图；V9.7.31 改为 api_gateway → task_service 调度 → gRPC 分发三个执行服务的分布式路由。物理设备互斥由进程内 dict 改为 Redis 分布式锁（`shared/utils/distributed_coordinator.py` `DistributedLock` L67 / `DistributedSemaphore` L153）。

```
            用户创建任务（选关联用例 + 被测设备）           ← UC-0903
                              │
                              ▼
        api_gateway:5000（HTTP + Socket.IO，唯一对外入口）
                              │  gRPC（shared/proto，11 个 proto）
                              ▼
        task_service:5001  调度（task_dispatch.py）
                              │  for each task_case_relations:
                              │    _dispatch_case_by_type(task_id, task, tc_rel, session)
                              │    按 tc_rel.device_type + device_id 路由
                              │
          ┌───────────────────┼────────────────────────────┐
          │                   │                            │
   device_type=physical   device_type=http_api        device_type=websocket_api
          │                   │                            │
          ▼ gRPC              ▼ gRPC                       ▼ gRPC
  e2e_test_service:5002   api_test_service:5003        api_test_service:5003
  E2EExecutor             (replicas:2, worker_instance_id)（同左）
          │                   │                            │
  ┌───────────────┐   ┌──────┴────────┐                   │
  │ audio_service │   │ 调用模式?      │                   │
  │ (gRPC:50052)  │   ├── 非实时        │                   │
  │ 物理播放+PCM   │   │  → HttpAPIAdapter                 │
  │ PlaybackOrch  │   │    文件级 HTTP POST                │
  │ (playback_    │   │    等完整 JSON                     │
  │ orchestrator. │   │    输出: text/image                │
  │ py)           │   └── 流式          │                   │
  │ SPLMapping    │      → HttpStreamAdapter             │
  │ Service       │      → RenderAudioStream（新增）       │
  │ .spl_to_gain  │        混音下沉 audio_service：        │
  │ (spl_service. │        离线混音 6 步                    │
  │ py)           │        → 100ms base64 chunk            │
  │               │        server-streaming 流式返回        │
  │ 物理设备互斥:   │      → SSE/WS 推给被测 API             │
  │ Redis 分布式锁 │                                       │
  │ (Distributed  │   ┌────────────────────────────┐      │
  │ Lock)         │   │ APIAdapterFactory.get_adapter()    │
  └───────────────┘   │   → RealtimeAPIAdapter             │
                      │ adapter.initialize()               │
                      │   → WS 连接 + _recv_loop 线程       │
                      │ adapter.pre_process()              │
                      │   → session.update()               │
                      │ for each round:                    │
                      │   ├── 合并噪声配置 (轮次级>全局)      │
                      │   ├── RenderAudioStream             │
                      │   │   有spl? → RMS补偿+SPL增益       │
                      │   │   混音(主讲+干扰+噪声)→切chunk    │
                      │   ├── adapter.send()×N              │
                      │   ├── adapter.commit()              │
                      │   ├── is_interruption?              │
                      │   │   ├── 是 → 等AI开始说话           │
                      │   │   │      → 推打断音频             │
                      │   │   │      → 检测barge-in          │
                      │   │   └── 否 → 等 AI 完整回复         │
                      │   └── round_result                   │
                      │                                      │
                      │ _aggregate() → 存库                   │
                      │ _submit_evaluation() → gRPC           │
                      │   → evaluation_service:5004           │
                      │ adapter.teardown()                    │
                      └────────────────────────────────────────┘
```

> 【适配说明】源文档中消费侧的 `AudioStreamOrchestrator.chunk_audio()` 在 V9.7.31 **不放消费侧**：混音下沉 audio_service，新增 server-streaming RPC `RenderAudioStream`（`shared/proto/audio_service.proto` 现仅有 PlayAudio / StopAudio / GetPlayStatus / GetAudioInfo / MeasureSPL，`RenderAudioStream` 标（新增）），实现"离线混音 6 步 → 100ms base64 chunk 流式返回"，api_test_service 与 e2e_test_service 共用。
> `shared/proto/api_test_service.proto` 的 `APITestService` 已有 CreateAPITest / StartAPITest / StopAPITest / GetAPITestStatus；其中 `StartAPITestRequest` **缺 `device_type` 字段，标（新增）**，调度分发时由 task_service 传入。

## 0.9 四种执行模式对比（V9.7.31）

> 【适配说明】在源文档对比表基础上增加"落位服务 / 事件通道"维度。

| 维度 | HTTP API（非实时） | HTTP API（流式） | E2E | WebSocket API |
|------|:---:|:---:|:---:|:---:|
| **落位服务** | api_test_service:5003 | api_test_service:5003 | e2e_test_service:5002 + audio_service:50052 | api_test_service:5003 |
| 传输 | HTTP POST 请求/响应 | SSE 流式 | 物理播放 + PCM 抓取 | WebSocket 全双工流式 |
| 混音 | 整段混音（执行中一次性混好整段，RenderAudioFile unary 整文件返回后 POST，见《08_混音与SPL映射.md》） | audio_service RenderAudioStream（新增，server-streaming） | audio_service 物理播放 + PyAudio callback | audio_service RenderAudioStream（新增，server-streaming） |
| SPL 映射 | ApiRmsSplService（api_rms_spl_mappings，新增） | ApiRmsSplService（api_rms_spl_mappings，新增） | SPLMappingService（audio_service，device→DB） | ApiRmsSplService（api_rms_spl_mappings，新增） |
| SPL 未配置 | gain=1.0 原始 RMS 不变 | gain=1.0 原始 RMS 不变 | gain=1.0 | gain=1.0 原始 RMS 不变 |
| AI 说话检测 | 不需要 | SSE 事件驱动 | PCM RMS 轮询 + UI 控件 | WS 事件驱动 |
| 打断检测 | 不支持 | 支持（SSE 事件） | RMS + sleep 延迟 | 支持（user_speech_started / response_cancelled） |
| 多轮 | HTTP session_id | HTTP session_id | case 模式连续通话 | 同一 WebSocket 连接 |
| 噪声/干扰 | 混入完整音频（整段混音后整文件上传） | 混入轮次混音缓冲 | 物理音箱播放 | 混入轮次混音缓冲 |
| 延迟测量 | HTTP 响应时间 | SSE 首事件时间戳 | 录屏首帧 + 时间戳 | 事件时间戳精确到 ms |
| 适配层 | HttpAPIAdapter | HttpStreamAdapter | device_driver | RealtimeAPIAdapter |
| 执行器 | APISessionExecutor | APISessionExecutor | E2EExecutor（BaseExecutor 五 mixin 基座） | RealtimeSessionExecutor（BaseExecutor 五 mixin 基座） |
| 执行器落位 | api_test_service/core/api_session_executor.py | 同左 | e2e_test_service/application/services/e2e_executor/executor.py | api_test_service/core/api_session_executor.py |
| 事件通道 | CASE_EVENTS（summary） | CASE_EVENTS（frame + summary） | CASE_EVENTS（summary） | CASE_EVENTS（frame + summary，UC-1002） |
| 评估入参 | answer + latency | answer + latency + first_frame_ms | user_wav + ai_wav + first_frame_ms | user_wav + ai_wav + first_frame_ms + event_log |
| 输出类型 | text, image | audio, text, video, image | audio (PCM) | audio, text, video, image |

## 0.10 UseCase：配置被测 API / Realtime 设备

> **场景**（与源文档一致）：用户需要新增一个被测 API（如 ChatGPT Realtime），配置其协议、adapter、音频参数、输出类型。
> 适用于 HTTP API（非实时/流式）和 WebSocket API（Realtime）两种。
> 【适配说明】V9.7.31 中每个 UC 增加扩展流程与验收标准，并标注落位服务 / 入口链路 / 领域事件。

### UC-0901：被测 API 管理（CRUD + 连通性测试）

- **落位服务**：api_test_service:5003（聚合：API，表 `apis`，模型 `api_test_service/infrastructure/persistence/models/api_models.py`）
- **入口**：前端 `views/APITest/APITest.vue` → api_gateway `routes/api_bp.py`（schemas `api_gateway/schemas/api.py` 校验，camelCase ↔ snake_case 适配层转换）→ gRPC `APITestService.CreateAPIConfig / UpdateAPIConfig / DeleteAPIConfig / ListAPIConfigs / GetAPIConfig / TestAPIConnection`（`shared/proto/api_test_service.proto`）→ api_test_service application command/query（CQRS）
- **领域事件**：`EventChannel.CONFIG_EVENTS`（配置变更，事件类型按需扩展，新增）

```
Actor: 测试管理员
Precondition: 已登录系统，拥有 API 管理权限（RBAC）

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
  5. 配置 audio_config（sample_rate/bit_depth/channels/format/chunk_duration_ms）
  6. 配置 output_types（勾选该 API 支持的输出类型）
  7. 关联 RMS SPL 映射（可选）：选择已校准的 api_rms_spl_mapping，不选则 gain=1.0
  8. 保存 → api_gateway → gRPC CreateAPIConfig → application command
     （CommandHandler → API 聚合不变量校验 → persistence 仓储落库）
  9. 连通性测试 → gRPC TestAPIConnection → 记录 health_score

扩展流程:
  3a. meta.api_key 不落明文日志；Realtime 执行时按密钥链
      case_config → meta → env OPENAI_API_KEY 逐级回退
  4a. protocol=websocket 且 vendor=openai → 前端建议默认 adapter_class=OpenAIRealtimeAdapter
  8a. 校验失败 → api_gateway 返回统一错误码（api_gateway/utils/error_codes.py），不入库
  9a. 连通性失败 → status=offline → 发布 DEVICE_STATUS_CHANGED（DEVICE_EVENTS）

验收标准:
  ├── apis 表新增记录，含 device_type / adapter_class / audio_config / output_types（新增列）
  ├── 前端只见 camelCase Domain（domain/model/apiConfig.ts），snake_case 仅存在于 api/dto/adapter 层
  ├── CRUD 全部经 gRPC，api_gateway 无直连 DB
  ├── DeviceType / OutputType 枚举入 shared/models/common_enums.py + frontend/src/domain/enums.ts（新增），无魔法字符串
  └── 密钥不出现在任何日志/事件 payload 中

Postcondition: apis 表新增记录，含 adapter_class / audio_config / output_types / rms_spl_mapping_id
```

### UC-0902：配置 RMS SPL 映射（校准）

- **落位服务**：api_test_service:5003（`ApiRmsSplMapping` 聚合按 DDD 五层落位：domain 聚合 → application command/query → interfaces gRPC → infrastructure persistence，表 `api_rms_spl_mappings`（新增））+ audio_service:50052（SPL→gain 换算共享：`ApiRmsSplService` 多点插值 / `SPLMappingService.spl_to_gain`）
- **入口**：`/api/digital-spl` 蓝图（api_gateway，新增）→ gRPC `ApiRmsSplConfigService`（新增）→ application command；校准互斥走 `DistributedLock`（`shared/utils/distributed_coordinator.py` L67）
- **领域事件**：`EventChannel.CONFIG_EVENTS`（事件类型按需扩展，新增）

```
Actor: 测试管理员
Precondition: 已有被测 API 记录（UC-0901）

Main Flow:
  1. 用户进入"API RMS SPL 映射"页面
     （前端按 SPLMapping 五层对称模板落位：
      SPLMapping.vue → useSplMapping（composables/Port）→ splPort → splApi
      → splAdapter → splDto → domain/model/spl.ts，camelCase 全程）
  2. 选择被测 API
  3. 新建映射
     ├── name: "OpenAI Realtime 灵敏度校准"
     ├── reference_spl: 65.0
     ├── reference_gain_linear: 1.0
     └── calibration_data: {points: [{target_spl, gain_linear, rms_dbfs}, ...]}
  4. 执行校准（可选）
     ├── 获取 DistributedLock("spl_calibration:{api_id}")  ← 分布式互斥（新增）
     ├── 发送已知 RMS 的音频到 API
     ├── 评估识别效果
     └── 记录校准点到 calibration_data
  5. 保存映射（释放锁）
  6. 在 API 编辑页关联此映射 → api.rms_spl_mapping_id

扩展流程:
  4a. 并发校准同一 API：第二请求拿锁失败 → 返回"校准进行中"（分布式锁互斥，
      取代源文档单体内隐式互斥）【适配说明：V9.7.31 新增】
  4b. 校准超时/实例宕机：锁 TTL 到期自动释放，避免死锁
  5a. 校准状态流转用 CalibrationStatus 枚举（frontend/src/domain/enums.ts，新增；
      后端入 shared/models/common_enums.py）

验收标准:
  ├── api_rms_spl_mappings 表（新增）落库，与 API 关联
  ├── 执行期 ApiRmsSplService.spl_to_gain(api_id, spl) 多点插值结果与校准点一致
  ├── 同一 API 并发校准被分布式锁互斥，无脏校准数据
  ├── 前端五层对称模板完整（Port/Api/Adapter/Dto/Model），无跨层调用
  └── 无魔法数字：采样点间隔、锁 TTL、插值边界值均配置化

Postcondition: api_rms_spl_mappings 表新增记录，与 API 关联
```

### UC-0903：创建任务时关联被测设备

- **落位服务**：task_service:5001（Task 聚合 + 调度）+ device_service（gRPC:50053，物理设备元数据）+ api_test_service（API 下拉数据源，经 api_gateway 查询）
- **入口**：前端 `views/Tasks/` → api_gateway `routes/task_bp.py`（schemas `task.py`）→ gRPC `TaskService` / `DeviceService` → task_service application command
- **领域事件**：`TASK_EVENTS` / `TASK_CREATED`（启动）、`DEVICE_EVENTS` / `DEVICE_STATUS_CHANGED`（设备离线联动）

```
Actor: 测试执行人员
Precondition: 已有用例 + 已有被测 API/设备

Main Flow:
  1. 用户创建任务
  2. 关联用例（选多个用例）
  3. 为每个 task_case_relations 选择被测设备
     ├── 用例A × 设备(小翼音箱)    → device_type=physical,      device_id=设备ID
     ├── 用例A × 设备(ChatGPT RT)  → device_type=websocket_api, device_id=api.id
     └── 用例B × 设备(通义千问)    → device_type=http_api,      device_id=api.id
  4. 启动任务 → task_service 发布 TASK_CREATED
     → 调度器 _dispatch_case_by_type 按 device_type 路由（见 0.8）

扩展流程:
  3a. device_type=physical 时校验物理设备在线（device_service gRPC 查询），
      离线 → 拒绝启动或标记 skip
  3b. device_type=http_api/websocket_api 时校验 API 可用
      （status=online，必要时触发 UC-0901 连通性测试）
  4a. 物理设备互斥：同设备被另一任务占用 → DistributedLock 获取失败 →
      排队或跳过（进程内 dict 方案废弃）【适配说明：V9.7.31 改为 Redis 分布式锁】
  4b. api_test_service 多实例（replicas:2）：task case 分配携带
      worker_instance_id，实例宕机由 Registry 孤儿收养接管（见 UC-1001）

验收标准:
  ├── task_case_relations 含 device_id（已有，task_models.py L111）+ device_type（新增）
  ├── 执行时按 device_type 精确路由（混跑示例 0.1 全部正确分发）
  ├── 同一物理设备同时只被一个任务占用（分布式锁验证）
  ├── TASK_CREATED / DEVICE_STATUS_CHANGED 事件均携带 task_id，前端按房间隔离接收
  └── 废弃字段 task.type / test_type 不再读写；TaskType 无 'realtime_api' 取值

Postcondition: task_case_relations 表含 device_type + device_id，执行时按设备类型路由
```

## 0.11 UseCase：API Realtime Adaptor 模式（V9.7.31）

> **核心原则**（与源文档一致）：不同厂商的 Realtime API 返回事件字段各不相同，所有厂商特定字段的解读、映射、聚合
> 都由具体的 `RealtimeAPIAdapter` 子类负责。`RealtimeSessionExecutor` 只调用通用接口，不关心厂商字段。
>
> **帧结果 vs 最终结果**（与源文档一致）：Realtime 适配器需要保留**每帧结果**（逐 chunk 的中间状态）和**最终聚合结果**
> （完整回复），以支持延迟分析、barge-in 时序分析、多模态评估。
>
> 【适配说明】源文档 UC-1001（厂商事件字段隔离）在本版调整为运行时"事件隔离（多任务并发）"，厂商字段归一化内容并入 UC-1003 的扩展流程；UC-1002 由"保留帧结果和最终结果"适配为 frame/summary 双通道实时获取。

### 背景事件样例（归一化输入）

```
OpenAI Realtime 返回的事件:
  response.audio.delta              → AI 音频增量（base64 PCM）
  response.audio.done               → AI 音频结束
  input_audio_buffer.speech_started → 用户开始说话
  response.cancelled                → AI 回复被取消（barge-in 成功）
  response.done                     → AI 回复完整结束
  error                             → 错误事件

其他厂商（如豆包/通义千问 Realtime）可能返回:
  audio_chunk          → AI 音频增量
  audio_complete       → AI 音频结束
  user_speech_start    → 用户开始说话
  response_interrupted → 回复被中断
  response_finished    → 回复完整结束
  error_event          → 错误事件

→ 字段名、事件结构、payload 格式完全不同
→ 不能在 executor 里写死任何厂商特定字段（归一化职责见 UC-1003）
→ 归一化事件共 11 种（ai_audio_delta / user_speech_started / response_cancelled 等），
  枚举化定义，禁止裸字符串
```

### UC-1001：事件隔离（多任务并发）

- **落位服务**：各执行服务（api_test_service:5003 replicas:2 / e2e_test_service:5002，事件发布方）+ api_gateway:5000（订阅转发方）
- **入口**：执行服务内 `EventBus.publish(EventChannel.X, payload)`（`shared/utils/redis_pubsub.py`，`RedisPubSub` L51 / `EventBus` L107 / `EventChannel` L21 / `EventType` L30）→ api_gateway 订阅 Redis 频道 → Socket.IO 房间（room=task_id）推送前端（`api_gateway/websocket/socketio_server.py`，前端 `frontend/src/utils/socket.ts`）
- **领域事件**：`TASK_EVENTS` / `CASE_EVENTS` / `DEVICE_EVENTS`，频道名全部取自 `EventChannel` 枚举（禁止裸字符串）

```
Actor: 系统（多任务并发执行）
Precondition: api_test_service 双副本部署（replicas:2），多任务并行执行中

Main Flow:
  1. 执行服务发布事件：channel=EventChannel.CASE_EVENTS（或 TASK_EVENTS），
     payload 一律携带 task_id（隔离键）
  2. api_gateway 订阅 Redis 频道（RedisPubSub 单例）
  3. api_gateway 按 payload.task_id 路由到 Socket.IO 房间 room=task:{task_id}
  4. 前端 socket.ts 进入对应房间，只接收本任务事件 → 多任务页面互不串扰
  5. 每个执行 worker 以 worker_instance_id 标识，事件 payload 内携带，
     便于链路追踪与实例级排查

扩展流程:
  5a. 实例宕机：RedisServiceRegistry（shared/utils/service_registry.py L16）
      TTL 心跳（last_heartbeat）超时 → 孤儿任务被其他实例收养
      （SchedulerMixin._adopt_orphan_tasks）→ 新实例以同一 task_id
      继续发布事件，前端事件流恢复且无重复房间
  5b. 物理设备互斥场景：等待锁的任务不发执行事件，仅发布排队状态，
      避免"假运行中"误导前端
  5c. 频道扩展必须改 EventChannel/EventType 枚举，禁止运行时拼接裸字符串频道名

验收标准:
  ├── 并发 ≥2 任务，各前端会话仅收到自己 task_id 的事件（房间隔离验证）
  ├── 任一实例 kill 后，其名下任务在心跳超时后被收养并继续产出事件
  ├── 全代码库无裸字符串频道名（静态检查 EventChannel 引用）
  └── log_and_emit 直发模式废弃，统一走 EventBus 发布 + api_gateway 转发
      【适配说明：源单体 log_and_emit 直发 Socket.IO 在 V9.7.31 废弃】

Postcondition: 多任务并发下事件按 task_id 完全隔离，无跨任务串台
```

### UC-1002：帧结果实时获取（frame / summary 双通道）

- **落位服务**：api_test_service:5003（`RealtimeSessionExecutor`，`api_test_service/core/api_session_executor.py`）→ api_gateway:5000（转发）
- **入口**：执行内推送（frame 高频 → 仅 Socket.IO 房间；summary 低频 → Redis EventBus `CASE_EVENTS` + 落库）→ 前端房间
- **领域事件**：`CASE_EVENTS` / `CASE_EXECUTION_COMPLETED`、`CASE_EVALUATION_COMPLETED`

```
Actor: 系统（RealtimeSessionExecutor + 前端实时视图）
Precondition: 适配器正在接收 AI 回复（Realtime 会话进行中）

Main Flow:
  1. adapter 接收每个事件时:
     ├── 原始事件 → 存入 _raw_event_log（完整保留，含时间戳）
     ├── 归一化事件 → 存入 _event_log（归一化后，含 type + 时间戳）
     └── AI 音频 delta → 追加到 _ai_audio_chunks（逐帧 PCM）

  2. frame 通道（逐帧，高频、轻量、不落库）:
     ├── _ai_audio_chunks[i]  → 第 i 个音频帧（PCM bytes）
     ├── _frame_timestamps[i] → 第 i 帧到达时间戳（ms 精度）
     └── _frame_types[i]      → 第 i 帧事件类型（11 种归一化事件）
     → executor 节流聚合（按帧数/时间窗，阈值配置化）后经
       CASE_EVENTS → api_gateway → room=task:{task_id} 推前端

  3. summary 通道（轮次/用例终态，低频、落库）:
     ├── adapter.output.audio      → 所有帧拼接的完整 PCM
     ├── adapter.output.text       → 所有 token 累积的完整文本
     ├── adapter.output.video_chunks → 所有视频帧列表
     ├── adapter.output.images     → 所有图片列表
     ├── adapter.output.event_log  → 完整事件时间线（含每帧时间戳）
     ├── adapter.output.latency_ms → 首帧/首 token 延迟（commit → 首个 ai_audio_delta）
     ├── adapter.barge_in_detected → 是否检测到 barge-in
     └── adapter.barge_in_latency_ms → barge-in 延迟（ms）
     → 轮次结束聚合落库 → 发布 CASE_EXECUTION_COMPLETED（触发评估）

  4. 消费方职责:
     ├── frame → 前端实时波形/时序渲染、执行中状态展示
     ├── summary → 语音质量评估、语义评估、多模态评估、报告生成
     └── 评估入参取自 summary（frame 不参与评估计算）

扩展流程:
  3a. barge-in 打断：response_cancelled → 立即 flush 未推 frame →
      summary 标记 interrupted + barge_in_latency_ms → 提前结束本轮
  3b. 前端断线重连：重连后按 task_id 重新 join 房间，frame 从当前帧续传，
      summary 由落库数据兜底（历史轮次查 DB，不重放事件）
  3c. HTTP API（非实时）无 frame 通道，仅 summary（见 0.9 对比表）

验收标准:
  ├── frame 时间戳 ms 精度，可用于时序/barge-in 分析
  ├── summary 与该轮 frame 聚合结果一致（帧拼接 = summary.audio）
  ├── executor 不直接访问厂商字段（不读 event["delta"] / event["audio_chunk"]），
      只读 adapter.output / barge_in_* 通用属性
  ├── frame 推送频率可配置（节流阈值无魔法数字），前端无卡顿
  └── 双通道分离：frame 不落库、summary 必落库，评估只读 summary

Postcondition: 前端实时获取逐帧结果，评估取最终聚合结果，厂商字段零泄漏
```

### UC-1003：新增厂商 Realtime 适配器

- **落位服务**：api_test_service:5003（适配器注册表）。`APIAdapterFactory` 现位于 `api_adapter_service/adapters/factory.py`，【适配说明：P3 阶段 api_adapter_service(5008) 下线并入 api_test_service，注册表与 adapter 实现随迁】
- **入口**：代码扩展（`APIAdapterFactory` 注册表注册），无 HTTP/gRPC 新入口；生效入口为 UC-0901 的 `adapter_class` 配置
- **领域事件**：—（开发期变更）

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

  3. _parse_event 职责（厂商字段归一化，源 UC-1001 内容并入此处）:
     ├── 解析豆包特有字段 → 映射到统一事件类型（11 种归一化事件枚举）
     │   audio_chunk          → {"type": "ai_audio_delta", "delta": decode(audio_data)}
     │   user_speech_start    → {"type": "user_speech_started"}
     │   response_interrupted → {"type": "response_cancelled"}
     │   response_finished    → {"type": "ai_audio_done"}
     ├── 将音频 delta 存入 self._ai_audio_chunks（帧结果）
     └── 记录帧时间戳到 self._frame_timestamps

  4. 注册到工厂:
     └── APIAdapterFactory.register('websocket', 'doubao', DoubaoRealtimeAdapter)
        （注册表以 (protocol, vendor) 为键，vendor 取值入枚举，禁魔法字符串）

  5. 在 apis 表配置（UC-0901）:
     └── adapter_class = "DoubaoRealtimeAdapter"（或 vendor="doubao" 自动匹配）

扩展流程:
  2a. OpenAI 系厂商复用密钥链（case_config → meta → env OPENAI_API_KEY），
      新厂商如需其他鉴权方式仅在 _build_connect_headers 内实现
  4a. P3 迁移窗口期：注册表随 api_adapter_service 并入 api_test_service，
      register 调用点同步迁移，(protocol, vendor) 键不变，apis 表配置无需变更
  5a. 自动匹配冲突（同 (protocol, vendor) 多实现）→ 启动期抛错，强制显式 adapter_class

验收标准:
  ├── 新厂商适配器只新增一个子类文件，基类 / executor / 工厂零改动（OCP 验证）
  ├── 归一化事件 11 种全覆盖，executor 只见归一化事件
  ├── 帧结果与最终结果经基类统一属性输出（UC-1002 契约不变）
  └── vendor / 事件类型均枚举化，无魔法字符串/硬编码

Postcondition: 新厂商适配器注册即生效，UC-0901 下拉可选，执行链路自动路由
```

### 厂商适配职责矩阵（与源文档一致）

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

## 附录 A：V9.7.31 适配差异清单（与源 v3.0/v3.1 对照）

| # | 差异点 | 源文档（V9.7.10 单体） | V9.7.31（微服务 + 分布式） |
|---|---|---|---|
| 1 | 执行路由 | 单体内 executor 直调 | task_service `_dispatch_case_by_type`（task_dispatch.py）→ gRPC 分发 e2e_test_service / api_test_service |
| 2 | 类型语义 | `task.type=e2e / realtime_api` 分支 | 废弃 task.type / test_type；`task_case_relations.device_type`（新增）承载，TaskType 不引入 'realtime_api' |
| 3 | 混音 | 消费侧 AudioStreamOrchestrator | 下沉 audio_service，新增 server-streaming RPC `RenderAudioStream`（audio_service.proto 现无此 RPC，标新增） |
| 4 | 物理设备互斥 | 进程内 dict | Redis `DistributedLock` / `DistributedSemaphore`（distributed_coordinator.py） |
| 5 | 事件推送 | log_and_emit 直发 Socket.IO | Redis EventBus（EventChannel/EventType 枚举）发布 → api_gateway 订阅 → Socket.IO 房间（task_id 隔离） |
| 6 | 多实例 | 无 | api_test_service replicas:2 + worker_instance_id + RedisServiceRegistry TTL 心跳 + 孤儿任务收养 |
| 7 | UC-1001 | 厂商事件字段隔离 | 调整为多任务并发事件隔离；厂商归一化并入 UC-1003 |
| 8 | UC-1002 | 帧结果 + 最终结果保留 | frame/summary 双通道实时获取（frame 不落库，summary 落库触发评估） |
| 9 | API 表 | 单体共享模型 | `apis` 归 api_test_service（api_models.py），device_type/adapter_class/audio_config/output_types 列（新增） |
| 10 | SPL 映射 | 与设备 SPL 混同 | `ApiRmsSplMapping` 聚合（表 api_rms_spl_mappings，新增）按 DDD 五层落位 api_test_service + gRPC `ApiRmsSplConfigService`（新增）+ `/api/digital-spl` 蓝图（新增）；校准互斥 Redis 锁 |
| 11 | 前端 | 单体组件直调 | DDD 四层（views/components → composables/store(Ports) → domain/model+enums → api/adapters/dto/http）；SPLMapping 五层对称模板；enums.ts 补 DeviceType/OutputType/CalibrationStatus（新增） |
| 12 | 适配器归属 | api_adapter_service 独立服务(5008) | P3 下线并入 api_test_service，APIAdapterFactory 注册表随迁 |
| 13 | 密钥管理 | 单体内配置 | OpenAI 密钥链：case_config → meta → env OPENAI_API_KEY 逐级回退，日志零明文 |
| 14 | 枚举与配置 | 局部枚举、少量魔法值 | 枚举统一入 shared/models/common_enums.py + shared/utils/status_constants.py；前端 frontend/src/domain/enums.ts；阈值/频道名/锁 TTL 全配置化，拒绝魔法数字/硬编码 |
| 15 | 执行器基座 | 各 executor 自行实现 | 统一 BaseExecutor（shared/infrastructure/base_executor/_base.py，五 mixin）+ worker_instance_id |

