<template>
  <div class="upload-file-modal">
    <h3>{{ title || '上传文件' }}</h3>
    
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
          <i v-if="selectedFiles.length === 0" class="fas fa-cloud-upload-alt"></i>
          <i v-else class="fas fa-folder-open"></i>
          
          <template v-if="selectedFiles.length === 0">
            <h4>{{ dragMessage }}</h4>
            <p class="drop-zone-hint">
              支持格式：{{ acceptedTypes.join(', ') }}<br>
              选择或拖拽音频文件进行上传
            </p>
            <label class="browse-btn">
              <input 
                type="file" 
                :id="inputId"
                ref="fileInput"
                :accept="acceptedTypes"
                :multiple="multiple"
                @change="handleFileSelect"
              >
              选择文件
            </label>
          </template>
          
          <template v-else>
            <h4>已选择 {{ selectedFiles.length }} 个文件</h4>
            <p class="drop-zone-hint">
              支持格式：{{ acceptedTypes.join(', ') }}
            </p>
            <label class="browse-btn">
              <input 
                type="file" 
                :id="inputId"
                ref="fileInput"
                :accept="acceptedTypes"
                :multiple="multiple"
                @change="handleFileSelect"
              >
              重新选择
            </label>
          </template>
        </div>
      </div>
      
      <!-- 文件统计信息 -->
      <div class="file-stats" v-if="selectedFiles.length > 0 || selectedTxtFiles.length > 0">
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-label">音频文件数量</span>
            <span class="stat-value">{{ audioFilesCount }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">文本文件数量</span>
            <span class="stat-value">{{ selectedTxtFiles.length }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">总大小</span>
            <span class="stat-value">{{ formatFileSize(totalFileSize) }}</span>
          </div>
        </div>
      </div>
      
      <!-- 选中的文本文件列表 -->
      <div class="file-list" v-if="selectedTxtFiles.length > 0">
        <h4>已选择的文本文件</h4>
        <div class="files-container">
          <div class="file-item" v-for="(txtFile, index) in selectedTxtFiles" :key="index">
            <i class="fas fa-file-alt txt-file-icon"></i>
            <div class="file-details">
              <span class="file-name">{{ txtFile.name }}</span>
              <span class="file-size">{{ formatFileSize(txtFile.file.size) }}</span>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 音频文件关联信息 -->
      <div class="file-list" v-if="selectedFiles.length > 0">
        <h4>音频文件关联信息</h4>
        <div class="files-container">
          <div class="file-item audio-file-item" v-for="(fileItem, index) in selectedFiles" :key="index">
            <i class="fas fa-file-audio audio-file-icon"></i>
            <div class="file-details">
              <span class="file-name">{{ fileItem.name }}</span>
              <span class="file-size">{{ formatFileSize(fileItem.file.size) }}</span>
              <div class="file-meta" v-if="fileItem.hasTxtFile">
                <span class="meta-tag has-txt">已关联文本文件</span>
                <div class="meta-content" v-if="fileItem.asrText">
                  <div class="meta-label">ASR文本:</div>
                  <div class="meta-value">{{ fileItem.asrText }}</div>
                </div>
                <div class="meta-content" v-if="fileItem.translations && fileItem.translations.length > 0">
                  <div class="meta-label">翻译:</div>
                  <div class="translations-list">
                    <div class="translation-item" v-for="(trans, idx) in fileItem.translations" :key="idx">
                      <span class="direction">{{ trans.direction }}</span>
                      <span class="text">{{ trans.text }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div class="file-meta" v-else>
                <span class="meta-tag no-txt">未关联文本文件</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 标注 Code 选择 -->
      <div class="annotation-code-config" v-if="selectedFiles.length > 0 && referenceParamOptions.length > 0">
        <div class="form-row">
          <label>标注代码：</label>
          <select v-model="annotationCode" class="form-input">
            <option value="">留空则使用 JSON 内 code/name 字段</option>
            <option v-for="opt in referenceParamOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>
      </div>
      
      <!-- 上传选项 -->
      <UploadOptions
        v-if="hasUploadOptions"
        v-model="uploadConfig"
        v-model:tags="tags"
        :audio-type-options="audioTypeOptions"
        :playback-device-options="playbackDeviceOptions"
        :device-options="deviceOptions"
        :algorithm-options="algorithmOptions"
        :show-tags-input="showTagsInput"
      />
    </div>
    
    <div class="modal-footer">
      <button 
        type="button" 
        class="btn-secondary"
        @click="$emit('close')"
        :disabled="uploading"
      >
        取消
      </button>
      <button 
        type="button" 
        class="btn-primary"
        @click="handleUpload"
        :disabled="!canUpload || uploading"
      >
        <span v-if="uploading" class="loading-spinner"></span>
        {{ uploading ? '上传中...' : '开始上传' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useTestCaseConfig, createDefaultUploadConfig } from '../../../composables/useTestCaseConfig'
import { parseAudioTxtFile, parseAnnotationFormat, determineAnnotationType } from '../../../utils/audioUtils'
import { algorithmApi } from '../../../utils/api'
import UploadOptions from '../../common/UploadOptions.vue'

const props = defineProps({
  modalId: { type: String, default: '' },
  title: { type: String, default: '上传文件' },
  acceptedTypes: { type: Array, default: () => ['audio/*', 'video/*', '.txt', '.json', '.rttm', '.stm'] },
  maxSize: { type: Number, default: 100 * 1024 * 1024 },
  multiple: { type: Boolean, default: false },
  uploadOptions: { type: Array, default: () => [] },
  showTagsInput: { type: Boolean, default: true },
  autoUpload: { type: Boolean, default: false },
  supportedFormats: { type: Array, default: () => ['mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg'] },
  deviceOptions: { type: Array, default: () => [] },
  algorithmOptions: { type: Array, default: () => [] }
})

const emit = defineEmits(['close', 'confirm', 'selectFolder'])

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
                const type = ann.type || determineAnnotationType(ann.name || ann.code || 'asr')
                annotations.push({
                    format: annData.format,
                    name: code,
                    code: code,
                    type: type,
                    data: { segments: ann.segments, ...(ann.extra_fields || {}) },
                    source_language: ann.source_language || '',
                    target_language: ann.target_language || ''
                })
            }
        } else if (annData && annData.segments && annData.segments.length > 0) {
            const annotationCodeVal = uploadConfig.value.algorithmType || determineAnnotationName(audioFileName, annData.format)
            const type = annData.type || determineAnnotationType(annData.name || annData.code || 'asr')
            annotations.push({
                format: annData.format,
                name: annotationCodeVal,
                code: annotationCodeVal,
                type: type,
                data: { segments: annData.segments, ...(annData.extra_fields || {}) },
                source_language: annData.source_language || '',
                target_language: annData.target_language || ''
            })
        } else if (markerText) {
            annotations.push({
                format: 'text',
                name: 'asr',
                code: 'asr',
                type: 'asr',
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
</script>

<style scoped>
.upload-file-modal {
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

.dimension-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
}

.dimension-summary {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
}

.dimension-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  max-height: 200px;
  overflow: auto;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #ffffff;
  pointer-events: auto;
}

.upload-file-modal .upload-options .dimension-cloud button.dimension-chip {
  border: 1px solid #dbe2ea;
  background: #f3f6fa;
  color: #334155;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.15s ease;
  user-select: none;
  pointer-events: auto;
  min-height: 0;
  height: 30px;
  line-height: 1;
  box-shadow: none;
}

.upload-file-modal .upload-options .dimension-cloud button.dimension-chip:hover {
  background: #eaf2ff;
}

.upload-file-modal .upload-options .dimension-cloud button.dimension-chip.dimension-chip-selected {
  border-color: #1677ff;
  background: #1677ff;
  color: #ffffff;
}

.dimension-empty,
.dimension-loading {
  width: 100%;
  padding: 10px 6px;
  color: #64748b;
  font-size: 12px;
}

/* 拖放区域 */
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

.drop-zone.has-file {
  padding: 30px 20px;
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

.drop-zone-content h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #334155;
}

.drop-zone-hint {
  margin: 0;
  font-size: 14px;
  color: #64748b;
  line-height: 1.5;
}

.browse-btn {
  display: inline-block;
  padding: 10px 20px;
  background-color: #3b82f6;
  color: white;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-top: 8px;
}

.browse-btn:hover {
  background-color: #2563eb;
}

.browse-btn input[type="file"] {
  display: none;
}

/* 文件信息 */
.file-info {
  display: flex;
  align-items: center;
  gap: 12px;
  background-color: white;
  padding: 16px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  width: 100%;
  max-width: 500px;
}

.file-info i {
  font-size: 32px;
  color: #3b82f6;
  margin-right: 12px;
}

.file-details {
  flex: 1;
  text-align: left;
}

.file-name {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: #334155;
  word-break: break-all;
}

.file-size {
  font-size: 12px;
  color: #9ca3af;
}

.btn-remove {
  background: none;
  border: none;
  color: #9ca3af;
  cursor: pointer;
  padding: 8px;
  border-radius: 4px;
  transition: all 0.2s;
}

.btn-remove:hover {
  color: #ef4444;
  background-color: #fee2e2;
}

/* 文件统计信息 */
.file-stats {
  background-color: #f0f9ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  padding: 16px;
  margin: 16px 0;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-label {
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #3b82f6;
}

/* 文件列表 */
.file-list {
  background-color: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  margin: 16px 0;
}

.file-list h4 {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.files-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 12px;
  background-color: white;
  padding: 12px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  transition: all 0.2s ease;
}

.file-item:hover {
  border-color: #3b82f6;
  background-color: #f8fafc;
}

.txt-file-icon {
  font-size: 24px;
  color: #f59e0b;
  flex-shrink: 0;
}

.audio-file-icon {
  font-size: 24px;
  color: #3b82f6;
  flex-shrink: 0;
}

.file-item .file-details {
  flex: 1;
  min-width: 0;
}

.file-item .file-name {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: #334155;
  word-break: break-all;
  margin-bottom: 4px;
}

.file-item .file-size {
  font-size: 12px;
  color: #9ca3af;
  display: block;
}

/* 文件关联信息 */
.file-meta {
  margin-top: 8px;
  padding: 8px;
  background-color: #f1f5f9;
  border-radius: 4px;
}

.meta-tag {
  display: inline-block;
  padding: 4px 8px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 12px;
  margin-bottom: 8px;
}

.meta-tag.has-txt {
  background-color: #dcfce7;
  color: #166534;
}

.meta-tag.no-txt {
  background-color: #fef2f2;
  color: #991b1b;
}

.meta-content {
  margin-bottom: 8px;
}

.meta-content:last-child {
  margin-bottom: 0;
}

.meta-label {
  font-size: 12px;
  font-weight: 500;
  color: #64748b;
  margin-bottom: 4px;
  display: block;
}

.meta-value {
  font-size: 13px;
  color: #334155;
  word-break: break-all;
  white-space: pre-wrap;
}

/* 翻译列表 */
.translations-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.translation-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
}

.translation-item .direction {
  font-weight: 600;
  color: #3b82f6;
  min-width: 60px;
  flex-shrink: 0;
}

.translation-item .text {
  color: #334155;
  flex: 1;
  word-break: break-all;
}

/* 上传选项 */
.upload-options {
  background-color: #f8fafc;
  padding: 16px;
  border-radius: 8px;
}

.upload-options h4 {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.options-grid {
  display: grid;
  gap: 12px;
}

.option-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-item input[type="checkbox"],
.option-item input[type="radio"] {
  margin: 0;
}

.option-item label {
  font-size: 14px;
  color: #334155;
  margin: 0;
}

.option-hint {
  margin: 4px 0 0 0 !important;
  font-size: 12px;
  color: #94a3b8;
}

.radio-group {
  display: flex;
  gap: 16px;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.radio-label input[type="radio"] {
  margin: 0;
}

.radio-label .radio-text {
  font-size: 14px;
  color: #334155;
}

.checkbox-group {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  margin: 0;
  position: static;
  opacity: 1;
  height: auto;
  width: auto;
}

.checkbox-label .checkbox-text {
  font-size: 14px;
  color: #334155;
  position: static;
  display: inline;
}

.checkbox-label .checkbox-text::before,
.checkbox-label .checkbox-text::after {
  content: none;
}

.form-input {
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  color: #334155;
  transition: border-color 0.2s ease;
}

.form-input:focus {
  outline: none;
  border-color: #3b82f6;
}

.custom-select-wrapper {
  position: relative;
  width: 100%;
}

.custom-select {
  width: 100%;
  padding-right: 60px;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2364748b' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  padding-right: 36px;
}

.custom-select.select-with-loading {
  padding-right: 80px;
}

.select-loading-indicator {
  position: absolute;
  right: 40px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 12px;
  color: #3b82f6;
  pointer-events: none;
}

.loading-dots::after {
  content: '';
  animation: dots 1.5s steps(4, end) infinite;
}

@keyframes dots {
  0%, 20% { content: ''; }
  40% { content: '.'; }
  60% { content: '..'; }
  80%, 100% { content: '...'; }
}

/* 按钮区域 */
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e2e8f0;
}

.btn-primary {
  padding: 10px 20px;
  background-color: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.btn-primary:hover:not(:disabled) {
  background-color: #2563eb;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 10px 20px;
  background-color: white;
  color: #374151;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.btn-secondary:hover:not(:disabled) {
  background-color: #f3f4f6;
}

.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 加载状态 */
.loading-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  border-top-color: white;
  animation: spin 0.8s linear infinite;
  margin-right: 8px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 测试类型配置区域 */
.test-type-config {
  margin-top: 16px;
  padding: 16px;
  background-color: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.test-type-config.api-config {
  background-color: #f0f9ff;
  border-color: #bae6fd;
}

.test-type-config.e2e-config {
  background-color: #fdf4ff;
  border-color: #fbcfe8;
}

.config-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.api-config .config-header {
  color: #0369a1;
}

.e2e-config .config-header {
  color: #be185d;
}

.config-header i {
  font-size: 16px;
}

.option-item.full-width {
  grid-column: 1 / -1;
}

.dimension-summary.has-error {
  color: #ef4444;
  font-weight: 500;
}

.form-input.has-error {
  border-color: #ef4444;
}

.option-hint.error {
  color: #ef4444;
}

.required {
  color: #ef4444;
}
</style>
