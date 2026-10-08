# AlgorithmConfigModal - 共用模态窗适配方案

> **落地状态说明**：本方案描述的 AlgorithmConfigModal 组件已完整落地于
> `frontend/src/components/algorithm/AlgorithmConfigModal.vue`。
> 与最初设计稿相比，落地版本在 UI 框架、参数配置结构、分组管理等方面有多处演进，
> 本文已按代码现状修订，差异处以"落地记录"标注。

## 1. 组件概述

### 1.1 组件定位

AlgorithmConfigModal 是一个共用的算法配置模态窗组件（已落地），提供算法定义的
完整生命周期管理能力：列表查看、新建、编辑、启停用、删除、选择。它是
**算法配置化管理能力的唯一入口组件**，供算法配置页与测试页共用。

### 1.2 使用场景（实际挂载点）

| 调用方 | 挂载方式 | 说明 |
|--------|---------|------|
| `views/AlgorithmConfigPage.vue` | `v-model:visible` + `:mode` + `:edit-data` + `@select` + `@success` | 算法配置管理页，完整功能 |
| `views/E2ETest.vue` | `v-model:visible` + `:mode` + `:edit-data` | E2E 测试页步骤 0，经 AlgorithmSelectionPanel 的 `@open-config` 触发 |
| `views/APITest.vue` | `v-model:visible` + `:mode` + `:edit-data` | API 测试页步骤 0，触发链路同上 |

E2E/API 测试页的打开入口为 Application 层 composable
`useAlgorithmSelection.openAlgorithmConfigModal(algo?)`：
- 传入 `algo` 时先经 `GET /api/v1/algorithm/definitions/:type` 加载算法详情，
  以 `mode='edit'` 打开编辑模式；
- 不传时以 `mode='list'` 打开列表模式，供浏览/新建。

> **落地记录**：设计稿中的第 4 个使用场景"TestCaseModal 新建用例时选择算法"未采用本组件。
> 用例弹窗内选择算法由 `AlgorithmSelector`（`components/common/`，见 05 号文档）承担，
> AlgorithmConfigModal 聚焦于算法定义的管理侧，两者职责分离。

### 1.3 核心功能（已实现）

- 查看算法列表（类型/名称/分组/状态/操作 五列，关键字搜索前端过滤）
- 新建算法（基本信息 + 参数配置 + 参考参数 + 参数映射 + 关联维度 五标签页）
- 编辑算法（进入编辑前经 `algorithmApi.getDefinition(type)` 拉取详情回填）
- 禁用/启用（切换 `status: 'online' | 'offline'`）
- 选择算法（`select` 模式，列表行"选择"按钮 emit `select`）
- 删除算法（`useModalControl` 弹出 `BASIC_CONFIRM` 二次确认）
- 所属分组选择与**新建分组**（下拉内置 `+ 新建分组` 选项）
- 参数自动保存（设备/API/用例/参考参数失焦防抖自动入库）
- 功能特性快捷开关（用例参数标签页，按 bundle 批量增删参数）

---

## 2. 现有实现分析

### 2.1 当前组件结构（实际）

```
AlgorithmConfigModal.vue
├── BasicModal                      # 共用模态窗（components/common/modal/）
│   ├── mode-list                   # 列表模式（effectiveMode === 'list'）
│   │   ├── modal-toolbar           # 新建按钮 + 搜索框
│   │   └── table.data-table        # 原生表格：类型/名称/分组/状态/操作
│   └── mode-form                   # 新建/编辑模式（tabs-nav 自绘标签页）
│       ├── basic                   # 基本信息（算法代码/显示名称/所属分组/排序/描述/状态开关）
│       ├── params                  # 参数配置（设备参数 | API参数 | 用例参数 三分栏）
│       ├── reference               # 参考参数（参考字段配置，供评估映射取用）
│       ├── mappings                # 参数映射（设备/API/评估 三段折叠）
│       └── dimensions              # 关联维度（dimension_id / weight / is_default）
└── MappingEditor.vue               # 映射编辑子组件（components/algorithm/）
```

配套的 Application/Infrastructure 依赖：
- `useModalControl`（`composables/useModal`）：删除确认弹窗；
- `useDimensions().fetchAllDimensions()`：评估维度列表（带缓存）；
- `useAlgorithmConfig().clearFormSchemaCache()`：算法定义变更后清空表单 Schema 缓存，
  确保测试页能拉到最新参数定义；
- `algorithmApi`（`utils/api.ts`）：全部数据操作的统一出口（Infrastructure 层）。

### 2.2 当前布局

**列表模式 (effectiveMode='list')**

```
┌──────────────────────────────────────────────────────────────┐
│  算法配置管理                                          [×]    │
├──────────────────────────────────────────────────────────────┤
│  [新建算法]                              [🔍 搜索算法...]     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  类型    │ 名称  │  分组   │ 状态  │      操作         │ │
│  ├────────────────────────────────────────────────────────┤ │
│  │translation│ 翻译 │  翻译   │ 上线  │ 编辑|禁用|选择|删除│ │
│  │   asr    │ ASR  │语音识别 │ 上线  │ 编辑|禁用|选择|删除│ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

**新建/编辑模式 (effectiveMode='create'/'edit')** — 宽 1200px，五个标签页：

```
┌──────────────────────────────────────────────────────────────┐
│  新建算法 / 编辑算法                                    [×]  │
├──────────────────────────────────────────────────────────────┤
│  [基本信息] [参数配置] [参考参数] [参数映射] [关联维度]        │
│  ──────────────────────────────────────────────────────────  │
│  【基本信息】                                                │
│  算法代码*: [________] ← 编辑时禁用（主键，不可变更）         │
│  显示名称*: [________]                                       │
│  所属分组*: [翻译 ▼]  ← 内置「+ 新建分组」选项               │
│  排序:     [0]        描述: [________________________]       │
│  状态:     (开关) 上线/下线                                  │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 差距分析与适配结果

### 3.1 功能差距与落地状态

| 功能点 | 设计稿要求 | 落地状态 |
|--------|-----------|---------|
| UI 框架 | Ant Design Vue | **BasicModal + 原生 HTML 表格/表单/按钮**，样式走 CSS 变量 |
| 模式控制 | props.mode | **props.mode + internalMode 内部切换**（列表页内直达新建/编辑，不关闭弹窗） |
| 分组选择 | 需要 group_id | ✅ **已落地**（下拉选择 + 新建分组，组件内部经 `algorithmApi.getGroups()` 加载） |
| 列表操作 | 编辑/禁用/删除 | ✅ **已落地**（编辑/禁用启用/**选择**/删除 四操作，保留选择模式） |
| 参数映射 | 保持 MappingEditor | ✅ **已落地**（映射编辑器注入用例参数/参考参数/设备/API 参数及主维度上下文） |
| 关联维度 | 新增维度标签页 | ✅ **已落地**（dimensions 标签页，weight + is_default，失焦自动保存） |
| 参数配置 | 单一参数表 | ✅ **演进为三分栏**：设备参数 / API 参数 / 用例参数（含 scope 作用域） |
| 参考参数 | 未覆盖 | ✅ **新增 reference 标签页**（参考字段，供评估参数映射取用） |
| 自动保存 | 未覆盖 | ✅ **新增**（失焦防抖自动入库，见 §5.5） |

### 3.2 适配结论（已实施）

1. ~~UI 框架沿用 Ant Design Vue~~ → 实际沿用项目统一的 **BasicModal + 原生 HTML + CSS 变量** 风格，未引入 Ant Design Vue；
2. ~~Props 传入 groups~~ → 实际**组件内部加载分组**（见 §4.1 落地记录），调用方无需感知分组数据；
3. 分组选择、禁用/启用、关联维度标签页均已落地；
4. 参数配置演进为"设备参数 / API 参数 / 用例参数"三类独立配置，
   用例参数支持 `scope: 'common' | 'api' | 'e2e'` 执行器作用域（对齐三执行器路由口径：
   执行方式由被测设备 `device_type` 路由 E2EExecutor / APISessionExecutor / RealtimeSessionExecutor，
   用例参数的 scope 仅决定该参数在哪个执行器作用域的表单中出现）。

---

## 4. 组件接口

### 4.1 Props

```typescript
interface ModalProps {
  visible: boolean
  mode?: 'list' | 'create' | 'edit' | 'select'
  editData?: AlgorithmRecord | null
}
```

> **落地记录**：设计稿中的 `groups?: AlgorithmGroup[]` prop **未落地**。
> 分组列表由组件内部 `loadGroups()` 经 `algorithmApi.getGroups()`（`GET /api/v1/algorithm/groups`）
> 加载，弹窗打开时与算法/维度一并加载，调用方无需传入。

**AlgorithmRecord**（组件内部接口，snake_case / camelCase 双命名兼容，
对齐后端 convert_keys_to_camel 响应与 Pydantic AliasChoices 双向解析）：

```typescript
interface AlgorithmRecord {
  type: string
  name: string
  group_id?: number
  groupId?: number
  group_name?: string
  description?: string
  status: string                        // 'online' | 'offline'
  icon?: string
  display_order: number
  displayOrder?: number
  device_params?: any[]                 // 设备参数
  deviceParams?: any[]
  api_params?: any[]                    // API 参数
  apiParams?: any[]
  case_params?: any[]                   // 用例参数
  caseParams?: any[]
  mappings?: any                        // { device: [], api: [], evaluation: [] }
  associated_dimensions?: AssociatedDimension[]
  associatedDimensions?: AssociatedDimension[]
  reference_params?: any[]              // 参考参数
  referenceParams?: any[]
}
```

组件内通过 `normalizeParamFields` / `normalizeCaseParamFields` / `normalizeMappings`
做字段归一（`paramCode ?? param_code` 式取值），兼容历史数据与新响应。

### 4.2 Emits

```typescript
interface ModalEmits {
  (e: 'update:visible', visible: boolean): void
  (e: 'select', data: AlgorithmRecord): void
  (e: 'success'): void
}
```

与设计稿一致。

---

## 5. 核心实现要点

### 5.1 分组选择与新建分组

基本信息标签页的"所属分组"下拉内置哨兵选项实现新建分组流：

```typescript
const NEW_GROUP_SENTINEL = '__new_group__'
const creatingNewGroup = ref(false)
const newGroupName = ref('')

// 计算属性双向代理：选中哨兵项时切换到"输入新分组名"态
const groupSelectValue = computed<number | string | null>({
  get: () => (creatingNewGroup.value ? NEW_GROUP_SENTINEL : formState.group_id),
  set: (val) => {
    if (val === NEW_GROUP_SENTINEL) {
      creatingNewGroup.value = true
      newGroupName.value = ''
    } else {
      creatingNewGroup.value = false
      formState.group_id = val === null ? null : Number(val)
    }
  }
})
```

保存算法时若处于新建分组态，先创建分组再回填 `group_id`：

```typescript
if (creatingNewGroup.value) {
  const newGroup = await algorithmApi.createGroup({ name: newGroupName.value.trim() })
  await loadGroups()
  formState.group_id = newGroup.id ?? null
}
```

### 5.2 参数配置三分栏（设备 / API / 用例）

`paramConfigType: 'device' | 'api' | 'case'` 控制三张参数表切换：

- **设备参数 / API 参数**：`param_code`、`param_name`、`direction(input|output)`、
  `param_type(text|audio_stream|audio_file|text_file|rttm|stm|json)`、`required`；
- **用例参数**：额外包含 `scope(common|api|e2e)`、`default_value`、
  范围约束（`min_value` / `max_value` / `step` / `unit`，slider|number 类型时展示）、
  `annotation_code`（标注匹配代码，默认同算法类型）、`field_path`（评估取值路径，默认同参数代码）、
  `help_text`；`param_type` 支持 `text|number|textarea|switch|slider|audio_select|device_select|json`，
  类型变更时经 `getDefaultComponent()` 同步前端渲染组件值；
- 参数代码输入框挂 `datalist`（`PARAM_CODE_PRESETS` 预设字典），选中预设自动回填
  名称/类型/默认值/范围/帮助文本。

### 5.3 状态切换（禁用/启用）

列表操作列保留"选择"按钮（对齐设计稿的 select 模式），启停用切换实现：

```typescript
async function handleToggleStatus(record: AlgorithmRecord) {
  const newStatus = record.status === 'online' ? 'offline' : 'online'
  await algorithmApi.updateDefinition(record.type, { status: newStatus })
  loadAlgorithms()
}
```

状态枚举为 `'online' | 'offline'`（对应"上线 / 下线"），表单侧用
`statusSwitch` 布尔开关代理，保存时回写为枚举值，无魔法字符串散落。

### 5.4 关联评估维度

dimensions 标签页维护 `AlgorithmDimensionRelation` 关联（`dimension_id` + `weight` + `is_default`）：

- 勾选某行为默认维度时，其余行经 `updateDimensionRelation(id, { is_default: false })` 互斥取消；
- 失焦/变更时自动保存：
  - 新增：`POST /api/v1/algorithm/dimension-relations`
  - 更新：`PUT /api/v1/algorithm/dimension-relations/:relationId`
  - 删除：`DELETE /api/v1/algorithm/dimension-relations/:relationId`
- 评估维度下拉数据来自 `useDimensions().fetchAllDimensions()`（Application 层缓存）；
- 评估参数映射可指向任意维度（含子维度），不再按 `dimensionType` 过滤。

> **落地记录**：设计稿草拟的 `POST /api/v1/algorithm/definitions/:type/dimensions`、
> `DELETE /api/v1/algorithm/definitions/:type/dimensions/:id` 两个路径未采用，
> 实际以独立的 `dimension-relations` 资源接口实现（另有 `associateDimensions` 批量关联接口保留可用）。

### 5.5 参数自动保存（防抖）

编辑模式下各参数表失焦即自动入库，避免整表提交丢失中间态：

| 参数类别 | 防抖 | 出口 |
|---------|------|------|
| 设备 / API 参数 | 1500ms | `createParam` / `updateParam`（`POST/PUT /api/v1/algorithm/params`） |
| 用例参数 | 1000ms | `createCaseParam` / `updateCaseParam`（`POST/PUT /api/v1/algorithm/case-params`），保存前校验 `param_code` 重复 |
| 参考参数 | 1000ms | `createReferenceParam` / `updateReferenceParam`（`POST/PUT /api/v1/algorithm/reference-params`），`annotation_code` 为空时自动回填为 `code` |

- 新建模式下算法定义尚未创建，参考参数受外键约束跳过自动保存，
  待 `createDefinition` 成功后由 `savePendingReferenceParams()` 统一补存；
- 行删除失败时回滚行数据并提示（乐观删除 + 失败恢复）；
- 所有定义变更成功后调用 `useAlgorithmConfig().clearFormSchemaCache()` 清空
  表单 Schema 缓存，保证测试页（AlgorithmSelector / DynamicForm）拉取最新参数定义。

### 5.6 功能特性快捷开关（用例参数）

用例参数标签页内置 `FEATURE_BUNDLES` 快捷开关（翻译方向 / 声纹注册 / 干扰人 /
环境设备 / 交叠播放 / Prompt 音频 / 用例配置），每个 bundle 声明
`{ label, scope, params: string[] }`：

- 勾选：按预设批量追加缺失参数（scope 取 bundle 配置）并立即保存；
- 取消：从 `formState` 移除，且已入库参数逐个调用 `deleteCaseParam(id)`；
- 激活态由"bundle 内参数是否全部存在"推导，无冗余状态。

---

## 6. 组件代码说明

> **废弃说明**：设计稿第 6 章"完整修改后的组件代码"为 Ant Design Vue 风格的
> 实施伪代码（a-modal / a-table / a-tabs / a-form），与落地实现差异过大，
> 已从本文移除。组件真实实现以
> `frontend/src/components/algorithm/AlgorithmConfigModal.vue` 为准，
> 结构与实现要点见 §2.1 与 §5，此处不再重复维护代码快照。

落地实现的补充说明：

- 模态窗壳为共用 `BasicModal`（`components/common/modal/BasicModal.vue`），
  列表模式隐藏底部操作区（`show-footer=false`）；
- 标签页为自绘 `tabs-nav`（非 UI 库 Tabs），五页对应 §2.1 结构；
- 列表/表单模式共用一个弹窗实例，`internalMode` 在 list → create/edit 间内部切换，
  取消时若无外部 mode 变更则回落列表模式而非直接关闭弹窗。

---

## 7. 实施清单

### 7.1 需要修改的文件

- [x] `frontend/src/components/algorithm/AlgorithmConfigModal.vue`
  - ~~添加分组下拉选择（基本信息标签页）~~ 已落地（含新建分组）
  - ~~添加禁用/启用按钮~~ 已落地
  - ~~添加关联评估维度标签页~~ 已落地（含 is_default 互斥与自动保存）
  - ~~更新 formState 数据结构~~ 已落地（三分栏参数 + 参考参数 + 关联维度）
  - ~~更新表单校验~~ 以 `handleOk` 内必填校验实现（未引入声明式 FormRules）

### 7.2 功能实现

- [x] 列表模式（现有）
- [x] 新建模式（现有）
- [x] 编辑模式（现有，进入前加载详情回填）
- [x] 选择模式（现有）
- [x] 分组选择功能（已落地，含新建分组）
- [x] 禁用/启用功能（已落地）
- [x] 关联评估维度（已落地）
- [x] 参考参数配置（已落地，设计稿外新增）
- [x] 参数自动保存（已落地，设计稿外新增）
- [x] 功能特性快捷开关（已落地，设计稿外新增）

### 7.3 API 依赖（均经 `algorithmApi` / `useDimensions` 出口访问，前缀 `/api/v1`）

- [x] `GET /algorithm/definitions` - 获取算法列表
- [x] `GET /algorithm/definitions/:type` - 获取算法详情（编辑回填）
- [x] `POST /algorithm/definitions` - 创建算法
- [x] `PUT /algorithm/definitions/:type` - 更新算法（含状态启停用）
- [x] `DELETE /algorithm/definitions/:type` - 删除算法
- [x] `GET /algorithm/groups` - 获取算法分组列表
- [x] `POST /algorithm/groups` - 创建分组（新建分组流）
- [x] `POST /algorithm/params`、`PUT /algorithm/params/:id` - 设备/API 参数自动保存
- [x] `POST /algorithm/case-params`、`PUT /algorithm/case-params/:id`、`DELETE /algorithm/case-params/:id` - 用例参数管理
- [x] `POST /algorithm/reference-params`、`PUT /algorithm/reference-params/:id`、`DELETE /algorithm/reference-params/:id` - 参考参数管理
- [x] `POST /algorithm/dimension-relations`、`PUT /algorithm/dimension-relations/:id`、`DELETE /algorithm/dimension-relations/:id` - 维度关联管理
- [x] 评估维度列表 - 经 `useDimensions().fetchAllDimensions()`（Application 层缓存），不再直接调用 `/evaluation/dimensions`
