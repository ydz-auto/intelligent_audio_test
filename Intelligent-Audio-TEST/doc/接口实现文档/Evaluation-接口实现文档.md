
# 评估维度管理接口实现文档

## 1. 模块概述
评估维度管理模块定义了如何衡量测试结果的优劣。每个维度包含特定的评分规则（如：准确率 > 95% 得 10 分）和执行该评估的 API 链接。

## 2. 接口详细实现思路

### 2.1 维度与分类管理 (CRUD)
**实现思路：**
- **分类管理**：
  - **GET /api/v1/evaluation/categories**: 获取分类列表，返回所有分类信息，包含 `id`, `name`, `description`, `icon` 等字段。
  - **POST /api/v1/evaluation/categories**: 创建新分类，验证 `name` 必填，使用 `Category` 模型创建记录。
  - **PUT /api/v1/evaluation/categories/:cat_id**: 更新分类信息，根据 `cat_id` 查找分类，支持更新 `name`, `description`, `icon` 字段。
  - **DELETE /api/v1/evaluation/categories/:cat_id**: 删除分类，根据 `cat_id` 查找并删除分类记录。
- **维度管理**：
  - **GET /api/v1/evaluation/dimensions**: 查询 `dimensions` 表，支持按 `categoryId/category_id` 过滤，支持 `search` 关键词搜索（在 `name`, `description`, `keywords` 中模糊匹配），支持分页。
  - **POST /api/v1/evaluation/dimensions**: 创建维度，验证 `name` 必填，处理 `rule` (JSON) 和 `api_settings` (JSON) 字段，支持规则结构验证，支持前端 camelCase 到后端 snake_case 的字段映射。
  - **GET /api/v1/evaluation/dimensions/:id**: 获取单个维度详情，返回完整的维度信息。
  - **PUT /api/v1/evaluation/dimensions/:id**: 更新维度信息，支持更新 `name`, `description`, `category_id`, `api_url`, `api_settings`, `rule`, `status` 等字段，支持规则结构验证。
  - **DELETE /api/v1/evaluation/dimensions/:id**: 删除维度，逻辑删除（设置 `deleted=True`）。

### 2.2 评分规则引擎
**实现逻辑：**
评分逻辑在 `EvaluationController.calculate_score` 方法中实现：

1. **参数验证**：
   - 从请求中获取 `value` 参数（待评估的原始值）。
   - 验证 `rule` 配置是否存在且格式正确。

2. **规则匹配机制**：
   - 支持多种条件运算符：`>`, `>=`, `<`, `<=`, `==`, `!=`。
   - 遍历 `rule['rules']` 数组，按顺序匹配条件。
   - 匹配第一个符合条件的规则，返回对应的 `score`。

3. **类型转换**：
   - 将 `test_value` 转换为数值类型（float/int）以便比较。
   - 处理字符串类型的数值转换。

4. **结果返回**：
   - 返回匹配到的 `score` 值。
   - 若没有匹配的规则，返回默认 `score=0`。

### 2.3 API 接入与探测
**实现逻辑：**
1. **API 健康探测**：
   - **GET/POST /api/v1/evaluation/dimensions/:id/health**: 测试评估 API 是否可达并返回正确格式的数据。
   - **实现流程**：
     1. 根据 `dim_id` 查找维度，验证 API URL 是否配置。
     2. 从 `api_settings` 中获取 `method`, `headers`, `body_template` 等配置。
     3. 替换 `body_template` 中的占位符（如 `${test_value}`）为默认值。
     4. 发送 HTTP 请求，记录响应时间。
     5. 根据响应状态码更新维度的 `api_status`（online/offline）。
     6. 尝试验证 `response_mapping` 提取功能。
2. **评分计算**：
   - **POST /api/v1/evaluation/dimensions/:id/calculate**: 根据维度配置的评分规则计算分数。
   - **实现流程**：
     1. 根据 `dim_id` 查找维度配置。
     2. 接收待评估的值（`value` 参数）。
     3. 根据维度配置的评分规则（`rule` 字段）计算分数。
     4. 支持多种条件运算符：`>`, `>=`, `<`, `<=`, `==`, `!=`。
     5. 返回计算出的分数和原始值。
2. **API 配置支持**：
   - 支持配置 `method` (GET/POST)、`headers`、`body_template`、`response_mapping` 等。
   - `body_template` 支持使用 `${}` 占位符，在实际调用时动态替换。
3. **API 状态管理**：
   - 定期或手动触发健康检查，更新 API 状态。
   - API 状态用于评估任务调度，优先使用 `online` 状态的 API。

### 2.4 批量操作与导入导出
**实现思路：**
- **批量操作**：
  - **POST /api/v1/evaluation/dimensions/batch**: 支持批量删除、启用、禁用或导出维度。
  - **实现流程**：
    1. 从请求中获取 `ids/itemIds` 和 `action` 参数。
    2. 根据 `action` 参数执行不同操作：
       - `delete`: 设置维度的 `deleted=True`（逻辑删除）。
       - `enable`: 设置维度的 `status=True`。
       - `disable`: 设置维度的 `status=False`。
       - `export`: 返回维度配置数据。
    3. 执行数据库批量更新操作。
    4. 返回操作结果。

- **导入导出**：
  - **GET /api/v1/evaluation/dimensions/export**: 导出维度配置到文件。
  - **实现流程**：
    1. 支持 `json` 和 `excel` 两种格式。
    2. 根据 `ids` 参数筛选需要导出的维度。
    3. 使用 `pandas` 生成 Excel 文件或直接返回 JSON 数据。
    4. 返回文件流或 JSON 数据。
  
  - **POST /api/v1/evaluation/dimensions/import**: 从文件导入维度配置。
  - **实现流程**：
    1. 支持 Excel 和 JSON 格式文件。
    2. 读取文件内容，转换为 DataFrame。
    3. 遍历数据行，验证必填字段。
    4. 处理 `rule` 和 `api_settings` 字段的 JSON 解析。
    5. 支持更新现有维度（根据 `updateExisting` 参数）。
    6. 批量导入或更新维度数据。
    7. 返回导入和更新的数量。

### 2.6 评估执行引擎 (EvaluationEngine)
**实现思路：**
1.  **单例服务**：`EvaluationService` 作为单例运行，提供 `evaluate_result` 核心方法。
2.  **API 聚合优化**：
    -   **逻辑**：在一次评估任务中，如果多个维度指向同一个 `api_url`，引擎会将其聚合为一次 API 调用。
    -   **结果分发**：API 返回的结果会根据各维度的 `response_mapping` 进行提取。
3.  **多源数据提取**：
    -   支持从 `asr_result` (语音识别结果)、`translation_result` (翻译结果) 或 `result_data` (API 测试原始响应) 中提取评估输入值。
4.  **分值计算与存储**：
    -   计算出的分值和提取出的原始值一同存入 `test_result_dimensions` 表。
    -   支持异常处理，如果 API 调用失败或解析失败，记录错误信息并赋予默认分值（通常为 0）。

## 3. 评估执行引擎 (EvaluationEngine)
**实现思路：**
1.  **单例服务**：`EvaluationService` 作为单例运行，提供 `evaluate_result` 核心方法。
2.  **API 聚合优化**：
    -   **逻辑**：在一次评估任务中，如果多个维度指向同一个 `api_url`，引擎会将其聚合为一次 API 调用。
    -   **结果分发**：API 返回的结果会根据各维度的 `response_mapping` 进行提取。
3.  **多源数据提取**：
    -   支持从 `asr_result` (语音识别结果)、`translation_result` (翻译结果) 或 `result_data` (API 测试原始响应) 中提取评估输入值。
4.  **分值计算与存储**：
    -   计算出的分值和提取出的原始值一同存入 `test_result_dimensions` 表。
    -   支持异常处理，如果 API 调用失败或解析失败，记录错误信息并赋予默认分值（通常为 0）。

## 4. PostgreSql 存储规范

### 3.1 维度表 (`dimensions`)
| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | Integer | 主键，自增 |
| `name` | String | 维度名称 (如：WER, 翻译 BLEU) |
| `category_id` | Integer | 外键，关联 `categories.id` |
| `api_url` | String | 评估 API 地址 |
| `type` | String | 评分模式 (direct/linear/threshold) |
| `rule` | JSON | 评分规则配置 (如线性系数、阈值数组) |
| `api_settings`| JSON | API 调用配置 (headers, body_template, mapping) |

### 3.2 维度结果表 (`test_result_dimensions`)
| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `test_result_id` | Integer | 外键，关联 `test_results.id` |
| `dimension_id` | Integer | 外键，关联 `dimensions.id` |
| `dimension_value`| Float | 提取出的原始值 (如 0.95) |
| `score` | Float | 最终计算出的得分 (0-100) |
| `status` | String | 维度执行状态 (passed/failed) |

## 4. 技术规范

### 4.1 统一度量衡
为确保数据一致性，系统强制要求以下单位：
- **时间**：接口响应时间统一使用 `ms` (毫秒)；任务时长使用 `seconds` (秒)。
- **声压**：音频播放与校准统一使用 `dB SPL`。
- **频率**：音频采样率与测试频率统一使用 `Hz`。
- **文件大小**：存储容量统一使用 `bytes`。
- **得分**：所有维度的最终得分必须映射到 `[0, 100]` 区间。

### 4.2 错误码定义
系统使用 `ErrorCode` 枚举进行错误透传：
- `0`: `SUCCESS` - 操作成功
- `1xx`: 参数错误 (如 `100: INVALID_PARAMS`)
- `2xx`: 业务错误 (如 `220: TASK_EXECUTION_ERROR`)
- `3xx`: 系统错误 (如 `301: DATABASE_ERROR`)
