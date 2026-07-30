<template>
  <div class="batch-annotation-modal">
    <div class="upload-content">
      <!-- 拖放区域（紧凑：有文件后收缩） -->
      <div
        class="drop-zone"
        :class="{ 'drop-zone-active': isDragging, 'drop-zone-compact': annotationItems.length > 0 || md5Calculating }"
        @dragover.prevent="handleDragOver"
        @dragleave.prevent="handleDragLeave"
        @drop.prevent="handleDrop"
      >
        <div class="drop-zone-content">
          <i v-if="annotationItems.length === 0 && !md5Calculating" class="fas fa-file-import"></i>
          <i v-else-if="md5Calculating" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-check-circle"></i>

          <template v-if="annotationItems.length === 0 && !md5Calculating">
            <h4>拖拽音频+标注文件到此处或点击选择</h4>
            <p class="drop-zone-hint">
              同时选择音频文件和对应的标注文件<br>
              支持音频：.wav, .mp3, .m4a, .flac 等；标注：.json, .jsonl, .rttm, .stm, .txt<br>
              按文件名匹配（如 audio1.wav ↔ audio1.json）
            </p>
            <label class="browse-btn">
              <input
                type="file"
                ref="fileInput"
                accept=".wav,.mp3,.m4a,.flac,.aac,.ogg,.json,.jsonl,.rttm,.stm,.txt"
                multiple
                @change="handleFileSelect"
              >
              选择文件
            </label>
          </template>

          <template v-else-if="md5Calculating">
            <h4>正在处理... {{ progress.processed }} / {{ progress.total }}</h4>
            <div class="progress-bar-wrap">
              <div class="progress-bar" :style="{ width: progressPercent + '%' }"></div>
            </div>
            <p class="drop-zone-hint">{{ progress.stage }} · {{ progressPercent }}%</p>
            <button class="btn-cancel" @click="cancelProcessing">取消</button>
          </template>

          <template v-else>
            <div class="compact-summary">
              <span>已解析 <strong>{{ annotationItems.length }}</strong> 个标注</span>
              <span class="dot">·</span>
              <span class="matched">匹配 {{ matchedCount }}</span>
              <span class="dot">·</span>
              <span class="unmatched">未匹配 {{ annotationItems.length - matchedCount }}</span>
            </div>
            <label class="browse-btn">
              <input
                type="file"
                ref="fileInput"
                accept=".wav,.mp3,.m4a,.flac,.aac,.ogg,.json,.jsonl,.rttm,.stm,.txt"
                multiple
                @change="handleFileSelect"
              >
              重新选择
            </label>
          </template>
        </div>
      </div>

      <!-- 算法 + checkbox 并排 -->
      <div class="options-row" v-if="annotationItems.length > 0">
        <div class="algorithm-col">
          <AlgorithmSelector
            v-model="algorithmType"
            :show-params="false"
            :single="true"
          />
        </div>
        <div class="checkbox-col">
          <label class="checkbox-label">
            <input type="checkbox" v-model="refreshTestCases" />
            <span>同步刷新关联测试用例的参考参数</span>
          </label>
          <p class="checkbox-hint">更新后自动重新提取用例参数</p>
        </div>
      </div>

      <!-- 结果列表（虚拟/限量渲染） -->
      <div class="file-list" v-if="annotationItems.length > 0">
        <div class="file-list-header">
          <h4>标注匹配结果</h4>
          <div class="file-list-actions">
            <button v-if="unmatchedItems.length > 0" class="link-btn" @click="exportUnmatched">
              <i class="fas fa-download"></i> 导出未匹配 ({{ unmatchedItems.length }})
            </button>
            <label class="filter-toggle">
              <input type="checkbox" v-model="showUnmatchedOnly" :disabled="unmatchedItems.length === 0">
              <span>仅看未匹配</span>
            </label>
          </div>
        </div>
        <div class="files-container" ref="filesContainerRef" @scroll="onScroll">
          <div
            class="file-item"
            v-for="item in visibleItems"
            :key="item.annotationFileName"
          >
            <i class="fas" :class="item.matched ? 'fa-link has-match' : 'fa-unlink no-match'"></i>
            <div class="file-details">
              <span class="file-name">{{ item.annotationFileName }}</span>
              <span class="file-meta" v-if="item.matched">
                <span class="meta-tag has-match">→ {{ item.audioName }} (ID: {{ item.audioId }})</span>
              </span>
              <span class="file-meta" v-else>
                <span class="meta-tag no-match">未匹配到音频</span>
              </span>
              <div class="annotation-summary" v-if="item.annotations.length > 0">
                <span class="ann-tag" v-for="(ann, idx) in item.annotations" :key="idx">
                  {{ ann.code }} ({{ ann.format }})
                </span>
              </div>
            </div>
          </div>
          <div v-if="displayedItems.length < filteredItems.length" class="load-more-hint">
            已加载 {{ displayedItems.length }} / {{ filteredItems.length }} 条（滚动加载更多）
          </div>
        </div>
      </div>
    </div>

    <!-- 完成统计 toast -->
    <div v-if="resultToast.visible" class="result-toast" :class="resultToast.type">
      <i class="fas" :class="resultToast.type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'"></i>
      <div class="toast-body">
        <strong>{{ resultToast.title }}</strong>
        <span>{{ resultToast.detail }}</span>
      </div>
      <button class="toast-close" @click="resultToast.visible = false">×</button>
    </div>

    <!-- 错误提示 -->
    <div v-if="errorMsg" class="error-banner">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ errorMsg }}</span>
      <button class="toast-close" @click="errorMsg = ''">×</button>
    </div>

    <div class="modal-footer">
      <button
        type="button"
        class="btn-secondary"
        @click="$emit('close')"
        :disabled="submitting"
      >
        取消
      </button>
      <button
        type="button"
        class="btn-primary"
        @click="handleSubmit"
        :disabled="matchedCount === 0 || submitting"
      >
        <span v-if="submitting" class="loading-spinner"></span>
        {{ submitting ? '提交中...' : `更新标注 (${matchedCount})` }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { parseAnnotationFormat, parseAudioTxtFile } from '../../../utils/audioUtils'
import { audiosApi } from '../../../utils/api'
import SparkMD5 from 'spark-md5'
import AlgorithmSelector from '../audio/AlgorithmSelector.vue'

defineProps({})
const emit = defineEmits(['close', 'success'])

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
</script>

<style scoped>
.batch-annotation-modal {
}

.upload-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 紧凑模式 drop-zone */
.drop-zone {
  border: 2px dashed #cbd5e1;
  border-radius: 8px;
  padding: 32px 20px;
  text-align: center;
  transition: all 0.2s ease;
  background-color: #f8fafc;
  cursor: pointer;
}

.drop-zone.drop-zone-compact {
  padding: 14px 16px;
}

.drop-zone:hover,
.drop-zone-active {
  border-color: #3b82f6;
  background-color: #eff6ff;
}

.drop-zone-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.drop-zone-content i {
  font-size: 40px;
  color: #94a3b8;
  transition: color 0.2s ease;
}

.drop-zone-compact .drop-zone-content i {
  font-size: 22px;
}

.drop-zone:hover i,
.drop-zone-active i {
  color: #3b82f6;
}

.drop-zone h4 {
  margin: 0;
  font-size: 15px;
  color: #475569;
}

.drop-zone-hint {
  margin: 0;
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.6;
}

.browse-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  background: #3b82f6;
  color: #fff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.2s ease;
}

.browse-btn:hover {
  background: #2563eb;
}

.browse-btn input[type="file"] {
  display: none;
}

.compact-summary {
  font-size: 13px;
  color: #475569;
  display: flex;
  align-items: center;
  gap: 8px;
}

.compact-summary .dot { color: #cbd5e1; }
.compact-summary .matched { color: #10b981; }
.compact-summary .unmatched { color: #ef4444; }

/* 进度条 */
.progress-bar-wrap {
  width: 100%;
  max-width: 320px;
  height: 8px;
  background: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: #3b82f6;
  border-radius: 4px;
  transition: width 0.2s ease;
}

.btn-cancel {
  padding: 4px 14px;
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fca5a5;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}

.btn-cancel:hover { background: #fecaca; }

/* 算法 + checkbox 紧凑垂直排列 */
.options-row {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.algorithm-col {
  min-width: 0;
}

/* 压缩 AlgorithmSelector 内部多余间距 */
.algorithm-col :deep(.options-grid) {
  gap: 0;
  grid-template-columns: 1fr;
}

.algorithm-col :deep(.option-item) {
  gap: 0;
}

.algorithm-col :deep(.option-item label) {
  font-size: 13px;
  font-weight: 500;
  color: #475569;
  margin-bottom: 4px;
}

.algorithm-col :deep(.select-header) {
  min-height: 38px;
  padding: 6px 12px;
  border-width: 1px;
  border-color: #cbd5e1;
  background: #fff;
}

/* 单选模式隐藏关闭按钮 */
.algorithm-col :deep(.algo-tag .fa-times) {
  display: none;
}

.algorithm-col :deep(.algo-tag) {
  padding: 3px 10px;
  font-size: 13px;
}

.algorithm-col :deep(.dropdown-icon) {
  font-size: 13px;
  color: #94a3b8;
}

.checkbox-col {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #334155;
  cursor: pointer;
}

.checkbox-hint {
  margin: 0;
  font-size: 11px;
  color: #94a3b8;
  padding-left: 32px;
}

/* 结果列表 */
.file-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.file-list h4 {
  margin: 0;
  font-size: 13px;
  color: #475569;
}

.file-list-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.link-btn {
  background: none;
  border: none;
  color: #3b82f6;
  font-size: 12px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.link-btn:hover { text-decoration: underline; }

.filter-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #64748b;
  cursor: pointer;
}

.files-container {
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 6px;
}

.file-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 8px;
  border-bottom: 1px solid #f1f5f9;
}

.file-item:last-child {
  border-bottom: none;
}

.file-item i {
  font-size: 15px;
  margin-top: 2px;
}

.has-match { color: #10b981; }
.no-match { color: #ef4444; }

.file-details {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.file-name {
  font-size: 12px;
  font-weight: 500;
  color: #1e293b;
}

.file-meta {
  display: flex;
  gap: 8px;
}

.meta-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
}

.meta-tag.has-match {
  background: #d1fae5;
  color: #065f46;
}

.meta-tag.no-match {
  background: #fee2e2;
  color: #991b1b;
}

.annotation-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.ann-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  background: #e0e7ff;
  color: #3730a3;
}

.load-more-hint {
  text-align: center;
  padding: 10px;
  font-size: 12px;
  color: #94a3b8;
}

/* toast */
.result-toast {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 12px;
  font-size: 13px;
}

.result-toast.success {
  background: #d1fae5;
  color: #065f46;
  border: 1px solid #6ee7b7;
}

.result-toast.error {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fca5a5;
}

.result-toast i { font-size: 18px; }

.toast-body {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.toast-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: inherit;
  opacity: 0.6;
}

.toast-close:hover { opacity: 1; }

.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #fcd34d;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 16px;
}

.btn-primary,
.btn-secondary {
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-primary {
  background: #3b82f6;
  color: #fff;
  border: none;
}

.btn-primary:hover:not(:disabled) {
  background: #2563eb;
}

.btn-primary:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}

.btn-secondary {
  background: #f1f5f9;
  color: #475569;
  border: 1px solid #cbd5e1;
}

.btn-secondary:hover:not(:disabled) {
  background: #e2e8f0;
}

.loading-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  margin-right: 6px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
