# 报告 Benchmark 排行功能设计文档

## 1. 文档说明

### 1.1 目标

测试报告只能回答"我们这次跑得好不好"，无法回答"我们在业界处于什么水平"。本功能为系统增加 **Benchmark 排行** 能力：将开源模型、闭源模型、已上线 APP（如豆包、ChatGPT 等）在我们的平台上用公开测试集和内部测试集完成实测（API 测试 / E2E 测试），以**正式发布任务**的实测结果为主要数据来源，同时支持**人工导入外部基线数据**（业界公开 Benchmark 榜单数据），将两者合并生成横向 Benchmark 排行与 Benchmark 报告。

> **核心原则**：排行数据来源双轨制——
> 1. **平台实测**（主）：开源模型 / 闭源模型 / 已上线 APP 在本平台执行测试，只有正式发布的任务（`published_tasks`）才能上 Benchmark。
> 2. **外部基线导入**（辅）：人工导入业界公开 Benchmark 榜单数据（如 Pipecat STT Benchmark、Open ASR Leaderboard、Full-Duplex-Bench 等），作为平台尚未实测的模型的参照补充。
>
> 排行结果中每条数据标注来源（`platform_test` / `external_import`），用户可筛选仅看实测或含外部基线。

### 1.2 文档关系

| 文档 | 职责 |
| --- | --- |
| [报告管理功能设计文档](报告管理功能设计文档.md) | 报告生成、存储、对比、导出等总设计 |
| [报告Benchmark排行功能设计文档](报告Benchmark排行功能设计文档.md) | 本功能：实测排行计算、Benchmark 报告发布 |
| [评估系统功能设计文档](../04_评估/评估系统功能设计文档.md) | 评估维度与指标定义（WER/CER/BLEU/接话率/打断等） |
| [任务发布功能设计文档](../02_任务管理/任务发布功能设计文档.md) | 正式任务与版本快照机制——Benchmark 入口 |
| [任务管理功能设计文档](../02_任务管理/任务管理功能设计文档.md) | 任务创建、执行、测试集选择 |
| [端到端测试功能设计文档](../01_测试执行/端到端测试功能设计文档.md) | E2E 执行模式 |
| [Realtime API Adapter 方案](../01_测试执行/Realtime_API_Adapter方案与UseCase文档.md) | API / Realtime 执行模式 |
| [多厂商API适配完整方案](../06_设备管理/多厂商API适配完整方案.md) | 被测 API 配置（厂商、协议、endpoint） |
| [用例管理功能设计文档](../07_用例管理/用例管理功能设计文档.md) | 测试用例与测试集管理 |
| [report_metrics_format_change](report_metrics_format_change.md) | 报告用例 metrics 数组格式 `[{id, metric, value}]` |

## 2. 业务模型

### 2.1 被测主体（Subject）

被测主体是参与 Benchmark 排行的模型/APP/API，分为三类：

| 类型 | 说明 | device_type | 示例 |
| --- | --- | --- | --- |
| 闭源模型 / 商业 API | 厂商提供的云端 API | `http_api` / `websocket_api` | OpenAI GPT-4o Realtime、Gemini Live、Azure、火山引擎、阿里云百炼、Deepgram Nova |
| 开源模型 | 自部署的开源权重模型 | `http_api` / `websocket_api` / `physical` | Whisper、NVIDIA Canary、Moshi、Sesame CSM、Qwen-Audio、Voxtral |
| 已上线 APP | 安装在真机上的应用 | `physical` | 豆包、ChatGPT APP、小翼音箱、小爱同学 |

被测主体通过现有设备管理（`physical`）或多厂商 API 适配（`http_api` / `websocket_api`）注册，无需新增实体表——复用现有 `devices` 和 `apis` 表，`device_type` 决定执行方式。

### 2.2 测试集（Test Suite）

测试集是一组测试用例的集合，分两类：

| 来源 | 说明 | 示例 |
| --- | --- | --- |
| 公开测试集 | 业界公开的标准测试数据集 | LibriSpeech（ASR）、Common Voice、Full-Duplex-Bench（全双工）、WMT（翻译） |
| 内部测试集 | 平台自建的测试用例组 | 普通话多轮对话集、噪声打断场景集、干扰人拒识集 |

测试集对应现有 `test_case_groups`（用例分组）+ 标签系统，不新增实体表。测试集可更新（新增用例、调整维度），更新后通过发布新版本正式任务来触发重测。

### 2.3 Benchmark 数据来源（双轨制）

排行数据来自两个来源，合并后统一参与排名：

#### 来源一：平台实测（主）

**只有正式发布的任务（`published_tasks`）才能进入 Benchmark 排行。**

```
日常任务（Task）执行完成 → 评估完成 → 报告生成 → 发布为正式任务 → 标记参与 Benchmark → 进入排行
```

正式任务发布时保存完整配置快照（`snapshot_config`），包含用例、设备/API、算法配置、评估维度。这保证了排行可比性：同一正式任务版本用同样的测试集、同样的评估维度测出的结果才有资格横向对比。

#### 来源二：外部基线导入（辅）

人工导入业界公开 Benchmark 榜单数据，作为平台尚未实测的模型的参照补充。

```
录入/批量导入外部基线数据
  → 校验（模型、指标、单位、方向、场景标签、数据来源）
  → 发布基线版本（不可变快照，同任务发布的版本快照思路）
  → 参与排行
```

外部基线要求可追溯：每条数据必须标注来源（如 Pipecat STT Benchmark）、采样规模（sample_size）、数据日期。导入校验失败时按行返回错误，合法行正常入库。

> **双轨对比规则**：同一个模型如果既有平台实测又有外部基线数据，**两者同时展示、可对比**，不互相覆盖。排行中该模型展示两个值（实测值 + 导入值），并计算差异（`delta = 实测值 - 导入值`），用户可直观看到平台实测结果与业界公开数据的偏差。排名默认以平台实测值参与排序；无实测值时以导入值参与排序。

### 2.4 排行结果（Ranking）

对参与 Benchmark 的每个被测主体，按指标在全部参与排行的数据中计算：

- `rank`：名次（并列取同排名）。
- `total`：参与对比的模型数。
- `percentile`：百分位（越低越靠前）。
- `score100`：归一化 0-100 分（同时兼容"越低越好"与"越高越好"）。
- `gapBest` / `gapMedian`：与头部 / 中位数的差距。
- `deltaExternal`：平台实测值与外部基线值的差异（仅当两者并存时有值）。

## 3. 功能范围

### 3.1 第一阶段

- 正式任务发布时标记是否参与 Benchmark（`published_tasks.snapshot_config` 增加 `benchmark: true`）。
- 外部基线数据导入：批量导入业界公开 Benchmark 榜单数据，版本快照管理（同任务发布不可变版本思路）。
- Benchmark 排行计算：合并平台实测 + 外部基线数据，按指标横向排名（实测优先，外部基线填充空位）。
- 指标映射配置：系统评估维度 → Benchmark 排行指标（含单位、方向、场景标签），配置化。
- 报告详情页嵌入「Benchmark 排行」区块（支持按数据来源筛选）。
- 独立 Benchmark 排行页（排行表 + 对比图 + 被测主体筛选 + 来源筛选）。
- Benchmark 报告发布：将排行结果生成为独立的 Benchmark 报告（复用现有报告生成机制）。
- 新模型 / 新测试集导入后，创建正式任务并发布，自动更新排行。
- 评测维度和测试集可更新（通过发布新版本正式任务触发重测）。
- 记录排行计算、基线导入、Benchmark 报告发布的审计操作。

### 3.2 暂不包含

- 定时自动执行全量 Benchmark 重测（一期手动触发或发布时触发）。
- 多级审批流与租户隔离。
- 跨测试集的加权综合评分（一期按单测试集单指标排行）。

## 4. 核心流程

### 4.1 新模型 / 新测试集导入 → 执行测试 → 发布 → 更新排行

```text
注册被测主体（设备管理 / API 适配）
  → 创建/导入测试集（用例分组 + 标签）
  → 创建任务（关联用例 + 被测设备/API）
  → 执行测试（E2E / API / Realtime，按 device_type 路由）
  → 评估完成（xiaoyi_metrics 计算维度指标）
  → 报告生成
  → 发布为正式任务（snapshot_config 标记 benchmark: true）
  → 触发 Benchmark 排行更新
```

### 4.2 外部基线导入

```text
录入/批量导入外部基线数据（业界公开 Benchmark 榜单）
  → 校验（模型名、指标、单位、方向、场景标签、数据来源 URL、采样规模）
  → 逐行校验，合法行入库，非法行返回错误明细
  → 发布基线版本（不可变快照，is_current = true）
  → 参与排行合并
```

### 4.3 排行计算

```text
数据源 A：查询所有 published_tasks（benchmark = true, status = published）
  → 取每个正式任务的最新执行报告
  → 读取报告指标（report_cases.metrics / dimension_values）
  → 来源标记 source = platform_test

数据源 B：查询当前生效的外部基线版本（is_current = true）
  → 来源标记 source = external_import

合并 A + B：同模型两者并存，不互相覆盖
  → 按指标映射配置解析（维度 → 排行指标 + 单位 + 方向）
  → 按测试集 + 场景标签分组
  → 排名默认以实测值排序；无实测值时以导入值排序
  → 计算每个被测主体在每个指标上的 rank / percentile / score100 / gap
  → 同模型两者并存时计算 delta_external = 实测值 - 导入值
  → 存储排行结果（benchmark_rankings，同模型可有两条：source 不同）
  → 更新 Benchmark 排行页与报告内嵌排行区块
```

### 4.4 评测维度 / 测试集更新

```text
更新评测维度（用例的 evaluation.dimensions）
  或 更新测试集（新增/修改用例）
  → 创建新日常任务（用更新后的配置）
  → 执行测试 → 评估 → 报告
  → 发布为新版本正式任务（v2, v3, ...）
  → 触发排行重算（引用新版本快照，旧版本排行保留不漂移）
```

### 4.5 Benchmark 报告发布

```text
触发 Benchmark 报告生成（手动或发布时自动）
  → 收集当前所有参与排行的正式任务排行结果
  → 生成 Benchmark 报告（复用报告生成器，report_type = 'benchmark'）
  → 存储报告（test_reports + 扩展表）
  → 前端可查看 / 导出
```

### 4.6 排行嵌入报告

报告详情页展示「Benchmark 排行」区块（异步计算 + 进度轮询，同现有报告生成机制）；报告导出 HTML 时包含排行区块。

## 5. 排行规则

### 5.1 指标映射（配置化，拒绝魔法字符串）

| 系统维度（dimension） | 排行指标 | 单位 | 方向 | 场景标签示例 |
| --- | --- | --- | --- | --- |
| `WER` / `CER` | Word Error Rate | % | 越低越好 | 普通话通用、噪声 |
| `takeover_latency`（接管时延） | TTLW 末字延迟 / TTFS | ms | 越低越好 | 通用 |
| `tor`（接话率） | 对话接话率 | % | 越高越好 | 通用 |
| `interruption_success_rate`（打断成功率） | 全双工打断成功率 | % | 越高越好 | 打断场景 |
| `avg_stop_latency_s` / `avg_recovery_latency_s` | 打断/恢复时延 | ms | 越低越好 | 打断场景 |
| `interruption_coherence`（连贯性 0-5） | 打断连贯性 | 分 | 越高越好 | 打断场景 |
| `interruption_relevance`（相关性 0-5） | 打断相关性 | 分 | 越高越好 | 打断场景 |
| `false_takeover`（误接管率） | 误接管率 | % | 越低越好 | 通用 |
| `BLEU` / `COMET`（翻译质量） | BLEU / COMET | 分 | 越高越好 | 翻译 |
| `MOS`（合成自然度） | MOS | 分 | 越高越好 | TTS |

> 映射关系存储于 `benchmark_metric_mappings` 表，前端与 Domain 使用 camelCase；snake_case 只允许出现在后端数据库和 DTO 转换层。

### 5.2 场景匹配

- 排行按 **测试集 + 场景标签** 分组：同一测试集、同一场景下的被测主体才互相排名。
- 测试集取自正式任务快照中的 `caseIds` 聚合所属 `test_case_groups`。
- 场景标签取自已执行用例的标签聚合；无匹配场景时使用 `通用` 场景。
- 每个被测主体在每个指标上最多一条排行记录；无数据的指标不参与排行。

### 5.3 排行算法

1. 方向判定：`direction = lowerIsBetter | higherIsBetter`。
2. 名次：`rank = 1 + count(其他被测主体优于本主体) `，并列共享名次。
3. 百分位：`percentile = rank / total * 100`（越低越靠前）。
4. 归一化分：将参与排行的全部被测主体极值线性映射到 0-100，方向取反后得到 `score100`；只有 1 个被测主体时不归一化（`score100` 置空，只给 rank）。
5. 差距：`gapBest = 本主体值 - 排行最佳`，`gapMedian = 本主体值 - 排行中位数`（符号随方向语义化展示）。

### 5.4 版本与不可变性

- 正式任务版本不可变（同现有任务发布机制），排行固定引用计算时的正式任务版本号。
- 测试集或评测维度更新后，需发布新版本正式任务，触发排行重算。
- 旧版本排行结果保留，不随新版本发布漂移（历史可追溯）。
- 支持"仅用当前版本"或"指定版本"重算排行。

## 6. 数据模型

### 6.1 现有表复用（不新增实体）

| 现有表 | 复用方式 |
| --- | --- |
| `published_tasks` | 增加 `benchmark` 标记到 `snapshot_config`；正式任务即 Benchmark 入口（平台实测来源） |
| `test_reports` | 增加 `report_type = 'benchmark'` 枚举值，Benchmark 报告复用报告 7 表结构 |
| `devices` / `apis` | 被测主体注册，`device_type` 决定执行方式 |
| `test_case_groups` | 测试集（用例分组），不新增实体 |
| `dimensions` | 评测维度定义，可更新 |

### 6.2 `published_tasks.snapshot_config` 扩展

在现有快照结构中增加 `benchmark` 字段：

```json
{
  "caseIds": ["case-1", "case-2"],
  "deviceIds": [1, 2],
  "apiIds": [3],
  "config": {},
  "algorithmType": "voice_llm",
  "algorithmParams": {},
  "tags": ["回归", "正式"],
  "sourceTaskId": 123,
  "benchmark": true,
  "benchmarkSuite": "full-duplex-v1",
  "benchmarkCategory": "voice_llm"
}
```

| 新增字段 | 类型 | 说明 |
| --- | --- | --- |
| `benchmark` | boolean | 是否参与 Benchmark 排行 |
| `benchmarkSuite` | string | 测试集标识（用于排行分组） |
| `benchmarkCategory` | string | 被测类别：`asr` / `voice_llm` / `tts` / `translation` |

### 6.3 `benchmark_rankings`（排行结果）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | bigint | 排行 ID |
| `source` | varchar | 数据来源：`platform_test` / `external_import` |
| `published_task_id` | bigint | 外键 → published_tasks.id（source=platform_test 时有值） |
| `published_task_version` | int | 引用的正式任务版本号（source=platform_test 时有值） |
| `report_id` | bigint | 外键 → test_reports.id（来源报告，source=platform_test 时有值） |
| `baseline_id` | bigint | 外键 → benchmark_baselines.id（source=external_import 时有值） |
| `subject_name` | varchar | 被测对象名（模型/APP/API 名称） |
| `subject_type` | varchar | `open_source` / `closed_source` / `app` |
| `device_type` | varchar | `physical` / `http_api` / `websocket_api` |
| `benchmark_suite` | varchar | 测试集标识 |
| `category` | varchar | `asr` / `voice_llm` / `tts` / `translation` |
| `metric_code` | varchar | 排行指标代码 |
| `metric_name` | varchar | 指标显示名 |
| `metric_value` | double | 被测指标值 |
| `unit` | varchar | 单位 |
| `direction` | varchar | `lower_is_better` / `higher_is_better` |
| `rank` | int | 名次 |
| `total` | int | 参与对比的模型数 |
| `percentile` | double | 百分位（越低越靠前） |
| `score100` | double | 归一化分 0-100，可空 |
| `gap_best` | double | 与排行最佳差距 |
| `gap_median` | double | 与排行中位数差距 |
| `delta_external` | double | 实测值与外部基线值的差异（仅当同模型两者并存时有值） |
| `scenario_key` | varchar | 排行所用场景 |
| `computed_at` | datetime | 计算时间 |

### 6.4 `benchmark_metric_mappings`（指标映射配置）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | bigint | 映射 ID |
| `dimension_name` | varchar | 系统维度名（如 WER、takeover_latency） |
| `metric_code` | varchar | 排行指标代码 |
| `unit` | varchar | 单位 |
| `direction` | varchar | 方向 |
| `scenario_tags` | json | 默认场景标签 |
| `active` | boolean | 是否启用 |

### 6.5 `benchmark_sources`（外部基线数据源）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | bigint | 数据源 ID |
| `name` | varchar | 数据源名称（如 Pipecat STT Benchmark） |
| `provider` | varchar | 发布方 |
| `source_type` | varchar | `official` / `third_party` / `self_test` / `manual` |
| `url` | varchar | 原始链接 |
| `version` | varchar | 数据源版本 |
| `description` | text | 说明 |
| `created_by` | varchar | 创建人 |
| `created_at` | datetime | 创建时间 |

### 6.6 `benchmark_baselines`（外部基线条目）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | bigint | 基线 ID |
| `source_id` | bigint | 外键 → benchmark_sources.id |
| `category` | varchar | `asr` / `voice_llm` / `tts` / `translation` |
| `model_name` | varchar | 模型名（如 Deepgram Nova-4） |
| `vendor` | varchar | 厂商（如 Deepgram） |
| `metric_code` | varchar | 排行指标代码（如 WER、TTLW） |
| `metric_name` | varchar | 指标显示名 |
| `value` | double | 指标值 |
| `unit` | varchar | 单位（% / ms / 分） |
| `direction` | varchar | `lower_is_better` / `higher_is_better` |
| `scenario_tags` | json | 场景标签（普通话通用 / 噪声 / 多轮 / 打断 / 翻译 / TTS） |
| `sample_size` | int | 采样规模（可空） |
| `metric_date` | date | 数据产生日期 |
| `version` | int | 基线版本号，从 1 开始 |
| `is_current` | boolean | 是否当前版本 |
| `created_at` | datetime | 创建时间 |

### 6.7 `benchmark_reports`（Benchmark 报告发布记录）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | bigint | 发布记录 ID |
| `report_id` | bigint | 外键 → test_reports.id |
| `suite` | varchar | 测试集标识 |
| `category` | varchar | 被测类别 |
| `published_task_count` | int | 参与排行的正式任务数 |
| `subject_count` | int | 参与排行的被测主体数 |
| `version` | int | Benchmark 报告版本号 |
| `published_by` | varchar | 发布人 |
| `published_at` | datetime | 发布时间 |
| `created_at` | datetime | 创建时间 |

## 7. 接口设计

### 7.1 Benchmark 排行计算

接口前缀：`/api/v1/benchmarks`。

```http
POST /api/v1/benchmarks/ranking/compute          # 全量重算排行（异步 + 进度轮询）
GET  /api/v1/benchmarks/ranking?suite=full-duplex-v1&category=voice_llm&metricCode=WER
GET  /api/v1/benchmarks/ranking?publishedTaskId=123
GET  /api/v1/benchmarks/ranking?source=platform_test   # 仅看平台实测
GET  /api/v1/benchmarks/ranking?source=external_import  # 仅看外部基线
```

排行接口幂等：同版本同测试集重复计算返回已存在结果，不产生重复记录。

### 7.2 外部基线管理

```http
GET  /api/v1/benchmarks/sources?page=1&perPage=10&sourceType=official
POST /api/v1/benchmarks/sources                    # 创建数据源
GET  /api/v1/benchmarks/baselines?category=asr&metricCode=WER&isCurrent=true
POST /api/v1/benchmarks/baselines                  # 批量导入基线条目
POST /api/v1/benchmarks/baselines/version          # 发布新基线版本（不可变快照）
```

导入校验失败时按行返回错误（`{row, field, message}`），不阻断合法行。

### 7.3 Benchmark 报告发布

```http
POST /api/v1/benchmarks/reports                   # 生成并发布 Benchmark 报告
GET  /api/v1/benchmarks/reports                   # Benchmark 报告列表
GET  /api/v1/benchmarks/reports/{reportId}        # Benchmark 报告详情
```

### 7.4 指标映射管理

```http
GET /api/v1/benchmarks/metric-mappings
PUT /api/v1/benchmarks/metric-mappings/{id}
```

### 7.5 正式任务标记 Benchmark

在现有 `POST /published-tasks` 发布接口中，请求体增加可选字段：

```json
{
  "sourceTaskId": 123,
  "name": "全双工对话 Benchmark - 2026Q3",
  "description": "Full-Duplex-Bench 测试集",
  "publishReason": "新模型 Moshi 上线，更新排行",
  "benchmark": true,
  "benchmarkSuite": "full-duplex-v1",
  "benchmarkCategory": "voice_llm"
}
```

发布成功后，如果 `benchmark = true`，后端自动触发排行重算。

### 7.6 排行查询

```http
GET /api/v1/benchmarks/ranking?suite=full-duplex-v1&category=voice_llm
GET /api/v1/benchmarks/ranking?suite=librispeech&category=asr&metricCode=WER
GET /api/v1/benchmarks/ranking/subjects?suite=full-duplex-v1  # 查看参与排行的被测主体列表
```

## 8. 前端设计

### 8.1 报告详情页

在报告详情页新增「Benchmark 排行」区块（卡片式）：

- 排行表：名次、被测主体、主体类型（开源/闭源/APP）、数据来源标记（实测/导入）、指标值、与头部差距、百分位条、实测与导入差异列（`delta`，有值时高亮）。
- 参考线图表：ECharts 横向柱状图，展示全部被测主体同指标对比，标注中位数与最佳参考线，实测与导入数据用不同颜色区分；同模型两者并存时展示双柱对比。
- 版本标注：展示所引用正式任务版本与测试集（实测数据）或基线版本与数据源链接（导入数据）。
- 来源筛选：可切换"仅实测"/"仅导入"/"全部"/"仅看有差异的"。
- 差异对比：同模型既有实测又有导入值时，在排行表中并列展示两个值，并计算 delta 差异，用颜色标注（正值/负值含义随指标方向不同）。

### 8.2 独立 Benchmark 排行页

建议路由：

```text
/benchmarks                         # 排行概览（测试集、被测类别、参与主体数、来源分布）
/benchmarks/ranking                 # 排行详情（按测试集 + 类别 + 指标 + 来源筛选）
/benchmarks/ranking/:suite/:category  # 特定测试集 + 类别的排行
/benchmarks/baselines               # 外部基线数据管理（导入、录入、发布版本）
/benchmarks/reports                 # Benchmark 报告列表
/benchmarks/reports/:reportId       # Benchmark 报告详情
```

### 8.3 正式任务发布弹窗

在现有发布弹窗中增加 Benchmark 选项：

- 勾选「参与 Benchmark 排行」
- 选择测试集（`benchmarkSuite`）
- 选择被测类别（`benchmarkCategory`：ASR / Voice LLM / TTS / 翻译）

### 8.4 分层建议

```text
frontend/src/domain/model/benchmark.ts                    # BenchmarkRanking / BenchmarkReport / BenchmarkBaseline Domain
frontend/src/domain/enums.ts                               # BenchmarkCategory / SubjectType / Direction / RankingSource 枚举
frontend/src/composables/useBenchmarkRanking.ts           # 编排排行查询用例（Ports）
frontend/src/composables/useBenchmarkReports.ts            # 编排 Benchmark 报告用例
frontend/src/composables/useBenchmarkBaselines.ts          # 编排外部基线导入用例
frontend/src/store/benchmarkStore.ts                       # 排行、报告、基线状态
frontend/src/views/Benchmarks.vue                          # 排行概览
frontend/src/views/BenchmarkRanking.vue                    # 排行详情
frontend/src/views/BenchmarkBaselines.vue                 # 外部基线数据管理
frontend/src/views/BenchmarkReports.vue                    # Benchmark 报告列表
frontend/src/components/benchmark/BenchmarkRankingCard.vue  # 报告内嵌排行卡片
frontend/src/components/benchmark/BenchmarkRankingChart.vue # 横向对比图
frontend/src/components/benchmark/BenchmarkToggle.vue       # 发布弹窗中的 Benchmark 选项
frontend/src/components/benchmark/BaselineImportModal.vue   # 外部基线批量导入弹窗
frontend/src/infrastructure/api/benchmarkApi.ts
```

## 9. 权限与审计

预留权限编码：

- `benchmark.ranking.read` — 查看排行
- `benchmark.ranking.compute` — 触发排行计算
- `benchmark.baseline.read` — 查看外部基线数据
- `benchmark.baseline.write` — 导入/录入外部基线
- `benchmark.baseline.publish` — 发布基线版本
- `benchmark.report.read` — 查看 Benchmark 报告
- `benchmark.report.publish` — 发布 Benchmark 报告
- `benchmark.mapping.manage` — 管理指标映射

审计事件：

- `BENCHMARK_RANKING_COMPUTED` — 排行计算完成
- `BENCHMARK_BASELINE_IMPORTED` — 外部基线导入
- `BENCHMARK_BASELINE_VERSION_PUBLISHED` — 外部基线版本发布
- `BENCHMARK_REPORT_PUBLISHED` — Benchmark 报告发布
- `BENCHMARK_MAPPING_UPDATED` — 指标映射配置更新

审计记录至少包含操作人、操作时间、测试集、被测类别、参与主体数和操作结果。

## 10. 异常处理

| 场景 | 处理方式 |
| --- | --- |
| 正式任务未标记 benchmark | 不参与排行，不报错 |
| 正式任务无执行报告 | 跳过该主体，排行中标记 `no_report` |
| 外部基线导入部分非法 | 返回逐行错误，合法行正常入库 |
| 外部基线版本被引用后修改 | 禁止原地修改，只能发布新版本 |
| 同一模型既有实测又有外部基线 | 两者并存展示，不互相覆盖；排名默认以实测值排序，无实测值时以导入值排序；计算 delta 差异 |
| 指标无映射配置 | 排行中该指标跳过，结果中标记 `no_mapping` |
| 同一测试集同一主体多个版本 | 取最新版本参与排行，旧版本保留历史 |
| 排行计算失败 | 保留上次排行结果可用，显示失败原因，支持重算 |
| 重复触发排行计算 | 幂等返回已存在结果，不重复入库 |
| 单位/方向不一致 | 映射配置校验拦截，不允许入库 |
| 被测主体已下线（设备/API 不可用） | 历史排行结果保留，标记 `subject_offline`，不参与后续重算 |

## 11. 迁移与兼容

1. 新增 `benchmark_rankings`、`benchmark_metric_mappings`、`benchmark_sources`、`benchmark_baselines`、`benchmark_reports` 五表及索引。
2. `published_tasks.snapshot_config` 增加 `benchmark` / `benchmarkSuite` / `benchmarkCategory` 字段（JSON 扩展，无 DDL 变更）。
3. `test_reports.report_type` 枚举增加 `benchmark` 值。
4. 报告主表不加字段，排行通过 `benchmark_rankings.report_id` 关联（按需加载）。
5. 部署接口与前端区块，旧报告无排行数据时区块隐藏。
6. 现有报告生成、对比、导出流程不受影响；排行计算为独立异步任务。

兼容要求：

- 报告接口既有字段保持不变。
- 新排行接口独立前缀 `/api/v1/benchmarks`，不侵入 `/api/v1/reports` 既有路由语义。
- 无 Benchmark 数据时报告渲染与导出行为与现状完全一致。
- 正式任务发布接口向后兼容：不传 `benchmark` 字段时行为不变。

## 12. 测试与验收

### 12.1 后端测试

- 正式任务标记 `benchmark = true` 后触发排行计算。
- 外部基线批量导入校验（字段缺失、单位/方向非法、重复）。
- 外部基线版本发布与不可变约束。
- 双轨对比：同模型既有实测又有外部基线时两者并存，排名以实测值排序，计算 delta 差异。
- 排行算法单测：并列名次、百分位、双向归一化、gap 计算。
- 场景标签与测试集分组匹配过滤。
- 版本不可变：新版本发布后旧排行不漂移。
- 排行计算幂等。
- Benchmark 报告生成与 `report_type = 'benchmark'`。
- 指标映射配置校验（单位/方向不一致拦截）。

### 12.2 前端测试

- 报告详情排行区块正确展示排名与参考线。
- 实测与导入数据颜色区分与来源筛选。
- 无排行数据时区块隐藏。
- 独立排行页按测试集/类别/指标/来源筛选正确。
- 外部基线管理页导入错误逐行提示。
- 发布弹窗 Benchmark 选项交互。
- Benchmark 报告列表与详情。

### 12.3 验收标准

1. 新模型注册后，创建任务、执行测试、发布为正式任务（标记 benchmark），排行自动更新。
2. 用户可导入外部基线数据（业界公开榜单），与平台实测结果合并排行。
3. 同一模型既有实测又有外部基线时，两者并列展示并计算差异（delta），用户可直观对比平台实测与业界公开数据的偏差。
4. 用户可在独立排行页按测试集 + 被测类别 + 数据来源查看排行。
5. 评测维度或测试集更新后，发布新版本正式任务，排行自动重算，旧版本排行保留。
6. 可发布 Benchmark 报告，包含全部参与排行的被测主体横向对比。
7. 只有正式发布的任务能上 Benchmark；日常任务不参与排行。
8. 现有报告生成、对比、导出功能无回归。

## 13. 被测主体候选（一期目标覆盖）

### 13.1 Realtime Voice LLM（全双工对话）

| 被测主体 | 类型 | device_type | 关键指标 |
| --- | --- | --- | --- |
| OpenAI GPT-4o Realtime | 闭源 API | `websocket_api` | 打断成功率、接管时延、连贯性 |
| Gemini Live | 闭源 API | `websocket_api` | 同上 |
| Moshi | 开源 | `websocket_api` | 同上 |
| Sesame CSM | 开源 | `websocket_api` | 同上 |
| Qwen-Audio | 开源 | `http_api` | 同上 |
| 豆包 | APP | `physical` | 同上 |
| ChatGPT APP | APP | `physical` | 同上 |
| 小翼音箱 | APP | `physical` | 同上 |
| MiniMax | 闭源 API | `websocket_api` | 同上 |
| 智谱 GLM-4-Voice | 闭源 API | `websocket_api` | 同上 |

### 13.2 ASR（实时流式语音识别）

| 被测主体 | 类型 | device_type | 关键指标 |
| --- | --- | --- | --- |
| Deepgram Nova | 闭源 API | `http_api` | WER、末字延迟 |
| OpenAI Whisper / gpt-4o-transcribe | 闭源 API | `http_api` | WER |
| AssemblyAI | 闭源 API | `http_api` | WER |
| Azure Speech | 闭源 API | `http_api` | WER |
| Google Chirp | 闭源 API | `http_api` | WER |
| NVIDIA Canary / Parakeet | 开源 | `http_api` | WER |
| ElevenLabs Scribe | 闭源 API | `http_api` | WER |
| Mistral Voxtral | 开源 | `http_api` | WER |
| 阿里云百炼 ASR | 闭源 API | `http_api` | WER |
| 火山引擎 ASR | 闭源 API | `http_api` | WER |
| 腾讯云 ASR | 闭源 API | `http_api` | WER |
| Soniox | 闭源 API | `http_api` | WER |

### 13.3 TTS（语音合成）

| 被测主体 | 类型 | device_type | 关键指标 |
| --- | --- | --- | --- |
| ElevenLabs | 闭源 API | `http_api` | MOS、首字延迟 |
| Cartesia Sonic | 闭源 API | `http_api` | MOS |
| Azure TTS | 闭源 API | `http_api` | MOS |
| Google TTS | 闭源 API | `http_api` | MOS |

### 13.4 翻译

| 被测主体 | 类型 | device_type | 关键指标 |
| --- | --- | --- | --- |
| Google Translate | 闭源 API | `http_api` | BLEU、COMET |
| DeepL | 闭源 API | `http_api` | BLEU |
| Azure Translator | 闭源 API | `http_api` | BLEU |

> 说明：以上为一期目标覆盖范围，实际参与排行的主体取决于已注册并完成测试发布的正式任务（平台实测）以及已导入的外部基线数据。新模型/新 APP 上线后随时可加入——注册被测主体 → 创建任务 → 执行 → 发布正式任务 → 自动入榜。尚未在本平台实测的模型，可通过导入外部基线数据先行入榜，待后续实测后替换为实测数据。

### 13.5 外部基线数据源参照（导入用）

| 领域 | 数据源 | 关键指标 | 说明 |
| --- | --- | --- | --- |
| ASR | Pipecat STT Benchmark | semantic WER、TTFS | 开源流式 ASR 评测 |
| ASR | Open ASR Leaderboard | WER | Hugging Face 维护 |
| ASR | 声网 ASR 排行 | WER、延迟 | 国内厂商覆盖 |
| Voice LLM | Full-Duplex-Bench | 打断成功率、连贯性 GPT-4o Score | 全双工对话评测 |
| Voice LLM | 声网对话式 AI 评测平台 | TTLW、WER、接话率 | 国内平台 |
| Voice LLM | Artificial Analysis | 延迟、质量分 | 综合评测 |
| TTS | 声网 TTS 排行 | MOS、TTFB | 国内厂商覆盖 |
| 翻译 | WMT 公开榜单 | BLEU、COMET | 国际机器翻译评测 |

> 导入外部基线时必须标注 `source`（数据来源）与 `sample_size`（采样规模），排行页展示口径提示，避免误导性对比。
