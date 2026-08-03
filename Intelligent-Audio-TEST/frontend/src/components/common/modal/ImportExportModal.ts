import { ref, computed, onMounted } from 'vue'

export function useImportExportModal(props: any, emit: any) {
  const fileInput = ref(null)
  const selectedFile = ref(null)

  const importConfig = ref({
    format: props.supportedFormats[0],
    ...props.importOptions.reduce((acc, option) => {
      acc[option.key] = option.defaultValue || false
      return acc
    }, {})
  })

  const exportConfig = ref({
    format: props.supportedFormats[0],
    range: 'all',
    ...props.advancedOptions.reduce((acc, option) => {
      acc[option.key] = option.defaultValue || false
      return acc
    }, {})
  })

  const selectedFields = ref(
    props.exportFields.filter(field => field.defaultChecked).map(field => field.key)
  )

  const previewData = ref([])
  const previewColumns = ref([])

  const hasImportOptions = computed(() => props.importOptions.length > 0)
  const hasExportRange = computed(() => true)
  const hasExportFields = computed(() => props.exportFields.length > 0)
  const hasAdvancedOptions = computed(() => props.advancedOptions.length > 0)

  const handleFileSelect = (event) => {
    const file = event.target.files[0]
    if (file) {
      selectedFile.value = file
      if (props.showPreview) {
        generatePreview(file)
      }
    }
  }

  const generatePreview = (file) => {
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
    if (props.exportFields.length > 0 && selectedFields.value.length === 0) {
      selectedFields.value = props.exportFields.map(field => field.key)
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
