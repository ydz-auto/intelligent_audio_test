/**
 * 表单字段通用类型定义 —— camelCase
 * 供 CRUDFormModal / FormField / ImportExportModal 等表单类组件共用，
 * 统一收敛字段结构，避免各处重复定义与魔法字符串索引。
 */

/** 下拉/选项通用结构 */
export interface FieldOption {
  value: any
  label: string
}

/** 表单字段配置（前端 Domain 契约，全 camelCase） */
export interface FormFieldConfig {
  /** 字段键名（camelCase，与 Domain 对象字段一致） */
  key: string
  /** 显示标签 */
  label: string
  /** 字段类型（text/number/select/array/apiMeta 等） */
  type?: string
  /** 默认值 */
  defaultValue?: any
  /** 下拉选项 */
  options?: FieldOption[]
  /** 分组名 */
  group?: string
  /** 条件显示规则 */
  conditional?: { field: string; value: any }
  /** 数组项类型（apiEndpoint/gainSpl 等） */
  arrayItemType?: string
  /** 数组项模板 */
  arrayItemTemplate?: Record<string, any>
  /** 占位提示 */
  placeholder?: string
  /** 提示文案 */
  hint?: string
  /** 是否必填 */
  required?: boolean
  /** 是否禁用 */
  disabled?: boolean
  /** 只读 */
  readonly?: boolean
  /** 按钮动作（loadDriverKeywords/scanPlaybackDevices 等） */
  action?: string
  /** 按钮文案 */
  text?: string
  /** 校验规则 */
  pattern?: string
  patternMessage?: string
  /** 隐藏字段 */
  hidden?: boolean
}

/** 表单值容器：字段 key → 值 */
export type FormValues = Record<string, any>

/** 导入/导出选项（ImportExportModal 等） */
export interface ImportExportOption {
  key: string
  label: string
  defaultValue?: any
}

/** 导出字段定义 */
export interface ExportField {
  key: string
  label: string
  defaultChecked?: boolean
}

/** 文件上传载荷 */
export interface FileUploadPayload {
  fieldKey: string
  file: File | null
}

/** SPL 测试载荷 */
export interface SplTestPayload {
  index: number
  gainValue?: number | null
  splValue?: number | null
  gainOffset?: number | null
}
