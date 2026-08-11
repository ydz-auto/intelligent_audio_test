# DynamicForm - 动态表单组件适配方案

## 1. 组件概述

### 1.1 组件定位
DynamicForm 是一个根据 Schema 动态渲染表单的通用组件，用于在多个页面中统一提供算法参数配置功能。

### 1.2 使用场景
- TestCaseModal：用例参数配置
- E2ETest：E2E测试参数配置
- APITest：API测试参数配置
- Device：设备算法参数配置
- AlgorithmConfigPage：算法参数定义

### 1.3 核心功能
- 根据 Schema 动态渲染表单字段
- 支持多种字段类型（input、select、number、slider、switch、textarea、code-editor）
- 支持字段分组显示
- 支持字段验证
- 支持字段联动
- 支持字段隐藏

---

## 2. 组件设计

### 2.1 组件结构

```
DynamicForm.vue
├── .form-groups              # 分组容器
│   └── .form-group-item      # 分组项
│       ├── .group-header     # 分组标题（可点击展开/收起）
│       └── .group-content    # 分组内容
│           └── .form-row     # 表单行
│               └── .form-group  # 表单字段组
│                   ├── label    # 字段标签
│                   └── input/select/textarea  # 字段控件
└── ...
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
│  │  采样率:   [16kHz ▼]                                             │   │
│  │  模型大小: [base ▼]                                              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ▶ 高级选项                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  置信度阈值: [━━━●━━━━] 0.8                                      │   │
│  │  调试模式:   [○ 开启]                                            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 组件接口

### 3.1 Props

```typescript
interface DynamicFormProps {
  // 表单 Schema
  schema: FormSchema;
  
  // 初始值
  initialValues?: Record<string, any>;
  
  // 是否禁用
  disabled?: boolean;
  
  // 是否显示分组折叠
  showGroupHeader?: boolean;
  
  // 默认展开的分组
  defaultExpandedGroups?: string[];
  
  // 标签宽度（CSS 值）
  labelWidth?: string;
}
```

### 3.2 Emits

```typescript
interface DynamicFormEmits {
  // 更新表单值
  (e: 'update:modelValue', values: Record<string, any>): void;
  
  // 字段变化时触发
  (e: 'change', field: FormFieldSchema, value: any): void;
  
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

```typescript
interface FormSchema {
  // 算法类型
  algorithmType: string;
  
  // 算法名称
  algorithmName: string;
  
  // 分类
  category: string;
  
  // 描述
  description: string;
  
  // 分组列表
  groups: FormGroup[];
  
  // 扁平字段列表
  fields: FormFieldSchema[];
}
```

### 4.2 FormGroup

```typescript
interface FormGroup {
  // 分组名称
  name: string;
  
  // 分组标签
  label: string;
  
  // 分组字段
  fields: FormFieldSchema[];
}
```

### 4.3 FormFieldSchema

```typescript
interface FormFieldSchema {
  // 字段代码
  fieldCode: string;
  
  // 字段名称
  fieldName: string;
  
  // 字段类型
  fieldType: 'string' | 'number' | 'boolean' | 'select' | 'multiselect' | 'json';
  
  // 是否必填
  required: boolean;
  
  // 默认值
  defaultValue: any;
  
  // 前端组件
  component: 'input' | 'input-number' | 'select' | 'textarea' | 'slider' | 'switch' | 'code-editor';
  
  // 选项列表（select 类型）
  options?: Array<{ label: string; value: any }>;
  
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
  hidden: boolean;
  
  // UI 排序
  uiOrder: number;
  
  // UI 分组
  uiGroup: string;
}
```

---

## 5. 组件实现

### 5.1 DynamicForm 主组件

```vue
<!-- src/components/algorithm/DynamicForm.vue -->
<template>
  <div class="dynamic-form">
    <!-- 按分组显示 -->
    <div v-if="showGroupHeader && schema.groups.length > 0" class="form-groups">
      <div
        v-for="group in visibleGroups"
        :key="group.name"
        class="form-group-item"
      >
        <div class="group-header" @click="toggleGroup(group.name)">
          <span class="group-icon">{{ isGroupExpanded(group.name) ? '▼' : '▶' }}</span>
          <span class="group-title">{{ group.label }}</span>
        </div>
        <div v-show="isGroupExpanded(group.name)" class="group-content">
          <div
            v-for="field in getVisibleFields(group.fields)"
            :key="field.fieldCode"
            class="form-row"
          >
            <div class="form-group">
              <label :for="field.fieldCode" :class="{ required: field.required }">
                {{ field.fieldName }}
              </label>
              
              <!-- 输入框 -->
              <input
                v-if="field.component === 'input'"
                :id="field.fieldCode"
                v-model="formData[field.fieldCode]"
                type="text"
                class="form-input"
                :placeholder="`请输入${field.fieldName}`"
                :disabled="disabled"
                @change="handleFieldChange(field, $event)"
              />
              
              <!-- 文本域 -->
              <textarea
                v-else-if="field.component === 'textarea'"
                :id="field.fieldCode"
                v-model="formData[field.fieldCode]"
                class="form-input"
                rows="3"
                :placeholder="`请输入${field.fieldName}`"
                :disabled="disabled"
                @change="handleFieldChange(field, $event)"
              ></textarea>
              
              <!-- 数字输入 -->
              <input
                v-else-if="field.component === 'input-number'"
                :id="field.fieldCode"
                v-model.number="formData[field.fieldCode]"
                type="number"
                class="form-input"
                :min="field.validation?.min"
                :max="field.validation?.max"
                :step="field.validation?.step ?? 1"
                :disabled="disabled"
                @change="handleFieldChange(field, $event)"
              />
              
              <!-- 下拉选择 -->
              <select
                v-else-if="field.component === 'select'"
                :id="field.fieldCode"
                v-model="formData[field.fieldCode]"
                class="form-input"
                :disabled="disabled"
                @change="handleFieldChange(field, $event)"
              >
                <option value="">请选择{{ field.fieldName }}</option>
                <option
                  v-for="opt in field.options"
                  :key="opt.value"
                  :value="opt.value"
                >
                  {{ opt.label }}
                </option>
              </select>
              
              <!-- 滑块 -->
              <div v-else-if="field.component === 'slider'" class="slider-field">
                <input
                  :id="field.fieldCode"
                  v-model.number="formData[field.fieldCode]"
                  type="range"
                  class="slider-input"
                  :min="field.validation?.min ?? 0"
                  :max="field.validation?.max ?? 100"
                  :step="field.validation?.step ?? 1"
                  :disabled="disabled"
                  @change="handleFieldChange(field, $event)"
                />
                <span class="slider-value">{{ formatSliderValue(formData[field.fieldCode], field) }}</span>
              </div>
              
              <!-- 开关 -->
              <label v-else-if="field.component === 'switch'" class="switch-container">
                <input
                  :id="field.fieldCode"
                  v-model="formData[field.fieldCode]"
                  type="checkbox"
                  class="switch-input"
                  :disabled="disabled"
                  @change="handleFieldChange(field, $event)"
                />
                <span class="switch-slider"></span>
              </label>
              
              <!-- 代码编辑器（简化版 textarea） -->
              <textarea
                v-else-if="field.component === 'code-editor'"
                :id="field.fieldCode"
                v-model="formData[field.fieldCode]"
                class="form-input code-editor"
                rows="6"
                :placeholder="`请输入${field.fieldName}`"
                :disabled="disabled"
                @change="handleFieldChange(field, $event)"
              ></textarea>
              
              <!-- 默认：输入框 -->
              <input
                v-else
                :id="field.fieldCode"
                v-model="formData[field.fieldCode]"
                type="text"
                class="form-input"
                :placeholder="`请输入${field.fieldName}`"
                :disabled="disabled"
                @change="handleFieldChange(field, $event)"
              />
              
              <!-- 帮助文本 -->
              <div v-if="field.helpText" class="help-text">{{ field.helpText }}</div>
              
              <!-- 错误提示 -->
              <div v-if="errors[field.fieldCode]" class="error-message">
                {{ errors[field.fieldCode] }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 不分组显示 -->
    <div v-else class="form-rows">
      <div
        v-for="field in visibleFields"
        :key="field.fieldCode"
        class="form-row"
      >
        <div class="form-group">
          <label :for="field.fieldCode" :class="{ required: field.required }">
            {{ field.fieldName }}
          </label>
          <!-- 字段控件同上 -->
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';

interface Props {
  schema: FormSchema;
  initialValues?: Record<string, any>;
  disabled?: boolean;
  showGroupHeader?: boolean;
  defaultExpandedGroups?: string[];
  labelWidth?: string;
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  showGroupHeader: true,
  defaultExpandedGroups: () => ['basic'],
  labelWidth: '120px'
});

const emit = defineEmits<{
  (e: 'update:modelValue', values: Record<string, any>): void;
  (e: 'change', field: FormFieldSchema, value: any): void;
  (e: 'fieldChange', fieldCode: string, value: any, allValues: Record<string, any>): void;
  (e: 'validate', valid: boolean, errors: Record<string, string>): void;
}>();

// 表单数据
const formData = ref<Record<string, any>>({});
const errors = ref<Record<string, string>>({});
const expandedGroups = ref<Set<string>>(new Set(props.defaultExpandedGroups));

// 可见的分组
const visibleGroups = computed(() => {
  return props.schema.groups.filter(group => 
    getVisibleFields(group.fields).length > 0
  );
});

// 可见的字段（扁平列表）
const visibleFields = computed(() => {
  return getVisibleFields(props.schema.fields);
});

// 获取可见字段
const getVisibleFields = (fields: FormFieldSchema[]) => {
  return fields.filter(f => !f.hidden);
};

// 判断分组是否展开
const isGroupExpanded = (groupName: string) => {
  return expandedGroups.value.has(groupName);
};

// 切换分组展开状态
const toggleGroup = (groupName: string) => {
  if (expandedGroups.value.has(groupName)) {
    expandedGroups.value.delete(groupName);
  } else {
    expandedGroups.value.add(groupName);
  }
};

// 初始化表单数据
const initFormData = () => {
  const values: Record<string, any> = {};
  
  for (const field of props.schema.fields) {
    const initialValue = props.initialValues?.[field.fieldCode];
    values[field.fieldCode] = initialValue ?? field.defaultValue ?? getDefaultByType(field.fieldType);
  }
  
  formData.value = values;
};

// 根据类型获取默认值
const getDefaultByType = (fieldType: string) => {
  const defaults: Record<string, any> = {
    'string': '',
    'number': 0,
    'boolean': false,
    'select': null,
    'multiselect': [],
    'json': '{}'
  };
  return defaults[fieldType] ?? null;
};

// 处理字段变化
const handleFieldChange = (field: FormFieldSchema, event: Event) => {
  const value = (event.target as HTMLInputElement).value;
  emit('change', field, formData.value[field.fieldCode]);
  emit('fieldChange', field.fieldCode, formData.value[field.fieldCode], formData.value);
  emit('update:modelValue', formData.value);
};

// 格式化滑块值
const formatSliderValue = (value: any, field: FormFieldSchema) => {
  if (field.validation?.max === 1) {
    return `${((value || 0) * 100).toFixed(0)}%`;
  }
  return value ?? 0;
};

// 验证单个字段
const validateFieldInternal = (field: FormFieldSchema): string | null => {
  const value = formData.value[field.fieldCode];
  
  // 必填验证
  if (field.required && (value === null || value === undefined || value === '')) {
    return `请${field.component === 'select' ? '选择' : '输入'}${field.fieldName}`;
  }
  
  // 正则验证
  if (field.validation?.pattern && value) {
    const regex = new RegExp(field.validation.pattern);
    if (!regex.test(value)) {
      return field.validation.patternMessage || `${field.fieldName}格式不正确`;
    }
  }
  
  // 长度验证
  if (field.validation?.minLength && value && value.length < field.validation.minLength) {
    return `${field.fieldName}长度不能少于${field.validation.minLength}个字符`;
  }
  if (field.validation?.maxLength && value && value.length > field.validation.maxLength) {
    return `${field.fieldName}长度不能超过${field.validation.maxLength}个字符`;
  }
  
  // 数值范围验证
  if (field.component === 'input-number' && value !== null && value !== undefined) {
    if (field.validation?.min !== undefined && value < field.validation.min) {
      return `${field.fieldName}不能小于${field.validation.min}`;
    }
    if (field.validation?.max !== undefined && value > field.validation.max) {
      return `${field.fieldName}不能大于${field.validation.max}`;
    }
  }
  
  return null;
};

// 获取表单值
const getValues = () => {
  return { ...formData.value };
};

// 设置表单值
const setValues = (values: Record<string, any>) => {
  for (const [key, value] of Object.entries(values)) {
    formData.value[key] = value;
  }
  emit('update:modelValue', formData.value);
};

// 验证表单
const validate = async (): Promise<boolean> => {
  const newErrors: Record<string, string> = {};
  
  for (const field of props.schema.fields) {
    const error = validateFieldInternal(field);
    if (error) {
      newErrors[field.fieldCode] = error;
    }
  }
  
  errors.value = newErrors;
  const valid = Object.keys(newErrors).length === 0;
  emit('validate', valid, newErrors);
  return valid;
};

// 验证单个字段
const validateField = async (fieldCode: string): Promise<boolean> => {
  const field = props.schema.fields.find(f => f.fieldCode === fieldCode);
  if (!field) return true;
  
  const error = validateFieldInternal(field);
  if (error) {
    errors.value[fieldCode] = error;
    return false;
  } else {
    delete errors.value[fieldCode];
    return true;
  }
};

// 重置表单
const reset = () => {
  initFormData();
  errors.value = {};
};

// 清空验证
const clearValidate = () => {
  errors.value = {};
};

// 监听 schema 变化
watch(() => props.schema, () => {
  initFormData();
}, { immediate: true, deep: true });

// 监听初始值变化
watch(() => props.initialValues, (newValues) => {
  if (newValues) {
    for (const [key, value] of Object.entries(newValues)) {
      formData.value[key] = value;
    }
  }
}, { deep: true });

// 暴露方法
defineExpose({
  getValues,
  setValues,
  validate,
  validateField,
  reset,
  clearValidate
});
</script>

<style scoped>
.dynamic-form {
  width: 100%;
}

/* 分组样式 */
.form-groups {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.form-group-item {
  border: var(--card-border);
  border-radius: var(--border-radius-lg);
  overflow: hidden;
}

.group-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background-color: var(--background-secondary);
  cursor: pointer;
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  transition: background-color var(--transition-fast);
}

.group-header:hover {
  background-color: var(--background-tertiary);
}

.group-icon {
  font-size: 12px;
  color: var(--text-secondary);
  transition: transform var(--transition-fast);
}

.group-title {
  flex: 1;
}

.group-content {
  padding: var(--spacing-md);
}

/* 表单行样式 */
.form-row {
  display: flex;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.form-row:last-child {
  margin-bottom: 0;
}

.form-group {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.form-group label {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.form-group label.required::after {
  content: ' *';
  color: var(--danger-color);
}

/* 使用全局表单样式 */
.form-group :deep(.form-input) {
  width: 100%;
  height: 40px;
  padding: 0 var(--spacing-md);
  border: 1px solid var(--gray-light-color);
  border-radius: var(--border-radius-md);
  font-size: var(--font-size-md);
  color: var(--text-primary);
  background-color: var(--background-primary);
  transition: all var(--transition-normal);
  box-sizing: border-box;
  outline: none;
}

.form-group :deep(.form-input:hover) {
  border-color: var(--primary-color);
}

.form-group :deep(.form-input:focus) {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px var(--primary-light);
}

.form-group :deep(textarea.form-input) {
  height: auto;
  min-height: 80px;
  padding: var(--spacing-sm) var(--spacing-md);
  resize: vertical;
}

/* 滑块样式 */
.slider-field {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.slider-input {
  flex: 1;
  height: 6px;
  -webkit-appearance: none;
  appearance: none;
  background: var(--gray-light-color);
  border-radius: var(--border-radius-full);
  outline: none;
}

.slider-input::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  background: var(--primary-color);
  border-radius: 50%;
  cursor: pointer;
  transition: transform var(--transition-fast);
}

.slider-input::-webkit-slider-thumb:hover {
  transform: scale(1.1);
}

.slider-value {
  min-width: 50px;
  text-align: right;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

/* 开关样式 */
.switch-container {
  position: relative;
  display: inline-block;
  width: 48px;
  height: 24px;
}

.switch-input {
  opacity: 0;
  width: 0;
  height: 0;
}

.switch-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--gray-light-color);
  border-radius: var(--border-radius-full);
  transition: var(--transition-fast);
}

.switch-slider::before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  border-radius: 50%;
  transition: var(--transition-fast);
}

.switch-input:checked + .switch-slider {
  background-color: var(--primary-color);
}

.switch-input:checked + .switch-slider::before {
  transform: translateX(24px);
}

/* 代码编辑器样式 */
.code-editor {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: var(--font-size-sm);
  line-height: 1.5;
}

/* 帮助文本 */
.help-text {
  font-size: var(--font-size-xs);
  color: var(--text-light);
  line-height: 1.4;
}

/* 错误提示 */
.error-message {
  font-size: var(--font-size-xs);
  color: var(--danger-color);
  line-height: 1.4;
}
</style>
```

---

## 6. 字段类型与组件映射

### 6.1 映射关系

| 字段类型 | 前端组件 | HTML 元素 | 说明 |
|---------|---------|----------|------|
| string | input | `<input type="text">` | 文本输入 |
| number | input-number | `<input type="number">` | 数字输入 |
| boolean | switch | `<input type="checkbox">` | 开关 |
| select | select | `<select>` | 下拉选择 |
| multiselect | select (multiple) | `<select multiple>` | 多选下拉 |
| json | code-editor | `<textarea>` | JSON编辑器 |

### 6.2 特殊字段类型

```typescript
// 根据字段类型自动选择组件
const getDefaultComponent = (fieldType: string): string => {
  const componentMap: Record<string, string> = {
    'string': 'input',
    'text': 'textarea',
    'number': 'input-number',
    'boolean': 'switch',
    'select': 'select',
    'multiselect': 'select',
    'json': 'code-editor',
    'slider': 'slider'
  };
  return componentMap[fieldType] || 'input';
};
```

---

## 7. 字段联动

### 7.1 联动配置

```typescript
interface FieldLinkage {
  // 触发字段
  triggerField: string;
  
  // 触发值
  triggerValue: any;
  
  // 目标字段
  targetField: string;
  
  // 联动动作
  action: 'show' | 'hide' | 'setValue' | 'setOptions';
  
  // 联动值
  value?: any;
}
```

### 7.2 联动处理

```typescript
// 处理字段联动
const handleFieldLinkage = (fieldCode: string, value: any) => {
  const linkages = props.schema.linkages || [];
  
  for (const linkage of linkages) {
    if (linkage.triggerField === fieldCode && linkage.triggerValue === value) {
      switch (linkage.action) {
        case 'show':
          showField(linkage.targetField);
          break;
        case 'hide':
          hideField(linkage.targetField);
          break;
        case 'setValue':
          setFieldValue(linkage.targetField, linkage.value);
          break;
        case 'setOptions':
          setFieldOptions(linkage.targetField, linkage.value);
          break;
      }
    }
  }
};
```

---

## 8. 使用示例

### 8.1 基本使用

```vue
<template>
  <DynamicForm
    ref="formRef"
    :schema="formSchema"
    v-model="formData"
    @change="handleFieldChange"
  />
</template>

<script setup lang="ts">
const formRef = ref();
const formSchema = ref({
  algorithmType: 'translation',
  algorithmName: '翻译',
  category: 'translation',
  description: '机器翻译算法测试',
  groups: [
    {
      name: 'basic',
      label: '基本配置',
      fields: [
        {
          fieldCode: 'translation_direction',
          fieldName: '翻译方向',
          fieldType: 'select',
          required: true,
          component: 'select',
          options: [
            { label: '中译英', value: 'zh2en' },
            { label: '英译中', value: 'en2zh' }
          ],
          helpText: '选择翻译的源语言和目标语言'
        }
      ]
    }
  ],
  fields: []
});

const formData = ref({});

const handleFieldChange = (field: FormFieldSchema, value: any) => {
  console.log(`字段 ${field.fieldName} 变化:`, value);
};

// 验证表单
const validate = async () => {
  const valid = await formRef.value?.validate();
  if (valid) {
    const values = formRef.value?.getValues();
    console.log('表单值:', values);
  }
};
</script>
```

### 8.2 与 AlgorithmSelect 集成

```vue
<template>
  <div>
    <AlgorithmSelect
      v-model="selectedAlgorithm"
      @change="handleAlgorithmChange"
    />
    
    <DynamicForm
      v-if="formSchema"
      ref="formRef"
      :schema="formSchema"
      v-model="formData"
    />
  </div>
</template>

<script setup lang="ts">
const selectedAlgorithm = ref('');
const formSchema = ref(null);
const formData = ref({});

const handleAlgorithmChange = async (algorithm: Algorithm | null) => {
  if (algorithm) {
    formSchema.value = await algorithmService.getFormSchema(algorithm.type);
    formData.value = await algorithmService.getDefaultParams(algorithm.type);
  } else {
    formSchema.value = null;
    formData.value = {};
  }
};
</script>
```

---

## 9. 样式规范

### 9.1 使用 CSS 变量

组件样式使用项目定义的 CSS 变量，确保风格一致：

```css
/* 颜色 */
--primary-color: #FF6A00;
--text-primary: #333333;
--text-secondary: #777777;
--border-color: #E5E7EB;

/* 间距 */
--spacing-xs: 4px;
--spacing-sm: 8px;
--spacing-md: 16px;
--spacing-lg: 24px;

/* 圆角 */
--border-radius-sm: 4px;
--border-radius-md: 8px;
--border-radius-lg: 12px;

/* 过渡 */
--transition-fast: 0.2s ease;
--transition-normal: 0.3s ease;
```

### 9.2 表单样式类

复用现有表单样式类：

| 类名 | 用途 |
|-----|------|
| `.form-container` | 表单容器 |
| `.form-row` | 表单行布局 |
| `.form-group` | 表单字段组 |
| `.form-input` | 输入框样式 |
| `.help-text` | 帮助文本 |
| `.error-message` | 错误提示 |

---

## 10. 性能优化

### 10.1 防抖处理

```typescript
import { debounce } from 'lodash-es';

// 防抖处理字段变化
const debouncedEmitChange = debounce((field, value) => {
  emit('change', field, value);
}, 300);
```

### 10.2 懒加载

```typescript
// 对于大型表单，可以考虑虚拟滚动
import { useVirtualList } from '@vueuse/core';
```

---

## 11. 实施清单

### 11.1 组件开发

- [ ] 修改 DynamicForm.vue 主组件（原生 HTML + CSS）
- [ ] 实现分组折叠功能
- [ ] 实现各字段类型渲染
- [ ] 实现字段验证
- [ ] 实现字段联动

### 11.2 功能实现

- [ ] 实现 Schema 解析
- [ ] 实现字段渲染
- [ ] 实现字段验证
- [ ] 实现分组折叠
- [ ] 实现字段联动
- [ ] 实现字段隐藏

### 11.3 集成测试

- [ ] TestCaseModal 集成测试
- [ ] E2ETest 集成测试
- [ ] APITest 集成测试
- [ ] 不同字段类型测试
- [ ] 验证规则测试
- [ ] 字段联动测试
