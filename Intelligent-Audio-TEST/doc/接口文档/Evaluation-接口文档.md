# Evaluation 接口文档

## 1. 文档概述

### 1.1 文档目的
本文档详细描述评估维度管理模块的API接口设计，包括API端点、请求参数、响应格式等，旨在为前后端开发人员提供清晰的API使用指南，确保API功能的完整性和一致性。

### 1.2 适用范围
- 前端开发人员
- 后端开发人员
- 测试人员

### 1.4 核心流程说明 (Evaluation Flow)
1.  **数据采集**：测试执行引擎完成放音与录音后，获取识别结果（ASR）与翻译结果（Translation）。
2.  **维度解析**：根据用例关联的维度，确定需要调用的评估 API 列表。
3.  **API 聚合**：评估引擎扫描所有待评估维度，将具有相同 `api_url` 的请求进行合并，减少冗余调用。
4.  **分值计算**：解析 API 响应，根据 `response_mapping` 提取目标值，并应用 `rule` 中的评分规则。
5.  **结果持久化**：将最终分值、原始值及错误信息写入 `test_result_dimensions`。

## 2. 认证与授权
- **认证方式**: JWT Token (可选)
- **授权范围**: 基于角色的访问控制 (RBAC)
- **API前缀**: `/api/v1`

## 3. 维度管理 API (evaluation)

### 3.1 获取维度列表

```
GET /api/v1/evaluation
```

**请求参数**:

| 参数名 | 类型 | 位置 | 必需 | 描述 |
|--------|------|------|------|------|
| page | INTEGER | query | 否 | 页码，默认1 |
| per_page | INTEGER | query | 否 | 每页记录数，默认10 |
| search | STRING | query | 否 | 搜索关键字 |
| category_id | INTEGER | query | 否 | 分类ID |

**响应示例**:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": 1,
        "name": "唤醒准确率",
        "description": "语音唤醒功能的准确率评估",
        "keywords": "唤醒,准确率",
        "category_id": 1,
        "api_url": "https://api.example.com/evaluation/wakeup",
        "api_endpoints": ["https://api.example.com/evaluation/wakeup"],
        "api_settings": {
          "method": "POST",
          "headers": {
            "Content-Type": "application/json"
          }
        },
        "api_status": "online",
        "score_unit": "%",
        "type": "性能指标",
        "result_type": 1,
        "result_min": 0,
        "result_max": 100,
        "decimal_places": 2,
        "weight": 8,
        "estimated_exec_time": 5,
        "rule": {
          "rules": [
            {"condition": ">=", "value": 95, "score": 10},
            {"condition": ">=", "value": 80, "score": 8},
            {"condition": "<", "value": 80, "score": 0}
          ]
        },
        "required_inputs": {},
        "status": true,
        "created_at": "2023-01-01T12:00:00Z",
        "updated_at": "2023-01-01T12:00:00Z"
      }
    ],
    "total": 100,
    "page": 1,
    "per_page": 10,
    "pages": 10
  }
}
```

### 3.2 获取维度详情

```
GET /api/v1/evaluation/:id
```

**响应示例**:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 1,
    "name": "唤醒准确率",
    "description": "语音唤醒功能的准确率评估",
    "keywords": "唤醒,准确率",
    "category_id": 1,
    "api_url": "https://api.example.com/evaluation/wakeup",
    "api_endpoints": ["https://api.example.com/evaluation/wakeup"],
    "api_settings": {
      "method": "POST",
      "headers": {
        "Content-Type": "application/json"
      }
    },
    "api_status": "online",
    "score_unit": "%",
    "type": "性能指标",
    "result_type": 1,
    "result_min": 0,
    "result_max": 100,
    "decimal_places": 2,
    "weight": 8,
    "estimated_exec_time": 5,
    "rule": {
      "rules": [
        {"condition": ">=", "value": 95, "score": 10},
        {"condition": ">=", "value": 80, "score": 8},
        {"condition": "<", "value": 80, "score": 0}
      ]
    },
    "required_inputs": {},
    "status": true,
    "created_at": "2023-01-01T12:00:00Z",
    "updated_at": "2023-01-01T12:00:00Z"
  }
}
```

### 3.3 新增维度

```
POST /api/v1/evaluation
```

**请求示例**:

```json
{
  "name": "新增维度",
  "description": "新的评估维度",
  "keywords": "评估,新维度",
  "category_id": 1,
  "api_url": "https://api.example.com/evaluation/new",
  "api_endpoints": ["https://api.example.com/evaluation/new"],
  "api_settings": {
    "method": "POST",
    "headers": {
      "Content-Type": "application/json"
    }
  },
  "score_unit": "%",
  "type": "性能指标",
  "result_type": 1,
  "result_min": 0,
  "result_max": 100,
  "decimal_places": 2,
  "weight": 5,
  "estimated_exec_time": 5,
  "rule": {
    "rules": [{"condition": ">=", "value": 90, "score": 10}]
  },
  "required_inputs": {},
  "status": true
}
```

**响应示例**:

```json
{
  "code": 0,
  "message": "Dimension created successfully",
  "data": {
    "id": 2
  }
}
```

### 3.4 更新维度

```
PUT /api/v1/evaluation/:id
```

**请求示例**:

```json
{
  "name": "更新后的维度名称",
  "weight": 9,
  "status": "inactive"
}
```

**响应示例**:

```json
{
  "code": 0,
  "message": "Dimension updated successfully"
}
```

### 3.5 删除维度 (逻辑删除)

```
DELETE /api/v1/evaluation/:id
```

**响应示例**:

```json
{
  "code": 0,
  "message": "Dimension deleted successfully"
}
```

### 3.6 测试API健康

```
POST /api/v1/evaluation/:id/health-check
```

**响应示例**:

```json
{
  "code": 0,
  "message": "健康探测完成",
  "data": {
    "results": [
      {
        "url": "https://api.example.com/evaluation/wakeup",
        "status": "online",
        "status_code": 200,
        "response_time": "120.50ms",
        "message": "健康探测完成"
      }
    ],
    "overall_status": "online"
  }
}
```

### 3.7 计算维度得分

```
POST /api/v1/evaluation/:id/calculate
```

**请求示例**:

```json
{
  "value": 95
}
```

**响应示例**:

```json
{
  "code": 0,
  "message": "分值计算完成",
  "data": {
    "score": 10.0
  }
}
```

### 3.8 批量操作维度

```
POST /api/v1/evaluation/batch-action
```

**请求示例**:

```json
{
  "ids": [1, 2, 3],
  "action": "delete"
}
```

**响应示例**:

```json
{
  "code": 0,
  "message": "批量操作 delete 执行成功"
}
```

### 3.9 导出维度

```
GET /api/v1/evaluation/export
```

**请求参数**:

| 参数名 | 类型 | 位置 | 必需 | 描述 |
|--------|------|------|------|------|
| format | STRING | query | 否 | 导出格式：json或excel，默认json |
| ids | STRING | query | 否 | 维度ID列表，逗号分隔 |

**响应示例**:

```json
{
  "code": 0,
  "message": "数据准备就绪",
  "data": [
    {
      "name": "唤醒准确率",
      "description": "语音唤醒功能的准确率评估",
      "category_id": 1,
      "type": "性能指标",
      "rule": {
        "rules": [
          {"condition": ">=", "value": 95, "score": 10},
          {"condition": ">=", "value": 80, "score": 8},
          {"condition": "<", "value": 80, "score": 0}
        ]
      },
      "api_url": "https://api.example.com/evaluation/wakeup",
      "api_settings": {
        "method": "POST",
        "headers": {
          "Content-Type": "application/json"
        }
      },
      "result_type": 1,
      "score_unit": "%",
      "status": true
    }
  ]
}
```

### 3.10 导入维度

```
POST /api/v1/evaluation/import
```

**请求参数**:

| 参数名 | 类型 | 位置 | 必需 | 描述 |
|--------|------|------|------|------|
| file | FILE | form | 是 | 导入文件，支持Excel或JSON格式 |
| update_existing | BOOLEAN | form | 否 | 是否更新已存在的维度，默认false |

**响应示例**:

```json
{
  "code": 0,
  "message": "导入成功: 新增 5 条, 更新 3 条",
  "data": {
    "imported": 5,
    "updated": 3
  }
}
```



## 5. 分类管理 API (categories)

### 5.1 获取分类列表

```
GET /api/v1/evaluation/categories
```

**响应示例**:

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "id": 1,
      "name": "性能指标",
      "desc": "评估系统性能的指标",
      "icon": "fas fa-tachometer-alt"
    }
  ]
}
```

### 5.2 新增分类

```
POST /api/v1/evaluation/categories
```

**请求示例**:

```json
{
  "name": "趋势指标",
  "desc": "评估系统趋势的指标",
  "icon": "fas fa-chart-line"
}
```

**响应示例**:

```json
{
  "code": 0,
  "message": "Category created successfully",
  "data": {
    "id": 2
  }
}
```

### 5.3 更新分类

```
PUT /api/v1/evaluation/categories/:id
```

**请求示例**:

```json
{
  "name": "更新后的分类名称",
  "desc": "更新后的分类描述"
}
```

**响应示例**:

```json
{
  "code": 0,
  "message": "Category updated successfully"
}
```

### 5.4 删除分类

```
DELETE /api/v1/evaluation/categories/:id
```

**响应示例**:

```json
{
  "code": 0,
  "message": "Category deleted successfully"
}
```

## 6. 响应码说明

| 响应码 | 描述 |
|--------|------|
| 200 | 请求成功 |
| 201 | 资源创建成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

## 7. 版本控制

| 版本 | 日期 | 作者 | 描述 |
|------|------|------|------|
| v1.0 | 2023-12-20 | 开发团队 | 初始版本 |
| v1.1 | 2023-12-25 | 开发团队 | 新增导入导出功能 |
| v1.2 | 2024-01-20 | 开发团队 | 新增API健康测试功能 |
| v1.3 | 2024-12-23 | 架构师 | 对齐实现文档：更新字段结构与评分引擎逻辑 |

