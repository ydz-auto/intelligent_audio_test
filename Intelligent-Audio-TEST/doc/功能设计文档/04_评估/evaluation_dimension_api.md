# 评估维度API接口文档

## 1. 概述

评估维度API用于管理和操作评估维度（Dimension），包括维度的创建、查询、更新、删除、健康检查、分值计算等功能。评估维度是定义质量评估指标、评分规则及计算API的核心实体。

## 2. 数据模型

### 2.1 评估维度模型 (Dimension)

| 字段名 | 类型 | 描述 | 示例值 |
|-------|------|------|--------|
| id | Integer | 维度唯一ID | 1 |
| name | String | 维度名称 | "准确率" |
| keywords | String | 搜索关键字 | "准确,精度" |
| description | Text | 维度详细描述 | "评估翻译结果的准确率" |
| category_id | Integer | 所属分类ID | 2 |
| type | String | 评估类型 (auto/manual) | "auto" |
| result_type | Integer | 结果数据类型 (1:数值, 2:布尔, 3:文本) | 1 |
| result_min | Float | 结果最小值限制 | 0 |
| result_max | Float | 结果最大值限制 | 100 |
| decimal_places | Integer | 数值保留小数位数 | 2 |
| weight | Integer | 维度权重 | 5 |
| estimated_exec_time | Integer | 预计执行时间 (秒) | 10 |
| rule | JSON | 评分规则配置 | `{"rules": [{"condition": ">=", "value": 95, "score": 10}]}` |
| api_settings | JSON | API调用详细设置 | `{"method": "POST", "headers": {"Content-Type": "application/json"}}` |
| status | Boolean | 是否启用标志 | true |
| deleted | Boolean | 逻辑删除标志 | false |
| created_at | DateTime | 创建时间 | "2023-01-01T00:00:00" |
| updated_at | DateTime | 更新时间 | "2023-01-01T00:00:00" |
| api_status | String | 算法API在线状态 | "online" |
| required_inputs | JSON | 计算指标所需的输入配置 | `["asr_result", "translation_result"]` |
| api_endpoints | JSON | 多个评估算法API地址及配置 | `[{"url": "http://example.com/api", "max_process": 5}]` |
| api_url | String | 评估微服务主入口URL | "http://example.com/api" |
| score_unit | String | 分数单位 | "%" |

### 2.2 分类模型 (Category)

| 字段名 | 类型 | 描述 | 示例值 |
|-------|------|------|--------|
| id | Integer | 分类唯一ID | 1 |
| name | String | 分类名称 | "翻译质量" |
| description | String | 分类描述 | "翻译质量评估维度" |
| icon | String | 分类图标 | "default-icon" |
| created_at | DateTime | 创建时间 | "2023-01-01T00:00:00" |
| updated_at | DateTime | 更新时间 | "2023-01-01T00:00:00" |

## 3. 接口列表

### 3.1 分类管理

| 接口名称 | URL | 方法 | 功能描述 |
|---------|-----|------|----------|
| 获取分类列表 | `/api/v1/evaluation/categories` | GET | 获取所有评估分类 |
| 创建分类 | `/api/v1/evaluation/categories` | POST | 创建新的评估分类 |
| 更新分类 | `/api/v1/evaluation/categories/{cat_id}` | PUT | 更新分类信息 |
| 删除分类 | `/api/v1/evaluation/categories/{cat_id}` | DELETE | 删除分类 |

### 3.2 维度管理

| 接口名称 | URL | 方法 | 功能描述 |
|---------|-----|------|----------|
| 获取维度列表 | `/api/v1/evaluation/dimensions` | GET | 获取评估维度列表，支持分页和搜索 |
| 创建维度 | `/api/v1/evaluation/dimensions` | POST | 创建新的评估维度 |
| 更新维度 | `/api/v1/evaluation/dimensions/{dim_id}` | PUT | 更新评估维度信息 |
| 删除维度 | `/api/v1/evaluation/dimensions/{dim_id}` | DELETE | 逻辑删除评估维度 |
| 健康检查 | `/api/v1/evaluation/dimensions/{dim_id}/health` | GET | 检查维度关联的API健康状态 |
| 计算分值 | `/api/v1/evaluation/dimensions/{dim_id}/calculate` | POST | 根据规则计算分值 |
| 批量操作 | `/api/v1/evaluation/dimensions/batch` | POST | 批量删除、启用或禁用维度 |
| 导出到文件 | `/api/v1/evaluation/dimensions/export-file` | GET | 导出维度配置到文件 |
| 从文件导入 | `/api/v1/evaluation/dimensions/import-file` | POST | 从文件导入维度配置 |

## 4. 接口详细说明

### 4.1 分类管理接口

#### 4.1.1 获取分类列表

**URL**: `/api/v1/evaluation/categories`
**方法**: GET
**响应示例**:
```json
{
  "success": true,
  "error": null,
  "data": {
    "items": [
      {
        "id": 1,
        "name": "翻译质量",
        "description": "翻译质量评估维度",
        "icon": "default-icon",
        "createdAt": "2023-01-01T00:00:00",
        "updatedAt": "2023-01-01T00:00:00"
      }
    ],
    "total": 1
  }
}
```

#### 4.1.2 创建分类

**URL**: `/api/v1/evaluation/categories`
**方法**: POST
**请求体**:
```json
{
  "name": "新分类",
  "description": "分类描述",
  "icon": "category-icon"
}
```
**响应示例**:
```json
{
  "success": true,
  "error": null,
  "data": {
    "id": 2
  },
  "message": "分类创建成功"
}
```

### 4.2 维度管理接口

#### 4.2.1 获取维度列表

**URL**: `/api/v1/evaluation/dimensions`
**方法**: GET
**查询参数**:
- `categoryId`: 分类ID（可选）
- `page`: 页码（默认1）
- `perPage`: 每页数量（默认10）
- `search`: 搜索关键词（可选）

**响应示例**:
```json
{
  "success": true,
  "error": null,
  "data": {
    "items": [
      {
        "id": 1,
        "name": "准确率",
        "description": "评估翻译结果的准确率",
        "keywords": "准确,精度",
        "categoryId": 1,
        "apiUrl": "http://example.com/api/accuracy",
        "apiEndpoints": [{"url": "http://example.com/api/accuracy", "maxProcess": 5}],
        "apiSettings": {"method": "POST"},
        "apiStatus": "online",
        "type": "auto",
        "resultType": 1,
        "resultMin": 0,
        "resultMax": 100,
        "decimalPlaces": 2,
        "weight": 5,
        "estimatedExecTime": 10,
        "rule": {"rules": [{"condition": ">=", "value": 95, "score": 10}]},
        "requiredInputs": ["asr_result", "translation_result"],
        "scoreUnit": "%",
        "status": true,
        "createdAt": "2023-01-01T00:00:00",
        "updatedAt": "2023-01-01T00:00:00"
      }
    ],
    "total": 1,
    "page": 1,
    "perPage": 10,
    "pages": 1
  }
}
```

#### 4.2.2 创建维度

**URL**: `/api/v1/evaluation/dimensions`
**方法**: POST
**请求体**:
```json
{
  "name": "新维度",
  "description": "维度描述",
  "keywords": "关键词1,关键词2",
  "categoryId": 1,
  "type": "auto",
  "resultType": 1,
  "resultMin": 0,
  "resultMax": 100,
  "decimalPlaces": 2,
  "weight": 5,
  "estimatedExecTime": 10,
  "rule": {"rules": [{"condition": ">=", "value": 95, "score": 10}]},
  "apiEndpoints": [{"url": "http://example.com/api/new", "maxProcess": 5}],
  "apiSettings": {"method": "POST", "headers": {"Content-Type": "application/json"}},
  "requiredInputs": ["asr_result", "translation_result"],
  "scoreUnit": "%",
  "status": true
}
```
**响应示例**:
```json
{
  "success": true,
  "error": null,
  "data": {
    "id": 2
  },
  "message": "评分维度创建成功"
}
```

#### 4.2.3 更新维度

**URL**: `/api/v1/evaluation/dimensions/{dim_id}`
**方法**: PUT
**请求体**:
```json
{
  "name": "更新后的维度名",
  "description": "更新后的描述",
  "status": false
}
```
**响应示例**:
```json
{
  "success": true,
  "error": null,
  "data": null,
  "message": "评分维度更新成功"
}
```

#### 4.2.4 删除维度

**URL**: `/api/v1/evaluation/dimensions/{dim_id}`
**方法**: DELETE
**响应示例**:
```json
{
  "success": true,
  "error": null,
  "data": null,
  "message": "评分维度已删除"
}
```

#### 4.2.5 健康检查

**URL**: `/api/v1/evaluation/dimensions/{dim_id}/health`
**方法**: GET
**响应示例**:
```json
{
  "success": true,
  "error": null,
  "data": {
    "results": [
      {
        "url": "http://example.com/api/accuracy",
        "status": "online",
        "statusCode": 200,
        "responseTime": "123.45ms",
        "message": "健康探测完成"
      }
    ],
    "overallStatus": "online"
  },
  "message": "健康探测完成"
}
```

#### 4.2.6 计算分值

**URL**: `/api/v1/evaluation/dimensions/{dim_id}/calculate`
**方法**: POST
**请求体**:
```json
{
  "value": 96.5
}
```
**响应示例**:
```json
{
  "success": true,
  "error": null,
  "data": {
    "score": 10
  },
  "message": "分值计算完成"
}
```

#### 4.2.7 批量操作

**URL**: `/api/v1/evaluation/dimensions/batch`
**方法**: POST
**请求体**:
```json
{
  "ids": [1, 2, 3],
  "action": "delete"
}
```
**支持的操作**:
- `delete`: 逻辑删除
- `enable`: 启用
- `disable`: 禁用
- `export`: 导出数据

**响应示例**:
```json
{
  "success": true,
  "error": null,
  "data": null,
  "message": "批量操作 delete 执行成功"
}
```

#### 4.2.8 导出到文件

**URL**: `/api/v1/evaluation/dimensions/export-file`
**方法**: GET
**查询参数**:
- `format`: 导出格式 (json/excel，默认 json)
- `ids`: 要导出的维度ID列表，逗号分隔（可选，默认全部）

**响应**: 文件下载

#### 4.2.9 从文件导入

**URL**: `/api/v1/evaluation/dimensions/import-file`
**方法**: POST
**Content-Type**: `multipart/form-data`
**参数**:
- `file`: 要导入的文件 (支持 Excel 和 JSON 格式)
- `updateExisting`: 是否更新现有维度 (true/false，默认 false)

**响应示例**:
```json
{
  "success": true,
  "error": null,
  "data": {
    "imported": 2,
    "updated": 1
  },
  "message": "导入成功: 新增 2 条, 更新 1 条"
}
```

## 5. 评分规则格式

评分规则采用 JSON 格式，用于定义维度的评分逻辑。规则格式如下：

```json
{
  "rules": [
    {
      "condition": ">=",
      "value": 95,
      "score": 10
    },
    {
      "condition": ">=",
      "value": 90,
      "score": 8
    },
    {
      "condition": ">=",
      "value": 80,
      "score": 6
    },
    {
      "condition": ">=",
      "value": 70,
      "score": 4
    },
    {
      "condition": ">=",
      "value": 60,
      "score": 2
    }
  ]
}
```

**规则说明**:
- 规则按顺序匹配，匹配到第一个符合条件的规则后停止
- 支持的比较条件：>, >=, <, <=, ==, !=
- 阈值和得分必须为数字类型
- 每条规则必须包含 `condition`、`value`、`score` 三个字段

## 6. API 配置格式

### 6.1 api_endpoints 格式

```json
[
  {
    "url": "http://example.com/api/accuracy",
    "maxProcess": 5
  }
]
```

### 6.2 api_settings 格式

```json
{
  "method": "POST",
  "headers": {
    "Content-Type": "application/json",
    "Authorization": "Bearer token"
  },
  "timeout": 30
}
```

## 7. 错误码说明

| 错误码 | HTTP状态码 | 描述 | 示例 |
|-------|-----------|------|------|
| PARAM_MISSING | 400 | 缺少必要参数 | "缺少名称(name)" |
| PARAM_INVALID | 400 | 参数格式无效 | "规则格式错误: 无效的 JSON 字符串" |
| NOT_FOUND | 404 | 资源不存在 | "未找到评分维度" |
| DATABASE_ERROR | 500 | 数据库操作失败 | "数据库错误" |

## 8. API调用示例

### 8.1 创建维度示例

```javascript
fetch('/api/v1/evaluation/dimensions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    name: '新维度',
    description: '维度描述',
    categoryId: 1,
    type: 'auto',
    resultType: 1,
    rule: {rules: [{condition: '>=', value: 95, score: 10}]},
    apiEndpoints: [{url: 'http://example.com/api', maxProcess: 5}],
    requiredInputs: ['asr_result', 'translation_result']
  }),
})
.then(response => response.json())
.then(data => console.log(data));
```

### 8.2 获取维度列表示例

```javascript
fetch('/api/v1/evaluation/dimensions?page=1&perPage=10&search=准确率')
.then(response => response.json())
.then(data => console.log(data));
```

### 8.3 健康检查示例

```javascript
fetch('/api/v1/evaluation/dimensions/1/health')
.then(response => response.json())
.then(data => console.log(data));
```

## 9. 最佳实践

1. **维度命名**: 使用清晰、简洁的名称，便于理解和搜索
2. **规则设计**: 设计合理的评分规则，确保评分结果的准确性和合理性
3. **API配置**: 确保API端点配置正确，包括URL、请求方法、headers等
4. **健康检查**: 定期对维度关联的API进行健康检查，确保评估服务的可靠性
5. **批量操作**: 对于大量维度的操作，优先使用批量操作接口，提高效率
6. **导入导出**: 利用导入导出功能，方便维度配置的备份和迁移

## 10. 注意事项

1. 所有API请求必须使用正确的HTTP方法
2. 所有JSON请求必须设置正确的Content-Type头
3. 分页查询时，注意page和perPage参数的合理设置
4. 删除操作是逻辑删除，不会物理删除数据
5. 导入操作时，注意文件格式和数据完整性
6. 健康检查可能会产生实际的API请求，请合理使用
7. 响应数据统一使用 camelCase 格式
8. 请求数据支持 camelCase 和 snake_case 两种格式

## 11. 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| 1.0 | 2023-01-01 | 初始版本 |
| 1.1 | 2023-02-15 | 新增批量操作功能 |
| 1.2 | 2023-03-30 | 新增导入导出功能 |
| 1.3 | 2023-05-20 | 优化健康检查机制 |
| 1.4 | 2024-08-01 | 添加 api_endpoints 多端点支持 |
| 1.5 | 2024-12-01 | 添加 score_unit 字段，优化规则验证 |
