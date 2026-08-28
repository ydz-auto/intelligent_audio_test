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

export function useDynamicForm(props: Props, emit: any) {
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

  // Props exposed to template
  const disabled = computed(() => props.disabled)

  return {
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
  }
}
