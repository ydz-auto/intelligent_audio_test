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

#### 3.1.1 测试报告表 (test_reports)

| 字段名 | 数据类型 | 描述 |
|-------|---------|------|
| id | INTEGER | 报告ID |
| name | VARCHAR(255) | 报告名称 |
| description | TEXT | 报告描述 |
| type | VARCHAR(50) | 报告类型 (task/comparison/secondary_comparison) |
| status | VARCHAR(20) | 报告状态 (draft/published) |
| test_type | INTEGER | 测试类型 |
| comparison_data | TEXT | 对比数据（JSON格式） |
| duration | FLOAT | 测试时长（秒） |
| creator | VARCHAR(50) | 创建人 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

#### 3.1.2 测试结果表 (test_result)

| 字段名 | 数据类型 | 描述 |
|-------|---------|------|
| id | INTEGER | 结果ID |
| task_id | INTEGER | 任务ID |
| case_id | INTEGER | 用例ID |
| device_id | INTEGER | 设备ID |
| asr_result | TEXT | ASR识别结果 |
| trans_result | TEXT | 翻译结果 |
| evaluation_results | TEXT | 评估结果（JSON格式） |
| create_time | DATETIME | 创建时间 |

### 3.2 报告数据结构

```json
{
  "id": "report_id",
  "name": "报告名称",
  "description": "报告描述",
  "type": "task/comparison/secondary_comparison",
  "status": "draft/published",
  "createdAt": "2025-12-16T10:30:00Z",
  "updatedAt": "2025-12-16T10:45:00Z",
  "report_structure": {
    "device_api_comparison": [],
    "case_execution_comparison": [],
    "analysis_conclusion": "",
    "category_comparison": {},
    "tag_comparison": {},
    "specific_case_comparison": {}
  }
}
```

### 3.3 数据存储方式

1. **关系型存储** - 核心数据（测试任务、用例、结果、报告）存储在SQLite数据库中
2. **JSON存储** - 复杂的对比数据和评估结果以JSON格式存储在数据库字段中
3. **前端缓存** - 频繁访问的数据在前端进行缓存，提高性能

## 4. 数据查询与计算

### 4.1 数据查询逻辑

#### 4.1.1 任务报告数据查询

```sql
-- 查询任务基本信息
SELECT * FROM test_task WHERE id = ?;

-- 查询任务关联的测试结果
SELECT tr.*, tc.name as case_name, td.name as device_name 
FROM test_result tr
JOIN test_case tc ON tr.case_id = tc.id
LEFT JOIN test_device td ON tr.device_id = td.id
WHERE tr.task_id = ?;

-- 查询测试结果的统计信息
SELECT 
    COUNT(*) as total_cases,
    SUM(CASE WHEN evaluation_results LIKE '%"status":"passed"%' THEN 1 ELSE 0 END) as passed_cases,
    SUM(CASE WHEN evaluation_results LIKE '%"status":"failed"%' THEN 1 ELSE 0 END) as failed_cases
FROM test_result 
WHERE task_id = ?;
```

#### 4.1.2 任务对比报告数据查询

```sql
-- 查询多个任务的基本信息
SELECT * FROM test_task WHERE id IN (?);

-- 查询多个任务的测试结果
SELECT tr.*, tc.name as case_name, td.name as device_name, tt.name as task_name
FROM test_result tr
JOIN test_case tc ON tr.case_id = tc.id
LEFT JOIN test_device td ON tr.device_id = td.id
JOIN test_task tt ON tr.task_id = tt.id
WHERE tr.task_id IN (?);
```

### 4.2 数据计算逻辑

#### 4.2.1 通过率计算

```javascript
// 计算通过率
function calculatePassRate(total, passed) {
    if (total === 0) return 0;
    return (passed / total) * 100;
}
```

#### 4.2.2 设备/API性能评分

```javascript
// 计算设备/API综合评分
function calculateDeviceScore(results) {
    let totalScore = 0;
    let count = 0;
    
    results.forEach(result => {
        if (result.evaluation_results) {
            const evalResults = JSON.parse(result.evaluation_results);
            evalResults.forEach(evalItem => {
                if (evalItem.score) {
                    totalScore += evalItem.score;
                    count++;
                }
            });
        }
    });
    
    return count > 0 ? totalScore / count : 0;
}
```

#### 4.2.3 用例分组统计

```javascript
// 按分组统计用例执行情况
const calculateCategoryStats = (results) => {
    const stats = {};
    results.forEach(result => {
        const category = result.category || '未分组';
        if (!stats[category]) {
            stats[category] = { total: 0, passed: 0, failed: 0 };
        }
        
        stats[category].total++;
        if (result.status === 'passed') {
            stats[category].passed++;
        } else {
            stats[category].failed++;
        }
    });
    
    // 计算通过率
    Object.keys(stats).forEach(category => {
        stats[category].passRate = calculatePassRate(stats[category].total, stats[category].passed);
    });
    
    return stats;
}
```

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

```javascript
// 任务报告生成函数
window.taskReport.generateTaskReport = function(taskData) {
    // 1. 确保报告容器显示
    // 2. 更新报告标题
    // 3. 生成与对比报告兼容的mock数据
    // 4. 初始化测试结果数据
    // 5. 调用对比报告生成函数，实现与对比报告一致的格式
};
```

#### 6.1.3 关键组件

- **ReportHeaderComponent** - 报告头部组件，展示报告标题和操作按钮
- **TaskInfoCard** - 任务信息卡片，展示任务的基本信息
- **ExecutionStatsCard** - 执行统计卡片，展示任务的执行情况
- **TestCaseTable** - 用例列表表格，展示所有用例的执行结果

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

- **UnifiedSelector** - 统一的设备和API选择器，支持多任务对比
- **ComparisonTable** - 对比表格，展示不同任务的执行结果对比
- **ChartComponent** - 图表组件，展示对比数据的可视化图表
- **CategoryComparison** - 按分组对比组件，展示不同分组的执行情况对比
- **TagComparison** - 按标签对比组件，展示不同标签的执行情况对比

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

- **ReportSelector** - 历史报告选择器，支持选择多个历史报告
- **TrendChart** - 趋势图表，展示性能随时间的变化趋势
- **DifferenceAnalysis** - 差异分析组件，展示报告间的差异

## 7. 卡片数据的查询存储计算

### 7.1 设备/API信息对比卡片

#### 7.1.1 数据来源

- **设备信息** - 从`test_device`表查询
- **API信息** - 从`test_api`表查询
- **测试结果** - 从`test_result`表查询

#### 7.1.2 数据计算

```javascript
// 计算设备/API的测试统计数据
function calculateDeviceStats(deviceId, taskIds) {
    const results = queryDeviceResults(deviceId, taskIds);
    
    return {
        totalCases: results.length,
        passedCases: results.filter(r => r.status === 'passed').length,
        failedCases: results.filter(r => r.status === 'failed').length,
        passRate: calculatePassRate(results.length, results.filter(r => r.status === 'passed').length),
        averageExecutionTime: calculateAverageExecutionTime(results)
    };
}
```

#### 7.1.3 数据展示

以卡片形式展示设备/API的基本信息和测试统计数据，支持展开查看详细信息。

### 7.2 用例执行数量对比卡片

#### 7.2.1 数据来源

- **测试结果** - 从`test_result`表查询

#### 7.2.2 数据计算

```javascript
// 计算用例执行数量统计
function calculateExecutionStats(taskIds) {
    const results = queryResultsByTaskIds(taskIds);
    
    return {
        totalCases: results.length,
        executedCases: results.filter(r => r.executed).length,
        passedCases: results.filter(r => r.status === 'passed').length,
        failedCases: results.filter(r => r.status === 'failed').length,
        passRate: calculatePassRate(results.length, results.filter(r => r.status === 'passed').length)
    };
}
```

#### 7.2.3 数据展示

以表格和柱状图形式展示各任务的用例执行情况对比。

### 7.3 按用例分组对比卡片

#### 7.3.1 数据来源

- **测试结果** - 从`test_result`表查询
- **测试用例** - 从`test_case`表查询，获取用例分组信息

#### 7.3.2 数据计算

```javascript
// 按分组计算用例评估维度平均值
function calculateCategoryComparison(taskIds, selectedDimensions = []) {
    const results = queryResultsByTaskIds(taskIds);
    const categories = {};
    
    results.forEach(result => {
        const category = result.case.category || '未分组';
        if (!categories[category]) {
            categories[category] = {
                taskStats: {},
                totalCases: 0
            };
        }
        
        if (!categories[category].taskStats[result.taskId]) {
            categories[category].taskStats[result.taskId] = {
                totalCases: 0,
                dimensionAverages: {} // 存储各评估维度的平均值
            };
        }
        
        categories[category].totalCases++;
        categories[category].taskStats[result.taskId].totalCases++;
        
        // 计算每个评估维度的平均值
        if (result.evaluation_results) {
            const evalResults = JSON.parse(result.evaluation_results);
            selectedDimensions.forEach(dimension => {
                const dimResult = evalResults.find(r => r.dimensionId === dimension.id);
                if (dimResult && typeof dimResult.score === 'number') {
                    if (!categories[category].taskStats[result.taskId].dimensionAverages[dimension.id]) {
                        categories[category].taskStats[result.taskId].dimensionAverages[dimension.id] = {
                            total: 0,
                            count: 0,
                            average: 0
                        };
                    }
                    
                    const dimStats = categories[category].taskStats[result.taskId].dimensionAverages[dimension.id];
                    dimStats.total += dimResult.score;
                    dimStats.count++;
                    dimStats.average = dimStats.total / dimStats.count;
                }
            });
        }
    });
    
    // 计算每个分组下所有任务的维度平均值
    Object.keys(categories).forEach(category => {
        categories[category].dimensionAverages = {};
        
        // 收集所有维度的总分和总数
        const categoryDimStats = {};
        Object.values(categories[category].taskStats).forEach(taskStats => {
            Object.entries(taskStats.dimensionAverages).forEach(([dimId, dimStats]) => {
                if (!categoryDimStats[dimId]) {
                    categoryDimStats[dimId] = { total: 0, count: 0 };
                }
                categoryDimStats[dimId].total += dimStats.total;
                categoryDimStats[dimId].count += dimStats.count;
            });
        });
        
        // 计算分组维度平均值
        Object.entries(categoryDimStats).forEach(([dimId, dimStats]) => {
            categories[category].dimensionAverages[dimId] = dimStats.count > 0 ? dimStats.total / dimStats.count : 0;
        });
    });
    
    return categories;
}
```

#### 7.3.3 数据展示

以筛选条件面板、表格和柱状图形式展示不同分组的评估维度平均值对比。

### 7.4 按用例标签对比卡片

#### 7.4.1 数据来源

- **测试结果** - 从`test_result`表查询
- **测试用例** - 从`test_case`表查询，获取用例标签信息

#### 7.4.2 数据计算

```javascript
// 按标签计算用例评估维度平均值
function calculateTagComparison(taskIds, selectedDimensions = []) {
    const results = queryResultsByTaskIds(taskIds);
    const tags = {};
    
    results.forEach(result => {
        const caseTags = result.case.tags || [];
        caseTags.forEach(tag => {
            if (!tags[tag]) {
                tags[tag] = {
                    taskStats: {},
                    totalCases: 0
                };
            }
            
            if (!tags[tag].taskStats[result.taskId]) {
                tags[tag].taskStats[result.taskId] = {
                    totalCases: 0,
                    dimensionAverages: {} // 存储各评估维度的平均值
                };
            }
            
            tags[tag].totalCases++;
            tags[tag].taskStats[result.taskId].totalCases++;
            
            // 计算每个评估维度的平均值
            if (result.evaluation_results) {
                const evalResults = JSON.parse(result.evaluation_results);
                selectedDimensions.forEach(dimension => {
                    const dimResult = evalResults.find(r => r.dimensionId === dimension.id);
                    if (dimResult && typeof dimResult.score === 'number') {
                        if (!tags[tag].taskStats[result.taskId].dimensionAverages[dimension.id]) {
                            tags[tag].taskStats[result.taskId].dimensionAverages[dimension.id] = {
                                total: 0,
                                count: 0,
                                average: 0
                            };
                        }
                        
                        const dimStats = tags[tag].taskStats[result.taskId].dimensionAverages[dimension.id];
                        dimStats.total += dimResult.score;
                        dimStats.count++;
                        dimStats.average = dimStats.total / dimStats.count;
                    }
                });
            }
        });
    });
    
    // 计算每个标签下所有任务的维度平均值
    Object.keys(tags).forEach(tag => {
        tags[tag].dimensionAverages = {};
        
        // 收集所有维度的总分和总数
        const tagDimStats = {};
        Object.values(tags[tag].taskStats).forEach(taskStats => {
            Object.entries(taskStats.dimensionAverages).forEach(([dimId, dimStats]) => {
                if (!tagDimStats[dimId]) {
                    tagDimStats[dimId] = { total: 0, count: 0 };
                }
                tagDimStats[dimId].total += dimStats.total;
                tagDimStats[dimId].count += dimStats.count;
            });
        });
        
        // 计算标签维度平均值
        Object.entries(tagDimStats).forEach(([dimId, dimStats]) => {
            tags[tag].dimensionAverages[dimId] = dimStats.count > 0 ? dimStats.total / dimStats.count : 0;
        });
    });
    
    return tags;
}
```

#### 7.4.3 数据展示

以交互式标签云和分组表格形式展示不同标签的评估维度平均值对比。

### 7.5 具体用例对比卡片

#### 7.5.1 数据来源

- **测试结果** - 从`test_result`表查询
- **测试用例** - 从`test_case`表查询，获取用例详细信息
- **音频信息** - 从`audio`表查询，获取音频文件信息

#### 7.5.2 数据计算

```javascript
// 计算用例的详细对比数据
function calculateTestCaseComparison(testCaseId, taskIds) {
    const results = queryResultsByTestCaseAndTaskIds(testCaseId, taskIds);
    
    return {
        testCaseId: testCaseId,
        testCaseName: results[0].case.name,
        results: results.map(result => {
            return {
                taskId: result.taskId,
                taskName: result.task.name,
                status: result.status,
                executionTime: result.executionTime,
                evaluationResults: result.evaluation_results,
                asrResult: result.asr_result,
                transResult: result.trans_result
            };
        })
    };
}
```

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

- **框架** - Flask + SQLite
- **RESTful API** - 提供RESTful API接口，支持前端数据访问
- **ORM** - 使用SQLAlchemy进行数据库操作
- **异步处理** - 耗时操作采用异步处理，提高系统响应速度

### 8.3 核心组件

| 组件名称 | 功能描述 | 实现文件 |
|---------|---------|---------|
| ReportHeaderComponent | 报告头部组件 | src/components/report/ReportHeader.vue |
| ComparisonTableComponent | 对比表格组件 | src/components/report/ComparisonTable.vue |
| ChartComponent | 图表展示组件 | src/components/report/Chart.vue |
| AnalysisEditorComponent | 分析结论编辑组件 | src/components/report/AnalysisEditor.vue |
| FilterComponent | 筛选组件 | src/components/common/Filter.vue |

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

系统采用了现代化的技术栈，包括Vue.js、Electron、Flask、SQLite等，实现了高性能、可扩展的报告功能。报告数据来自于系统中的测试任务和测试结果，通过复杂的数据查询和计算，生成直观、有用的报告内容。

报告功能的设计遵循了统一的设计规范，包括视觉设计、交互设计和技术实现规范，确保了报告的一致性和专业性。同时，系统还提供了丰富的编辑和导出功能，满足用户的不同需求。

通过报告功能，用户可以全面了解测试结果，对比不同任务的执行情况，分析系统性能趋势，为后续优化提供依据。