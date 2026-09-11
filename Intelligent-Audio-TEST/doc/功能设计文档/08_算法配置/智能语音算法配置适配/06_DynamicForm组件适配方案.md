# DynamicForm - 动态表单组件适配方案

## 1. 组件概述

### 1.1 组件定位
DynamicForm 是一个根据 Schema 动态渲染表单的通用组件（已落地：`frontend/src/components/algorithm/DynamicForm.vue`），用于统一渲染算法参数配置表单。

### 1.2 使用场景（实际调用方）
- AlgorithmSelector.vue：算法选择时内嵌渲染参数表单（`show-params=true` 分支）
- AlgorithmParamsConfig.vue（AlgorithmConfigPage）：算法参数定义的实时预览/编辑
- TestCaseModal/sections/AlgoParamsStep.vue：用例参数按轮配置的参数表单
- BatchAlgorithmParamsModal.vue：批量修改用例算法参数

### 1.3 核心功能
- 根据 Schema 动态渲染表单字段（字段控件由 Schema 的 `component` 字段指定）
- 支持多种控件类型（input、textarea、input-number、select、slider、switch、code-editor）
- 支持字段分组显示与折叠（`show-group-header` + `default-expanded-groups`）
- 支持 scope 过滤（`scope: 'api' | 'e2e'`，仅渲染当前执行器作用域的字段）
- 支持字段验证（必填/正则/长度/数值范围）
- 支持字段隐藏（Schema `hidden` 字段静态隐藏）

---

## 2. 组件设计

### 2.1 组件结构

```
DynamicForm.vue
├── .form-groups              # 分组容器（showGroupHeader=true 且 schema.groups 非空）
│   └── .form-group-item      # 分组项
│       ├── .group-header     # 分组标题（可点击展开/收起）
│       └── .group-content    # 分组内容
│           └── .form-row     # 表单行
│               └── .form-group  # 表单字段组
│                   ├── label    # 字段标签
│                   └── input/select/textarea  # 字段控件
└── .form-rows                # 扁平容器（不分组显示）
```

### 2.2 组件布局

```
┌─────────────────────────────────────────────────────────────────────────┐
│  算法参数配置                                                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ▼ 基本配置                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  翻译方向: [中译英 ▼]                                             │   │
│  │  帮助文本: 选择翻译的源语言和目标语言                               │   │
│  │                                                                │   │
│  │  参考文本: [________________________________]                    │   │
│  │  帮助文本: 用于 ASR 识别结果对比                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ▶ 模型配置                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  采样率:   [━━━●━━━━] [16000]      （slider 滑块 + 数字输入双控件） │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ▶ 高级选项                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  置信度阈值: [━━━●━━━━] [0.8]                                    │   │
│  │  调试模式:   [○ 开启]                                            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 组件接口

### 3.1 Props（实际定义）

```typescript
interface Props {
  // 表单 Schema
  schema: FormSchema;
  
  // 初始值（编辑回填）
  initialValues?: Record<string, any>;
  
  // 是否禁用
  disabled?: boolean;
  
  // 是否显示分组折叠
  showGroupHeader?: boolean;
  
  // 默认展开的分组
  defaultExpandedGroups?: string[];
  
  // 标签宽度（CSS 值）
  labelWidth?: string;
  
  // 执行器作用域过滤（'api' | 'e2e'，缺省不过滤）
  scope?: 'api' | 'e2e';
}
```

### 3.2 Emits

```typescript
interface DynamicFormEmits {
  // 更新表单值
  (e: 'update:modelValue', values: Record<string, any>): void;
  
  // 字段变化时触发
  (e: 'change', field: FieldSchema, value: any): void;
  
  // 字段变化时触发（带所有值）
  (e: 'fieldChange', fieldCode: string, value: any, allValues: Record<string, any>): void;
  
  // 表单验证结果
  (e: 'validate', valid: boolean, errors: Record<string, string>): void;
}
```

### 3.3 Expose

```typescript
interface DynamicFormExpose {
  // 获取表单值
  getValues: () => Record<string, any>;
  
  // 设置表单值
  setValues: (values: Record<string, any>) => void;
  
  // 验证表单
  validate: () => Promise<boolean>;
  
  // 验证单个字段
  validateField: (fieldCode: string) => Promise<boolean>;
  
  // 重置表单
  reset: () => void;
  
  // 清空验证
  clearValidate: () => void;
}
```

---

## 4. 数据结构

### 4.1 FormSchema

Schema 由后端 GET `/api/v1/algorithm/form-schema/:type` 下发（响应统一 camelCase），与 `useAlgorithmConfig.ts` 中 `FormSchema` 接口一致：

```typescript
interface FormSchema {
  // 算法类型
  algorithmType: string;
  
  // 算法名称
  algorithmName: string;
  
  // 分组 ID/分组名（可选，来自算法分组配置）
  group_id?: number;
  group_name?: string;
  
  // 描述（可选）
  description?: string;
  
  // 分组列表
  groups: FormGroup[];
  
  // 扁平字段列表
  fields: FieldSchema[];
}
```

### 4.2 FormGroup

```typescript
interface FormGroup {
  // 分组名称（如 'basic'、'model'，用于 default-expanded-groups）
  name: string;
  
  // 分组标签
  label: string;
  
  // 分组字段
  fields: FieldSchema[];
}
```

### 4.3 FieldSchema

> 命名口径：组件内部接口名为 `FieldSchema`（部分上下文亦称 `FormFieldSchema`/`FormField`，字段结构一致，见 `useAlgorithmConfig.ts` 的 `FormField`）。

```typescript
interface FieldSchema {
  // 字段代码（参数提交键，如 translation_direction）
  fieldCode: string;
  
  // 字段名称（显示标签）
  fieldName: string;
  
  // 字段类型（string/number/boolean/select/multiselect/json/timestamp）
  fieldType: string;
  
  // 是否必填
  required: boolean;
  
  // 默认值
  defaultValue?: any;
  
  // 前端组件（input/textarea/input-number/select/slider/switch/code-editor）
  component?: string;
  
  // 选项列表（select 类型）
  options?: { value: string; label: string }[];
  
  // 验证规则
  validation?: {
    min?: number;
    max?: number;
    step?: number;
    pattern?: string;
    patternMessage?: string;
    minLength?: number;
    maxLength?: number;
  };
  
  // 帮助文本
  helpText?: string;
  
  // 是否隐藏
  hidden?: boolean;
  
  // UI 排序
  uiOrder?: number;
  
  // UI 分组
  uiGroup?: string;
  
  // 执行器作用域（'api' | 'e2e' | 'common'，缺省视为通用；配合 Props.scope 过滤）
  scope?: string;
}
```

### 4.4 类型缺省值映射（initFormData 使用）

```typescript
const getDefaultByType = (fieldType: string) => {
  const defaults: Record<string, any> = {
    'string': '',
    'number': 0,
    'boolean': false,
    'select': '',
    'multiselect': [],
    'json': '{}',
    'timestamp': ''
  }
  return defaults[fieldType] ?? ''
}
```

---

## 5. 组件实现（实际实现要点）

> 实际落地组件约 800 行（原生 HTML + CSS，无第三方表单库），以下为关键实现摘要，完整代码见 `frontend/src/components/algorithm/DynamicForm.vue`。

### 5.1 scope 作用域过滤

```typescript
const filterByScope = (fields: FieldSchema[]): FieldSchema[] => {
  if (!props.scope) return fields
  return fields.filter(f => !f.scope || f.scope === 'common' || f.scope === props.scope)
}
```

- `visibleGroups`/`visibleFields` 均先经 `filterByScope` 再过滤 `hidden`
- `validate` 仅校验当前 scope 可见字段，防止被过滤字段的必填规则误报

### 5.2 表单数据初始化与回填

- `initFormData`：按 `initialValues[fieldCode]` > `field.defaultValue` > `getDefaultByType(fieldType)` 优先级取值；**schema 之外的外部键仅保留"不属于 schema 定义"的键**（防止被 scope 过滤掉的字段泄露进提交数据）
- `initialValues` watch（deep）：仅更新当前 scope 可见的 schema 字段或不属于 schema 的外部键
- `schema` watch（immediate + deep）：schema 变化（切换算法）时重新初始化

### 5.3 控件渲染与变更事件

- 分组/扁平两套渲染分支，控件模板一致（input/textarea/input-number/select/slider/switch/code-editor，未知 component 回落 text input）
- `handleFieldChange` 依次触发 `change` / `fieldChange` / `update:modelValue`
- slider 为 **range 滑块 + 数字输入双控件**（双向同步，均以 `@input` 触发变更），便于精确输入

### 5.4 字段验证

`validateFieldInternal` 覆盖：必填（按控件类型区分"请输入/请选择"文案）、正则（pattern + patternMessage）、长度（minLength/maxLength）、数值范围（input-number 的 min/max）。`validate` 汇总所有 scope 可见字段并 emit `validate`。

---

## 6. 字段类型与组件映射

### 6.1 映射关系（component 由后端 Schema 直接指定）

| component 值 | HTML 元素 | 说明 |
|---------|----------|------|
| input | `<input type="text">` | 文本输入 |
| textarea | `<textarea>` | 多行文本 |
| input-number | `<input type="number">` | 数字输入（带 min/max/step） |
| select | `<select>` | 下拉选择 |
| slider | `<input type="range">` + `<input type="number">` | 滑块 + 数字输入双控件 |
| switch | `<input type="checkbox">` | 开关 |
| code-editor | `<textarea>`（等宽字体） | JSON/代码编辑（简化版） |

说明：字段控件由 Schema 的 `component` 字段**直接指定**（后端算法参数定义的 `component` 配置项），组件内未实现 fieldType→component 的自动映射；未识别的 component 回落为文本输入。

### 6.2 fieldType 与缺省值

`fieldType` 用于初始化缺省值（见 §4.4），与 `component` 解耦：如 `multiselect` 类型缺省值为 `[]`，当前无专属多选控件分支（回落文本输入）；`timestamp` 类型缺省值为 `''`。

---

## 7. 字段联动（未实施）

原方案设计的 `FieldLinkage` 配置（triggerField/triggerValue/action → show/hide/setValue/setOptions）**未在组件中实现**。当前的动态显隐仅支持 Schema 级静态 `hidden` 字段。若后续出现字段间联动需求，建议以配置化方式扩展 Schema（拒绝硬编码联动逻辑），届时再评估实现。

---

## 8. 使用示例（实际调用方摘录）

### 8.1 AlgorithmSelector 内嵌渲染（showParams=true 分支）

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

说明：schema 经 `useAlgorithmConfig().getFormSchema(algorithmType)` 获取（带缓存）；`onFieldChange(field, value)` 汇入参数对象并向上 emit `paramsChange`。

### 8.2 用例参数步骤（TestCaseModal/sections/AlgoParamsStep.vue）

用例参数按轮配置中，DynamicForm 承载单轮参数编辑，外层由 RoundConfigEditor 按轮组织（每轮独立表单实例），参数提交结构为按轮分组的 `algorithm_params`（见《02_TestCaseModal适配方案》）。

### 8.3 表单验证与取值

```typescript
const valid = await formRef.value?.validate()
if (valid) {
  const values = formRef.value?.getValues()
}
```

---

## 9. 样式规范

### 9.1 现状说明

组件样式为 scoped CSS，**当前硬编码色值/间距**（如主题橙 `#FF6A00`、边框 `#E5E7EB`、间距 16px、圆角 8px 等），未引用全局 CSS 变量。与设计系统变量的统一属后续样式治理事项（避免在此组件内继续新增魔法色值）。

### 9.2 样式类

| 类名 | 用途 |
|-----|------|
| `.form-groups` / `.form-group-item` | 分组容器/分组项 |
| `.group-header` / `.group-title` | 分组标题（可折叠） |
| `.form-row` / `.form-group` | 表单行布局/字段组 |
| `.form-input` | 输入控件样式 |
| `.slider-field` / `.slider-input` / `.slider-number-input` | 滑块双控件 |
| `.switch-container` / `.switch-slider` | 开关 |
| `.help-text` | 帮助文本 |
| `.error-message` | 错误提示 |

---

## 10. 性能优化（未实施项）

- **防抖**：字段变更事件未做防抖（`change` 事件在控件失焦/变更时触发，高频 slider 以 `@input` 直通；如出现性能问题可对 `fieldChange` 引入防抖）
- **虚拟滚动**：未引入虚拟列表（当前算法参数字段量级小，无必要；依赖 `@vueuse/core` 的方案仅为备选）
- **Schema 缓存**：不在组件内处理，由 `useAlgorithmConfig` 的 `formSchemas` 缓存承担（见《05_AlgorithmSelect组件适配方案》§9）

---

## 11. 实施清单（已完成）

> **与设计稿差异落地记录**：① 实际组件位于 `frontend/src/components/algorithm/DynamicForm.vue`（原生 HTML + CSS 实现，与设计稿结构一致）；② 新增设计稿未覆盖的 **scope 作用域过滤**（api/e2e/common）与 slider 数字输入双控件；③ **字段联动（FieldLinkage）未实施**，动态显隐仅支持 Schema 静态 hidden；④ 样式为 scoped 硬编码色值，未接入 CSS 变量。

### 11.1 组件开发

- [x] DynamicForm.vue 主组件（原生 HTML + CSS）
- [x] 分组折叠功能
- [x] 各字段类型控件渲染（input/textarea/input-number/select/slider/switch/code-editor）
- [x] 字段验证（必填/正则/长度/数值范围）
- [x] 字段隐藏（Schema 静态 hidden）
- [x] scope 作用域过滤（api/e2e/common，设计稿外补充）

### 11.2 功能实现

- [x] Schema 解析与初始化（initialValues > defaultValue > 类型缺省值）
- [x] 外部键保留策略（防 scope 过滤字段泄露进提交数据）
- [x] 分组折叠（default-expanded-groups）
- [x] ~~字段联动~~（未实施，见 §7）

### 11.3 集成测试

- [x] AlgorithmSelector 集成（showParams=true 内嵌）
- [x] AlgorithmConfigPage/AlgorithmParamsConfig 集成
- [x] TestCaseModal（AlgoParamsStep 按轮参数）集成
- [x] BatchAlgorithmParamsModal 集成
- [x] 不同字段类型与验证规则测试
- [x] ~~字段联动测试~~（随联动功能一并取消）
