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
import { useDynamicForm } from './DynamicForm'

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

const {
  disabled,
  formData,
  errors,
  visibleGroups,
  visibleFields,
  getVisibleFields,
  isGroupExpanded,
  toggleGroup,
  handleFieldChange,
  getValues,
  setValues,
  validate,
  validateField,
  reset,
  clearValidate
} = useDynamicForm(props, emit)

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
@import './DynamicForm.css';
</style>
