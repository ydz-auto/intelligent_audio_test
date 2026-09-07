import { computed, ref, watch } from 'vue'
import type { AudioInfo } from '../../../domain/model/audio'

// 已知的 segment 字段（这些字段有专门列，不作为额外字段显示）
const KNOWN_SEGMENT_FIELDS = ['speaker', 'start', 'end', 'text', 'duration', 'orthography', 'speaker_type', 'speaker_name', 'file', 'channel']

// 已知的 data 顶层字段（这些字段有专门 UI，不作为额外字段显示）
const KNOWN_DATA_KEYS = ['segments', 'text', 'annotations', 'timestamps', 'timestamps_global']

/** 标注项结构（与模板 editableData.annotations 的使用方式一致） */
interface AnnotationItem {
  format: string
  name?: string
  code?: string
  data: any
  source_language?: string
  target_language?: string
  [key: string]: any
}

/** 可编辑的音频详情数据（AudioInfo 域对象的编辑副本） */
type EditableAudioData = Omit<AudioInfo, 'annotations' | 'translations'> & {
  annotations?: AnnotationItem[]
  translations?: Array<{ text: string; direction: string }>
}

/** 详情字段配置（传统格式 props.fields 元素结构） */
interface DetailField {
  key: string
  label?: string
  formatter?: (value?: any, data?: any) => any
  [key: string]: any
}

export function useDetailViewModal(props: any, emit: any) {
  // 可编辑数据（AudioInfo 域对象副本，annotations/translations 为其数组属性）
  const editableData = ref<EditableAudioData>({} as EditableAudioData)

  // 初始化可编辑数据（props.data 为 AudioInfo 域对象，camelCase）
  const initEditableData = () => {
    editableData.value = { ...props.data }

    // 确保translations是数组
    if (editableData.value.translations && !Array.isArray(editableData.value.translations)) {
      editableData.value.translations = [editableData.value.translations as any]
    }

    // 确保annotations是数组
    if (!Array.isArray(editableData.value.annotations)) {
      editableData.value.annotations = []
    }
  }

  // 初始化可编辑数据
  initEditableData()

  // 监听props.data变化，更新可编辑数据
  watch(() => props.data, () => {
    initEditableData()
  }, { deep: true })

  // 添加标注项
  const addAnnotationItem = () => {
    if (!Array.isArray(editableData.value.annotations)) {
      editableData.value.annotations = []
    }

    editableData.value.annotations!.push({
      format: 'json',
      name: '',
      data: { segments: [] },
      source_language: '',
      target_language: ''
    })

    selectedAnnotationIndex.value = editableData.value.annotations!.length - 1
    annotationEditMode.value = 'visual'
  }

  // 删除标注项
  const removeAnnotationItem = (index: number) => {
    if (Array.isArray(editableData.value.annotations)) {
      editableData.value.annotations.splice(index, 1)
      // 调整选中索引
      if (selectedAnnotationIndex.value === index) {
        selectedAnnotationIndex.value = (editableData.value.annotations?.length ?? 0) > 0 ? 0 : null
      } else if (selectedAnnotationIndex.value !== null && selectedAnnotationIndex.value > index) {
        selectedAnnotationIndex.value--
      }
    }
  }

  // 标注编辑相关状态
  const selectedAnnotationIndex = ref<number | null>(null)
  const annotationEditMode = ref<'visual' | 'raw'>('visual')
  const rawAnnotationData = ref('')

  // 获取当前标注项（集中判空，消除重复的 annotations[index] 访问）
  const getCurrentAnnotation = (): AnnotationItem | undefined => {
    if (selectedAnnotationIndex.value === null) return undefined
    return editableData.value.annotations?.[selectedAnnotationIndex.value]
  }

  // 选择标注
  const selectAnnotation = (index: number) => {
    selectedAnnotationIndex.value = index
    annotationEditMode.value = 'visual'
    // 更新原始数据
    const ann = editableData.value.annotations?.[index]
    if (ann) {
      const exportData = { ...ann }
      delete exportData.data
      rawAnnotationData.value = JSON.stringify(exportData, null, 2)
    }
  }

  // 获取当前标注的片段 (JSON格式)
  const getCurrentSegments = () => {
    const ann = getCurrentAnnotation()
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
    const ann = getCurrentAnnotation()
    if (!ann || ann.format !== 'json') return []
    const segments = ann.data?.segments || []
    const fieldSet = new Set<string>()
    segments.forEach((seg: any) => {
      if (seg && typeof seg === 'object') {
        Object.keys(seg).forEach((key: string) => {
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
    const ann = getCurrentAnnotation()
    if (!ann || !ann.data || typeof ann.data !== 'object') return []
    return Object.keys(ann.data).filter((key: string) => !KNOWN_DATA_KEYS.includes(key))
  })

  // 添加 segment 额外字段
  const addSegmentField = () => {
    const ann = getCurrentAnnotation()
    if (!ann || !ann.data || !Array.isArray(ann.data.segments)) return
    const fieldName = prompt('请输入字段名称：')
    if (!fieldName || KNOWN_SEGMENT_FIELDS.includes(fieldName)) return
    ann.data.segments.forEach((seg: any) => {
      if (seg && typeof seg === 'object' && !(fieldName in seg)) {
        seg[fieldName] = ''
      }
    })
  }

  // 添加 data 顶层额外字段
  const addDataField = () => {
    const ann = getCurrentAnnotation()
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
  const removeDataField = (fieldName: string) => {
    const ann = getCurrentAnnotation()
    if (!ann || !ann.data) return
    delete ann.data[fieldName]
  }

  // 获取RTTM片段
  const getRTTMSegments = () => {
    const ann = getCurrentAnnotation()
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
  const removeRTTMSegment = (index: number) => {
    const segments = getRTTMSegments()
    segments.splice(index, 1)
  }

  // 获取STM片段
  const getSTMSegments = () => {
    const ann = getCurrentAnnotation()
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
  const removeSTMSegment = (index: number) => {
    const segments = getSTMSegments()
    segments.splice(index, 1)
  }

  // 添加片段
  const addSegment = () => {
    const segments = getCurrentSegments()
    segments.push({
      speaker: 'spk0',
      start: 0,
      end: 1,
      text: ''
    })
  }

  // 删除片段
  const removeSegment = (index: number) => {
    const segments = getCurrentSegments()
    segments.splice(index, 1)
  }

  // 从原始编辑更新数据
  const updateAnnotationDataFromRaw = () => {
    if (selectedAnnotationIndex.value === null) return
    try {
      const parsed = JSON.parse(rawAnnotationData.value)
      const ann = editableData.value.annotations?.[selectedAnnotationIndex.value]
      if (ann) {
        Object.assign(ann, parsed)
      }
    } catch (e) {
      console.error('JSON解析失败:', e)
    }
  }

  // 监听标注编辑模式切换，同步数据
  watch(annotationEditMode, (newMode) => {
    if (newMode === 'raw') {
      const ann = getCurrentAnnotation()
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
      const ann = editableData.value.annotations?.[newIndex]
      if (ann) {
        const exportData = { ...ann }
        delete exportData.data
        rawAnnotationData.value = JSON.stringify(exportData, null, 2)
      }
    }
  })

  // 监听格式变化，当选择RTTM/STM时默认设置名称为diarization
  watch(() => getCurrentAnnotation()?.format, (newFormat) => {
    if (newFormat === 'rttm' || newFormat === 'stm') {
      const ann = getCurrentAnnotation()
      if (ann) {
        ann.code = 'diarization'
      }
    }
  })

  // 保存编辑
  const handleSave = () => {
    emit('confirm', { action: 'save', data: editableData.value })
    emit('close')
  }

  const basicInfoFields = computed<Record<string, any>>(() => {
    // 过滤掉translations和annotations（有专门UI）
    const fields: DetailField[] = props.fields || []
    return fields
      .filter((field: DetailField) => field.key !== 'translations' && field.key !== 'annotations')
      .reduce((acc: Record<string, any>, field: DetailField) => {
        acc[field.key] = field
        return acc
      }, {})
  })

  const hasBasicInfo = computed(() => {
    return (props.fields?.length ?? 0) > 0
  })

  const hasAnnotations = computed(() => {
    // 检查是否有annotations或translations字段定义（有专门UI）
    return (props.fields || []).some((field: DetailField) => field.key === 'annotations' || field.key === 'translations')
  })

  return {
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
    hasAnnotations
  }
}
