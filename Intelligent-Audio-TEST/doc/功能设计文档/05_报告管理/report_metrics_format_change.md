# 测试报告用例 metrics 格式变更说明

## 变更概述

将测试报告用例数据中 `metrics` 字段的格式从**按资源分组的动态键值对对象**改为**固定格式的数组**，以提高数据一致性和前端适配便利性。

---

## 数据格式对比

### 变更前（对象格式）

```json
"metrics": {
  "API测试任务_xxx-mock1": {
    "WER": 2.55,
    "wer_en": 0.0,
    "wer_zh": 0.0
  },
  "API测试任务_xxx-mock2": {
    "WER": 3.21,
    "wer_en": 1.0,
    "wer_zh": 0.0
  }
}
```

### 变更后（数组格式）

```json
"metrics": [
  {"id": 9, "metric": "WER", "value": 2.5487333333333333},
  {"metric": "success_rate", "value": 100},
  {"id": 11, "metric": "wer_en", "value": 0},
  {"id": 10, "metric": "wer_zh", "value": 0}
]
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | number | 维度ID，可选 |
| `metric` | string | 指标名称（如 WER、success_rate） |
| `value` | number | 指标数值 |

---

## 代码修改清单

### 1. 任务报告生成 (`report_controller_task.py`)

#### 修改位置
- **行 240**: `case_metrics` 初始化从 `{}` 改为 `[]`
- **行 317-331**: 将指标数据存储逻辑从 `case_metrics[resource] = dim_values` 改为遍历追加数组元素

```python
# 修改前
case_metrics = {}

for result in case_results:
    dim_values = ReportControllerBase.extract_dimension_values(...)
    case_metrics[resource] = dim_values

# 修改后
case_metrics = []

for result in case_results:
    dim_values = ReportControllerBase.extract_dimension_values(...)
    for dim_name, dim_value in dim_values.items():
        if dim_value is not None:
            dim_id = None
            for dim in all_dimensions:
                if dim.name == dim_name:
                    dim_id = dim.id
                    break
            case_metrics.append({
                "id": dim_id,
                "metric": dim_name,
                "value": dim_value
            })
```

#### 修复问题
- **行 402-415**: 修复 ASR/翻译默认文本生成逻辑，改用 `case_results` 而非 `case_metrics.keys()`

### 2. 报告工具类 (`utils/report_utils.py`)

#### 修改位置
- **行 990-992**: 在 `normalize_summary_metrics` 函数中添加数组格式判断

```python
# 新增判断
metrics = case.get('metrics')
if isinstance(metrics, list):
    new_case['metrics'] = metrics
elif isinstance(metrics, dict):
    # 原有对象格式处理逻辑...
```

### 3. 基础报告控制器 (`controllers/report_controller_base.py`)

#### 修改位置
- **行 527-542**: `search_report_cases` 方法改为直接从 `test_reports_cases` 字段读取

```python
# 直接从 test_reports_cases 字段读取用例数据
cases = []
if report.test_reports_cases and isinstance(report.test_reports_cases, list):
    cases = report.test_reports_cases
else:
    # 备选：从 summary.cases 读取（向后兼容）
    summary = ReportUtils.normalize_summary_metrics(dict(report.summary) if report.summary else {})
    cases = summary.get('cases', []) or []
```

### 4. 对比报告生成 (`controllers/report_controller_compare.py`)

#### 数据来源
对比报告从源任务报告的 `test_reports_cases` 字段获取用例数据。

#### 核心逻辑
```python
# 从源任务报告获取用例数据
source_cases = []
for report in task_reports:
    if report.test_reports_cases and isinstance(report.test_reports_cases, list):
        source_cases.extend(report.test_reports_cases)
        break  # 只取最新的报告
```

#### 处理流程
1. 查找任务关联的最新报告
2. 从报告的 `test_reports_cases` 字段读取用例数据
3. 用例数据保持原格式（数组格式的 metrics）
4. 存储到新对比报告的 `test_reports_cases` 字段

### 5. 二次对比报告生成 (`controllers/report_controller_secondary.py`)

#### 数据来源
二次对比报告从多个源任务报告的 `test_reports_cases` 字段聚合用例数据。

#### 核心逻辑
```python
# 从所有源任务报告获取用例数据
source_cases = []
for report in reports:
    if report.test_reports_cases and isinstance(report.test_reports_cases, list):
        source_cases.extend(report.test_reports_cases)

# 如果没有从源报告获取到用例数据，使用构建的 cases
if not source_cases:
    # 备选：从 summary.cases 读取（向后兼容）
    ...
```

#### 处理流程
1. 遍历所有源任务报告
2. 从每个报告的 `test_reports_cases` 字段读取用例数据
3. 聚合所有用例到 `source_cases` 列表
4. 存储到新二次对比报告的 `test_reports_cases` 字段

### 6. 用例搜索 API 向后兼容设计

#### 设计原则
用例搜索 API `/api/v1/reports/{id}/cases/search` 应同时支持：
1. **新格式**: 直接从 `test_reports_cases` 字段读取（新生成的报告）
2. **旧格式**: 从原始测试任务相关数据查询（兼容旧报告）

#### 兼容逻辑
```python
def search_report_cases(report_id):
    report = db.session.get(Report, report_id)
    if not report:
        return error_response("未找到测试报告", 404)
    
    cases = []
    
    # 优先级1: 直接从 test_reports_cases 读取（新报告）
    if report.test_reports_cases and isinstance(report.test_reports_cases, list):
        cases = report.test_reports_cases
    else:
        # 备选: 从 summary.cases 读取（旧报告）
        summary = dict(report.summary) if report.summary else {}
        cases = summary.get('cases', []) or []
    
    # 如果仍然没有数据，从原始测试任务查询（兜底兼容）
    if not cases:
        task_ids = []
        if report.task_id:
            task_ids = [report.task_id]
        elif report.comparison_data and isinstance(report.comparison_data, dict):
            task_ids = report.comparison_data.get('task_ids', [])
        
        if task_ids:
            # 从原始 TestResult、TestCase 等表查询数据
            results = TestResult.query.filter(TestResult.task_id.in_(task_ids)).all()
            # 构建用例数据（按新格式）
            ...
    
    # 应用筛选条件（关键词、分类、标签）
    ...
    
    return success_response({"items": paginated_cases, ...})
```

#### 兼容性保证
| 场景 | 数据来源 | metrics 格式 |
|------|----------|--------------|
| 新任务报告 | `test_reports_cases` | 数组格式 |
| 旧任务报告 | `summary.cases` | 可能为对象或数组 |
| 无用例数据 | 原始任务数据查询 | 按新格式构建 |

### 7. 前端组件适配

#### 7.1 TestCaseReportDetail.vue (`components/common/TestCaseReportDetail.vue`)

- 添加 `metrics` prop 支持新格式
- 新增 `displayMetrics` computed 属性，兼容新旧格式
- 新增 `calculateScore` 和 `formatValue` 辅助函数

```javascript
const displayMetrics = computed(() => {
  if (props.dimensions && props.dimensions.length > 0) {
    return props.dimensions.map(dim => ({
      id: dim.id,
      metric: dim.name,
      value: dim.value,
      score: dim.score,
      errorMessage: dim.errorMessage
    }));
  }
  if (props.metrics && props.metrics.length > 0) {
    return props.metrics.map(m => ({
      id: m.id,
      metric: m.metric,
      value: m.value,
      score: calculateScore(m.value),
      errorMessage: null
    }));
  }
  return [];
});
```

#### 7.2 SpecificCaseComparisonComponent.vue (`components/report/SpecificCaseComparisonComponent.vue`)

- **行 589-617**: 添加 `toMetricsMap` 和 `toTextMap` 辅助函数
- **行 410-436**: 更新 `actualAllMetrics` computed 属性，支持新数组格式

```javascript
const toMetricsMap = (caseItem) => {
  if (!caseItem) return {}
  if (caseItem.metrics && Array.isArray(caseItem.metrics)) {
    const result = {}
    caseItem.metrics.forEach(m => {
      if (!m || !m.metric) return
      const key = m.id ? `${m.id}_${m.metric}` : m.metric
      result[key] = m.value
    })
    return result
  }
  if (caseItem.metrics && typeof caseItem.metrics === 'object') {
    return caseItem.metrics
  }
  return {}
}
```

---

## 数据流程

```
任务执行 → 生成任务报告 → cases 按新格式存储到 test_reports_cases
                                        ↓
对比报告生成 → 从源任务报告的 test_reports_cases 获取
                                        ↓
二次对比报告 → 从所有源任务报告聚合 test_reports_cases
                                        ↓
/api/v1/reports/{id}/cases/search → 直接读取 test_reports_cases
                                        ↓
前端展示 → TestCaseReportDetail 组件渲染
```

---

## 向后兼容性

1. **search_report_cases API**: 当 `test_reports_cases` 为空时，自动从 `summary.cases` 读取
2. **前端组件**: `displayMetrics` 同时支持 `dimensions`（旧格式）和 `metrics`（新格式）
3. **normalize_summary_metrics**: 同时处理对象格式和数组格式

---

## 验证方法

### 1. 生成任务报告
```bash
curl -X POST "http://localhost:5000/api/v1/reports/generate-task" \
  -H "Content-Type: application/json" \
  -d '{"taskId": 24, "name": "测试报告"}'
```

### 2. 查询用例数据
```bash
curl -X POST "http://localhost:5000/api/v1/reports/{report_id}/cases/search" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 3. 验证返回数据格式
```json
{
  "items": [
    {
      "id": 1,
      "name": "测试用例1",
      "metrics": [
        {"id": 9, "metric": "WER", "value": 2.55},
        {"metric": "success_rate", "value": 100}
      ]
    }
  ]
}
```

---

## 注意事项

1. **重启服务**: 修改 Python 代码后需重启后端服务
2. **新数据生效**: 变更仅对新生成的报告生效，旧报告数据格式不变
3. **维度ID查找**: 部分指标可能无法找到对应的维度ID（`id` 字段可能为 `null`）
