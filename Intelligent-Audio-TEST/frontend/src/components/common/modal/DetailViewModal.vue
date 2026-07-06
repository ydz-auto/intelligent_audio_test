<template>
  <div class="detail-view-modal">
    <div v-if="!data || (Object.keys(data).length === 0 && !isDetailDataFormat)" class="loading-state">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>
    
    <div v-else class="detail-content">
      <!-- 标题区域 -->
      <div class="detail-header" v-if="title">
        <h3>{{ title }}</h3>
      </div>
      
      <!-- 基础信息卡片 -->
      <div class="info-card" v-if="hasBasicInfo">
        <h4>基本信息</h4>
        <div class="info-grid">
          <!-- 处理detailData格式 -->
          <template v-if="isDetailDataFormat">
            <div 
              v-for="(item, index) in props.detail_data.metadata" 
              :key="index" 
              class="info-item"
            >
              <span class="info-label">{{ item.label }}:</span>
              
              <!-- 音频类型可编辑 -->
              <select v-if="item.key === 'audioType'" v-model="editableData[item.key]" class="form-input info-value">
                <option value="dry">干声 (信号音频)</option>
                <option value="noise">噪声</option>
                <option value="prompt">提示词音频</option>
              </select>
              
              <!-- 其他字段可编辑 -->
              <input v-else type="text" v-model="editableData[item.key]" class="form-input info-value" :class="item.class_name">
            </div>
          </template>
          
          <!-- 处理传统格式 -->
          <template v-else>
            <div 
              v-for="(field, key) in basicInfoFields" 
              :key="key" 
              class="info-item"
            >
              <span class="info-label">{{ field.label }}:</span>
              
              <!-- 音频类型可编辑 -->
              <select v-if="key === 'audioType'" v-model="editableData[key]" class="form-input info-value">
                <option value="dry">干声 (信号音频)</option>
                <option value="noise">噪声</option>
                <option value="prompt">提示词音频</option>
              </select>
              
              <!-- 其他字段可编辑 -->
              <input v-else type="text" v-model="editableData[key]" class="form-input info-value" :class="field.class_name">
            </div>
          </template>
        </div>
      </div>
      
      <!-- 标注编辑卡片（统一管理所有标注） -->
      <div class="annotation-card" v-if="hasAnnotations">
        <h4>标注管理</h4>
        
        <!-- 标注列表和编辑区 -->
        <div class="annotation-editor">
          <!-- 左侧：标注列表 -->
          <div class="annotation-list-panel">
            <div class="annotation-list-header">
              <span>标注列表</span>
              <button type="button" class="btn btn-primary btn-small" @click="addAnnotationItem">
                + 添加标注
              </button>
            </div>
            <div class="annotation-list">
              <div 
                v-for="(ann, aIndex) in editableData.annotations" 
                :key="aIndex"
                class="annotation-item"
                :class="{ active: selectedAnnotationIndex === aIndex }"
                @click="selectAnnotation(aIndex)"
              >
                <div class="annotation-item-header">
                  <span class="annotation-format-badge" :class="'format-' + ann.format">{{ ann.format.toUpperCase() }}</span>
                  <span class="annotation-name">{{ ann.code || '未命名' }}</span>
                </div>
                <div class="annotation-item-meta">
                  {{ ann.source_language || '-' }} → {{ ann.target_language || '-' }}
                </div>
                <button type="button" class="btn btn-danger btn-tiny" @click.stop="removeAnnotationItem(aIndex)">删除</button>
              </div>
              <div v-if="!editableData.annotations || editableData.annotations.length === 0" class="annotation-empty">
                暂无标注，点击上方添加
              </div>
            </div>
          </div>
          
          <!-- 右侧：标注编辑区 -->
          <div class="annotation-edit-panel" v-if="selectedAnnotationIndex !== null && editableData.annotations[selectedAnnotationIndex]">
            <div class="annotation-edit-header">
              <span>编辑标注</span>
              <div class="annotation-edit-tabs">
                <button 
                  type="button" 
                  class="tab-btn" 
                  :class="{ active: annotationEditMode === 'visual' }"
                  @click="annotationEditMode = 'visual'"
                >
                  可视化编辑
                </button>
                <button 
                  type="button" 
                  class="tab-btn" 
                  :class="{ active: annotationEditMode === 'raw' }"
                  @click="annotationEditMode = 'raw'"
                >
                  原始编辑
                </button>
              </div>
            </div>
            
            <!-- 标注基本信息 -->
            <div class="annotation-basic-info">
                            <div class="form-row annotation-name-row">
                <label>标注代码：</label>
                <select v-model="editableData.annotations[selectedAnnotationIndex].code" class="form-input">
                  <option value="">自定义...</option>
                  <option value="diarization">diarization</option>
                  <option value="asr">asr</option>
                  <option value="translation">translation</option>
                </select>
                <input 
                  v-if="!['asr', 'translation', 'diarization'].includes(editableData.annotations[selectedAnnotationIndex].code)"
                  type="text" 
                  v-model="editableData.annotations[selectedAnnotationIndex].code" 
                  class="form-input" 
                  placeholder="自定义名称"
                >
              </div>
              <div class="form-row">
                <label>格式：</label>
                <select v-model="editableData.annotations[selectedAnnotationIndex].format" class="form-input">
                  <option value="text">TEXT (纯文本)</option>
                  <option value="json">JSON (带时间戳)</option>
                  <option value="rttm">RTTM</option>
                  <option value="stm">STM</option>
                </select>
              </div>

              <div class="form-row-inline">
                <div class="form-row">
                  <label>源语言：</label>
                  <input type="text" v-model="editableData.annotations[selectedAnnotationIndex].source_language" class="form-input" placeholder="zh">
                </div>
                <div class="form-row">
                  <label>目标语言：</label>
                  <input type="text" v-model="editableData.annotations[selectedAnnotationIndex].target_language" class="form-input" placeholder="en">
                </div>
              </div>
            </div>
            
            <!-- 可视化编辑模式 -->
            <div v-if="annotationEditMode === 'visual'" class="annotation-visual-editor">
              <!-- TEXT格式：纯文本编辑 -->
              <div v-if="editableData.annotations[selectedAnnotationIndex].format === 'text'" class="text-editor">
                <div class="text-editor-header">
                  <span>文本内容</span>
                </div>
                <textarea 
                  v-model="editableData.annotations[selectedAnnotationIndex].data.text" 
                  class="raw-textarea" 
                  placeholder="请输入纯文本内容"
                ></textarea>
              </div>
              
              <!-- JSON格式：片段表格编辑 -->
              <div v-else-if="editableData.annotations[selectedAnnotationIndex].format === 'json'" class="segments-editor">
                <div class="segments-header">
                  <span>片段列表</span>
                  <div class="segments-header-actions">
                    <button type="button" class="btn btn-secondary btn-small" @click="addSegmentField">+ 添加字段</button>
                    <button type="button" class="btn btn-primary btn-small" @click="addSegment">+ 添加片段</button>
                  </div>
                </div>
                <div class="segments-list">
                  <table class="segments-table">
                    <thead>
                      <tr>
                        <th>Speaker</th>
                        <th>开始时间(s)</th>
                        <th>结束时间(s)</th>
                        <th>文本内容</th>
                        <th v-for="field in extraSegmentFields" :key="field">{{ field }}</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(seg, sIndex) in getCurrentSegments()" :key="sIndex">
                        <td>
                          <input type="text" v-model="seg.speaker" class="form-input input-tiny" placeholder="spk0">
                        </td>
                        <td>
                          <input type="number" step="0.01" v-model="seg.start" class="form-input input-tiny" placeholder="0.00">
                        </td>
                        <td>
                          <input type="number" step="0.01" v-model="seg.end" class="form-input input-tiny" placeholder="0.00">
                        </td>
                        <td>
                          <input type="text" v-model="seg.text" class="form-input" placeholder="文本内容">
                        </td>
                        <td v-for="field in extraSegmentFields" :key="field">
                          <input type="text" v-model="seg[field]" class="form-input input-tiny" :placeholder="field">
                        </td>
                        <td>
                          <button type="button" class="btn btn-danger btn-tiny" @click="removeSegment(sIndex)">删除</button>
                        </td>
                      </tr>
                      <tr v-if="getCurrentSegments().length === 0">
                        <td :colspan="5 + extraSegmentFields.length" class="empty-row">
                          暂无片段，点击添加片段
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <!-- data 顶层额外字段编辑 -->
                <div v-if="extraDataFields.length > 0" class="extra-data-fields">
                  <div class="extra-data-header">
                    <span>额外数据字段</span>
                  </div>
                  <div class="extra-data-list">
                    <div v-for="fieldName in extraDataFields" :key="fieldName" class="extra-data-item">
                      <label class="extra-data-label">{{ fieldName }}:</label>
                      <input
                        type="text"
                        v-model="editableData.annotations[selectedAnnotationIndex].data[fieldName]"
                        class="form-input extra-data-input"
                        :placeholder="fieldName"
                      >
                      <button type="button" class="btn btn-danger btn-tiny" @click="removeDataField(fieldName)">删除</button>
                    </div>
                  </div>
                </div>

                <!-- 添加 data 字段按钮 -->
                <div class="extra-data-actions">
                  <button type="button" class="btn btn-secondary btn-small" @click="addDataField">+ 添加数据字段</button>
                </div>
              </div>
              
              <!-- RTTM格式：类似JSON但无text字段 -->
              <div v-else-if="editableData.annotations[selectedAnnotationIndex].format === 'rttm'" class="segments-editor">
                <div class="segments-header">
                  <span>RTTM片段列表</span>
                  <button type="button" class="btn btn-primary btn-small" @click="addRTTMSegment">+ 添加片段</button>
                </div>
                <div class="segments-list">
                  <table class="segments-table">
                    <thead>
                      <tr>
                        <th>Speaker</th>
                        <th>开始时间(s)</th>
                        <th>持续时间(s)</th>
                        <th>正交字</th>
                        <th>说话类型</th>
                        <th> speaker类型</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(seg, sIndex) in getRTTMSegments()" :key="sIndex">
                        <td>
                          <input type="text" v-model="seg.speaker" class="form-input input-tiny" placeholder="spk0">
                        </td>
                        <td>
                          <input type="number" step="0.01" v-model="seg.start" class="form-input input-tiny" placeholder="0.00">
                        </td>
                        <td>
                          <input type="number" step="0.01" v-model="seg.duration" class="form-input input-tiny" placeholder="1.00">
                        </td>
                        <td>
                          <input type="text" v-model="seg.orthography" class="form-input input-tiny" placeholder="<NA>">
                        </td>
                        <td>
                          <input type="text" v-model="seg.speaker_type" class="form-input input-tiny" placeholder="<NA>">
                        </td>
                        <td>
                          <input type="text" v-model="seg.speaker_name" class="form-input input-tiny" placeholder="<NA>">
                        </td>
                        <td>
                          <button type="button" class="btn btn-danger btn-tiny" @click="removeRTTMSegment(sIndex)">删除</button>
                        </td>
                      </tr>
                      <tr v-if="getRTTMSegments().length === 0">
                        <td colspan="7" class="empty-row">
                          暂无片段，点击添加片段
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              
              <!-- STM格式：类似JSON -->
              <div v-else-if="editableData.annotations[selectedAnnotationIndex].format === 'stm'" class="segments-editor">
                <div class="segments-header">
                  <span>STM片段列表</span>
                  <button type="button" class="btn btn-primary btn-small" @click="addSTMSegment">+ 添加片段</button>
                </div>
                <div class="segments-list">
                  <table class="segments-table">
                    <thead>
                      <tr>
                        <th>文件名</th>
                        <th>Channel</th>
                        <th>Speaker</th>
                        <th>开始时间(s)</th>
                        <th>结束时间(s)</th>
                        <th>文本内容</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(seg, sIndex) in getSTMSegments()" :key="sIndex">
                        <td>
                          <input type="text" v-model="seg.file" class="form-input input-tiny" placeholder="filename">
                        </td>
                        <td>
                          <input type="text" v-model="seg.channel" class="form-input input-tiny" placeholder="1">
                        </td>
                        <td>
                          <input type="text" v-model="seg.speaker" class="form-input input-tiny" placeholder="spk0">
                        </td>
                        <td>
                          <input type="number" step="0.01" v-model="seg.start" class="form-input input-tiny" placeholder="0.00">
                        </td>
                        <td>
                          <input type="number" step="0.01" v-model="seg.end" class="form-input input-tiny" placeholder="1.00">
                        </td>
                        <td>
                          <input type="text" v-model="seg.text" class="form-input" placeholder="文本内容">
                        </td>
                        <td>
                          <button type="button" class="btn btn-danger btn-tiny" @click="removeSTMSegment(sIndex)">删除</button>
                        </td>
                      </tr>
                      <tr v-if="getSTMSegments().length === 0">
                        <td colspan="7" class="empty-row">
                          暂无片段，点击添加片段
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            
            <!-- 原始编辑模式 -->
            <div v-else class="annotation-raw-editor">
              <textarea 
                v-model="rawAnnotationData" 
                class="raw-textarea" 
                placeholder='{"segments": [{"speaker": "spk0", "start": 0, "end": 1.5, "text": "Hello"}]}'
                @blur="updateAnnotationDataFromRaw"
              ></textarea>
            </div>
          </div>
          <div v-else class="annotation-edit-panel-empty">
            请在左侧选择要编辑的标注
          </div>
        </div>
      </div>
      
      <!-- 日志内容区域 (仅用于detailData格式) -->
      <div class="content-card" v-if="isDetailDataFormat && detailData.content">
        <h4>日志内容</h4>
        <div class="log-content">
          {{ detailData.content }}
        </div>
      </div>
      
      <!-- 上下文信息区域 (仅用于detailData格式) -->
      <div class="context-card" v-if="isDetailDataFormat && detailData.context">
        <h4>上下文信息</h4>
        <pre class="log-context">{{ JSON.stringify(detailData.context, null, 2) }}</pre>
      </div>
      
      <!-- 自定义内容区域 -->
      <div class="custom-content" v-if="$slots.default">
        <slot></slot>
      </div>
      
      <!-- 数据表格区域 -->
      <div class="data-table-section" v-if="hasTableData">
        <h4>{{ tableConfig.title || '数据列表' }}</h4>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th v-for="column in tableConfig.columns" :key="column.key">
                  {{ column.title }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in tableConfig.data" :key="index">
                <td v-for="column in tableConfig.columns" :key="column.key">
                  {{ getTableCellValue(row, column) }}
                </td>
              </tr>
              <tr v-if="tableConfig.data.length === 0">
                <td :colspan="tableConfig.columns.length" class="empty-row">
                  暂无数据
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      
      <!-- 按钮区域 -->
      <div class="modal-footer">
        <button type="button" class="btn-secondary" @click="$emit('close')">
          取消
        </button>
        <button type="button" class="btn-primary" @click="handleSave">
          保存
        </button>
        <button 
          v-if="$slots.actions" 
          type="button" 
          class="btn-secondary"
          @click="$emit('action')"
        >
          <slot name="actions"></slot>
        </button>
      </div>
    </div></div>
</template>

<script setup>
import { computed, ref, watch, onMounted } from 'vue'

// 已知的 segment 字段（这些字段有专门列，不作为额外字段显示）
const KNOWN_SEGMENT_FIELDS = ['speaker', 'start', 'end', 'text', 'duration', 'orthography', 'speaker_type', 'speaker_name', 'file', 'channel']

// 已知的 data 顶层字段（这些字段有专门 UI，不作为额外字段显示）
const KNOWN_DATA_KEYS = ['segments', 'text', 'annotations', 'timestamps', 'timestamps_global']

const props = defineProps({
  modal_id: {
    type: String,
    default: ''
  },
  data: {
    type: Object,
    default: () => ({})
  },
  title: {
    type: String,
    default: ''
  },
  fields: {
    type: Array,
    default: () => []
  },
  table_config: {
    type: Object,
    default: () => ({
      columns: [],
      data: []
    })
  },
  // 支持从LogView传递的detailData格式
  detail_data: {
    type: Object,
    default: null
  }
})

// 调试：记录props变化
console.log('[DetailViewModal] props.data:', props.data)
console.log('[DetailViewModal] props.detail_data:', props.detail_data)
console.log('[DetailViewModal] props.title:', props.title)

const emit = defineEmits(['close', 'save', 'action', 'confirm'])

// 计算属性：是否为detailData格式
const isDetailDataFormat = computed(() => {
  return props.detail_data !== null
})

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
</script>

<style scoped>
.detail-view-modal {
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  gap: 16px;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f4f6;
  border-top: 4px solid #3b82f6;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.detail-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-header {
  padding-bottom: 12px;
  border-bottom: 1px solid #e2e8f0;
}

.detail-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #334155;
}

.info-card {
  background-color: #f8fafc;
  padding: 20px;
  border-radius: 8px;
}

.info-card h4 {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 12px;
  font-weight: 500;
  color: #64748b;
}

.info-value {
  font-size: 14px;
  color: #334155;
  word-break: break-word;
}

.custom-content {
  padding: 16px 0;
}

.data-table-section {
  background-color: #f8fafc;
  padding: 20px;
  border-radius: 8px;
}

.data-table-section h4 {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.table-container {
  overflow-x: auto;
  background-color: white;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th, td {
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid #e2e8f0;
  font-size: 14px;
}

th {
  background-color: #f1f5f9;
  font-weight: 600;
  color: #334155;
  white-space: nowrap;
}

td {
  color: #475569;
}

.empty-row {
  text-align: center;
  padding: 24px;
  color: #94a3b8;
  font-style: italic;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e2e8f0;
}

.content-card,
.context-card {
  background-color: #f8fafc;
  padding: 20px;
  border-radius: 8px;
}

.content-card h4,
.context-card h4 {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.log-content {
  background-color: white;
  padding: 16px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  font-size: 14px;
  line-height: 1.6;
  color: #475569;
  white-space: pre-wrap;
  word-break: break-word;
}

.log-context {
  background-color: white;
  padding: 16px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  font-size: 13px;
  line-height: 1.5;
  color: #475569;
  overflow-x: auto;
  margin: 0;
}

/* 支持日志级别样式 */
.log-level {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
}

.log-level.error {
  background-color: #fee2e2;
  color: #dc2626;
}

.log-level.warning {
  background-color: #fef3c7;
  color: #d97706;
}

.log-level.info {
  background-color: #dbeafe;
  color: #2563eb;
}

.log-level.debug {
  background-color: #e0e7ff;
  color: #6366f1;
}

/* 翻译表格样式 */
.translations-container {
  width: 100%;
  overflow-x: auto;
}

.translations-table {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  background-color: white;
  border-radius: 6px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  font-size: 13px;
}

.translations-table th,
.translations-table td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid #e2e8f0;
  white-space: nowrap;
}

.translations-table th {
  background-color: #f1f5f9;
  font-weight: 600;
  color: #334155;
  font-size: 12px;
  text-transform: uppercase;
}

.translations-table td {
  color: #475569;
}

.translations-table .translation-direction {
  font-weight: 500;
  color: #334155;
  min-width: 100px;
}

.translations-table .translation-text {
  white-space: normal;
  word-break: break-word;
  max-width: 300px;
}

/* 确保模态框内容可以滚动 */
.detail-view-modal {
  padding: 20px;
}

/* 翻译输入框样式 */
.translation-input {
  width: 100%;
  padding: 6px 8px;
  font-size: 13px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  box-sizing: border-box;
  transition: border-color 0.2s ease;
}

.translation-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

/* 翻译操作按钮样式 */
.translation-actions {
  margin: 8px 0;
  display: flex;
  gap: 8px;
  align-items: center;
}

.translation-actions .btn-primary {
  background-color: #3b82f6;
  color: white;
}

.translation-actions .btn-primary:hover {
  background-color: #2563eb;
}

.translation-actions .btn-danger {
  background-color: #ef4444;
  color: white;
}

.translation-actions .btn-danger:hover {
  background-color: #dc2626;
}

/* 确保翻译表格中的操作列宽度合适 */
.translations-table th:last-child,
.translations-table td:last-child {
  width: 80px;
  white-space: nowrap;
  text-align: center;
}

/* 标注表格样式 */
.annotations-container {
  width: 100%;
  overflow-x: auto;
}

.annotations-table {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  background-color: white;
  border-radius: 6px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  font-size: 13px;
}

.annotations-table th,
.annotations-table td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid #e2e8f0;
  white-space: nowrap;
}

.annotations-table th {
  background-color: #f1f5f9;
  font-weight: 600;
  color: #334155;
  font-size: 12px;
  text-transform: uppercase;
}

.annotations-table td {
  color: #475569;
}

.annotation-input {
  width: 100%;
  padding: 6px 8px;
  font-size: 13px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  box-sizing: border-box;
  transition: border-color 0.2s ease;
}

.annotation-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.annotation-actions {
  margin: 8px 0;
  display: flex;
  gap: 8px;
  align-items: center;
}

.annotation-actions .btn-primary {
  background-color: #3b82f6;
  color: white;
}

.annotation-actions .btn-primary:hover {
  background-color: #2563eb;
}

.annotation-actions .btn-danger {
  background-color: #ef4444;
  color: white;
}

.annotation-actions .btn-danger:hover {
  background-color: #dc2626;
}

.btn-small {
  padding: 4px 8px;
  font-size: 12px;
}

/* 确保标注表格中的操作列宽度合适 */
.annotations-table th:last-child,
.annotations-table td:last-child {
  width: 80px;
  white-space: nowrap;
  text-align: center;
}

/* 调整信息网格中annotations项目的样式 */
.info-item {
  align-items: flex-start;
}

.info-item .info-label {
  margin-bottom: 8px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .info-grid {
    grid-template-columns: 1fr;
  }
  
  th, td {
    padding: 8px 12px;
    font-size: 13px;
  }
  
  .log-content,
  .log-context {
    padding: 12px;
    font-size: 13px;
  }
  
  .translations-table .translation-text {
    max-width: 200px;
  }
}

/* 标注编辑卡片样式 */
.annotation-card {
  background-color: #f8fafc;
  padding: 20px;
  border-radius: 8px;
}
  .annotation-card h4 {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
}

/* ASR信息区域样式 */
.asr-info-section {
  background-color: white;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  margin-bottom: 16px;
}

.asr-info-header {
  padding: 12px;
  border-bottom: 1px solid #e2e8f0;
  font-weight: 600;
  color: #334155;
}

.asr-info-content {
  padding: 12px;
}

.asr-info-content .form-row {
  margin-bottom: 12px;
}

.asr-info-content .form-row:last-child {
  margin-bottom: 0;
}

.asr-info-content label {
  display: block;
  font-size: 13px;
  color: #64748b;
  margin-bottom: 6px;
}

.asr-text-row {
  flex-direction: column;
}

.asr-textarea {
  width: 100%;
  min-height: 80px;
  padding: 8px 12px;
  font-size: 13px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  resize: vertical;
  font-family: inherit;
  box-sizing: border-box;
}

.asr-textarea:focus {
  outline: none;
  border-color: #3b82f6;
}

.annotation-editor {
  display: flex;
  gap: 16px;
  min-height: 400px;
}

/* 左侧标注列表面板 */
.annotation-list-panel {
  width: 280px;
  flex-shrink: 0;
  background-color: white;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
}

.annotation-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-bottom: 1px solid #e2e8f0;
  font-weight: 600;
  color: #334155;
}

.annotation-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.annotation-item {
  padding: 10px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid transparent;
  margin-bottom: 8px;
  transition: all 0.2s ease;
  position: relative;
}

.annotation-item:hover {
  background-color: #f1f5f9;
}

.annotation-item.active {
  background-color: #eff6ff;
  border-color: #3b82f6;
}

.annotation-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.annotation-format-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 3px;
  text-transform: uppercase;
}

.format-json {
  background-color: #dbeafe;
  color: #2563eb;
}

.format-rttm {
  background-color: #dcfce7;
  color: #16a34a;
}

.format-stm {
  background-color: #fef3c7;
  color: #d97706;
}

.annotation-name {
  font-weight: 500;
  color: #334155;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.annotation-item-meta {
  font-size: 12px;
  color: #64748b;
}

.annotation-item .btn-danger {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.annotation-item:hover .btn-danger {
  opacity: 1;
}

.annotation-empty {
  text-align: center;
  padding: 24px;
  color: #94a3b8;
  font-style: italic;
}

/* 右侧标注编辑面板 */
.annotation-edit-panel {
  flex: 1;
  background-color: white;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.annotation-edit-panel-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-style: italic;
  background-color: white;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.annotation-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-bottom: 1px solid #e2e8f0;
  font-weight: 600;
  color: #334155;
}

.annotation-edit-tabs {
  display: flex;
  gap: 4px;
}

.tab-btn {
  padding: 6px 12px;
  border: none;
  background-color: transparent;
  color: #64748b;
  font-size: 13px;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s ease;
}

.tab-btn:hover {
  background-color: #f1f5f9;
}

.tab-btn.active {
  background-color: #3b82f6;
  color: white;
}

/* 标注基本信息 */
.annotation-basic-info {
  padding: 12px;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.form-row-inline {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.form-row-inline .form-row {
  flex: 1;
  min-width: 120px;
}

.annotation-name-row {
  flex-wrap: nowrap;
}

.annotation-name-row .form-input {
  flex: 1;
  min-width: 100px;
}

.form-row label {
  font-size: 13px;
  color: #64748b;
  white-space: nowrap;
}

.form-row .form-input {
  flex: 1;
  min-width: 100px;
}

/* 可视化编辑 */
.annotation-visual-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.segments-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  font-weight: 600;
  color: #334155;
}

.segments-header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.extra-data-fields {
  margin-top: 12px;
  padding: 12px;
  background-color: #f8fafc;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.extra-data-header {
  font-weight: 600;
  color: #334155;
  margin-bottom: 8px;
  font-size: 13px;
}

.extra-data-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.extra-data-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.extra-data-label {
  min-width: 100px;
  font-size: 13px;
  color: #475569;
}

.extra-data-input {
  flex: 1;
}

.extra-data-actions {
  margin-top: 8px;
  padding: 0 12px 12px;
}

.segments-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 12px 12px;
}

.segments-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.segments-table th,
.segments-table td {
  padding: 8px;
  text-align: left;
  border-bottom: 1px solid #e2e8f0;
}

.segments-table th {
  background-color: #f8fafc;
  font-weight: 600;
  color: #334155;
  font-size: 12px;
}

.input-tiny {
  width: 80px;
  padding: 4px 8px;
  font-size: 13px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
}

.input-tiny:focus {
  outline: none;
  border-color: #3b82f6;
}

/* 原始编辑 */
.annotation-raw-editor {
  flex: 1;
  padding: 12px;
  display: flex;
  flex-direction: column;
}

.raw-textarea {
  flex: 1;
  width: 100%;
  min-height: 300px;
  padding: 12px;
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 13px;
  line-height: 1.5;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  resize: vertical;
  box-sizing: border-box;
}

.raw-textarea:focus {
  outline: none;
  border-color: #3b82f6;
}

/* 翻译编辑区域样式 */
.translation-section {
  margin-top: 20px;
  background-color: white;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.translation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-bottom: 1px solid #e2e8f0;
  font-weight: 600;
  color: #334155;
}

.translation-list {
  padding: 12px;
}

.translation-list .translations-table {
  margin: 0;
}

.translation-input {
  width: 100%;
  padding: 6px 8px;
  font-size: 13px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  box-sizing: border-box;
}

.translation-input:focus {
  outline: none;
  border-color: #3b82f6;
}

.btn-tiny {
  padding: 2px 6px;
  font-size: 11px;
}
</style>