import { ref, computed, onMounted } from 'vue'
import type { ImportExportOption, ExportField } from '../form/formFieldTypes'
import type { ExportRangeOption } from '../../../domain/model/ui'
import type { ImportReport } from '../../../domain/model/common'
import { toUserErrorMessage } from '../../../utils/errorMessage'

/** ImportExportModal 组件 props 契约 */
interface ImportExportModalProps {
  mode?: string
  title?: string
  supportedFormats?: string[]
  acceptedFileTypes?: string
  importOptions?: ImportExportOption[]
  advancedOptions?: ImportExportOption[]
  exportFields?: ExportField[]
  showPreview?: boolean
  totalItems?: number
  /** 导出范围选项（缺省为「全部 / 选中 / 筛选后」三项历史口径） */
  exportRanges?: ExportRangeOption[]
  /** 格式展示名（如 json → JSON、excel → Excel） */
  formatLabels?: Record<string, string>
  /** 导入模式补充说明（如匹配键口径、状态字段说明） */
  importHint?: string
  /** 导入结果区固定说明（缺省「状态以本环境为准」） */
  resultNote?: string
  /** 可导入扩展名（缺省 json/csv/xlsx/xls） */
  allowedImportExtensions?: string[]
  /** 真实导入动作（提供时弹窗内发起请求并展示计数/错误，未提供则维持原 confirm 事件口径） */
  importAction?: (file: File, config: Record<string, any>) => Promise<ImportReport>
  /** 真实导出动作（提供时弹窗内发起下载，未提供则维持原 confirm 事件口径） */
  exportAction?: (config: Record<string, any>) => Promise<any>
  /** 导入成功回调（resource 侧在此刷新列表/统计，弹窗保持打开展示结果） */
  onImported?: (report: ImportReport) => void | Promise<void>
}

/** 预览行数据 */
type PreviewRow = Record<string, any>

/** 预览最多展示行数 */
const PREVIEW_MAX_ROWS = 3

/** 缺省导出范围（历史三口径，老调用方行为不变） */
const DEFAULT_EXPORT_RANGES: ExportRangeOption[] = [
  { value: 'all', label: '全部数据' },
  { value: 'selected', label: '选中数据' },
  { value: 'filtered', label: '筛选后数据' }
]

/** 缺省可导入扩展名（后端 INT-816 支持 JSON / CSV / Excel） */
const DEFAULT_IMPORT_EXTENSIONS = ['json', 'csv', 'xlsx', 'xls']

/** 格式展示名缺省映射 */
const DEFAULT_FORMAT_LABELS: Record<string, string> = {
  json: 'JSON',
  excel: 'Excel',
  csv: 'CSV',
  xlsx: 'Excel',
  xls: 'Excel',
  zip: 'ZIP',
  txt: 'TXT'
}

/** 扩展名 → 可读格式名（用于校验提示） */
const EXTENSION_LABELS: Record<string, string> = {
  json: 'JSON',
  csv: 'CSV',
  xlsx: 'Excel',
  xls: 'Excel'
}

function getFileExtension(filename: string): string {
  const index = filename.lastIndexOf('.')
  return index >= 0 ? filename.slice(index + 1).toLowerCase() : ''
}

/** 读取文件文本（优先 File.text，旧环境回落 FileReader） */
function readFileText(file: File): Promise<string> {
  if (typeof (file as any).text === 'function') {
    return (file as any).text()
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(reader.error || new Error('读取文件失败'))
    reader.readAsText(file)
  })
}

/** 单行 CSV 拆分（支持双引号包裹与 "" 转义） */
function splitCsvLine(line: string): string[] {
  const cells: string[] = []
  let current = ''
  let inQuotes = false
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i]
    if (inQuotes) {
      if (char === '"') {
        if (line[i + 1] === '"') {
          current += '"'
          i += 1
        } else {
          inQuotes = false
        }
      } else {
        current += char
      }
    } else if (char === '"') {
      inQuotes = true
    } else if (char === ',') {
      cells.push(current)
      current = ''
    } else {
      current += char
    }
  }
  cells.push(current)
  return cells
}

/** JSON 顶层取数据数组（裸数组，或信封中第一个数组字段） */
function extractJsonRows(data: any): any[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === 'object') {
    const arrayValue = Object.values(data).find((value) => Array.isArray(value))
    if (Array.isArray(arrayValue)) return arrayValue as any[]
  }
  throw new Error('未找到可预览的数据数组')
}

/** 单元格展示化：对象/数组序列化为 JSON 文本并截断 */
function formatCell(value: any): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') {
    const text = JSON.stringify(value)
    return text.length > 80 ? `${text.slice(0, 80)}…` : text
  }
  return String(value)
}

export function useImportExportModal(props: ImportExportModalProps, emit: any) {
  const fileInput = ref<HTMLInputElement | null>(null)
  const selectedFile = ref<File | null>(null)

  // 提交态（提供真实动作时使用）
  const submitting = ref(false)
  const submitError = ref('')
  const importResult = ref<ImportReport | null>(null)

  // 预览态
  const previewError = ref('')
  const previewUnsupported = ref(false)

  // 选项按 key 归并为布尔开关配置
  const toOptionFlags = (options: ImportExportOption[] = []): Record<string, any> =>
    options.reduce<Record<string, any>>((acc, option) => {
      acc[option.key] = option.defaultValue || false
      return acc
    }, {})

  const importConfig = ref<Record<string, any>>({
    format: props.supportedFormats?.[0],
    ...toOptionFlags(props.importOptions)
  })

  const exportConfig = ref<Record<string, any>>({
    format: props.supportedFormats?.[0],
    range: 'all',
    ...toOptionFlags(props.advancedOptions)
  })

  const selectedFields = ref<string[]>(
    (props.exportFields || []).filter((field: ExportField) => field.defaultChecked).map((field: ExportField) => field.key)
  )

  const previewData = ref<PreviewRow[]>([])
  const previewColumns = ref<string[]>([])

  const exportRangeOptions = computed<ExportRangeOption[]>(() =>
    props.exportRanges && props.exportRanges.length > 0 ? props.exportRanges : DEFAULT_EXPORT_RANGES
  )

  const hasImportOptions = computed(() => (props.importOptions?.length ?? 0) > 0)
  const hasExportRange = computed(() => exportRangeOptions.value.length > 0)
  const hasExportFields = computed(() => (props.exportFields?.length ?? 0) > 0)
  const hasAdvancedOptions = computed(() => (props.advancedOptions?.length ?? 0) > 0)

  const allowedImportExtensions = computed<string[]>(() =>
    props.allowedImportExtensions && props.allowedImportExtensions.length > 0
      ? props.allowedImportExtensions.map((extension) => extension.toLowerCase().replace(/^\./, ''))
      : DEFAULT_IMPORT_EXTENSIONS
  )

  const formatLabel = (format: string): string =>
    props.formatLabels?.[format] || DEFAULT_FORMAT_LABELS[String(format).toLowerCase()] || String(format).toUpperCase()

  /** 可读格式名（xlsx/xls 同为 Excel，去重后用于提示文案） */
  const importFormatNames = computed<string[]>(() =>
    Array.from(new Set(allowedImportExtensions.value.map((ext) => EXTENSION_LABELS[ext] || ext.toUpperCase())))
  )

  const importFormatHint = computed(() => importFormatNames.value.join(' / '))

  const importAcceptedTypes = computed(() =>
    props.acceptedFileTypes || allowedImportExtensions.value.map((ext) => `.${ext}`).join(',')
  )

  const resultNote = computed(() => props.resultNote || '状态以本环境为准')

  /** 真实导入动作是否启用（提供 importAction 时弹窗内纳管请求与结果） */
  const usesImportAction = computed(() => typeof props.importAction === 'function')

  /** 真实导出动作是否启用 */
  const usesExportAction = computed(() => typeof props.exportAction === 'function')

  const handleFileSelect = (event: Event) => {
    const file = (event.target as HTMLInputElement).files?.[0]
    if (file) {
      selectedFile.value = file
      // 重新选择文件时清掉上一份结果/错误，避免残留
      importResult.value = null
      submitError.value = ''
      if (props.showPreview) {
        generatePreview(file)
      }
    }
  }

  const applyPreviewRows = (rawRows: any[]) => {
    const rows = rawRows.filter((row) => row && typeof row === 'object').slice(0, PREVIEW_MAX_ROWS)
    if (rows.length === 0) {
      previewError.value = '文件中没有可预览的数据行'
      return
    }
    const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))))
    previewColumns.value = columns
    previewData.value = rows.map((row) => {
      const formatted: PreviewRow = {}
      for (const column of columns) formatted[column] = formatCell(row[column])
      return formatted
    })
  }

  /**
   * 预览：按所选文件真实解析前 N 行（JSON / CSV）。
   * Excel 前端无解析库，不再展示任何示例数据，改为提示服务端解析。
   */
  const generatePreview = async (file: File) => {
    previewData.value = []
    previewColumns.value = []
    previewError.value = ''
    previewUnsupported.value = false

    const extension = getFileExtension(file.name)
    try {
      if (extension === 'json') {
        const text = await readFileText(file)
        applyPreviewRows(extractJsonRows(JSON.parse(text)))
      } else if (extension === 'csv') {
        const text = await readFileText(file)
        const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0)
        if (lines.length === 0) throw new Error('文件内容为空')
        const columns = splitCsvLine(lines[0]).map((column) => column.trim())
        const rows = lines.slice(1, PREVIEW_MAX_ROWS + 1).map((line) => {
          const cells = splitCsvLine(line)
          const row: PreviewRow = {}
          columns.forEach((column, index) => {
            row[column] = cells[index] ?? ''
          })
          return row
        })
        previewColumns.value = columns
        previewData.value = rows
      } else if (extension === 'xlsx' || extension === 'xls') {
        previewUnsupported.value = true
      } else {
        previewUnsupported.value = true
      }
    } catch (error) {
      previewError.value = `预览解析失败：${toUserErrorMessage(error, '无法解析该文件')}`
    }
  }

  /** 导入前本地校验：扩展名白名单 + 空文件（错误可见且不发请求） */
  const validateImportFile = (file: File): string => {
    const extension = getFileExtension(file.name)
    const allowed = allowedImportExtensions.value
    if (!extension || !allowed.includes(extension)) {
      return `不支持的导入文件${extension ? `（.${extension}）` : ''}，仅支持 ${importFormatNames.value.join(' / ')} 格式`
    }
    if (file.size === 0) return '文件为空，无法导入'
    return ''
  }

  const handleImport = async () => {
    if (submitting.value || !selectedFile.value) return

    // 未提供真实动作：维持历史 confirm 事件口径（老调用方零改动）
    if (!usesImportAction.value) {
      emit('confirm', {
        mode: 'import',
        file: selectedFile.value,
        config: importConfig.value,
        previewData: previewData.value
      })
      return
    }

    const validationError = validateImportFile(selectedFile.value)
    if (validationError) {
      submitError.value = validationError
      return
    }

    submitting.value = true
    submitError.value = ''
    importResult.value = null
    try {
      const report = await props.importAction!(selectedFile.value, { ...importConfig.value })
      importResult.value = report
      // 列表/分页/统计即时刷新（弹窗保持打开展示导入结果）
      if (typeof props.onImported === 'function') {
        await props.onImported(report)
      }
    } catch (error) {
      // 服务端 400 / 解析失败：错误留在弹窗内，不关闭
      submitError.value = toUserErrorMessage(error, '导入失败，请检查文件后重试')
    } finally {
      submitting.value = false
    }
  }

  const handleExport = async () => {
    if (submitting.value) return

    const config = {
      ...exportConfig.value,
      fields: selectedFields.value
    }

    // 未提供真实动作：维持历史 confirm 事件口径
    if (!usesExportAction.value) {
      emit('confirm', { mode: 'export', config })
      return
    }

    submitting.value = true
    submitError.value = ''
    try {
      const result = await props.exportAction!(config)
      emit('confirm', { mode: 'export', config, result })
    } catch (error) {
      // 导出失败不沉底、不把错误响应当文件下载（client.handleResponse 已先行判 response.ok）
      submitError.value = toUserErrorMessage(error, '导出失败，请稍后重试')
    } finally {
      submitting.value = false
    }
  }

  /** 导入结果查看完毕：关闭弹窗并把结果回传调用方 */
  const finishImport = () => {
    emit('confirm', {
      mode: 'import',
      config: importConfig.value,
      result: importResult.value
    })
  }

  onMounted(() => {
    if ((props.exportFields?.length ?? 0) > 0 && selectedFields.value.length === 0) {
      selectedFields.value = (props.exportFields || []).map((field: ExportField) => field.key)
    }
  })

  return {
    fileInput,
    selectedFile,
    importConfig,
    exportConfig,
    selectedFields,
    previewData,
    previewColumns,
    previewError,
    previewUnsupported,
    submitting,
    submitError,
    importResult,
    usesImportAction,
    usesExportAction,
    exportRangeOptions,
    importAcceptedTypes,
    importFormatHint,
    resultNote,
    formatLabel,
    hasImportOptions,
    hasExportRange,
    hasExportFields,
    hasAdvancedOptions,
    handleFileSelect,
    handleImport,
    handleExport,
    finishImport
  }
}
