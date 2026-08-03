import { computed, ref, watch, onMounted } from 'vue'

// 已知的 segment 字段（这些字段有专门列，不作为额外字段显示）
const KNOWN_SEGMENT_FIELDS = ['speaker', 'start', 'end', 'text', 'duration', 'orthography', 'speaker_type', 'speaker_name', 'file', 'channel']

// 已知的 data 顶层字段（这些字段有专门 UI，不作为额外字段显示）
const KNOWN_DATA_KEYS = ['segments', 'text', 'annotations', 'timestamps', 'timestamps_global']

export function useDetailViewModal(props: any, emit: any) {
  // 调试：记录props变化
  console.log('[DetailViewModal] props.data:', props.data)
  console.log('[DetailViewModal] props.detail_data:', props.detail_data)
  console.log('[DetailViewModal] props.title:', props.title)

  // 计算属性：是否为detailData格式
  const isDetailDataFormat = computed(() => {
    return props.detail_data !== null
  })

  // detailData 别名（模板中使用 detailData，对应 props.detail_data）
  const detailData = computed(() => props.detail_data)

  // tableConfig 别名（模板中使用 tableConfig，对应 props.table_config）
  const tableConfig = computed(() => props.table_config)

  // 可编辑数据
  const editableData = ref({})

  // 初始化可编辑数据
  const initEditableData = () => {
    if (isDetailDataFormat.value && props.detail_data) {
      // detailData格式
      const metadata = props.detail_data.metadata || []
      const initialData = {}

      metadata.forEach(item => {
        initialData[item.key] = item.value
      })

      // 确保translations是数组
      if (!Array.isArray(initialData.translations)) {
        initialData.translations = initialData.translations ? [JSON.parse(initialData.translations)] : []
      }

      // 确保annotations是数组
      if (!Array.isArray(initialData.annotations)) {
        initialData.annotations = []
      }

      editableData.value = initialData
    } else {
      // 传统格式
      editableData.value = {...props.data}

      // 确保translations是数组
      if (editableData.value.translations && !Array.isArray(editableData.value.translations)) {
        editableData.value.translations = [editableData.value.translations]
      }

      // 确保annotations是数组
      if (!Array.isArray(editableData.value.annotations)) {
        editableData.value.annotations = []
      }
    }
  }

  // 初始化可编辑数据
  initEditableData()

  // 监听props.data变化，更新可编辑数据
  watch(() => props.data, (newData) => {
    initEditableData()
  }, { deep: true })

  // 监听props.detailData变化，更新可编辑数据
  watch(() => props.detail_data, (newDetailData) => {
    initEditableData()
  }, { deep: true })

  // 添加标注项
  const addAnnotationItem = () => {
    if (!Array.isArray(editableData.value.annotations)) {
      editableData.value.annotations = []
    }

    editableData.value.annotations.push({
      format: 'json',
      name: '',
      data: { segments: [] },
      source_language: '',
      target_language: ''
    })

    selectedAnnotationIndex.value = editableData.value.annotations.length - 1
    annotationEditMode.value = 'visual'
  }

  // 删除标注项
  const removeAnnotationItem = (index) => {
    if (Array.isArray(editableData.value.annotations)) {
      editableData.value.annotations.splice(index, 1)
      // 调整选中索引
      if (selectedAnnotationIndex.value === index) {
        selectedAnnotationIndex.value = editableData.value.annotations.length > 0 ? 0 : null
      } else if (selectedAnnotationIndex.value > index) {
        selectedAnnotationIndex.value--
      }
    }
  }

  // 标注编辑相关状态
  const selectedAnnotationIndex = ref(null)
  const annotationEditMode = ref('visual')
  const rawAnnotationData = ref('')

  // 选择标注
  const selectAnnotation = (index) => {
    selectedAnnotationIndex.value = index
    annotationEditMode.value = 'visual'
    // 更新原始数据
    if (editableData.value.annotations && editableData.value.annotations[index]) {
      const ann = editableData.value.annotations[index]
      const exportData = { ...ann }
      delete exportData.data
      rawAnnotationData.value = JSON.stringify(exportData, null, 2)
    }
  }

  // 获取当前标注的片段 (JSON格式)
  const getCurrentSegments = () => {
    if (selectedAnnotationIndex.value === null) return []
    const ann = editableData.value.annotations[selectedAnnotationIndex.value]
    if (!ann) return []
    if (!ann.data) {
      ann.data = { segments: [] }
    }
    if (!Array.isArray(ann.data.segments)) {
      ann.data.segments = []
    }
    return ann.data.segments
  }

  // 计算当前 JSON 标注 segments 中的额外字段（非已知字段）
  const extraSegmentFields = computed(() => {
    if (selectedAnnotationIndex.value === null) return []
    const ann = editableData.value.annotations?.[selectedAnnotationIndex.value]
    if (!ann || ann.format !== 'json') return []
    const segments = ann.data?.segments || []
    const fieldSet = new Set()
    segments.forEach(seg => {
      if (seg && typeof seg === 'object') {
        Object.keys(seg).forEach(key => {
          if (!KNOWN_SEGMENT_FIELDS.includes(key)) {
            fieldSet.add(key)
          }
        })
      }
    })
    return Array.from(fieldSet)
  })

  // 计算当前标注 data 顶层的额外字段（非已知字段）
  const extraDataFields = computed(() => {
    if (selectedAnnotationIndex.value === null) return []
    const ann = editableData.value.annotations?.[selectedAnnotationIndex.value]
    if (!ann || !ann.data || typeof ann.data !== 'object') return []
    return Object.keys(ann.data).filter(key => !KNOWN_DATA_KEYS.includes(key))
  })

  // 添加 segment 额外字段
  const addSegmentField = () => {
    if (selectedAnnotationIndex.value === null) return
    const ann = editableData.value.annotations[selectedAnnotationIndex.value]
    if (!ann || !ann.data || !Array.isArray(ann.data.segments)) return
    const fieldName = prompt('请输入字段名称：')
    if (!fieldName || KNOWN_SEGMENT_FIELDS.includes(fieldName)) return
    ann.data.segments.forEach(seg => {
      if (seg && typeof seg === 'object' && !(fieldName in seg)) {
        seg[fieldName] = ''
      }
    })
  }

  // 添加 data 顶层额外字段
  const addDataField = () => {
    if (selectedAnnotationIndex.value === null) return
    const ann = editableData.value.annotations[selectedAnnotationIndex.value]
    if (!ann) return
    if (!ann.data || typeof ann.data !== 'object') {
      ann.data = {}
    }
    const fieldName = prompt('请输入字段名称：')
    if (!fieldName || KNOWN_DATA_KEYS.includes(fieldName)) return
    if (!(fieldName in ann.data)) {
      ann.data[fieldName] = ''
    }
  }

  // 删除 data 顶层额外字段
  const removeDataField = (fieldName) => {
    if (selectedAnnotationIndex.value === null) return
    const ann = editableData.value.annotations[selectedAnnotationIndex.value]
    if (!ann || !ann.data) return
    delete ann.data[fieldName]
  }

  // 获取RTTM片段
  const getRTTMSegments = () => {
    if (selectedAnnotationIndex.value === null) return []
    const ann = editableData.value.annotations[selectedAnnotationIndex.value]
    if (!ann) return []
    if (!ann.data) {
      ann.data = { segments: [] }
    }
    if (!Array.isArray(ann.data.segments)) {
      ann.data.segments = []
    }
    return ann.data.segments
  }

  // 添加RTTM片段
  const addRTTMSegment = () => {
    if (selectedAnnotationIndex.value === null) return
    const segments = getRTTMSegments()
    segments.push({
      speaker: 'spk0',
      start: 0,
      duration: 1,
      orthography: 'o',
      speaker_type: '<NA>',
      speaker_name: '<NA>'
    })
  }

  // 删除RTTM片段
  const removeRTTMSegment = (index) => {
    const segments = getRTTMSegments()
    segments.splice(index, 1)
  }

  // 获取STM片段
  const getSTMSegments = () => {
    if (selectedAnnotationIndex.value === null) return []
    const ann = editableData.value.annotations[selectedAnnotationIndex.value]
    if (!ann) return []
    if (!ann.data) {
      ann.data = { segments: [] }
    }
    if (!Array.isArray(ann.data.segments)) {
      ann.data.segments = []
    }
    return ann.data.segments
  }

  // 添加STM片段
  const addSTMSegment = () => {
    if (selectedAnnotationIndex.value === null) return
    const segments = getSTMSegments()
    segments.push({
      file: '',
      channel: '1',
      speaker: 'spk0',
      start: 0,
      end: 1,
      text: ''
    })
  }

  // 删除STM片段
  const removeSTMSegment = (index) => {
    const segments = getSTMSegments()
    segments.splice(index, 1)
  }

  // 添加片段
  const addSegment = () => {
    if (selectedAnnotationIndex.value === null) return
    const segments = getCurrentSegments()
    segments.push({
      speaker: 'spk0',
      start: 0,
      end: 1,
      text: ''
    })
  }

  // 删除片段
  const removeSegment = (index) => {
    const segments = getCurrentSegments()
    segments.splice(index, 1)
  }

  // 从原始编辑更新数据
  const updateAnnotationDataFromRaw = () => {
    if (selectedAnnotationIndex.value === null) return
    try {
      const parsed = JSON.parse(rawAnnotationData.value)
      Object.assign(editableData.value.annotations[selectedAnnotationIndex.value], parsed)
    } catch (e) {
      console.error('JSON解析失败:', e)
    }
  }

  // 监听标注编辑模式切换，同步数据
  watch(annotationEditMode, (newMode) => {
    if (newMode === 'raw' && selectedAnnotationIndex.value !== null) {
      const ann = editableData.value.annotations[selectedAnnotationIndex.value]
      if (ann) {
        const exportData = { ...ann }
        delete exportData.data
        rawAnnotationData.value = JSON.stringify(exportData, null, 2)
      }
    }
  })

  // 监听选择标注变化，同步原始数据
  watch(selectedAnnotationIndex, (newIndex) => {
    if (newIndex !== null && annotationEditMode.value === 'raw') {
      const ann = editableData.value.annotations[newIndex]
      if (ann) {
        const exportData = { ...ann }
        delete exportData.data
        rawAnnotationData.value = JSON.stringify(exportData, null, 2)
      }
    }
  })

  // 监听格式变化，当选择RTTM/STM时默认设置名称为diarization
  watch(() => editableData.value.annotations[selectedAnnotationIndex.value]?.format, (newFormat) => {
    if (newFormat === 'rttm' || newFormat === 'stm') {
      editableData.value.annotations[selectedAnnotationIndex.value].code = 'diarization'
    }
  })

  // 保存编辑
  const handleSave = () => {
    emit('confirm', { action: 'save', data: editableData.value })
    emit('close')
  }

  const basicInfoFields = computed(() => {
    if (isDetailDataFormat.value) {
      // 使用detailData.metadata作为基本信息字段，但过滤掉translations和annotations
      return props.detail_data.metadata
        .filter(item => item.key !== 'translations' && item.key !== 'annotations')
        .reduce((acc, item) => {
          acc[item.key] = {
            label: item.label,
            key: item.key,
            formatter: () => item.value,
            class_name: item.class_name
          }
          return acc
        }, {})
    }
    // 传统格式，过滤掉translations和annotations
    return props.fields
      .filter(field => field.key !== 'translations' && field.key !== 'annotations')
      .reduce((acc, field) => {
        acc[field.key] = field
        return acc
      }, {})
  })

  const hasBasicInfo = computed(() => {
    console.log('[DetailViewModal] hasBasicInfo check:', {
      isDetailDataFormat: isDetailDataFormat.value,
      detail_data: props.detail_data,
      fields: props.fields,
      fieldsLength: props.fields.length
    })
    if (isDetailDataFormat.value) {
      return props.detail_data.metadata && props.detail_data.metadata.length > 0
    }
    return props.fields.length > 0
  })

  const hasAnnotations = computed(() => {
    // 检查是否有annotations或translations字段定义
    if (isDetailDataFormat.value && props.detail_data.metadata) {
      return props.detail_data.metadata.some(item => item.key === 'annotations' || item.key === 'translations')
    }
    // 传统格式检查
    return props.fields.some(field => field.key === 'annotations' || field.key === 'translations')
  })

  const hasTableData = computed(() => {
    return props.table_config.columns.length > 0 && props.table_config.data.length > 0
  })

  const getFieldValue = (key, field) => {
    if (isDetailDataFormat.value) {
      // 对于detailData格式，直接使用formatter返回值
      if (field.formatter) {
        return field.formatter()
      }
      return '-'
    }

    // 传统格式
    const value = props.data[key]
    if (value === null || value === undefined) {
      return '-'
    }

    if (field.formatter) {
      return field.formatter(value, props.data)
    }

    if (typeof value === 'object') {
      return JSON.stringify(value)
    }

    return value
  }

  const getTableCellValue = (row, column) => {
    const value = row[column.key]
    if (value === null || value === undefined) {
      return '-'
    }

    if (column.formatter) {
      return column.formatter(value, row)
    }

    if (typeof value === 'object') {
      return JSON.stringify(value)
    }

    return value
  }

  return {
    isDetailDataFormat,
    detailData,
    tableConfig,
    editableData,
    addAnnotationItem,
    removeAnnotationItem,
    selectedAnnotationIndex,
    annotationEditMode,
    rawAnnotationData,
    selectAnnotation,
    getCurrentSegments,
    extraSegmentFields,
    extraDataFields,
    addSegmentField,
    addDataField,
    removeDataField,
    getRTTMSegments,
    addRTTMSegment,
    removeRTTMSegment,
    getSTMSegments,
    addSTMSegment,
    removeSTMSegment,
    addSegment,
    removeSegment,
    updateAnnotationDataFromRaw,
    handleSave,
    basicInfoFields,
    hasBasicInfo,
    hasAnnotations,
    hasTableData,
    getFieldValue,
    getTableCellValue
  }
}
