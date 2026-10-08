# 智能语音测试系统 - 报告文档

## 1. 文档概述

本文档详细描述智能语音测试系统中报告功能的实现，包括任务报告、任务对比报告和二次对比报告的设计、数据处理、存储和展示。同时提供每个卡片数据的查询、存储和计算逻辑的详细说明。

## 2. 报告类型与结构

### 2.1 报告类型

系统支持三种主要报告类型：

| 报告类型 | 核心功能 | 应用场景 |
|---------|---------|---------|
| 任务报告 | 单个测试任务的执行结果分析 | 查看单次测试任务的详细结果 |
| 任务对比报告 | 多个测试任务之间的对比分析 | 比较不同任务在相同设备/API上的表现 |
| 二次对比报告 | 历史报告之间的对比分析 | 分析系统性能随时间的变化趋势 |

### 2.2 统一报告结构

所有报告遵循统一的结构框架，包含以下核心模块：

1. **报告头部** - 报告基本信息和操作按钮
2. **设备/API信息对比** - 参与测试的设备和API基本信息
3. **用例执行数量对比** - 各设备/API上的用例执行情况
4. **分析结论** - 测试结果的综合分析
5. **按用例分组对比** - 按用例分组展示对比结果
6. **按用例标签对比** - 按用例标签展示对比结果
7. **具体用例对比** - 具体用例的执行结果对比

## 3. 数据模型与存储

### 3.1 核心数据模型

报告模块采用"主表 + 按需加载扩展表"的 7 表结构（定义见 `backend/models/models.py`），主表与各扩展表均以 `report_id` 关联，扩展表随报告级联删除。

#### 3.1.1 报告主表 (test_reports)

| 字段名 | 数据类型 | 描述 |
|-------|---------|------|
| id | INTEGER | 报告ID（主键） |
| name | VARCHAR(255) | 报告名称 |
| type | VARCHAR(30) | 报告类型 (task/comparison/secondary_comparison) |
| description | TEXT | 报告描述 |
| task_id | INTEGER | 关联测试任务ID（外键 → test_tasks.id，任务报告使用） |
| status | VARCHAR(20) | 报告状态 (draft/published) |
| analysis | TEXT | 人工/自动分析结论 |
| created_at / updated_at | DATETIME | 创建/更新时间 |

#### 3.1.2 报告扩展表（均以 report_id 关联 test_reports.id）

| 表名 | 关系 | 核心字段 | 用途 |
|------|------|---------|------|
| report_summaries | 一对一 | task_ids(JSON)、total_cases、completed_cases、failed_cases、pass_rate、duration、started_at、completed_at | 小数据量摘要，报告列表页快速查询 |
| report_summary_meta | 一对一 | dimension_values、case_categories、all_case_tags、devices、apis、resources、all_metrics、field_mappings（均 JSON） | 摘要元数据，筛选条件与维度列表按需加载 |
| report_raw_data | 一对一 | raw_data(JSON) | 原始维度分数数据，按需加载 |
| report_cases | 一对多 | test_case_id、name、category、tags(JSON)、metrics(JSON)、results(JSON)、audios(JSON)、algorithm_results(JSON)、algorithm_type、logs | 单用例详情，一个用例一行；metrics 为指标数组 `[{id, metric, value}]` |
| report_metric_stats | 一对一 | metric_data、tag_metric_data、tag_category_metric_data、case_type_stats、device_stats、api_stats（均 JSON） | 分组/标签/用例类型/设备/API 统计数据 |
| report_comparison_matrix | 一对一 | matrix_data(JSON) | 对比/二次对比报告的矩阵数据 |

#### 3.1.3 报告数据来源表（评估结果侧）

| 表名 | 核心字段 | 用途 |
|------|---------|------|
| test_results | task_id、test_case_id、device_id、api_id、algorithm_type、execution_status、response_time、algorithm_result(JSON)、execution_steps(JSON) | 测试执行结果（snake_case 存储） |
| test_result_dimensions | test_result_id、dimension_id、round_number（NULL=整体评估，0-indexed）、dimension_value、score、status(passed/failed)、evaluation_status | 各轮次/整体维度得分，报告指标计算的直接数据源 |

### 3.2 报告数据结构

```json
{
  "id": 1,
  "name": "报告名称",
  "description": "报告描述",
  "type": "task/comparison/secondary_comparison",
  "status": "draft/published",
  "task_id": 100,
  "analysis": "分析结论",
  "created_at": "2025-12-16T10:30:00",
  "updated_at": "2025-12-16T10:45:00",
  "summary": {
    "total_cases": 0,
    "completed_cases": 0,
    "failed_cases": 0,
    "pass_rate": 0,
    "duration": 0
  },
  "summary_meta": {
    "dimension_values": [],
    "case_categories": [],
    "all_case_tags": [],
    "devices": [],
    "apis": [],
    "all_metrics": []
  }
}
```

字段命名约定：数据库与后端 API 均为 **snake_case**；前端遵循 DDD 分层，仅 Infrastructure 层（api/adapters/dto）感知 snake_case，并在 DTO→Domain 映射时转换为 **camelCase**，Presentation 层（views/components）只见 camelCase Domain 模型。

### 3.3 数据存储方式

1. **关系型存储** - 核心数据（测试任务、用例、结果、报告）存储在PostgreSql数据库中
2. **JSON存储** - 复杂的对比数据和评估结果以JSON格式存储在数据库字段中
3. **前端缓存** - 频繁访问的数据在前端进行缓存，提高性能

## 4. 数据查询与计算

### 4.1 数据查询逻辑

报告的指标计算统一在后端完成（Python），前端不做指标计算，仅消费报告接口返回的聚合结果。

#### 4.1.1 任务报告数据流

报告生成入口为 `POST /api/v1/reports/generate-task`，异步执行 `report_controller_task._generate_task_report_async`，数据流如下：

```
test_results / test_result_dimensions          # 评估结果原始数据
        │  _get_dimension_results_batch(result_ids)   # 批量读取维度得分
        ▼
calculate_core_metrics → extract_dimension_values  # 有 overall 取 overall，否则取各轮算术平均
        ▼
_apply_resource_aggregation_strategies        # 聚合 3 策略（见 4.2）
        ▼
calculate_case_type_stats_optimized / calculate_device_api_stats
        ▼
test_reports + report_summaries / report_summary_meta / report_raw_data
        + report_cases / report_metric_stats（+ 对比报告另写 report_comparison_matrix）
```

生成进度可通过 `GET /api/v1/reports/<id>/progress` 轮询查询。

#### 4.1.2 对比报告数据查询

对比报告（`POST /api/v1/reports/compare`）与二次对比报告（`POST /api/v1/reports/secondary-compare`）复用上述计算链路；二次对比直接从源报告的 `report_cases.metrics`（指标数组 `[{id, metric, value}]`）读取数据，不重复计算。

#### 4.1.3 报告列表与详情查询

- 列表页：`GET /api/v1/reports` 从 `test_reports` JOIN `report_summaries` 快速返回摘要，避免加载大字段。
- 详情页：`GET /api/v1/reports/<id>` 返回主表 + summary/meta 扩展表；用例明细按需通过 `GET /api/v1/reports/<id>/cases` 或 `POST /api/v1/reports/<id>/cases/search` 查询。

### 4.2 数据计算逻辑

#### 4.2.1 维度取值规则 (extract_dimension_values)

位于 `backend/utils/report/report_utils.py`。对单个测试结果提取维度值：优先取整体评估（`round_number` 为 NULL）的维度得分；无整体结果时对各轮次得分做算术平均。多轮评估维度隔离规则见《报告轮次数据修复文档》。

#### 4.2.2 资源聚合 3 策略 (_apply_resource_aggregation_strategies)

位于 `backend/utils/report/aggregation_strategies.py`，按维度的 aggregation 配置选择策略（配置化，非硬编码）：

| 策略类 | 聚合方式 | 说明 |
|-------|---------|------|
| SimpleAverageStrategy | average | 算术平均，通用默认策略 |
| WeightedSumRatioStrategy | weighted_wer | 加权求和比值，适用于 WER/CER 等错误率类指标 |
| PassRateStrategy | pass_rate | 通过率统计，基于维度状态 passed/failed |

#### 4.2.3 用例分组/标签统计

按分组与标签的维度平均值统计由 `calculate_case_type_stats_optimized`（`report_utils.py`）实现，结果写入 `report_metric_stats.metric_data / tag_metric_data / tag_category_metric_data`；分组与标签信息来自 `report_cases.category / tags`。

#### 4.2.4 设备/API 统计

设备与 API 维度的执行统计由 `calculate_device_api_stats`（`report_utils.py`）计算，结果写入 `report_metric_stats.device_stats / api_stats`。

#### 4.2.5 指标维度与 xiaoyi_metrics 体系对齐

报告展示的指标维度由 `dimensions` 表配置驱动（小艺维度经 `backend/scripts/migrations/202606/seed_xiaoyi_dimensions.py` 以中文名 + `task_type_code` 注册），维度名与 `xiaoyi_metrics` 评估指标体系的 12 个 task_type（Calculator 注册表）一一对应：turn_taking（话轮接管主维度，统一双路 ASR 后遍历子维度）、tor、false_takeover、takeover_latency、high_freq_turn_taking、high_freq_llm_judge、interruption_metrics、non_interactive_latency、noise_latency、rejection_judge、interruption_judge、llm_judge。报告侧不重新定义指标含义，仅按上述体系展示与聚合；`input_asr`（输入识别准确率）为 turn_taking 包内的辅助计算函数，非独立注册维度。

## 5. 报告生成流程

### 5.1 任务报告生成流程

1. **数据收集** - 收集测试任务的基本信息和测试结果
2. **数据处理** - 计算测试统计数据，如通过率、执行时间等
3. **报告生成** - 根据统一结构生成报告
4. **自动分析** - 生成初步的分析结论
5. **报告保存** - 保存为草稿报告
6. **用户编辑** - 支持用户编辑和完善报告
7. **报告发布** - 发布或导出报告

### 5.2 任务对比报告生成流程

1. **任务选择** - 用户选择多个测试任务
2. **数据收集** - 收集所有选中任务的测试数据
3. **数据处理** - 计算各任务的统计数据和对比指标
4. **报告生成** - 根据统一结构生成对比报告
5. **自动分析** - 生成初步的对比分析结论
6. **报告保存** - 保存为草稿报告
7. **用户编辑** - 支持用户编辑和完善报告
8. **报告发布** - 发布或导出报告

### 5.3 二次对比报告生成流程

1. **报告选择** - 用户从历史报告库中选择多个报告
2. **数据收集** - 收集所有选中报告的对比数据
3. **数据处理** - 计算报告间的差异和趋势
4. **报告生成** - 根据统一结构生成二次对比报告
5. **自动分析** - 生成初步的趋势分析结论
6. **报告保存** - 保存为草稿报告
7. **用户编辑** - 支持用户编辑和完善报告
8. **报告发布** - 发布或导出报告

## 6. 核心功能模块

### 6.1 任务报告模块

#### 6.1.1 功能描述

任务报告模块用于展示单个测试任务的执行结果，包括任务基本信息、设备/API执行情况、用例执行结果和分析结论。

#### 6.1.2 实现逻辑

1. **触发** - 任务记录页调用 `POST /api/v1/reports/generate-task`，后端异步生成任务报告并落库
2. **加载** - Presentation 层组件（TaskReportPanel）通过 composables（Ports）获取报告，Infrastructure 层调用 `GET /api/v1/reports/<id>` 并将 snake_case DTO 映射为 camelCase Domain 模型
3. **展示** - 按 2.2 统一结构渲染报告头部、设备/API信息、执行统计、用例明细与分析结论

#### 6.1.3 关键组件

- **TaskReportPanel** - 任务报告面板组件，任务报告的主容器（`src/components/report/TaskReportPanel.vue`）
- **ReportHeaderComponent** - 报告头部组件，展示报告标题和操作按钮
- **OverviewCardComponent** - 概览卡片组件，展示用例执行数量与通过率等概览统计

### 6.2 任务对比报告模块

#### 6.2.1 功能描述

任务对比报告模块用于对比多个测试任务的执行结果，包括设备/API对比、用例执行情况对比、按分组对比和按标签对比。

#### 6.2.2 实现逻辑

1. **获取任务数据** - 调用API获取对比的任务详情和测试结果
2. **生成基本信息** - 提取对比任务的标题、创建时间等信息
3. **生成设备/API信息** - 提取所有任务涉及的设备和API信息
4. **生成用例执行情况** - 计算各任务下不同设备/API的成功率、时长等
5. **生成分析结论** - 对比各任务的整体表现
6. **生成用例分组对比** - 计算各任务下不同分组的评估维度平均值
7. **生成用例标签对比** - 计算各任务下不同标签的评估维度平均值
8. **生成具体用例对比** - 对比具体用例在各任务/设备上的执行结果

#### 6.2.3 关键组件

- **ComparisonTableComponent** - 对比表格组件，展示不同任务的执行结果对比
- **ChartComponent** - 图表组件，展示对比数据的可视化图表
- **CaseCategoryComparisonComponent** - 按分组对比组件，展示不同分组的执行情况对比
- **CaseTagComparisonComponent** - 按标签对比组件，展示不同标签的执行情况对比
- **SpecificCaseComparisonComponent** - 具体用例对比组件，展示同一用例在各任务/设备/API上的表现
- **FilterComponent** - 筛选组件，支持设备和API等筛选条件

### 6.3 二次对比报告模块

#### 6.3.1 功能描述

二次对比报告模块用于对比多个历史报告，分析系统性能随时间的变化趋势。

#### 6.3.2 实现逻辑

```javascript
// 二次对比报告生成函数
function generateHistoricalComparisonReport(selectedReports) {
    // 1. 收集历史报告数据
    // 2. 计算报告间的差异和趋势
    // 3. 生成趋势分析图表
    // 4. 生成趋势分析结论
    // 5. 保存报告
}
```

#### 6.3.3 关键组件

- **HistoryReports** - 历史报告页面（`src/views/HistoryReports.vue`），支持选择多个历史报告，选择逻辑位于 `src/views/HistoryReportsLogic/historyReports.ts`
- **ComparisonTableComponent** - 对比表格组件，复用统一报告结构展示报告间差异
- **ChartComponent** - 图表组件，展示性能随时间的变化趋势

## 7. 卡片数据的查询存储计算

### 7.1 设备/API信息对比卡片

#### 7.1.1 数据来源

- **设备信息** - `devices` 表，随报告快照写入 `report_summary_meta.devices`
- **API信息** - `apis` 表，随报告快照写入 `report_summary_meta.apis`
- **执行统计** - `calculate_device_api_stats` 计算结果写入 `report_metric_stats.device_stats / api_stats`

#### 7.1.2 数据计算

设备/API 维度的用例执行统计（总数、完成数、失败数、通过率、时长）由后端 `calculate_device_api_stats`（`backend/utils/report/report_utils.py`）统一计算，指标得分经 4.2.2 聚合策略汇总；前端不做计算，仅渲染接口返回结果。

#### 7.1.3 数据展示

以卡片形式展示设备/API的基本信息和测试统计数据，支持展开查看详细信息。

### 7.2 用例执行数量对比卡片

#### 7.2.1 数据来源

- **执行统计** - `report_summaries.total_cases / completed_cases / failed_cases`（对比报告的 `task_ids` 关联各任务）

#### 7.2.2 数据计算

用例执行数量统计在报告生成阶段由后端计算并写入 `report_summaries`；报告详情接口直接返回，前端仅做展示。通过率口径为完成用例中维度状态 passed 的占比（PassRateStrategy）。

#### 7.2.3 数据展示

以表格和柱状图形式展示各任务的用例执行情况对比。

### 7.3 按用例分组对比卡片

#### 7.3.1 数据来源

- **分组统计数据** - `report_metric_stats.case_type_stats`（报告生成阶段快照）
- **用例分组信息** - `report_cases.category`（报告生成时从用例快照）

#### 7.3.2 数据计算

按分组的维度平均值统计由后端在报告生成阶段统一完成：`calculate_case_type_stats_optimized`（`backend/utils/report/report_utils.py`）按 `report_cases.category` 分组，对每个分组先经 4.2.1 维度取值规则提取维度值，再经 4.2.2 聚合策略汇总，结果写入 `report_metric_stats.case_type_stats`；前端不做计算，仅渲染接口返回结果。

#### 7.3.3 数据展示

以筛选条件面板、表格和柱状图形式展示不同分组的评估维度平均值对比。

### 7.4 按用例标签对比卡片

#### 7.4.1 数据来源

- **标签统计数据** - `report_metric_stats.tag_metric_data / tag_category_metric_data`（报告生成阶段快照）
- **用例标签信息** - `report_cases.tags`（报告生成时从用例快照）

#### 7.4.2 数据计算

按标签的维度平均值统计同样由后端在报告生成阶段统一完成：`calculate_case_type_stats_optimized`（`backend/utils/report/report_utils.py`）按 `report_cases.tags` 聚合（标签可多选，一个用例计入其全部标签），维度取值与聚合策略同 7.3.2，结果写入 `report_metric_stats.tag_metric_data / tag_category_metric_data`；前端不做计算，仅渲染接口返回结果。

#### 7.4.3 数据展示

以交互式标签云和分组表格形式展示不同标签的评估维度平均值对比。

### 7.5 具体用例对比卡片

#### 7.5.1 数据来源

- **用例详情** - `report_cases`（name、category、tags、algorithm_type、algorithm_results）
- **用例指标** - `report_cases.metrics`（指标数组 `[{id, metric, value}]`）
- **执行结果与音频** - `report_cases.results / audios`（报告生成时从 `test_results` 与 `audios` 快照）

#### 7.5.2 数据计算

具体用例对比不做二次计算：报告生成阶段将每个用例的执行结果、算法结果（如 ASR 识别文本、翻译文本，存于 `algorithm_results`，按 `algorithm_type` 区分结构）与音频信息快照至 `report_cases`；查询时通过 `GET /api/v1/reports/<id>/cases` 或 `POST /api/v1/reports/<id>/cases/search` 按条件检索，对比展示同一用例在各任务/设备/API 上的表现。

#### 7.5.3 数据展示

以可折叠的用例列表形式展示，每个用例包含详细的执行结果对比，支持展开查看音频信息、ASR识别信息和翻译信息。

## 8. 技术实现细节

### 8.1 前端实现

- **框架** - Vue.js 3 + Electron 29.4.4
- **组件化设计** - 采用组件化架构，提高代码复用性和可维护性
- **响应式设计** - 支持不同屏幕尺寸的自适应布局
- **数据可视化** - 使用Chart.js实现各种图表展示
- **性能优化** - 采用数据懒加载、图表缓存、异步处理等优化手段

### 8.2 后端实现

- **框架** - Flask + PostgreSql
- **RESTful API** - 提供RESTful API接口，支持前端数据访问
- **ORM** - 使用SQLAlchemy进行数据库操作
- **异步处理** - 耗时操作采用异步处理，提高系统响应速度

### 8.3 核心组件

| 组件名称 | 功能描述 | 实现文件 |
|---------|---------|---------|
| TaskReportPanel | 任务报告面板组件 | src/components/report/TaskReportPanel.vue |
| ReportHeaderComponent | 报告头部组件 | src/components/report/ReportHeaderComponent.vue |
| OverviewCardComponent | 概览卡片组件 | src/components/report/OverviewCardComponent.vue |
| ComparisonTableComponent | 对比表格组件 | src/components/report/ComparisonTableComponent.vue |
| CaseCategoryComparisonComponent | 按分组对比组件 | src/components/report/CaseCategoryComparisonComponent.vue |
| CaseTagComparisonComponent | 按标签对比组件 | src/components/report/CaseTagComparisonComponent.vue |
| SpecificCaseComparisonComponent | 具体用例对比组件 | src/components/report/SpecificCaseComparisonComponent.vue |
| ChartComponent | 图表展示组件 | src/components/report/ChartComponent.vue |
| AnalysisEditorComponent | 分析结论编辑组件 | src/components/report/AnalysisEditorComponent.vue |
| FilterComponent | 筛选组件 | src/components/report/FilterComponent.vue |

## 9. 使用指南

### 9.1 生成任务报告

1. 进入测试任务记录页面
2. 找到需要生成报告的任务
3. 点击"查看报告"按钮
4. 系统自动生成任务报告
5. 可以编辑报告内容，添加分析结论
6. 点击"发布"或"导出"按钮完成报告生成

### 9.2 生成任务对比报告

1. 进入测试任务记录页面
2. 选择多个需要对比的任务（至少2个）
3. 点击"批量对比"按钮
4. 系统自动生成任务对比报告
5. 可以使用统一的设备和API选择器筛选对比项
6. 可以编辑报告内容，添加分析结论
7. 点击"发布"或"导出"按钮完成报告生成

### 9.3 生成二次对比报告

1. 进入历史报告页面
2. 选择多个需要对比的历史报告（至少2个）
3. 点击"报告对比"按钮
4. 系统自动生成二次对比报告
5. 可以查看性能趋势和差异分析
6. 可以编辑报告内容，添加分析结论
7. 点击"发布"或"导出"按钮完成报告生成

## 10. 性能优化

### 10.1 前端优化

1. **数据懒加载** - 分段加载大量数据，提高页面加载速度
2. **图表缓存** - 缓存生成的图表，避免重复渲染
3. **异步处理** - 耗时操作（如导出）采用异步处理
4. **防抖节流** - 搜索和筛选操作添加防抖节流，减少不必要的请求
5. **组件按需加载** - 采用动态导入方式，按需加载组件

### 10.2 后端优化

1. **查询优化** - 优化数据库查询语句，添加合适的索引
2. **缓存机制** - 缓存频繁访问的数据，减少数据库查询次数
3. **异步处理** - 耗时操作采用异步处理，提高系统响应速度
4. **数据分页** - 提供分页查询接口，减少单次返回数据量

## 11. 总结

智能语音测试系统的报告功能提供了全面的测试结果分析和对比能力，支持任务报告、任务对比报告和二次对比报告。报告采用统一的结构框架，包含设备/API信息对比、用例执行情况对比、分析结论、按分组对比、按标签对比和具体用例对比等模块。

系统采用了现代化的技术栈，前端基于 Vue 3 + Pinia + Element Plus + ECharts 并遵循 DDD 分层，后端基于 Flask + SQLAlchemy + PostgreSQL，实现了高性能、可扩展的报告功能。报告数据来自系统中的测试任务与评估结果（test_results / test_result_dimensions），由后端统一计算并快照至报告 7 表，指标维度与 xiaoyi_metrics 评估指标体系对齐，通过配置化的聚合策略生成直观、有用的报告内容。

报告功能的设计遵循了统一的设计规范，包括视觉设计、交互设计和技术实现规范，确保了报告的一致性和专业性。同时，系统还提供了丰富的编辑和导出功能，满足用户的不同需求。

通过报告功能，用户可以全面了解测试结果，对比不同任务的执行情况，分析系统性能趋势，为后续优化提供依据。