# AlgorithmConfigPage - 算法配置管理页面适配方案

> **架构变更说明（2026-07）**：`options_source` 字段已废弃，`TranslationDirection` 表已删除。所有算法参数（包括翻译方向、语种）都是静态文本输入（`param_type=text`），不再从数据库表动态获取选项。本文档中涉及 `options_source=translation_directions` 的内容已过时。
>
> **分层与命名口径（当前实现）**：后端模型/请求校验内部为 snake_case，但所有 API 响应经 `success_response` 统一转换为 **camelCase**（`convert_keys_to_camel`）；请求体通过 Pydantic `validation_alias` 同时接受 camelCase 与 snake_case。前端遵循 DDD 分层——Infrastructure（`api/`/`adapters/`/`dto/`）唯一负责 snake_case↔camelCase 映射，Presentation/Application 只见 camelCase Domain 模型与 composables（Ports）。

## 1. 页面概述

### 1.1 页面定位
AlgorithmConfigPage 是算法配置管理的核心页面，用于管理所有算法类型的定义、参数配置、参数映射等信息。（已实施：`frontend/src/views/AlgorithmConfigPage.vue`，算法新建/编辑由共用组件 `AlgorithmConfigModal.vue` 承载，弹窗经 `useModal` composable 全局注册管理。）

### 1.2 页面路由
- 路由路径：`/AlgorithmConfig`（`router/index.ts` 中 name 为 `algorithmConfig`）
- 菜单位置：系统设置 > 算法配置

### 1.3 核心功能
- 算法列表展示（卡片/表格视图）
- 新建/编辑/删除算法
- 算法参数配置管理
- 参数映射配置
- 评估维度关联
- 配置导入/导出

---

## 2. 页面布局

```
┌─────────────────────────────────────────────────────────────────────────┐
│  算法配置管理                                                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  [+ 新建算法]  [分组管理]  [刷新配置]  [导出]  [导入]             │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  分组筛选: [全部 ▼]  状态: [全部 ▼]                               │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                                                                   │  │
│  │  算法列表 (表格视图)                                               │  │
│  │  ┌────────────────────────────────────────────────────────────┐ │  │
│  │  │ ID │ 算法类型 │ 名称 │ 分组 │ 参数数 │ 关联用例 │ 状态 │ 操作 │ │  │
│  │  ├────────────────────────────────────────────────────────────┤ │  │
│  │  │ 1  │translat.│ 翻译 │ 翻译 │ 1     │ 50      │ 在线 │...  │ │  │
│  │  │ 2  │asr      │ ASR  │语音识别│ 4    │ 30      │ 在线 │...  │ │  │
│  │  │ 3  │speaker..│ 声纹 │声纹识别│ 2    │ 20      │ 在线 │...  │ │  │
│  │  │ 4  │tts      │ TTS  │语音合成│ 3    │ 15      │ 在线 │...  │ │  │
│  │  └────────────────────────────────────────────────────────────┘ │  │
│  │                                                                   │  │
│  │  分页: 1 / 1                                                     │  │
│  │                                                                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 数据结构

### 3.1 算法列表数据

> 命名口径：以下为**前端 Domain 模型（camelCase）**。后端 `algorithm_models.py` 内部为 snake_case，响应经统一转换后即为下述 camelCase 结构。

```typescript
// 算法分组 - 对应 algorithm_models.py 中的 AlgorithmGroup 模型
interface AlgorithmGroup {
  id: number;
  name: string;            // 分组名称：翻译、语音识别、声纹识别、语音合成
  description: string;     // 分组描述
  icon: string;            // 图标URL
  displayOrder: number;    // 排序权重（后端 display_order）
  algorithmCount: number;  // 分组下算法数量（后端 algorithm_count）
  createdAt: string;
  updatedAt: string;
}

// 算法定义 - 对应 algorithm_models.py 中的 AlgorithmDefinition 模型
interface Algorithm {
  id: number;
  type: string;            // 算法类型代码：translation, asr, speaker_recognition, tts
  name: string;            // 显示名称：翻译、ASR、声纹识别、TTS
  groupId: number;         // 关联分组ID（后端 group_id，外键 -> AlgorithmGroup）
  groupName: string;       // 分组名称（关联查询，后端 group_name）
  description: string;     // 描述
  status: 'online' | 'offline';  // 状态（枚举化，禁止魔法字符串）
  icon: string;            // 图标URL
  displayOrder: number;    // 排序权重（后端 display_order）
  createdAt: string;
  updatedAt: string;
}
```

### 3.2 算法详情数据

```typescript
// 算法详情 - 包含参数和映射配置（GET /api/v1/algorithm/definitions/:type 响应，camelCase）
interface AlgorithmDetail {
  type: string;
  name: string;
  groupId: number;
  groupName: string;
  description: string;
  status: 'online' | 'offline';
  icon: string;
  displayOrder: number;

  // 设备参数 - 对应 AlgorithmDeviceParam 模型
  deviceParams: AlgorithmDeviceParam[];

  // API参数 - 对应 AlgorithmApiParam 模型（字段同设备参数，direction 默认 output）
  apiParams: AlgorithmApiParam[];

  // 用例专属参数 - 对应 CaseAlgorithmParam 模型（驱动动态表单）
  caseParams: CaseAlgorithmParam[];

  // 参数映射 - 对应 ParamMapping 模型（按 source 分组：device/api/evaluation）
  mappings: ParamMappingGroups;

  // 评估维度关联 - 对应 AlgorithmDimensionRelation 模型
  dimensionRelations: AlgorithmDimensionRelation[];

  // 参考参数 - 对应 AlgorithmReferenceParam 模型
  referenceParams: AlgorithmReferenceParam[];
}

// 设备参数 - algorithm_models.py AlgorithmDeviceParam
interface AlgorithmDeviceParam {
  id: number;
  algorithmType: string;   // 后端 algorithm_type
  paramCode: string;       // 参数代码（后端 param_code）
  paramName: string;       // 参数显示名称（后端 param_name）
  label: string;           // 字段显示名称（映射配置中展示）
  paramType: string;       // 参数类型：text, audio_stream, audio_file, text_file, rttm, stm, json
  direction: string;       // 方向：input, output（枚举化）
  required: boolean;       // 是否必填
  defaultValue: any;       // 默认值（后端 default_value，JSON）
  validation: object;      // 验证规则（后端 validation_rules 解析后）
  helpText: string;        // 帮助提示（后端 help_text）
  uiOrder: number;         // 界面排序（后端 ui_order）
  hidden: boolean;         // 是否隐藏
}

// API参数 - algorithm_models.py AlgorithmApiParam（字段同 AlgorithmDeviceParam）
interface AlgorithmApiParam extends Omit<AlgorithmDeviceParam, 'direction'> {
  // API参数 direction 默认为 output
}

// 用例专属参数 - algorithm_models.py CaseAlgorithmParam（动态表单字段来源）
interface CaseAlgorithmParam {
  id: number;
  algorithmType: string;
  paramCode: string;
  paramName: string;
  label: string;
  paramType: string;       // text, number, textarea, slider, switch, audio_select, device_select, json
  required: boolean;
  defaultValue: any;
  helpText: string;
  uiOrder: number;
  hidden: boolean;
  scope: 'common' | 'api' | 'e2e';  // 参数适用范围（枚举化）
  minValue?: number;       // number/slider 约束
  maxValue?: number;
  step?: number;
  unit?: string;           // 单位显示（如 cm, dB, s）
  annotationCode?: string; // 关联音频标注代码
  fieldPath?: string;      // 标注数据字段路径
}

// 参数映射 - algorithm_models.py ParamMapping
interface ParamMapping {
  id: number;
  algorithmType: string;
  source: string;                 // 参数来源（枚举化）：case=用例参数, reference=参考参数, device=设备输出, api=API输出, case_config=用例配置(config.rounds)字段
  sourceParam: string;            // 源参数代码（后端 source_param）
  paramName?: string;             // 源参数显示名称（后端按 source 回填）
  sourceDirection: string;        // 源参数方向：input, output（后端 source_direction）
  dimensionId: number | null;     // 目标评估维度ID（后端 dimension_id，评估类映射必填）
  dimensionName: string;          // 评估维度名称（后端 dimension_name）
  targetParam: string;            // 目标评估维度参数代码（后端 target_param）
  transformType: string;          // 转换类型（枚举化）：none, uppercase, lowercase, json_parse, base64
}

// 评估维度关联 - algorithm_models.py AlgorithmDimensionRelation
interface AlgorithmDimensionRelation {
  id: number;
  algorithmType: string;
  dimensionId: number;     // 后端 dimension_id
  dimensionName: string;   // 后端 dimension_name
  isDefault: boolean;      // 是否默认评估维度（后端 is_default）
  weight: number;          // 权重
}
```

> **注**：完整字段映射方案见本目录及《15_完整字段映射方案.md》（历史引用路径已失效，以本目录文档为准）。

---

## 4. API 接口

### 4.1 获取算法分组列表

```typescript
// GET /api/v1/algorithm/groups
interface AlgorithmGroupListResponse {
  data: AlgorithmGroup[];
  total: number;
}
```

### 4.2 创建算法分组

```typescript
// POST /api/v1/algorithm/groups
interface CreateAlgorithmGroupRequest {
  name: string;
  description?: string;
  icon?: string;
  display_order?: number;
}
```

### 4.3 更新算法分组

```typescript
// PUT /api/v1/algorithm/groups/:id
interface UpdateAlgorithmGroupRequest extends Partial<CreateAlgorithmGroupRequest> {}
```

### 4.4 删除算法分组

```typescript
// DELETE /api/v1/algorithm/groups/:id
// 返回 { success: boolean, message: string }
```

### 4.5 获取算法列表

```typescript
// GET /api/v1/algorithm/definitions（全量返回，按 displayOrder 排序）
interface AlgorithmListResponse {
  data: Algorithm[];
  total: number;
}

// 请求参数（AlgorithmListQuery）
interface AlgorithmListParams {
  status?: 'online' | 'offline';  // 按状态筛选
  groupId?: number;               // 按分组筛选（后端 group_id）
}
```

### 4.6 获取算法详情

```typescript
// GET /api/v1/algorithm/definitions/:type
// 返回 AlgorithmDetail，包含 deviceParams, apiParams, caseParams, mappings, dimensionRelations, referenceParams
```

### 4.7 创建算法

```typescript
// POST /api/v1/algorithm/definitions
interface CreateAlgorithmRequest {
  type: string;
  name: string;
  group_id: number;           // 关联分组ID
  description?: string;
  status?: 'online' | 'offline';
  icon?: string;
  display_order?: number;
}
```

### 4.8 更新算法

```typescript
// PUT /api/v1/algorithm/definitions/:type
interface UpdateAlgorithmRequest extends Partial<CreateAlgorithmRequest> {}
```

### 4.9 删除算法

```typescript
// DELETE /api/v1/algorithm/definitions/:type
// 返回 { success: boolean, message: string }
```

### 4.10 获取参数列表（设备参数 / API 参数统一入口）

```typescript
// GET /api/v1/algorithm/params?algorithmType=:type&paramType=device|api
// paramType=device 返回 AlgorithmDeviceParam[]，paramType=api 返回 AlgorithmApiParam[]
// 响应：{ parameters: [...], total: number }
```

### 4.11 获取用例专属参数列表

```typescript
// GET /api/v1/algorithm/case-params?algorithmType=:type
// 返回 CaseAlgorithmParam[]；支持 POST/PUT/DELETE /api/v1/algorithm/case-params[/:id] 维护
```

### 4.12 获取参数映射列表

```typescript
// GET /api/v1/algorithm/mappings?algorithmType=:type
// 返回按 source 分组的映射：{ device: [...], api: [...], evaluation: [...] }
// 支持 POST /api/v1/algorithm/mappings、PUT/DELETE /api/v1/algorithm/mappings/:id
```

### 4.13 获取评估维度关联

```typescript
// GET /api/v1/algorithm/dimensions/:type
// 返回 { dimensions: [...], dimensionIds: [...], defaultDimensionId, weights }
// 其中 dimensions 元素含 id/name/description/type/weight/isDefault
```

### 4.14 关联评估维度（整体替换）

```typescript
// POST /api/v1/algorithm/dimensions/:type
interface AssociateDimensionsRequest {
  dimensions: Array<{ dimensionId: number; weight?: number }>;
}
```

### 4.15 维度关联单条维护

```typescript
// POST /api/v1/algorithm/dimension-relations          （新建单条关联）
// PUT  /api/v1/algorithm/dimension-relations/:id      （更新 isDefault/weight）
// DELETE /api/v1/algorithm/dimension-relations/:id    （删除单条关联，逻辑删除）
```

### 4.16 获取表单 Schema

```typescript
// GET /api/v1/algorithm/form-schema/:type
interface FormSchemaResponse {
  algorithmType: string;
  algorithmName: string;
  description: string;
  groups: FormGroup[];
  fields: FormField[];
}

interface FormGroup {
  name: string;
  label: string;
  fields: FormField[];
}

interface FormField {
  fieldCode: string;
  fieldName: string;
  fieldType: string;
  required: boolean;
  defaultValue: any;
  component: string;
  helpText?: string;
  hidden: boolean;
  uiOrder: number;   // 界面排序（后端 ui_order）
  scope: string;     // 参数适用范围：common/api/e2e
}

// fieldType -> component 默认映射（后端 _get_default_component）
// select->select  text->input  textarea->textarea  number->input-number
// boolean->switch  json->code-editor  slider->slider
```

### 4.17 重新加载配置

```typescript
// POST /api/v1/algorithm/reload
// 返回 { success: boolean, message: string }
```

### 4.18 其他配套接口（已实现）

```typescript
// 参考参数：GET/POST /api/v1/algorithm/reference-params；PUT/DELETE /api/v1/algorithm/reference-params/:id
// 维度参数：GET /api/v1/algorithm/dimension-params/:dimensionId
// 算法导入：POST /api/v1/algorithm/import
// 批量删除：POST /api/v1/algorithm/bulk-delete
// 参数提取：POST /api/v1/algorithm/extract-params
```

---

## 5. 组件设计

### 5.1 页面组件结构（当前实现）

```
AlgorithmConfigPage.vue                      # views/AlgorithmConfigPage.vue（已实施）
├── PaginationComponent.vue                  # 分页组件（components/common/）
├── useModal / MODAL_TYPES                   # 弹窗控制 composable（全局弹窗注册）
├── AlgorithmConfigModal.vue                 # 算法配置弹窗（components/algorithm/，5 个标签页）
│   ├── 基本信息basic / 参数配置params / 参考参数reference / 参数映射mappings / 关联维度dimensions
│   ├── AlgorithmParamsConfig.vue            # 参数配置面板（含 supportedAlgorithms 选择）
│   └── DynamicForm.vue                      # 动态表单（依据 FormSchema 渲染）
├── AlgorithmSelect.vue                      # 算法选择器（components/algorithm/）
└── 数据访问：utils/api.ts 中 algorithmApi（Infrastructure 层，唯一感知接口报文）
```

### 5.2 AlgorithmGroupModal（分组管理弹窗）

```typescript
interface AlgorithmGroupModalProps {
  visible: boolean;
  mode: 'list' | 'create' | 'edit';
  editData?: AlgorithmGroup | null;
}

// 分组管理弹窗布局（对应 AlgorithmGroup 模型）
```
┌──────────────────────────────────────────────────────────────┐
│  算法分组管理                                          [×]    │
├──────────────────────────────────────────────────────────────┤
│  [新建分组]                                                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  名称        │ 描述           │ 算法数 │ 操作         │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │ 翻译        │ 机器翻译算法    │ 1     │ 编辑 | 删除   │ │
│  │ 语音识别    │ 语音识别算法    │ 1     │ 编辑 | 删除   │ │
│  │ 声纹识别    │ 声纹识别算法    │ 1     │ 编辑 | 删除   │ │
│  │ 语音合成    │ 语音合成算法    │ 1     │ 编辑 | 删除   │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 5.3 AlgorithmConfigModal（共用模态窗）

```typescript
// 模态窗支持的模式
type ModalMode = 'create' | 'edit' | 'view';

interface AlgorithmConfigModalProps {
  visible: boolean;
  mode: ModalMode;
  editData?: AlgorithmDetail | null;  // 编辑时传入
  groups: AlgorithmGroup[];           // 分组列表（新增）
}

// 模态窗标签页（当前实现为 5 个，见 AlgorithmConfigModal.vue 的 formTabs）
type TabKey = 'basic' | 'params' | 'reference' | 'mappings' | 'dimensions';
```

### 5.4 ParameterConfigPanel

```vue
<!-- 参数配置面板 -->
<template>
  <div class="parameter-config-panel">
    <div class="panel-header">
      <span>参数配置</span>
      <el-button @click="addParameter">+ 添加参数</el-button>
    </div>
    
    <el-table :data="parameters" border>
      <el-table-column prop="code" label="参数代码" width="150" />
      <el-table-column prop="name" label="显示名称" width="120" />
      <el-table-column prop="type" label="类型" width="100" />
      <el-table-column prop="required" label="必填" width="80">
        <template #default="{ row }">
          <el-tag :type="row.required ? 'danger' : 'info'">
            {{ row.required ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="component" label="组件" width="120" />
      <el-table-column label="操作" width="150">
        <template #default="{ row, $index }">
          <el-button link @click="editParameter($index)">编辑</el-button>
          <el-button link type="danger" @click="deleteParameter($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>
```

---

## 6. 核心交互逻辑

### 6.1 新建算法流程

```typescript
const handleCreateAlgorithm = () => {
  modalMode.value = 'create';
  modalData.value = {
    type: '',
    name: '',
    category: 'translation',
    description: '',
    parameters: [],
    default_params: {},
    device_params_mapping: [],
    api_params_mapping: [],
    evaluation_params_mapping: []
  };
  modalVisible.value = true;
};

const handleSaveAlgorithm = async (data: CreateAlgorithmRequest) => {
  try {
    await algorithmApi.createDefinition(data);
    ElMessage.success('算法创建成功');
    await loadAlgorithmList();
    modalVisible.value = false;
  } catch (error) {
    ElMessage.error('算法创建失败: ' + error.message);
  }
};
```

### 6.2 编辑算法流程

```typescript
const handleEditAlgorithm = async (type: string) => {
  try {
    const detail = await algorithmApi.getDefinition(type);
    modalMode.value = 'edit';
    modalData.value = detail;
    modalVisible.value = true;
  } catch (error) {
    ElMessage.error('获取算法详情失败');
  }
};
```

### 6.3 删除算法流程

```typescript
const handleDeleteAlgorithm = async (type: string, name: string) => {
  try {
    await ElMessageBox.confirm(
      `确定删除算法"${name}"？此操作不可恢复。`,
      '确认删除',
      { type: 'warning' }
    );
    
    await algorithmApi.deleteDefinition(type);
    ElMessage.success('算法删除成功');
    await loadAlgorithmList();
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('算法删除失败: ' + error.message);
    }
  }
};
```

### 6.4 导入导出流程

```typescript
// 导出算法配置
const handleExport = async () => {
  const algorithms = await algorithmApi.getDefinitions();
  const blob = new Blob([JSON.stringify(algorithms.data, null, 2)], {
    type: 'application/json'
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `algorithms_${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
};

// 导入算法配置
const handleImport = async (file: File) => {
  try {
    const content = await file.text();
    const algorithms = JSON.parse(content);
    
    await ElMessageBox.confirm(
      `将导入 ${algorithms.length} 个算法配置，确定继续？`,
      '确认导入'
    );
    
    for (const algo of algorithms) {
      await algorithmApi.createDefinition(algo);
    }
    
    ElMessage.success(`成功导入 ${algorithms.length} 个算法`);
    await loadAlgorithmList();
  } catch (error) {
    ElMessage.error('导入失败: ' + error.message);
  }
};
```

---

## 7. 参数配置面板详细设计

### 7.1 参数编辑弹窗

```
┌─────────────────────────────────────────────────────────────────────────┐
│  编辑参数                                                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  参数代码: [translation_direction    ]  ← 唯一标识                       │
│  显示名称: [翻译方向                  ]                                   │
│  参数类型: [select ▼]                ← select/text/number/textarea/...  │
│  是否必填: [✓]                                                          │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│  （原"选项来源/值字段/显示字段"配置已随 options_source 废弃而移除，        │
│   选项内容直接内置于默认值或前端枚举配置）                                  │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│  前端组件: [select ▼]                ← select/input/input-number/...    │
│  排序权重: [1                        ]                                   │
│  是否隐藏: [ ]                                                          │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│  默认值:   [{"source_language": "zh", "target_language": "en"}]         │
│  帮助文本: [选择翻译的源语言和目标语言    ]                                   │
│                                                                          │
│                                [取消] [保存]                              │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.2 参数类型与组件对应关系

| 参数类型 | 前端组件 | 说明 |
|---------|---------|------|
| select | select | 下拉选择 |
| text | input | 文本输入 |
| number | input-number | 数字输入 |
| textarea | textarea | 多行文本 |
| slider | slider | 滑块 |
| switch | switch | 开关 |
| json | code-editor | JSON编辑器 |

### 7.3 选项来源配置（已废弃）

> 原 `translation_directions / languages / sample_rates` 数据库动态选项来源方案已废弃：`options_source` 字段与 `TranslationDirection` 表均已删除，选项不再从数据库表获取。当前所有参数选项均为静态文本输入或内置于前端枚举/配置中。

---

## 8. 映射配置面板详细设计

### 8.1 映射配置界面

```
┌─────────────────────────────────────────────────────────────────────────┐
│  参数映射配置                                                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ▶ 设备参数映射 (device)                                                 │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │  源参数          │  目标参数      │  转换类型    │  操作           ││
│  ├────────────────────────────────────────────────────────────────────┤│
│  │ translation_dir │ translation_dir │ none       │ [编辑] [删除]   ││
│  │ source_language │ source_language │ none       │ [编辑] [删除]   ││
│  │ target_language │ target_language │ none       │ [编辑] [删除]   ││
│  └────────────────────────────────────────────────────────────────────┘│
│  [+ 添加设备映射]                                                        │
│                                                                          │
│  ▶ API参数映射 (api)                                                     │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │  源参数          │  目标参数      │  转换类型    │  操作           ││
│  ├────────────────────────────────────────────────────────────────────┤│
│  │ translation_dir │ direction       │ none       │ [编辑] [删除]   ││
│  └────────────────────────────────────────────────────────────────────┘│
│  [+ 添加API映射]                                                         │
│                                                                          │
│  ▶ 评估参数映射 (evaluation)                                             │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │  源参数          │  目标参数      │  转换类型    │  操作           ││
│  ├────────────────────────────────────────────────────────────────────┤│
│  │ translation_dir │ direction       │ none       │ [编辑] [删除]   ││
│  └────────────────────────────────────────────────────────────────────┘│
│  [+ 添加评估映射]                                                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.2 转换类型

| 转换类型 | 说明 | 示例 |
|---------|------|------|
| none | 不转换 | zh2en → zh2en |
| uppercase | 转大写 | zh2en → ZH2EN |
| lowercase | 转小写 | ZH2EN → zh2en |
| json_parse | JSON解析 | '{"a":1}' → {a:1} |

---

## 9. 评估维度关联

### 9.1 维度关联界面

```
┌─────────────────────────────────────────────────────────────────────────┐
│  关联评估维度                                                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  可选维度:                                                               │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │  □ BLEU评分    - 用于翻译质量评估                                   ││
│  │  □ ROUGE评分   - 用于翻译质量评估                                   ││
│  │  □ TER错误率   - 用于翻译错误率评估                                  ││
│  │  □ WER错误率   - 用于ASR错误率评估                                   ││
│  │  □ CER错误率   - 用于ASR字符错误率评估                               ││
│  │  □ 说话人准确率 - 用于声纹识别评估                                   ││
│  └────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  已选维度:                                                               │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │  ✓ BLEU评分    [默认] [权重: 1.0]                                   ││
│  │  ✓ ROUGE评分   [      ] [权重: 1.0]                                 ││
│  │  ✓ TER错误率   [      ] [权重: 0.5]                                 ││
│  └────────────────────────────────────────────────────────────────────┘│
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 10. 状态管理

### 10.1 当前实现：composables（Application 层）+ 页面本地状态

> 原方案中的 Pinia `useAlgorithmStore` 与 `algorithmService` **未实施且已废弃**。当前遵循 DDD 分层约定：页面状态由 `AlgorithmConfigPage.vue` 内部 `ref/computed` 管理，跨页面复用的算法能力沉淀为 composables（Ports），接口访问统一收敛到 `utils/api.ts` 的 `algorithmApi`（Infrastructure 层）。

```typescript
// composables/useAlgorithmConfig.ts（已实施，核心应用层封装）
// - getFormSchema(algorithmType)：拉取 /api/v1/algorithm/form-schema/:type，
//   并以 Map 缓存（formSchemas）避免重复请求（ReadModel 缓存）
// - getCaseAlgorithmParams(algorithmType)：拉取 /api/v1/algorithm/case-params，
//   同样带缓存（caseParamCache）；内部完成 snake_case -> camelCase 字段映射
//   （paramCode/paramName/paramType/defaultValue/helpText/uiOrder/hidden 等）
// - 仅依赖 algorithmApi 与 Domain 类型，不感知 HTTP 细节

// composables/useAlgorithmSelection.ts / useAlgorithmLabels.ts
// - 算法选择状态与算法标签文案（枚举化映射，避免魔法字符串）

// 弹窗控制：composables/useModal.ts（MODAL_TYPES 注册 ALGORITHM_CONFIG 等全局弹窗）
```

如后续算法列表数据需要跨页面共享，再考虑引入轻量 store；当前规模下页面本地状态 + composable 缓存已满足 CQRS 读模型要求。

---

## 11. 实施清单

### 11.1 后端实施（已完成）

- [x] 创建 `backend/models/algorithm_models.py` 数据模型（AlgorithmGroup/AlgorithmDefinition/AlgorithmDeviceParam/AlgorithmApiParam/CaseAlgorithmParam/AlgorithmReferenceParam/ParamMapping/AlgorithmDimensionRelation）
- [x] 创建 `backend/controllers/algorithm_controller.py` API 控制器 + `backend/blueprints/algorithm_bp.py` 路由（前缀 `/api/v1/algorithm`）
- [x] 创建 `backend/schemas/algorithm.py` 请求/响应 Schema（Pydantic validation_alias 兼容 camelCase/snake_case）
- [x] 数据库迁移与算法数据初始化

### 11.2 前端实施（已完成）

- [x] 创建 `views/AlgorithmConfigPage.vue` 页面（路由 `/AlgorithmConfig`）
- [x] 创建 `components/algorithm/AlgorithmConfigModal.vue` 模态窗（basic/params/reference/mappings/dimensions 5 个标签页）
- [x] 创建 `components/algorithm/AlgorithmParamsConfig.vue` 参数配置面板
- [x] 创建 `components/algorithm/DynamicForm.vue` 动态表单（06 文档）
- [x] 维度选择能力并入 `AlgorithmConfigModal.vue` 关联维度标签页（原计划独立 `DimensionSelect.vue` 未单独实施，相关面板见 `components/common/DimensionConfigPanel.vue`）
- [x] 创建 `utils/api.ts` 中 `algorithmApi`（原计划的 `algorithmService.ts` 未实施，改为 Infrastructure 层 API 对象）
- [x] 创建 `composables/useAlgorithmConfig.ts` 等应用层封装（原计划的 `useAlgorithmStore` 未实施，改为 composables）

### 11.3 测试验证

- [ ] 算法列表加载测试
- [ ] 算法创建测试
- [ ] 算法编辑测试
- [ ] 算法删除测试
- [ ] 参数配置测试
- [ ] 映射配置测试
- [ ] 导入导出测试
