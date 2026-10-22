import { reactive } from 'vue'

export interface ValidationField {
  key: string;
  label: string;
  required?: boolean;
  pattern?: string;
  patternMessage?: string;
  type?: string;
  arrayItemType?: string;
  min?: number;
  max?: number;
  /** 跨字段/自定义校验：返回错误文案则校验失败，null 表示通过 */
  validate?: (formValues: Record<string, any>) => string | null;
  conditional?: {
    field: string;
    value: any;
  };
}

/**
 * 表单验证composable
 * @returns {Object} 包含验证相关的函数和状态
 */
export function useFormValidation() {
  // 错误信息对象
  const errors = reactive<Record<string, string>>({})
  
  /**
   * 验证表单字段
   * @param {Array} fields 表单字段配置数组
   * @param {Object} formValues 表单值对象
   * @returns {Boolean} 验证结果
   */
  const validateForm = (fields: ValidationField[], formValues: any) => {
    // 清空之前的错误
    Object.keys(errors).forEach(key => delete errors[key])
    
    // 标记是否有错误
    let hasErrors = false
    
    // 遍历所有字段进行验证
    fields.forEach(field => {
      // 检查字段是否有条件显示设置，如果有，只在条件满足时验证
      const isFieldVisible = !field.conditional || 
        (formValues[field.conditional.field] === field.conditional.value) ||
        (Array.isArray(field.conditional.value) && field.conditional.value.includes(formValues[field.conditional.field]))
      
      if (!isFieldVisible) {
        // 跳过隐藏字段的验证
        return
      }
      
      // 必填验证
      if (field.required) {
        const value = formValues[field.key]

        if (value === null || value === undefined || value === '') {
          errors[field.key] = `${field.label}不能为空`
          hasErrors = true
        } else if (Array.isArray(value) && value.length === 0) {
          errors[field.key] = `${field.label}不能为空`
          hasErrors = true
        }
      }

      // 数值范围验证（number 类型且有 min/max）
      if (field.type === 'number' && (field.min !== undefined || field.max !== undefined)) {
        const rawValue = formValues[field.key]
        if (rawValue !== null && rawValue !== undefined && rawValue !== '') {
          const num = Number(rawValue)
          if (!isNaN(num)) {
            if (field.min !== undefined && num < field.min) {
              errors[field.key] = `${field.label}不能小于 ${field.min}`
              hasErrors = true
            } else if (field.max !== undefined && num > field.max) {
              errors[field.key] = `${field.label}不能大于 ${field.max}`
              hasErrors = true
            }
          }
        }
      }

      // 正则表达式验证
      if (field.pattern && formValues[field.key]) {
        const regex = new RegExp(field.pattern)
        if (!regex.test(formValues[field.key])) {
          errors[field.key] = field.patternMessage || `${field.label}格式不正确`
          hasErrors = true
        }
      }

      // 特殊验证：API端点列表中的每个endpoint必须包含协议前缀
      if (field.type === 'array' && field.arrayItemType === 'api_endpoint') {
        const endpoints = formValues[field.key]
        if (Array.isArray(endpoints)) {
          let hasValidEndpoints = false
          
          for (let i = 0; i < endpoints.length; i++) {
            const ep = endpoints[i]
            if (ep && ep.endpoint) {
              // 检查endpoint是否包含协议前缀
              if (!/^(http|https|ws|wss):\/\//i.test(ep.endpoint)) {
                if (!errors[field.key]) {
                  errors[field.key] = `${field.label}中的端点URL必须包含协议前缀 (http://, https://, ws:// 或 wss://)`
                  hasErrors = true
                }
              } else {
                hasValidEndpoints = true
              }
            }
          }
          
          // 如果有必填标记但没有有效的端点
          if (field.required && !hasValidEndpoints) {
            errors[field.key] = `${field.label}不能为空且必须包含有效的端点URL`
            hasErrors = true
          }
        }
      }

      // 自定义校验（跨字段等），未命中已有错误才执行
      if (field.validate && !errors[field.key]) {
        const customError = field.validate(formValues)
        if (customError) {
          errors[field.key] = customError
          hasErrors = true
        }
      }
    })

    return !hasErrors
  }
  
  /**
   * 验证单个字段
   * @param {Object} field 字段配置
   * @param {*} value 字段值
   * @returns {Boolean} 验证结果
   */
  const validateField = (field: ValidationField, value: any) => {
    // 清空该字段之前的错误
    delete errors[field.key]
    
    // 标记是否有错误
    let fieldHasError = false
    
    // 必填验证
    if (field.required) {
      if (value === null || value === undefined || value === '') {
        errors[field.key] = `${field.label}不能为空`
        fieldHasError = true
      } else if (Array.isArray(value) && value.length === 0) {
        errors[field.key] = `${field.label}不能为空`
        fieldHasError = true
      }
    }

    // 数值范围验证（number 类型且有 min/max）
    if (field.type === 'number' && (field.min !== undefined || field.max !== undefined)) {
      if (value !== null && value !== undefined && value !== '') {
        const num = Number(value)
        if (!isNaN(num)) {
          if (field.min !== undefined && num < field.min) {
            errors[field.key] = `${field.label}不能小于 ${field.min}`
            fieldHasError = true
          } else if (field.max !== undefined && num > field.max) {
            errors[field.key] = `${field.label}不能大于 ${field.max}`
            fieldHasError = true
          }
        }
      }
    }

    // 正则表达式验证
    if (field.pattern && value) {
      const regex = new RegExp(field.pattern)
      if (!regex.test(value)) {
        errors[field.key] = field.patternMessage || `${field.label}格式不正确`
        fieldHasError = true
      }
    }

    // 特殊验证：API端点列表
    if (field.type === 'array' && field.arrayItemType === 'api_endpoint' && Array.isArray(value)) {
      let hasValidEndpoints = false
      
      for (let i = 0; i < value.length; i++) {
        const ep = value[i]
        if (ep && ep.endpoint) {
          // 检查endpoint是否包含协议前缀
          if (!/^(http|https|ws|wss):\/\//i.test(ep.endpoint)) {
            errors[field.key] = `${field.label}中的端点URL必须包含协议前缀 (http://, https://, ws:// 或 wss://)`
            fieldHasError = true
          } else {
            hasValidEndpoints = true
          }
        }
      }
      
      // 如果有必填标记但没有有效的端点
      if (field.required && !hasValidEndpoints) {
        errors[field.key] = `${field.label}不能为空且必须包含有效的端点URL`
        fieldHasError = true
      }
    }
    
    return !fieldHasError
  }
  
  /**
   * 清空所有错误
   */
  const clearErrors = () => {
    Object.keys(errors).forEach(key => delete errors[key])
  }
  
  /**
   * 设置单个字段的错误信息
   * @param {String} fieldKey 字段键名
   * @param {String} errorMessage 错误信息
   */
  const setFieldError = (fieldKey: string, errorMessage: string) => {
    errors[fieldKey] = errorMessage
  }
  
  /**
   * 清除单个字段的错误信息
   * @param {String} fieldKey 字段键名
   */
  const clearFieldError = (fieldKey: string) => {
    delete errors[fieldKey]
  }
  
  return {
    errors,
    validateForm,
    validateField,
    clearErrors,
    setFieldError,
    clearFieldError
  }
}
