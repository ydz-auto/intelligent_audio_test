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
import { useDetailViewModal } from './DetailViewModal'

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

const emit = defineEmits(['close', 'save', 'action', 'confirm'])

const {
  isDetailDataFormat,
  detailData,
  tableConfig,
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
  hasAnnotations,
  hasTableData,
  getFieldValue,
  getTableCellValue
} = useDetailViewModal(props, emit)
</script>

<style scoped>
@import './DetailViewModal.css';
</style>
