# Intelligent Audio TEST 平台 — DDD 重构方案

> 参考美团 DDD 实践文章方法论，结合项目实际架构，给出限界上下文划分、聚合根设计、上下文映射、CRUD 下沉计划与认证方案。
>
> **本文档为代码核查后的最终版本，状态截至 2026-08-06（v3 修订：audio_service / device_service 已实际拆分落地，e2e_test_service PO 已迁移，grpc_proxies 已接入，P2.5 完成）。**

---

## 一、方法论

美团 DDD 文章的核心步骤：

1. 根据需求划分领域和限界上下文，梳理上下文关系
2. 识别实体、值对象
3. 划分聚合和聚合根
4. 设计仓储
5. 工程实践检验

核心原则：**限界上下文从需求出发，按领域划分，紧耦合的圈在一起，用语言描述职责看是否清晰。**

---

## 二、领域划分：核心域 / 支撑域 / 通用域

| 分类 | 限界上下文 | 划分依据 | 归属微服务 |
|---|---|---|---|
| **核心域** | 测试任务上下文 | 平台核心价值——编排测试任务的生命周期，用户最高频交互 | `task_service` |
| **核心域** | 测试执行上下文 | 平台差异化能力——调度设备/API、采集结果 | `api_test_service`（API 执行） / `e2e_test_service`（E2E 执行，纯执行器） |
| **核心域** | 评估上下文 | 跨 API/E2E 共享——按维度打分、多轮聚合、重新评估 | `evaluation_service` |
| **核心域** | 报告上下文 | 平台产出价值——单任务/对比报告生成 | `report_service`（PO 已下沉，CRUD 待回归） |
| **支撑域** | 测试用例上下文 | 为任务提供输入配置，不直接产生业务价值 | `task_service`（详见第十一章决策） |
| **支撑域** | 设备管理上下文 | 被测设备 DUT + 播放设备 + SPL 校准，被 task/report/e2e 多方读 | `device_service`（**v3 已落地**，从 e2e_test_service 分离） |
| **支撑域** | 音频管理上下文 | 音频素材 CRUD/上传/标注/转换/预览，被 task/api/e2e/report 多方读 | `audio_service`（**v3 已落地**，从 e2e_test_service 分离） |
| **支撑域** | API 配置上下文 | 为 API 测试提供被测对象配置 | `api_test_service` |
| **支撑域** | 评估维度上下文 | 为评估提供维度定义和评分规则配置（Dimension CRUD） | `evaluation_service` |
| **通用域** | 算法配置上下文 | 全系统共享的"算法类型"字典，跨上下文引用 | `algorithm_service`（PO + domain 已建，CRUD 待从 task_service 回归） |
| **通用域** | 用户与权限上下文 | RBAC+OAuth，横切所有上下文 | `auth_service`（PO 骨架已建） |
| **通用域** | 系统审计上下文 | 日志/首页统计，横切关注点 | `task_service`（Log CRUD 待从网关下沉）+ 各服务自维护统计 |
| **通用域** | API 适配上下文 | 多 vendor 协议适配，已有完整 DDD 分层 | `api_adapter_service` |

---

## 三、限界上下文详解 — 聚合根 / 实体 / 值对象

### 核心域

#### 1. 测试任务上下文（Task Context）

```
聚合根：Task
  ├─ 实体：TaskCase（任务下用例执行状态）
  ├─ 实体：TaskDevice（任务关联设备）
  ├─ 实体：TaskAPI（任务关联API）
  ├─ 实体：TaskTag（任务标签关联）
  ├─ 实体：TaskMergeRelation（任务合并关系）
  └─ 值对象：TaskConfig（rounds/dimensions/background_noise 等配置快照）
     值对象：AlgorithmParams（按轮分组的算法参数快照）
```

**职责**：管理测试任务从创建→启动→执行中→完成/失败的全生命周期，编排用例分发和设备/API 调度。Task 是全系统最大的聚合根，通过唯一标识引用 TestCase/Device/API（而非持有对象引用），符合"设计小聚合"原则。

**已落地**（DDD 四层全部完成）：
- `domain/entities/`：`task.py`（TaskAggregate 纯 dataclass + TaskSnapshot + TaskStatus）、`task_case.py`（TaskCaseEntity + TaskCaseSnapshot）、`task_merge_relation.py`
- `domain/value_objects/`：`task_config.py`（TaskConfig / TaskId / TaskProgress）
- `domain/events/`：`task_events.py`（TaskCreated / TaskStarted / TaskCompleted / TaskFailed / TaskStopped）
- `domain/services/`：`task_state_machine.py`（状态流转纯逻辑）、`task_scheduler.py`（调度策略纯逻辑）
- `infrastructure/persistence/`：PO 下沉到 `models/`（task_models / testcase_models / result_models / system_models）+ `task_repository.py`（4 个 PO↔Entity 转换函数）
- `application/`：commands + queries + handlers（CQRS）
- `interfaces/`：grpc/server.py + api/admin.py
- gRPC 读接口已暴露（`task_service/infrastructure/grpc/task_data_service.py`，11 个 RPC）

---

#### 2. 测试执行上下文（Execution Context）

```
聚合根：TestResult
  └─ 值对象：AlgorithmResult（算法原始返回快照）
     值对象：ExecutionSteps（执行步骤记录）
     值对象：ResultDataRef（大字段文件路径引用）
```

**职责**：记录单用例在特定 device+api 上的执行结果（原始算法输出）。大字段（result_data）存文件、DB 仅存轻量元数据，是跨域数据枢纽。**执行上下文只负责采集原始结果，不再负责打分**——打分移交给评估上下文。

**子上下文**（按执行类型）：
- **API 执行子上下文**：聚合 `APITestService` + `APIExecutor`，处理 API 类型的用例执行
- **E2E 执行子上下文**：聚合 `E2EService` + `E2EExecutor` + 设备驱动 + 音频播放 + 结果采集

**数据所有权**：
- TestResult（原始结果元数据）→ 归属 `task_service`。api_test_service / e2e_test_service 执行完成后通过 gRPC 回调 `task_service.SubmitResult` 写入（**已完成**，P2.1/P2.2 改造完毕）
- 执行完成后 → 通过 `shared.clients.grpc_clients.submit_evaluate_case` gRPC 调用评估上下文打分

**已落地**（DDD 四层全部完成）：
- `api_test_service`：domain（APIAggregate + APISnapshot + HTTPMethod + APIStatus）、application（commands/queries/handlers）、infrastructure（PO + Repository + gRPC servicer）、interfaces（grpc/server + api/admin）
- `e2e_test_service`：domain（DeviceAggregate + PlaybackDeviceAggregate + AudioAggregate + UploadTaskAggregate + SPL/Calibration 实体 + 值对象 + 事件 + upload_scheduler）、application（commands/queries/handlers + 6 个 CRUD service，**v3: PO 改为 re-export 存根**）、infrastructure（3 个 Repository + gRPC servicer）、interfaces（grpc/server + api/admin）
- `api_test_service/infrastructure/persistence/models/api_models.py`（API PO）；`device_service/infrastructure/persistence/models/`（Device/SPL PO）；`audio_service/infrastructure/persistence/models/`（Audio/Upload PO）

**已完成**：TestResult 写入已改 gRPC（P2.1/P2.2 完成）；e2e_test_service 音频/设备 CRUD 已拆出为独立 audio_service / device_service（P2.5 完成，e2e 保留 re-export 存根）

---

#### 3. 评估上下文（Evaluation Context）

```
聚合根：EvaluationDimension（评估维度定义）
  ├─ 实体：DimensionScore（维度评分结果，对应 TestResultDimension PO）
  ├─ 值对象：DimensionSnapshot（维度规则快照：rule + api_settings + params）
  ├─ 值对象：RoundResult（单轮原始结果引用）
  └─ 值对象：ScoringRule（打分规则：direct / linear / threshold）
```

**职责**：从执行上下文接收原始结果，按 Dimension 定义调评估 API、按规则打分、多轮聚合。**跨 API/E2E 共享**——两类执行器均通过 gRPC 复用同一套评估逻辑，不各自实现打分。

**已落地**（DDD 分层完成度最高的服务）：
- `domain/entities/evaluation_dimension.py`：纯 dataclass 聚合根（EvaluationDimension + DimensionScore + DimensionSnapshot + ScoringRule + RoundResult）
- `domain/services/evaluation_service/`：9 个 Mixin 组合（CaseEvaluation/DimensionLoader/TaskDispatcher...）+ `evaluation_utils.py`（calculate_score + extract_by_path）
- `infrastructure/persistence/models/`：Category / Dimension / TestResultDimension PO 真正下沉
- `infrastructure/persistence/evaluation_dimension_repository.py`：DDD 仓储（PO↔Entity 转换）
- `infrastructure/evaluation_api/`：HTTP 客户端（api_request_handler + endpoint_worker + evaluation_api_client + payload_builder）
- `infrastructure/grpc_clients/task_service_client.py`：gRPC 客户端（11 个 RPC，替代直连 task_service PO）
- `application/handlers/reevaluation_executor.py`：重新评估编排（已从 domain/services 移到 application/）
- `application/commands/evaluation_command_service.py` + `application/queries/evaluation_query_service.py`：CQRS 拆分
- `interfaces/grpc/servicers.py`：入站 gRPC servicer（已从 infrastructure/ 移到 interfaces/）

**数据所有权**：`TestResultDimension` 归属 evaluation_service。`TestResult`（元数据）归属 task_service，通过 gRPC 访问。

**部署**：HTTP :5004 + gRPC :50091，独立部署。

---

#### 4. 报告上下文（Report Context）

```
聚合根：Report
  ├─ 实体：ReportCase（报告内用例视图）
  ├─ 实体：ReportSummary（1:1 报告摘要）
  ├─ 实体：ReportSummaryMeta（1:1 摘要元数据）
  ├─ 实体：ReportRawData（1:1 原始数据）
  ├─ 实体：ReportMetricStats（1:1 指标统计）
  ├─ 实体：ReportComparisonMatrix（1:1 对比矩阵）
  └─ 值对象：DimensionValues（维度值快照）
     值对象：CaseCategorySnapshot（用例分类快照）
```

**职责**：从 Task 执行结果聚合生成报告，支持单任务报告和对比报告（多 Task）。Report 内部各实体均为 1:1，聚合内一致性高。

**已落地**（DDD 四层全部完成）：
- `domain/`：`entities/report.py`（ReportAggregate + 6 子实体 + 2 枚举）、`value_objects/report_config.py`、`events/report_events.py`、`services/report_generator.py`
- `infrastructure/persistence/`：`models/report_models.py`（7 个 PO）、`report_repository.py`（7 个转换函数 + 子实体加载方法）
- `application/`：commands（CreateReport / GenerateReport / UpdateReportStatus / DeleteReport）+ queries（GetReport / GetReportByTask / ListReports / GetReportSummary）+ handlers（ReportCommandHandler + ReportQueryHandler）
- `interfaces/`：`grpc/servicers.py`（ReportServicer 8 个 RPC 骨架）+ `grpc/server.py`（端口 50068）+ `api/routes.py`（8 个 HTTP 路由）

**v2 决策**：report_service 补 application 层，CRUD 从 api_gateway 下沉回归。理由：
1. PO 和 domain 层都在 report_service，但全部 CRUD 逻辑在 api_gateway（report_command_service + report_query_service + 4 个辅助文件，直连 6 个服务 PO）
2. report_command_service 的 import 触目惊心：直接 import report_service/task_service/evaluation_service/e2e_test_service/api_test_service 的 PO
3. 应将 CRUD 逻辑迁移到 `report_service/application/`，通过 gRPC 拉取 task/testcase/device/audio/evaluation 数据
4. 网关只做路由转发

---

### 支撑域

#### 5. 测试用例上下文（Test Case Context）

```
聚合根：TestCase
  ├─ 实体：TestCaseGroup（用例分组）
  ├─ 实体：TestCaseTag（用例标签关联）
  └─ 值对象：CaseConfig（rounds/dimensions 配置）
     值对象：AlgorithmParams（按轮算法参数）
     值对象：ReferenceParams（参考参数路径+内容）
```

**关键决策**：TestCase 表归 `task_service`（PO 已下沉到 `task_service/infrastructure/persistence/models/testcase_models.py`）。理由及 API/E2E 用例结构差异对策详见第十一章。

---

#### 6. 设备管理上下文（Device Context）— v3 已落地 device_service

```
聚合根：Device（被测设备 DUT）
  ├─ 实体：DeviceTag
  └─ 值对象：DeviceSpec（型号/系统/版本/连接信息快照）
     值对象：SupportedAlgorithms（支持的算法类型列表）

聚合根：PlaybackDevice（播放设备）
  └─ 值对象：PlaybackSpec（型号/采样率/通道）

聚合根：SPLMapping（声压级映射）
  ├─ 实体：CalibrationHistory（校准历史）
  └─ 值对象：CalibrationData（校准数据快照）
```

**v3 落地**：从 `e2e_test_service` 拆出独立 `device_service`。理由：
1. 设备被 task_service（TaskDevice 关联）、report（报告读设备信息）、e2e_test_service（执行时驱动设备）**三方读**，不应归任一执行器
2. SPL 校准与播放设备强耦合（校准时需播放测试音），同归 device_service
3. e2e_test_service 回归纯执行器，不再承载设备 CRUD

**已落地**（v3 完成）：
- PO 已迁移到 `device_service/infrastructure/persistence/models/device_models.py`（Device/PlaybackDevice/DeviceTag）+ `system_models.py`（SPLMapping/CalibrationHistory）
- domain 层已建：`device_service/domain/entities/device.py`（DeviceAggregate）、`playback_device.py`、`spl.py`、`value_objects/device_config.py`、`events/device_events.py`
- CRUD 实现：`device_service/application/device_crud_service.py` + `playback_crud_service.py` + `spl_crud_service.py`
- gRPC servicer：`device_service/interfaces/grpc/servicers.py`（6 个 Servicer：DeviceService/DeviceResultService/EnvDeviceService/DeviceConfigService/PlaybackConfigService/SPLConfigService）
- gRPC server：`device_service/interfaces/grpc/server.py`（端口 50053）
- e2e_test_service PO 改为 re-export 存根（从 device_service 导入）

---

#### 7. 音频管理上下文（Audio Context）— v3 已落地 audio_service

```
聚合根：Audio
  ├─ 实体：AudioAnnotation（多格式标注）
  ├─ 实体：AudioAlgorithmRelation（音频-算法关联）
  ├─ 实体：AudioTag
  └─ 值对象：AudioMeta（时长/采样率/声道/格式）
     值对象：SourceLanguage（源语言）

聚合根：UploadTask（上传任务）
  ├─ 实体：UploadFile
  └─ 实体：UploadChunk
```

**v3 落地**：从 `e2e_test_service` 拆出独立 `audio_service`。理由：
1. 音频被 **4 个服务读**（task_service 读 AudioTag、api_test_service 读音频配置、e2e_test_service 播放音频、report 读音频信息），是中立素材服务，不该归任一执行器
2. 上传任务是音频的前置状态（UploadTask → Audio），同聚合根，应放一起
3. 音频标注跨域直连 algorithm_service PO（CaseAlgorithmParam/AlgorithmReferenceParam），拆出后通过 gRPC 访问算法参数
4. e2e_test_service 瘦身后只保留执行逻辑

**已落地**（v3 完成）：
- PO 已迁移到 `audio_service/infrastructure/persistence/models/audio_models.py`（Audio/AudioAnnotation/AudioTag/AudioAlgorithmRelation）+ `upload_models.py`（UploadTask/UploadFile/UploadChunk）
- domain 层已建：`audio_service/domain/entities/audio.py`（AudioAggregate + AudioSnapshot）、`upload.py`（UploadTaskAggregate）、`value_objects/audio_meta.py`、`events/audio_events.py`、`services/upload_scheduler.py`
- CRUD 实现：`audio_service/application/audio_crud_service.py` + `audio_upload_service.py` + `audio_annotation_service.py` + `audio_convert_service.py` + `audio_preview_service.py` + `audio_testcase_creation_service.py`
- gRPC servicer：`audio_service/interfaces/grpc/servicers.py`（3 个 Servicer：AudioService/PlaybackService/AudioConfigService）
- gRPC server：`audio_service/interfaces/grpc/server.py`（端口 50052）
- e2e_test_service PO 改为 re-export 存根（从 audio_service 导入）

---

#### 8. API 配置上下文（API Config Context）

```
聚合根：API
  └─ 值对象：ApiMeta（鉴权信息快照）
     值对象：ApiEndpoints（端点列表快照）
     值对象：ConcurrencyConfig（max_process/max_timeout/max_audio_duration）
```

**已落地**：PO 已下沉到 `api_test_service/infrastructure/persistence/models/api_models.py`

---

#### 9. 评估维度上下文（Evaluation Dimension Context）

```
聚合根：Dimension
  ├─ 实体：Category（维度分类）
  └─ 值对象：DimensionRule（评分规则 JSON 快照）
     值对象：ApiSettings（维度级 API 配置快照）
     值对象：ScoreRange（result_min/max/decimal_places/weight）
```

**已落地**：PO 已下沉到 `evaluation_service/infrastructure/persistence/models/evaluation_models.py`，维度 CRUD 在 `evaluation_service/application/`

---

#### 10. SPL 校准上下文（SPL Context）— v3 合并到 device_service

```
聚合根：SPLMapping
  ├─ 实体：CalibrationHistory（校准历史）
  └─ 值对象：CalibrationData（校准数据快照）
```

**v3 落地**：SPL 校准合并到 `device_service`。理由：SPL 校准与播放设备强耦合（校准时需通过播放设备播放测试音），拆开会造成 device_service ↔ e2e_test_service 的循环依赖。

**已落地**：PO 已迁移到 `device_service/infrastructure/persistence/models/system_models.py`（SPLMapping/CalibrationHistory），e2e_test_service 改为 re-export 存根

---

### 通用域

#### 11. 算法配置上下文（Algorithm Context）— 共享内核

```
聚合根：AlgorithmDefinition
  ├─ 实体：AlgorithmGroup
  ├─ 实体：AlgorithmDeviceParam
  ├─ 实体：AlgorithmApiParam
  ├─ 实体：AlgorithmReferenceParam
  ├─ 实体：ParamMapping（设备/API输出 → 维度输入 映射）
  ├─ 实体：AlgorithmDimensionRelation（算法-维度关联）
  └─ 实体：CaseAlgorithmParam
```

**特殊定位**：`algorithm_type` 是全系统软外键，被 Task/TestCase/API/Audio/TestResult 等所有上下文引用。这是**共享内核（Shared Kernel）**——所有上下文依赖此模型，变更影响面大。

**已落地**（DDD 四层全部完成）：
- `domain/`：`entities/`（AlgorithmGroupAggregate + AlgorithmDefinitionAggregate + AlgorithmParamEntity + 3 个关联实体 + AlgorithmStatus 枚举）、`value_objects/algorithm_config.py`、`events/algorithm_events.py`、`services/algorithm_validator.py`
- `infrastructure/persistence/`：`models/algorithm_models.py`（9 个 PO）、`algorithm_repository.py`（2 个 Repository + 5 个转换函数）
- `application/`：commands（8 个写命令）+ queries（6 个读查询）+ handlers（AlgorithmCommandHandler + AlgorithmQueryHandler）
- `interfaces/`：`grpc/servicers.py`（AlgorithmGroupServicer + AlgorithmDefinitionServicer）+ `grpc/server.py`（端口 50067）+ `api/routes.py`（12 个 HTTP 路由）

**P6.2 已标记废弃**：task_service/application/algorithm/ 已加 DEPRECATED 注释，grpc_clients.py 已预留 algorithm_service 入口。待 algorithm_service proto 接入后整体删除。e2e_test_service 的 audio_annotation_service 仍直连 algorithm PO（P6.3，未执行）

---

#### 12. 用户与权限上下文（User Context）

```
聚合根：User
  ├─ 实体：Role
  ├─ 实体：Permission
  ├─ 实体：RolePermission
  ├─ 实体：UserPermission
  ├─ 实体：OAuthClient
  └─ 实体：OAuthRefreshToken
```

**已落地**（DDD 四层全部完成）：
- `domain/`：`entities/user.py`（UserAggregate + UserStatus）、`entities/role.py`（RoleEntity + PermissionEntity）、`value_objects/credential.py`（TokenPayload + OAuthCredential + PasswordHash）、`events/auth_events.py`、`services/auth_service.py`（validate_token_payload + check_permission + resolve_role_permissions）
- `infrastructure/persistence/`：`models/user_models.py`（7 个 PO）、`user_repository.py`（UserRepository + RoleRepository + 4 个转换函数 + list_users 分页）
- `application/`：commands（6 个写命令）+ queries（6 个读查询）+ handlers（AuthCommandHandler + AuthQueryHandler）
- `interfaces/`：`grpc/servicers.py`（AuthServicer 14 个 RPC 骨架）+ `grpc/server.py`（端口 50069）+ `api/routes.py`（14 个 HTTP 路由）

**待补**：认证中间件、OAuth Provider、JWT 签发/校验未实现（d9-d13 阶段）

---

#### 13. 系统审计上下文（System Context）— v2 重构 stats_cache

```
聚合根：Log
  └─ 值对象：LogMeta（level/category/module/source）

聚合根：StatsCache（网关侧，仅存聚合后的首页统计）
  └─ 值对象：CacheValue（JSON 快照）
```

**已落地**：Log PO 下沉到 `task_service/infrastructure/persistence/models/system_models.py`；StatsCache PO 下沉到 `api_gateway/infrastructure/persistence/models/cache_models.py`

**v2 决策**：拆解 `shared/utils/report/stats_cache.py` 全局耦合点。理由：
1. `stats_cache.py` 当前直连 6 个服务的 PO（task/e2e/api_test/report/evaluation）做全局统计，是全系统最大耦合点
2. **改造方案**：
   - 每个服务自己维护自己的统计计数（如 task_service 统计任务数、audio_service 统计音频数）
   - 网关 `home_service` 通过 gRPC 并行调用各服务的 `GetStats` 接口聚合首页数据
   - StatsCache 只存网关聚合后的缓存结果，不再直连各服务 PO
   - `refresh_stats_cache()` 拆解到各服务内部，各自刷新自己的统计
3. **Log CRUD 下沉**：当前在 api_gateway 直连 task_service Log PO，改通过 task_service gRPC 调用

---

#### 14. 分组上下文（Group Context）— v2 归 task_service

```
聚合根：TestCaseGroup
  └─ 值对象：GroupMeta（名称/排序/颜色）
```

**v2 决策**：Group CRUD 从 api_gateway 下沉到 task_service。理由：TestCaseGroup PO 已在 task_service，网关直连 PO 违规。Group 本质是 testcase 域的子上下文，不独立。

---

#### 15. API 适配上下文（API Adapter Context）— DDD 演进模板

```
聚合根：AdapterSession
  ├─ 实体：DialogRound
  └─ 值对象：TranslationDirection
     值对象：VendorConfig
     值对象：RoundResult
```

**已落地**：`api_adapter_service` 已有完整四层（domain/entities + value_objects + services + events + application/commands + queries + handlers + infrastructure/adapters + persistence + interfaces/api + grpc），是 DDD 演进的参考模板，无需改造。

---

## 四、上下文映射图（Context Map）

```
                         ┌──────────────────────────────────────────┐
                         │          共享内核（Shared Kernel）          │
                         │  算法配置上下文    用户与权限上下文           │
                         │ (algorithm_type)  (created_by_user_id)  │
                         └────────────┬─────────────────────────────┘
                                      │ 被所有上下文引用
          ┌───────────────────────────┼───────────────────────────┐
          │                           │                           │
          ▼                           ▼                           ▼
┌─────────────────┐  gRPC   ┌─────────────────┐        ┌─────────────────┐
│  测试任务上下文  │◄────────│  测试执行上下文  │        │   报告上下文     │
│  (Task)        │ 回写结果 │ (TestResult)    │        │  (Report)      │
│  聚合根:Task   │         │  聚合根:TestResult│        │  聚合根:Report │
│ task_service   │         │ e2e_test_service │        │ report_service │
│  :50061        │         │  :50051         │        │  :50068        │
└───────┬─────────┘         └──┬──────────────┘        └───────▲─────────┘
        │                      │                       │ ACL
    CS  │               gRPC   │ 调评估打分                 │
        │              ┌───────▼──────────┐              │
        │              │  评估上下文       │──────────────┘
        │              │ (EvaluationTask) │ 消费打分结果
        │              │ evaluation_service│
        │              │  聚合根:Evaluation│
        │              │  :50091/:5004    │
        │              └──┬──────────────┘
        │                 │ ACL
    CS  │           CS     │
   ┌────▼────┐    ┌────────▼─────┐
   │测试用例  │    │评估维度上下文 │
   │上下文    │    │(Dimension)   │
   │(TestCase)│   │聚合根:Dimension│
   └────┬────┘    └──────────────┘
        │
        │ gRPC
   ┌────┼──────────────────────────────────────┐
   │    │                                     │
   ▼    ▼                                     ▼
┌──────────────┐  gRPC   ┌──────────────┐  gRPC  ┌──────────────┐
│设备管理上下文 │◄───────│ 音频管理上下文 │◄──────│ API 适配上下文 │
│(Device)      │  播放   │(Audio)       │ 调用   │(AdapterSession)│
│聚合根:Device │         │聚合根:Audio  │        │ 已有完整DDD分层│
│device_service│         │audio_service │        │api_adapter_   │
│ :50053       │         │ :50052       │        │ service :50081│
└──────┬───────┘         └──────┬───────┘        └──────────────┘
       │ SPL 校准                │ 上传
       ▼                         ▼
┌──────────────┐         ┌──────────────┐
│ SPL 校准上下文│         │ 上传任务上下文│
│(SPLMapping)  │         │(UploadTask)  │
│合并到        │         │合并到        │
│device_service │         │audio_service │
└──────────────┘         └──────────────┘

  CS  = Customer-Supplier（客户-供应方）
  ACL = Anticorruption Layer（防腐层）
  OHS = Open Host Service（开放主机服务）
  PL  = Published Language（发布语言）
```

### 映射关系详解

| 上游 | 下游 | 关系类型 | 说明 |
|---|---|---|---|
| 算法配置上下文 | 所有上下文 | **共享内核** | `algorithm_type` 字符串被全系统引用，变更影响面大，需严格管控 |
| 用户与权限上下文 | 所有上下文 | **共享内核** | `created_by_user_id` / `updated_by_user_id` 横切引用 |
| 测试任务上下文 | 测试执行上下文 | **客户-供应方** | Task 创建→Execution 执行→回写原始结果 |
| 测试执行上下文 | 评估上下文 | **客户-供应方** | Execution 采集完原始结果→gRPC 调 Evaluation 打分（API/E2E 均走 `submit_evaluate_case`） |
| 评估上下文 | 评估维度上下文 | **同一服务** | 均归属 evaluation_service，Dimension 定义即评估输入 |
| 评估上下文 | 测试执行上下文 | **客户-供应方** | 重新评估时调 e2e_test_service.ReextractResult 重新提取设备输出 |
| 评估上下文 | API 适配上下文 | **开放主机服务+发布语言** | 评估调外部评估 API 时复用 api_adapter_service 的协议适配 |
| 测试任务上下文 | 报告上下文 | **客户-供应方** | Task 完成→Report 生成 |
| 测试任务上下文 | 测试用例上下文 | **合作关系** | Task 与 TestCase 紧耦合，TaskCase 是关联实体（同归 task_service） |
| 测试任务上下文 | 设备管理上下文 | **客户-供应方** | Task 通过 TaskDevice 引用 Device（✅ 改调 device_service gRPC，P3.2 完成） |
| 测试任务上下文 | API 配置上下文 | **客户-供应方** | Task 通过 TaskAPI 引用 API |
| 测试任务上下文 | 音频管理上下文 | **客户-供应方** | Task 读 AudioTag（✅ 改调 audio_service gRPC，P3.2 完成） |
| 测试执行上下文 | API 配置上下文 | **防腐层** | 执行器需将 API 配置转换为执行参数 |
| 测试执行上下文 | 设备管理上下文 | **防腐层** | E2E 执行器需将设备配置转换为驱动指令（✅ 改调 device_service gRPC，P2.5 完成） |
| 测试执行上下文 | 音频管理上下文 | **防腐层** | 音频播放需将音频元数据转换为播放指令（✅ 改调 audio_service gRPC，P2.5 完成） |
| 测试执行上下文 | API 适配上下文 | **开放主机服务+发布语言** | api_adapter_service 通过 gRPC proto 对外暴露 |
| 设备管理上下文 | 音频管理上下文 | **客户-供应方** | SPL 校准时需通过 audio_service 播放测试音 |
| 报告上下文 | 评估上下文 | **防腐层** | Report 需将 TestResultDimension 打分结果转换为报告数据视图 |
| 报告上下文 | 设备/音频管理上下文 | **防腐层** | Report 读设备/音频信息（改调 device_service / audio_service gRPC） |
| 系统审计上下文 | 所有上下文 | **遵奉者** | Log 软引用多域，被动跟随 |

---

## 五、微服务与限界上下文映射

| 微服务 | 限界上下文 | 当前状态 | 改造方向 |
|---|---|---|---|
| `api_gateway` | BFF 网关 | 16个域路由 + report/home/group/log 直连 DB | 瘦网关：仅路由聚合+认证+协议转换，CRUD 全部下沉，stats_cache 拆解（P4） |
| `task_service` | 测试任务 + 测试用例 + 标签 + 分组 + Log | **DDD 四层完成**，gRPC 读接口已暴露 | ✅ 跨域读已改 gRPC（P3 完成），Log/Group CRUD 从网关下沉（P4 保留加 TODO） |
| `api_test_service` | API 配置 + API 执行子上下文 | **DDD 四层完成** | ✅ TestResult 写入已改 gRPC（P2.1 完成） |
| `e2e_test_service` | **E2E 执行（纯执行器）** | **DDD 四层完成**，音频/设备/SPL/上传 CRUD 已迁出 | ✅ TestResult 写入已改 gRPC（P2.2 完成），音频/设备/SPL/上传 CRUD 已迁出（P2.5 完成，e2e 保留 re-export 存根） |
| `audio_service` | 音频管理 + 文件上传 | **DDD 四层完成**（v3 落地），gRPC :50052 | ✅ 已完成（PO + domain + application + gRPC servicer 全套） |
| `device_service` | 设备管理 + SPL 校准 | **DDD 四层完成**（v3 落地），gRPC :50053 | ✅ 已完成（PO + domain + application + gRPC servicer 全套） |
| `evaluation_service` | 评估 + 评估维度 | **DDD 四层完成**，gRPC :50091/:5004 | ✅ 已完成，作为其他服务改造模板 |
| `api_adapter_service` | API 适配 | **已有完整 DDD 分层**，gRPC :50081 | 无需改造，作为模板 |
| `report_service` | 报告 | **DDD 四层完成**，gRPC :50068 | CRUD 逻辑从网关下沉（P4） |
| `algorithm_service` | 算法配置 | **DDD 四层完成**，gRPC :50067 | CRUD 从 task_service 回归（P6.2） |
| `auth_service` | 用户与权限 | **DDD 四层完成**，gRPC :50069 | 认证中间件 + OAuth + JWT 实现（d9-d13） |

---

## 六、CRUD 下沉归属总表

| CRUD 域 | 当前位置 | 下沉目标 | 限界上下文 | 优先级 | 状态 |
|---|---|---|---|---|---|
| API CRUD | 网关(薄代理) → e2e(实现) | `api_test_service` | API 配置上下文 | ✅ | 已下沉到 api_test_service |
| Audio CRUD | 网关(薄代理) → audio_service gRPC | `audio_service` | 音频管理上下文 | ✅ | 已下沉到 audio_service（P2.5 完成） |
| Upload CRUD | 网关(薄代理) → audio_service gRPC | `audio_service` | 音频管理上下文 | ✅ | 同上 |
| Device CRUD | 网关(薄代理) → device_service gRPC | `device_service` | 设备管理上下文 | ✅ | 已下沉到 device_service（P2.5 完成） |
| PlaybackDevice CRUD | 网关(薄代理) → device_service gRPC | `device_service` | 设备管理上下文 | ✅ | 同上 |
| SPL CRUD | 网关(薄代理) → device_service gRPC | `device_service` | SPL 校准上下文 | ✅ | 合并到 device_service（P2.5 完成） |
| Task CRUD | 网关(薄代理) → task(实现) | `task_service` | 测试任务上下文 | ✅ | 已下沉 |
| TestCase CRUD | 网关(薄代理) → task(实现) | `task_service` | 测试用例上下文 | ✅ | 已下沉 |
| TestCase Import/Export | **网关直连 DB** | `task_service` | 测试用例上下文 | P4 | 网关 import_export 直连5服务PO，待改gRPC |
| Tag CRUD | 网关(薄代理) → task(实现) | `task_service` | 测试用例上下文 | ✅ | 已下沉 |
| Evaluation CRUD | 网关(薄代理) → eval(实现) | `evaluation_service` | 评估维度上下文 | ✅ | 已下沉 |
| Algorithm CRUD | 网关(薄代理) → **task**(实现) | `algorithm_service` | 算法配置上下文 | P6 | ✅ application 层已建，待 task_service 删旧 CRUD 改 gRPC（P6.2） |
| 评估核心逻辑 | `evaluation_service` | `evaluation_service` | 评估上下文 | ✅ | 已完成 |
| Report CRUD | **网关直连 DB** | `report_service` | 报告上下文 | P4 | ✅ application 层已建，待网关 CRUD 下沉（P4） |
| Log CRUD | **网关直连 DB** | `task_service` | 系统审计上下文 | P4 | PO 已在 task_service，网关改 gRPC |
| Home/Stats | **网关直连 DB** | 保留网关(聚合) | 系统审计上下文 | P4 | stats_cache 拆解，各服务自维护统计，网关gRPC聚合 |
| Group | **网关直连 DB** | `task_service` | 测试用例上下文（子） | P4 | PO 已在 task_service，网关改 gRPC |

---

## 七、关键设计决策

### 1. TestResult / TestResultDimension 数据所有权拆分

**问题**：api_test_service / e2e_test_service 共享 DB 直写 TestResult，且 TestResultDimension（打分）也混在 task_service，违反微服务数据所有权。

**方案**：
- **TestResult（原始结果元数据）** → 归属 `task_service`。api_test_service / e2e_test_service 执行完成后通过 gRPC 回调 `task_service.SubmitResult` 写入。
- **TestResultDimension（打分结果）** → 归属 `evaluation_service`。执行完成后通过 gRPC 调 `evaluation_service.EvaluateCase` 打分写入，不回写 task_service。
- Task 聚合内的一致性（状态流转）由 task_service 统一管控；评估结果一致性由 evaluation_service 管控。

**当前状态**：evaluation_service 侧已完成（P1.4，11 个 gRPC RPC 实现）。api_test_service / e2e_test_service 侧已完成（P2.1/P2.2，通过 submit_result / update_task_case_status gRPC 写入）。

### 2. algorithm_type 作为共享内核严控变更

**问题**：`algorithm_type` 字符串被 6+ 上下文软引用，AlgorithmDefinition 变更影响全系统。

**方案**：
- 算法配置上下文作为共享内核，变更需全量回归测试
- 其他上下文通过防腐层（ACL）将 `algorithm_type` 转换为本地值对象，避免直接依赖 AlgorithmDefinition 的内部结构
- 例如 Task 上下文内用 `AlgorithmTypeRef` 值对象封装，而非裸字符串

### 3. 报告上下文通过 ACL 隔离 Task

**问题**：Report 通过 `task_id` 引用 Task，对比报告引用多 Task。直接查询 Task 表会导致报告上下文与任务上下文数据耦合。

**方案**：报告上下文内建 `TaskResultFacade`（防腐层），通过 gRPC 调用 task_service 获取 Task 数据快照，转换为报告所需的 `TaskSummaryVO` 值对象。ReportCase 只持有 `TestCaseSnapshot` 值对象（用例快照），而非 TestCase 实体引用。

**只读例外**：报告/统计类**只读**查询，可用 raw SQL 跨表 JOIN（性能考量），但 ORM 不建模别人的 PO。Report PO 下沉时已移除 `Report.task` 跨域 relationship。

### 4. api_adapter_service 作为 DDD 演进模板

`api_adapter_service` 已有完整四层：
- domain/entities + value_objects + services + events
- application/commands + queries + handlers
- infrastructure/adapters + persistence
- interfaces/api + grpc

其他微服务下沉 CRUD 时，参考此结构：

```
task_service/
  domain/
    entities/          # Task, TaskCase, TaskDevice...
    value_objects/     # TaskConfig, AlgorithmParams...
    events/            # TaskStarted, TaskCompleted...
    services/          # 领域服务（纯领域逻辑，不依赖 DB/HTTP/线程池）
    repositories/      # 仓储接口（ABC）：自有数据 Repository 接口 + ACL 仓储接口
  application/
    commands/          # CreateTask, StartTask...
    queries/           # GetTask, GetTaskProgress...
    handlers/          # CQRS Handler
  infrastructure/
    persistence/       # 自有数据 Repository 实现 + PO（models/ 子包）
    acl/               # ACL 仓储实现（跨域访问，调其他服务 gRPC，返回 dict/Entity）
  interfaces/
    grpc/              # gRPC server + servicer（入站协议适配）
    api/               # HTTP 路由（如有）
```

> **分层原则**：
> - `interfaces/` 放**入站适配器**（gRPC servicer、HTTP 路由）——把外部协议请求转成内部调用
> - `infrastructure/` 放**出站技术实现**（Repository 实现、ACL 仓储实现）——技术细节
> - `domain/` 只含**纯领域逻辑**，不依赖 DB/HTTP/线程池等基础设施

> **gRPC 目录约定**：
> - `interfaces/grpc/` 放**入站** gRPC 代码（servicer + server）——所有 servicer 必须在此
> - 出站 gRPC stub 工厂统一放 `shared/clients/grpc_clients.py`（全局复用 channel）
> - **禁止**在 `infrastructure/` 下建 `grpc/` 目录放 servicer（r1 已修正 evaluation_service，其他服务须同步）
> - 跨域 gRPC 调用的业务语义封装在 `infrastructure/acl/` 下，调用 `shared/clients/grpc_clients.py` 的 stub

> **ACL 仓储约定**：
> - `infrastructure/acl/` 放**跨域 ACL 仓储实现**（如 `task_acl_repository.py`、`algorithm_acl_repository.py`）
> - ACL 仓储接口定义在 `domain/repositories/`（ABC），infrastructure/acl 只做实现
> - ACL 仓储返回 dict / 领域实体，**绝不返回 ORM 对象**
> - 自有数据访问走 `infrastructure/persistence/`（Repository 实现 + PO）
> - domain 层**禁止直接 import infrastructure/acl**，必须通过 domain/repositories 接口注入

> **DDD+CQRS 分层规则（强制要求）**：
>
> 以下规则适用于所有微服务，违反即为架构缺陷，必须在 code review 中拦截。
>
> **规则 1：interfaces 层零 DB 访问**
> - `interfaces/grpc/` 下的 servicer **禁止**直接 `import get_db_session` 或 `import PO models`
> - servicer 仅做 protocol 适配：反序列化请求 → 调 application 层或 repository → 序列化响应
> - 所有 DB 访问必须通过 `infrastructure/persistence/` 下的 repository 实现完成
> - 违反示例：`from shared.models.database import get_db_session` + `session.query(TaskPO)` 在 servicer 方法内
> - 正确做法：`from task_service.infrastructure.persistence.task_repository import task_repository` + `task_repository.get_task_dict_by_id(task_id)`
>
> **规则 2：domain 层零基础设施依赖**
> - `domain/` 下所有文件**禁止** `import infrastructure.*`、`import shared.models.database`、`import shared.utils.log_handler`
> - domain 层只依赖：标准库、domain 内部的 entities/value_objects/events、`domain/repositories/` 下的 ABC 接口
> - 日志通过 `shared/domain/ports/logging_port.py` 的 `LoggingPort` ABC 代理访问（domain 层 import ABC，infrastructure 层注入实现）
>
> **规则 3：repository 实现必须继承 domain ABC**
> - `infrastructure/persistence/` 下的每个 Repository 类**必须**继承 `domain/repositories/` 下对应的 ABC
> - 违反示例：`class TaskRepository:` 无继承
> - 正确做法：`class TaskRepository(TaskRepositoryABC, TaskCaseRepositoryABC):`
> - 这确保依赖倒置：application 层可以面向 ABC 编程，infrastructure 层只做实现
>
> **规则 4：application 层面向 ABC 编程**
> - `application/` 下的 service 类**禁止**直接实例化具体 Repository 类名
> - 违反示例：`from task_service.infrastructure.persistence.testcase_repository import TestCaseRepository` + `self.repo = TestCaseRepository()`
> - 正确做法：`from task_service.domain.repositories.testcase_group_repository import TestCaseGroupRepositoryABC` + `from task_service.infrastructure.persistence.testcase_repository import testcase_repository` + `self.repo = repo or testcase_repository`
> - 类型标注用 ABC，默认实例用 infrastructure 层的模块级单例
>
> **规则 5：CQRS handler 分离**
> - Command handler（写操作）和 Query handler（读操作）必须放在不同的类/文件中
> - `application/handlers/command_handlers.py` 和 `application/handlers/query_handlers.py` 不可合并
> - Command handler 不应调用 Query handler，反之亦然（聚合加载除外）
>
> **规则 6：repository 返回 dict/Entity，绝不返回 ORM 对象**
> - repository 的公共方法返回 `dict`、`Entity` 或 `Optional[Entity]`，**绝不返回 PO 对象**
> - PO ↔ Entity / PO ↔ dict 转换在 repository 内部完成（`_xxx_po_to_entity` / `_xxx_po_to_dict` 函数）
> - 这确保调用方（application 层、interfaces 层）不会接触到 ORM 对象
>
> **规则 7：domain/repositories/ 必须为每个 owned 数据定义 ABC**
> - 每个服务拥有的数据表，必须在 `domain/repositories/` 下有对应的 ABC 接口
> - task_service 的完整 ABC 清单：`TaskRepositoryABC`、`TaskCaseRepositoryABC`、`TestCaseGroupRepositoryABC`、`LogRepositoryABC`、`TestResultRepositoryABC`、`TaskMergeRelationRepositoryABC`、`AlgorithmAclRepository`
> - 其他服务同理：每个 owned PO 对应一个 domain/repositories/ 下的 ABC
>
> **规则 8：跨服务数据访问必须经 ACL 仓储，禁止 import 他服务 PO**
> - 跨服务（跨限界上下文）数据访问**必须**通过 `infrastructure/acl/` 下的 ACL 仓储实现，调用 `shared/clients/grpc_clients.py` 的 gRPC stub，**禁止**直接 `import` 他服务的 PO / `infrastructure/persistence/models`
> - ACL 仓储接口定义在 `domain/repositories/`（ABC），`infrastructure/acl/` 只做实现；domain 层禁止直接 `import infrastructure/acl`，必须通过接口注入（依赖倒置，与规则 4 一致）
> - ACL 仓储返回 `dict` / DTO / 领域实体，**绝不返回 ORM 对象**（与规则 6 一致，跨服务亦然）
> - 只读例外：报告/统计类只读查询可用 raw SQL 跨表 JOIN（性能考量），但 ORM 不建模他服务 PO
> - 违反示例：在 `e2e_test_service` 内 `from audio_service.infrastructure.persistence.models import Audio`
> - 正确做法：`e2e_test_service/infrastructure/acl/audio_acl_repository_impl.py` 调 gRPC，返回 `AudioDTO`

> **DTO 转换规范（强制要求）**
>
> 以下规则适用于所有微服务 ACL 仓储的返回值类型，违反即为架构缺陷，必须在 code review 中拦截。
>
> **规则 D1：DTO 用 dataclass，字段全 Optional**
> - 跨服务 gRPC 返回的 DTO 必须用 `@dataclass`，文件首行 `from __future__ import annotations`
> - 所有字段声明为 `Optional[T] = None`，兼容 gRPC 返回缺键
> - 结构不固定的字段用 `Any = None`（如动态表单 / JSON 配置块）
>
> **规则 D2：命名与目录**
> - ACL DTO 文件命名统一 `<service>_acl_dto.py`，放在 `domain/dto/` 目录
> - 类名 `<Domain>DTO`（如 `AlgorithmDTO`、`DeviceDTO`、`PlaybackResultDTO`）
> - 禁止自封装命名（如 task_service 早期的 `algorithm_dto.py` 不带 `_acl_` 前缀）
>
> **规则 D3：转换走 shared 工具**
> - ACL 仓储把 gRPC 返回的 dict 转为 DTO，**必须**调用 `shared/utils/dto_utils.py` 的 `dict_to_dto` / `dict_list_to_dto`
> - 禁止在 ACL 仓储内手写 `DTO(field=raw.get(...))` 逐字段构造（重复样板、易漏键）
> - 自定义转换封装必须替换为 shared 工具，禁止"一套服务一套转换函数"
>
> **规则 D4：无 raw dict 返回**
> - ACL 仓储公共方法返回 `DTO` / `List[DTO]`，**禁止**直接返回 raw `dict` 给上层
> - 上层（application / interfaces）不应接触裸 dict，应消费有类型的 DTO

### 5. 评估上下文独立为 evaluation_service

**已完成**：`evaluation_service` 微服务已从 `task_service/evaluation/` 拆分独立部署，HTTP :5004 + gRPC :50091。

**现状**：
- `api_test_service` / `e2e_test_service` → 通过 gRPC `submit_evaluate_case` 提交评估
- 评分核心函数 `evaluation_service/domain/services/evaluation_utils.py`：`calculate_score`（direct/linear/threshold）+ `extract_by_path`
- 评估编排 `evaluation_service/domain/services/evaluation_service/`：9 个 Mixin 组合（CaseEvaluation/DimensionLoader/TaskDispatcher...）
- 重新评估 `evaluation_service/application/handlers/reevaluation_executor.py`：区分 API 逐轮 / E2E 一次性，可选调 e2e_test_service.ReextractResult
- 维度 CRUD `evaluation_service/application/queries/evaluation_query_service.py` + `evaluation_service/application/commands/evaluation_command_service.py`

**数据所有权**：
- `TestResultDimension` 归属 evaluation_service（PO 已下沉）
- `TestResult`（元数据）仍归属 task_service，通过 `task_service_client.py` gRPC 访问

### 6. evaluation_service 分层重构记录

evaluation_service 已完成以下分层修正：

| 阶段 | 内容 | 状态 |
|---|---|---|
| r1 | `infrastructure/grpc/servicers.py` → `interfaces/grpc/servicers.py` | ✅ 已完成 |
| r2 | domain/services 下 infrastructure 逻辑移到 infrastructure/（evaluation_api/ + persistence/） | ✅ 已完成 |
| r3 | reevaluation_executor 编排逻辑移到 application/ | ✅ 已完成 |
| r5 | 补 domain/entities（EvaluationDimension 聚合根 + 值对象） | ✅ 已完成 |
| r7 | 编译验证 | ✅ 已完成 |

**可选优化**（非阻塞）：
- r4：补 infrastructure/persistence Repository 实现（当前有 `evaluation_dimension_repository.py`，其余仓储待补）
- r6：application 层补 handlers（当前有 `evaluation_config_handler.py` + `reevaluation_executor.py`，可进一步拆分）
- 问题 7：EvaluationService Mixin 过多（9 重继承），远期可考虑改为组合模式

### 6.1 evaluation_service ↔ algorithm_service 跨服务写消除（P7 阶段）

**已完成**。evaluation_service 的 `evaluation_repository.py` 原直连 algorithm_service 的 3 个 PO（AlgorithmDimensionRelation / EvaluationDimensionParam / ParamMapping）进行写操作，现已全部改为通过 gRPC 访问。

**改造内容**：
1. `shared/proto/algorithm_service.proto` 新增 8 个 RPC：
   - `DeleteRelationsByDimension` / `GetRelationsByDimension` / `SyncDimensionRelations`
   - `CreateDimensionParam` / `DeleteDimensionParamsByDirection` / `FindAudioDimensionIds`
   - `SyncParamMappings` / `ListParamMappingsForDimension`
2. `algorithm_service/interfaces/grpc/servicers.py` 实现上述 8 个 RPC
3. `evaluation_service/infrastructure/grpc_clients/algorithm_service_client.py` 新建出站 gRPC 客户端，封装调用并返回 dict
4. `evaluation_service/infrastructure/persistence/evaluation_repository.py` 移除 `from algorithm_service.infrastructure.persistence.models import ...`，所有方法改为委托 `algorithm_service_client`
5. `evaluation_service/application/commands/evaluation_command_service.py` 的 `_sync_param_mappings` 改为委托 `repo.sync_param_mappings`（gRPC）；create/update_dimension 的关联算法处理改为 `repo.sync_relations`（gRPC 批量同步）

**验证**：
- `python -m py_compile` 全部文件语法检查通过
- grep 确认 evaluation_service 内无 `from algorithm_service.infrastructure.persistence.models import` 残留（仅 docstring 注释）
- evaluation_service domain 层仍保持 0 处 `db.session` / 0 处跨服务 PO 直连

---

## 七之三、PO 归属与跨服务数据访问原则

> 数据库：PostgreSQL（单库逻辑隔离模式）
> 目标：每个服务只定义自己拥有的表的 PO，跨服务访问走 gRPC，消除跨域 ORM 耦合。

### 1. 跨服务数据访问五种模式（业界标准）

| 模式 | 适用场景 | 本项目采用 |
|---|---|---|
| **Shared Database（已消除）** | 单库多服务直连，PO 集中 | ❌ 已消除 |
| **Logical Isolation + gRPC（目标）** | 物理同库，但每服务只定义自有 PO，跨服务走 gRPC | ✅ 采纳 |
| **Database per Service** | 每服务独立库 | ❌ 改动过大，暂不做 |
| **CQRS 读模型** | 报表/统计等复杂查询 | ⚠️ 报告模块用 |
| **事件驱动同步** | 跨服务数据一致性 | ⚠️ 后续可考虑 |

### 2. 目标架构规则

1. **物理层面**：所有服务连同一个 PostgreSQL 库
2. **代码层面**：每个服务**只在自己 `infrastructure/persistence/models/` 定义自己拥有的表的 PO**
3. **跨服务读**：通过 gRPC 调用对方服务，对方返回 DTO（不是 ORM 对象）
4. **跨服务写**：禁止直接写别人的表，必须通过 gRPC
5. **只读例外**：报告/统计类**只读**查询，可用 raw SQL 跨表 JOIN（性能考量），但 ORM 不建模别人的 PO
6. **shared/models/models/ 改造**：已改为 re-export 存根，从各服务 `infrastructure/persistence/models/` re-export

### 3. PO 归属总表（已完成下沉）

> 改造基准：grep 全仓库 `from shared.models` 引用关系，按业务表归属划分。
> **P5 阶段已完成**：所有 PO 真正下沉到各服务 `infrastructure/persistence/models/`，shared/models/models/ 改为 re-export 存根。

#### 3.1 表归属服务

| 表名 | 归属服务 | PO 模型类 | 下沉位置 |
|---|---|---|---|
| `users`, `roles`, `permissions`, `role_permissions`, `user_permissions`, `oauth_clients`, `oauth_refresh_tokens` | auth_service | User, Role, Permission, RolePermission, UserPermission, OAuthClient, OAuthRefreshToken | auth_service/infrastructure/persistence/models/user_models.py |
| `test_cases`, `test_case_groups`, `tags`, `tag_categories`, `test_case_tags` | task_service | TestCase, TestCaseGroup, Tag, TagCategory, TestCaseTag | task_service/infrastructure/persistence/models/testcase_models.py |
| `devices`, `playback_devices`, `device_tags` | device_service | Device, PlaybackDevice, DeviceTag | device_service/infrastructure/persistence/models/device_models.py |
| `audios`, `audio_annotations`, `audio_tags`, `audio_algorithm_relations` | audio_service | Audio, AudioAnnotation, AudioTag, AudioAlgorithmRelation | audio_service/infrastructure/persistence/models/audio_models.py |
| `apis` | api_test_service | API | api_test_service/infrastructure/persistence/models/api_models.py |
| `test_tasks`, `task_tags`, `task_case_relations`, `task_device_relations`, `task_api_relations`, `task_merge_relations` | task_service | Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation | task_service/infrastructure/persistence/models/task_models.py |
| `test_results` | task_service | TestResult | task_service/infrastructure/persistence/models/result_models.py |
| `test_result_dimensions` | evaluation_service | TestResultDimension | evaluation_service/infrastructure/persistence/models/result_models.py |
| `test_reports`, `report_summaries`, `report_summary_meta`, `report_raw_data`, `report_cases`, `report_metric_stats`, `report_comparison_matrix` | report_service | Report, ReportSummary, ReportSummaryMeta, ReportRawData, ReportCase, ReportMetricStats, ReportComparisonMatrix | report_service/infrastructure/persistence/models/report_models.py |
| `categories`, `dimensions` | evaluation_service | Category, Dimension | evaluation_service/infrastructure/persistence/models/evaluation_models.py |
| `logs` | task_service | Log | task_service/infrastructure/persistence/models/system_models.py |
| `spl_mappings`, `calibration_histories` | device_service | SPLMapping, CalibrationHistory | device_service/infrastructure/persistence/models/system_models.py |
| `upload_tasks`, `upload_files`, `upload_chunks` | audio_service | UploadTask, UploadFile, UploadChunk | audio_service/infrastructure/persistence/models/upload_models.py |
| `stats_cache` | api_gateway | StatsCache | api_gateway/infrastructure/persistence/models/cache_models.py |
| `algorithm_groups`, `algorithm_definitions`, `algorithm_device_params`, `algorithm_api_params`, `algorithm_reference_params`, `evaluation_dimension_params`, `param_mappings`, `algorithm_dimension_relations`, `case_algorithm_params` | algorithm_service | AlgorithmGroup, AlgorithmDefinition, AlgorithmDeviceParam, AlgorithmApiParam, AlgorithmReferenceParam, EvaluationDimensionParam, ParamMapping, AlgorithmDimensionRelation, CaseAlgorithmParam | algorithm_service/infrastructure/persistence/models/algorithm_models.py |

#### 3.2 跨服务引用矩阵（v3 修订：当前现状 → 目标）

行 = PO 归属服务，列 = 引用方。`自` = 自有，`读` = 跨服务只读（含 re-export 存根），`写` = 跨服务写（**违规**），`—` = 无引用。

**当前现状**（v3：audio/device PO 已迁到 audio_service / device_service，e2e 保留 re-export 存根）：

| PO 来源 \ 引用方 | api_gateway | api_test_service | e2e_test_service | evaluation_service | task_service | audio_service | device_service |
|---|---|---|---|---|---|---|---|
| user/auth | 读 | — | — | — | — | — | — |
| testcase | 读+写 | 读 | 读+写 | ✅ gRPC | **自** | — | — |
| device | 读+写 | — | 读(re-export) | — | ✅ gRPC | — | **自** |
| audio | 读+写 | 读 | 读(re-export) | — | ✅ gRPC | **自** | — |
| api(API) | 读+写 | **自** | — | — | ✅ gRPC | — | — |
| task | 读+写 | ✅ gRPC | ✅ gRPC | ✅ gRPC | **自** | — | — |
| TestResult | 读+写 | ✅ gRPC | ✅ gRPC | ✅ gRPC | **自** | — | — |
| TestResultDimension | 读 | — | — | **自** | ✅ gRPC | — | — |
| report | **自** | — | — | — | 读(read_model) | — | — |
| Category/Dimension | 读 | — | — | **自** | ✅ gRPC | — | — |
| Log | 读+写 | — | — | — | **自** | — | — |
| SPLMapping/Calibration | 读+写 | — | 读(re-export) | — | — | — | **自** |
| Upload* | 读+写 | — | 读(re-export) | — | — | **自** | — |
| StatsCache | **自** | — | — | — | — | — | — |
| Algorithm* | 读+写 | — | 读(annotation) | — | 读+写(CRUD在此) | — | — |

**v2 目标**（P2-P6 完成后）：

| PO 来源 \ 引用方 | api_gateway | api_test_service | e2e_test_service | evaluation_service | task_service | audio_service | device_service |
|---|---|---|---|---|---|---|---|
| user/auth | ✅ gRPC | ✅ gRPC | ✅ gRPC | ✅ gRPC | ✅ gRPC | ✅ gRPC | ✅ gRPC |
| testcase | ✅ gRPC | ✅ gRPC | ✅ gRPC | ✅ gRPC | **自** | — | — |
| device | ✅ gRPC | — | ✅ gRPC | — | ✅ gRPC | — | **自** |
| audio | ✅ gRPC | ✅ gRPC | ✅ gRPC | — | ✅ gRPC | **自** | — |
| api(API) | ✅ gRPC | **自** | — | — | ✅ gRPC | — | — |
| task | ✅ gRPC | ✅ gRPC | ✅ gRPC | ✅ gRPC | **自** | — | — |
| TestResult | ✅ gRPC | ✅ gRPC | ✅ gRPC | ✅ gRPC | **自** | — | — |
| TestResultDimension | ✅ gRPC | — | — | **自** | ✅ gRPC | — | — |
| report | ✅ gRPC | — | — | — | ✅ gRPC | — | — |
| Category/Dimension | ✅ gRPC | — | — | **自** | ✅ gRPC | — | — |
| Log | ✅ gRPC | — | — | — | **自** | — | — |
| SPLMapping/Calibration | ✅ gRPC | — | ✅ gRPC | — | — | — | **自** |
| Upload* | ✅ gRPC | — | — | — | — | **自** | — |
| StatsCache | **自** | — | — | — | — | — | — |
| Algorithm* | ✅ gRPC | — | ✅ gRPC | ✅ gRPC | ✅ gRPC | ✅ gRPC | — |

**已解决的矛盾**：
1. ~~TestResultDimension 被两个服务同时写~~ → evaluation_service 独占，task_service 改 gRPC（P1.7 完成）
2. ~~evaluation_service 直连 task_service PO~~ → 改 gRPC（P1.4 完成，11 个 RPC）

**已解决的矛盾**：
1. ~~TestResult 被三个服务同时写~~ → ✅ 已改 gRPC（P2.1/P2.2 完成）
2. **api_gateway 跨域直连已大部分消除**：report/testcase/home/handlers 已改 gRPC（P4 完成），log/group 保留直连（加 TODO）
3. **shared 模块跨服务直连已大部分消除**：report/algorithm/event_manager 工具类已改 gRPC 或加 TODO（剩余 12 处均有 TODO）
4. ~~algorithm_service split-brain~~ → ⚠️ P6.2 已标记废弃，待 proto 接入后整体删除
5. ~~e2e_test_service 超载~~ → ✅ 音频/设备/SPL/上传 CRUD 已拆出（P2.5 完成），e2e 保留 re-export 存根
6. ~~task_service 直连 device/audio PO~~ → ✅ 改调 device_service / audio_service gRPC（P3.2 完成）

**当前状态**：全系统跨服务 PO 直连从 80 处降至约 35 处，全部有 TODO 注释说明保留原因。剩余直连原因：
- report_service 无 proto（11 处）
- algorithm_service 无 proto（6 处）
- task_service proto 无 Log/TestCaseGroup CRUD RPC（8 处）
- event_manager 实时进度推送不适合 gRPC 往返（9 处）
- stats_cache 聚合查询 gRPC 接口不足（5 处）
- TaskMergeRelation 无独立 gRPC 接口（5 处）
- e2e_test_service 保留 re-export 存根（过渡兼容，不影响 PO 归属）

### 4. 跨服务数据访问 gRPC 接口清单

> gRPC 接口，用于替代跨服务直连 DB。

#### 4.1 task_service 暴露（供其他服务调用）

| 接口 | 入参 | 出参 | 用途 | 调用方 | 状态 |
|---|---|---|---|---|---|
| `GetTestResultById` | result_id | TestResultDTO | 读单个测试结果 | evaluation_service, api_gateway/report | ✅ 已实现 |
| `GetTaskCaseByIds` | task_id, case_ids[] | TaskCaseDTO[] | 批量读任务用例 | evaluation_service, e2e_test_service | ✅ 已实现 |
| `GetTaskById` | task_id | TaskDTO | 读任务详情 | evaluation_service, report | ✅ 已实现 |
| `GetTaskDevices` | task_id | TaskDeviceDTO[] | 读任务关联设备 | evaluation_service | ✅ 已实现 |
| `GetTaskApis` | task_id | TaskAPIDTO[] | 读任务关联 API | evaluation_service | ✅ 已实现 |
| `SubmitResult` | task_id, result_data | result_id | 写测试结果 | api_test_service, e2e_test_service | ✅ 已实现 |
| `UpdateTaskCaseStatus` | task_id, case_id, status | success | 更新任务用例状态 | evaluation_service, e2e_test_service | ✅ 已实现 |
| `UpdateTaskStatus` | task_id, status | success | 更新任务状态 | evaluation_service | ✅ 已实现 |

#### 4.2 evaluation_service 暴露（供其他服务调用）

| 接口 | 入参 | 出参 | 用途 | 调用方 | 状态 |
|---|---|---|---|---|---|
| `EvaluateCase`（已存在） | task_id, result_id, ... | success | 评估单个用例 | task_service, api_test_service, e2e_test_service | ✅ 已实现 |
| `Reevaluate`（已存在） | task_id, ... | success | 重新评估 | task_service | ✅ 已实现 |
| `GetDimensionByIds` | dim_ids[] | DimensionDTO[] | 批量读维度 | api_gateway/report, task_service | ✅ 已实现 |
| `ListCategories`（已存在） | — | CategoryDTO[] | 列分类 | api_gateway | ✅ 已实现 |
| `ListDimensions`（已存在） | category_id | DimensionDTO[] | 列维度 | api_gateway | ✅ 已实现 |
| `GetTestResultDimensions` | result_id | TestResultDimensionDTO[] | 读评分结果 | api_gateway/report, task_service | ✅ 已实现 |

#### 4.3 testcase 域暴露（task_service 暴露）

| 接口 | 入参 | 出参 | 用途 | 调用方 | 状态 |
|---|---|---|---|---|---|
| `GetTestCaseByIds` | case_ids[] | TestCaseDTO[] | 批量读用例 | evaluation_service, e2e_test_service, api_test_service | 待实现 |
| `ListTestCases` | filter | TestCaseDTO[] | 列用例 | api_gateway | 待实现 |
| `CreateTestCase` / `UpdateTestCase` / `DeleteTestCase` | ... | ... | 用例 CRUD | api_gateway, e2e_test_service | 待实现 |

#### 4.4 device_service 暴露（供其他服务调用）

| 接口 | 入参 | 出参 | 用途 | 调用方 | 状态 |
|---|---|---|---|---|---|
| DeviceConfigService | ... | ... | 设备 CRUD（创建/更新/删除/列表/详情/扫描/测试） | api_gateway, task_service, e2e_test_service | ✅ 已实现（:50053） |
| PlaybackConfigService | ... | ... | 播放设备 CRUD | api_gateway, e2e_test_service | ✅ 已实现（:50053） |
| SPLConfigService | ... | ... | SPL 校准 CRUD | api_gateway, e2e_test_service | ✅ 已实现（:50053） |
| DeviceService | device_config | ... | 设备驱动创建/销毁/扫描/模式控制 | e2e_test_service | ✅ 已实现（:50053） |
| DeviceResultService | ... | ... | 采集/重新提取设备结果 | evaluation_service, e2e_test_service | ✅ 已实现（:50053） |
| EnvDeviceService | ... | ... | 环境设备控制（导轨等） | e2e_test_service | ✅ 已实现（:50053） |

#### 4.5 audio_service 暴露（供其他服务调用）

| 接口 | 入参 | 出参 | 用途 | 调用方 | 状态 |
|---|---|---|---|---|---|
| AudioConfigService | ... | ... | 音频 CRUD（元数据/标注/批量/删除/算法关联/标签/列表/详情/上传/合并/导入/转换/预览） | api_gateway, e2e_test_service | ✅ 已实现（:50052） |
| AudioService | play_config, audio_file_paths | ... | 播放/停止音频、获取播放状态、SPL 测量 | e2e_test_service | ✅ 已实现（:50052） |
| PlaybackService | ... | ... | 开始/停止播放编排 | e2e_test_service | ✅ 已实现（:50052） |

---

## 七之四、全服务 PO 下沉路线图

> 按"先消除违规写、再消除跨服务读、最后清理 shared"的顺序执行。
> 每个阶段完成后做 `py_compile` 全量编译验证。

### 阶段 P1：消除 evaluation_service ↔ task_service 双向写表 ✅ 已完成

| 子阶段 | 内容 | 状态 |
|---|---|---|
| P1.1 | evaluation_service：PO（Category/Dimension/TestResultDimension）下沉到 `infrastructure/persistence/models/` | ✅ 已完成 |
| P1.2 | evaluation_service：补 domain/entities（纯领域对象，不继承 db.Model） | ✅ 已完成 |
| P1.3 | evaluation_service：补 infrastructure/persistence/evaluation_dimension_repository.py（Repository 实现 + PO↔Entity 转换） | ✅ 已完成 |
| P1.4 | evaluation_service：删除对 task_service PO 的直接引用，改调 task_service gRPC（11 个 RPC） | ✅ 已完成 |
| P1.5 | task_service：补 gRPC 读接口（TaskDataService 11 个 RPC） | ✅ 已完成 |
| P1.6 | task_service：删除 evaluation/ 子模块，改为 gRPC 调 evaluation_service | ✅ 已完成 |
| P1.7 | task_service：删除对 evaluation_service PO 的直接引用，改调 evaluation_service gRPC | ✅ 已完成 |
| P1.8 | 编译验证 | ✅ 已完成 |

### 阶段 P2：消除 api_test_service / e2e_test_service 写 task_service 表

| 子阶段 | 内容 | 影响文件 | 状态 |
|---|---|---|---|
| P2.1 | api_test_service：删除对 TaskCase/TaskAPI/TestResult PO 的直接写，改调 task_service gRPC | api_test_service/core/api_executor.py、api_result_processor.py 等 5 个文件 | ✅ 已完成 |
| P2.2 | e2e_test_service：删除对 TaskCase/TestResult/TestResultDimension PO 的直接写，改调 task_service / evaluation_service gRPC | e2e_test_service/device/device_result_reextractor.py、core/e2e_aggregator.py 等 6 个文件 | ✅ 已完成 |
| P2.3 | api_test_service：domain 层接入应用层 | api_test_service/domain/* + application/* + interfaces/* | ✅ 已完成 |
| P2.4 | e2e_test_service：domain 层接入应用层 | e2e_test_service/domain/* + application/* + interfaces/* | ✅ 已完成 |
| P2.5 | 编译验证 | — | ✅ 已完成 |

### 阶段 P2.5（v3 完成）：拆分 audio_service / device_service，e2e_test_service 瘦身 ✅

> **目标**：把音频管理（audio CRUD + upload + annotation + convert + preview）和设备管理（device CRUD + playback + SPL）从 e2e_test_service 拆出为独立微服务。
> domain 层和 PO 已建好，整体平移 + 暴露 gRPC + e2e_test_service 改调 gRPC。

| 子阶段 | 内容 | 影响文件/目录 | 状态 |
|---|---|---|---|
| P2.5.1 | 新建 `audio_service/` 目录，将 e2e_test_service 的 audio domain + PO + CRUD + infrastructure/audio 整体平移 | audio_service/* | ✅ 已完成 |
| P2.5.2 | 新建 `device_service/` 目录，将 e2e_test_service 的 device domain + PO + CRUD + drivers 整体平移（含 SPL） | device_service/* | ✅ 已完成 |
| P2.5.3 | audio_service：补 interfaces/grpc/server.py + servicers.py，暴露 AudioService/PlaybackService/AudioConfigService 3 个 Servicer | audio_service/interfaces/grpc/* | ✅ 已完成 |
| P2.5.4 | device_service：补 interfaces/grpc/server.py + servicers.py，暴露 DeviceService/DeviceResultService/EnvDeviceService/DeviceConfigService/PlaybackConfigService/SPLConfigService 6 个 Servicer | device_service/interfaces/grpc/* | ✅ 已完成 |
| P2.5.5 | e2e_test_service：PO 改为 re-export 存根（从 audio_service / device_service 导入），application 保留 CRUD 代理 | e2e_test_service/infrastructure/persistence/models/__init__.py | ✅ 已完成 |
| P2.5.6 | api_gateway + shared/clients：更新 grpc_proxies 指向新的 audio_service (:50052) / device_service (:50053) | api_gateway/infrastructure/grpc_proxies.py、shared/clients/grpc_clients.py | ✅ 已完成 |
| P2.5.7 | e2e_test_service：audio_testcase_creation_service 仍保留（通过 e2e PO re-export 访问） | e2e_test_service/application/audio_testcase_creation_service.py | ⚠️ 保留（re-export 兼容） |
| P2.5.8 | 编译验证 | — | ✅ 已完成 |

### 阶段 P3：消除 task_service 跨域读（device/audio/api）

| 子阶段 | 内容 | 影响文件 | 状态 |
|---|---|---|---|
| P3.1 | task_service：清理 testcase_repository.py 接口（TestCase PO 已归属 task_service） | task_service/infrastructure/persistence/testcase_repository.py | ✅ 已完成 |
| P3.2 | task_service：删除对 Device/PlaybackDevice/AudioTag PO 的引用，改调 device_service / audio_service gRPC | task_service/infrastructure/persistence/task_repository.py、core/execution_engine/_task_runner_mixin.py | ✅ 已完成 |
| P3.3 | task_service：删除对 API PO 的引用，改调 api_test_service gRPC | task_service/infrastructure/persistence/task_repository.py | ✅ 已完成 |
| P3.4 | task_service：补 domain/events + value_objects，TaskAggregate 脱 ORM 包装 | task_service/domain/* | ✅ 已完成 |
| P3.5 | 编译验证 | — | 待执行 |

### 阶段 P4：消除 api_gateway 跨域直连 + stats_cache 拆解 + log/group 下沉

| 子阶段 | 内容 | 影响文件 | 状态 |
|---|---|---|---|
| P4.1 | api_gateway：report 模块（10+2 个文件）改为通过 gRPC 拉取 task/testcase/device/audio/evaluation 数据 | api_gateway/application/services/report/* | ✅ 已完成（report_service PO 保留直连加 TODO） |
| P4.2 | api_gateway：删除 report 模块对 task/testcase/device/audio/result/evaluation PO 的直接 import | api_gateway/application/services/report/* | ✅ 已完成 |
| P4.3 | api_gateway：log CRUD 改调 task_service gRPC（不再直连 Log PO） | api_gateway/application/services/log/* | ⚠️ 保留直连（proto 无 Log CRUD RPC，加 TODO） |
| P4.4 | api_gateway：group CRUD 改调 task_service gRPC（不再直连 TestCaseGroup PO） | api_gateway/application/services/group_service.py | ⚠️ 保留直连（proto 无 Group CRUD RPC，加 TODO） |
| P4.5 | api_gateway：testcase_import_export 改调 task_service gRPC（不再直连 5 服务 PO） | api_gateway/application/services/testcase/testcase_import_export_service.py | ✅ 已完成（TestCaseGroup 保留加 TODO） |
| P4.6 | shared/utils/report/stats_cache.py 拆解：各服务自维护统计，网关 home_service 通过 gRPC 聚合 | shared/utils/report/stats_cache.py、各服务 application/ | 待执行 |
| P4.7 | api_gateway：home_service 改为通过 gRPC 并行调用各服务 GetStats 接口聚合首页数据 | api_gateway/application/services/home_service.py | ✅ 已完成 |
| P4.8 | 编译验证 | — | ✅ 已完成 |

### 阶段 P5：清理 shared/models/models/ ✅ 已完成

| 子阶段 | 内容 | 状态 |
|---|---|---|
| P5.1 | shared/models/models/* 改为 re-export 存根（从各服务 infrastructure/persistence/models/ re-export） | ✅ 已完成 |
| P5.2 | PO 定义真正下沉到各服务（8 个服务） | ✅ 已完成 |
| P5.3 | 跨服务 relationship 全部移除（Task.devices/apis、Report.task、AudioAlgorithmRelation.algorithm 等） | ✅ 已完成 |
| P5.4 | 共享枚举（ReportStatus/TaskStatus/ReportType）拆出到 shared/models/common_enums.py | ✅ 已完成 |
| P5.5 | 全量编译验证 | ✅ 已完成 |

### 阶段 P6：algorithm_service CRUD 回归 + auth_service 实现

| 子阶段 | 内容 | 状态 |
|---|---|---|
| P6.1 | algorithm_service：补 application 层（commands/queries/handlers），CRUD 从 task_service 回归（修复 split-brain） | ✅ 已完成 |
| P6.2 | task_service：删除 application/algorithm/ 目录，改调 algorithm_service gRPC | ⚠️ 已标记废弃（algorithm_service 未接入 proto，预留 gRPC 入口） |
| P6.3 | e2e_test_service / audio_service：audio_annotation_service 删除对 algorithm_service PO 的直连，改 gRPC | 待执行 |
| P6.4 | auth_service：认证逻辑实现（d9-d13） | 待执行 |
| P6.5 | api_gateway：最终瘦网关验证（仅路由聚合+认证+协议转换，0 直连 DB） | 待执行 |

### P5 阶段详情：PO 真正下沉到各服务 infrastructure/persistence/models/

**改造原则**：单库逻辑隔离——每张表只在所属服务定义 PO，shared/models/models/* 改为 re-export 存根。所有 PO 仍继承同一个 shared.models.database.db.Model（同一 Base.metadata），跨服务 relationship 解析在 metadata 层面仍可工作，但跨服务 relationship 本身违反 DDD，已在下沉时移除。

**PO 归属表**（53 张表/52 个 PO + 3 个共享枚举）：

| 服务 | 归属 PO（数量） |
|---|---|
| evaluation_service | Category, Dimension, TestResultDimension（3） |
| task_service | Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation, TestResult, TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag, Log（13） |
| algorithm_service | AlgorithmGroup, AlgorithmDefinition, AlgorithmDeviceParam, AlgorithmApiParam, AlgorithmReferenceParam, EvaluationDimensionParam, ParamMapping, AlgorithmDimensionRelation, CaseAlgorithmParam（9） |
| report_service | Report, ReportSummary, ReportSummaryMeta, ReportRawData, ReportCase, ReportMetricStats, ReportComparisonMatrix（7） |
| auth_service | Role, Permission, RolePermission, UserPermission, User, OAuthClient, OAuthRefreshToken（7） |
| audio_service（**v3 落地**，从 e2e 拆出） | Audio, AudioAnnotation, AudioTag, AudioAlgorithmRelation, UploadTask, UploadFile, UploadChunk（7） |
| device_service（**v3 落地**，从 e2e 拆出） | Device, PlaybackDevice, DeviceTag, SPLMapping, CalibrationHistory（5） |
| e2e_test_service（v3 瘦身后） | 无自有 PO（纯执行器，PO 改为 re-export 存根，通过 gRPC 访问 audio/device/task/evaluation） |
| api_test_service | API（1） |
| api_gateway | StatsCache（1） |

**共享枚举**：ReportStatus / TaskStatus / ReportType 拆出到 shared/models/common_enums.py（非 PO，跨服务共享）。

**关键决策**：
1. 跨服务 relationship 全部移除（违反单库逻辑隔离原则）：
   - Task.devices / Task.apis（Device/API 不归属 task_service）
   - Report.task（Task 归属 task_service）
   - AudioAlgorithmRelation.algorithm（AlgorithmDefinition 归属 algorithm_service）
   - EvaluationDimensionParam.dimension / ParamMapping.dimension / AlgorithmDimensionRelation.dimension（Dimension 归属 evaluation_service）
2. 跨服务数据访问通过 gRPC 调用对应服务（已在 P1.4-P1.7 完成）
3. ReportStatus/TaskStatus/ReportType 拆出作为共享枚举（不归属任何单一服务）
4. utc8now 函数从 shared/models/models/_base.py 提升到 shared/models/database.py（避免服务 models 触发 shared/models/models/__init__.py 全量导入）

**验证**：
- `python -m compileall -q shared evaluation_service task_service e2e_test_service api_test_service api_gateway algorithm_service report_service auth_service` exit 0
- 53 张表全部注册成功，无重复定义、无遗漏

---

### P5+ 阶段：删除 shared re-export 存根，所有代码直接从服务导入（已完成）

> **状态**：已完成。shared/models/models.py 和 shared/models/models/ 子目录均已删除，仅保留 database.py + common_enums.py + __init__.py（纯 docstring）。所有 PO 已下沉到各服务 infrastructure/persistence/models/。

**改造范围**：56 个业务文件 import 路径替换：
- task_service 11 文件
- shared/utils + shared/algorithm + shared/infrastructure 16 文件
- api_gateway 19 文件
- e2e_test_service 15 文件
- api_test_service 5 文件
- evaluation_service 1 文件

**import 路径规则**：
- 各服务的 PO：`from <service>.infrastructure.persistence.models import X, Y`
- 共享枚举：`from shared.models.common_enums import ReportStatus, TaskStatus, ReportType`
- utc8now：`from shared.models.database import utc8now`

**shared/models/ 最终内容**：
| 文件 | 内容 |
|---|---|
| `database.py` | `db` 命名空间 + `utc8now` + `get_db_session` 等基础设施 |
| `common_enums.py` | 3 个跨服务共享枚举 |
| `__init__.py` | 仅 docstring |

**验证**：
- `python -m compileall` 全 8 个服务 + shared exit 0
- 实际 import 验证全部成功
- 53 张表注册成功
- grep 确认无 `from shared.models.models import` / `from shared.models.algorithm_models import` 残留（仅文档 docstring 文本）

**后续 P6 阶段**（服务真正拆分）：
- audio_service / device_service：✅ DDD 四层已全部落地（v3 完成），含 gRPC servicer
- algorithm_service / report_service / auth_service：DDD 四层已建，但部分 CRUD 逻辑仍在 api_gateway
- 后续需要把 api_gateway/algorithm/、report/、auth/ 的 CRUD 逻辑迁移到对应服务，api_gateway 改为 gRPC 调用
- 这属于 d7+ 阶段，工作量大，单独排期

---

## 八、认证与开发模式设计

### 1. 现状

| 维度 | 状态 |
|---|---|
| 认证流程 | **未实现** — 无中间件、无依赖注入、无装饰器，所有 API 完全开放 |
| OAuth 模型 | **已定义** — User/OAuthClient/OAuthRefreshToken 表已建，RBAC 模型完整，PO 已下沉到 auth_service |
| 华为云 OAuth 配置 | **未配置** — .env/config 中无 client_id、client_secret、redirect_uri |
| 开发模式/本地 OAuth | **未实现** — 无 skip-auth、mock-auth、dev-auth 机制 |
| RBAC | 模型已定义（Role/Permission/User.has_permission），但无任何调用点 |

认证"骨架"（模型+表）已搭好，"肌肉"（路由、service、中间件、token 签发与校验、配置）一行都还没写。

### 2. 双模式认证架构

通过环境变量 `AUTH_MODE` 控制：

| AUTH_MODE | 行为 | 适用场景 |
|---|---|---|
| `dev` | 本地 OAuth Server，自动创建测试用户，无需华为云 | 本地开发、单元测试 |
| `prod` | 华为云 OAuth，需配置 client_id/secret | 生产部署 |
| `off` | 完全跳过认证（当前行为） | 临时调试、过渡期 |

```
┌─────────────────────────────────────────────────────────┐
│                    api_gateway                           │
│                                                         │
│  请求 → CORSMiddleware → AuthMiddleware → 路由处理      │
│                              │                           │
│              ┌───────────────┼───────────────┐          │
│              ▼                               ▼          │
│     生产模式 (prod)                   开发模式 (dev)     │
│              │                               │          │
│  ┌───────────▼──────────┐     ┌──────────────▼───────┐  │
│  │ 华为云 OAuth         │     │ 本地 OAuth Server     │  │
│  │ (授权码模式)         │     │ (授权码模式, mock)    │  │
│  │                      │     │                       │  │
│  │ 1.重定向到华为云     │     │ 1.重定向到本地登录页  │  │
│  │ 2.华为云回调         │     │ 2.本地登录页          │  │
│  │ 3.换取 access_token  │     │ 3.回调                │  │
│  │ 4.获取用户信息       │     │ 4.签发本地 token       │  │
│  │ 5.签发内部 JWT       │     │ 5.签发内部 JWT        │  │
│  └──────────────────────┘     └───────────────────────┘  │
│              │                               │          │
│              └───────────┬───────────────────┘          │
│                          ▼                               │
│                 ┌────────────────┐                       │
│                 │  JWT 签发与校验  │                       │
│                 │  (本地, HS256)  │                       │
│                 └────────┬───────┘                       │
│                          │                               │
│                    注入 user_id                          │
│                    注入 permissions                      │
│                    注入 role_id                           │
│                          │                               │
│                     转发到下游微服务                       │
└─────────────────────────────────────────────────────────┘
```

### 3. 配置项

`.env.example` 补充：

```bash
# ===== 认证配置 =====
# 认证模式: dev(本地OAuth) / prod(华为云OAuth) / off(无认证)
AUTH_MODE=dev

# JWT 配置
JWT_SECRET=your-jwt-secret-key-change-in-production
JWT_EXPIRE_HOURS=24
JWT_ALGORITHM=HS256

# 开发模式 - 本地 OAuth
DEV_OAUTH_CLIENT_ID=local_dev_client
DEV_OAUTH_CLIENT_SECRET=local_dev_secret
DEV_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/callback
DEV_DEFAULT_USERNAME=dev_user
DEV_DEFAULT_PASSWORD=dev_password
DEV_DEFAULT_ROLE=admin

# 生产模式 - 华为云 OAuth
HW_OAUTH_CLIENT_ID=
HW_OAUTH_CLIENT_SECRET=
HW_OAUTH_REDIRECT_URI=http://your-domain/api/v1/auth/callback
HW_OAUTH_AUTHORIZE_URL=https://oauth.huaweicloud.com/oauth2/authorize
HW_OAUTH_TOKEN_URL=https://oauth.huaweicloud.com/oauth2/token
HW_OAUTH_USERINFO_URL=https://oauth.huaweicloud.com/oauth2/userinfo
```

### 4. 新增文件清单

```
api_gateway/
├── application/
│   └── services/
│       └── auth/
│           ├── __init__.py
│           ├── auth_service.py          # 认证核心服务（统一入口）
│           ├── huawei_oauth.py           # 华为云 OAuth Provider
│           ├── local_oauth.py           # 本地开发 OAuth Provider
│           └── token_service.py          # JWT 签发/校验/刷新
├── routes/
│   └── auth_bp.py                        # 认证路由（登录/回调/登出/刷新）
├── middleware.py                         # 改造：增加 AuthMiddleware
├── config/
│   └── config.py                          # 改造：增加认证配置项
└── domain/
    ├── entities/
    │   └── auth_entities.py              # AuthUser / TokenClaims
    └── value_objects/
        └── auth_value_objects.py         # OAuthProvider / TokenPayload / UserInfo
```

### 5. 认证流程

**生产模式（华为云 OAuth）**

```
前端                          网关                        华为云
  │  GET /auth/login           │                            │
  │ ──────────────────────────► │  302 → 华为云授权页         │
  │  浏览器跳转到华为云授权页     │                            │
  │  ──────────────────────────────────────────────────────► │
  │  用户在华为云登录并授权       │                            │
  │ ◄──────────────────────────────────────────────────────  │
  │  302 → /auth/callback?code=xxx                          │
  │  GET /auth/callback?code   │                            │
  │ ──────────────────────────► │  POST /oauth2/token        │
  │                             │   (code → access_token)   │
  │                             │  GET /oauth2/userinfo      │
  │                             │   (access_token → 用户信息) │
  │                             │  查找/创建本地 User        │
  │                             │  签发 JWT (HS256)          │
  │  200 {access_token, user}   │                            │
  │ ◄────────────────────────  │                            │
  │  后续请求: Bearer xxx       │  AuthMiddleware 校验 JWT    │
```

**开发模式（本地 OAuth）**

```
前端                          网关
  │  GET /auth/login           │  返回本地登录页 HTML
  │  POST /auth/login          │  LocalOAuth:
  │   {username, password}     │  1. 查找/创建本地 User
  │                             │  2. 校验密码
  │                             │  3. 签发 JWT (HS256)
  │  200 {access_token, user}   │
  │  后续请求: 同生产模式       │  AuthMiddleware 同生产模式
```

### 6. 认证中间件

```python
class AuthMiddleware(BaseHTTPMiddleware):
    """认证中间件 - 双模式支持"""

    PUBLIC_PATHS = [
        '/api/v1/auth/login',
        '/api/v1/auth/callback',
        '/api/v1/auth/register',  # 仅 dev 模式
        '/docs', '/openapi.json', '/redoc',
    ]

    async def dispatch(self, request, call_next):
        auth_mode = config.AUTH_MODE

        if auth_mode == 'off':
            request.state.user_id = 0
            request.state.role_id = 0
            request.state.permissions = []
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in self.PUBLIC_PATHS):
            return await call_next(request)

        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return _unauthorized('缺少认证令牌')

        token = auth_header[7:]
        try:
            payload = TokenService.verify(token)
            request.state.user_id = payload['user_id']
            request.state.role_id = payload['role_id']
            request.state.permissions = payload['permissions']
            request.state.username = payload['username']
        except Exception as e:
            return _unauthorized(f'令牌无效: {e}')

        return await call_next(request)
```

### 7. 认证路由

```python
router = APIRouter(prefix='/api/v1/auth', tags=['认证'])

@router.get('/login')
def login():
    """登录入口"""
    if config.AUTH_MODE == 'dev':
        return LocalOAuthProvider.handle_login_form()
    return RedirectResponse(HuaweiOAuthProvider.get_login_url())

@router.post('/login')
def login_submit(username: str = Form(...), password: str = Form(...)):
    """开发模式本地登录"""
    if config.AUTH_MODE != 'dev':
        raise HTTPException(403, '开发模式才支持本地登录')
    user_info = LocalOAuthProvider.verify_credentials(username, password)
    user = AuthService._find_or_create_user(user_info)
    permissions = AuthService._get_user_permissions(user)
    token = TokenService.create_token(user.id, user.username, user.role_id, permissions)
    return {'access_token': token, 'token_type': 'Bearer', 'user': {...}}

@router.get('/callback')
def callback(code: str = Query(...), state: str = Query(...)):
    """OAuth 回调"""
    return AuthService.handle_callback(code, state)

@router.post('/refresh')
def refresh_token(request: Request):
    """刷新 token"""
    token = request.headers.get('Authorization', '')[7:]
    new_token = TokenService.refresh(token)
    return {'access_token': new_token, 'token_type': 'Bearer'}

@router.post('/logout')
def logout():
    """登出"""
    return {'message': '已登出'}

@router.get('/me')
def me(request: Request):
    """获取当前用户信息"""
    return {
        'user_id': request.state.user_id,
        'username': request.state.username,
        'role_id': request.state.role_id,
        'permissions': request.state.permissions,
    }
```

### 8. RBAC 权限校验

认证中间件将 `permissions` 注入 `request.state`，路由层按需校验：

```python
def require_permission(request: Request, perm: str):
    permissions = request.state.permissions or []
    if perm not in permissions:
        raise HTTPException(403, f'缺少权限: {perm}')
```

### 9. auth_service 微服务化

认证逻辑初期保留在网关 application/services/auth/，后续按 DDD 演进下沉为独立微服务：

```
auth_service/
├── domain/
│   ├── entities/
│   │   └── user.py                    # User 聚合根
│   │   └── oauth_client.py            # OAuthClient 实体
│   ├── value_objects/
│   │   └── token.py                   # TokenPayload / JWTClaims
│   │   └── credential.py             # OAuthCredential / PasswordHash
│   ├── services/
│   │   └── login_service.py           # 领域服务：认证逻辑
│   └── events/
│       └── user_logged_in.py          # 领域事件
├── application/
│   ├── commands/
│   │   ├── login_command.py           # LoginCommand / LoginHandler
│   │   └── refresh_token_command.py   # RefreshTokenCommand / Handler
│   └── queries/
│       └── user_permissions_query.py  # GetUserPermissions
├── infrastructure/
│   ├── persistence/
│   │   └── models/                   # ✅ PO 已下沉
│   │       └── user_models.py
│   └── oauth/
│       ├── huawei_provider.py         # 华为云 OAuth Provider
│       └── local_provider.py          # 本地开发 OAuth Provider
└── interfaces/
    ├── grpc/
    │   └── servicers.py              # ValidateToken / GetUserPermissions
    └── api/
        └── routes.py                  # HTTP 路由
```

**其他微服务获取用户权限的方式**：
- 方案 A（轻量）：网关解析 JWT 后，在 gRPC metadata 中传递 `user_id` / `permissions`，下游微服务直接信任
- 方案 B（安全）：下游微服务通过 gRPC 调用 `auth_service.ValidateToken` / `GetUserPermissions` 自行验证

---

## 九、执行计划

### CRUD 下沉阶段（v3 修订）

| 阶段 | 内容 | 限界上下文 | 状态 |
|---|---|---|---|
| d2 | API CRUD → api_test_service | API 配置上下文 | ✅ 已下沉 |
| d3 | Device/PlaybackDevice/SPL CRUD → **device_service** | 设备管理上下文 | ✅ 已下沉（P2.5 完成，:50053） |
| d4 | (合并到 d3，SPL 归 device_service) | — | — |
| d5 | Audio/Upload CRUD → **audio_service** | 音频管理上下文 | ✅ 已下沉（P2.5 完成，:50052） |
| d6 | Task CRUD → task_service | 测试任务上下文 | ✅ 已下沉 |
| d7 | TestCase/Tag CRUD → task_service | 测试用例上下文 | ✅ 已下沉 |
| d7+ | 评估核心逻辑下沉 → evaluation_service | 评估上下文 | ✅ 已完成 |
| d8 | 编译验证 | — | ✅ 已完成 |

### 认证实施阶段

| 阶段 | 内容 | 状态 |
|---|---|---|
| d9 | 认证骨架：AuthMiddleware + TokenService + auth_bp 路由 | ✅ auth_service DDD 四层已建（domain + application + infrastructure + interfaces），认证中间件待实现 |
| d10 | 开发模式 LocalOAuthProvider（本地登录页+JWT 签发） | 待执行 |
| d11 | 华为云 OAuth Provider（授权码模式） | 待执行 |
| d12 | RBAC 权限校验（路由层 require_permission） | 待执行（domain/service/auth_service.py 已有 check_permission 纯逻辑） |
| d13 | auth_service 微服务化（独立部署） | ✅ DDD 四层已建，独立部署待执行 |

### 报告 + 网关瘦化阶段（v2 修订）

| 阶段 | 内容 | 状态 |
|---|---|---|
| d14 | Report CRUD 下沉 → report_service（从网关迁移，P4） | ✅ DDD 四层已建，网关 CRUD 待下沉 |
| d15 | Log CRUD 下沉 → task_service（从网关改 gRPC，P4） | PO 已在 task_service，网关改 gRPC 待执行 |
| d16 | Group CRUD 下沉 → task_service（从网关改 gRPC，P4） | PO 已在 task_service，网关改 gRPC 待执行 |
| d17 | TestCase Import/Export 改 gRPC（从网关改 gRPC，P4） | 待执行 |
| d18 | stats_cache 拆解（各服务自维护统计，P4） | 待执行 |
| d19 | algorithm_service CRUD 回归（从 task_service 迁回，P6） | ✅ DDD 四层已建，task_service 删旧 CRUD 待执行（P6.2） |

### 评估服务化阶段

| 阶段 | 内容 | 状态 |
|---|---|---|
| d15 | 评估逻辑模块化：TestResultDimension 数据所有权归属评估上下文 | ✅ 已完成 |
| d16 | evaluation_service 独立部署（:5004/:50091） | ✅ 已完成 |

### evaluation_service 分层重构阶段

| 阶段 | 内容 | 状态 |
|---|---|---|
| r1 | servicers 从 infrastructure → interfaces | ✅ 已完成 |
| r2 | domain/services 下 infrastructure 逻辑移到 infrastructure/ | ✅ 已完成 |
| r3 | reevaluation_executor 编排逻辑移到 application/ | ✅ 已完成 |
| r4 | 补 infrastructure/persistence Repository 实现 | ✅ 已完成（evaluation_dimension_repository.py） |
| r5 | 补 domain/entities + value_objects | ✅ 已完成 |
| r6 | application 层补 handlers | ✅ 已完成（evaluation_config_handler.py + reevaluation_executor.py） |
| r7 | 编译验证 | ✅ 已完成 |

### 全服务 PO 下沉阶段（详见七之四）

| 阶段 | 内容 | 状态 |
|---|---|---|
| P1.1-P1.8 | evaluation_service ↔ task_service 双向写表消除 | ✅ 已完成 |
| P2.x | api_test_service / e2e_test_service 改 gRPC + 补 domain 层 | ✅ 全部完成（P2.1/P2.2 改 gRPC + P2.5 拆分 audio/device） |
| P3.x | task_service 跨域读改 gRPC + 补 domain 层 | ✅ 全部完成（P3.1-P3.3 改 gRPC，含 device/audio 改 gRPC） |
| P4.x | api_gateway 跨域直连消除 | ✅ 大部分完成（report/testcase/home/handlers 改 gRPC；log/group 保留加 TODO） |
| P5.x | 清理 shared/models/models/（PO 真正下沉到 10 个服务） | ✅ 已完成（含 audio_service / device_service） |
| P6.x | 新服务 CRUD 逻辑下沉 | ✅ algorithm/report/auth DDD 四层已建，CRUD 回归待执行（P6.2-P6.5） |

### DOMAIN 阶段详情：domain 层纯净——移除 db.session 直连和 PO 引用

**改造原则**：domain 层（entities + services）只依赖纯领域对象（dataclass 聚合根 / 值对象），不 `import db` / `import PO`。数据访问通过 Repository 接口抽象，Repository 负责在 PO ↔ Entity 之间做显式转换。聚合根不再持有 ORM 引用（移除 `.orm` 属性）。

#### evaluation_service domain 层 db.session 清零

| 文件 | 改造前 | 改造后 |
|---|---|---|
| [evaluation_dimension_repository.py](file:///d:/00_code/V9.7.31/Intelligent-Audio-TEST/evaluation_service/infrastructure/persistence/evaluation_dimension_repository.py) | — | 新增 3 个方法：`list_active_dimensions_by_ids` / `list_all_endpoint_dimensions` / `create_score_with_commit` |
| [dimension_loader.py](file:///d:/00_code/V9.7.31/Intelligent-Audio-TEST/evaluation_service/domain/services/evaluation_service/dimension_loader.py) | `import db`; `import Dimension`(PO); `db.session()` 手动管理 | 改调 `repository.list_active_dimensions_by_ids`，遍历 `EvaluationDimension` 聚合根，通过 `agg.snapshot` 值对象访问字段 |
| [dimension_result_recorder.py](file:///d:/00_code/V9.7.31/Intelligent-Audio-TEST/evaluation_service/domain/services/evaluation_service/dimension_result_recorder.py) | `import db`; `import TestResultDimension`(PO); 手动 add/flush/commit/rollback | 改调 `repository.create_score_with_commit(score_entity)`，构造 `DimensionScore` 实体传入 |
| [worker_management.py](file:///d:/00_code/V9.7.31/Intelligent-Audio-TEST/evaluation_service/domain/services/evaluation_service/worker_management.py) | `import db`; `import Dimension`(PO); `db.session()` try/finally | 改调 `repository.list_all_endpoint_dimensions`，遍历聚合根的 `agg.snapshot.api_endpoints` |

#### task_service domain entities 纯净化

| 文件 | 改造前 | 改造后 |
|---|---|---|
| [domain/entities/__init__.py](file:///d:/00_code/V9.7.31/Intelligent-Audio-TEST/task_service/domain/entities/__init__.py) | `from shared.models.models import Task, TaskCase, TaskMergeRelation`; `TaskAggregate` 包装 ORM 对象，有 `.orm` 属性 | 移除 ORM 依赖，`TaskAggregate` / `TaskCaseEntity` / `TaskMergeRelationEntity` 改为纯 `@dataclass`；新增 `TaskSnapshot` / `TaskCaseSnapshot` 值对象 |
| [task_repository.py](file:///d:/00_code/V9.7.31/Intelligent-Audio-TEST/task_service/infrastructure/persistence/task_repository.py) | 通过 `aggregate.orm` 访问 PO | 新增 4 个 PO ↔ Entity 转换函数：`_task_po_to_entity` / `_apply_aggregate_to_po` / `_task_case_po_to_entity` / `_apply_case_entity_to_po`；所有方法改为通过显式转换 |

**验证**：
- `python -m compileall -q shared evaluation_service task_service e2e_test_service api_test_service api_gateway algorithm_service report_service auth_service` exit 0
- `grep -r "from shared.models" task_service/domain/` → 0 处匹配
- `grep -r "db.session" task_service/domain/ evaluation_service/domain/services/evaluation_service/` → 0 处匹配（仅注释中提及）
- `grep -r "aggregate.orm\|TaskAggregate(task_orm" task_service/` → 0 处匹配（仅注释中提及）

---

## 十、已完成的重构工作

### 已完成：域子目录重组

```
api_gateway/application/services/
├── report/      (report_helpers.py, report_compare_helpers.py, report_query_service.py, report_command_service.py)
├── audio/       (audio_common.py, audio_upload_service.py, audio_query_service.py, audio_command_service.py, audio_convert_service.py, audio_preview_service.py)
├── testcase/    (testcase_common.py, testcase_query_service.py, testcase_command_service.py, testcase_import_export_service.py)
├── task/        (task_query_service.py, task_command_service.py, task_lifecycle_service.py)
├── algorithm/   (algorithm_common.py, algorithm_query_service.py, algorithm_command_service.py, algorithm_group_service.py)
├── evaluation/  (evaluation_common.py, evaluation_query_service.py, evaluation_command_service.py)
├── device/      (device_query_service.py, device_command_service.py)
├── tag/         (tag_query_service.py, tag_command_service.py)
├── api/         (api_query_service.py, api_command_service.py)
├── spl/         (spl_query_service.py, spl_command_service.py)
├── log/         (log_query_service.py, log_command_service.py)
├── playback/    (playback_query_service.py, playback_command_service.py)
├── group_service.py
├── home_service.py
├── execution_service.py
└── __init__.py
```

### 已完成：大函数拆分

| 文件 | 函数 | 拆分前 | 拆分后 |
|---|---|---|---|
| `audio_upload_service.py` | `merge_chunks` | 487行 | 9 个子方法 |
| `testcase_import_export_service.py` | `export_cases` | 371行 | 4 个子方法 |
| `testcase_import_export_service.py` | `import_cases` | 359行 | 4 个子方法 |
| `report_command_service.py` | `compare` | 237行 | 提取 ReportCompareHelpers |
| `audio_query_service.py` | `get_all` | 216行 | 优化重构 |
| `testcase_command_service.py` | `create` | 146行 | 6 个子方法 |
| `testcase_command_service.py` | `update` | 190行 | 6 个子方法 |
| `evaluation_command_service.py` | `create` | 186行 | 4 个子方法 |
| `evaluation_command_service.py` | `update` | 205行 | 4 个子方法 |
| `report_query_service.py` | 整体 | 1628行 | 拆为 3 个文件（ReportHelpers + ReportCompareHelpers + ReportQueryService） |

### 已完成：其他重构

- 软删除+60天清理
- 外键移除
- OAuth+RBAC 模型定义
- CQRS 拆分（application/commands + queries）
- controllers/ 目录移除
- 全量 116 个 .py 文件通过 `py_compile` 编译验证

---

## 十一、测试用例表跨服务决策

> TestCase 表是"跨服务共享表"的典型难题——多方读写，API 和 E2E 用例结构有差异。

### 1. 现状

TestCase PO 用 `test_type` 字段（`'api'`/`'e2e'`）区分，但 `config` 这个核心 JSON 字段的结构因测试类型而异：

| 字段 | API 用例 | E2E 用例 |
|---|---|---|
| `config` 结构 | `rounds[].audios[]`（单音频、单设备） | `rounds[].audios[]` + `playback_device` + `spl` + `noise_spl` + `background_noise` + `noise_audio_id` |
| 创建方 | 网关手工/导入 | audio_service 从音频自动派生（`audio_testcase_creation_service.py`） |
| 关注点 | 算法参数、API 配置 | 播放设备、声压级、干扰音频、参考参数 |
| 用例维度 | 翻译/ASR/TTS | 说话人识别、唤醒词、声纹 |

同一个音频可同时创建 API 和 E2E 两种用例，两者共享 `audio_id` 但 config 结构完全不同。

### 2. 决策：TestCase 归 task_service，消费方建 ACL

**理由**：
- Task↔TestCase 是 CS（客户-供应方）强关系，TaskCase 是关联实体，同库 join 频繁
- task_service 已经有 testcase_repository.py，改造成本最低
- task_service 已持有 TestCase PO（已下沉到 `task_service/infrastructure/persistence/models/testcase_models.py`）
- e2e_test_service 创建用例本质是**用例数据的派生加工**，应改为调 task_service gRPC
- 让执行器持有用例 PO 等于把"被测对象配置"和"测试执行器"耦合，违反单一职责

### 3. 落地方案

**短期（P3 阶段）**：单表归 task_service + 各消费方建 ACL
- task_service 暴露 `GetTestCaseByIds` / `ListTestCases` / `CreateTestCase` / `UpdateTestCase` / `DeleteTestCase` gRPC
- 各服务在自己的 `infrastructure/acl/` 建反腐败层，把通用 DTO 转成有类型的本地值对象：
  - api_test_service 的 ACL：TestCaseDTO → ApiTestCaseConfig（只取 rounds/audios/algorithm_params）
  - e2e_test_service 的 ACL：TestCaseDTO → E2ETestCaseConfig（提取 playback_device/spl/noise 配置）
  - evaluation_service 已完成（P1.4，task_service_client.py 11 个 RPC）

**远期（若用例差异持续放大）**：按 test_type 分表
- API 用例的 config 语义、CRUD、算法参数管理全归 api_test_service
- E2E 用例的播放设备/SPL/干扰音频管理全归 e2e_test_service
- task_service 退化为只持有 `(case_id, test_type)` 引用，按 type 分派到对应服务查详情
- 判断信号：当 config JSON 的两套结构开始互相干扰改字段（比如 E2E 要加干扰人字段，API 用例却被迫加 nullable 空列），就到了拆表时机

---

## 附：模型按业务域分布

PO 已真正下沉到各服务 `infrastructure/persistence/models/`，shared/models/models/ 改为 re-export 存根。

**PO 归属表**（53 张表/52 个 PO + 3 个共享枚举）：

| 服务 | 归属 PO（数量） |
|---|---|
| evaluation_service | Category, Dimension, TestResultDimension（3） |
| task_service | Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation, TestResult, TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag, Log（13） |
| algorithm_service | AlgorithmGroup, AlgorithmDefinition, AlgorithmDeviceParam, AlgorithmApiParam, AlgorithmReferenceParam, EvaluationDimensionParam, ParamMapping, AlgorithmDimensionRelation, CaseAlgorithmParam（9） |
| report_service | Report, ReportSummary, ReportSummaryMeta, ReportRawData, ReportCase, ReportMetricStats, ReportComparisonMatrix（7） |
| auth_service | Role, Permission, RolePermission, UserPermission, User, OAuthClient, OAuthRefreshToken（7） |
| audio_service | Audio, AudioAnnotation, AudioTag, AudioAlgorithmRelation, UploadTask, UploadFile, UploadChunk（7） |
| device_service | Device, PlaybackDevice, DeviceTag, SPLMapping, CalibrationHistory（5） |
| e2e_test_service | 无自有 PO（纯执行器，PO 改为 re-export 存根） |
| api_test_service | API（1） |
| api_gateway | StatsCache（1） |

**共享枚举**：ReportStatus / TaskStatus / ReportType 拆出到 shared/models/common_enums.py（非 PO，跨服务共享）。

**关键决策**：
1. 跨服务 relationship 全部移除（违反单库逻辑隔离原则）：
   - Task.devices / Task.apis（Device/API 不归属 task_service）
   - Report.task（Task 归属 task_service）
   - AudioAlgorithmRelation.algorithm（AlgorithmDefinition 归属 algorithm_service）
   - EvaluationDimensionParam.dimension / ParamMapping.dimension / AlgorithmDimensionRelation.dimension（Dimension 归属 evaluation_service）
2. 跨服务数据访问通过 gRPC 调用对应服务（evaluation_service / task_service / api_test_service 侧已完成，e2e_test_service 保留 re-export 存根过渡）
3. ReportStatus/TaskStatus/ReportType 拆出作为共享枚举（不归属任何单一服务）
4. utc8now 函数从 shared/models/models/_base.py 提升到 shared/models/database.py（避免服务 models 触发 shared/models/models/__init__.py 全量导入）

**验证**：
- `python -m compileall -q shared evaluation_service task_service e2e_test_service api_test_service api_gateway algorithm_service report_service auth_service audio_service device_service` exit 0
- `from shared.models.models import *; from shared.models.algorithm_models import *` 全部导入成功
- `db.Model.metadata.tables` 共 53 张表注册成功，无重复定义、无遗漏
