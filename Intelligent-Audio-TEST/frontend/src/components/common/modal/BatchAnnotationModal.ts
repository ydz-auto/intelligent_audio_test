import { ref, computed, watch } from 'vue'
import { parseAnnotationFormat, parseAudioTxtFile } from '../../../utils/audioUtils'
import { audiosApi } from '../../../utils/api'
import SparkMD5 from 'spark-md5'

export function useBatchAnnotationModal(props: any, emit: any) {
  const fileInput = ref(null)
  const isDragging = ref(false)
  const submitting = ref(false)
  const md5Calculating = ref(false)
  const algorithmType = ref('')
  const refreshTestCases = ref(true)
  const annotationItems = ref<any[]>([])
  const errorMsg = ref('')

  // 进度状态
  const progress = ref({ processed: 0, total: 0, stage: '' })
  const progressPercent = computed(() => progress.value.total > 0 ? Math.round(progress.value.processed / progress.value.total * 100) : 0)

  // 取消标志
  let cancelled = false
  const cancelProcessing = () => { cancelled = true }

  // 结果 toast
  const resultToast = ref({ visible: false, type: 'success' as 'success' | 'error', title: '', detail: '' })

  // 列表虚拟/限量渲染
  const PAGE_SIZE = 200
  const visibleCount = ref(PAGE_SIZE)
  const showUnmatchedOnly = ref(false)
  const filesContainerRef = ref<HTMLElement | null>(null)

  const matchedItems = computed(() => annotationItems.value.filter(i => i.matched))
  const unmatchedItems = computed(() => annotationItems.value.filter(i => !i.matched))
  const filteredItems = computed(() => showUnmatchedOnly.value ? unmatchedItems.value : annotationItems.value)
  const displayedItems = computed(() => filteredItems.value.slice(0, visibleCount.value))
  // 兼容旧模板 visibleItems 命名
  const visibleItems = displayedItems

  const matchedCount = computed(() => matchedItems.value.length)

  const onScroll = () => {
    const el = filesContainerRef.value
    if (!el) return
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 50) {
      if (visibleCount.value < filteredItems.value.length) {
        visibleCount.value = Math.min(visibleCount.value + PAGE_SIZE, filteredItems.value.length)
      }
    }
  }

  watch(showUnmatchedOnly, () => { visibleCount.value = PAGE_SIZE })

  const calculateMd5 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const chunkSize = 10 * 1024 * 1024
      const chunks = Math.ceil(file.size / chunkSize)
      const spark = new SparkMD5.ArrayBuffer()
      const reader = new FileReader()
      let currentChunk = 0

      reader.onload = (e) => {
        if (e.target?.result) {
          spark.append(e.target.result as ArrayBuffer)
          currentChunk++
          if (currentChunk < chunks) {
            loadNext()
          } else {
            resolve(spark.end())
          }
        }
      }

      reader.onerror = () => reject(new Error(`MD5 计算失败: ${file.name}`))

      function loadNext() {
        const start = currentChunk * chunkSize
        const end = Math.min(start + chunkSize, file.size)
        reader.readAsArrayBuffer(file.slice(start, end))
      }

      loadNext()
    })
  }

  const readFileAsText = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = (e) => resolve(e.target?.result as string)
      reader.onerror = () => reject(new Error(`读取文件失败: ${file.name}`))
      reader.readAsText(file)
    })
  }

  const determineAnnotationName = (fileName: string, format: string): string => {
    const lowerName = fileName.toLowerCase()
    if (lowerName.includes('asr') || lowerName.includes('result')) return 'asr'
    if (lowerName.includes('trans') || lowerName.includes('翻译')) return 'translation'
    if (lowerName.includes('ref') || lowerName.includes('reference')) return 'reference'
    if (lowerName.includes('diar') || lowerName.includes('speaker')) return 'diarization'
    if (format === 'rttm' || format === 'stm') return 'diarization'
    return 'reference'
  }

  const isAudioFile = (file: File): boolean => {
    const audioExts = ['wav', 'mp3', 'm4a', 'flac', 'aac', 'ogg']
    const ext = file.name.split('.').pop()?.toLowerCase() || ''
    return audioExts.includes(ext)
  }

  const isAnnotationFile = (file: File): boolean => {
    const annExts = ['json', 'jsonl', 'rttm', 'stm', 'txt']
    const ext = file.name.split('.').pop()?.toLowerCase() || ''
    return annExts.includes(ext)
  }

  const handleFileSelect = (event: Event) => {
    const files = Array.from((event.target as HTMLInputElement).files || [])
    if (files.length > 0) {
      processFiles(files)
    }
  }

  const handleDragOver = () => {
    isDragging.value = true
  }

  const handleDragLeave = () => {
    isDragging.value = false
  }

  const handleDrop = (event: DragEvent) => {
    isDragging.value = false
    const files = Array.from(event.dataTransfer?.files || [])
    if (files.length > 0) {
      processFiles(files)
    }
  }

  // 超阈值确认
  const LARGE_THRESHOLD = 500
  const confirmLargeBatch = (count: number): Promise<boolean> => {
    if (count <= LARGE_THRESHOLD) return Promise.resolve(true)
    return new Promise(resolve => {
      const ok = window.confirm(`即将处理 ${count} 个文件，可能耗时较长。是否继续？`)
      resolve(ok)
    })
  }

  // 分块调用后端 by-md5，避免单次 IN 列表过大
  const fetchMd5Batched = async (md5List: string[]): Promise<Record<string, { id: number; name: string }>> => {
    const result: Record<string, { id: number; name: string }> = {}
    const BATCH = 500
    for (let i = 0; i < md5List.length; i += BATCH) {
      if (cancelled) break
      const chunk = md5List.slice(i, i + BATCH)
      progress.value.stage = `查询音频 (${i + chunk.length}/${md5List.length})`
      const res = await audiosApi.getByMd5(chunk)
      Object.assign(result, (res as any) || {})
    }
    return result
  }

  const processFiles = async (files: File[]) => {
    const audioFiles = files.filter(isAudioFile)
    const annotationFiles = files.filter(isAnnotationFile)

    if (annotationFiles.length === 0) {
      errorMsg.value = '未选择标注文件（支持 .json/.jsonl/.rttm/.stm/.txt）'
      return
    }

    // 超阈值确认
    const total = audioFiles.length + annotationFiles.length
    const ok = await confirmLargeBatch(total)
    if (!ok) return

    errorMsg.value = ''
    cancelled = false
    md5Calculating.value = true
    progress.value = { processed: 0, total: audioFiles.length + annotationFiles.length, stage: '计算 MD5' }

    try {
      // 1. 分批计算音频 MD5（并发 N 个）
      const baseNameToMd5 = new Map<string, string>()
      const md5ToList: string[] = []
      const CONCURRENCY = 4
      for (let i = 0; i < audioFiles.length; i += CONCURRENCY) {
        if (cancelled) break
        const batch = audioFiles.slice(i, i + CONCURRENCY)
        const results = await Promise.all(batch.map(async (f) => {
          try {
            const md5 = await calculateMd5(f)
            return { md5, name: f.name, file: f }
          } catch (e) {
            console.error((e as Error).message)
            return null
          }
        }))
        for (const r of results) {
          if (!r) continue
          md5ToList.push(r.md5)
          const baseName = r.name.replace(/\.[^.]+$/, '')
          baseNameToMd5.set(baseName, r.md5)
        }
        progress.value.processed = Math.min(i + CONCURRENCY, audioFiles.length)
      }

      // 2. 分批查后端
      let md5ToAudio: Record<string, { id: number; name: string }> = {}
      if (md5ToList.length > 0) {
        md5ToAudio = await fetchMd5Batched(md5ToList)
      }

      // 3. 解析标注并匹配
      progress.value.stage = '解析标注文件'
      const items: any[] = []
      for (let i = 0; i < annotationFiles.length; i++) {
        if (cancelled) break
        const annFile = annotationFiles[i]
        try {
          const text = await readFileAsText(annFile)
          const baseName = annFile.name.replace(/\.[^.]+$/, '')
          const md5 = baseNameToMd5.get(baseName)
          const audioInfo = md5 ? md5ToAudio[md5] : null
          const matched = !!audioInfo
          const annotations = parseAnnotationContent(annFile.name, text)
          items.push({
            annotationFileName: annFile.name,
            audioName: matched ? audioInfo!.name : '',
            audioId: matched ? audioInfo!.id : null,
            matched,
            annotations,
          })
        } catch (e) {
          errorMsg.value = (e as Error).message
        }
        progress.value.processed = audioFiles.length + i + 1
      }

      if (!cancelled) {
        annotationItems.value = items
        visibleCount.value = PAGE_SIZE
        showUnmatchedOnly.value = false
      }
    } catch (e) {
      errorMsg.value = `处理失败: ${(e as Error).message}`
    } finally {
      md5Calculating.value = false
      progress.value = { processed: 0, total: 0, stage: '' }
    }
  }

  // 抽取标注解析逻辑
  const parseAnnotationContent = (fileName: string, text: string): any[] => {
    const annotations: any[] = []
    if (fileName.endsWith('.txt')) {
      const parsedInfo = parseAudioTxtFile(text)
      if (parsedInfo.asrText) {
        annotations.push({
          format: 'text', code: 'asr', data: { text: parsedInfo.asrText },
          source_language: '', target_language: ''
        })
      }
      if (parsedInfo.translations && parsedInfo.translations.length > 0) {
        for (const trans of parsedInfo.translations) {
          annotations.push({
            format: 'text', code: 'translation', data: { text: trans.text },
            source_language: trans.source || '', target_language: trans.target || ''
          })
        }
      }
    } else {
      let format = 'json'
      if (fileName.endsWith('.rttm')) format = 'rttm'
      else if (fileName.endsWith('.stm')) format = 'stm'
      else if (fileName.endsWith('.jsonl')) format = 'jsonl'

      const parsed = parseAnnotationFormat(text, format)
      const code = algorithmType.value || determineAnnotationName(fileName, format)

      if (parsed.annotations && parsed.annotations.length > 0) {
        for (const ann of parsed.annotations) {
          annotations.push({
            format: parsed.format, code, data: { segments: ann.segments, ...(parsed.extra_fields || {}) },
            source_language: parsed.source_language || '', target_language: parsed.target_language || ''
          })
        }
      } else if (parsed.segments && parsed.segments.length > 0) {
        annotations.push({
          format: parsed.format, code, data: { segments: parsed.segments, ...(parsed.extra_fields || {}) },
          source_language: parsed.source_language || '', target_language: parsed.target_language || ''
        })
      }
    }
    return annotations
  }

  const exportUnmatched = () => {
    const lines = unmatchedItems.value.map(i => i.annotationFileName)
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `未匹配标注_${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleSubmit = async () => {
    const matchedItemsList = annotationItems.value.filter(item => item.matched)
    if (matchedItemsList.length === 0) return

    submitting.value = true
    errorMsg.value = ''
    try {
      const res = await audiosApi.batchUpdateAnnotations({
        items: matchedItemsList.map(item => ({
          audioId: item.audioId,
          annotations: item.annotations,
        })),
        algorithmType: algorithmType.value || undefined,
        refreshTestCases: refreshTestCases.value,
      })

      const data = (res as any) || {}
      const payload = {
        updatedCount: data.updated_count || 0,
        failedCount: data.failed_count || 0,
        refreshedTestCaseIds: data.refreshed_test_case_ids || [],
      }
      resultToast.value = {
        visible: true,
        type: 'success',
        title: '更新完成',
        detail: `成功 ${payload.updatedCount} 个，失败 ${payload.failedCount} 个，刷新用例 ${payload.refreshedTestCaseIds.length} 个`,
      }
      emit('success', payload)
    } catch (e) {
      const msg = (e as Error).message || '未知错误'
      errorMsg.value = `批量更新标注失败: ${msg}`
      resultToast.value = { visible: true, type: 'error', title: '更新失败', detail: msg }
    } finally {
      submitting.value = false
    }
  }

  watch(algorithmType, (newVal) => {
    // 算法变化后，重新设置已解析标注的 code（txt 的 asr/translation 不受影响）
    if (!newVal) return
    for (const item of annotationItems.value) {
      for (const ann of item.annotations) {
        if (ann.format === 'text') continue // txt 的 asr/translation 固定
        ann.code = newVal
      }
    }
  })

  return {
    fileInput,
    isDragging,
    submitting,
    md5Calculating,
    algorithmType,
    refreshTestCases,
    annotationItems,
    errorMsg,
    progress,
    progressPercent,
    cancelProcessing,
    resultToast,
    showUnmatchedOnly,
    filesContainerRef,
    matchedCount,
    unmatchedItems,
    filteredItems,
    displayedItems,
    visibleItems,
    onScroll,
    handleFileSelect,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    exportUnmatched,
    handleSubmit
  }
}
