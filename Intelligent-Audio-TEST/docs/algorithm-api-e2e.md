# 算法配置模块 - 端到端接口文档

> 本文档基于前后端源码自动生成，覆盖"新建算法"和"参数配置"的完整端到端数据流。

---

## 目录

1. [总览](#1-总览)
2. [端到端流程图](#2-端到端流程图)
3. [接口清单](#3-接口清单)
   - [3.1 新建算法定义](#31-新建算法定义)
   - [3.2 获取算法详情](#32-获取算法详情)
   - [3.3 更新算法定义](#33-更新算法定义)
   - [3.4 删除算法定义](#34-删除算法定义)
   - [3.5 获取算法列表](#35-获取算法列表)
   - [3.6 新建设备/API参数](#36-新建设备api参数)
   - [3.7 更新设备/API参数](#37-更新设备api参数)
   - [3.8 删除设备/API参数](#38-删除设备api参数)
   - [3.9 新建用例参数](#39-新建用例参数)
   - [3.10 更新用例参数](#310-更新用例参数)
   - [3.11 删除用例参数](#311-删除用例参数)
   - [3.12 新建参考参数](#312-新建参考参数)
   - [3.13 更新参考参数](#313-更新参考参数)
   - [3.14 删除参考参数](#314-删除参考参数)
   - [3.15 新建参数映射](#315-新建参数映射)
   - [3.16 更新参数映射](#316-更新参数映射)
   - [3.17 删除参数映射](#317-删除参数映射)
   - [3.18 新建维度关联](#318-新建维度关联)
   - [3.19 获取算法关联维度](#319-获取算法关联维度)
   - [3.20 批量关联维度](#320-批量关联维度)
   - [3.21 获取分组列表](#321-获取分组列表)
   - [3.22 获取选项来源](#322-获取选项来源)
4. [数据模型总览](#4-数据模型总览)
5. [前端表单字段定义](#5-前端表单字段定义)
6. [端到端测试用例](#6-端到端测试用例)

---

## 1. 总览

### 1.1 API 基础路径

```
http://localhost:5000/api/v1/algorithm
```

所有接口均注册在 `algorithm_bp` 蓝图下，URL 前缀为 `/api/v1/algorithm`。

### 1.2 统一响应格式

所有接口返回 JSON，外层结构固定为：

**成功响应：**

```json
{
  "success": true,
  "code": 200,
  "message": "Success",
  "data": { ... }
}
```

**错误响应：**

```json
{
  "success": false,
  "code": 400,
  "message": "错误描述",
  "detail": null
}
```

> **重要**：`data` 内的所有 `snake_case` 键名会被自动转换为 `camelCase`。例如 `algorithm_type` → `algorithmType`，`ui_order` → `uiOrder`。前端对接时使用 camelCase 键名。

### 1.3 前端两种调用方式

项目中存在两套 API 调用方式：

| 方式 | 使用位置 | 特点 |
|------|----------|------|
| `algorithmApi`（推荐） | `AlgorithmConfigModal.vue` | 通过 `request()` 封装，自动解包 `data.data`，支持 Electron IPC |
| 原生 `fetch` | `AlgorithmConfigPage.vue`、`useAlgorithmConfig.ts` | 手动检查 `result.success`，手动取 `result.data` |

**`algorithmApi` 调用示例：**

```typescript
import { algorithmApi } from '@/utils/api'

// 自动解包，返回的已经是 data 字段内容
const result = await algorithmApi.createDefinition(bodyData)
console.log(result.id)  // 直接访问返回对象
```

**原生 `fetch` 调用示例：**

```typescript
const response = await fetch('/api/v1/algorithm/definitions')
const result = await response.json()
if (result.success) {
  console.log(result.data)  // 需手动取 data
}
```

### 1.4 响应解包机制

`algorithmApi` 通过 `request()` 函数（`api.ts` 第 165-309 行）处理响应：

1. **Electron IPC 模式**：检查 `result.code` 为 0/200/201 时返回 `result.data`
2. **Fetch 模式**：检查 `result.code` 或 `result.success`，成功时返回 `result.data`

---

## 2. 端到端流程图

### 2.1 新建算法完整流程

```
用户点击"新建算法"按钮
  │
  ▼
AlgorithmConfigPage.vue handleCreate()
  │  设置 modalMode='create', currentAlgorithm=null, modalVisible=true
  │
  ▼
AlgorithmConfigModal.vue 打开 (mode='create')
  │
  ├──▶ GET /algorithm/groups              → 加载分组下拉
  ├──▶ GET /algorithm/options-sources     → 加载选项来源下拉
  └──▶ (composable) GET /evaluation/...   → 加载评估维度下拉
  │
  ▼
用户填写表单（5 个 Tab）
  │
  ├── 基本信息 Tab：type, name, group_id, status, description, display_order
  ├── 参数配置 Tab：device_params, api_params, case_params（失焦自动保存）
  ├── 参考参数 Tab：reference_params（失焦自动保存）
  ├── 参数映射 Tab：mappings（随主表单提交）
  └── 关联维度 Tab：associated_dimensions（create 模式下随主表单提交）
  │
  ▼
用户点击"确定" → handleOk()
  │  校验 type/name/group_id 必填
  │
  ▼
saveAlgorithm()
  │  组装 bodyData（含所有子配置）
  │
  ▼
POST /api/v1/algorithm/definitions
  │
  ├── 成功 → emit('success') → 父组件 loadAlgorithms() 刷新列表
  └── 失败 → console.error（无用户提示）
```

### 2.2 参数自动保存流程

```
用户编辑参数字段 → 失焦(blur)事件
  │
  ▼
handleParamBlur() / handleCaseParamBlur() / handleReferenceParamBlur()
  │  debounce 1000~1500ms
  │
  ▼
autoSaveParams() / autoSaveCaseParams() / autoSaveReferenceParams()
  │
  ├── 参数有 id → PUT /algorithm/params/{param_id}     （更新）
  ├── 参数无 id → POST /algorithm/params               （创建）
  └── 失败 → console.error
  │
  ▼
响应处理：param.id = result.id（保存返回的 ID 供后续更新）
```

> **注意**：自动保存仅检查 `formState.type` 非空，不检查算法是否已在后端创建。在 create 模式下，用户填写 type 后编辑参数，会尝试向尚未创建的算法创建参数，可能导致后端外键约束错误。

---

## 3. 接口清单

### 3.1 新建算法定义

创建一条算法定义，可在同一请求中批量创建关联的设备参数、API参数、用例参数、映射和维度关联。

**请求**

```
POST /api/v1/algorithm/definitions
Content-Type: application/json
```

**请求参数**

| 字段 | camelCase | 类型 | 必填 | 默认值 | 可选值 | 中文含义 |
|------|-----------|------|------|--------|--------|----------|
| `type` | `type` | string | 是 | - | min 1~50 字符 | 算法类型代码（唯一标识，如 `translation`） |
| `name` | `name` | string | 是 | - | min 1~100 字符 | 算法显示名称（如"翻译"） |
| `group_id` | `groupId` | integer | 否 | null | - | 所属分组 ID |
| `description` | `description` | string | 否 | null | - | 算法描述 |
| `status` | `status` | string | 否 | `online` | `online`/`offline` | 状态 |
| `icon` | `icon` | string | 否 | null | max 200 字符 | 图标 URL |
| `display_order` | `displayOrder` | integer | 否 | 0 | >= 0 | 排序权重 |
| `device_params` | `deviceParams` | array | 否 | null | 见 [3.6](#36-新建设备api参数) | 设备参数列表 |
| `api_params` | `apiParams` | array | 否 | null | 见 [3.6](#36-新建设备api参数) | API 参数列表 |
| `case_params` | `caseParams` | array | 否 | null | 见 [3.9](#39-新建用例参数) | 用例参数列表 |
| `mappings` | `mappings` | object | 否 | null | 见 [3.15](#315-新建参数映射) | 参数映射 `{device:[], api:[], evaluation:[]}` |
| `associated_dimensions` | `associatedDimensions` | array | 否 | null | 见 [3.18](#318-新建维度关联) | 关联评估维度 |
| `reference_params` | `referenceParams` | array | 否 | null | 见 [3.12](#312-新建参考参数) | 参考参数（**注意：控制器未处理，需单独创建**） |

**请求示例**

```json
{
  "type": "translation",
  "name": "翻译算法",
  "groupId": 1,
  "description": "语音翻译算法",
  "status": "online",
  "displayOrder": 10,
  "deviceParams": [
    {
      "paramCode": "audio_input",
      "paramName": "音频输入",
      "paramType": "audio_stream",
      "direction": "input",
      "required": true
    }
  ],
  "apiParams": [
    {
      "paramCode": "text_output",
      "paramName": "文本输出",
      "paramType": "text",
      "direction": "output",
      "required": true
    }
  ],
  "caseParams": [
    {
      "paramCode": "translation_direction",
      "paramName": "翻译方向",
      "paramType": "select",
      "scope": "common",
      "optionsSource": "translation_directions",
      "required": true
    }
  ],
  "mappings": {
    "device": [
      {
        "source": "case",
        "sourceParam": "audio_input",
        "sourceDirection": "input",
        "targetParam": "audio_input",
        "transformType": "none"
      }
    ],
    "api": [],
    "evaluation": []
  },
  "associatedDimensions": [
    {
      "dimensionId": 1,
      "weight": 1.0,
      "isDefault": true
    }
  ]
}
```

**响应**

```json
{
  "success": true,
  "code": 200,
  "message": "Algorithm created",
  "data": {
    "id": 100,
    "type": "translation",
    "name": "翻译算法",
    "groupId": 1,
    "groupName": "语音处理",
    "description": "语音翻译算法",
    "status": "online",
    "icon": null,
    "displayOrder": 10,
    "deviceParams": [...],
    "apiParams": [...],
    "caseParams": [...],
    "mappings": {...},
    "associatedDimensions": [...],
    "referenceParams": [],
    "createdAt": "2026-07-01T10:00:00",
    "updatedAt": "2026-07-01T10:00:00"
  }
}
```

**前端调用**

```typescript
// AlgorithmConfigModal.vue → saveAlgorithm()
import { algorithmApi } from '@/utils/api'

const bodyData = {
  type: formState.value.type,
  name: formState.value.name,
  group_id: formState.value.group_id,
  description: formState.value.description,
  status: formState.value.statusSwitch ? 'online' : 'offline',
  icon: formState.value.icon || '',
  display_order: formState.value.display_order || 0,
  device_params: formState.value.device_params,
  api_params: formState.value.api_params,
  case_params: formState.value.case_params,
  mappings: formState.value.mappings,
  associated_dimensions: formState.value.associated_dimensions,
  reference_params: formState.value.reference_params
}

const result = await algorithmApi.createDefinition(bodyData)
// result 已解包，直接使用 result.id
```

**注意事项**
- `type` 必须唯一，已存在则返回错误 `Algorithm '{type}' already exists`
- `name` 为空时回退使用 `type` 值
- `reference_params` 虽在 Schema 中定义，但控制器代码未处理，需通过 `POST /reference-params` 单独创建
- 子参数（device_params 等）中的 `id` 字段：提供则更新，不提供则创建

---

### 3.2 获取算法详情

**请求**

```
GET /api/v1/algorithm/definitions/{algo_type}
```

**Path 参数**

| 参数 | 类型 | 必填 | 中文含义 |
|------|------|------|----------|
| `algo_type` | string | 是 | 算法类型代码 |

**响应字段**

| 字段 | camelCase | 类型 | 中文含义 |
|------|-----------|------|----------|
| `id` | `id` | integer | 算法 ID |
| `type` | `type` | string | 算法类型代码 |
| `name` | `name` | string | 算法名称 |
| `group_id` | `groupId` | integer/null | 分组 ID |
| `group_name` | `groupName` | string/null | 分组名称 |
| `description` | `description` | string/null | 描述 |
| `status` | `status` | string | 状态 |
| `icon` | `icon` | string/null | 图标 URL |
| `display_order` | `displayOrder` | integer | 排序权重 |
| `device_params` | `deviceParams` | array | 设备参数列表 |
| `api_params` | `apiParams` | array | API 参数列表 |
| `case_params` | `caseParams` | array | 用例参数列表 |
| `mappings` | `mappings` | object | 参数映射 |
| `associated_dimensions` | `associatedDimensions` | array | 关联维度 |
| `reference_params` | `referenceParams` | array | 参考参数 |
| `created_at` | `createdAt` | datetime | 创建时间 |
| `updated_at` | `updatedAt` | datetime | 更新时间 |

**前端调用**

```typescript
const result = await algorithmApi.getDefinition('translation')
// 或原生 fetch：
const res = await fetch('/api/v1/algorithm/definitions/translation')
const result = await res.json()
const data = result.data
```

---

### 3.3 更新算法定义

**请求**

```
PUT /api/v1/algorithm/definitions/{algo_type}
```

**请求参数**（所有字段可选，仅传入的字段会被更新）

| 字段 | camelCase | 类型 | 必填 | 中文含义 |
|------|-----------|------|------|----------|
| `name` | `name` | string | 否 | 算法名称 |
| `group_id` | `groupId` | integer | 否 | 分组 ID |
| `description` | `description` | string | 否 | 描述 |
| `status` | `status` | string | 否 | 状态 |
| `icon` | `icon` | string | 否 | 图标 URL |
| `display_order` | `displayOrder` | integer | 否 | 排序权重 |
| `device_params` | `deviceParams` | array | 否 | 设备参数（**全量覆盖**） |
| `api_params` | `apiParams` | array | 否 | API 参数（**全量覆盖**） |
| `case_params` | `caseParams` | array | 否 | 用例参数（**全量覆盖**） |
| `mappings` | `mappings` | object | 否 | 参数映射（**全量覆盖**） |
| `associated_dimensions` | `associatedDimensions` | array | 否 | 关联维度（**全量覆盖**） |

> **重要**：子配置（device_params 等）为**全量覆盖**语义——未在提交列表中出现的已有记录会被软删除。

**前端调用**

```typescript
const result = await algorithmApi.updateDefinition('translation', bodyData)
```

---

### 3.4 删除算法定义

**请求**

```
DELETE /api/v1/algorithm/definitions/{algo_type}
```

**前端调用**

```typescript
await algorithmApi.deleteDefinition('translation')
```

> 软删除，设置 `deleted=true`。

---

### 3.5 获取算法列表

**请求**

```
GET /api/v1/algorithm/definitions?status={status}&group_id={group_id}
```

**Query 参数**

| 参数 | 类型 | 必填 | 中文含义 |
|------|------|------|----------|
| `status` | string | 否 | 按状态过滤（online/offline） |
| `group_id` | integer | 否 | 按分组过滤 |

**前端调用**

```typescript
const result = await algorithmApi.getDefinitions({ status: 'online' })
// result.data = 算法数组, result.total = 总数
```

---

### 3.6 新建设备/API参数

通过 `param_type_source` 字段区分创建设备参数还是 API 参数。

**请求**

```
POST /api/v1/algorithm/params
```

**请求参数**

| 字段 | camelCase | 类型 | 必填 | 默认值 | 可选值 | 中文含义 |
|------|-----------|------|------|--------|--------|----------|
| `param_type_source` | `paramTypeSource` | string | 否 | `device` | `device`/`api` | 参数来源类型 |
| `algorithm_type` | `algorithmType` | string | 是 | - | - | 关联算法类型 |
| `param_code` | `paramCode` | string | 是 | - | 1~50 字符 | 参数代码 |
| `param_name` | `paramName` | string | 否 | null | max 100 | 参数显示名称 |
| `label` | `label` | string | 否 | null | max 100 | 字段显示名称 |
| `param_type` | `paramType` | string | 是 | - | 见下表 | 参数类型 |
| `direction` | `direction` | string | 否 | `input` | `input`/`output` | 方向 |
| `required` | `required` | boolean | 否 | false | - | 是否必填 |
| `default_value` | `defaultValue` | string | 否 | null | - | 默认值 |
| `validation_rules` | `validationRules` | string | 否 | null | - | 验证规则 |
| `help_text` | `helpText` | string | 否 | null | - | 帮助提示 |
| `ui_order` | `uiOrder` | integer | 否 | 0 | >= 0 | 界面排序 |
| `hidden` | `hidden` | boolean | 否 | false | - | 是否隐藏 |

**`param_type` 可选值**

| 值 | 中文含义 |
|----|----------|
| `text` | 文本 |
| `audio_stream` | 音频流 |
| `audio_file` | 音频文件 |
| `text_file` | 文本文件 |
| `rttm` | RTTM 标注 |
| `stm` | STM 标注 |
| `json` | JSON 结构化 |

**请求示例**

```json
{
  "paramTypeSource": "device",
  "algorithmType": "translation",
  "paramCode": "audio_input",
  "paramName": "音频输入",
  "paramType": "audio_stream",
  "direction": "input",
  "required": true,
  "uiOrder": 1
}
```

**响应**

```json
{
  "success": true,
  "code": 200,
  "message": "Parameter created",
  "data": {
    "id": 501,
    "algorithmType": "translation",
    "paramCode": "audio_input",
    "paramName": "音频输入",
    "paramType": "audio_stream",
    "direction": "input",
    "required": true,
    "defaultValue": null,
    "validation": null,
    "helpText": null,
    "uiOrder": 1,
    "hidden": false
  }
}
```

**前端调用**

```typescript
// AlgorithmConfigModal.vue → autoSaveParams()
const bodyData = {
  algorithm_type: formState.value.type,
  param_type_source: paramType,  // 'device' 或 'api'
  param_code: param.param_code,
  param_name: param.param_name,
  param_type: param.param_type,
  direction: param.direction,
  required: param.required,
  default_value: param.default_value || '',
  validation_rules: param.validation_rules || '',
  help_text: param.help_text || '',
  ui_order: index,
  hidden: param.hidden || false
}

if (param.id) {
  // 更新
  await algorithmApi.updateParam(param.id, bodyData)
} else {
  // 创建
  const result = await algorithmApi.createParam(bodyData)
  param.id = result.id  // 保存返回的 ID
}
```

**注意事项**
- 唯一约束：`(algorithm_type, param_code, direction)` 三字段组合唯一
- 同一 param_code 可同时存在 input 和 output 两条记录

---

### 3.7 更新设备/API参数

**请求**

```
PUT /api/v1/algorithm/params/{param_id}
```

**请求参数**（全部可选，仅传入的非 null 字段会被更新）

| 字段 | camelCase | 类型 | 必填 | 中文含义 |
|------|-----------|------|------|----------|
| `param_code` | `paramCode` | string | 否 | 参数代码 |
| `param_name` | `paramName` | string | 否 | 参数名称 |
| `label` | `label` | string | 否 | 字段显示名称 |
| `param_type` | `paramType` | string | 否 | 参数类型 |
| `direction` | `direction` | string | 否 | 方向 |
| `required` | `required` | boolean | 否 | 是否必填 |
| `default_value` | `defaultValue` | string | 否 | 默认值 |
| `validation_rules` | `validationRules` | string | 否 | 验证规则 |
| `help_text` | `helpText` | string | 否 | 帮助提示 |
| `ui_order` | `uiOrder` | integer | 否 | 界面排序 |
| `hidden` | `hidden` | boolean | 否 | 是否隐藏 |

> 逻辑：先查 `AlgorithmDeviceParam`，找不到再查 `AlgorithmApiParam`。

---

### 3.8 删除设备/API参数

**请求**

```
DELETE /api/v1/algorithm/params/{param_id}
```

**前端调用**

```typescript
await algorithmApi.deleteParam(param.id)
// 乐观更新：先从本地数组移除，失败则恢复
```

---

### 3.9 新建用例参数

**请求**

```
POST /api/v1/algorithm/case-params
```

**请求参数**

| 字段 | camelCase | 类型 | 必填 | 默认值 | 可选值 | 中文含义 |
|------|-----------|------|------|--------|--------|----------|
| `algorithm_type` | `algorithmType` | string | 是 | - | - | 关联算法类型 |
| `param_code` | `paramCode` | string | 是 | - | 1~50 字符 | 参数代码 |
| `param_name` | `paramName` | string | 否 | null | max 100 | 参数名称 |
| `label` | `label` | string | 否 | null | max 100 | 字段显示名称 |
| `param_type` | `paramType` | string | 否 | `text` | 见下表 | 参数类型 |
| `required` | `required` | boolean | 否 | false | - | 是否必填 |
| `default_value` | `defaultValue` | string | 否 | null | - | 默认值 |
| `options_source` | `optionsSource` | string | 否 | null | - | 选项来源 |
| `options_field` | `optionsField` | string | 否 | null | - | 选项值字段 |
| `options_label_field` | `optionsLabelField` | string | 否 | null | - | 选项显示字段 |
| `help_text` | `helpText` | string | 否 | null | - | 帮助提示 |
| `ui_order` | `uiOrder` | integer | 否 | 0 | >= 0 | 界面排序 |
| `hidden` | `hidden` | boolean | 否 | false | - | 是否隐藏 |
| `scope` | `scope` | string | 否 | `common` | `common`/`api`/`e2e` | 适用范围 |
| `min_value` | `minValue` | float | 否 | null | - | 最小值（slider/number） |
| `max_value` | `maxValue` | float | 否 | null | - | 最大值（slider/number） |
| `step` | `step` | float | 否 | null | - | 步长（slider/number） |
| `unit` | `unit` | string | 否 | null | max 20 | 单位显示 |

**`param_type` 可选值**

| 值 | 中文含义 |
|----|----------|
| `text` | 文本输入 |
| `number` | 数字输入 |
| `textarea` | 多行文本 |
| `select` | 下拉选择 |
| `slider` | 滑块 |
| `switch` | 开关 |

**`scope` 可选值**

| 值 | 中文含义 |
|----|----------|
| `common` | 通用（API 和 E2E 测试均适用） |
| `api` | 仅 API 测试 |
| `e2e` | 仅 E2E 测试 |

**请求示例**

```json
{
  "algorithmType": "translation",
  "paramCode": "translation_direction",
  "paramName": "翻译方向",
  "paramType": "select",
  "scope": "common",
  "optionsSource": "translation_directions",
  "required": true,
  "uiOrder": 1
}
```

**前端调用**

```typescript
// AlgorithmConfigModal.vue → autoSaveCaseParams()
const bodyData = {
  algorithm_type: formState.value.type,
  param_code: param.param_code,
  param_name: param.param_name,
  param_type: param.param_type,
  required: param.required,
  default_value: param.default_value || '',
  help_text: param.help_text || '',
  component: paramTypeToComponent(param.param_type),  // 映射为 UI 组件类型
  ui_order: index,
  hidden: param.hidden || false,
  scope: param.scope || 'common',
  min_value: param.min_value ?? null,
  max_value: param.max_value ?? null,
  step: param.step ?? null,
  unit: param.unit || '',
  options_source: param.options_source || null,
  options_field: param.options_field || null,
  options_label_field: param.options_label_field || null
}

if (param.id) {
  await algorithmApi.updateCaseParam(param.id, bodyData)
} else {
  const result = await algorithmApi.createCaseParam(bodyData)
  param.id = result.id
}
```

**注意事项**
- 唯一约束：`(algorithm_type, param_code)` 二字段组合唯一
- `scope` 非法值会被回退为 `common`

---

### 3.10 更新用例参数

**请求**

```
PUT /api/v1/algorithm/case-params/{param_id}
```

**请求参数**（全部可选）

与 [3.9 新建用例参数](#39-新建用例参数) 字段一致，但 `algorithm_type` 和 `param_code` 不需要。

> 更新逻辑：检查字段是否在原始 JSON 中存在（支持 snake_case 和 camelCase 两种键名），存在即更新。

---

### 3.11 删除用例参数

**请求**

```
DELETE /api/v1/algorithm/case-params/{param_id}
```

---

### 3.12 新建参考参数

**请求**

```
POST /api/v1/algorithm/reference-params
```

**请求参数**

| 字段 | camelCase | 类型 | 必填 | 默认值 | 可选值 | 中文含义 |
|------|-----------|------|------|--------|--------|----------|
| `algorithm_type` | `algorithmType` | string | 是 | - | - | 关联算法类型 |
| `code` | `code` | string | 是 | - | - | 参数代码 |
| `name` | `name` | string | 否 | `''` | - | 参数名称 |
| `type` | `type` | string | 否 | `text` | `text`/`audio`/`json`/`rttm`/`stm` | 参考类型 |
| `annotation_code` | `annotationCode` | string | 否 | null | - | 关联标注代码 |
| `annotation_format` | `annotationFormat` | string | 否 | null | `text`/`json`/`rttm`/`stm` | 标注格式 |
| `field_path` | `fieldPath` | string | 否 | null | 如 `segments[].emotion` | 字段路径 |
| `merge_mode` | `mergeMode` | string | 否 | `join` | `join`/`collect`/`first` | 合并方式 |
| `help_text` | `helpText` | string | 否 | `''` | - | 帮助提示 |

**`merge_mode` 可选值**

| 值 | 中文含义 |
|----|----------|
| `join` | 拼接多个值 |
| `collect` | 收集为数组 |
| `first` | 取第一个值 |

**请求示例**

```json
{
  "algorithmType": "translation",
  "code": "asr_reference_text",
  "name": "ASR参考文本",
  "type": "text",
  "annotationCode": "asr_annotation",
  "annotationFormat": "text",
  "fieldPath": "text",
  "mergeMode": "join",
  "helpText": "ASR识别的参考文本"
}
```

**前端调用**

```typescript
// AlgorithmConfigModal.vue → autoSaveReferenceParams()
const bodyData = {
  code: param.code,
  name: param.name,
  type: param.type,
  annotation_code: param.annotation_code || param.code,  // 为空时自动同步为 code
  annotation_format: param.annotation_format || null,
  field_path: param.field_path || null,
  merge_mode: param.merge_mode || 'join',
  help_text: param.help_text || ''
}

if (param.id) {
  await algorithmApi.updateReferenceParam(param.id, formState.value.type, bodyData)
} else {
  const result = await algorithmApi.createReferenceParam({
    ...bodyData,
    algorithm_type: formState.value.type
  })
  param.id = result.id
}
```

**注意事项**
- 唯一约束：`(algorithm_type, code)` 二字段组合唯一
- `annotation_code` 为空时前端自动同步为 `code` 值

---

### 3.13 更新参考参数

**请求**

```
PUT /api/v1/algorithm/reference-params/{param_id}
```

**请求参数**（全部可选）

| 字段 | camelCase | 类型 | 必填 | 中文含义 |
|------|-----------|------|------|----------|
| `algorithm_type` | `algorithmType` | string | 否 | 关联算法类型 |
| `code` | `code` | string | 否 | 参数代码 |
| `name` | `name` | string | 否 | 参数名称 |
| `type` | `type` | string | 否 | 参考类型 |
| `annotation_code` | `annotationCode` | string | 否 | 标注代码 |
| `annotation_format` | `annotationFormat` | string | 否 | 标注格式 |
| `field_path` | `fieldPath` | string | 否 | 字段路径 |
| `merge_mode` | `mergeMode` | string | 否 | 合并方式 |
| `help_text` | `helpText` | string | 否 | 帮助提示 |

> `code` 和 `type` 使用真值判断（空字符串不更新）；其余用 `is not None` 判断。

---

### 3.14 删除参考参数

**请求**

```
DELETE /api/v1/algorithm/reference-params/{param_id}?algorithm_type={algo_type}
```

**Query 参数**

| 参数 | 类型 | 必填 | 中文含义 |
|------|------|------|----------|
| `algorithm_type` | string | 是 | 关联算法类型 |

**前端调用**

```typescript
await algorithmApi.deleteReferenceParam(param.id, formState.value.type)
```

---

### 3.15 新建参数映射

**请求**

```
POST /api/v1/algorithm/mappings
```

**请求参数**

| 字段 | camelCase | 类型 | 必填 | 默认值 | 可选值 | 中文含义 |
|------|-----------|------|------|--------|--------|----------|
| `algorithm_type` | `algorithmType` | string | 是 | - | - | 关联算法类型 |
| `source_type` | `sourceType` | string | 是 | - | `device`/`api`/`case`/`reference` | 源类型 |
| `source_param` | `sourceParam` | string | 是 | - | - | 源参数代码 |
| `source_direction` | `sourceDirection` | string | 否 | `output` | `input`/`output` | 源参数方向 |
| `dimension_id` | `dimensionId` | integer | 否 | null | - | 目标评估维度 ID |
| `target_param` | `targetParam` | string | 是 | - | - | 目标参数代码 |
| `transform_type` | `transformType` | string | 否 | `none` | 见下表 | 转换类型 |

**`transform_type` 可选值**

| 值 | 中文含义 |
|----|----------|
| `none` | 不转换 |
| `uppercase` | 转大写 |
| `lowercase` | 转小写 |
| `json_parse` | JSON 解析 |
| `base64` | Base64 编解码 |

**`source_type` 可选值**

| 值 | 中文含义 | 说明 |
|----|----------|------|
| `case` | 用例参数 | 从用例配置中取值 |
| `reference` | 参考参数 | 从参考标注中取值 |
| `device` | 设备参数 | 从设备输出中取值 |
| `api` | API 参数 | 从 API 输出中取值 |

**请求示例**

```json
{
  "algorithmType": "translation",
  "sourceType": "case",
  "sourceParam": "translation_direction",
  "sourceDirection": "input",
  "targetParam": "direction",
  "transformType": "none"
}
```

**响应**

```json
{
  "success": true,
  "code": 200,
  "message": "Mapping created",
  "data": {
    "id": 801,
    "algorithmType": "translation",
    "source": "case",
    "sourceParam": "translation_direction",
    "sourceDirection": "input",
    "dimensionId": null,
    "dimensionName": null,
    "targetParam": "direction",
    "transformType": "none"
  }
}
```

> **注意**：请求中为 `source_type`，响应中为 `source`（后端将 `source_type` 赋给模型的 `source` 字段）。

---

### 3.16 更新参数映射

**请求**

```
PUT /api/v1/algorithm/mappings/{mapping_id}
```

**请求参数**（全部可选）

| 字段 | camelCase | 类型 | 必填 | 中文含义 |
|------|-----------|------|------|----------|
| `source_type` | `sourceType` | string | 否 | 源类型 |
| `source_param` | `sourceParam` | string | 否 | 源参数代码 |
| `source_direction` | `sourceDirection` | string | 否 | 源参数方向 |
| `dimension_id` | `dimensionId` | integer | 否 | 目标维度 ID |
| `target_param` | `targetParam` | string | 否 | 目标参数代码 |
| `transform_type` | `transformType` | string | 否 | 转换类型 |

---

### 3.17 删除参数映射

**请求**

```
DELETE /api/v1/algorithm/mappings/{mapping_id}
```

---

### 3.18 新建维度关联

**请求**

```
POST /api/v1/algorithm/dimension-relations
```

**请求参数**

| 字段 | camelCase | 类型 | 必填 | 默认值 | 中文含义 |
|------|-----------|------|------|--------|----------|
| `algorithm_type` | `algorithmType` | string | 是 | - | 关联算法类型 |
| `dimension_id` | `dimensionId` | integer | 是 | - | 评估维度 ID |
| `weight` | `weight` | float | 否 | 1.0 | 权重（0~1） |
| `is_default` | `isDefault` | boolean | 否 | false | 是否默认维度 |

**请求示例**

```json
{
  "algorithmType": "translation",
  "dimensionId": 1,
  "weight": 1.0,
  "isDefault": true
}
```

**前端调用**

```typescript
// AlgorithmConfigModal.vue → handleDimensionBlur()（仅 edit 模式触发）
const data = {
  algorithm_type: formState.value.type,
  dimension_id: dim.dimension_id,
  weight: dim.weight,
  is_default: dim.is_default
}

if (dim.id) {
  await algorithmApi.updateDimensionRelation(dim.id, data)
} else {
  const result = await algorithmApi.createDimensionRelation(data)
  dim.id = result.id
}
```

**注意事项**
- 唯一约束：`(algorithm_type, dimension_id)` 二字段组合唯一
- 设置 `is_default=true` 时，前端会自动调用 `updateDimensionRelation` 将其他维度的 `is_default` 设为 false

---

### 3.19 获取算法关联维度

**请求**

```
GET /api/v1/algorithm/dimensions/{algo_type}
```

**响应**

```json
{
  "success": true,
  "code": 200,
  "data": [
    {
      "id": 1,
      "algorithmType": "translation",
      "dimensionId": 1,
      "dimensionName": "BLEU",
      "weight": 1.0,
      "isDefault": true
    }
  ]
}
```

---

### 3.20 批量关联维度

**请求**

```
POST /api/v1/algorithm/dimensions/{algo_type}
```

**请求 Body**

```json
{
  "dimensions": [
    { "dimensionId": 1, "weight": 1.0, "isDefault": true },
    { "dimensionId": 2, "weight": 0.5, "isDefault": false }
  ]
}
```

---

### 3.21 获取分组列表

**请求**

```
GET /api/v1/algorithm/groups
```

**响应**

```json
{
  "success": true,
  "code": 200,
  "data": [
    {
      "id": 1,
      "name": "语音处理",
      "description": "语音相关算法",
      "icon": null,
      "displayOrder": 1
    }
  ]
}
```

**前端调用**

```typescript
// AlgorithmConfigModal.vue → loadGroups()
const result = await algorithmApi.getGroups()
groups.value = result.data || []
```

---

### 3.22 获取选项来源

**请求**

```
GET /api/v1/algorithm/options-sources
```

**响应**

```json
{
  "success": true,
  "code": 200,
  "data": [
    { "value": "translation_directions", "label": "翻译方向" },
    { "value": "languages", "label": "语言列表" }
  ]
}
```

**前端调用**

```typescript
// AlgorithmConfigModal.vue → loadOptionsSources()
const result = await algorithmApi.getOptionsSources()
optionsSources.value = result.data || []
```

---

## 4. 数据模型总览

### 4.1 表关系图

```
algorithm_groups (算法分组)
  └── 1:N ── algorithm_definitions (算法定义)
                ├── 1:N ── algorithm_device_params (设备参数)
                ├── 1:N ── algorithm_api_params (API参数)
                ├── 1:N ── case_algorithm_params (用例参数)
                ├── 1:N ── algorithm_reference_params (参考参数)
                ├── 1:N ── param_mappings (参数映射)
                └── 1:N ── algorithm_dimension_relations (维度关联)
                               └── N:1 ── evaluation_dimension_params (维度参数)
```

### 4.2 核心表字段

#### algorithm_definitions（算法定义表）

| 列名 | 类型 | 可空 | 默认值 | 中文含义 |
|------|------|------|--------|----------|
| id | BigInteger | 否 | 自增 | 主键 |
| type | String(50) | 否 | - | 算法类型代码（唯一） |
| name | String(100) | 否 | - | 算法名称 |
| group_id | BigInteger | 是 | - | 分组 ID |
| description | Text | 是 | - | 描述 |
| status | String(20) | 是 | `online` | 状态 |
| icon | String(200) | 是 | - | 图标 URL |
| display_order | Integer | 是 | 0 | 排序权重 |
| deleted | Boolean | 是 | false | 逻辑删除 |
| created_at | DateTime | 是 | now() | 创建时间 |
| updated_at | DateTime | 是 | now() | 更新时间 |

#### algorithm_device_params / algorithm_api_params（设备/API参数表）

| 列名 | 类型 | 可空 | 默认值 | 中文含义 |
|------|------|------|--------|----------|
| id | Integer | 否 | 自增 | 主键 |
| algorithm_type | String(50) | 否 | - | 关联算法类型 |
| param_code | String(50) | 否 | - | 参数代码 |
| param_name | String(100) | 是 | - | 参数名称 |
| label | String(100) | 是 | - | 字段显示名称 |
| param_type | String(30) | 否 | - | 参数类型 |
| direction | String(10) | 是 | `input` | 方向 |
| required | Boolean | 是 | false | 是否必填 |
| default_value | Text | 是 | - | 默认值 |
| validation_rules | Text | 是 | - | 验证规则 |
| help_text | Text | 是 | - | 帮助提示 |
| ui_order | Integer | 是 | 0 | 界面排序 |
| hidden | Boolean | 是 | false | 是否隐藏 |
| deleted | Boolean | 是 | false | 逻辑删除 |

> 唯一约束：`(algorithm_type, param_code, direction)`

#### case_algorithm_params（用例参数表）

比设备/API参数多出以下字段：

| 列名 | 类型 | 可空 | 默认值 | 中文含义 |
|------|------|------|--------|----------|
| options_source | String(50) | 是 | - | 选项来源 |
| options_field | String(50) | 是 | - | 选项值字段 |
| options_label_field | String(50) | 是 | - | 选项显示字段 |
| scope | String(10) | 否 | `common` | 适用范围 |
| min_value | Float | 是 | - | 最小值 |
| max_value | Float | 是 | - | 最大值 |
| step | Float | 是 | - | 步长 |
| unit | String(20) | 是 | - | 单位 |

> 唯一约束：`(algorithm_type, param_code)`

#### algorithm_reference_params（参考参数表）

| 列名 | 类型 | 可空 | 默认值 | 中文含义 |
|------|------|------|--------|----------|
| id | Integer | 否 | 自增 | 主键 |
| algorithm_type | String(50) | 否 | - | 关联算法类型 |
| code | String(50) | 否 | - | 参数代码 |
| name | String(100) | 是 | - | 参数名称 |
| param_type | String(30) | 是 | `text` | 参考类型 |
| annotation_code | String(100) | 是 | - | 标注代码 |
| annotation_format | String(20) | 是 | - | 标注格式 |
| field_path | String(255) | 是 | - | 字段路径 |
| merge_mode | String(20) | 是 | `join` | 合并方式 |
| help_text | Text | 是 | - | 帮助提示 |

> 唯一约束：`(algorithm_type, code)`

#### param_mappings（参数映射表）

| 列名 | 类型 | 可空 | 默认值 | 中文含义 |
|------|------|------|--------|----------|
| id | Integer | 否 | 自增 | 主键 |
| algorithm_type | String(50) | 否 | - | 关联算法类型 |
| source | String(20) | 否 | `api` | 来源 |
| source_param | String(50) | 否 | - | 源参数代码 |
| source_direction | String(10) | 是 | `output` | 源参数方向 |
| dimension_id | Integer | 是 | - | 目标维度 ID |
| target_param | String(50) | 否 | - | 目标参数代码 |
| transform_type | String(20) | 是 | `none` | 转换类型 |

> 唯一约束：`(algorithm_type, source, source_param, dimension_id)`

---

## 5. 前端表单字段定义

### 5.1 基本信息 Tab

| 字段 key | 表单类型 | 必填 | 选项/约束 | 中文含义 |
|----------|----------|------|-----------|----------|
| `type` | text input | 是 | placeholder "如: translation, asr" | 算法代码 |
| `name` | text input | 是 | placeholder "如: 翻译" | 显示名称 |
| `group_id` | select | 是 | 动态加载自 `GET /groups` | 所属分组 |
| `display_order` | number input | 否 | min=0 | 排序 |
| `description` | textarea | 否 | rows=3 | 描述 |
| `statusSwitch` | switch | 否 | true=online / false=offline | 状态 |

### 5.2 参数配置 Tab — 设备参数 / API参数

| 字段 key | 表头 | 表单类型 | 选项 |
|----------|------|----------|------|
| `param_code` | 参数代码 | text input | - |
| `param_name` | 参数名称 | text input | - |
| `direction` | 方向 | select | `input`/`output` |
| `param_type` | 类型 | select | `text`/`audio_stream`/`audio_file`/`text_file`/`rttm`/`stm`/`json` |
| `required` | 必填 | checkbox | true/false |

### 5.3 参数配置 Tab — 用例参数

| 字段 key | 表头 | 表单类型 | 选项 |
|----------|------|----------|------|
| `param_code` | 参数代码 | text + datalist | 19 个预设值 |
| `param_name` | 参数名称 | text input | - |
| `param_type` | 类型 | select | `text`/`number`/`textarea`/`select`/`switch`/`slider` |
| `scope` | 适用范围 | select | `common`/`api`/`e2e` |
| `options_source` | 选项来源 | select | 动态加载 |
| `required` | 必填 | checkbox | - |
| `default_value` | 默认值 | text input | - |
| `min_value` | 最小值 | number input | 仅 slider/number 显示 |
| `max_value` | 最大值 | number input | 同上 |
| `step` | 步长 | number input | 同上 |
| `unit` | 单位 | text input | 同上 |
| `help_text` | 帮助文本 | text input | - |

**用例参数预设代码（PARAM_CODE_PRESETS）：**

| 预设代码 | 中文含义 |
|----------|----------|
| `translation_direction` | 翻译方向 |
| `source_language` | 源语言 |
| `target_language` | 目标语言 |
| `promptAudioId` | Prompt 音频 ID |
| `overlap_rate` | 交叠率 |
| `overlap_time` | 交叠时间 |
| `voiceprintEnabled` | 声纹注册开关 |
| `voiceprintAudioId` | 声纹音频 ID |
| `voiceprintPlaybackDeviceId` | 声纹播放设备 ID |
| `voiceprintSpl` | 声纹 SPL |
| `voiceprintWaitTime` | 声纹等待时间 |
| `interferers` | 干扰人 |
| `railDistance` | 轨道距离 |
| `volumeLevel` | 音量等级 |

### 5.4 参考参数 Tab

| 字段 key | 表头 | 表单类型 | 选项 |
|----------|------|----------|------|
| `code` | 参数代码 | text input | - |
| `annotation_code` | 标注代码 | text input | 默认同 code |
| `name` | 参数名称 | text input | - |
| `type` | 参考类型 | select | `text`/`audio`/`json`/`rttm`/`stm` |
| `annotation_format` | 标注格式 | select | `""`/`text`/`json`/`rttm`/`stm` |
| `field_path` | 字段路径 | text input | - |
| `merge_mode` | 合并方式 | select | `join`/`collect`/`first` |
| `help_text` | 帮助文本 | text input | - |

### 5.5 关联维度 Tab

| 字段 key | 表头 | 表单类型 | 选项 |
|----------|------|----------|------|
| `dimension_id` | 评估维度 | select | 动态加载 |
| `weight` | 权重 | number input | min=0, max=1, step=0.1 |
| `is_default` | 默认 | checkbox | 互斥（仅一个默认） |

---

## 6. 端到端测试用例

### 6.1 完整创建流程测试

**前置条件**：PostgreSQL 运行中，后端服务运行在 `localhost:5000`

**Step 1：获取初始化数据**

```bash
# 获取分组列表
curl http://localhost:5000/api/v1/algorithm/groups

# 获取选项来源
curl http://localhost:5000/api/v1/algorithm/options-sources
```

**Step 2：创建算法定义（含子配置）**

```bash
curl -X POST http://localhost:5000/api/v1/algorithm/definitions \
  -H "Content-Type: application/json" \
  -d '{
    "type": "test_e2e_algo",
    "name": "E2E测试算法",
    "groupId": 1,
    "description": "端到端测试用算法",
    "status": "online",
    "displayOrder": 99,
    "deviceParams": [
      {
        "paramCode": "audio_input",
        "paramName": "音频输入",
        "paramType": "audio_stream",
        "direction": "input",
        "required": true
      },
      {
        "paramCode": "asr_result",
        "paramName": "ASR结果",
        "paramType": "text",
        "direction": "output",
        "required": true
      }
    ],
    "apiParams": [
      {
        "paramCode": "text_input",
        "paramName": "文本输入",
        "paramType": "text",
        "direction": "input",
        "required": true
      }
    ],
    "caseParams": [
      {
        "paramCode": "translation_direction",
        "paramName": "翻译方向",
        "paramType": "select",
        "scope": "common",
        "optionsSource": "translation_directions",
        "required": true
      }
    ],
    "mappings": {
      "device": [
        {
          "source": "case",
          "sourceParam": "translation_direction",
          "sourceDirection": "input",
          "targetParam": "direction",
          "transformType": "none"
        }
      ],
      "api": [],
      "evaluation": []
    },
    "associatedDimensions": [
      {
        "dimensionId": 1,
        "weight": 1.0,
        "isDefault": true
      }
    ]
  }'
```

**预期响应**：

```json
{
  "success": true,
  "code": 200,
  "message": "Algorithm created",
  "data": {
    "id": 100,
    "type": "test_e2e_algo",
    "name": "E2E测试算法",
    "groupId": 1,
    "groupName": "语音处理",
    "status": "online",
    "displayOrder": 99,
    "deviceParams": [...],
    "apiParams": [...],
    "caseParams": [...],
    "mappings": {...},
    "associatedDimensions": [...]
  }
}
```

**Step 3：验证创建结果**

```bash
curl http://localhost:5000/api/v1/algorithm/definitions/test_e2e_algo
```

**Step 4：单独创建参考参数**

```bash
curl -X POST http://localhost:5000/api/v1/algorithm/reference-params \
  -H "Content-Type: application/json" \
  -d '{
    "algorithmType": "test_e2e_algo",
    "code": "asr_reference_text",
    "name": "ASR参考文本",
    "type": "text",
    "annotationCode": "asr_annotation",
    "annotationFormat": "text",
    "fieldPath": "text",
    "mergeMode": "join"
  }'
```

**Step 5：更新参数（自动保存场景）**

```bash
curl -X PUT http://localhost:5000/api/v1/algorithm/params/{param_id} \
  -H "Content-Type: application/json" \
  -d '{
    "paramName": "音频输入（已更新）",
    "helpText": "输入音频流"
  }'
```

**Step 6：清理（删除测试算法）**

```bash
curl -X DELETE http://localhost:5000/api/v1/algorithm/definitions/test_e2e_algo
```

### 6.2 错误场景测试

| 场景 | 请求 | 预期结果 |
|------|------|----------|
| 重复创建 type | POST 同一 type | `success: false`, message: `Algorithm '{type}' already exists` |
| 缺少必填字段 | POST 无 type | `success: false`, message 包含验证错误 |
| 参数代码重复 | POST 同一 (type, code, direction) | `success: false`, message: 参数已存在 |
| 更新不存在的算法 | PUT /definitions/nonexistent | `success: false`, 404 |
| 删除不存在的算法 | DELETE /definitions/nonexistent | `success: false`, 404 |

### 6.3 前端 UI 测试

| 测试点 | 操作 | 预期结果 |
|--------|------|----------|
| 打开新建模态窗 | 点击"新建算法"按钮 | 模态窗打开，分组/维度/选项来源下拉加载完成 |
| 填写基本信息 | 输入 type/name，选择分组 | 字段校验通过 |
| 添加设备参数 | 在参数配置 Tab 添加行 | 参数行出现，填写后失焦自动保存 |
| 添加用例参数 | 切换到用例参数，添加行 | 参数行出现，预设代码可选择 |
| 添加参考参数 | 切换到参考参数 Tab，添加行 | 参数行出现，annotation_code 自动同步 |
| 配置映射 | 切换到参数映射 Tab | MappingEditor 加载，可选择源/目标参数 |
| 关联维度 | 切换到关联维度 Tab | 维度下拉加载，权重可调 |
| 提交 | 点击"确定" | POST 请求发送，成功后模态窗关闭，列表刷新 |
| 编辑模式 | 点击列表项"编辑" | 模态窗打开，所有字段回填 |
| 删除 | 点击"删除"并确认 | 确认对话框 → DELETE 请求 → 列表刷新 |

---

## 附录：接口快速索引

| # | 方法 | 路径 | 前端 API 方法 |
|---|------|------|---------------|
| 1 | POST | `/definitions` | `algorithmApi.createDefinition(data)` |
| 2 | GET | `/definitions/{type}` | `algorithmApi.getDefinition(type)` |
| 3 | PUT | `/definitions/{type}` | `algorithmApi.updateDefinition(type, data)` |
| 4 | DELETE | `/definitions/{type}` | `algorithmApi.deleteDefinition(type)` |
| 5 | GET | `/definitions` | `algorithmApi.getDefinitions(params)` |
| 6 | POST | `/params` | `algorithmApi.createParam(data)` |
| 7 | PUT | `/params/{id}` | `algorithmApi.updateParam(id, data)` |
| 8 | DELETE | `/params/{id}` | `algorithmApi.deleteParam(id)` |
| 9 | POST | `/case-params` | `algorithmApi.createCaseParam(data)` |
| 10 | PUT | `/case-params/{id}` | `algorithmApi.updateCaseParam(id, data)` |
| 11 | DELETE | `/case-params/{id}` | `algorithmApi.deleteCaseParam(id)` |
| 12 | POST | `/reference-params` | `algorithmApi.createReferenceParam(data)` |
| 13 | PUT | `/reference-params/{id}` | `algorithmApi.updateReferenceParam(id, type, data)` |
| 14 | DELETE | `/reference-params/{id}?algorithm_type={type}` | `algorithmApi.deleteReferenceParam(id, type)` |
| 15 | POST | `/mappings` | `algorithmApi.createMapping(data)` |
| 16 | PUT | `/mappings/{id}` | `algorithmApi.updateMapping(id, data)` |
| 17 | DELETE | `/mappings/{id}` | `algorithmApi.deleteMapping(id)` |
| 18 | POST | `/dimension-relations` | `algorithmApi.createDimensionRelation(data)` |
| 19 | GET | `/dimensions/{type}` | `algorithmApi.getDimensions(type)` |
| 20 | POST | `/dimensions/{type}` | `algorithmApi.associateDimensions(type, dims)` |
| 21 | GET | `/groups` | `algorithmApi.getGroups()` |
| 22 | GET | `/options-sources` | `algorithmApi.getOptionsSources()` |
