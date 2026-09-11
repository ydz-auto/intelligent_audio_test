# 算法选择组件适配方案（AlgorithmSelector / AlgorithmSelectionPanel）

## 1. 组件概述

### 1.1 组件定位

> **落地口径**：原方案中的单一 `AlgorithmSelect.vue` 组件未单独落地，算法选择能力按使用场景拆分为两个已实施组件：
>
> | 组件 | 位置 | 形态 | 场景 |
> |------|------|------|------|
> | `AlgorithmSelector.vue` | `frontend/src/components/common/` | 下拉选择器（单选/多选，主算法标记，可选内嵌参数表单） | 表单场景：用例表单、音频上传、批量标注 |
> | `AlgorithmSelectionPanel.vue` | `frontend/src/components/algorithm/` | 卡片网格单选面板 | 测试页步骤 0：E2ETest / APITest |

本章其余章节以 `AlgorithmSelector.vue` 的实际实现为准进行说明；`AlgorithmSelectionPanel.vue` 详见 §7.1 与《03_E2ETest适配方案》§8。

### 1.2 使用场景（实际调用方）

- `AlgorithmSelector.vue`：
  - TestCaseModal/CaseForm.vue：新建/编辑用例时选择算法类型（单选，`show-params=false`）
  - UploadOptions.vue：音频上传时关联算法类型（单选，`show-params=false`，双向绑定 algorithm-relations）
  - BatchAnnotationModal.vue：批量标注时选择算法类型（单选，`show-params=false`）
- `AlgorithmSelectionPanel.vue`：
  - E2ETest.vue / APITest.vue 步骤 0：算法选择（卡片网格单选 + 搜索 + 打开配置）

### 1.3 核心功能

- 算法选项按分组渲染（分组名 `group_name` 由后端算法配置中心返回，前端不硬编码映射）
- 搜索过滤（按名称/类型不区分大小写）
- 单选/多选模式（多选支持主算法 `isPrimary` 标记与"设为主"操作）
- `show-params=true` 时内嵌 DynamicForm 渲染算法参数表单（schema 按算法类型缓存）
- 算法切换时联动加载关联评估维度（`dimensions-change` 事件）

---

## 2. 组件设计

### 2.1 组件结构（AlgorithmSelector.vue 实际结构）

```
AlgorithmSelector.vue（components/common/）
├── .select-header                  # 选择框头部（已选标签 / 占位文本）
│   └── .algo-tag                   # 已选算法标签（多选时含"主"徽标，可移除）
├── .dropdown-menu（Teleport to body）
│   ├── .dropdown-search            # 搜索输入框
│   └── .dropdown-list
│       ├── .group-header           # 分组标题（group_name + 数量）
│       └── .dropdown-item          # 算法选项（勾选图标 + 名称 + "设为主"按钮）
└── .algorithm-params-section       # 参数区（showParams=true 时）
    └── DynamicForm.vue             # 内嵌动态表单（components/algorithm/）
```

### 2.2 交互布局

```
多选模式（single=false，当前调用方未使用，组件已支持）:
┌─────────────────────────────────────────────────────────────────────────┐
│  关联算法 (可多选): [语音识别(主) ×] [翻译 ×]                              │
│            ┌─ 搜索算法...                                               │
│            ├─ 语音识别                                        12         │
│            │    ☑ 通用识别                              [主算法]         │
│            └─ 翻译                                            3          │
└─────────────────────────────────────────────────────────────────────────┘

单选模式（single=true，实际调用方均为该模式）:
┌─────────────────────────────────────────────────────────────────────────┐
│  关联算法: [语音识别 ▼]                                                   │
│            ├─ 搜索算法...                                                │
│            ├─ 语音识别                                    ◉              │
│            └─ 翻译                                        ○              │
└─────────────────────────────────────────────────────────────────────────┘
```

说明：下拉菜单通过 `Teleport` 挂载到 `body`，按视口剩余空间自动向上/向下展开，避免被弹窗/表格裁剪。

---

## 3. 组件接口

### 3.1 Props（实际定义）

```typescript
interface AlgorithmRelation {
  algorithmType: string   // 算法类型代码
  isPrimary: boolean      // 是否主算法（single 模式恒为 true，不显示徽标）
  weight: number          // 权重（当前固定 1.0）
  params?: Record<string, any>
}

interface Props {
  // v-model 绑定主算法类型
  modelValue?: string
  // 已选算法关系列表（支持 v-model:algorithm-relations 双向绑定）
  algorithmRelations?: AlgorithmRelation[]
  // 初始参数（编辑场景回填，内容变化时经快照比对后重新应用）
  initialParams?: Record<string, any>
  // 是否内嵌 DynamicForm 渲染参数表单（默认 true；纯选择场景传 false）
  showParams?: boolean
  // 单选模式（默认 false 多选；实际调用方均为 true）
  single?: boolean
}
```

### 3.2 Emits（实际定义）

```typescript
interface Emits {
  // 更新主算法类型（v-model）
  (e: 'update:modelValue', value: string): void
  // 更新算法关系列表（v-model:algorithm-relations）
  (e: 'update:algorithmRelations', value: AlgorithmRelation[]): void
  // 参数变化（payload 含参数值 + caseAlgorithmParams 用例参数定义 + algorithmFormSchema）
  (e: 'paramsChange', params: Record<string, any>): void
  // 主算法类型变化
  (e: 'algorithmTypeChange', value: string): void
  // 关联评估维度变化（算法切换后经 getAssociatedDimensions 拉取）
  (e: 'dimensionsChange', dimensions: any[], dimensionIds: number[]): void
}
```

### 3.3 Expose（实际定义）

```typescript
defineExpose({
  algorithmParams,        // Ref<Record<string, any>> 当前参数值
  selectedAlgorithms,     // Ref<AlgorithmRelation[]> 当前选中关系
  primaryAlgorithmType    // ComputedRef<string> 主算法类型
})
```

---

## 4. 数据结构

### 4.1 算法选项（下拉数据源）

```typescript
// AlgorithmOption —— 由 useAlgorithmConfig().getAlgorithmOptions() 提供
// 数据来自 GET /api/v1/algorithm/options（响应统一 camelCase）
interface AlgorithmOption {
  value: string        // 算法类型代码
  name: string         // 显示名称
  group_id?: number    // 分组 ID
  group_name?: string  // 分组名（下拉分组标题，缺省归入"其他算法"）
}
```

### 4.2 算法关系（选中结果）

```typescript
// AlgorithmRelation —— 组件内部选中状态，经 update:algorithmRelations 对外暴露
interface AlgorithmRelation {
  algorithmType: string
  isPrimary: boolean
  weight: number
  params?: Record<string, any>
}
```

### 4.3 分组来源（原前端 categoryLabels 映射已废弃）

早期方案在前端维护 `categoryLabels` 静态映射（`translation`→`翻译` 等）。落地后**分类分组信息由算法配置中心统一下发**（`/api/v1/algorithm/options` 返回 `group_id`/`group_name`），前端不再硬编码分类映射表，新增分组无需改前端代码（配置化，消除魔法字符串）。

---

## 5. 组件实现（AlgorithmSelector.vue 实现要点）

> 原方案的 el-select 完整伪代码为早期设计稿，实际落地为自研下拉组件（约 740 行，`frontend/src/components/common/AlgorithmSelector.vue`），以下为关键实现摘要。

### 5.1 选项加载与分组渲染

- 挂载时调用 `useAlgorithmConfig().getAlgorithmOptions()`（GET `/api/v1/algorithm/options`）拉取选项，映射为 `AlgorithmOption[]`
- `filteredGroups` computed：按搜索词（name/value 不区分大小写）过滤后，按 `group_name` 分组（缺省归入"其他算法"），`Map` 维护分组顺序
- 下拉菜单 `Teleport to body` + `fixed` 定位，`updateDropdownPosition` 按视口空间决定向上/向下展开；监听 `document.click`/`resize`/`scroll` 关闭与重定位

### 5.2 选中状态管理（AlgorithmRelation[]）

```typescript
function toggleAlgorithm(type: string) {
  if (props.single) {
    // 单选：再次点击取消；否则整表替换为单条 { algorithmType, isPrimary: true, weight: 1.0 }
  } else {
    // 多选：切换勾选；移除后若无主算法则自动迁移 isPrimary 至首个
  }
  emitChanges()  // 依次 emit update:modelValue / update:algorithmRelations / algorithmTypeChange
}
```

- `primaryAlgorithmType` computed：取 `isPrimary` 项，缺省回落到首个选中项
- 多选下拉内提供"设为主"按钮（`set-primary-algorithm`），single 模式隐藏主算法徽标与按钮

### 5.3 表单 Schema 与参数加载（showParams=true 时）

```typescript
const [schema, caseParamsDef] = await Promise.all([
  getFormSchema(algorithmType),        // GET /api/v1/algorithm/form-schema/:type（useAlgorithmConfig 缓存）
  getCaseAlgorithmParams(algorithmType) // algorithmApi.getCaseParams（caseParamCache 缓存）
])
```

- 参数合并策略：已保存参数 > 字段 `defaultValue`；schema 外的遗留键保留
- `paramsChange` payload 携带 `{ ...参数值, caseAlgorithmParams, algorithmFormSchema }`，供父组件做按轮参数校验/持久化
- `initialParams` watch 使用 `lastAppliedInitialParams` JSON 快照比对，防止 `paramsChange` 回流触发循环请求

### 5.4 showParams=false 分支（实际调用方的主要路径）

跳过表单 schema 与默认值预填（用例参数从标注 JSON 提取，无需表单预填），仅拉取关联维度：

```typescript
const dimensionsData = await getAssociatedDimensions(algorithmType)
// GET /api/v1/algorithm/dimensions/:type → { dimensions, dimension_ids, default_dimension_id, weights }
emit('dimensionsChange', dimensions, dimensionIds)
```

### 5.5 联动 watch

- `modelValue`：外部回填主算法时同步 `selectedAlgorithms` 并重新加载 schema/维度
- `algorithmRelations`（deep）：批量回填（编辑用例场景）
- `initialParams`（deep + 快照比对）：参数回填

---

## 6. 使用示例（实际调用方摘录）

### 6.1 用例表单（TestCaseModal/CaseForm.vue，单选 + 不渲染参数）

```vue
<AlgorithmSelector
  v-if="!isTestTypeLocked"
  v-model="localFormData.algorithmType"
  :initial-params="algorithmParams"
  :single="true"
  :show-params="false"
  @params-change="handleAlgorithmParamsChange"
  @algorithm-type-change="handleAlgorithmTypeChange"
/>
```

说明：用例参数由 RoundConfigEditor 按轮编辑（见《02_TestCaseModal适配方案》），算法选择器仅承担类型选择与维度联动，故 `show-params=false`。

### 6.2 音频上传（UploadOptions.vue，单选 + 算法关系双向绑定）

```vue
<AlgorithmSelector
  v-if="!['noise'].includes(uploadConfig.audioType || '')"
  v-model="uploadConfig.algorithmType"
  v-model:algorithm-relations="uploadConfig.algorithmRelations"
  :initial-params="algorithmParams"
  :show-params="false"
  :single="true"
  @params-change="handleAlgorithmParamsChange"
  @dimensions-change="handleDimensionsChange"
/>
```

说明：`noise` 类型音频不关联算法（避免魔法字符串，类型取值见用例类型枚举）；`dimensions-change` 用于联动评估维度。

### 6.3 批量标注（BatchAnnotationModal.vue，纯选择）

```vue
<AlgorithmSelector
  v-model="algorithmType"
  :show-params="false"
  :single="true"
/>
```

### 6.4 多选模式说明

组件已支持多选（`single=false`，含主算法标记与"设为主"操作），但当前所有调用方均为单选场景；设备"支持算法"的多选编辑由设备管理页自身的表单承载（见《08_Device适配方案》），不经过本组件。

---

## 7. 组件变体

### 7.1 AlgorithmSelectionPanel - 卡片网格选择面板（已落地，替代原 AlgorithmSelectList 方案）

原方案中的 `AlgorithmSelectList.vue` 未落地，E2ETest/APITest 步骤 0 的算法选择由 **`AlgorithmSelectionPanel.vue`**（`frontend/src/components/algorithm/`）承载：

- **形态**：单选卡片网格（分组图标 + 名称 + 分组元信息 + ⚙配置按钮 + 选中态），非下拉
- **Props**：`algorithmList: AlgorithmOption[]`、`selectedAlgorithmType: string | null`、`searchQuery: string`
- **Emits**：`select`（选中算法类型）、`open-config`（打开算法配置弹窗）、`update:searchQuery`
- **数据与编排**：选项加载、选中状态、语音提示（voiceLlmHint 等）由页面 composable（useE2eView / useApiTest）经 `useAlgorithmSelection` 编排，组件本身为纯展示

详细结构见《03_E2ETest适配方案》§8。

### 7.2 AlgorithmRadioGroup - 单选按钮组（未实施）

该变体未落地，无对应组件文件；同类需求已由上述两个组件覆盖（表单场景用 AlgorithmSelector，页面场景用 AlgorithmSelectionPanel），如后续出现密集单选场景再行评估。

---

## 8. 与其他组件的集成

### 8.1 与 DynamicForm 集成（已在 AlgorithmSelector 内部实现）

`AlgorithmSelector` 在 `showParams=true` 时内嵌 `DynamicForm`（`frontend/src/components/algorithm/DynamicForm.vue`）渲染算法参数表单：

```vue
<DynamicForm
  v-if="algorithmFormSchema.fields && algorithmFormSchema.fields.length > 0"
  ref="dynamicFormRef"
  :schema="algorithmFormSchema"
  :initial-values="algorithmParams"
  :show-group-header="true"
  :default-expanded-groups="['basic', 'model']"
  @field-change="onFieldChange"
/>
```

- schema 经 `useAlgorithmConfig().getFormSchema(algorithmType)` 获取（`FormSchema`/`FormField` 结构，camelCase，详见《06_DynamicForm组件适配方案》）
- 字段变更经 `onFieldChange(field, value)` 汇入 `algorithmParams` 并触发 `paramsChange`
- schema 无字段时显示"该算法暂无参数配置"空态

> 早期方案中 `algorithmService.getFormSchema/getDefaultParams` 属废弃口径：服务层已由 `algorithmApi`（Infrastructure 层）+ `useAlgorithmConfig`（Application 层 composable）替代，默认参数由 schema 字段 `defaultValue` 承载，不再有独立接口。

### 8.2 评估维度联动（原 DimensionSelect 方案已调整）

独立 `DimensionSelect.vue` 组件未落地。实际的维度联动路径：

- `AlgorithmSelector` 切换算法后内部调用 `getAssociatedDimensions(algorithmType)`（GET `/api/v1/algorithm/dimensions/:type`），经 `dimensionsChange` 事件向父组件返回 `{ dimensions, dimension_ids }`
- 用例场景由 TestCaseModal 的 `useDimensionConfig.ts` + `DimensionConfigPanel.vue`（`frontend/src/components/common/`）承接维度选择与权重配置（见《02_TestCaseModal适配方案》）
- 评估页面（Evaluation.vue）的维度选择独立实现，不依赖本组件

---

## 9. 性能优化（实际落地：useAlgorithmConfig composable 缓存）

### 9.1 缓存策略（已实施）

原方案的 `useAlgorithmStore`（Pinia）未实施；实际由 **`useAlgorithmConfig`**（`frontend/src/composables/useAlgorithmConfig.ts`，模块级单例状态，符合 Application 层 composable 约定）承担缓存：

```typescript
// 模块级单例（跨组件共享，非 Pinia）
const algorithms = ref<AlgorithmDefinition[]>([])
const formSchemas = ref<Map<string, FormSchema>>(new Map())      // 表单 Schema 缓存（按 algorithmType）
const caseParamCache = ref<Map<string, any[]>>(new Map())        // 用例参数定义缓存（避免循环 watch 重复请求）

// 缓存失效入口
function clearFormSchemaCache() {
  formSchemas.value.clear()
  caseParamCache.value.clear()
}
```

- `getFormSchema(algorithmType)`：命中 `formSchemas` 直接返回，未命中拉取 GET `/api/v1/algorithm/form-schema/:type` 后入缓存
- `getCaseAlgorithmParams(algorithmType)`：命中 `caseParamCache` 直接返回，未命中经 `algorithmApi.getCaseParams` 拉取（并做 snake_case→camelCase 字段兼容归一）后入缓存
- 算法选项列表（`/api/v1/algorithm/options`）不持久缓存，由组件挂载时拉取

### 9.2 懒加载（已实施）

- 表单 Schema/用例参数定义均按需拉取（首次选中某算法时），非页面初始化全量加载
- `AlgorithmSelector` 挂载时仅拉取选项列表，schema 延迟到首次选中触发
- 搜索过滤为前端内存过滤（选项量级小），未做防抖；如后续选项规模增长可评估引入

---

## 10. 实施清单（已完成）

> **与设计稿差异落地记录**：① 原 `AlgorithmSelect.vue` 拆分为 `AlgorithmSelector.vue`（components/common/，表单场景）+ `AlgorithmSelectionPanel.vue`（components/algorithm/，测试页场景）；② 分组分类由后端 `group_name` 下发，前端 categoryLabels 硬编码映射已废弃；③ 数据访问经 `algorithmApi`（Infrastructure）+ `useAlgorithmConfig`（Application composable，formSchemas/caseParamCache 双缓存），原 Pinia `useAlgorithmStore` 方案未采用；④ `DimensionSelect` 独立组件未落地，维度联动经 `dimensionsChange` 事件 + `useDimensionConfig` 承载；⑤ `AlgorithmRadioGroup` 未实施。

### 10.1 组件开发

- [x] 算法选择组件（落地为 AlgorithmSelector.vue + AlgorithmSelectionPanel.vue 两个形态）
- [x] ~~创建 AlgorithmSelectList.vue 组件~~（由 AlgorithmSelectionPanel.vue 替代）
- [x] ~~创建 AlgorithmRadioGroup.vue 组件~~（未实施，需求由前两者覆盖）
- [x] 单选模式支持（single prop，实际调用方均为单选）
- [x] 多选模式支持（主算法标记 + "设为主"，组件已支持，调用方暂未使用）
- [x] 分组渲染（group_name 后端下发，前端零硬编码）
- [x] 搜索过滤功能
- [x] ~~状态显示功能~~（算法选项无在线/离线状态语义，未实施）

### 10.2 集成测试

- [x] TestCaseModal（CaseForm.vue）集成
- [x] E2ETest 集成（AlgorithmSelectionPanel）
- [x] APITest 集成（AlgorithmSelectionPanel）
- [x] UploadOptions.vue（音频上传）集成
- [x] BatchAnnotationModal.vue（批量标注）集成
- [x] ~~Device 页面集成~~（设备支持算法由设备管理页表单承载，见《08_Device适配方案》）
- [x] ~~API管理页面集成~~（API 算法类型由后端数据维护，APIEditModal 未集成编辑控件，见《09_API管理适配方案》）
- [x] ~~Tasks 页面集成~~（任务列表未使用算法选择器）

### 10.3 性能优化

- [x] 缓存策略（useAlgorithmConfig：formSchemas + caseParamCache 双缓存）
- [x] 懒加载（schema 按需拉取，首选中触发）
- [x] 防重复请求（initialParams 快照比对 + caseParamCache 命中短路）
