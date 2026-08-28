import { ref, computed, watch, reactive, onMounted, onUnmounted } from 'vue'
import { parseAudioTxtFile, parseAnnotationFormat, determineAnnotationType } from '../../../utils/audioUtils'
import { evaluationApi, devicesApi, algorithmApi } from '../../../utils/api'
import type { PropType } from 'vue'
import { useTestCaseConfig, createDefaultUploadConfig } from '../../../composables/testCase/useTestCaseConfig'
import { buildTestCaseGroups } from '../../../utils/testCaseStrategy'
import { useAlgorithmConfig } from '../../../composables/algorithm/useAlgorithmConfig'

interface UploadOption {
  key: string
  type: 'boolean' | 'radio' | 'checkbox' | 'select' | 'number' | 'text' | 'dimensions'
  label: string
  defaultValue?: any
  options?: Array<{ value: any; label: string }>
  disabled?: boolean
  min?: number
  max?: number
  step?: number
  placeholder?: string
  hint?: string
}

interface FileWithMetadata {
  file: File
  asrText: string
  translations: Array<{ text: string; direction: string }>
  speakerCount: number
  speakerNames: string[]
  tags: string[]
}

interface ImportConfirmData {
  config: Record<string, any>
  files: FileWithMetadata[]
  folderGroupMappings: Record<string, string>
  selectedFolders: string[]
  onProgressUpdate: (progress: number) => void
  onImportComplete: () => void
  onImportError: (error: Error) => void
}

export function useFolderImportModal(props: any, emit: (event: string, ...args: any[]) => void) {
  const algorithmConfig = useAlgorithmConfig()
  const getAlgorithmOptions = () => algorithmConfig.getAlgorithmOptions()
  const getFormSchema = (type: string) => algorithmConfig.getFormSchema(type)

  const folderInput = ref<HTMLInputElement | null>(null)
  const importing = ref(false)
  const isDragActive = ref(false)
  const importProgress = ref(0)
  const selectedFiles = ref<File[]>([])
  const tags = ref('')
  const annotationCode = ref('')
  const referenceParamOptions = ref<Array<{label: string; value: string}>>([])

  const uploadConfig = reactive<Record<string, any>>(
    Object.assign(
      createDefaultUploadConfig(),
      props.uploadOptions.reduce((acc: Record<string, any>, option: UploadOption) => {
        acc[option.key] = option.defaultValue ?? (option.type === 'boolean' ? false : '')
        return acc
      }, {} as Record<string, any>)
    )
  )

  const {
    dimensionSearchQuery,
    e2eDimensionSearchQuery,
    dimensionsLoading,
    dimensionsError,
    audioTypeOptions,
    hasAudioType,
    groupNameTypeOptions,
    filteredDimensions,
    e2eFilteredDimensions,
    dimensionCount,
    isDimensionSelected,
    toggleDimensionSelection,
    ensureDimensionsLoaded,
    defaultSpl
  } = useTestCaseConfig({
    audioTypeOptions: props.uploadOptions.find((o: UploadOption) => o.key === 'audioType')?.options || []
  })

  const playbackDeviceOptions = ref<Array<{ value: any; label: string }>>([])
  const playbackDevicePage = ref(1)
  const playbackDevicePages = ref(1)
  const playbackDeviceLoading = ref(false)
  const playbackDeviceHasMore = ref(true)
  const playbackDeviceDropdownOpen = ref(false)
  let playbackDeviceSelectRef: HTMLSelectElement | null = null

  const fetchPlaybackDevices = async (reset = true) => {
    if (reset) {
      playbackDevicePage.value = 1
      playbackDeviceOptions.value = []
      playbackDeviceHasMore.value = true
    }
    if (playbackDeviceLoading.value || (!playbackDeviceHasMore.value && !reset)) return
    playbackDeviceLoading.value = true
    try {
      const response = await devicesApi.getPlaybackDevices({
        params: { page: playbackDevicePage.value, per_page: 50 },
        unwrapResponse: false
      }) as unknown as { success: boolean; data: { items: Array<{ id: any; name: string }>; pages: number } }
      if (response.success && response.data && Array.isArray(response.data.items)) {
        const newOptions = response.data.items.map((d) => ({ label: d.name, value: d.id }))
        if (reset) {
          playbackDeviceOptions.value = newOptions
        } else {
          playbackDeviceOptions.value = [...playbackDeviceOptions.value, ...newOptions]
        }
        playbackDevicePages.value = response.data.pages || 1
        playbackDeviceHasMore.value = playbackDevicePage.value < playbackDevicePages.value
        if (playbackDeviceHasMore.value) {
          playbackDevicePage.value += 1
        }
      } else {
        if (reset) playbackDeviceOptions.value = []
      }
    } catch (e) {
      console.error('Fetch playback devices failed:', e)
      if (reset) playbackDeviceOptions.value = []
    } finally {
      playbackDeviceLoading.value = false
    }
  }

  const loadMorePlaybackDevices = async () => {
    if (!playbackDeviceLoading.value && playbackDeviceHasMore.value) {
      await fetchPlaybackDevices(false)
    }
  }

  const handlePlaybackDeviceSelectScroll = (event: Event) => {
    const target = event.target as HTMLSelectElement
    const scrollTop = target.scrollTop
    const scrollHeight = target.scrollHeight
    const clientHeight = target.clientHeight
    if (scrollTop + clientHeight >= scrollHeight - 50) {
      loadMorePlaybackDevices()
    }
  }

  const isPlaybackDeviceLoading = () => playbackDeviceLoading.value

  const selectedFolders = ref<string[]>([])
  const folderGroupNames = ref<Map<string, string>>(new Map())
  const algorithmParams = ref<any[]>([])
  const algorithmOptions = ref<{ value: string; name: string }[]>([])
  const algorithmFormSchema = ref<any>(null)

  async function loadAlgorithmOptions() {
    try {
      const options = await getAlgorithmOptions()
      algorithmOptions.value = (options || []).map((opt: any) => ({
        value: opt.value,
        name: opt.name || opt.label || opt.value
      }))
    } catch (error) {
      console.error('加载算法选项失败:', error)
      algorithmOptions.value = []
    }
  }

  async function loadAlgorithmFormSchema(algorithmType: string) {
    if (!algorithmType) {
      algorithmFormSchema.value = null
      algorithmParams.value = []
      return
    }

    try {
      const schema = await getFormSchema(algorithmType)
      algorithmFormSchema.value = schema

      const newParams: any[] = []
      if (schema?.fields) {
        schema.fields.forEach((field: any) => {
          if (field.defaultValue !== undefined) {
            newParams.push({
              fieldCode: field.fieldCode,
              fieldValue: field.defaultValue
            })
          }
        })
      }
      algorithmParams.value = newParams
    } catch (error) {
      console.error('加载算法表单Schema失败:', error)
      algorithmFormSchema.value = null
    }
  }

  const supportedAudioExts = props.supportedFormats

  watch(() => uploadConfig, (newConfig) => {
    emit('configChange', newConfig)
  }, { deep: true })

  watch(
    () => [uploadConfig.createTestCase, uploadConfig.testTypes],
    ([createTestCase, testTypes]) => {
      if (createTestCase || (testTypes && testTypes.length > 0)) {
        ensureDimensionsLoaded()
      }
      if (testTypes && testTypes.includes('e2e')) {
        fetchPlaybackDevices(true)
      }
    },
    { immediate: true }
  )

  const audioFilesCount = computed(() => {
    return selectedFiles.value.filter(file => {
      const ext = file.name.split('.').pop()?.toLowerCase() || ''
      return supportedAudioExts.includes(ext)
    }).length
  })

  const dragMessage = computed(() => {
    if (isDragActive.value) {
      return '释放文件夹以上传'
    }
    return '拖拽文件夹到此处或点击选择文件夹'
  })

  const canImport = computed(() => selectedFiles.value.length > 0)

  const hasUploadOptions = computed(() => props.uploadOptions.length > 0)

  onMounted(async () => {
    await loadAlgorithmOptions()
    if (uploadConfig.algorithmType) {
      await loadAlgorithmFormSchema(uploadConfig.algorithmType)
    }
  })

  watch(() => uploadConfig.algorithmType, async (newType) => {
    referenceParamOptions.value = []
    annotationCode.value = ''
    if (newType) {
      loadAlgorithmFormSchema(newType)
      try {
        const res = await algorithmApi.getReferenceParams(newType)
        referenceParamOptions.value = (res.data || []).map((p: any) => ({
          label: p.code ? `${p.code}${p.name ? ' - ' + p.name : ''}` : p.name,
          value: p.code || ''
        }))
      } catch (e) {
        console.error('加载参考参数失败:', e)
      }
    } else {
      algorithmFormSchema.value = null
      algorithmParams.value = []
    }
  })

  const totalFileSize = computed(() => {
    const audioFiles = selectedFiles.value.filter(file => {
      const ext = file.name.split('.').pop()?.toLowerCase() || ''
      return supportedAudioExts.includes(ext)
    })
    return audioFiles.reduce((total, file) => total + file.size, 0)
  })

  const handleDragOver = (event: DragEvent) => {
    event.preventDefault()
    isDragActive.value = true
  }

  const handleDragLeave = (event: DragEvent) => {
    event.preventDefault()
    isDragActive.value = false
  }

  const handleDrop = (event: DragEvent) => {
    event.preventDefault()
    isDragActive.value = false

    const files = Array.from(event.dataTransfer?.files || [])
    processFiles(files)
  }

  const handleFolderSelect = (event: Event) => {
    const target = event.target as HTMLInputElement
    const files = Array.from(target.files || [])
    processFiles(files)
  }

  const processFiles = (files: File[]) => {
    const supportedExts = [...supportedAudioExts, 'txt', 'json', 'rttm', 'stm']

    const filteredFiles = files.filter(file => {
      const fileExtension = file.name.split('.').pop()?.toLowerCase() || ''
      return supportedExts.includes(fileExtension)
    })

    if (filteredFiles.length > 0) {
      selectedFiles.value = [...filteredFiles]

      const audioFiles = filteredFiles.filter(file => {
        const ext = file.name.split('.').pop()?.toLowerCase() || ''
        return supportedAudioExts.includes(ext)
      })

      const folders = new Set<string>()
      audioFiles.forEach(file => {
        const relativePath = (file as any).webkitRelativePath
        if (relativePath) {
          const rootFolder = relativePath.split('/')[0]
          folders.add(rootFolder)
        } else {
          folders.add(file.name.split('.')[0])
        }
      })

      selectedFolders.value = Array.from(folders)

      selectedFolders.value.forEach(folder => {
        if (!folderGroupNames.value.has(folder)) {
          folderGroupNames.value.set(folder, folder)
        }
      })
    } else {
      selectedFiles.value = []
      selectedFolders.value = []
      folderGroupNames.value.clear()
    }

    if (folderInput.value) {
      folderInput.value.value = ''
    }
  }

  const updateFolderGroupName = (folder: string, groupName: string) => {
    folderGroupNames.value.set(folder, groupName)
  }

  const handleFolderGroupInput = (folder: string, event: Event) => {
    const target = event.target as HTMLInputElement
    updateFolderGroupName(folder, target.value)
  }

  const handleImport = async () => {
    if (selectedFiles.value.length === 0 || importing.value) return

    importing.value = true
    try {
      const audioFiles = selectedFiles.value.filter(file => {
        const ext = file.name.split('.').pop()?.toLowerCase() || ''
        return supportedAudioExts.includes(ext)
      })
      const txtFiles = selectedFiles.value.filter(file => file.name.toLowerCase().endsWith('.txt'))
      const annotationFiles = selectedFiles.value.filter(file =>
        file.name.toLowerCase().endsWith('.json') ||
        file.name.toLowerCase().endsWith('.jsonl') ||
        file.name.toLowerCase().endsWith('.rttm') ||
        file.name.toLowerCase().endsWith('.stm')
      )

      const txtDataMap = new Map<string, { asrText: string; translations: Array<{ text: string; direction: string }> }>()
      const annotationDataMap = new Map<string, any[]>()

      for (const txtFile of txtFiles) {
        try {
          const content = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = (e) => resolve(e.target?.result as string)
            reader.onerror = reject
            reader.readAsText(txtFile)
          })
          const parsedData = parseAudioTxtFile(content)

          const key = (txtFile as any).webkitRelativePath || txtFile.name
          const baseKey = key.substring(0, key.lastIndexOf('.'))
          txtDataMap.set(baseKey, parsedData)
        } catch (e) {
          console.error(`解析文本文件 ${txtFile.name} 失败:`, e)
        }
      }

      // 用策略模式解析 JSON 标注文件，每个 JSON 产生一个独立的测试用例分组
      // 分组键 = JSON 文件名去扩展名（如 9.json → "9"，环境音理解.json → "环境音理解"）
      // 支持 rounds 多轮 / flat 单轮 / txt 数组单轮 三种 JSON 格式
      // 未被任何 JSON 引用的音频回退到 folderParser 按文件名分组
      const jsonTestCaseFiles = annotationFiles.filter(f => f.name.toLowerCase().endsWith('.json'))
      const testCaseGroups = await buildTestCaseGroups(jsonTestCaseFiles)
      // 转为 unifiedRoundsByGroup 格式（兼容 audioImport.ts 的消费方式）
      const unifiedRoundsByGroup = new Map<string, any>()
      for (const [groupKey, group] of testCaseGroups) {
        const roundsWithMeta: any = group.rounds
        if (group.backgroundNoise) {
          roundsWithMeta._caseBackgroundNoise = group.backgroundNoise
        }
        unifiedRoundsByGroup.set(groupKey, roundsWithMeta)
      }

      // 非用例 JSON（rttm/stm/jsonl/annotations 格式）仍走标注附加路径
      const nonTestCaseAnnotationFiles = annotationFiles.filter(f => !f.name.toLowerCase().endsWith('.json'))
      for (const annFile of nonTestCaseAnnotationFiles) {
        try {
          const content = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = (e) => resolve(e.target?.result as string)
            reader.onerror = reject
            reader.readAsText(annFile)
          })

          let format = 'json'
          if (annFile.name.toLowerCase().endsWith('.rttm')) format = 'rttm'
          else if (annFile.name.toLowerCase().endsWith('.stm')) format = 'stm'
          else if (annFile.name.toLowerCase().endsWith('.jsonl')) format = 'jsonl'

          const parsedData = parseAnnotationFormat(content, format)

          const key = (annFile as any).webkitRelativePath || annFile.name
          const baseKey = key.substring(0, key.lastIndexOf('.'))
          // 标注文件所在目录路径（用于拼接 segment.audio 相对路径）
          const annDir = baseKey.includes('/') ? baseKey.substring(0, baseKey.lastIndexOf('/')) : ''

          if (parsedData.annotations && parsedData.annotations.length > 0) {
            const annotationsList = parsedData.annotations.map(ann => ({
              format: format,
              code: ann.code || 'asr',
              data: { segments: ann.segments, ...(ann.extra_fields || {}) },
              source_language: ann.source_language || '',
              target_language: ann.target_language || ''
            }))
            annotationDataMap.set(baseKey, annotationsList)
          } else if (parsedData.segments && parsedData.segments.length > 0) {
            const annotationCode = parsedData.code || determineAnnotationName(annFile.name, format)
            annotationDataMap.set(baseKey, [{
              format: format,
              code: annotationCode,
              data: { segments: parsedData.segments, ...(parsedData.extra_fields || {}) },
              source_language: parsedData.source_language || '',
              target_language: parsedData.target_language || ''
            }])
          }
        } catch (e) {
          console.error(`解析标注文件 ${annFile.name} 失败:`, e)
        }
      }

      // 用例 JSON 也需要为引用的音频附加标注（segments 里的非 audio 字段如 query/correctAnswer 等）
      for (const [groupKey, group] of testCaseGroups) {
        const annFile = jsonTestCaseFiles.find(f => {
          const key = (f as any).webkitRelativePath || f.name
          const baseKey = key.substring(0, key.lastIndexOf('.'))
          const fileName = baseKey.split('/').pop() || baseKey
          return fileName.replace(/\.[^.]+$/, '') === groupKey
        })
        if (!annFile) continue

        try {
          const content = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = (e) => resolve(e.target?.result as string)
            reader.onerror = reject
            reader.readAsText(annFile)
          })
          const rawJson = JSON.parse(content)
          const key = (annFile as any).webkitRelativePath || annFile.name
          const baseKey = key.substring(0, key.lastIndexOf('.'))
          const annDir = baseKey.includes('/') ? baseKey.substring(0, baseKey.lastIndexOf('/')) : ''

          // 从 rounds JSON 的 segments 提取标注，按 audio 分发到 annotationDataMap
          if (Array.isArray(rawJson.rounds)) {
            const annotationCode = rawJson.code || uploadConfig.algorithmType || determineAnnotationName(annFile.name, 'json')
            for (const round of rawJson.rounds) {
              if (!round || !Array.isArray(round.segments)) continue
              // 按 segment.audio 字段分组
              const segsByAudio = new Map<string, any[]>()
              for (const seg of round.segments) {
                if (!seg || typeof seg !== 'object') continue
                const audioPath = seg.audio || seg.audio_name || seg.audioName || ''
                if (audioPath) {
                  const segs = segsByAudio.get(audioPath) || []
                  segs.push(seg)
                  segsByAudio.set(audioPath, segs)
                }
              }
              for (const [audioPath, segs] of segsByAudio) {
                // 构造匹配 baseKey：标注目录 + audio 相对路径，去扩展名
                let matchKey = audioPath.replace(/\.[^.]+$/, '')
                if (annDir) {
                  matchKey = `${annDir}/${matchKey}`
                }
                // 也尝试不带目录前缀的文件名匹配
                const fileNameOnly = audioPath.split('/').pop()!.replace(/\.[^.]+$/, '')
                const existing = annotationDataMap.get(matchKey) || annotationDataMap.get(fileNameOnly) || []
                existing.push({
                  format: 'json',
                  code: annotationCode,
                  data: { segments: segs, round_number: round.round_number || round.roundNumber || 1 },
                  source_language: rawJson.source_language || '',
                  target_language: rawJson.target_language || ''
                })
                annotationDataMap.set(matchKey, existing)
              }
            }
          } else if (Array.isArray(rawJson.txt)) {
            // txt 数组 JSON：按 segment.audio 分发
            const annotationCode = rawJson.code || uploadConfig.algorithmType || determineAnnotationName(annFile.name, 'json')
            for (const item of rawJson.txt) {
              if (!item || typeof item !== 'object') continue
              const audioPath = item.audio || item.audio_name || item.audioName || ''
              if (audioPath) {
                let matchKey = audioPath.replace(/\.[^.]+$/, '')
                if (annDir) {
                  matchKey = `${annDir}/${matchKey}`
                }
                const fileNameOnly = audioPath.split('/').pop()!.replace(/\.[^.]+$/, '')
                const existing = annotationDataMap.get(matchKey) || annotationDataMap.get(fileNameOnly) || []
                existing.push({
                  format: 'json',
                  code: annotationCode,
                  data: { segments: [item] },
                  source_language: rawJson.source_language || '',
                  target_language: rawJson.target_language || ''
                })
                annotationDataMap.set(matchKey, existing)
              }
            }
          } else {
            // flat JSON：标注就是顶层字段，按 audio 分发
            const audioPath = rawJson.audio || rawJson.audio_name || rawJson.audioName || ''
            if (audioPath) {
              const annotationCode = rawJson.code || uploadConfig.algorithmType || determineAnnotationName(annFile.name, 'json')
              let matchKey = audioPath.replace(/\.[^.]+$/, '')
              if (annDir) {
                matchKey = `${annDir}/${matchKey}`
              }
              const fileNameOnly = audioPath.split('/').pop()!.replace(/\.[^.]+$/, '')
              const existing = annotationDataMap.get(matchKey) || annotationDataMap.get(fileNameOnly) || []
              existing.push({
                format: 'json',
                code: annotationCode,
                data: { segments: [rawJson] },
                source_language: rawJson.source_language || '',
                target_language: rawJson.target_language || ''
              })
              annotationDataMap.set(matchKey, existing)
            }
          }
        } catch (e) {
          console.error(`解析用例 JSON 标注 ${annFile.name} 失败:`, e)
        }
      }

      const filesWithMetadata: FileWithMetadata[] = audioFiles.map(file => {
        const key = (file as any).webkitRelativePath || file.name
        const baseKey = key.substring(0, key.lastIndexOf('.'))
        const metadata = txtDataMap.get(baseKey) || { asrText: '', translations: [] as Array<{ text: string; direction: string }> }
        // 标注匹配：先按完整 baseKey，再按文件名回退匹配（统一标注文件分发的场景）
        let annData = annotationDataMap.get(baseKey)
        if (!annData) {
          const fileNameOnly = baseKey.split('/').pop()!
          for (const [mapKey, mapVal] of annotationDataMap) {
            if (mapKey.split('/').pop() === fileNameOnly) {
              annData = mapVal
              break
            }
          }
        }

        let annotations: any[] = []

        if (annData && annData.length > 0) {
          annotations = annData.map(ann => {
            if (ann.format === 'json' || ann.format === 'rttm' || ann.format === 'stm') {
              const code = uploadConfig.algorithmType || determineAnnotationName(baseKey, ann.format)
              return {
                ...ann,
                name: code,
                code: code
              }
            }
            return ann
          })
        }

        if (metadata.asrText) {
          const hasAsr = annotations.some(a => a.name === 'asr')
          if (!hasAsr) {
            annotations.push({
              format: 'text',
              name: 'asr',
              data: { text: metadata.asrText },
              source_language: '',
              target_language: ''
            })
          }
        }

        if (metadata.translations && metadata.translations.length > 0) {
          for (const trans of metadata.translations) {
            annotations.push({
              format: 'text',
              name: 'translation',
              data: { text: trans.text },
              source_language: trans.direction?.split('-')[0] || '',
              target_language: trans.direction?.split('-')[1] || ''
            })
          }
        }

        return {
          file,
          asrText: metadata.asrText || '',
          translations: metadata.translations,
          annotations: annotations,
          speakerCount: annData ? extractSpeakersFromAnnotation(annData).speakerCount : 0,
          speakerNames: annData ? extractSpeakersFromAnnotation(annData).speakerNames : [],
          tags: []
        }
      })

      const filesWithTags = filesWithMetadata.map(f => ({
        ...f,
        tags: [...tags.value.split(',').map(t => t.trim()).filter(t => t),
              ...f.speakerNames,
              ...(f.speakerCount > 0 ? [`${f.speakerCount}人`] : [])]
      }))

      emit('confirm', {
        config: uploadConfig,
        files: filesWithTags,
        tags: tags.value.split(',').map(t => t.trim()).filter(t => t),
        folderGroupMappings: Object.fromEntries(folderGroupNames.value),
        selectedFolders: selectedFolders.value,
        algorithmParams: algorithmParams.value,
        unifiedRoundsByGroup: unifiedRoundsByGroup.size > 0 ? Object.fromEntries(unifiedRoundsByGroup) : undefined,
        testCaseGroups: testCaseGroups.size > 0 ? Object.fromEntries(testCaseGroups) : undefined,
        onProgressUpdate: (progress: number) => {
        },
        onImportComplete: () => {
        },
        onImportError: (error: Error) => {
          console.error('文件夹导入失败:', error)
        }
      })

      emit('close')

      selectedFiles.value = []
      selectedFolders.value = []
      folderGroupNames.value.clear()
      annotationCode.value = ''
    } catch (error) {
      console.error('文件夹导入失败:', error)
    } finally {
      importing.value = false
    }
  }

  const handleCancel = () => {
    emit('cancel')
    importing.value = false
    importProgress.value = 0
    selectedFiles.value = []
    selectedFolders.value = []
    folderGroupNames.value.clear()
    annotationCode.value = ''
    emit('close')
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
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

  const extractSpeakersFromAnnotation = (annotationData: any): { speakerCount: number; speakerNames: string[] } => {
    const speakerSet = new Set<string>()

    if (!annotationData) {
      return { speakerCount: 0, speakerNames: [] }
    }

    const annotations = Array.isArray(annotationData) ? annotationData : [annotationData]

    for (const ann of annotations) {
      const segments = ann.segments || (ann.data && ann.data.segments) || []
      for (const seg of segments) {
        if (seg.speaker && seg.speaker.trim()) {
          speakerSet.add(seg.speaker.trim())
        }
      }

      if (ann.annotations) {
        for (const nestedAnn of ann.annotations) {
          const nestedSegments = nestedAnn.segments || (nestedAnn.data && nestedAnn.data.segments) || []
          for (const seg of nestedSegments) {
            if (seg.speaker && seg.speaker.trim()) {
              speakerSet.add(seg.speaker.trim())
            }
          }
        }
      }
    }

    return {
      speakerCount: speakerSet.size,
      speakerNames: Array.from(speakerSet)
    }
  }

  return {
    folderInput,
    importing,
    isDragActive,
    importProgress,
    selectedFiles,
    tags,
    annotationCode,
    referenceParamOptions,
    uploadConfig,
    audioTypeOptions,
    playbackDeviceOptions,
    algorithmOptions,
    selectedFolders,
    folderGroupNames,
    audioFilesCount,
    dragMessage,
    canImport,
    hasUploadOptions,
    totalFileSize,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleFolderSelect,
    handleFolderGroupInput,
    handleImport,
    handleCancel,
    formatFileSize,
  }
}
