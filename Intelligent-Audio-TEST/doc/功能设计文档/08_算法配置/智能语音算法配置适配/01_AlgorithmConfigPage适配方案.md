# AlgorithmConfigPage - 算法配置管理页面适配方案

## 1. 页面概述

### 1.1 页面定位
AlgorithmConfigPage 是算法配置管理的核心页面，用于管理所有算法类型的定义、参数配置、参数映射等信息。

### 1.2 页面路由
- 路由路径：`/algorithm-config`
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

```typescript
// 算法分组 - 对应 algorithm_models.py 中的 AlgorithmGroup 模型
interface AlgorithmGroup {
  id: number;
  name: string;           // 分组名称：翻译、语音识别、声纹识别、语音合成
  description: string;    // 分组描述
  icon: string;           // 图标URL
  display_order: number;  // 排序权重
  algorithm_count: number; // 分组下算法数量
  created_at: string;
  updated_at: string;
}

// 算法定义 - 对应 algorithm_models.py 中的 AlgorithmDefinition 模型
interface Algorithm {
  id: number;
  type: string;           // 算法类型代码：translation, asr, speaker_recognition, tts
  name: string;           // 显示名称：翻译、ASR、声纹识别、TTS
  group_id: number;       // 关联分组ID (外键 -> AlgorithmGroup)
  group_name: string;     // 分组名称（关联查询）
  description: string;    // 描述
  status: 'online' | 'offline';  // 状态
  icon: string;           // 图标URL
  display_order: number;  // 排序权重
  created_at: string;
  updated_at: string;
}
```

### 3.2 算法详情数据

```typescript
// 算法详情 - 包含参数和映射配置
interface AlgorithmDetail {
  type: string;
  name: string;
  group_id: number;
  group_name: string;
  description: string;
  status: 'online' | 'offline';
  icon: string;
  display_order: number;
  
  // 设备参数 - 对应 AlgorithmDeviceParam 模型
  device_params: AlgorithmDeviceParam[];
  
  // API参数 - 对应 AlgorithmApiParam 模型  
  api_params: AlgorithmApiParam[];
  
  // 参数映射 - 对应 ParamMapping 模型
  mappings: ParamMapping[];
  
  // 评估维度关联 - 对应 AlgorithmDimensionRelation 模型
  dimension_relations: AlgorithmDimensionRelation[];
}

// 设备参数 - algorithm_models.py AlgorithmDeviceParam
interface AlgorithmDeviceParam {
  id: number;
  algorithm_type: string;
  param_code: string;       // 参数代码
  param_name: string;       // 参数显示名称
  label: string;            // 字段显示名称
  param_type: string;       // 参数类型：select, text, number, textarea, slider, switch, json
  direction: string;        // 方向：input, output
  required: boolean;        // 是否必填
  default_value: any;        // 默认值
  options_source: string;    // 选项来源
  options_field: string;    // 选项值字段
  options_label_field: string; // 选项显示字段
  validation: object;        // 验证规则
  help_text: string;        // 帮助提示
  component: string;         // 前端组件
  ui_order: number;         // 界面排序
  ui_group: string;         // 分组：basic, model, inference, advanced
  hidden: boolean;          // 是否隐藏
}

// API参数 - algorithm_models.py AlgorithmApiParam（字段同 AlgorithmDeviceParam）
interface AlgorithmApiParam extends Omit<AlgorithmDeviceParam, 'direction'> {
  // API参数direction默认为output
}

// 参数映射 - algorithm_models.py ParamMapping
interface ParamMapping {
  id: number;
  algorithm_type: string;
  source_type: 'device' | 'api';  // 源类型
  source_param: string;           // 源参数代码
  source_direction: string;       // 源参数方向：input, output
  dimension_id: number;           // 目标评估维度ID
  dimension_name: string;         // 评估维度名称
  target_param: string;           // 目标评估维度参数代码
  transform_type: string;         // 转换类型：none, uppercase, lowercase, json_parse, base64
}

// 评估维度关联 - algorithm_models.py AlgorithmDimensionRelation
interface AlgorithmDimensionRelation {
  id: number;
  algorithm_type: string;
  dimension_id: number;
  dimension_name: string;
  is_default: boolean;     // 是否默认评估维度
  weight: number;          // 权重
}
```

> **注**：完整字段映射方案见 [15_完整字段映射方案.md](file:///c:/S2TT/auto_test/ver8/202601292330/doc/功能设计文档/智能语音算法配置适配/15_完整字段映射方案.md)
```

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
// GET /api/v1/algorithm/definitions
interface AlgorithmListResponse {
  data: Algorithm[];
  total: number;
}

// 请求参数
interface AlgorithmListParams {
  page?: number;
  page_size?: number;
  status?: 'online' | 'offline';
  group_id?: number;      // 按分组筛选
}
```

### 4.6 获取算法详情

```typescript
// GET /api/v1/algorithm/definitions/:type
// 返回 AlgorithmDetail，包含 device_params, api_params, mappings, dimension_relations
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

### 4.10 获取设备参数列表

```typescript
// GET /api/v1/algorithm/definitions/:type/device-params
// 返回 AlgorithmDeviceParam[]
```

### 4.11 获取API参数列表

```typescript
// GET /api/v1/algorithm/definitions/:type/api-params
// 返回 AlgorithmApiParam[]
```

### 4.12 获取参数映射列表

```typescript
// GET /api/v1/algorithm/definitions/:type/mappings
// 返回 ParamMapping[]
```

### 4.13 获取评估维度关联

```typescript
// GET /api/v1/algorithm/definitions/:type/dimensions
// 返回 AlgorithmDimensionRelation[]
```

### 4.14 添加评估维度关联

```typescript
// POST /api/v1/algorithm/definitions/:type/dimensions
interface AddDimensionRelationRequest {
  dimension_id: number;
  is_default?: boolean;
  weight?: number;
}
```

### 4.15 删除评估维度关联

```typescript
// DELETE /api/v1/algorithm/definitions/:type/dimensions/:id
// 返回 { success: boolean, message: string }
```

### 4.16 获取表单 Schema

```typescript
// GET /api/v1/algorithm/definitions/:type/form-schema
interface FormSchemaResponse {
  algorithmType: string;
  algorithmName: string;
  groupId: number;
  groupName: string;
  description: string;
  status: string;
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
  options?: Array<{ label: string; value: any }>;
  validation?: Record<string, any>;
  helpText?: string;
  hidden: boolean;
}
```

### 4.17 重新加载配置

```typescript
// POST /api/v1/algorithm/reload
// 返回 { success: boolean, message: string }
```

---

## 5. 组件设计

### 5.1 页面组件结构

```
AlgorithmConfigPage.vue
├── AlgorithmGroupSelect.vue     # 分组筛选下拉框（关联 AlgorithmGroup）
├── AlgorithmGroupModal.vue      # 分组管理弹窗
├── AlgorithmTable.vue          # 算法列表表格
├── AlgorithmCard.vue           # 算法卡片（可选视图）
├── AlgorithmConfigModal.vue    # 算法配置弹窗（共用）
├── DeviceParamPanel.vue        # 设备参数配置面板（对应 AlgorithmDeviceParam）
├── ApiParamPanel.vue           # API参数配置面板（对应 AlgorithmApiParam）
├── MappingConfigPanel.vue      # 映射配置面板（对应 ParamMapping）
└── DimensionRelationPanel.vue # 评估维度关联面板（对应 AlgorithmDimensionRelation）
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

// 模态窗标签页
type TabKey = 'basic' | 'parameters' | 'mappings' | 'dimensions';
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
    await algorithmService.createAlgorithm(data);
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
    const detail = await algorithmService.getAlgorithmDetail(type);
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
    
    await algorithmService.deleteAlgorithm(type);
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
  const algorithms = await algorithmService.getAlgorithmList({ page_size: 1000 });
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
      await algorithmService.createAlgorithm(algo);
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
│  选项配置 (仅 select 类型):                                              │
│  选项来源: [translation_directions ▼] ← 数据库表名                       │
│  值字段:   [code                    ]                                    │
│  显示字段: [description              ]                                   │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│  前端组件: [select ▼]                ← select/input/input-number/...    │
│  界面分组: [basic ▼]                 ← basic/model/inference/advanced   │
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

### 7.3 选项来源配置

| 选项来源 | 数据表 | 值字段 | 显示字段 |
|---------|-------|-------|---------|
| translation_directions | TranslationDirection | code | description |
| languages | - | code | name |
| sample_rates | - | value | label |

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

### 10.1 Pinia Store

```typescript
// stores/algorithm.ts
import { defineStore } from 'pinia';
import { algorithmService } from '@/services/algorithmService';

export const useAlgorithmStore = defineStore('algorithm', {
  state: () => ({
    algorithms: [] as Algorithm[],
    currentAlgorithm: null as AlgorithmDetail | null,
    loading: false,
    total: 0,
    page: 1,
    pageSize: 10,
    filters: {
      status: '',
      category: ''
    }
  }),
  
  actions: {
    async loadAlgorithms() {
      this.loading = true;
      try {
        const response = await algorithmService.getAlgorithmList({
          page: this.page,
          page_size: this.pageSize,
          ...this.filters
        });
        this.algorithms = response.data;
        this.total = response.total;
      } finally {
        this.loading = false;
      }
    },
    
    async loadAlgorithmDetail(type: string) {
      this.loading = true;
      try {
        this.currentAlgorithm = await algorithmService.getAlgorithmDetail(type);
      } finally {
        this.loading = false;
      }
    },
    
    async createAlgorithm(data: CreateAlgorithmRequest) {
      await algorithmService.createAlgorithm(data);
      await this.loadAlgorithms();
    },
    
    async updateAlgorithm(type: string, data: UpdateAlgorithmRequest) {
      await algorithmService.updateAlgorithm(type, data);
      await this.loadAlgorithms();
    },
    
    async deleteAlgorithm(type: string) {
      await algorithmService.deleteAlgorithm(type);
      await this.loadAlgorithms();
    }
  }
});
```

---

## 11. 实施清单

### 11.1 后端实施

- [ ] 创建 `algorithm_models.py` 数据模型
- [ ] 创建 `algorithm_controller.py` API 控制器
- [ ] 创建 `algorithm_service.py` 业务逻辑
- [ ] 创建数据库迁移脚本
- [ ] 初始化算法数据

### 11.2 前端实施

- [ ] 创建 `AlgorithmConfigPage.vue` 页面
- [ ] 创建 `AlgorithmConfigModal.vue` 模态窗
- [ ] 创建 `ParameterConfigPanel.vue` 参数配置面板
- [ ] 创建 `MappingConfigPanel.vue` 映射配置面板
- [ ] 创建 `DimensionSelect.vue` 维度选择器
- [ ] 创建 `algorithmService.ts` API 服务
- [ ] 创建 `useAlgorithmStore` 状态管理
- [ ] 配置路由

### 11.3 测试验证

- [ ] 算法列表加载测试
- [ ] 算法创建测试
- [ ] 算法编辑测试
- [ ] 算法删除测试
- [ ] 参数配置测试
- [ ] 映射配置测试
- [ ] 导入导出测试
