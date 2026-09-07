import { ref, computed, onMounted } from 'vue'
import type { ImportExportOption, ExportField } from '../form/formFieldTypes'

/** ImportExportModal 组件 props 契约 */
interface ImportExportModalProps {
  supportedFormats?: string[]
  importOptions?: ImportExportOption[]
  advancedOptions?: ImportExportOption[]
  exportFields?: ExportField[]
  showPreview?: boolean
}

/** 预览行数据 */
type PreviewRow = Record<string, any>

export function useImportExportModal(props: ImportExportModalProps, emit: any) {
  const fileInput = ref<HTMLInputElement | null>(null)
  const selectedFile = ref<File | null>(null)

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

  const hasImportOptions = computed(() => (props.importOptions?.length ?? 0) > 0)
  const hasExportRange = computed(() => true)
  const hasExportFields = computed(() => (props.exportFields?.length ?? 0) > 0)
  const hasAdvancedOptions = computed(() => (props.advancedOptions?.length ?? 0) > 0)

  const handleFileSelect = (event: Event) => {
    const file = (event.target as HTMLInputElement).files?.[0]
    if (file) {
      selectedFile.value = file
      if (props.showPreview) {
        generatePreview(file)
      }
    }
  }

  const generatePreview = (file: File) => {
    previewData.value = [
      { id: 1, name: '示例数据1', status: 'active' },
      { id: 2, name: '示例数据2', status: 'inactive' },
      { id: 3, name: '示例数据3', status: 'active' }
    ]
    previewColumns.value = Object.keys(previewData.value[0] || {})
  }

  const handleImport = () => {
    if (!selectedFile.value) return

    const importData = {
      mode: 'import',
      file: selectedFile.value,
      config: importConfig.value,
      previewData: previewData.value
    }

    emit('confirm', importData)
  }

  const handleExport = () => {
    const exportData = {
      mode: 'export',
      config: { ...exportConfig.value, fields: selectedFields.value }
    }

    emit('confirm', exportData)
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
    hasImportOptions,
    hasExportRange,
    hasExportFields,
    hasAdvancedOptions,
    handleFileSelect,
    handleImport,
    handleExport
  }
}
