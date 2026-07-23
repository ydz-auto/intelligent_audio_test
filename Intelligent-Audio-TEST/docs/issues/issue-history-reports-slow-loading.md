# Issue: 历史报告页面加载慢 (10秒)

## 问题描述

历史报告页面加载报告列表需要约 10 秒，即使只有 2-4 条记录。

## 问题分析

### 诊断过程

1. **添加请求耗时日志** - 在 `app.py` 的 `before_request` 和 `after_request` 中添加耗时记录
2. **添加查询计时** - 在 `report_controller_base.py` 的 `get_all` 方法中添加详细计时
3. **数据库直接查询测试** - 在 PostgreSQL 中直接执行 SQL 查询

### 发现的问题

| 检查项 | 结果 |
|--------|------|
| 数据库直接查询 | 114ms (正常) |
| 后端接口总耗时 | 5031ms (异常) |
| paginate 耗时 | 5031ms (问题所在) |
| Data query 耗时 | 5832ms (主要瓶颈) |

### 根本原因

**Report 表及相关表包含大量 JSON 字段，导致 SELECT 查询慢：**

1. **Report 表**（已删除）：
   - `summary` - 数据摘要统计
   - `comparison_data` - 对比分析数据
   - `test_reports_cases` - 报告用例列表信息

2. **ReportSummary 表**（已拆分）：
   - `dimension_values` - 维度平均分列表
   - `case_categories` - 用例分组列表
   - `all_case_tags` - 用例标签列表
   - `devices` - 设备列表
   - `apis` - API列表
   - `resources` - 资源列表
   - `resource_headers` - 资源头信息
   - `all_metrics` - 评估维度列表

3. **ReportDetailData 表**（已拆分）：
   - `raw_data` - 原始维度分数数据（最大）
   - `metric_data` - 分组指标数据
   - `tag_metric_data` - 标签指标数据
   - `cases` - 用例详情列表（很大）
   - `comparison_matrix` - 对比矩阵数据
   - 其他统计数据字段

## 解决方案

### 1. 删除 Report 表的大 JSON 字段

Report 表本身不需要存储这些大数据。

### 2. 拆分 ReportSummary 和 ReportDetailData 的 JSON 字段到新表

创建以下新表，直接关联到 Report 表：

| 新表名 | 存储内容 | 用途 |
|--------|----------|------|
| `report_summary_meta` | dimension_values, case_categories, all_case_tags, devices, apis, resources, resource_headers, all_metrics | 详情页按需加载 |
| `report_raw_data` | raw_data | 详情页按需加载 |
| `report_cases` | cases | 用例列表页按需加载 |
| `report_metric_stats` | metric_data, tag_metric_data, tag_category_metric_data, case_type_stats, device_stats, api_stats | 详情页按需加载 |
| `report_comparison_matrix` | comparison_matrix | 对比报告按需加载 |

### 3. ReportSummary 只保留基本统计字段

保留：`report_id`, `task_ids`, `total_cases`, `completed_cases`, `failed_cases`, `pass_rate`, `duration`, `started_at`, `completed_at`

这些字段用于列表页快速查询，不需要加载大 JSON 字段。

### 4. 删除 ReportDetailData 表

数据已迁移到新表，不再需要此表。

## 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `backend/models/models.py` | 创建新模型，删除旧 JSON 字段，添加 Report relationship |
| `backend/controllers/report_controller_base.py` | 修改 get_one、get_report_cases 方法，从新表获取数据 |
| `backend/controllers/report_controller_task.py` | 修改报告生成逻辑，数据存储到新表 |
| `backend/controllers/report_controller_secondary.py` | 修改二次对比报告生成逻辑 |
| `backend/controllers/report_controller_compare.py` | 修改对比报告生成逻辑 |
| `backend/controllers/report_controller.py` | 修改报告更新逻辑 |
| `backend/app.py` | 添加请求耗时日志 |

## 新表结构

### report_summary_meta
```sql
CREATE TABLE report_summary_meta (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
    dimension_values JSONB,
    case_categories JSONB,
    all_case_tags JSONB,
    devices JSONB,
    apis JSONB,
    resources JSONB,
    resource_headers JSONB,
    all_metrics JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### report_raw_data
```sql
CREATE TABLE report_raw_data (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
    raw_data JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### report_cases
```sql
CREATE TABLE report_cases (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
    cases JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### report_metric_stats
```sql
CREATE TABLE report_metric_stats (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
    metric_data JSONB,
    tag_metric_data JSONB,
    tag_category_metric_data JSONB,
    case_type_stats JSONB,
    device_stats JSONB,
    api_stats JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### report_comparison_matrix
```sql
CREATE TABLE report_comparison_matrix (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL UNIQUE REFERENCES test_reports(id),
    comparison_matrix JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

## 迁移脚本

### 运行迁移脚本

```bash
python backend/scripts/migrations/202605/split_report_json_fields.py
```

### 迁移脚本执行内容

1. 创建 5 个新表
2. 创建索引
3. 从旧表迁移数据到新表
4. 删除旧表的 JSON 字段
5. 删除 Report 表的旧 JSON 字段

## 预期效果

执行迁移后，历史报告页面加载时间应从 **10 秒降低到毫秒级别**。

列表查询只加载 ReportSummary 的基本统计字段（`total_cases`, `completed_cases`, `failed_cases`, `pass_rate`），不加载任何大 JSON 字段。

详情页和用例列表页按需加载对应的新表数据。

## 注意事项

1. **旧数据兼容**：此修改不兼容旧报告数据，迁移脚本会将数据迁移到新表
2. **需要重启后端**：修改模型后需要重启后端服务
3. **前端无影响**：前端接口调用不变，数据格式不变

## 相关 Issue

- 无

## 日期

2025-05-22