import { ref, computed, watch } from 'vue'
import { useTestCaseConfig, createDefaultUploadConfig } from '../../../composables/testCase/useTestCaseConfig'
import { parseAudioTxtFile, parseAnnotationFormat, determineAnnotationType } from '../../../utils/audioUtils'
import { algorithmApi } from '../../../utils/api'

export function useUploadFileModal(props: any, emit: any) {
  const fileInput = ref(null)
  const selectedFiles = ref([])
  const selectedTxtFiles = ref([])
  const isDragging = ref(false)
  const uploading = ref(false)
  const tags = ref('')
  const annotationCode = ref('')
  const referenceParamOptions = ref<Array<{label: string; value: string}>>([])

  const inputId = computed(() => `file-input-${props.modalId || 'default'}`)

  const hasUploadOptions = computed(() => props.uploadOptions.length > 0)

  const uploadConfig = ref(
    Object.assign(
      createDefaultUploadConfig(),
      props.uploadOptions.reduce((acc, option) => {
        acc[option.key] = option.defaultValue ?? (option.type === 'boolean' ? false : '')
        return acc
      }, {})
    )
  )

  const {
    audioTypeOptions,
    hasAudioType
  } = useTestCaseConfig({
    audioTypeOptions: props.uploadOptions.find((o) => o.key === 'audioType')?.options || []
  })

  watch(() => uploadConfig.value.algorithmType, async (newType) => {
    referenceParamOptions.value = []
    annotationCode.value = ''
    if (newType) {
      try {
        const res = await algorithmApi.getReferenceParams(newType)
        referenceParamOptions.value = (res.data || []).map((p: any) => ({
          label: p.code ? `${p.code}${p.name ? ' - ' + p.name : ''}` : p.name,
          value: p.code || ''
        }))
      } catch (e) {
        console.error('加载参考参数失败:', e)
      }
    }
  })

  const playbackDeviceOptions = computed(() => {
    return props.uploadOptions.find((o) => o.key === 'playbackDeviceId')?.options || []
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
    const supportedAudioExts = props.supportedFormats
    return selectedFiles.value.filter(file => {
      const ext = file.file.name.split('.').pop()?.toLowerCase() || ''
      return supportedAudioExts.includes(ext)
    }).length
  })

  const totalFileSize = computed(() => {
    return selectedFiles.value.reduce((sum, file) => sum + file.file.size, 0)
  })

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const dragMessage = computed(() => {
    if (isDragging.value) {
      return '释放文件以上传'
    }
    return '拖拽文件到此处或点击选择文件'
  })

  const handleFileSelect = (event) => {
    const files = Array.from(event.target.files)
    if (files.length > 0) {
      processFiles(files)
    }
  }

  const handleDragOver = (event) => {
    isDragging.value = true
  }

  const handleDragLeave = (event) => {
    isDragging.value = false
  }

  const handleDrop = (event) => {
    isDragging.value = false
    const files = Array.from(event.dataTransfer.files)
    if (files.length > 0) {
      processFiles(files)
    }
  }

  const processFiles = (files) => {
    const audioFiles = files.filter(file => file.type.startsWith('audio/') || file.type.startsWith('video/'))
    const txtFiles = files.filter(file => file.name.endsWith('.txt'))
    const annotationFiles = files.filter(file =>
        file.name.endsWith('.json') || file.name.endsWith('.jsonl') || file.name.endsWith('.rttm') || file.name.endsWith('.stm')
    )

    selectedTxtFiles.value = txtFiles.map(file => ({
      file,
      name: file.name
    }))

    const txtMarkers = new Map()
    const annotationData = new Map()

    const readAnnotationFiles = async () => {
        for (const annFile of annotationFiles) {
            const text = await readFileAsText(annFile)
            const audioFileName = annFile.name.replace(/\.(json|rttm|stm)$/, '')
            let format = 'json'
            if (annFile.name.endsWith('.rttm')) format = 'rttm'
            else if (annFile.name.endsWith('.stm')) format = 'stm'
            else if (annFile.name.endsWith('.jsonl')) format = 'jsonl'

            const parsed = parseAnnotationFormat(text, format)
            annotationData.set(audioFileName, parsed)
        }
    }

    const readTxtFiles = async () => {
      for (const txtFile of txtFiles) {
        const text = await readFileAsText(txtFile)
        const audioFileName = txtFile.name.replace(/\.txt$/, '')
        txtMarkers.set(audioFileName, text)
      }

      const processedFiles = await Promise.all(audioFiles.map(async (audioFile) => {
        const audioFileName = audioFile.name.replace(/\.[^/.]+$/, '')
        const markerText = txtMarkers.get(audioFileName) || ''
        const parsedInfo = parseMarkerText(markerText)

        const annData = annotationData.get(audioFileName)
        const annotations = []

        if (annData && annData.annotations && annData.annotations.length > 0) {
            for (const ann of annData.annotations) {
                const code = uploadConfig.value.algorithmType || determineAnnotationName(audioFileName, annData.format)
                annotations.push({
                    format: annData.format,
                    code: code,
                    data: { segments: ann.segments, ...(ann.extra_fields || {}) },
                    source_language: ann.source_language || '',
                    target_language: ann.target_language || ''
                })
            }
        } else if (annData && annData.segments && annData.segments.length > 0) {
            const annotationCodeVal = uploadConfig.value.algorithmType || determineAnnotationName(audioFileName, annData.format)
            annotations.push({
                format: annData.format,
                code: annotationCodeVal,
                data: { segments: annData.segments, ...(annData.extra_fields || {}) },
                source_language: annData.source_language || '',
                target_language: annData.target_language || ''
            })
        } else if (markerText) {
            annotations.push({
                format: 'text',
                code: 'asr',
                data: { text: markerText },
                source_language: '',
                target_language: ''
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
                    source_language: trans.source || '',
                    target_language: trans.target || ''
                })
            }
        }

        return {
          file: audioFile,
          name: audioFile.name,
          asrText: markerText || '',
          translations: parsedInfo.translations || [],
          annotations: annotations,
          hasTxtFile: txtMarkers.has(audioFileName) || annotationData.has(audioFileName),
          speakerCount: annData ? extractSpeakersFromAnnotation(annData).speakerCount : 0,
          speakerNames: annData ? extractSpeakersFromAnnotation(annData).speakerNames : []
        }
      }))

      selectedFiles.value = processedFiles
    }

    readAnnotationFiles().then(() => readTxtFiles())
  }

  const readFileAsText = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = (e) => {
        resolve(e.target.result)
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

  // Placeholder for parseMarkerText - should be imported from utils or kept inline if needed
  const parseMarkerText = (text) => {
    const lines = text.split('\n').map(line => line.trim()).filter(line => line)
    const result = {
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

      const filesWithMetadata = selectedFiles.value.map(item => {
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
        progress: (p) => {}
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
