<template>
  <div class="dynamic-form">
    <div v-if="showGroupHeader && schema.groups && schema.groups.length > 0" class="form-groups">
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
                  @input="handleFieldChange(field, $event)"
                />
                <input
                  v-model.number="formData[field.fieldCode]"
                  type="number"
                  class="slider-number-input form-control form-control-sm"
                  :min="field.validation?.min ?? 0"
                  :max="field.validation?.max ?? 100"
                  :step="field.validation?.step ?? 1"
                  :disabled="disabled"
                  @input="handleFieldChange(field, $event)"
                />
              </div>
              
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
              
              <div v-if="field.helpText" class="help-text">{{ field.helpText }}</div>
              
              <div v-if="errors[field.fieldCode]" class="error-message">
                {{ errors[field.fieldCode] }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    
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
              @input="handleFieldChange(field, $event)"
            />
            <input
              v-model.number="formData[field.fieldCode]"
              type="number"
              class="slider-number-input form-control form-control-sm"
              :min="field.validation?.min ?? 0"
              :max="field.validation?.max ?? 100"
              :step="field.validation?.step ?? 1"
              :disabled="disabled"
              @input="handleFieldChange(field, $event)"
            />
          </div>
          
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
          
          <div v-if="field.helpText" class="help-text">{{ field.helpText }}</div>
          
          <div v-if="errors[field.fieldCode]" class="error-message">
            {{ errors[field.fieldCode] }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

interface FieldSchema {
  fieldCode: string
  fieldName: string
  fieldType: string
  required: boolean
  defaultValue?: any
  component?: string
  options?: { value: string; label: string }[]
  validation?: {
    min?: number
    max?: number
    step?: number
    pattern?: string
    patternMessage?: string
    minLength?: number
    maxLength?: number
  }
  helpText?: string
  hidden?: boolean
  uiOrder?: number
  uiGroup?: string
  scope?: string
}

interface FormGroup {
  name: string
  label: string
  fields: FieldSchema[]
}

interface FormSchema {
  algorithmType: string
  algorithmName: string
  category?: string
  description?: string
  groups: FormGroup[]
  fields: FieldSchema[]
}

interface Props {
  schema: FormSchema
  initialValues?: Record<string, any>
  disabled?: boolean
  showGroupHeader?: boolean
  defaultExpandedGroups?: string[]
  labelWidth?: string
  scope?: 'api' | 'e2e'
}

const props = withDefaults(defineProps<Props>(), {
  initialValues: () => ({}),
  disabled: false,
  showGroupHeader: true,
  defaultExpandedGroups: () => ['basic'],
  labelWidth: '120px',
  scope: undefined
})

const emit = defineEmits<{
  (e: 'update:modelValue', values: Record<string, any>): void
  (e: 'change', field: FieldSchema, value: any): void
  (e: 'fieldChange', fieldCode: string, value: any, allValues: Record<string, any>): void
  (e: 'validate', valid: boolean, errors: Record<string, string>): void
}>()

const formData = ref<Record<string, any>>({})
const errors = ref<Record<string, string>>({})
const expandedGroups = ref<Set<string>>(new Set(props.defaultExpandedGroups))

const filterByScope = (fields: FieldSchema[]): FieldSchema[] => {
  if (!props.scope) return fields
  return fields.filter(f => !f.scope || f.scope === 'common' || f.scope === props.scope)
}

const visibleGroups = computed(() => {
  if (!props.schema?.groups) return []
  return props.schema.groups.filter(group => 
    getVisibleFields(group.fields).length > 0
  )
})

const visibleFields = computed(() => {
  if (!props.schema?.fields) return []
  return getVisibleFields(props.schema.fields)
})

const getVisibleFields = (fields: FieldSchema[]) => {
  if (!fields) return []
  const scopeFiltered = filterByScope(fields)
  return scopeFiltered.filter(f => !f.hidden)
}

const isGroupExpanded = (groupName: string) => {
  return expandedGroups.value.has(groupName)
}

const toggleGroup = (groupName: string) => {
  if (expandedGroups.value.has(groupName)) {
    expandedGroups.value.delete(groupName)
  } else {
    expandedGroups.value.add(groupName)
  }
}

const getAllSchemaFieldCodes = (): Set<string> => {
  return new Set(
    (props.schema?.fields ?? []).map(f => f.fieldCode)
  )
}

const initFormData = () => {
  const values: Record<string, any> = {}
  
  if (props.schema?.fields) {
    const scopeFields = filterByScope(props.schema.fields)
    for (const field of scopeFields) {
      if (props.initialValues && props.initialValues.hasOwnProperty(field.fieldCode)) {
        values[field.fieldCode] = props.initialValues[field.fieldCode]
      } else if (field.defaultValue !== undefined) {
        values[field.fieldCode] = field.defaultValue
      } else {
        values[field.fieldCode] = getDefaultByType(field.fieldType)
      }
    }
  }
  
  // 仅保留不属于 schema 定义的外部键（防止 scope 过滤掉的字段泄露到提交数据中）
  if (props.initialValues) {
    const allSchemaFieldCodes = getAllSchemaFieldCodes()
    for (const key of Object.keys(props.initialValues)) {
      if (!values.hasOwnProperty(key) && !allSchemaFieldCodes.has(key)) {
        values[key] = props.initialValues[key]
      }
    }
  }
  
  formData.value = values
}

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

const handleFieldChange = (field: FieldSchema, event: Event) => {
  emit('change', field, formData.value[field.fieldCode])
  emit('fieldChange', field.fieldCode, formData.value[field.fieldCode], formData.value)
  emit('update:modelValue', formData.value)
}

const formatSliderValue = (value: any, field: FieldSchema) => {
  if (field.validation?.max === 1) {
    return `${((value || 0) * 100).toFixed(0)}%`
  }
  return value ?? 0
}

const validateFieldInternal = (field: FieldSchema): string | null => {
  const value = formData.value[field.fieldCode]
  
  if (field.required && (value === null || value === undefined || value === '')) {
    return `请${field.component === 'select' ? '选择' : '输入'}${field.fieldName}`
  }
  
  if (field.validation?.pattern && value) {
    const regex = new RegExp(field.validation.pattern)
    if (!regex.test(value)) {
      return field.validation.patternMessage || `${field.fieldName}格式不正确`
    }
  }
  
  if (field.validation?.minLength && value && value.length < field.validation.minLength) {
    return `${field.fieldName}长度不能少于${field.validation.minLength}个字符`
  }
  if (field.validation?.maxLength && value && value.length > field.validation.maxLength) {
    return `${field.fieldName}长度不能超过${field.validation.maxLength}个字符`
  }
  
  if (field.component === 'input-number' && value !== null && value !== undefined) {
    if (field.validation?.min !== undefined && value < field.validation.min) {
      return `${field.fieldName}不能小于${field.validation.min}`
    }
    if (field.validation?.max !== undefined && value > field.validation.max) {
      return `${field.fieldName}不能大于${field.validation.max}`
    }
  }
  
  return null
}

const getValues = () => {
  return { ...formData.value }
}

const setValues = (values: Record<string, any>) => {
  for (const [key, value] of Object.entries(values)) {
    formData.value[key] = value
  }
  emit('update:modelValue', formData.value)
}

const validate = async (): Promise<boolean> => {
  const newErrors: Record<string, string> = {}
  
  if (props.schema?.fields) {
    const scopeFields = filterByScope(props.schema.fields)
    for (const field of scopeFields) {
      const error = validateFieldInternal(field)
      if (error) {
        newErrors[field.fieldCode] = error
      }
    }
  }
  
  errors.value = newErrors
  const valid = Object.keys(newErrors).length === 0
  emit('validate', valid, newErrors)
  return valid
}

const validateField = async (fieldCode: string): Promise<boolean> => {
  const field = props.schema?.fields?.find(f => f.fieldCode === fieldCode)
  if (!field) return true
  
  const error = validateFieldInternal(field)
  if (error) {
    errors.value[fieldCode] = error
    return false
  } else {
    delete errors.value[fieldCode]
    return true
  }
}

const reset = () => {
  initFormData()
  errors.value = {}
}

const clearValidate = () => {
  errors.value = {}
}

watch(() => props.schema, () => {
  initFormData()
}, { immediate: true, deep: true })

watch(() => props.initialValues, (newValues) => {
  if (newValues && Object.keys(newValues).length > 0) {
    const allSchemaFieldCodes = getAllSchemaFieldCodes()
    const scopeFieldCodes = new Set(
      filterByScope(props.schema?.fields ?? []).map(f => f.fieldCode)
    )
    for (const [key, value] of Object.entries(newValues)) {
      // 仅更新当前 scope 可见的 schema 字段，或不属于 schema 的外部键
      if (scopeFieldCodes.has(key) || !allSchemaFieldCodes.has(key)) {
        formData.value[key] = value
      }
    }
  }
}, { deep: true })

defineExpose({
  getValues,
  setValues,
  validate,
  validateField,
  reset,
  clearValidate
})
</script>

<style scoped>
.dynamic-form {
  width: 100%;
}

.form-groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group-item {
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  overflow: hidden;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background-color: #F9FAFB;
  cursor: pointer;
  font-weight: 600;
  color: #333333;
  transition: background-color 0.2s ease;
}

.group-header:hover {
  background-color: #F3F4F6;
}

.group-icon {
  font-size: 12px;
  color: #777777;
  transition: transform 0.2s ease;
}

.group-title {
  flex: 1;
}

.group-content {
  padding: 16px;
}

.form-rows {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-row:last-child {
  margin-bottom: 0;
}

.form-group {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-group label {
  font-size: 14px;
  font-weight: 500;
  color: #333333;
}

.form-group label.required::after {
  content: ' *';
  color: #FF6A00;
}

.form-input {
  width: 100%;
  height: 40px;
  padding: 0 16px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  font-size: 14px;
  color: #333333;
  background-color: #FFFFFF;
  transition: all 0.3s ease;
  box-sizing: border-box;
  outline: none;
}

.form-input:hover {
  border-color: #FF6A00;
}

.form-input:focus {
  border-color: #FF6A00;
  box-shadow: 0 0 0 3px rgba(255, 106, 0, 0.1);
}

.form-input:disabled {
  background-color: #F3F4F6;
  cursor: not-allowed;
}

textarea.form-input {
  height: auto;
  min-height: 80px;
  padding: 8px 16px;
  resize: vertical;
}

.slider-field {
  display: flex;
  align-items: center;
  gap: 16px;
}

.slider-input {
  flex: 1;
  height: 6px;
  -webkit-appearance: none;
  appearance: none;
  background: #E5E7EB;
  border-radius: 9999px;
  outline: none;
}

.slider-input::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  background: #FF6A00;
  border-radius: 50%;
  cursor: pointer;
  transition: transform 0.2s ease;
}

.slider-input::-webkit-slider-thumb:hover {
  transform: scale(1.1);
}

.slider-value {
  min-width: 50px;
  text-align: right;
  color: #777777;
  font-size: 12px;
}

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
  background-color: #E5E7EB;
  border-radius: 9999px;
  transition: 0.2s ease;
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
  transition: 0.2s ease;
}

.switch-input:checked + .switch-slider {
  background-color: #FF6A00;
}

.switch-input:checked + .switch-slider::before {
  transform: translateX(24px);
}

.switch-input:disabled + .switch-slider {
  opacity: 0.5;
  cursor: not-allowed;
}

.code-editor {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.5;
}

.help-text {
  font-size: 12px;
  color: #9CA3AF;
  line-height: 1.4;
}

.error-message {
  font-size: 12px;
  color: #EF4444;
  line-height: 1.4;
}

.slider-number-input {
  width: 80px;
  text-align: center;
  font-weight: 600;
  color: #FF6A00;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 13px;
  outline: none;
  transition: all 0.3s ease;
}

.slider-number-input:hover {
  border-color: #FF6A00;
}

.slider-number-input:focus {
  border-color: #FF6A00;
  box-shadow: 0 0 0 3px rgba(255, 106, 0, 0.1);
}
</style>
