# API测试功能设计文档

| 项目 | 内容 |
| --- | --- |
| 版本 | v3.0（V9.7.31 适配版，2026-09-10，按测试执行 v3.0 设计修订） |
| 所属域 | 测试执行 · API 测试 |
| 口径基准 | 同目录 `01_UseCase总览.md`、`02_架构设计.md`、`05_路由与废弃.md`（如与本篇冲突，以三者为准） |
| 关联文档 | `06_评估与前端.md`、`07_流式推送与结果获取.md`、`08_混音与SPL映射.md` |
| 适用仓库 | `d:\00_code\V9.7.31\Intelligent-Audio-TEST` |

---

## 修订说明（v3.0）

【适配说明】本文档为 V9.7.31 独有旧文档（V9.7.10 无对应文件），原文基于「Flask 单体 + Flask-SocketIO + WebSocket 直连（`ws://localhost:5000/ws/api-test`）+ asyncio 并发压测（ConcurrentApiTester），以 QPS/RTT/SLA 为核心指标」的旧设计。本轮保留"API 测试功能设计"整体定位与 12 章骨架，将全部执行语义替换为「测试执行 v3.0」并落位 V9.7.31 微服务拓扑：

| # | 修订点 | v3.0 语义 |
| --- | --- | --- |
| 1 | 执行路由 | `device_type`（physical / http_api / websocket_api）为唯一路由依据；废弃 `task.type` / `test_type` 字符串判断；`TaskType` 不引入 `'realtime_api'` |
| 2 | 执行链路 | api_gateway:5000 → task_service:5001（`_dispatch_api_case`）→ Redis `task:queue` → api_test_service:5003（replicas:2，`worker_instance_id` 归属 + `RedisServiceRegistry` 心跳 + 孤儿收养）→ `HttpAPIAdapter` / `HttpStreamAdapter` / Realtime 三级体系（`ApiVendorAdapter` → `RealtimeAdapterBase` → `OpenAIRealtimeAdapter`）按 `(protocol, vendor)` 注册表 |
| 3 | 混音 | audio_service gRPC:50052 新增 server-streaming RPC `RenderAudioStream`（新增）；离线混音 6 步 → 100ms base64 chunk；`AudioFormatAdapter` 格式适配到 `api.audio_config` |
| 4 | SPL | `ApiRmsSplMapping` 聚合 + `api_rms_spl_mappings` 表（新增）；`SPLMappingService.spl_to_gain` 多点插值；`/api/digital-spl` 路由（新增）；校准互斥 `DistributedLock` |
| 5 | Realtime | `RealtimeSessionExecutor`（新增）：生产者-消费者事件队列、frame/summary 双通道、barge-in 打断检测、`RealtimeFrameType` 归一化事件（新增枚举） |
| 6 | 事件 | Redis EventBus → api_gateway 订阅 → Socket.IO `task_id` 房间；**不再直连 WebSocket** |
| 7 | 评估 | evaluation_service:5004 经 EventBus 订阅；result_type 映射（`'api'` / `'realtime'` 新增）；`CASE_EVALUATION_COMPLETED` |
| 8 | 数据模型 | `api_models.py` API 类新增 device_type / adapter_class / audio_config / output_types 四列；`StartAPITestRequest` 新增 device_type |
| 9 | 枚举 | `shared/models/common_enums.py` 与 `frontend/src/domain/enums.ts` 同步新增 DeviceType / OutputType / CalibrationStatus |
| 10 | 密钥链 | OpenAI 密钥：case_config → meta → env `OPENAI_API_KEY` 逐级回退 |
| 11 | 前端 | DDD 四层镜像，Infrastructure 唯一知道 snake_case；SPLMapping 五层对称模板为页面模板 |
| 12 | 网络代理 | `apis` 新增 `proxy_type` / `proxy_url` 两列（NULL=不用代理）；被测 API 请求面（HTTP / WS / 健康检查 / adapter 服务）统一走代理（INT-839，实现演进裁定 2026-10-19） |
| 13 | 依赖 | `requirements.txt` 新增 PySocks（requests socks 支持）+ websockets socks 代理依赖（INT-839） |
| 14 | 脱敏 | `shared/utils/secret_mask.py` 扩展掩码 `proxy_url` 值内 `user:pass` 段、保留 host:port（INT-839） |
| 15 | 输出调输入节奏 | Realtime 输入推流按被测实时输出事件调节奏：`RealtimePacingStrategy` 枚举（fixed / wait_turn_end / allow_barge_in / timeout_fallback）+ `_pacing_gate` 事件→决策映射 + `RealtimePacingService` 解析（case_config.pacing → meta.pacing → realtime_session 全局 → 默认，FIXED 与动态互斥）（INT-475，详见 `07_流式推送与结果获取.md` 附录） |
| 16 | 实机接入 | 新增用户说明《`doc/实机接入指南_API与Realtime测试.md`》+ 网页文档页 `docs/实机接入指南_网页文档页.html`：被测 API / REALTIME API 提供方如何接入本平台跑测试（配置字段、rounds、建任务执行、mock_dut :5096 / mock_realtime_api :5098 联调、常见问题） |
| 17 | Realtime 新架构回写（2026-10-22，同步 INT-497 / INT-1299） | Realtime 章节按最新架构更新：适配器三级体系（`ApiVendorAdapter` Port → `RealtimeAdapterBase` 协议级 base → `OpenAIRealtimeAdapter` 品牌类）+ 特殊化覆写落点表（pre_process / recv / output+post_process / wait_ai_* / _build_client）；`registry.resolve_for(protocol, flat_key)` 表驱动分发（新厂商 = 枚举 + `_FLAT_KEY_DIMENSIONS` 一行 + `@register_vendor_adapter` 类，执行器零改动）；轮次语义 `RealtimeAdapterBase.resolve_round_mode`（`_as_bool` 兼容 int/bool/str）+ 厂商方言覆写；评估字段走 field_mapper 配置透传（与 E2E/HTTP 同构，不写代码枚举）；打断/拒识口径（打断轮 = `is_interruption` + `interruption_delay_ms` + barge-in 窗口；推流中打断 = `allow_barge_in` 节奏策略；拒识 = 评估侧 `reject_judge`，适配器如实采集轮次结果）。见 §3.6 |
| 18 | 密钥池 | `apis.api_endpoints[].api_keys` 每端点密钥池（JSON 字符串数组），执行时按当前端点 round-robin 轮换 + 401/403/429 失败降级（冷却期默认 60s 可配），Realtime 与普通 HTTP 通用；逐端点 `api_keys_summary`（count + 尾号）摘要、完整密钥零响应；未配池回退单值链，行为与现状一致（INT-1173 / INT-1177 / INT-1178，负责人裁定 2026-10-22，见 3.10） |

原文档第 7 章中 QPS / RTT / SLA / 并发压测等通用性能指标**保留**，标注见 7.1 节。

---

## 1. 概述

### 1.1 文档目的

本文档描述 V9.7.31「API 测试」子域的功能设计：以被测 API（HTTP / HTTP 流式 / Realtime WebSocket）为被测对象，在微服务拓扑下完成任务路由、适配器执行、混音下发、SPL 数字增益映射、实时推送与结果评估的端到端设计。本文档是 `01_测试执行/` 文档族的 API 侧专项设计，执行语义遵循 v3.0 总体设计。

### 1.2 功能范围与 UseCase 映射

| UC | 名称 | 本文落位 |
| --- | --- | --- |
| UC-0901 | 被测 API 管理（CRUD + 连接测试） | 3.1 |
| UC-0902 | RMS SPL 映射校准（API 侧数字增益） | 3.5 |
| UC-0903 | 创建任务关联设备（device_type 判定） | 2.4 / 6.2 |
| UC-1001 | 事件隔离（task_id 房间） | 2.6 |
| UC-1002 | frame / summary 双通道 | 3.6 |
| UC-1003 | 新增厂商适配器（注册表扩展点） | 3.2 |

### 1.3 术语表

| 术语 | 含义 |
| --- | --- |
| device_type | 设备/执行类型三值枚举：physical（物理设备）、http_api（HTTP API）、websocket_api（Realtime WS API） |
| adapter_class | API 聚合上的显式适配器类名，非空时在适配器注册表中优先 |
| audio_config | API 聚合上的目标音频格式配置（采样率/位深/声道），供 AudioFormatAdapter 适配 |
| output_types | API 聚合上声明的产出类型集合（OutputType） |
| worker_instance_id | 任务在多副本 api_test_service 中的归属实例标识 |
| frame 通道 | Realtime 会话的实时帧事件流：不落库，仅经 Socket.IO 推送 |
| summary 通道 | Realtime 会话的汇总结果：落库 + 对象存储，触发评估 |
| barge-in | 用户开口打断 AI 播报；由 `user_speech_started` 触发打断检测 |
| RealtimeFrameType | Realtime 归一化事件枚举（`shared/models/common_enums.py`，新增，前端 `frontend/src/domain/enums.ts` 镜像） |
| RenderAudioStream | audio_service 新增的 server-streaming 混音渲染 RPC（新增） |
| ApiRmsSplMapping | API 侧 RMS→SPL 映射聚合（新增），物理侧对称物为 SPLMapping |
| 孤儿收养 | `_adopt_orphan_tasks`：worker 接管心跳过期实例遗留任务（见 02_架构设计.md） |
| proxy_type | 被测 API 网络代理类型枚举（INT-839）：http / https / socks5 / socks5h；NULL 或空 = 不用代理 |
| proxy_url | 被测 API 网络代理地址 `[user:pass@]host:port`（不含 scheme，INT-839）；配置代理时认证段必填 |

### 1.4 架构原则

- DDD + CQRS + 微服务 + Redis 分布式（无 MQ）；先重构（路由/DDL/枚举），再管消费方。
- 枚举化、配置化：禁止魔法数字、魔法字符串、硬编码；端口经 `service_ports.py`、并发参数经 `concurrency_config.json` 管理。
- 分开发/生产环境配置（环境矩阵见 02_架构设计.md）。
- 前端 DDD 四层镜像：Infrastructure 层唯一知道 snake_case。

---

## 2. 系统架构设计

### 2.1 微服务落位【适配说明】

【适配说明】原文档"Flask + Flask-SocketIO 单体三层架构（表现/业务/数据）"废除，落位 V9.7.31 十二服务拓扑；端口统一由 `service_ports.py` 配置化管理，禁止硬编码。

| 服务 | 端口 | 与本文相关的职责 |
| --- | --- | --- |
| api_gateway | 5000 | 鉴权/对外路由；订阅 EventBus → Socket.IO 房间转发 |
| task_service | 5001 | 任务编排：`_dispatch_case_by_type` / `_dispatch_api_case` |
| e2e_test_service | 5002 | physical 链路端到端执行 |
| api_test_service | 5003 | **API 测试执行主体（部署 replicas:2）** |
| evaluation_service | 5004 | 结果评估（经 EventBus 订阅） |
| report_service | 5006 | 报告生成 |
| algorithm_service | 5007 | 算法支撑 |
| api_adapter_service | 5008 | 旧适配服务，其职责由 API 适配器注册表承接，P3 下线（INT-1176 已删除）【适配说明】 |
| auth_service | 5009 | 认证鉴权 |
| audio_service | gRPC:50052 | 混音（RenderAudioStream）、SPL（spl_to_gain）、播放 |
| device_service | gRPC:50053 | 物理设备管理 |

### 2.2 分层架构

- **后端**：Interface（proto / api_gateway）→ Application（executor / service 编排）→ Domain（聚合 / 枚举，零框架依赖）→ Infrastructure（persistence / adapter / redis / http）。
- **前端**：DDD 四层镜像（见 5.2）。

### 2.3 API 测试执行链路总览

```mermaid
sequenceDiagram
    autonumber
    participant FE as 前端（Presentation）
    participant GW as api_gateway:5000
    participant TS as task_service:5001
    participant R as Redis
    participant API as api_test_service:5003（replicas:2）
    participant EXT as 被测 API
    participant EV as EventBus（Redis）
    participant EVAL as evaluation_service:5004

    FE->>GW: StartAPITest（task_id, device_type）
    GW->>TS: gRPC StartAPITest
    TS->>TS: _dispatch_case_by_type（DeviceType 枚举判断）
    TS->>R: LPUSH task:queue
    API->>R: BRPOP task:queue（绑定 worker_instance_id）
    API->>R: RedisServiceRegistry 注册 + 心跳（TTL 15s）
    API->>EXT: HttpAPIAdapter / HttpStreamAdapter / Realtime 三级体系（RealtimeAdapterBase → OpenAIRealtimeAdapter）
    EXT-->>API: 响应 / 流 / 归一化事件
    API->>EV: 发布 frame（实时）/ summary（落库）事件
    GW->>EV: 订阅
    GW-->>FE: Socket.IO 推送（room = task_id）
    EV-->>EVAL: summary 事件订阅
    EVAL->>EV: 发布 CASE_EVALUATION_COMPLETED
```

### 2.4 执行路由：device_type 三值【适配说明】

【适配说明】v3.0 以 `device_type` 为**唯一**路由依据。现状代码为魔法字符串判断，属待消除坏味道：

- 现状：`task_service/core/execution_engine/mixins/task_dispatch.py`
  - L89 `_dispatch_case_by_type`（路由入口，改造后按 `DeviceType` 枚举分派）
  - L91 `if task.type == 'api'`（魔法字符串，废弃）
  - L96 `_dispatch_api_case`（保留，目标：api_test_service）
  - L112 `_dispatch_e2e_case`（保留，目标：e2e_test_service）
  - L35 `task.type != 'api'`（魔法字符串，废弃）
- 数据侧：`task_service/infrastructure/persistence/models/task_models.py` L84 `TaskCase` **已有** `device_id` 列（L111），新增 `device_type` 列。
- 枚举侧：`TaskType` **不引入** `'realtime_api'`；`frontend/src/domain/enums.ts` L24 `TaskType` 保持既有取值，Realtime 语义由 `DeviceType.WEBSOCKET_API` 承担。

路由决策表：

| device_type | 分派方法 | 执行服务 | 适配器 | 说明 |
| --- | --- | --- | --- | --- |
| physical | `_dispatch_e2e_case` | e2e_test_service:5002 | — | 走 audio/device gRPC 物理链路 |
| http_api | `_dispatch_api_case` | api_test_service:5003 | HttpAPIAdapter / HttpStreamAdapter | 一问一答 / 流式 |
| websocket_api | `_dispatch_api_case` | api_test_service:5003 | Realtime 三级体系（`RealtimeAdapterBase` → `OpenAIRealtimeAdapter`） | WS 长连接，实例内闭环 |

废弃清单（节选，完整 9 项见 `05_路由与废弃.md`）：

1. `task.type == 'api'` / `task.type != 'api'` 字符串判断（task_dispatch.py L91 / L35）；
2. `test_type` 请求参数（proto 请求体）；
3. WebSocket 直连 `ws://localhost:5000/ws/api-test`（改 Socket.IO 房间）；
4. api_adapter_service:5008 独立适配服务（P3 下线，INT-1176 已删除）。

### 2.5 多副本执行与任务归属（新增）

- api_test_service 部署 **replicas:2**，经 Redis `task:queue`（LPUSH / BRPOP）消费任务；
- 每个任务绑定 `worker_instance_id`，执行器经 `RedisServiceRegistry`（`shared/utils/service_registry.py` L16）注册，**TTL 15s 心跳**维持存活；
- 孤儿收养 `_adopt_orphan_tasks`：worker 周期扫描心跳过期实例遗留的任务并接管重派（机制详见 02_架构设计.md）；
- Realtime WS 长连接**实例内闭环 + 亲和路由**：会话期间该 task 的事件路由固定到持有连接的实例。

### 2.6 事件通道【适配说明】

【适配说明】废除原文档 Flask-SocketIO 单体内直连 WebSocket 的推送方式，改为 Redis EventBus 中转。

- 基础设施：`shared/utils/redis_pubsub.py` —— `EventChannel`（L21）、`EventType`（L30）、`RedisPubSub`（L51）、`EventBus`（L107）；
- 链路：api_test_service 执行器发布事件 → EventBus → api_gateway 订阅 → Socket.IO 房间（**room = task_id**）→ 前端；
- UC-1001 事件隔离由 task_id 房间实现；
- 频道规划与事件清单详见 `02_架构设计.md`；
- 评估链路复用同一 EventBus（见 3.7 / 6.4）。

---

## 3. 核心功能模块

### 3.1 被测 API 管理（UC-0901）

- gRPC 契约：`shared/proto/api_test_service.proto` 既有 RPC —— `StartAPITest`（L10）、`CreateAPITest`、`CreateAPIConfig`、`UpdateAPIConfig`、`DeleteAPIConfig`、`ListAPIConfigs`、`GetAPIConfig`、`TestAPIConnection`；
- 聚合：`api_test_service/infrastructure/persistence/models/api_models.py` L15 `class API`，既有列：`id / name / vendor / status / meta / algorithm_type / max_process / max_timeout / max_audio_duration / health_score / api_endpoints`（INT-1361：api_url 已移除，api_endpoints 为唯一端点配置入口）；
- 新增四列：`device_type / adapter_class / audio_config / output_types`（见 6.2）；再新增两列 `proxy_type / proxy_url`（INT-839，见 3.9）；
- 前端 API 编辑弹窗（CRUDFormModal / APIEditModal）提供代理类型下拉 + 地址输入，校验规则与后端同口径（见 3.9）；
- `health_score` 健康分与连接测试沿用，口径见 7.1【保留：通用性能测试口径】。

### 3.2 API 适配器工厂（新增）

- 注册表键：`(protocol, vendor)` 双键注册；`api.adapter_class` 显式指定时**优先**于约定键；
- 内置适配器：
  - **HttpAPIAdapter**：request/response 一问一答（非流式 HTTP）；
  - **HttpStreamAdapter**：HTTP 流式（SSE / chunked）；
  - **Realtime 三级体系**（INT-497，见 3.6）：`ApiVendorAdapter`（Port）→ `RealtimeAdapterBase`（协议级 base，`infrastructure/adapters/protocol/realtime_adapter_base.py`）→ 品牌适配器（`vendors/OpenAIRealtimeAdapter`）；RealtimeWSClient 作传输/状态机被组合复用；
- 适配器输出统一为 `AdapterOutput`（dataclass，定义见 `07_流式推送与结果获取.md`）；
- UC-1003 扩展点：新增厂商经注册表表驱动分发（`registry.resolve_for(protocol, flat_key)`，INT-1299）——新厂商 = `AdapterVendor`/`VendorAdapterType` 枚举 + `_FLAT_KEY_DIMENSIONS` 一行映射 + `@register_vendor_adapter` 类，执行器零改动；
- 【适配说明】承接旧 api_adapter_service:5008 的适配职责，后者 P3 下线（INT-1176 已删除）。

### 3.3 会话执行器

- 现状模块：`api_test_service/core/`（api_session_executor.py L33 `class APISessionExecutor`；另有 api_task_runner / api_concurrency_manager / api_executor / api_result_processor / session_context / api_test_service）；
- 骨架：BaseExecutor 五 Mixin —— `ControlMixin / LoggingMixin / ParamsMixin / ResultsMixin / DbMixin`（`shared/infrastructure/base_executor/_base.py`）；
- `RealtimeSessionExecutor`（`api_test_service/core/realtime_session_executor.py`，已落地，INT-497 最小接线），见 3.6。

### 3.4 混音与音频下发【适配说明】

- 承载服务：audio_service（gRPC:50052），既有 41 个 RPC（`PlayAudio` / `StopAudio` / `GetPlayStatus` / `GetAudioInfo` / `MeasureSPL` / `StartSPL` / `StopSPL` / `PrepareAudios` / `StartPlayback` / `StopPlayback` 等，`shared/proto/audio_service.proto`）；
- **新增** server-streaming RPC `RenderAudioStream`（现有 proto 无此方法）：

```proto
// shared/proto/audio_service.proto（新增）
rpc RenderAudioStream(RenderAudioStreamRequest) returns (stream AudioChunk);

message AudioChunk {
  int32  seq        = 1;  // 分片序号
  string pcm_base64 = 2;  // PCM 分片（base64）
  int64  offset_ms  = 3;  // 相对时间轴偏移
  bool   last       = 4;  // 终止分片标记
}
```

- 离线混音 6 步（audio_service 进程内完成）：
  1. 加载 PCM 素材；
  2. 格式适配：`AudioFormatAdapter` 按目标 `api.audio_config`（采样率/位深/声道）转换；
  3. RMS 补偿 + SPL 增益：经 `SPLMappingService.spl_to_gain` 多点插值（未配置时 gain = 1.0）；
  4. 多音轨时间轴编排；
  5. 混音叠加；
  6. 切片输出：每 1600 samples（≈ 100ms）一个 chunk → base64；
- 流式下发：`RenderAudioStream` 按 chunk 顺序推送，`last = true` 终止；
- 详见 `08_混音与SPL映射.md`。

### 3.5 SPL 数字增益映射（UC-0902，新增）

- 聚合：`ApiRmsSplMapping` —— API 侧 RMS→SPL 映射，与物理侧 `SPLMapping` **对称设计**（见 08）；
- 表：`api_rms_spl_mappings`（**新增建表**，完整 DDL 以 `05_路由与废弃.md` 为准）；
- 服务：`audio_service/infrastructure/audio/spl_service.py` —— L21 `SPLMappingService`、L34 `spl_to_gain(mapping_id, target_spl)` **多点插值**求增益；未配置映射时 gain = 1.0；
- 数据获取：audio_service 经 ACL **只读拉取**映射数据并本地缓存，不直连业务库；
- **【实现演进裁定 2026-10-14，INT-323 代码核验】上两行的落位/取数与实现不符**：API 侧增益计算实际在 `audio_service/domain/services/api_rms_spl_service.py`（`ApiRmsSplService.spl_to_gain/_by_mapping`，由 `audio_stream_orchestrator.py:167` 在混音 Step 3b 调用；上行的 `spl_service.py` `SPLMappingService` 是 E2E 物理侧服务，非本 UC）；映射数据不经 ACL 拉取，由 api_test_service `round_render_service.py` 预载 dict 随每轮 `RenderAudioStream/File` 的 `render_config` 传入（聚合/表/写路径仍在 api_test_service，本节其余内容不变）；
- 路由：`/api/digital-spl`（**新增**，经 api_gateway 暴露）；
- 校准互斥：`DistributedLock`（`shared/utils/distributed_coordinator.py` L67），

```python
DistributedLock(key=f"calibration:api_rms_spl:{api_id}:{mapping_id}", ttl=30)
```

- 校准状态流转：`CalibrationStatus` 枚举（新增，见 6.4）。

### 3.6 Realtime 实时会话（新增）

- 执行器：`RealtimeSessionExecutor`（`api_test_service/core/realtime_session_executor.py`），**生产者-消费者**事件队列：`_recv_loop` daemon 线程收包 → `queue.Queue` → 主循环 `recv()` 消费；
- 归一化事件：`RealtimeFrameType` 枚举（`shared/models/common_enums.py`，前端 `frontend/src/domain/enums.ts` 镜像），厂商原始事件经 `RealtimeWSClient._parse_event` + `_EVENT_TYPE_MAP` 归一化（默认 OpenAI 事件协议）；
- **适配器三级体系**（INT-497）：
  - `ApiVendorAdapter`（Port，`domain/ports/api_vendor_adapter.py`）→ `RealtimeAdapterBase`（协议级 base，`infrastructure/adapters/protocol/realtime_adapter_base.py`）→ 品牌适配器（`vendors/OpenAIRealtimeAdapter`，零覆写样例：仅 `protocol` / `vendor` / `adapter_type` / `display_name` / `_transport_vendor` 五类属性）；
  - 组合复用 `RealtimeWSClient`（`infrastructure/adapters/transport/realtime_ws_client.py`）为传输/状态机，暴露同形方法面（connect / pre_process / send / recv / output / close）；
  - **特殊化覆写落点**（新厂商在此选覆写点，其余继承）：`pre_process`（握手/session.update 载荷）、`recv`（事件归一化，打断依赖 `user_speech_started` ↔ 厂商打断事件、`response_cancelled` ↔ 厂商取消回复事件）、`output`+`post_process`（聚合）、`wait_ai_speaking`+`wait_ai_complete`（等待语义）、`_build_client`（私有传输替换）；配置级差异（URL / 密钥 / 代理 / session_config / audio_config）走 `api.meta` 不写代码；
- **表驱动分发**（INT-1299）：`RealtimeSessionExecutor._resolve_realtime_transport` 查 `vendor_adapter_registry.resolve_for(AdapterProtocol.REALTIME, a_type)`（`registry.py`）——命中 → 严格分发（fallback=False）；未命中（未配置 / API_DRIVER / MOCK）→ 回退 `RealtimeWSClient` 默认构造。新厂商 = `AdapterVendor`/`VendorAdapterType` 枚举 + `_FLAT_KEY_DIMENSIONS` 一行 + `@register_vendor_adapter` 类，执行器零改动；
- **字段归一化**（INT-1299）：轮次语义 `RealtimeAdapterBase.resolve_round_mode`（默认实现 `_as_bool` 兼容 int/bool/str，参照 `harmony_xiaoyichat._as_bool`）+ 厂商方言覆写；评估字段走 field_mapper 配置透传（与 E2E/HTTP 同构）：评估入参遍历 `field_mappings['original']['evaluation']['output']`（param_mapping source_param→target_param，case/reference 源取 round_config、api 源取轮次输出），`answer` 等按 api 输出字段定义取（output_field_keys），别名兜底（question/query）收敛到算法 param_mapping 配置，代码无硬编码字段名；
- frame / summary 双通道（UC-1002）：
  - **frame**：不落库，`event_listener`（`_on_frame` 回调）逐帧经 EventBus → Socket.IO（room = task_id）实时推送前端渲染（异步观测，不参与停止）；
  - **summary**：会话汇总落库 + AI 输出音频归档（`audios/{task}/realtime/ai_output_*.wav`），触发评估；
- 打断/拒识口径（INT-1299）：
  - **打断轮**（`is_interruption` 用例配置）：等 AI 开口 → `interruption_delay_ms`（默认 1000）延时 → 推打断音频 → `barge_in_window_seconds=5` 检测窗口内等 `user_speech_started` / `response_cancelled` → 等 AI 重新回复；
  - **推流中打断** = `ALLOW_BARGE_IN` 节奏策略（INT-475）：输入推流中模型提前回话/打断 → `_pacing_gate` 返回 `interrupt` → 收敛输入推流；
  - **拒识** = 评估侧 `reject_judge` 判定（裁判族维度），适配器只需如实采集轮次结果（output.text / audio / 是否开口），无需特殊逻辑；
- **轮次成败语义**：起始窗口（`ai_start_timeout_seconds=25`）内无 `ai_audio_delta` → 「AI 未回复」轮失败；已开口仅表明通过起始窗口，收尾事件（`ai_audio_done`）须在 `ai_complete_timeout_seconds=60` 内到达，否则轮失败「AI 回复未在超时内完成」（`wait_ai_complete` + `success = bool(complete and output['ai_complete'])`）；
- 连接管理：WS 长连接实例内闭环 + 亲和路由（见 2.5，`RealtimeSessionRegistry.route_or_bind` / `bind_ttl_seconds=3600`）。

### 3.7 密钥与配置（新增）

- OpenAI 密钥链（逐级回退）：`case_config`（用例配置）→ `meta`（`api_models.API.meta`）→ 环境变量 `OPENAI_API_KEY`；
- 密钥不落日志、不进报告；密钥解析统一收敛在 Infrastructure 层密钥提供者，Domain 层只见解析结果。
- 端点级多密钥池（每端点 `api_keys` 轮换，Realtime + HTTP 通用）：见 3.10（INT-1173 / INT-1177 / INT-1178，负责人裁定 2026-10-22）。

### 3.8 停止立即生效与执行中删除用例联动【负责人裁定口径】

> 【负责人裁定 2026-10-13（INT-308 原话），2026-10-14 补录】API 会话链路（http_api / websocket_api）与 E2E 链路同口径：任务停止必须**立即生效**，全链路感知延迟目标 **< 5s**（实测值随 INT-308 验收回填）；执行中删除用例必须联动评估侧清理。

**停止语义分层**（stop = 三步，不等待自然完成）：

1. **中断当前轮次**：正在进行的 API 调用 / Realtime 会话轮次立即 abort，音频流推送立即停止，不等待当前轮次自然完成；
2. **队列清空**：待执行用例全部不再分发，已领取未启动的用例直接落停止终态；
3. **状态落 terminal**：任务状态立即落终态（stopped），不卡在 running。

**全链路 stop_event 传播**：跨进程停止信号以 **Redis 标志位为权威通道**——task_service 停止时置 `task:stop:{task_id}`（`task_service/.../task_control.py` → `shared/utils/distributed_coordinator.py`），api_test_service 执行器（BaseExecutor `ControlMixin`，`shared/infrastructure/base_executor/_control_mixin.py`）经 `_handle_control` 先查 Redis 标志位再查本地 Event（本地 `stop_flags` 由 `StopAPITest` RPC 置位）；所有等待点拆片（0.5s 片）可中断。

**轮次粒度检查点**：APISessionExecutor / RealtimeSessionExecutor 在每个会话轮次 / 每次 API 调用前后检查停止信号（检查点遍布 `api_executor.py` / `api_session_executor.py` / `api_result_processor.py`），Realtime 等待带 stop_check 回调（`realtime_session_executor.py`）；单轮次为最小中断单位，轮次内靠音频流停推与调用 abort 达成"立即"。

**执行中删除用例联动评估侧**：同 E2E 口径（见 `端到端测试功能设计文档.md` §3.1.3）——已提交评估的用例删除时取消评估任务，评估中则中断 + 结果丢弃 + 审计事件，走 gRPC + 事件通道且幂等。

### 3.9 被测 API 网络代理（INT-839，新增）

被测 API 支持网络代理配置，请求被测 API 时统一走代理（HTTP / WS / 健康检查 / adapter 服务四类请求面；不影响音频 OSS/存储直传）。

**数据模型**（`apis` 表新增两列，NULL 或空 = 不用代理）：

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `proxy_type` | VARCHAR(20) NULL | 枚举 http / https / socks5 / socks5h；NULL 或空 = 不用代理 |
| `proxy_url` | VARCHAR(255) NULL | `[user:pass@]host:port`，不含 scheme；配置代理时认证段必填 |

**校验规则**（前后端同口径，后端 `api_test_service/infrastructure/adapters/proxy_utils.py` `validate_proxy` / 前端 `frontend/src/utils/proxyValidation.ts` 镜像）：

- `proxy_type` 为空 → `proxy_url` 必须为空；
- `proxy_type` 非空 → 必须是 http / https / socks5 / socks5h，`proxy_url` 必填且带 `user:pass@` 认证段；
- `proxy_url` 不含 scheme 前缀（带则源头拒绝，避免执行侧拼双重 scheme 与脱敏失效）；端口若存在必须为数字。

**执行链路代理行为**（后端拼完整 URL `{proxy_type}://{proxy_url}` 分发）：

| 请求面 | 传输实现 | 代理参数 |
| --- | --- | --- |
| HTTP 执行（`api_client._call_http`） | `requests` | `proxies={'http': url, 'https': url}`，凭据内嵌 URL |
| HTTP 会话直接路由（`api_session_executor._send_direct`，`meta.use_adapter=false` 时多轮 HTTP 直发） | `requests` | 同 `_call_http`：`proxies={'http': url, 'https': url}` |
| WS 执行（`api_client._call_websocket`） | websocket-client | `http_proxy_host/port` + `http_proxy_auth=(user, pass)` + `proxy_type` 映射（http→http、socks5→socks5、socks5h→socks5h；https 代理端点走 http CONNECT 隧道语义） |
| Realtime WS（`realtime_ws_client.connect()`，websocket_api 实际执行路径） | websocket-client | 同 `_call_websocket` 同套参数，url 分解复用 `proxy_utils` |
| 健康检查双分支（`api_crud_service.test_connection`） | http/https → `requests.get`（proxies）；ws/wss → 裸 `websocket.WebSocket().connect` | 同上 |
| adapter 服务四件（`http_adapter` / `sse_adapter` / `qwen_adapter` / `volc_ast_adapter`） | http/sse → `requests.post`（proxies）；qwen/volc → `websockets.connect(proxy=url)` | 跨服务透传：`api_session_executor` vendor_config 构建显式携带 → `api_test_service` gRPC servicer + REST 双胞胎白名单 merge |

**跨服务透传三落点**：`api_test_service/core/api_session_executor.py` vendor_config 构建（`proxy_type` / `proxy_url` 显式加入）→ `api_test_service/interfaces/grpc/servicers.py` 白名单 merge → `api_test_service/routes/api.py` REST 双胞胎。任一落点漏加都会造成「配置能存、执行/检查不过代理」假象，三处必须同步。

**依赖变更**：`requirements.txt` 新增 `PySocks>=1.7.1`（requests socks 支持）与 websockets socks 代理依赖；不新增 socks4（遗留协议不做）。

**日志脱敏**：`shared/utils/secret_mask.py` 扩展掩码 `proxy_url` 值内 `user:pass` 段（保留 host:port 便于排查），覆盖文本日志（`mask_text`）与结构化 payload（`mask_mapping`）；adapter 侧 `utils/proxy.py` 对 websockets 异常消息做 userinfo 掩码（`mask_proxy_userinfo` / `masked_exc_info`），日志与异常上下文不出现明文凭据。

### 3.10 被测 API 密钥池（endpoint 级）（INT-1173 / INT-1177 / INT-1178，负责人裁定 2026-10-22）

被测 API 支持**端点级多密钥配置与轮换**：每个 `api_endpoints[]` 条目可配一个密钥池（`api_keys` 字符串数组），执行时按**当前选定端点**的密钥池轮换（round-robin + 401/403/429 失败降级 + 冷却期默认 60s），Realtime 与普通 HTTP 通用。本能力为 3.7 单值密钥链的端点级扩展：**未配 `api_keys` 的端点完全回退现有单值链（`case_config.api_key → meta.api_key → 服务配置层 → env`），行为与现状一致。**

#### 3.10.1 数据模型与校验

- 挂载点：`apis.api_endpoints[].api_keys`（JSON 字符串数组），**每个端点一个密钥池**，不是 API 级（INT-1230 审计 D1' 端点级返工口径）；一个 API 的多个端点可各自配自己的密钥池。
- 字段形态：纯字符串数组；元素去首尾空白后非空；**去重**；数量上限 **≤ 20**（`api_crud_service._MAX_API_KEYS = 20`）。
- 端点级单值 `api_key` 视为池单例：端点配置 `api_keys` 为单元素数组时即等价端点单值密钥（轮换池只有 1 个 key，round-robin 恒选该 key）；未配 `api_keys`（无数组/空数组）时回退单值链。
- 写侧校验（`APICrudService._validate_api_keys` / `_validate_endpoint_obj`，create / update 每端点逐条校验）：
  - 必须为字符串数组（非数组拒绝）；
  - 元素必须为非空字符串（strip 后非空）；
  - 元素不能重复（strip 后去重）；
  - 数量 ≤ 20。
- **写侧拒收摘要字段**：create / update 均拒收顶层与端点级 `api_keys_summary`（`_build_endpoints_list` 与 `_api_to_dict` 均剥除），摘要为读侧派生，防前端回传污染存储。
- **更新合并语义**（endpoint 级返工 INT-1230 审计 D2'/D6'）：读侧剥离完整 `api_keys`，编辑表单拿不到池、回传端点必无 `api_keys`——整块覆盖会静默清空既有池。故 update 合并按 **endpoint URL 匹配**保留既有池：入参端点未含 `api_keys` 时保留既有池，显式传完整数组才覆盖。

#### 3.10.2 解析与轮换策略（`shared/utils/api_key_provider.py`）

- 扩展函数 **`ApiKeyChainResolver.resolve_rotating(rotation_key, endpoint, case_config, service_candidates, case_value, meta_value, meta)`**（`resolve()` 单值语义保持不变，向后兼容零回归）：
  - 候选优先级：**case 层单值（最高优先，不变）→ 当前端点 `api_keys` 轮换池 → 单值回退链（`meta.api_key` → 服务配置层 → env）**。
  - 轮换 key = **`endpoint_rotation_key(api_id, endpoint base URL)`**（INT-1230 审计 D3'）：用 URL 而非索引，增删端点不漂移；同一 base URL 的 HTTP 与 Realtime 共享游标（**跨协议同源轮换**），不同端点各用各池不串扰。
- **round-robin**：`RotationStateStore.next_index` 按 `(api_id, endpoint_url)` 维度维护游标，顺序取下一个非冷却 key；全冷却返回 -1（`resolve_rotating` 返回空串，调用方不注入 Authorization → 立即失败语义）。
- **失败降级判定面**：HTTP status ∈ **{401, 403, 429}**；Realtime WS 握手异常（`last_handshake_status`）同集合（`_ROTATION_TRIGGER_STATUS_CODES = {401, 403, 429}`）。命中后经 `report_failure(rotation_key, key)` 置冷却。
- **冷却期**：默认 **60s**（`DEFAULT_COOLDOWN_SECONDS`），可配置（`resolver_from_config` 读 `cooldown_seconds`，`ApiKeyChainResolver(cooldown_seconds=...)` 可注入）；冷却期内不选中该 key，冷却到期自动恢复。
- **重试上限** = 当前端点池内 key 总数（有界）；**池全冷却立即失败**（不空转等待）。
- **5xx / 网络错误不轮换**（非账号配额问题，立即失败）。
- **并发安全**：`RotationStateStore` 抽象为端口（首版进程内 `InMemoryRotationStateStore`，`threading.Lock` 保护游标 + 冷却集合；Redis 跨副本实现列后续增强），模块级共享单例 `get_rotation_store()` —— 所有消费面（HTTP / Realtime / 多线程执行）经同一模块引用同一单例，轮换计数不错乱。

#### 3.10.3 消费面（均消费**当前端点**的密钥池）

| 消费面 | 实现位置 | 轮换 key | 失败降级 |
| --- | --- | --- | --- |
| HTTP 请求头 | `ApiDriverAdapter._merge_headers`（`api_driver_adapter.py`） | `(api_config.id, 当前端点 base URL)` | `_call_api_with_key_rotation`：响应 401/403/429 → 报告失败 → 重解析下一非冷却 key 重试；上限 = 池内 key 数；**仅池内 key 触发轮换**（case 单值 / 显式 Authorization / 无池不轮换，立即失败）；5xx/网络错误不轮换；无池退化为单次调用 |
| HTTP 内嵌 chat 路径 | `ApiDriverAdapter.execute_voice_llm_chat` → `_call_api_with_key_rotation`（INT-1178） | 同上（`_send_via_adapter` 内嵌执行） | 同上；`X-Session-Id` 等其余头原样保留，仅替换 Authorization |
| Realtime WS 握手头 | `RealtimeAdapterBase._resolve_ws_headers`（`realtime_adapter_base.py`） | `(api_config.id, 当前 ws 端点 URL)` | `_connect_with_rotation`：握手 401/403/429 → 报告失败 → 重建 client 取下一非冷却 key；上限 = 池内 key 数；池全冷却立即抛错；5xx/网络错误不轮换 |

- **端点身份解析**：HTTP 侧 `_current_endpoint()` 按 `self.endpoint`（含 path）对 `api_config.api_endpoints` 做 base 前缀最长匹配，未匹配（main url 单端点/未配端点）返回 None → 回退单值链；Realtime 侧 `_resolve_ws_endpoint()` 取 `api_endpoints` 中 ws://wss:// 条目（无则回退单端点包装），无 ws 端点返回 None → 回退单值链。
- case 层单值最高优先不变（Realtime `_connect_with_rotation` 检测到 case 层 key 即单次连接，不轮换）。

#### 3.10.4 响应摘要与安全

- **响应摘要（读侧，完整密钥零响应）**：`_api_to_dict` 逐端点内嵌 `api_keys_summary = {count, tails[]}`（count + 每个 key 尾号 4 位），完整 `api_keys` 一律不输出（`redact_endpoint_keys` / `derive_api_keys_summary` / `derive_endpoint_keys_summary`，`domain/entities/api.py`）；聚合根 `APIAggregate` 承载摘要而非完整密钥，PO 原始态读侧防御剥离。
- **脱敏**（`shared/utils/secret_mask.py`）：敏感键集合新增 **`api_keys`**（复数）及 `*_api_keys` 后缀（与单数 `_api_key` 平行）；`mask_text` 对 `api_keys=["sk-a","sk-b"]` JSON 数组形态**整数组掩 `****`**（零明文且不拆坏数组结构），`mask_mapping` 对结构化 payload 中 `api_keys` 键整值掩码；sk- 与非 sk- 密钥均覆盖。
- 明文存储口径：`api_keys` 与现状 `api_endpoints` / `meta.api_key` 一致明文落库（DB 权限面需知悉）；响应、日志、前端不回显完整密钥。

#### 3.10.5 前端（`frontend/src`）

- **端点行内多行 textarea**（`ArrayField` 组件，`arrayItemTemplate` 含 `apiKeys` 时渲染密钥池块）：每行一个 key，可**整段粘贴自动拆行**，非空行校验（`apiConfigAdapter` 按 `\r?\n` 拆分 → trim → 过滤空行）。
- **编辑回显不出现完整密钥**：读侧只拿到 `api_keys_summary`（count + 尾号），textarea 草稿 `apiKeysText` 仅表单瞬态，保存时 adapter 层拆行转 `api_keys` 落库，留空保存保留既有池；显式 `apiKeys`（防御映射）同样转 `api_keys`。
- **现有单值输入兼容**：`meta.api_key`（单值）保留为回退链最高级 API 级候选，未配端点池时行为与现状一致；`APIEditModal` 保留单值密钥输入。
- **`ArrayField` 密钥池能力开关**（INT-1177 返工(4)）：仅 `arrayItemTemplate` 含 `apiKeys`（或显式 `arrayKeysEnabled`）时渲染端点行内密钥池块——**评估维度 `apiEndpoints` 字段（模板无 apiKeys）不渲染密钥池 UI**，避免泄漏密钥池配置面。
- 前端落地范围：INT-1177 交付实现于旧 Vue `frontend/`（该分支基线含旧 Vue）；2026-10-22 负责人「旧 Vue 直接废弃」裁定后，React / 新 Vue 接线未含密钥池 UI（API 配置编辑沿用单值），密钥池接口能力已就绪，前端接线待相应接线项目排期（不在本卡范围）。

#### 3.10.6 向后兼容

- 未配 `api_keys`（无数组/空数组/无端点匹配）→ `resolve_rotating` 走 `resolve()` 单值链，行为与现状完全一致（4 消费面零回归）；
- `resolve()` 单值语义、密钥链优先级、日志脱敏口径均不变；
- 写侧对既有无 `api_keys` 数据零迁移（`_build_endpoints_list` 补空数组，摘要为 None）。

> 【实现演进裁定 2026-10-22，INT-1173 负责人拍板 + INT-1230 endpoint 级修订审计】密钥池从 API 级 `meta.api_keys`（旧 INT-1177 初版口径）返工迁移至 **endpoint 级 `api_endpoints[].api_keys`**；`meta` 不再承载密钥池，仅保留单值回退链。本能力在 `api_test_service` 内嵌适配器体系实现（INT-1169 迁回后），不在独立服务 api_adapter_service 上加（该服务已删除）。

---

## 4. 核心流程图

### 4.1 API 测试任务总流程

见 2.3 时序图。要点：device_type 路由 → 队列消费 → 适配器执行 → 双通道事件 → 评估。

### 4.2 Realtime 流式会话流程（新增）

```mermaid
sequenceDiagram
    autonumber
    participant EXE as RealtimeSessionExecutor
    participant AD as OpenAIRealtimeAdapter<br/>（RealtimeAdapterBase 子类）
    participant WS as RealtimeWSClient
    participant V as 厂商 WS 端
    participant Q as queue.Queue
    participant EV as EventBus
    participant ST as 对象存储

    EXE->>AD: connect（websocket_api 会话）
    AD->>WS: RealtimeWSClient.connect（_build_client 构造）
    WS->>V: WebSocket 握手
    V-->>WS: session.created / session.updated
    WS->>Q: _recv_loop（daemon 线程）归一化入队
    V-->>WS: ai_audio_delta / ai_text_delta / user_speech_started ...
    WS-->>Q: RealtimeFrameType 归一化事件
    EXE->>Q: recv() 同步拉取
    EXE->>EV: frame 事件（不落库，Socket.IO room=task_id 推送）
    EXE->>EXE: _pacing_gate：user_speech_started / response_cancelled → interrupt（ALLOW_BARGE_IN）
    V-->>WS: ai_audio_done / ai_text_done / connection_closed
    EXE->>ST: summary（audios/{task}/realtime/ai_output_*.wav + 汇总结论落库）
    EXE->>EV: summary 事件 → 触发评估
    Note over EXE,V: 已收到 ai_audio_delta 仅表明通过起始窗口；收尾事件 ai_audio_done 须在 ai_complete_timeout_seconds 内到达，否则轮失败「AI 回复未在超时内完成」
```

### 4.3 混音流式渲染流程（新增）

```mermaid
sequenceDiagram
    autonumber
    participant API as api_test_service:5003
    participant AU as audio_service（gRPC:50052）
    participant DB as ApiRmsSplService（ACL 只读 + 缓存）

    API->>AU: RenderAudioStream(渲染参数, api.audio_config)
    AU->>DB: 拉取 ApiRmsSplMapping（未配置 → gain=1.0）
    AU->>AU: ① 加载 PCM
    AU->>AU: ② AudioFormatAdapter 格式适配
    AU->>AU: ③ RMS 补偿 + SPL 增益（spl_to_gain 多点插值）
    AU->>AU: ④ 时间轴编排
    AU->>AU: ⑤ 混音叠加
    loop 每 1600 samples（≈100ms）
        AU->>AU: ⑥ 切片
        AU-->>API: AudioChunk(seq, pcm_base64, offset_ms)
    end
    AU-->>API: AudioChunk(last = true)
```

### 4.4 SPL 校准流程（UC-0902，新增）

```mermaid
flowchart TD
    A[发起 API RMS-SPL 校准] --> B{DistributedLock<br/>calibration:api_rms_spl:{api_id}:{mapping_id}<br/>ttl=30}
    B -- 获取失败 --> C[返回校准冲突]
    B -- 获取成功 --> D[采样 RMS / 目标 SPL 点集]
    D --> E[写入 api_rms_spl_mappings<br/>CalibrationStatus 状态流转]
    E --> F[audio_service ACL 缓存刷新]
    F --> G[释放锁]
```

---

## 5. 用户界面设计

### 5.1 页面结构【适配说明】

【适配说明】废除原文档 Flask 模板渲染 + ws 直连页面，落位 Vue3 SPA + DDD 四层。

- `frontend/src/views/APITest/APITest.vue`（已存在）：任务创建（选设备 → 判定 device_type）/ 执行监控（frame 通道）/ 结果查看（summary + 评估）；
- `frontend/src/views/SPLMapping/SPLMapping.vue` + `SPLMapping.ts`：SPL 校准页（对接 `/api/digital-spl`，新增）；
- 页面交互遵循既有 `ViewMode`（`shared/models/common_enums.py` / `frontend/src/domain/enums.ts`）口径。

### 5.2 前端 DDD 四层【适配说明】

```
Presentation    views/ + components/            只见 camelCase Domain + composables（Ports）
Application     composables/ + store/           编排用例，缓存 ReadModel，只见 Domain
Domain          domain/model/ + enums.ts        camelCase、零依赖、无索引签名兜底
Infrastructure  api/ + adapters/ + dto/ + http/ 唯一知道 snake_case
```

网络代理字段（INT-839）四层镜像：Domain `proxyType` / `proxyUrl`（camelCase，类型引用 `domain/enums.ts` `ProxyType`）⇄ DTO `proxy_type` / `proxy_url`（snake_case）⇄ adapter `apiConfigAdapter.ts` 转换，Infrastructure 层唯一做 snake_case↔camelCase 转换；校验规则 `frontend/src/utils/proxyValidation.ts` 镜像后端（见 3.9）。

### 5.3 实时推送展示

- Socket.IO 客户端按 `room = task_id` 订阅（UC-1001）；
- frame 通道渲染增量内容（文字流 / 音频进度条），对应 `ai_text_delta` / `ai_audio_delta` 等；
- 事件类型在前端以枚举消费（camelCase）；snake_case 报文由 `dto/` + `adapters/` 转换，Presentation 层不感知。

### 5.4 SPLMapping 五层对称模板（新增）

SPLMapping 页面为本轮前端四层的**对称模板**，API 测试页按其铺开：

| 层 | SPLMapping（已存在） | APITest（新增） |
| --- | --- | --- |
| Presentation | `views/SPLMapping/SPLMapping.vue` + `.ts` | `views/APITest/APITest.vue` + `.ts` |
| Application | `composables/device/splPort.ts` | `composables/apiTest/apiPort.ts`（新增） |
| Domain | `domain/model/spl.ts` | `domain/model/apiTest.ts`（新增） |
| Infrastructure | `infrastructure/api/splApi.ts`、`adapters/splAdapter.ts`、`dto/splDto.ts` | `infrastructure/api/apiApi.ts`、`adapters/apiAdapter.ts`、`dto/apiDto.ts`（新增） |

---

## 6. 技术实现

### 6.1 后端模块落位

| 模块路径 | 职责 |
| --- | --- |
| `task_service/core/execution_engine/mixins/task_dispatch.py` | `_dispatch_case_by_type` / `_dispatch_api_case` / `_dispatch_e2e_case`（路由） |
| `api_test_service/core/api_session_executor.py` | L33 `APISessionExecutor`（既有执行器） |
| `api_test_service/core/realtime_session_executor.py` | `RealtimeSessionExecutor`（新增，待建） |
| `audio_service/infrastructure/audio/spl_service.py` | L21 `SPLMappingService`、L34 `spl_to_gain` |
| `shared/utils/redis_pubsub.py` | EventBus / RedisPubSub / EventChannel / EventType |
| `shared/utils/service_registry.py` | L16 `RedisServiceRegistry`（心跳注册） |
| `shared/utils/distributed_coordinator.py` | L67 `DistributedLock`、L153 `DistributedSemaphore` |
| `shared/infrastructure/base_executor/_base.py` | BaseExecutor 五 Mixin |

### 6.2 数据模型【适配说明】

- `api_test_service/infrastructure/persistence/models/api_models.py` L15 `class API` **新增四列**：
  - `device_type`：DeviceType 取值（http_api / websocket_api）；
  - `adapter_class`：显式适配器类名（可空；注册表中优先）；
  - `audio_config`：JSON（目标采样率 / 位深 / 声道，供 AudioFormatAdapter）；
  - `output_types`：JSON（OutputType 集合，声明产出类型）；
- **再新增两列（INT-839，见 3.9）**：`proxy_type`（VARCHAR(20)，http/https/socks5/socks5h，NULL=不用代理）、`proxy_url`（VARCHAR(255)，`user:pass@host:port`，不含 scheme）；迁移脚本 `scripts/migrations/202610/add_api_proxy_columns.py`（幂等可重跑，存量行 NULL 不报错）；
- `task_service/infrastructure/persistence/models/task_models.py` L84 `TaskCase`：`device_id` 列**已有**（L111）；`device_type` 列**新增**；
- 新表 `api_rms_spl_mappings`（**新增**）：api 关联的 RMS→SPL 采样点集 + 校准状态 + 审计字段；完整 DDL 以 `05_路由与废弃.md` 为准。

### 6.3 gRPC 契约【适配说明】

- `shared/proto/api_test_service.proto` L46 `StartAPITestRequest`：现状仅 `task_id` → **新增** `device_type`、`device_id`（physical 归属校验用）；示例见 `05_路由与废弃.md`；
- `shared/proto/audio_service.proto`：**新增** `RenderAudioStream`（server-streaming，见 3.4）。

### 6.4 枚举化【适配说明】

- `shared/models/common_enums.py`（既有 ReportStatus / TaskStatus / ReportType / TestType / FieldType / ViewMode / RedisKeyPrefix / EvalTaskStatus 8 枚举）**新增**：
  - `DeviceType`：physical / http_api / websocket_api；
  - `OutputType`：产出类型（text / audio 等）；
  - `CalibrationStatus`：校准状态机；
- **新增** `RealtimeFrameType`：归一化事件（见 3.6）；`RealtimeRoundMode`（normal / interruption）、`RealtimePacingStrategy`（INT-475，fixed / wait_turn_end / allow_barge_in / timeout_fallback）；
- **新增** 被测 API 网络代理类型枚举（INT-839）：`proxy_type` 四值 http / https / socks5 / socks5h（无代理为 NULL/空），后端收敛于 `proxy_utils.PROXY_TYPES`，前端 `frontend/src/domain/enums.ts` `ProxyType` 同步（值 = 后端原值）；
- 前端 `frontend/src/domain/enums.ts` 同步**新增**三枚举；`TaskType`（L24）**不引入** `'realtime_api'`；
- result_type 映射（评估侧，详见 `06_评估与前端.md`）：

| 执行模式 | result_type |
| --- | --- |
| physical 实时 | `'real-time'`（既有） |
| physical 非实时 | `'non-real-time'`（既有） |
| http_api | `'api'`（新增） |
| websocket_api | `'realtime'`（新增） |

- 魔法字符串清理：现状 `task.type == 'api'`（task_dispatch.py L91）等一律替换为枚举判断（先重构，再管消费方）。

### 6.5 Redis 键规划（配置化，前缀经 `RedisKeyPrefix` 枚举）

| 键 | 用途 |
| --- | --- |
| `task:queue` | 任务队列（LPUSH / BRPOP） |
| `lock:task:physical:{device_id}` | physical 设备互斥 |
| `api:sem:{api_id}` / `sem:api:endpoint:{host}` | 被测端点并发闸（DistributedSemaphore） |
| `calibration:api_rms_spl:{api_id}:{mapping_id}` | SPL 校准互斥锁（ttl=30） |

---

## 7. 性能与可靠性设计

### 7.1 通用性能指标

> 【保留：通用性能测试口径，与本轮 device_type 化改造正交】

本节沿用原文档口径，指标定义、采样方式与阈值不变：

| 指标 | 口径 | 说明 |
| --- | --- | --- |
| QPS | 单位时间成功请求数 | 压测工具口径保留 |
| RTT | 请求往返时延（P50 / P95 / P99） | 保留分位数统计 |
| SLA | 可用性 / 成功率目标 | 保留阈值告警 |
| 并发压测 | ConcurrentApiTester 阶梯加压 | 保留 |
| 健康监控 | ApiHealthMonitor + `health_score` | `api_models.API.health_score` 列沿用 |

上述能力与本轮 device_type 化改造**正交**：路由与适配器层不改变性能指标口径。

### 7.2 v3.0 并发与互斥（新增）

- 被测端点并发闸：`DistributedSemaphore`（`shared/utils/distributed_coordinator.py` L153），键 `api:sem:{api_id}` / `sem:api:endpoint:{host}`；
- physical 设备互斥：`lock:task:physical:{device_id}`（同一物理设备同时仅一个任务）；
- SPL 校准互斥：`calibration:api_rms_spl:{api_id}:{mapping_id}`，ttl=30（见 3.5）；
- 并发参数配置化：`concurrency_config.json`，禁止硬编码。

### 7.3 高可用与容错（新增）

- api_test_service **replicas:2**；worker 心跳 TTL 15s；心跳过期由 `_adopt_orphan_tasks` 孤儿收养接管；
- Realtime 长连接亲和路由，保证会话事件归属一致；
- EventBus 事件消费幂等（task_id + 事件序号去重）；
- Realtime 判定容错：起始窗口超时（`ai_start_timeout_seconds=25` 无 `ai_audio_delta`）→「AI 未回复」轮失败；收尾窗口超时（`ai_complete_timeout_seconds=60` 无 `ai_audio_done`）→「AI 回复未在超时内完成」轮失败；`TIMEOUT_FALLBACK` 只兜底不无限等待，不改变成败语义（见 3.6）。

---

## 8. 安全设计

### 8.1 密钥管理（新增）

- OpenAI 密钥链逐级回退：case_config → meta → env `OPENAI_API_KEY`（见 3.7）；
- 端点级多密钥池（`api_endpoints[].api_keys`，round-robin + 失败降级 + 冷却）：明文落库、响应零完整密钥（逐端点 `api_keys_summary` 摘要）、日志经 `secret_mask` 整数组掩码（见 3.10）；
- 密钥与敏感头不出 Infrastructure 层；日志与 summary 报告统一脱敏。
- 被测 API 网络代理（INT-839）：`proxy_url` 明文落库（与 `meta.api_key` 明文存法一致，DB 权限面需知悉）；日志/异常上下文中 `user:pass` 段经 `secret_mask`（文本 + 结构化）与 adapter 侧 `mask_proxy_userinfo` 统一掩码，保留 host:port 便于排查（见 3.9）。

### 8.2 并发与互斥安全

- 分布式锁 / 信号量统一由 `shared/utils/distributed_coordinator.py` 提供，TTL 防死锁；
- 校准、physical 执行、endpoint 并发三类关键资源全部收敛到显式互斥/闸口。

### 8.3 传输与鉴权

- 对外统一经 api_gateway:5000 鉴权（auth_service:5009 签发凭据）；
- 服务间 gRPC 内网互信 + proto 契约校验；Socket.IO 握手鉴权后方可加入 task_id 房间。

### 8.4 数据安全

- summary.json 写对象存储 `api-test-results/<task_id>/<session_id>/summary.json`，按 task/session 隔离；
- frame 通道不落库，降低实时语音/文本的持久化暴露面。

---

## 9. 测试与维护

- **单元测试**：适配器归一化（RealtimeFrameType 全覆盖）、`spl_to_gain` 多点插值边界、OpenAI 密钥链回退顺序；密钥池（INT-1173/1177/1178）：`resolve_rotating` 轮换/冷却/全冷却回退/跨协议同源（`test_int70_api_key_chain.py`）、端点级 CRUD 校验 + 逐端点摘要（`test_int1177_api_keys_crud.py`）、Realtime 握手 401/403/429 轮换（`test_int497_realtime_adapter_base.py`）、HTTP 内嵌路径失败降级重试（`test_int1178_api_http_rotation_retry.py`）、前端 DTO⇄Domain 密钥池映射（`apiConfigKeys.spec.ts`）；网络代理（INT-839）：CRUD 校验（含 scheme 前缀拒绝 / 端口数字 / user:pass 必填）、URL 拼接、websocket-client 参数分解（含 realtime_ws_client）、requests proxies 注入、adapter 透传白名单 merge、socks 类型可用性（`tests/unit/test_int839_api_proxy.py` / `test_int847_adapter_proxy.py` / `test_int848_*`）；
- **集成测试**：api_gateway ↔ task_service ↔ api_test_service 双副本链路；EventBus → Socket.IO 房间隔离（UC-1001）；RenderAudioStream 分片连续性；
- **灰度策略**：device_type 白名单开关，旧 `task.type` 路径并行运行直至废弃清单收尾（先重构，再管消费方）；
- **监控维护**：task:queue 深度、worker 心跳 TTL、锁等待时长、replicas 副本均衡。

---

## 10. 未来规划（P0~P3）

| 阶段 | 内容 | 详见 |
| --- | --- | --- |
| P0 | device_type 路由改造（task_dispatch 枚举化）、DDL（API 四列 / TaskCase 增列 / api_rms_spl_mappings 建表）、三枚举新增、废弃清单落地 | `05_路由与废弃.md` |
| P1 | 适配器注册表（HttpAPI / HttpStream / Realtime 三级体系）、RealtimeSessionExecutor、RealtimeFrameType、RenderAudioStream RPC | `02_架构设计.md`、`07_流式推送与结果获取.md` |
| P2 | ApiRmsSplMapping 校准链路、`/api/digital-spl` 路由、SPLMapping 五层模板铺开至 APITest 页 | `08_混音与SPL映射.md` |
| P3 | api_adapter_service:5008 下线（INT-1176 已执行）、废弃清单收尾 | `02_架构设计.md` |

排期与完整迁移时间线以 `05_路由与废弃.md` / `02_架构设计.md` 为准。

---

## 11. 结论

v3.0 修订后，API 测试子域从"单体 + WebSocket 直连 + 通用压测"演进为"device_type 三值路由 + 微服务多副本 + 适配器注册表 + EventBus 房间推送 + frame/summary 双通道"的执行体系；混音与 SPL 数字增益由 audio_service 统一承载（RenderAudioStream / spl_to_gain），Realtime 会话获得归一化事件与 barge-in 语义。原文档通用性能口径（QPS / RTT / SLA）保留为正交能力。全部新增项与改造项均已对齐 `01_UseCase总览.md`、`02_架构设计.md`、`05_路由与废弃.md`。

---

## 12. 参考资料

**基准文档（口径冲突时以其为准）**

- `doc/功能设计文档/01_测试执行/01_UseCase总览.md`
- `doc/功能设计文档/01_测试执行/02_架构设计.md`
- `doc/功能设计文档/01_测试执行/05_路由与废弃.md`
- `doc/功能设计文档/01_测试执行/06_评估与前端.md`
- `doc/功能设计文档/01_测试执行/07_流式推送与结果获取.md`
- `doc/功能设计文档/01_测试执行/08_混音与SPL映射.md`

**关键代码路径**

- `shared/proto/api_test_service.proto`（L10 StartAPITest、L46 StartAPITestRequest）
- `shared/proto/audio_service.proto`（RenderAudioStream 新增）
- `shared/models/common_enums.py`（DeviceType / OutputType / CalibrationStatus 新增）
- `shared/utils/redis_pubsub.py`、`shared/utils/service_registry.py`、`shared/utils/distributed_coordinator.py`
- `shared/utils/api_key_provider.py`（`ApiKeyChainResolver.resolve_rotating` / `RotationStateStore` / `endpoint_rotation_key`，INT-1173）
- `shared/utils/secret_mask.py`（`api_keys` 数组掩码，INT-1173）
- `api_test_service/application/api_crud_service.py`（`_validate_api_keys` / `_build_endpoints_list` / `_api_to_dict` 逐端点摘要，INT-1173）
- `api_test_service/domain/entities/api.py`（`derive_api_keys_summary` / `redact_endpoint_keys`，INT-1173）
- `api_test_service/infrastructure/adapters/api_driver_adapter.py`（`_merge_headers` / `_call_api_with_key_rotation`，INT-1173/1178）
- `api_test_service/infrastructure/adapters/protocol/realtime_adapter_base.py`（`_resolve_ws_headers` / `_connect_with_rotation`，INT-1173）
- `api_gateway/schemas/api.py`（`ApiEndpointInput.api_keys` / `ApiEndpointItem.api_keys_summary`，INT-1173）
- `shared/infrastructure/base_executor/_base.py`
- `task_service/core/execution_engine/mixins/task_dispatch.py`
- `task_service/infrastructure/persistence/models/task_models.py`
- `api_test_service/infrastructure/persistence/models/api_models.py`
- `api_test_service/core/`（api_session_executor.py 等；realtime_session_executor.py 待建）
- `audio_service/infrastructure/audio/spl_service.py`
- `frontend/src/domain/enums.ts`
- `frontend/src/views/APITest/APITest.vue`、`frontend/src/views/SPLMapping/SPLMapping.vue`
- `frontend/src/composables/device/splPort.ts`、`frontend/src/infrastructure/{api,adapters,dto}/spl*.ts`、`frontend/src/domain/model/spl.ts`
