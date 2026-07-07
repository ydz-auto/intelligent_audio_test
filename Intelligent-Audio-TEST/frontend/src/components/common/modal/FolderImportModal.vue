<template>
  <div class="upload-file-modal">
    <h3>{{ title || '批量从文件夹导入' }}</h3>
    
    <div class="upload-content">
      <!-- 拖放区域 -->
      <div 
        class="drop-zone"
        :class="{ 'drop-zone-active': isDragActive }"
        @dragover.prevent="handleDragOver"
        @dragleave.prevent="handleDragLeave"
        @drop.prevent="handleDrop"
      >
        <div class="drop-zone-content">
          <i class="fas fa-folder-open"></i>
          <h4>{{ dragMessage }}</h4>
          <p class="drop-zone-hint">
            支持格式：{{ supportedFormats.join(', ') }}<br>
            选择包含音频文件的文件夹进行批量导入
          </p>
          <label class="browse-btn">
            <input 
              type="file" 
              ref="folderInput"
              webkitdirectory
              multiple
              @change="handleFolderSelect"
              :disabled="importing"
              accept=".mp3,.wav,.flac,.aac,.m4a,.ogg,.txt,.json,.jsonl,.rttm,.stm"
            >
            选择文件夹
          </label>
        </div>
      </div>
      
      <!-- 文件统计信息 -->
      <div class="file-stats" v-if="selectedFiles.length > 0">
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-label">音频文件数量</span>
            <span class="stat-value">{{ audioFilesCount }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">总大小</span>
            <span class="stat-value">{{ formatFileSize(totalFileSize) }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">文件夹数量</span>
            <span class="stat-value">{{ selectedFolders.length }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">支持的文件格式</span>
            <span class="stat-value">{{ supportedFormats.join(', ') }}</span>
          </div>
        </div>
      </div>
      
      <!-- 文件夹分组设置 -->
      <div class="folder-groups" v-if="selectedFolders.length > 0 && uploadConfig.createTestCase && uploadConfig.groupNameType === 'custom'">
        <h4>文件夹分组设置</h4>
        <div class="folder-group-list">
          <div class="folder-group-item" v-for="folder in selectedFolders" :key="folder">
            <div class="folder-name">{{ folder }}</div>
            <div class="folder-group-input">
              <input 
                type="text" 
                class="form-input" 
                :placeholder="`为文件夹 '${folder}' 设置自定义分组名`"
                :value="folderGroupNames.get(folder)"
                @input="handleFolderGroupInput(folder, $event)"
              >
            </div>
          </div>
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
        :show-tags-input="true"
      />

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
    </div>
    
    <!-- 按钮区域 -->
    <div class="modal-footer">
      <button 
        type="button" 
        class="btn-secondary"
        @click="handleCancel"
        :disabled="false"
      >
        取消
      </button>
      <button 
        type="button" 
        class="btn-primary"
        @click="handleImport"
        :disabled="!canImport || importing"
      >
        <span v-if="importing" class="loading-spinner"></span>
        {{ importing ? '导入中...' : '开始上传' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, reactive, onMounted, onUnmounted } from 'vue'
import { parseAudioTxtFile, parseAnnotationFormat, determineAnnotationType } from '../../../utils/audioUtils'
import { evaluationApi, devicesApi, algorithmApi } from '../../../utils/api'
import type { PropType } from 'vue'
import { useTestCaseConfig, createDefaultUploadConfig } from '../../../composables/useTestCaseConfig'
import { useAlgorithmConfig } from '../../../composables/useAlgorithmConfig'
import UploadOptions from '../../common/UploadOptions.vue'

const algorithmConfig = useAlgorithmConfig()
const getAlgorithmOptions = () => algorithmConfig.getAlgorithmOptions()
const getFormSchema = (type: string) => algorithmConfig.getFormSchema(type)

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

const props = defineProps<{
  modalId?: string
  title?: string
  uploadOptions?: UploadOption[]
  supportedFormats?: string[]
  deviceOptions?: any[]
  algorithmOptions?: any[]
  playbackDeviceOptions?: any[]
  audioTypeOptions?: any[]
}>()

const emit = defineEmits([
  'close',
  'confirm',
  'cancel',
  'configChange',
  'selectFolder'
])

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

    for (const annFile of annotationFiles) {
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
        
        if (parsedData.annotations && parsedData.annotations.length > 0) {
          const annotationsList = parsedData.annotations.map(ann => ({
            format: format,
            name: ann.name || ann.code || 'asr',
            code: ann.code || ann.name || 'asr',
            type: ann.type || determineAnnotationType(ann.name || ann.code || 'asr'),
            data: { segments: ann.segments, ...(ann.extra_fields || {}) },
            source_language: ann.source_language || '',
            target_language: ann.target_language || ''
          }))
          annotationDataMap.set(baseKey, annotationsList)
        } else if (parsedData.segments && parsedData.segments.length > 0) {
          const annotationCode = parsedData.code || parsedData.name || determineAnnotationName(annFile.name, format)
          const type = parsedData.type || determineAnnotationType(parsedData.name || parsedData.code || 'asr')
          annotationDataMap.set(baseKey, [{
            format: format,
            name: annotationCode,
            code: annotationCode,
            type: type,
            data: { segments: parsedData.segments, ...(parsedData.extra_fields || {}) },
            source_language: parsedData.source_language || '',
            target_language: parsedData.target_language || ''
          }])
        }
      } catch (e) {
        console.error(`解析标注文件 ${annFile.name} 失败:`, e)
      }
    }

    const filesWithMetadata: FileWithMetadata[] = audioFiles.map(file => {
      const key = (file as any).webkitRelativePath || file.name
      const baseKey = key.substring(0, key.lastIndexOf('.'))
      const metadata = txtDataMap.get(baseKey) || { asrText: '', translations: [] as Array<{ text: string; direction: string }> }
      const annData = annotationDataMap.get(baseKey)
      
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
  padding: 8px 12px;
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

/* 上传进度 */
.upload-progress {
  background-color: #f8fafc;
  padding: 16px;
  border-radius: 8px;
}

.progress-bar-container {
  width: 100%;
  height: 8px;
  background-color: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 8px;
}

.progress-bar {
  height: 100%;
  background-color: #3b82f6;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-text {
  margin: 0;
  font-size: 14px;
  color: #64748b;
  text-align: center;
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

/* 文件夹分组设置样式 */
.folder-groups {
  background-color: #f8fafc;
  padding: 16px;
  border-radius: 8px;
  margin: 16px 0;
}

.folder-groups h4 {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.folder-group-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.folder-group-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background-color: white;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
}

.folder-name {
  min-width: 150px;
  font-weight: 500;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.folder-group-input {
  flex: 1;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .drop-zone {
    padding: 30px 16px;
  }
  
  .drop-zone-content i {
    font-size: 32px;
  }
  
  .folder-group-item {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
  
  .folder-name {
    min-width: auto;
  }
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
