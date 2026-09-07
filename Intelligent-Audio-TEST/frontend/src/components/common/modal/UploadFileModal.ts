import { ref, computed, watch } from 'vue'
import { useTestCaseConfig, createDefaultUploadConfig, type AudioTypeOption } from '../../../composables/testCase/useTestCaseConfig'
import { parseAnnotationFormat, formatFileSize } from '../../../utils/audioUtils'
import { algorithmPort } from '../../../composables/algorithm/algorithmPort'
import type { ReferenceParam } from '../../../domain/model/algorithm'
import { readCamel } from '../../../utils/keyTransform'

// ─── 类型定义 ───────────────────────────────────────────────

/** 上传选项单项（父组件传入的上传配置项） */
export interface UploadOptionItem {
  key: string
  label: string
  type: string
  defaultValue?: string | number | boolean
  options?: Array<{ label: string; value: string | number }>
}

/** Props（与 UploadFileModal.vue defineProps 一一对应） */
export interface UploadFileModalProps {
  modalId?: string
  title?: string
  acceptedTypes?: string[]
  maxSize?: number
  multiple?: boolean
  uploadOptions?: UploadOptionItem[]
  showTagsInput?: boolean
  autoUpload?: boolean
  supportedFormats?: string[]
  deviceOptions?: Array<{ label: string; value: string | number }>
  algorithmOptions?: Array<{ label: string; value: string }>
}

/** 上传配置（基础默认值 + 父组件 option 覆盖） */
export type UploadConfig = ReturnType<typeof createDefaultUploadConfig>

/** 翻译条目 */
export interface TranslationItem {
  text: string
  direction: string
  source?: string
  target?: string
}

/** 标注条目（上传给后端的标注载荷；上行 wire 格式由 Infrastructure toAnnotationDto 统一转 snake_case） */
export interface AnnotationItem {
  format: string
  code: string
  name?: string
  type?: string
  data: Record<string, unknown>
  sourceLanguage: string
  targetLanguage: string
}

/** 已选 txt 文件 */
export interface SelectedTxtItem {
  file: File
  name: string
}

/** 已选音频项（含关联文本 / 标注解析结果） */
export interface SelectedAudioItem {
  file: File
  name: string
  asrText: string
  translations: TranslationItem[]
  annotations: AnnotationItem[]
  hasTxtFile: boolean
  speakerCount: number
  speakerNames: string[]
}

/** confirm 事件上传载荷 */
export interface UploadConfirmPayload {
  files: Array<{
    file: File
    asrText: string
    translations: TranslationItem[]
    annotations: AnnotationItem[]
    speakerCount: number
    speakerNames: string[]
  }>
  tags: string[]
  options: UploadConfig
  progress: (p: number) => void
}

/** 标注解析结果（parseAnnotationFormat 返回结构） */
type AnnotationParseResult = ReturnType<typeof parseAnnotationFormat>

/** 说话人来源（extractSpeakersFromAnnotation 参数结构） */
interface SpeakerSource {
  segments?: Array<{ speaker?: unknown }>
  data?: { segments?: Array<{ speaker?: unknown }> } | null
  annotations?: Array<{
    segments?: Array<{ speaker?: unknown }>
    data?: { segments?: Array<{ speaker?: unknown }> } | null
  }>
}

/** txt 标记解析结果 */
interface MarkerTextResult {
  asrText: string
  translations: TranslationItem[]
}

/** 事件发射函数 */
type EmitFn = (event: 'close' | 'confirm' | 'selectFolder', ...args: unknown[]) => void

// ─── 默认配置构造 ───────────────────────────────────────────

function buildUploadConfigDefaults(options: UploadOptionItem[]): Partial<UploadConfig> {
  const defaults: Record<string, unknown> = {}
  for (const option of options) {
    defaults[option.key] = option.defaultValue ?? (option.type === 'boolean' ? false : '')
  }
  return defaults as Partial<UploadConfig>
}

// ─── Composable ─────────────────────────────────────────────

export function useUploadFileModal(props: UploadFileModalProps, emit: EmitFn) {
  const uploadOptionList = props.uploadOptions ?? []

  const fileInput = ref<HTMLInputElement | null>(null)
  const selectedFiles = ref<SelectedAudioItem[]>([])
  const selectedTxtFiles = ref<SelectedTxtItem[]>([])
  const isDragging = ref(false)
  const uploading = ref(false)
  const tags = ref('')
  const annotationCode = ref('')
  const referenceParamOptions = ref<Array<{label: string; value: string}>>([])

  const inputId = computed(() => `file-input-${props.modalId || 'default'}`)

  const hasUploadOptions = computed(() => uploadOptionList.length > 0)

  const uploadConfig = ref<UploadConfig>(
    Object.assign(
      createDefaultUploadConfig(),
      buildUploadConfigDefaults(uploadOptionList)
    )
  )

  const audioTypeOption = uploadOptionList.find((o) => o.key === 'audioType')

  const {
    audioTypeOptions,
    hasAudioType
  } = useTestCaseConfig({
    audioTypeOptions: audioTypeOption?.options?.filter(
      (o): o is AudioTypeOption => typeof o.value === 'string'
    ) ?? []
  })

  watch(() => uploadConfig.value.algorithmType, async (newType) => {
    referenceParamOptions.value = []
    annotationCode.value = ''
    if (newType) {
      try {
        const res = await algorithmPort.getReferenceParams(newType)
        referenceParamOptions.value = (res.data || []).map((p: ReferenceParam) => ({
          label: p.code ? `${p.code}${p.name ? ' - ' + p.name : ''}` : p.name,
          value: p.code || ''
        }))
      } catch (e) {
        console.error('加载参考参数失败:', e)
      }
    }
  })

  const playbackDeviceOptions = computed(() => {
    return uploadOptionList.find((o) => o.key === 'playbackDeviceId')?.options || []
  })

  const deviceOptions = computed(() => props.deviceOptions || [])

  const algorithmOptions = computed(() => {
    if (props.algorithmOptions && props.algorithmOptions.length > 0) {
      return props.algorithmOptions
    }
    return []
  })

  const canUpload = computed(() => {
    return selectedFiles.value.length > 0
  })

  const audioFilesCount = computed(() => {
    const supportedAudioExts = props.supportedFormats ?? []
    return selectedFiles.value.filter(file => {
      const ext = file.file.name.split('.').pop()?.toLowerCase() || ''
      return supportedAudioExts.includes(ext)
    }).length
  })

  const totalFileSize = computed(() => {
    return selectedFiles.value.reduce((sum, file) => sum + file.file.size, 0)
  })

  const dragMessage = computed(() => {
    if (isDragging.value) {
      return '释放文件以上传'
    }
    return '拖拽文件到此处或点击选择文件'
  })

  const handleFileSelect = (event: Event) => {
    if (!(event.target instanceof HTMLInputElement) || !event.target.files) return
    const files = Array.from(event.target.files)
    if (files.length > 0) {
      processFiles(files)
    }
  }

  const handleDragOver = (_event: DragEvent) => {
    isDragging.value = true
  }

  const handleDragLeave = (_event: DragEvent) => {
    isDragging.value = false
  }

  const handleDrop = (event: DragEvent) => {
    isDragging.value = false
    const files = event.dataTransfer ? Array.from(event.dataTransfer.files) : []
    if (files.length > 0) {
      processFiles(files)
    }
  }

  const processFiles = (files: File[]) => {
    const audioFiles = files.filter(file => file.type.startsWith('audio/') || file.type.startsWith('video/'))
    const txtFiles = files.filter(file => file.name.endsWith('.txt'))
    const annotationFiles = files.filter(file =>
        file.name.endsWith('.json') || file.name.endsWith('.jsonl') || file.name.endsWith('.rttm') || file.name.endsWith('.stm')
    )

    selectedTxtFiles.value = txtFiles.map(file => ({
      file,
      name: file.name
    }))

    const txtMarkers = new Map<string, string>()
    const annotationDataMap = new Map<string, AnnotationParseResult>()

    const readAnnotationFiles = async () => {
        for (const annFile of annotationFiles) {
            const text = await readFileAsText(annFile)
            const audioFileName = annFile.name.replace(/\.(json|rttm|stm)$/, '')
            let format = 'json'
            if (annFile.name.endsWith('.rttm')) format = 'rttm'
            else if (annFile.name.endsWith('.stm')) format = 'stm'
            else if (annFile.name.endsWith('.jsonl')) format = 'jsonl'

            const parsed = parseAnnotationFormat(text, format)
            annotationDataMap.set(audioFileName, parsed)
        }
    }

    const readTxtFiles = async () => {
      for (const txtFile of txtFiles) {
        const text = await readFileAsText(txtFile)
        const audioFileName = txtFile.name.replace(/\.txt$/, '')
        txtMarkers.set(audioFileName, text)
      }

      const processedFiles = await Promise.all(audioFiles.map(async (audioFile): Promise<SelectedAudioItem> => {
        const audioFileName = audioFile.name.replace(/\.[^/.]+$/, '')
        const markerText = txtMarkers.get(audioFileName) || ''
        const parsedInfo = parseMarkerText(markerText)

        const annData = annotationDataMap.get(audioFileName)
        const annotations: AnnotationItem[] = []

        if (annData && annData.annotations && annData.annotations.length > 0) {
            for (const ann of annData.annotations) {
                const code = uploadConfig.value.algorithmType || determineAnnotationName(audioFileName, annData.format)
                annotations.push({
                    format: annData.format,
                    code: code,
                    // 解析器原始输出为 snake_case，readCamel 兜底读取（camelCase 优先）
                    data: { segments: ann.segments, ...(readCamel<Record<string, unknown>>(ann, 'extraFields') || {}) },
                    sourceLanguage: readCamel<string>(ann, 'sourceLanguage') || '',
                    targetLanguage: readCamel<string>(ann, 'targetLanguage') || ''
                })
            }
        } else if (annData && annData.segments && annData.segments.length > 0) {
            const annotationCodeVal = uploadConfig.value.algorithmType || determineAnnotationName(audioFileName, annData.format)
            annotations.push({
                format: annData.format,
                code: annotationCodeVal,
                data: { segments: annData.segments, ...(readCamel<Record<string, unknown>>(annData, 'extraFields') || {}) },
                sourceLanguage: readCamel<string>(annData, 'sourceLanguage') || '',
                targetLanguage: readCamel<string>(annData, 'targetLanguage') || ''
            })
        } else if (markerText) {
            annotations.push({
                format: 'text',
                code: 'asr',
                data: { text: markerText },
                sourceLanguage: '',
                targetLanguage: ''
            })
        }

        if (parsedInfo.translations && parsedInfo.translations.length > 0) {
            for (const trans of parsedInfo.translations) {
                annotations.push({
                    format: 'text',
                    name: 'translation',
                    code: 'translation',
                    type: 'translation',
                    data: { text: trans.text },
                    sourceLanguage: trans.source || '',
                    targetLanguage: trans.target || ''
                })
            }
        }

        return {
          file: audioFile,
          name: audioFile.name,
          asrText: markerText || '',
          translations: parsedInfo.translations || [],
          annotations: annotations,
          hasTxtFile: txtMarkers.has(audioFileName) || annotationDataMap.has(audioFileName),
          speakerCount: annData ? extractSpeakersFromAnnotation(annData).speakerCount : 0,
          speakerNames: annData ? extractSpeakersFromAnnotation(annData).speakerNames : []
        }
      }))

      selectedFiles.value = processedFiles
    }

    readAnnotationFiles().then(() => readTxtFiles())
  }

  const readFileAsText = (file: File): Promise<string> => {
    return new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = (e) => {
        const result = e.target?.result
        resolve(typeof result === 'string' ? result : '')
      }
      reader.onerror = reject
      reader.readAsText(file)
    })
  }

  const determineAnnotationName = (fileName: string, format: string): string => {
    const lowerName = fileName.toLowerCase()
    if (lowerName.includes('asr') || lowerName.includes('result')) {
      return 'asr'
    }
    if (lowerName.includes('trans') || lowerName.includes('翻译')) {
      return 'translation'
    }
    if (lowerName.includes('ref') || lowerName.includes('reference')) {
      return 'reference'
    }
    if (lowerName.includes('diar') || lowerName.includes('speaker')) {
      return 'diarization'
    }
    if (format === 'rttm' || format === 'stm') {
      return 'diarization'
    }
    return 'reference'
  }

  const extractSpeakersFromAnnotation = (annotationData: SpeakerSource | SpeakerSource[] | null): { speakerCount: number; speakerNames: string[] } => {
    const speakerSet = new Set<string>()

    if (!annotationData) {
      return { speakerCount: 0, speakerNames: [] }
    }

    const annotations = Array.isArray(annotationData) ? annotationData : [annotationData]
    const collectSpeakers = (segments: Array<{ speaker?: unknown }> | undefined) => {
      for (const seg of segments ?? []) {
        const speaker = seg.speaker
        if (typeof speaker === 'string' && speaker.trim()) {
          speakerSet.add(speaker.trim())
        }
      }
    }

    for (const ann of annotations) {
      const segments = ann.segments || ann.data?.segments || []
      collectSpeakers(segments)

      for (const nestedAnn of ann.annotations ?? []) {
        const nestedSegments = nestedAnn.segments || nestedAnn.data?.segments || []
        collectSpeakers(nestedSegments)
      }
    }

    return {
      speakerCount: speakerSet.size,
      speakerNames: Array.from(speakerSet)
    }
  }

  // 解析 txt 标记：首行为 ASR 文本，后续行为「译文 方向」条目
  const parseMarkerText = (text: string): MarkerTextResult => {
    const lines = text.split('\n').map(line => line.trim()).filter(line => line)
    const result: MarkerTextResult = {
      asrText: '',
      translations: []
    }

    if (lines.length === 0) {
      return result
    }

    result.asrText = lines[0].trim()

    for (let i = 1; i < lines.length; i++) {
      const line = lines[i]
      let translatedText = ''
      let direction = ''

      const tabParts = line.split('\t')
      if (tabParts.length >= 2) {
        translatedText = tabParts[0].trim()
        direction = tabParts[1].trim()
      } else {
        const spaceParts = line.split(' ')
        if (spaceParts.length >= 2) {
          translatedText = spaceParts.slice(0, -1).join(' ').trim()
          direction = spaceParts[spaceParts.length - 1].trim()
        } else {
          continue
        }
      }

      if (direction) {
        direction = direction
          .replace(/[_/2]/g, '-')
          .toLowerCase()
      }

      if (translatedText && direction) {
        result.translations.push({
          direction,
          text: translatedText
        })
      }
    }

    return result
  }

  const removeFile = () => {
    selectedFiles.value = []
    selectedTxtFiles.value = []
    annotationCode.value = ''
    if (fileInput.value) {
      fileInput.value.value = ''
    }
  }


  const handleUpload = async () => {
    if (!canUpload.value) return

    uploading.value = true

    try {
      const tagList = tags.value.split(',').map(t => t.trim()).filter(t => t)

      const filesWithMetadata: UploadConfirmPayload['files'] = selectedFiles.value.map(item => {
        const annotations = (item.annotations || []).map(ann => {
          if (ann.format === 'json' || ann.format === 'rttm' || ann.format === 'stm') {
            const code = uploadConfig.value.algorithmType || determineAnnotationName(item.name.replace(/\.[^/.]+$/, ''), ann.format)
            return {
              ...ann,
              name: code,
              code: code
            }
          }
          return ann
        })

        return {
          file: item.file,
          asrText: item.asrText || '',
          translations: item.translations || [],
          annotations,
          speakerCount: item.speakerCount || 0,
          speakerNames: item.speakerNames || []
        }
      })

      const allSpeakerNames = filesWithMetadata.flatMap(f => f.speakerNames).filter((v, i, a) => a.indexOf(v) === i)
      const speakerCountTag = filesWithMetadata.some(f => f.speakerCount > 0)
        ? [`${Math.max(...filesWithMetadata.map(f => f.speakerCount))}人`]
        : []

      emit('confirm', {
        files: filesWithMetadata,
        tags: [...tagList, ...allSpeakerNames, ...speakerCountTag],
        options: uploadConfig.value,
        progress: (p: number) => {}
      })
    } catch (error) {
      console.error('上传失败:', error)
    } finally {
      uploading.value = false
    }
  }

  return {
    fileInput,
    selectedFiles,
    selectedTxtFiles,
    isDragging,
    uploading,
    tags,
    annotationCode,
    referenceParamOptions,
    inputId,
    hasUploadOptions,
    uploadConfig,
    audioTypeOptions,
    playbackDeviceOptions,
    deviceOptions,
    algorithmOptions,
    canUpload,
    audioFilesCount,
    totalFileSize,
    formatFileSize,
    dragMessage,
    handleFileSelect,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    removeFile,
    handleUpload
  }
}