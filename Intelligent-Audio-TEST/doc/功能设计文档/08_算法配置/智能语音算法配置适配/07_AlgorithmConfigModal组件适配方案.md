# AlgorithmConfigModal - 共用模态窗适配方案

## 1. 组件概述

### 1.1 组件定位
AlgorithmConfigModal 是一个共用的算法配置模态窗组件，用于在多个页面中提供统一的算法管理功能。

### 1.2 使用场景
- AlgorithmConfigPage：算法配置管理页面（完整功能）
- E2ETest：E2E测试步骤0（新建/编辑算法）
- APITest：API测试步骤0（新建/编辑算法）
- TestCaseModal：新建用例时选择算法

### 1.3 核心功能
- 查看算法列表
- 新建算法（完整配置）
- 编辑算法参数
- 删除算法
- 支持多种模式切换

---

## 2. 现有实现分析

### 2.1 当前组件结构

```
AlgorithmConfigModal.vue
├── a-modal                    # Ant Design 模态窗
│   ├── mode-list              # 列表模式
│   │   ├── modal-header       # 新建按钮 + 搜索框
│   │   └── a-table            # 算法表格
│   └── mode-form              # 新建/编辑模式
│       ├── a-form             # 表单
│       └── a-tabs             # 标签页
│           ├── basic          # 基本信息
│           ├── params         # 参数配置
│           └── mappings       # 参数映射
└── MappingEditor.vue          # 映射编辑子组件
```

### 2.2 当前布局

**列表模式 (mode='list')**
```
┌──────────────────────────────────────────────────────────────┐
│  算法配置管理                                          [×]    │
├──────────────────────────────────────────────────────────────┤
│  [新建算法]                              [搜索算法...]        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  类型    │  名称  │  分类  │  状态  │      操作        │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │translation│ 翻译  │ 翻译   │ 在线   │ 编辑 | 选择 | 删除│ │
│  │   asr    │ ASR   │语音识别│ 在线   │ 编辑 | 选择 | 删除│ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

**新建/编辑模式 (mode='create'/'edit')**
```
┌──────────────────────────────────────────────────────────────┐
│  新建算法 / 编辑算法                                    [×]  │
├──────────────────────────────────────────────────────────────┤
│  [基本信息] [参数配置] [参数映射]                             │
│  ──────────────────────────────────────────────────────────  │
│  【基本信息】                                                │
│  算法类型: [________________] ← 编辑时禁用                   │
│  显示名称: [________________]                                │
│  分类:     [翻译 ▼]                                          │
│  状态:     ○ 上线  ○ 下线                                    │
│  描述:     [________________________________]                │
│  排序:     [0]                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 差距分析与适配方案

### 3.1 功能差距

| 功能点 | 现有实现 | 方案要求 | 适配方案 |
|--------|---------|---------|---------|
| UI框架 | Ant Design Vue | Element Plus | **保持 Ant Design Vue** |
| 模式控制 | props.mode | 标签页切换 | **保持现有 mode 机制** |
| 分组选择 | ❌ 无 category 字段 | ✅ 需要 group_id | **新增分组下拉选择** |
| 列表操作 | 编辑/选择/删除 | 编辑/禁用/删除 | **添加禁用/启用按钮** |
| 参数映射 | MappingEditor | MappingConfigPanel | **保持现有组件** |
| 关联维度 | ❌ 无 | ✅ 需要 | **新增维度关联标签页** |

### 3.2 适配方案

**保持不变的部分：**
1. 使用 Ant Design Vue 组件 (`a-modal`, `a-table`, `a-tabs`, `a-form`)
2. 通过 `props.mode` 控制显示内容
3. 现有的 `MappingEditor` 子组件

**需要新增的部分：**
1. 基本信息标签页添加"所属分组"下拉选择
2. 列表模式添加"禁用/启用"操作按钮
3. 新建/编辑模式添加"关联评估维度"标签页

---

## 4. 组件接口（保持现有）

### 4.1 Props

```typescript
interface ModalProps {
  visible: boolean
  mode?: 'list' | 'create' | 'edit' | 'select'
  editData?: AlgorithmRecord | null
  groups?: AlgorithmGroup[]        // 算法分组列表
}

interface AlgorithmGroup {
  id: number
  name: string
  description?: string
  icon?: string
  display_order: number
  algorithm_count?: number  // 分组下算法数量
}
```

### 4.2 Emits

```typescript
interface ModalEmits {
  (e: 'update:visible', visible: boolean): void
  (e: 'select', data: AlgorithmRecord): void
  (e: 'success'): void
}
```

---

## 5. 适配修改清单

### 5.1 基本信息标签页 - 添加分组选择

**修改位置：** `a-tab-pane key="basic"` 内

**新增表单项：**
```vue
<a-form-item label="所属分组" name="group_id">
  <a-select 
    v-model:value="formState.group_id" 
    placeholder="选择分组"
    :disabled="mode === 'edit'"
  >
    <a-select-option 
      v-for="group in groups" 
      :key="group.id" 
      :value="group.id"
    >
      {{ group.name }}
    </a-select-option>
  </a-select>
</a-form-item>
```

**更新 formState：**
```typescript
const formState = reactive({
  type: '',
  name: '',
  group_id: null as number | null,  // 新增：关联 AlgorithmGroup
  status: '',
  description: '',
  display_order: 0,
})
```

**更新 formRules：**
```typescript
const formRules: FormRules = {
  type: [{ required: true, message: '请输入算法类型' }],
  name: [{ required: true, message: '请输入显示名称' }],
  group_id: [{ required: true, message: '请选择所属分组' }]  // 新增
}
```

### 5.2 参数配置 - 使用独立的设备参数和API参数表

**修改说明：** 根据 algorithm_models.py，参数分为两类：
- `AlgorithmDeviceParam`: 设备参数（单算法专用）
- `AlgorithmApiParam`: API参数（单算法专用）

需要分别配置设备参数和API参数：

### 5.3 列表模式 - 添加禁用/启用按钮

**修改位置：** `listColumns` 的操作列

**修改前：**
```vue
<template v-if="column.key === 'action'">
  <a-space>
    <a @click="handleEdit(record)">编辑</a>
    <a-divider type="vertical" />
    <a @click="handleSelect(record)">选择</a>
    <a-divider type="vertical" />
    <a-popconfirm ...>
      <a class="danger">删除</a>
    </a-popconfirm>
  </a-space>
</template>
```

**修改后：**
```vue
<template v-if="column.key === 'action'">
  <a-space>
    <a @click="handleEdit(record)">编辑</a>
    <a-divider type="vertical" />
    <a @click="handleToggleStatus(record)">
      {{ record.status === 'online' ? '禁用' : '启用' }}
    </a>
    <a-divider type="vertical" />
    <a-popconfirm ...>
      <a class="danger">删除</a>
    </a-popconfirm>
  </a-space>
</template>
```

**新增方法：**
```typescript
async function handleToggleStatus(record: AlgorithmRecord) {
  const newStatus = record.status === 'online' ? 'offline' : 'online'
  const action = newStatus === 'offline' ? '禁用' : '启用'
  
  try {
    const response = await fetch(`/api/v1/algorithm/definitions/${record.type}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus })
    })
    const result = await response.json()
    if (result.success) {
      message.success(`${action}成功`)
      loadAlgorithms()
    } else {
      message.error(result.message || `${action}失败`)
    }
  } catch (error) {
    message.error(`${action}失败`)
  }
}
```

### 5.4 新建/编辑模式 - 添加关联评估维度标签页

**修改位置：** `a-tabs` 组件内

**新增标签页：**
```vue
<a-tab-pane key="dimensions" tab="关联评估维度">
  <div class="dimensions-config">
    <div class="dimensions-header">
      <a-button type="primary" size="small" @click="handleAddDimension">
        <template #icon><PlusOutlined /></template>
        添加关联维度
      </a-button>
    </div>
    
    <a-table
      :columns="dimensionColumns"
      :dataSource="formState.dimension_relations"
      :rowKey="(record, index) => index"
      :pagination="false"
      size="small"
    >
      <template #bodyCell="{ column, record, index }">
        <template v-if="column.key === 'dimension_id'">
          <a-select
            v-model:value="record.dimension_id"
            size="small"
            placeholder="选择评估维度"
            style="width: 100%"
            :options="availableDimensions.map(d => ({ value: d.id, label: d.name }))"
          />
        </template>
        <template v-else-if="column.key === 'is_default'">
          <a-switch v-model:checked="record.is_default" size="small" />
        </template>
        <template v-else-if="column.key === 'weight'">
          <a-input-number
            v-model:value="record.weight"
            size="small"
            :min="0"
            :max="1"
            :step="0.1"
          />
        </template>
        <template v-else-if="column.key === 'action'">
          <a-button type="link" danger size="small" @click="handleRemoveDimension(index)">
            删除
          </a-button>
        </template>
      </template>
    </a-table>
  </div>
</a-tab-pane>
```

**新增数据和方法：**
```typescript
const dimensionColumns = [
  { title: '评估维度', dataIndex: 'dimension_id', key: 'dimension_id' },
  { title: '默认', dataIndex: 'is_default', key: 'is_default', width: 60 },
  { title: '权重', dataIndex: 'weight', key: 'weight', width: 100 },
  { title: '操作', key: 'action', width: 60 }
]

const availableDimensions = ref<Dimension[]>([])

async function loadDimensions() {
  try {
    const response = await fetch('/api/v1/evaluation/dimensions')
    const result = await response.json()
    if (result.success) {
      availableDimensions.value = result.data || []
    }
  } catch (error) {
    console.error('加载评估维度失败', error)
  }
}

function handleAddDimension() {
  formState.dimension_relations.push({
    dimension_id: null,
    is_default: false,
    weight: 1.0
  })
}

function handleRemoveDimension(index: number) {
  formState.dimension_relations.splice(index, 1)
}
```

**更新 formState：**
```typescript
const formState = reactive({
  // ... 现有字段
  dimension_relations: [] as { dimension_id: string | number; is_default: boolean; weight: number }[]
})
```

**API 说明：** 保存关联维度时，会操作 `AlgorithmDimensionRelation` 表：
- POST `/api/v1/algorithm/definitions/:type/dimensions` - 添加关联
- DELETE `/api/v1/algorithm/definitions/:type/dimensions/:id` - 删除关联

---

## 6. 完整修改后的组件代码

### 6.1 主组件 AlgorithmConfigModal.vue

```vue
<template>
  <a-modal
    :title="title"
    :open="visible"
    :width="modalWidth"
    :destroyOnClose="true"
    @cancel="handleCancel"
    @ok="handleOk"
    :okText="okText"
    :cancelText="cancelText"
  >
    <div class="algorithm-config-modal">
      <!-- 列表模式 -->
      <div v-if="mode === 'list'" class="mode-list">
        <div class="modal-header">
          <a-button type="primary" @click="handleCreate">
            <template #icon><PlusOutlined /></template>
            新建算法
          </a-button>
          <a-input-search
            v-model:value="searchKeyword"
            placeholder="搜索算法"
            style="width: 200px"
            @search="handleSearch"
          />
        </div>

        <a-table
          :columns="listColumns"
          :dataSource="filteredAlgorithms"
          :rowKey="record => record.type"
          :pagination="false"
          :scroll="{ y: 400 }"
          size="small"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'status'">
              <a-badge 
                :status="record.status === 'online' ? 'success' : 'default'" 
                :text="record.status === 'online' ? '在线' : '离线'" 
              />
            </template>
            <template v-else-if="column.key === 'action'">
              <a-space>
                <a @click="handleEdit(record)">编辑</a>
                <a-divider type="vertical" />
                <a @click="handleToggleStatus(record)">
                  {{ record.status === 'online' ? '禁用' : '启用' }}
                </a>
                <a-divider type="vertical" />
                <a-popconfirm
                  title="确定删除此算法？"
                  ok-text="确定"
                  cancel-text="取消"
                  @confirm="handleDelete(record)"
                >
                  <a class="danger">删除</a>
                </a-popconfirm>
              </a-space>
            </template>
          </template>
        </a-table>
      </div>

      <!-- 新建/编辑模式 -->
      <div v-else class="mode-form">
        <a-form
          ref="formRef"
          :model="formState"
          :rules="formRules"
          :label-col="{ span: 6 }"
          :wrapper-col="{ span: 16 }"
        >
          <a-tabs v-model:activeKey="activeTab">
            <a-tab-pane key="basic" tab="基本信息">
              <a-form-item label="算法类型" name="type">
                <a-input
                  v-model:value="formState.type"
                  :disabled="mode === 'edit'"
                  placeholder="如: translation, asr"
                />
              </a-form-item>
              <a-form-item label="显示名称" name="name">
                <a-input v-model:value="formState.name" placeholder="如: 翻译" />
              </a-form-item>
              <a-form-item label="所属分组" name="group_id">
                <a-select 
                  v-model:value="formState.group_id" 
                  placeholder="选择分组"
                  :disabled="mode === 'edit'"
                >
                  <a-select-option 
                    v-for="group in groups" 
                    :key="group.id" 
                    :value="group.id"
                  >
                    {{ group.name }}
                  </a-select-option>
                </a-select>
              </a-form-item>
              <a-form-item label="分类" name="category">
                <a-select v-model:value="formState.category" placeholder="选择分类">
                  <a-select-option value="translation">翻译</a-select-option>
                  <a-select-option value="speech_recognition">语音识别</a-select-option>
                  <a-select-option value="voiceprint">声纹识别</a-select-option>
                  <a-select-option value="speech_synthesis">语音合成</a-select-option>
                </a-select>
              </a-form-item>
              <a-form-item label="状态" name="status">
                <a-radio-group v-model:value="formState.status">
                  <a-radio value="online">上线</a-radio>
                  <a-radio value="offline">下线</a-radio>
                </a-radio-group>
              </a-form-item>
              <a-form-item label="描述" name="description">
                <a-textarea v-model:value="formState.description" :rows="3" />
              </a-form-item>
              <a-form-item label="排序" name="display_order">
                <a-input-number v-model:value="formState.display_order" :min="0" />
              </a-form-item>
            </a-tab-pane>

            <a-tab-pane key="params" tab="参数配置">
              <div class="params-header">
                <a-button type="primary" size="small" @click="handleAddParam">
                  <template #icon><PlusOutlined /></template>
                  添加参数
                </a-button>
              </div>

              <a-table
                :columns="paramColumns"
                :dataSource="formState.params"
                :rowKey="record => record.param_code + '_' + Math.random()"
                :pagination="false"
                size="small"
              >
                <template #bodyCell="{ column, record, index }">
                  <template v-if="['param_code', 'param_name'].includes(column.key)">
                    <a-input v-model:value="record[column.key]" size="small" />
                  </template>
                  <template v-else-if="column.key === 'param_type'">
                    <a-select v-model:value="record.param_type" size="small" style="width: 100px">
                      <a-select-option value="select">下拉框</a-select-option>
                      <a-select-option value="text">文本</a-select-option>
                      <a-select-option value="number">数字</a-select-option>
                      <a-select-option value="boolean">开关</a-select-option>
                      <a-select-option value="textarea">多行文本</a-select-option>
                      <a-select-option value="slider">滑块</a-select-option>
                    </a-select>
                  </template>
                  <template v-else-if="column.key === 'required'">
                    <a-switch v-model:checked="record.required" size="small" />
                  </template>
                  <template v-else-if="column.key === 'component'">
                    <a-select v-model:value="record.component" size="small" style="width: 100px">
                      <a-select-option value="select">Select</a-select-option>
                      <a-select-option value="input">Input</a-select-option>
                      <a-select-option value="input-number">InputNumber</a-select-option>
                      <a-select-option value="switch">Switch</a-select-option>
                      <a-select-option value="slider">Slider</a-select-option>
                      <a-select-option value="textarea">Textarea</a-select-option>
                    </a-select>
                  </template>
                  <template v-else-if="column.key === 'ui_group'">
                    <a-select v-model:value="record.ui_group" size="small" style="width: 80px">
                      <a-select-option value="basic">基本</a-select-option>
                      <a-select-option value="model">模型</a-select-option>
                      <a-select-option value="advanced">高级</a-select-option>
                    </a-select>
                  </template>
                  <template v-else-if="column.key === 'action'">
                    <a-button type="link" danger size="small" @click="handleRemoveParam(index)">
                      删除
                    </a-button>
                  </template>
                </template>
              </a-table>
            </a-tab-pane>

            <a-tab-pane key="mappings" tab="参数映射">
              <a-collapse v-model:activeKey="mappingActiveKeys">
                <a-collapse-panel key="device" header="设备参数映射">
                  <MappingEditor
                    :mappings="formState.mappings.device"
                    component-type="device"
                    @update="updateMappings('device', $event)"
                  />
                </a-collapse-panel>
                <a-collapse-panel key="api" header="API参数映射">
                  <MappingEditor
                    :mappings="formState.mappings.api"
                    component-type="api"
                    @update="updateMappings('api', $event)"
                  />
                </a-collapse-panel>
                <a-collapse-panel key="evaluation" header="评估参数映射">
                  <MappingEditor
                    :mappings="formState.mappings.evaluation"
                    component-type="evaluation"
                    @update="updateMappings('evaluation', $event)"
                  />
                </a-collapse-panel>
              </a-collapse>
            </a-tab-pane>

            <!-- 新增：关联评估维度 -->
            <a-tab-pane key="dimensions" tab="关联评估维度">
              <div class="dimensions-header">
                <a-button type="primary" size="small" @click="handleAddDimension">
                  <template #icon><PlusOutlined /></template>
                  添加关联维度
                </a-button>
              </div>
              
              <a-table
                :columns="dimensionColumns"
                :dataSource="formState.associated_dimensions"
                :rowKey="(record, index) => index"
                :pagination="false"
                size="small"
              >
                <template #bodyCell="{ column, record, index }">
                  <template v-if="column.key === 'dimension_id'">
                    <a-select
                      v-model:value="record.dimension_id"
                      size="small"
                      placeholder="选择评估维度"
                      style="width: 100%"
                      :options="availableDimensions.map(d => ({ value: d.id, label: d.name }))"
                    />
                  </template>
                  <template v-else-if="column.key === 'weight'">
                    <a-input-number
                      v-model:value="record.weight"
                      size="small"
                      :min="0"
                      :max="1"
                      :step="0.1"
                    />
                  </template>
                  <template v-else-if="column.key === 'action'">
                    <a-button type="link" danger size="small" @click="handleRemoveDimension(index)">
                      删除
                    </a-button>
                  </template>
                </template>
              </a-table>
            </a-tab-pane>
          </a-tabs>
        </a-form>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { FormInstance, FormRules } from 'ant-design-vue'
import MappingEditor from './MappingEditor.vue'

interface AlgorithmRecord {
  type: string
  name: string
  group_id?: number           // 新增
  category?: string
  description?: string
  status: string
  icon?: string
  display_order: number
  params?: any[]
  mappings?: any
  associated_dimensions?: { dimension_id: string | number; weight: number }[]
}

interface AlgorithmGroup {    // 新增
  id: number
  name: string
  description?: string
  icon?: string
  display_order: number
}

interface Dimension {
  id: string | number
  name: string
  code: string
}

interface ModalProps {
  visible: boolean
  mode?: 'list' | 'create' | 'edit' | 'select'
  editData?: AlgorithmRecord | null
  groups?: AlgorithmGroup[]    // 新增
}

const props = withDefaults(defineProps<ModalProps>(), {
  visible: false,
  mode: 'list',
  editData: null,
  groups: () => []             // 新增默认值
})

const emit = defineEmits<{
  (e: 'update:visible', visible: boolean): void
  (e: 'select', data: AlgorithmRecord): void
  (e: 'success'): void
}>()

const modalWidth = computed(() => {
  if (props.mode === 'list') return 700
  return 900
})

const title = computed(() => {
  const titles = {
    list: '算法配置管理',
    create: '新建算法',
    edit: '编辑算法',
    select: '选择算法'
  }
  return titles[props.mode]
})

const okText = computed(() => {
  if (props.mode === 'select') return '选择'
  if (props.mode === 'list') return undefined
  return '确定'
})

const cancelText = computed(() => {
  if (props.mode === 'list') return undefined
  return '取消'
})

const searchKeyword = ref('')
const activeTab = ref('basic')
const mappingActiveKeys = ref(['device', 'api', 'evaluation'])
const formRef = ref<FormInstance>()

const algorithms = ref<AlgorithmRecord[]>([])
const availableDimensions = ref<Dimension[]>([])

const formState = reactive({
  type: '',
  name: '',
  group_id: null as number | null,  // 新增
  category: '',
  description: '',
  status: 'online' as 'online' | 'offline',
  icon: '',
  display_order: 0,
  params: [] as any[],
  mappings: {
    device: [] as any[],
    api: [] as any[],
    evaluation: [] as any[]
  },
  associated_dimensions: [] as { dimension_id: string | number; weight: number }[]
})

const formRules: FormRules = {
  type: [{ required: true, message: '请输入算法类型' }],
  name: [{ required: true, message: '请输入显示名称' }],
  group_id: [{ required: true, message: '请选择所属分组' }]  // 新增
}

const listColumns = [
  { title: '类型', dataIndex: 'type', key: 'type', width: 120 },
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '分类', dataIndex: 'category', key: 'category', width: 120 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 80 },
  { title: '操作', key: 'action', width: 200 }
]

const paramColumns = [
  { title: '参数代码', dataIndex: 'param_code', key: 'param_code', width: 120 },
  { title: '参数名称', dataIndex: 'param_name', key: 'param_name', width: 100 },
  { title: '类型', dataIndex: 'param_type', key: 'param_type', width: 100 },
  { title: '必填', dataIndex: 'required', key: 'required', width: 60 },
  { title: '组件', dataIndex: 'component', key: 'component', width: 100 },
  { title: '分组', dataIndex: 'ui_group', key: 'ui_group', width: 80 },
  { title: '操作', key: 'action', width: 60 }
]

const dimensionColumns = [
  { title: '评估维度', dataIndex: 'dimension_id', key: 'dimension_id' },
  { title: '权重', dataIndex: 'weight', key: 'weight', width: 100 },
  { title: '操作', key: 'action', width: 60 }
]

const filteredAlgorithms = computed(() => {
  if (!searchKeyword.value) return algorithms.value
  return algorithms.value.filter(a =>
    a.type.includes(searchKeyword.value) ||
    a.name.includes(searchKeyword.value)
  )
})

watch(() => props.visible, (visible) => {
  if (visible) {
    if (props.mode === 'list') {
      loadAlgorithms()
    }
    loadDimensions()
  }
})

watch(() => props.mode, (mode) => {
  if (mode === 'edit' && props.editData) {
    Object.assign(formState, {
      type: props.editData.type,
      name: props.editData.name,
      group_id: props.editData.group_id || null,  // 新增
      category: props.editData.category || '',
      description: props.editData.description || '',
      status: props.editData.status as 'online' | 'offline',
      icon: props.editData.icon || '',
      display_order: props.editData.display_order || 0,
      params: props.editData.params || [],
      mappings: props.editData.mappings || { device: [], api: [], evaluation: [] },
      associated_dimensions: props.editData.associated_dimensions || []
    })
  } else if (mode === 'create') {
    resetForm()
  }
}, { immediate: true })

async function loadAlgorithms() {
  try {
    const response = await fetch('/api/v1/algorithm/definitions')
    const result = await response.json()
    if (result.success) {
      algorithms.value = result.data.data || []
    }
  } catch (error) {
    message.error('加载算法列表失败')
  }
}

async function loadDimensions() {
  try {
    const response = await fetch('/api/v1/evaluation/dimensions')
    const result = await response.json()
    if (result.success) {
      availableDimensions.value = result.data || []
    }
  } catch (error) {
    console.error('加载评估维度失败', error)
  }
}

function resetForm() {
  formState.type = ''
  formState.name = ''
  formState.group_id = null  // 新增
  formState.category = ''
  formState.description = ''
  formState.status = 'online'
  formState.icon = ''
  formState.display_order = 0
  formState.params = []
  formState.mappings = { device: [], api: [], evaluation: [] }
  formState.associated_dimensions = []
  activeTab.value = 'basic'
}

function handleCancel() {
  emit('update:visible', false)
}

async function handleOk() {
  if (props.mode === 'select') {
    if (props.editData) {
      emit('select', props.editData)
      emit('update:visible', false)
    }
    return
  }

  try {
    await formRef.value?.validate()
    await saveAlgorithm()
  } catch (error) {
    // 验证失败
  }
}

async function saveAlgorithm() {
  try {
    const url = props.mode === 'edit'
      ? `/api/v1/algorithm/definitions/${formState.type}`
      : '/api/v1/algorithm/definitions'

    const method = props.mode === 'edit' ? 'PUT' : 'POST'

    const response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formState)
    })

    const result = await response.json()
    if (result.success) {
      message.success(props.mode === 'edit' ? '保存成功' : '创建成功')
      emit('success')
      emit('update:visible', false)
      loadAlgorithms()
    } else {
      message.error(result.message || '操作失败')
    }
  } catch (error) {
    message.error('操作失败')
  }
}

function handleCreate() {
  resetForm()
  emit('update:visible', true)
}

function handleEdit(record: AlgorithmRecord) {
  Object.assign(formState, {
    type: record.type,
    name: record.name,
    group_id: record.group_id || null,  // 新增
    category: record.category || '',
    description: record.description || '',
    status: record.status as 'online' | 'offline',
    icon: record.icon || '',
    display_order: record.display_order || 0,
    params: record.params || [],
    mappings: record.mappings || { device: [], api: [], evaluation: [] },
    associated_dimensions: record.associated_dimensions || []
  })
  emit('update:visible', true)
}

async function handleToggleStatus(record: AlgorithmRecord) {
  const newStatus = record.status === 'online' ? 'offline' : 'online'
  const action = newStatus === 'offline' ? '禁用' : '启用'
  
  try {
    const response = await fetch(`/api/v1/algorithm/definitions/${record.type}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus })
    })
    const result = await response.json()
    if (result.success) {
      message.success(`${action}成功`)
      loadAlgorithms()
    } else {
      message.error(result.message || `${action}失败`)
    }
  } catch (error) {
    message.error(`${action}失败`)
  }
}

async function handleDelete(record: AlgorithmRecord) {
  try {
    const response = await fetch(`/api/v1/algorithm/definitions/${record.type}`, {
      method: 'DELETE'
    })
    const result = await response.json()
    if (result.success) {
      message.success('删除成功')
      loadAlgorithms()
    } else {
      message.error(result.message || '删除失败')
    }
  } catch (error) {
    message.error('删除失败')
  }
}

function handleSearch() {
  // 搜索由 computed 属性自动处理
}

function handleAddParam() {
  formState.params.push({
    param_code: '',
    param_name: '',
    param_type: 'text',
    required: false,
    component: 'input',
    ui_group: 'basic',
    ui_order: formState.params.length
  })
}

function handleRemoveParam(index: number) {
  formState.params.splice(index, 1)
}

function updateMappings(componentType: string, mappings: any[]) {
  formState.mappings[componentType] = mappings
}

function handleAddDimension() {
  formState.associated_dimensions.push({
    dimension_id: null,
    weight: 1.0
  })
}

function handleRemoveDimension(index: number) {
  formState.associated_dimensions.splice(index, 1)
}
</script>

<style lang="less" scoped>
.algorithm-config-modal {
  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  .params-header,
  .dimensions-header {
    margin-bottom: 12px;
  }

  .danger {
    color: #ff4d4f;
  }
}
</style>
```

---

## 7. 实施清单

### 7.1 需要修改的文件

- [ ] `frontend/src/components/algorithm/AlgorithmConfigModal.vue`
  - 添加分组下拉选择（基本信息标签页）
  - 添加禁用/启用按钮
  - 添加关联评估维度标签页
  - 更新 formState 数据结构
  - 更新 formRules 验证规则

### 7.2 功能实现

- [x] 列表模式（现有）
- [x] 新建模式（现有）
- [x] 编辑模式（现有）
- [x] 选择模式（现有）
- [ ] 分组选择功能（新增）
- [ ] 禁用/启用功能（新增）
- [ ] 关联评估维度（新增）

### 7.3 API 依赖

- [x] GET `/api/v1/algorithm/definitions` - 获取算法列表
- [x] POST `/api/v1/algorithm/definitions` - 创建算法
- [x] PUT `/api/v1/algorithm/definitions/:type` - 更新算法
- [x] DELETE `/api/v1/algorithm/definitions/:type` - 删除算法
- [ ] GET `/api/v1/algorithm-groups` - 获取算法分组列表（新增）
- [ ] GET `/api/v1/evaluation/dimensions` - 获取评估维度列表（需确认）
