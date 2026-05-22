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

**Report 表包含三个大 JSON 字段，导致 SELECT * 查询慢：**

```python
summary = Column(JSON, comment='数据摘要统计
comparison_data = Column(JSON, comment='对比分析数据
test_reports_cases = Column(JSON, comment='存储报告用例列表信息
```

这些字段存储了大量数据，即使只有几条记录，`SELECT *` 也会读取所有大字段数据，导致查询耗时 5-8 秒。

## 解决方案

### 1. 删除 Report 表的大 JSON 字段

Report 表本身不需要存储这些大数据，因为已经有拆分表：
- `ReportSummary` - 存储摘要数据（列表页使用）
- `ReportDetailData` - 存储详情数据（详情页按需加载）

### 2. 将对比报告数据迁移到拆分表

- `ReportSummary.task_ids` - 存储对比报告关联的任务 ID
- `ReportDetailData.comparison_matrix` - 存储对比矩阵数据

### 3. 修改相关代码

- 模型定义 (`models.py`)
- Schema 定义 (`schemas/report.py`)
- 控制器代码 (`report_controller_base.py`, `report_controller_secondary.py`)

## 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `backend/models/models.py` | 删除 Report 表的 summary/comparison_data/test_reports_cases 字段，添加 ReportSummary.task_ids 和 ReportDetailData.comparison_matrix 字段 |
| `backend/schemas/report.py` | 删除 ReportDetailData 的 comparisonData 字段 |
| `backend/controllers/report_controller_base.py` | 删除 comparison_data 相关代码，添加查询计时日志 |
| `backend/controllers/report_controller_secondary.py` | 将 comparison_data 数据存储到 ReportDetailData.comparison_matrix |
| `backend/app.py` | 添加请求耗时日志 |

## 迁移脚本

### 1. 删除大字段并添加新字段

```bash
python backend/scripts/migrations/202505/remove_report_large_columns.py
```

或直接执行 SQL：

```sql
ALTER TABLE test_reports DROP COLUMN IF EXISTS summary;
ALTER TABLE test_reports DROP COLUMN IF EXISTS comparison_data;
ALTER TABLE test_reports DROP COLUMN IF EXISTS test_reports_cases;
ALTER TABLE report_summaries ADD COLUMN IF NOT EXISTS task_ids JSON;
ALTER TABLE report_detail_data ADD COLUMN IF NOT EXISTS comparison_matrix JSON;
```

### 2. 为 Task 表添加索引（可选优化）

```bash
python backend/scripts/migrations/202505/add_task_indexes.py
```

或直接执行 SQL：

```sql
CREATE INDEX IF NOT EXISTS idx_task_status ON test_tasks (status);
CREATE INDEX IF NOT EXISTS idx_task_algorithm_type ON test_tasks (algorithm_type);
CREATE INDEX IF NOT EXISTS idx_task_created_at ON test_tasks (created_at);
CREATE INDEX IF NOT EXISTS idx_task_status_deleted ON test_tasks (status, deleted);
ANALYZE test_tasks;
```

## 预期效果

执行迁移后，历史报告页面加载时间应从 **10 秒降低到毫秒级别**。

## 注意事项

1. **旧数据兼容**：此修改不兼容旧报告数据，旧报告的 summary/comparison_data 数据将丢失
2. **前端影响**：前端 `comparisonData` prop 仍然可用，数据来源改为从 `ReportDetailData.comparison_matrix` 获取
3. **需要重启后端**：修改模型后需要重启后端服务

## 相关 Issue

- 无

## 日期

2025-05-22