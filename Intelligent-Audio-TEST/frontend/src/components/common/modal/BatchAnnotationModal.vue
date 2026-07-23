<template>
  <div class="batch-annotation-modal">
    <h3>批量更新标注</h3>

    <div class="upload-content">
      <!-- 拖放区域 -->
      <div
        class="drop-zone"
        :class="{ 'drop-zone-active': isDragging }"
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
              支持音频：.wav, .mp3, .m4a, .flac 等<br>
              支持标注：.json, .jsonl, .rttm, .stm, .txt<br>
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
            <h4>正在计算 MD5 并匹配...</h4>
            <p class="drop-zone-hint">请稍候</p>
          </template>

          <template v-else>
            <h4>已解析 {{ annotationItems.length }} 个标注</h4>
            <p class="drop-zone-hint">
              {{ matchedCount }} 个匹配成功，{{ annotationItems.length - matchedCount }} 个未匹配
            </p>
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

      <!-- 算法类型选择 -->
      <div class="form-row" v-if="annotationItems.length > 0">
        <label class="form-label">算法类型：</label>
        <select v-model="algorithmType" class="form-input">
          <option value="">留空则从文件名推断</option>
          <option v-for="opt in algorithmOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </div>

      <!-- 刷新用例参考选项 -->
      <div class="form-row checkbox-row" v-if="annotationItems.length > 0">
        <label class="checkbox-label">
          <input type="checkbox" v-model="refreshTestCases" />
          <span>同步刷新关联测试用例的参考参数</span>
        </label>
        <p class="checkbox-hint">更新标注后自动重新提取用例参数并刷新参考参数</p>
      </div>

      <!-- 匹配结果列表 -->
      <div class="file-list" v-if="annotationItems.length > 0">
        <h4>标注匹配结果</h4>
        <div class="files-container">
          <div
            class="file-item"
            v-for="(item, index) in annotationItems"
            :key="index"
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
        </div>
      </div>
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
import { ref, computed, watch, onMounted } from 'vue'
import { parseAnnotationFormat, parseAudioTxtFile } from '../../../utils/audioUtils'
import { audiosApi } from '../../../utils/api'
import SparkMD5 from 'spark-md5'

const props = defineProps({
  algorithmOptions: { type: Array as () => Array<{ value: string; label: string }>, default: () => [] },
})

const emit = defineEmits(['close', 'success'])

const fileInput = ref(null)
const isDragging = ref(false)
const submitting = ref(false)
const md5Calculating = ref(false)
const algorithmType = ref('')
const refreshTestCases = ref(true)
const annotationItems = ref<any[]>([])

const matchedCount = computed(() => {
  return annotationItems.value.filter(item => item.matched).length
})

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

    reader.onerror = () => reject('MD5 calculation failed')

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
    reader.onerror = reject
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

const processFiles = async (files: File[]) => {
  const audioFiles = files.filter(isAudioFile)
  const annotationFiles = files.filter(isAnnotationFile)

  if (annotationFiles.length === 0) {
    return
  }

  md5Calculating.value = true

  try {
    // 1. 计算所有音频文件的 MD5
    const audioMd5Map = new Map<string, { file: File, name: string }>() // baseName → {file, name}
    const md5ToList: string[] = []

    for (const audioFile of audioFiles) {
      const md5 = await calculateMd5(audioFile)
      md5ToList.push(md5)
      const baseName = audioFile.name.replace(/\.[^.]+$/, '')
      audioMd5Map.set(md5, { file: audioFile, name: audioFile.name })
      // 也按 baseName 建立映射，用于和标注文件名匹配
    }

    // 2. 调后端 by-md5 接口批量查询
    let md5ToAudio: Record<string, { id: number; name: string }> = {}
    if (md5ToList.length > 0) {
      const res = await audiosApi.getByMd5(md5ToList)
      md5ToAudio = (res as any) || {}
    }

    // 3. 按文件名匹配音频和标注
    // baseName → md5 映射（用于通过文件名关联标注和音频）
    const baseNameToMd5 = new Map<string, string>()
    for (const [md5, info] of audioMd5Map.entries()) {
      const baseName = info.name.replace(/\.[^.]+$/, '')
      baseNameToMd5.set(baseName, md5)
    }

    // 4. 解析标注文件并匹配
    const items: any[] = []

    for (const annFile of annotationFiles) {
      const text = await readFileAsText(annFile)
      const baseName = annFile.name.replace(/\.[^.]+$/, '')

      // 通过文件名找到对应音频的 MD5，再查到 audio_id
      const md5 = baseNameToMd5.get(baseName)
      const audioInfo = md5 ? md5ToAudio[md5] : null
      const matched = !!audioInfo

      let annotations: any[] = []

      if (annFile.name.endsWith('.txt')) {
        const parsedInfo = parseAudioTxtFile(text)
        if (parsedInfo.asrText) {
          annotations.push({
            format: 'text',
            code: 'asr',
            data: { text: parsedInfo.asrText },
            source_language: '',
            target_language: ''
          })
        }
        if (parsedInfo.translations && parsedInfo.translations.length > 0) {
          for (const trans of parsedInfo.translations) {
            annotations.push({
              format: 'text',
              code: 'translation',
              data: { text: trans.text },
              source_language: trans.source || '',
              target_language: trans.target || ''
            })
          }
        }
      } else {
        let format = 'json'
        if (annFile.name.endsWith('.rttm')) format = 'rttm'
        else if (annFile.name.endsWith('.stm')) format = 'stm'
        else if (annFile.name.endsWith('.jsonl')) format = 'jsonl'

        const parsed = parseAnnotationFormat(text, format)
        const code = algorithmType.value || determineAnnotationName(annFile.name, format)

        if (parsed.annotations && parsed.annotations.length > 0) {
          for (const ann of parsed.annotations) {
            annotations.push({
              format: parsed.format,
              code: code,
              data: { segments: ann.segments, ...(parsed.extra_fields || {}) },
              source_language: parsed.source_language || '',
              target_language: parsed.target_language || ''
            })
          }
        } else if (parsed.segments && parsed.segments.length > 0) {
          annotations.push({
            format: parsed.format,
            code: code,
            data: { segments: parsed.segments, ...(parsed.extra_fields || {}) },
            source_language: parsed.source_language || '',
            target_language: parsed.target_language || ''
          })
        }
      }

      items.push({
        annotationFileName: annFile.name,
        audioName: matched ? audioInfo!.name : '',
        audioId: matched ? audioInfo!.id : null,
        matched,
        annotations,
      })
    }

    annotationItems.value = items
  } catch (e) {
    console.error('处理文件失败:', e)
  } finally {
    md5Calculating.value = false
  }
}

watch(algorithmType, () => {
  // 算法类型变化时重新解析
  if (annotationItems.value.length > 0 && fileInput.value?.files) {
    processFiles(Array.from(fileInput.value.files))
  }
})

const handleSubmit = async () => {
  const matchedItems = annotationItems.value.filter(item => item.matched)
  if (matchedItems.length === 0) return

  submitting.value = true
  try {
    const res = await audiosApi.batchUpdateAnnotations({
      items: matchedItems.map(item => ({
        audioId: item.audioId,
        annotations: item.annotations,
      })),
      algorithmType: algorithmType.value || undefined,
      refreshTestCases: refreshTestCases.value,
    })

    const data = (res as any) || {}
    emit('success', {
      updatedCount: data.updated_count || 0,
      failedCount: data.failed_count || 0,
      refreshedTestCaseIds: data.refreshed_test_case_ids || [],
    })
  } catch (e) {
    console.error('批量更新标注失败:', e)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.batch-annotation-modal {
}

h3 {
  margin: 0 0 20px 0;
  font-size: 18px;
  font-weight: 600;
  color: #334155;
}

.upload-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.drop-zone {
  border: 2px dashed #cbd5e1;
  border-radius: 8px;
  padding: 40px 20px;
  text-align: center;
  transition: all 0.2s ease;
  background-color: #f8fafc;
  cursor: pointer;
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
  gap: 12px;
}

.drop-zone-content i {
  font-size: 48px;
  color: #94a3b8;
  transition: color 0.2s ease;
}

.drop-zone:hover i,
.drop-zone-active i {
  color: #3b82f6;
}

.drop-zone h4 {
  margin: 0;
  font-size: 16px;
  color: #475569;
}

.drop-zone-hint {
  margin: 0;
  font-size: 13px;
  color: #94a3b8;
  line-height: 1.6;
}

.browse-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  background: #3b82f6;
  color: #fff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s ease;
}

.browse-btn:hover {
  background: #2563eb;
}

.browse-btn input[type="file"] {
  display: none;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.form-label {
  font-size: 14px;
  color: #475569;
  white-space: nowrap;
}

.form-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 14px;
}

.checkbox-row {
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #334155;
  cursor: pointer;
}

.checkbox-hint {
  margin: 0;
  font-size: 12px;
  color: #94a3b8;
}

.file-list h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: #475569;
}

.files-container {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 8px;
}

.file-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 8px;
  border-bottom: 1px solid #f1f5f9;
}

.file-item:last-child {
  border-bottom: none;
}

.file-item i {
  font-size: 16px;
  margin-top: 2px;
}

.has-match {
  color: #10b981;
}

.no-match {
  color: #ef4444;
}

.file-details {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-name {
  font-size: 13px;
  font-weight: 500;
  color: #1e293b;
}

.file-meta {
  display: flex;
  gap: 8px;
}

.meta-tag {
  font-size: 12px;
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

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
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
