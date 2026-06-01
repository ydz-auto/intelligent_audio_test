<template>
  <BasicModal
    :visible="visible"
    :title="title"
    :width="modalWidth"
    :show-footer="effectiveMode !== 'list'"
    :confirm-text="okText"
    :cancel-text="cancelText"
    @close="handleCancel"
    @cancel="handleCancel"
    @confirm="handleOk"
  >
    <div class="algorithm-config-modal">
      <div v-if="effectiveMode === 'list'" class="mode-list">
        <div class="modal-toolbar">
          <button class="btn btn-primary btn-sm" @click="handleCreate">
            <i class="fas fa-plus btn-icon"></i>新建算法
          </button>
          <div class="search-box">
            <i class="fas fa-search search-icon"></i>
            <input
              type="text"
              class="search-input"
              placeholder="搜索算法"
              v-model="searchKeyword"
              @input="handleSearch"
            >
          </div>
        </div>

        <div class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>类型</th>
                <th>名称</th>
                <th>分组</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="filteredAlgorithms.length === 0">
                <td colspan="5" class="empty-row">暂无数据</td>
              </tr>
              <tr v-else v-for="record in filteredAlgorithms" :key="record.type">
                <td>{{ record.type }}</td>
                <td>{{ record.name }}</td>
                <td>
                  <span class="status-tag" :class="getGroupTagClass(record.group_name)">
                    {{ record.group_name || '-' }}
                  </span>
                </td>
                <td>
                  <span class="status-badge" :class="record.status === 'online' ? 'active' : 'inactive'">
                    {{ record.status === 'online' ? '上线' : '下线' }}
                  </span>
                </td>
                <td>
                  <div class="table-actions">
                    <button class="btn btn-text btn-sm" @click="handleEdit(record)">
                      <i class="fas fa-edit btn-icon"></i>编辑
                    </button>
                    <button class="btn btn-text btn-sm" @click="handleToggleStatus(record)">
                      <i :class="record.status === 'online' ? 'fas fa-toggle-off' : 'fas fa-toggle-on'" class="btn-icon"></i>
                      {{ record.status === 'online' ? '禁用' : '启用' }}
                    </button>
                    <button class="btn btn-text btn-sm" @click="handleSelect(record)">
                      <i class="fas fa-check btn-icon"></i>选择
                    </button>
                    <button class="btn btn-text btn-sm btn-danger" @click="confirmDelete(record)">
                      <i class="fas fa-trash btn-icon"></i>删除
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else class="mode-form">
        <div class="tabs-nav">
          <button
            v-for="tab in formTabs"
            :key="tab.key"
            class="tab-btn"
            :class="{ active: activeTab === tab.key }"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </div>

        <div v-show="activeTab === 'basic'" class="tab-content">
          <div class="form-row">
            <div class="form-group">
              <label>算法类型 <span class="required">*</span></label>
              <input
                type="text"
                class="form-input"
                v-model="formState.type"
                :disabled="effectiveMode === 'edit'"
                placeholder="如: translation, asr"
              >
            </div>
            <div class="form-group">
              <label>显示名称 <span class="required">*</span></label>
              <input
                type="text"
                class="form-input"
                v-model="formState.name"
                placeholder="如: 翻译"
              >
            </div>
            <div class="form-group">
              <label>所属分组 <span class="required">*</span></label>
              <select class="form-input" v-model="formState.group_id" :disabled="effectiveMode === 'edit'">
                <option :value="null">请选择分组</option>
                <option v-for="group in groups" :key="group.id" :value="group.id">
                  {{ group.name }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label>排序</label>
              <input type="number" class="form-input" v-model.number="formState.display_order" min="0">
            </div>
          </div>

          <div class="form-row">
            <div class="form-group full-width">
              <label>描述</label>
              <textarea class="form-input" v-model="formState.description" rows="3"></textarea>
            </div>
          </div>
                    <div class="form-row">
            <div class="form-group status-switch-group">
              <label>状态</label>
              <div class="switch-container">
                <label class="custom-switch">
                  <input type="checkbox" class="switch-checkbox" v-model="formState.statusSwitch">
                  <span class="switch-slider"></span>
                </label>
                <span class="switch-label">{{ formState.statusSwitch ? '上线' : '下线' }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-show="activeTab === 'params'" class="tab-content">
          <div class="params-toolbar">
            <div class="param-type-tabs">
              <button 
                class="param-type-tab" 
                :class="{ active: paramConfigType === 'device' }"
                @click="paramConfigType = 'device'"
              >
                设备参数
              </button>
              <button 
                class="param-type-tab" 
                :class="{ active: paramConfigType === 'api' }"
                @click="paramConfigType = 'api'"
              >
                API参数
              </button>
              <button 
                class="param-type-tab" 
                :class="{ active: paramConfigType === 'case' }"
                @click="paramConfigType = 'case'"
              >
                用例参数
              </button>
            </div>
            <button class="btn btn-primary btn-sm" @click="handleAddParam">
              <i class="fas fa-plus btn-icon"></i>添加参数
            </button>
          </div>

          <!-- 设备参数和API参数表格 -->
          <div v-if="paramConfigType !== 'case'" class="table-container">
            <table class="data-table">
              <thead>
                <tr>
                  <th>参数代码</th>
                  <th>参数名称</th>
                  <th>方向</th>
                  <th>类型</th>
                  <th>必填</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="currentParams.length === 0">
                  <td colspan="6" class="empty-row">暂无参数</td>
                </tr>
                <tr v-else v-for="(param, index) in currentParams" :key="param.id || param.tempId || index">
                  <td>
                    <input type="text" class="form-input form-input-sm param-code-input" v-model="param.param_code" @blur="handleParamBlur(param, index, paramConfigType)">
                  </td>
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.param_name" @blur="handleParamBlur(param, index, paramConfigType)">
                  </td>
                  <td>
                    <select class="form-input form-input-sm" v-model="param.direction" @change="handleParamBlur(param, index, paramConfigType)">
                      <option value="input">输入</option>
                      <option value="output">输出</option>
                    </select>
                  </td>
                  <td>
                    <select class="form-input form-input-sm" v-model="param.param_type" @change="handleParamBlur(param, index, paramConfigType)">
                      <option value="text">文本</option>
                      <option value="audio_stream">音频流</option>
                      <option value="audio_file">音频文件</option>
                      <option value="text_file">文本文件</option>
                      <option value="rttm">RTTM标注</option>
                      <option value="stm">STM标注</option>
                      <option value="json">JSON结构化</option>
                    </select>
                  </td>
                  <td>
                    <label class="checkbox-container">
                      <input type="checkbox" v-model="param.required" @change="handleParamBlur(param, index, paramConfigType)">
                    </label>
                  </td>
                  <td>
                    <button class="btn btn-text btn-sm btn-danger" @click="handleRemoveParam(index)">
                      <i class="fas fa-trash btn-icon"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 用例参数表格 -->
          <div v-if="paramConfigType === 'case'" class="table-container">
            <table class="data-table">
              <thead>
                <tr>
                  <th>参数代码</th>
                  <th>参数名称</th>
                  <th>类型</th>
                  <th>组件</th>
                  <th>选项来源</th>
                  <th>必填</th>
                  <th>默认值</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="formState.case_params.length === 0">
                  <td colspan="8" class="empty-row">暂无用例参数</td>
                </tr>
                <tr v-else v-for="(param, index) in formState.case_params" :key="param.id || param.tempId || index">
                  <td>
                    <input type="text" class="form-input form-input-sm param-code-input" v-model="param.param_code" @blur="handleCaseParamBlur(param, index)">
                  </td>
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.param_name" @blur="handleCaseParamBlur(param, index)">
                  </td>
                  <td>
                    <select class="form-input form-input-sm" v-model="param.param_type" @change="handleCaseParamTypeChange(param, index)">
                      <option value="select">下拉框</option>
                      <option value="text">文本</option>
                      <option value="number">数字</option>
                      <option value="boolean">开关</option>
                      <option value="textarea">多行文本</option>
                      <option value="reference">参考参数</option>
                    </select>
                  </td>
                  <td>
                    <select 
                      class="form-input form-input-sm" 
                      v-model="param.component"
                      :disabled="param.param_type !== 'select'"
                      @change="handleCaseParamBlur(param, index)"
                    >
                      <option value="select">Select</option>
                      <option value="input">Input</option>
                      <option value="input-number">InputNumber</option>
                      <option value="switch">Switch</option>
                      <option value="textarea">Textarea</option>
                    </select>
                  </td>
                  <td>
                    <select 
                      class="form-input form-input-sm" 
                      v-model="param.options_source"
                      :disabled="param.param_type !== 'select'"
                      @change="handleCaseParamBlur(param, index)"
                    >
                      <option v-for="source in optionsSources" :key="source.value" :value="source.value">
                        {{ source.label }}
                      </option>
                    </select>
                  </td>
                  <td>
                    <label class="checkbox-container">
                      <input type="checkbox" v-model="param.required" @change="handleCaseParamBlur(param, index)">
                    </label>
                  </td>
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.default_value" placeholder="默认值" @blur="handleCaseParamBlur(param, index)">
                  </td>
                  <td>
                    <button class="btn btn-text btn-sm btn-danger" @click="handleRemoveCaseParam(index)">
                      <i class="fas fa-trash btn-icon"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- 参考参数配置 -->
        <div v-show="activeTab === 'reference'" class="tab-content">
          <div class="reference-config-intro">
            <p>配置算法的参考参数，用于存储参考文本、音频、文件等数据。</p>
            <p>参考类型支持：文本、音频、RTTM、STM等。配置的参考字段可参与评估参数映射。</p>
          </div>

          <div class="params-toolbar">
            <button class="btn btn-primary btn-sm" @click="handleAddReferenceParam">
              <i class="fas fa-plus btn-icon"></i>添加参考字段
            </button>
          </div>

          <div class="table-container">
            <table class="data-table" style="table-layout: fixed;">
              <thead>
                <tr>
                  <th style="width: 120px;">参数代码</th>
                  <th style="width: 100px;">参数名称</th>
                  <th style="width: 100px;">参考类型</th>
                  <th style="width: 120px;">标注代码</th>
                  <th style="width: 100px;">标注格式</th>
                  <th style="width: 120px;">帮助文本</th>
                  <th style="width: 60px;">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="formState.reference_params.length === 0">
                  <td colspan="7" class="empty-row">暂无参考参数</td>
                </tr>
                <tr v-else v-for="(param, index) in formState.reference_params" :key="param.id || param.tempId || index">
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.code" placeholder="如: asr_reference_text" @blur="handleReferenceParamBlur(param, index)">
                  </td>
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.name" placeholder="参数名称" @blur="handleReferenceParamBlur(param, index)">
                  </td>
                  <td>
                    <select class="form-input form-input-sm" v-model="param.type" @change="handleReferenceParamBlur(param, index)">
                      <option value="text">文本</option>
                      <option value="audio">音频</option>
                      <option value="json">JSON</option>
                      <option value="rttm">RTTM</option>
                      <option value="stm">STM</option>
                    </select>
                  </td>
                  <td>
                    <div class="annotation-name-input-group" style="display: flex; flex-wrap: wrap; gap: 4px;">
                      <select class="form-input form-input-sm" v-model="param.annotation_code" @change="handleReferenceParamBlur(param, index)">
                        <option value="">自定义...</option>
                        <option value="diarization">diarization</option>
                        <option value="asr">asr</option>
                        <option value="translation">translation</option>
                      </select>
                      <input 
                        v-if="!param.annotation_code || !['diarization', 'asr', 'translation'].includes(param.annotation_code)"
                        type="text" 
                        class="form-input form-input-sm" 
                        v-model="param.annotation_code" 
                        placeholder="自定义名称"
                        @blur="handleReferenceParamBlur(param, index)"
                      >
                    </div>
                  </td>
                  <td>
                    <select class="form-input form-input-sm" v-model="param.annotation_format" @change="handleReferenceParamBlur(param, index)">
                      <option value="">不指定</option>
                      <option value="text">文本</option>
                      <option value="json">JSON</option>
                      <option value="rttm">RTTM</option>
                      <option value="stm">STM</option>
                    </select>
                  </td>
                  <td>
                    <input type="text" class="form-input form-input-sm" v-model="param.help_text" placeholder="可选提示" @blur="handleReferenceParamBlur(param, index)">
                  </td>
                  <td>
                    <button class="btn btn-text btn-sm btn-danger" @click="handleRemoveReferenceParam(index)">
                      <i class="fas fa-trash btn-icon"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-show="activeTab === 'mappings'" class="tab-content">
          <div class="mapping-section">
            <div class="mapping-header" @click="toggleMapping('device')">
              <i class="fas fa-chevron-down expand-icon" :class="{ 'fa-chevron-up': mappingExpanded.device }"></i>
              <span>设备参数映射 (用例参数 → 设备参数)</span>
            </div>
            <div class="mapping-body" v-show="mappingExpanded.device">
              <MappingEditor
                :mappings="formState.mappings.device"
                :algorithm-type="formState.type"
                :case-params="[...caseParams, ...referenceParams]"
                :device-params="deviceParams"
                component-type="device"
                @update="updateMappings('device', $event)"
              />
            </div>
          </div>

          <div class="mapping-section">
            <div class="mapping-header" @click="toggleMapping('api')">
              <i class="fas fa-chevron-down expand-icon" :class="{ 'fa-chevron-up': mappingExpanded.api }"></i>
              <span>API参数映射 (用例参数 → API参数)</span>
            </div>
            <div class="mapping-body" v-show="mappingExpanded.api">
              <MappingEditor
                :mappings="formState.mappings.api"
                :algorithm-type="formState.type"
                :case-params="[...caseParams, ...referenceParams]"
                :api-params="apiParams"
                component-type="api"
                @update="updateMappings('api', $event)"
              />
            </div>
          </div>

          <div class="mapping-section">
            <div class="mapping-header" @click="toggleMapping('evaluation')">
              <i class="fas fa-chevron-down expand-icon" :class="{ 'fa-chevron-up': mappingExpanded.evaluation }"></i>
              <span>评估参数映射 (用例参数/设备输出/API输出 → 评估维度)</span>
            </div>
            <div class="mapping-body" v-show="mappingExpanded.evaluation">
              <MappingEditor
                :mappings="formState.mappings.evaluation"
                :algorithm-type="formState.type"
                :case-params="caseParams"
                :reference-params="referenceParams"
                :device-params="[...deviceParams, ...deviceOutputParams]"
                :api-params="[...apiParams, ...apiOutputParams]"
                :main-dimensions="mainDimensions"
                component-type="evaluation"
                @update="updateMappings('evaluation', $event)"
              />
            </div>
          </div>
        </div>

        <div v-show="activeTab === 'dimensions'" class="tab-content">
          <div class="dimensions-toolbar">
            <button class="btn btn-primary btn-sm" @click="handleAddDimension">
              <i class="fas fa-plus btn-icon"></i>添加关联维度
            </button>
          </div>

          <div class="table-container">
            <table class="data-table">
              <thead>
                <tr>
                  <th>评估维度</th>
                  <th>权重</th>
                  <th>默认</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="formState.associated_dimensions.length === 0">
                  <td colspan="4" class="empty-row">暂无关联维度</td>
                </tr>
                <tr v-else v-for="(dim, index) in formState.associated_dimensions" :key="index">
                  <td>
                    <select class="form-input form-input-sm" v-model="dim.dimension_id" @blur="handleDimensionBlur(index)">
                      <option :value="null">请选择维度</option>
                      <option v-for="dimension in availableDimensions" :key="dimension.id" :value="dimension.id">
                        {{ dimension.name }}
                      </option>
                    </select>
                  </td>
                  <td>
                    <input type="number" class="form-input form-input-sm" v-model.number="dim.weight" min="0" max="1" step="0.1" @blur="handleDimensionBlur(index)">
                  </td>
                  <td>
                    <label class="checkbox-container">
                      <input type="checkbox" v-model="dim.is_default" @change="handleDimensionChange(index)">
                    </label>
                  </td>
                  <td>
                    <button class="btn btn-text btn-sm btn-danger" @click="handleRemoveDimension(index)">
                      <i class="fas fa-trash btn-icon"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </BasicModal>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, nextTick } from 'vue'
import BasicModal from '../common/modal/BasicModal.vue'
import MappingEditor from './MappingEditor.vue'
import { useModalControl, MODAL_TYPES } from '../../composables/useModal'
import { useDimensions } from '../../composables/useDimensions'
import { algorithmApi, evaluationApi } from '../../utils/api'

interface AlgorithmGroup {
  id: number
  name: string
  description?: string
  icon?: string
  display_order: number
}

interface Dimension {
  id: number
  name: string
  code: string
  description?: string
  dimensionType?: string
  parentDimensionId?: number | null
}

interface AlgorithmRecord {
  type: string
  name: string
  group_id?: number
  group_name?: string
  description?: string
  status: string
  icon?: string
  display_order: number
  device_params?: any[]
  api_params?: any[]
  case_params?: any[]
  params?: any[]
  mappings?: any
  associated_dimensions?: { dimension_id: number | null; weight: number; is_default: boolean }[]
}

interface ModalProps {
  visible: boolean
  mode?: 'list' | 'create' | 'edit' | 'select'
  editData?: AlgorithmRecord | null
}

const props = withDefaults(defineProps<ModalProps>(), {
  visible: false,
  mode: 'list',
  editData: null
})

const internalMode = ref<'list' | 'create' | 'edit' | 'select'>(props.mode)

watch(() => props.mode, (newMode) => {
  internalMode.value = newMode
})

const effectiveMode = computed(() => internalMode.value)

const emit = defineEmits<{
  (e: 'update:visible', visible: boolean): void
  (e: 'select', data: AlgorithmRecord): void
  (e: 'success'): void
}>()

const modalControl = useModalControl()

const formTabs = [
  { key: 'basic', label: '基本信息' },
  { key: 'params', label: '参数配置' },
  { key: 'reference', label: '参考参数' },
  { key: 'mappings', label: '参数映射' },
  { key: 'dimensions', label: '关联维度' }
]

const modalWidth = computed(() => {
  if (effectiveMode.value === 'list') return '700px'
  return '1200px'
})

const title = computed(() => {
  const titles = {
    list: '算法配置管理',
    create: '新建算法',
    edit: '编辑算法',
    select: '选择算法'
  }
  return titles[effectiveMode.value]
})

const okText = computed(() => {
  if (effectiveMode.value === 'select') return '选择'
  return '确定'
})

const cancelText = computed(() => '取消')

const searchKeyword = ref('')
const activeTab = ref('basic')
const paramConfigType = ref<'device' | 'api' | 'case'>('device')
const mappingExpanded = ref({
  device: true,
  api: true,
  evaluation: true
})

const algorithms = ref<AlgorithmRecord[]>([])
const groups = ref<AlgorithmGroup[]>([])
const availableDimensions = ref<Dimension[]>([])
const optionsSources = ref<{ value: string; label: string; description: string }[]>([])

const { fetchAllDimensions } = useDimensions()

const mainDimensions = computed(() => {
  return availableDimensions.value.filter(d => d.dimensionType === 'main' || !d.dimensionType)
})

const formState = reactive({
  type: '',
  name: '',
  group_id: null as number | null,
  description: '',
  status: 'online' as 'online' | 'offline',
  statusSwitch: true,
  icon: '',
  display_order: 0,
  device_params: [] as any[],
  api_params: [] as any[],
  case_params: [] as any[],
  mappings: {
    device: [] as any[],
    api: [] as any[],
    evaluation: [] as any[]
  },
  associated_dimensions: [] as { dimension_id: number | null; weight: number; is_default: boolean }[],
  reference_params: [] as { code: string; name: string; type: string; annotation_code: string; annotation_format: string; help_text: string }[]
})

const currentParams = computed(() => {
  if (paramConfigType.value === 'device') {
    return formState.device_params
  } else if (paramConfigType.value === 'api') {
    return formState.api_params
  }
  return []
})

const availableParams = computed(() => {
  const params = paramConfigType.value === 'device' ? formState.device_params : formState.api_params
  return params
    .filter(param => param.param_code && !param.hidden)
    .map(param => ({
      code: param.param_code,
      name: param.param_name || param.param_code,
      direction: param.direction
    }))
})

const caseParams = computed(() => {
  return (formState.case_params || [])
    .filter(param => param.param_code && !param.hidden)
    .map(param => ({
      code: param.param_code,
      name: param.param_name || param.param_code,
      direction: param.direction
    }))
})

const referenceParams = computed(() => {
  return (formState.reference_params || [])
    .filter(param => param.code)
    .map(param => ({
      code: param.code,
      name: param.name || param.code,
      direction: 'reference'
    }))
})

const deviceParams = computed(() => {
  return (formState.device_params || [])
    .filter(param => param.param_code && !param.hidden)
    .map(param => ({
      code: param.param_code,
      name: param.param_name || param.param_code,
      direction: param.direction
    }))
})

const deviceOutputParams = computed(() => {
  const existingCodes = new Set(deviceParams.value.map(p => p.code))
  return (formState.device_params || [])
    .filter(param => param.param_code && !param.hidden && param.direction === 'output' && !existingCodes.has(param.param_code))
    .map(param => ({
      code: param.param_code,
      name: param.param_name || param.param_code,
      direction: 'output'
    }))
})

const apiParams = computed(() => {
  return (formState.api_params || [])
    .filter(param => param.param_code && !param.hidden)
    .map(param => ({
      code: param.param_code,
      name: param.param_name || param.param_code,
      direction: param.direction
    }))
})

const apiOutputParams = computed(() => {
  const existingCodes = new Set(apiParams.value.map(p => p.code))
  return (formState.api_params || [])
    .filter(param => param.param_code && !param.hidden && param.direction === 'output' && !existingCodes.has(param.param_code))
    .map(param => ({
      code: param.param_code,
      name: param.param_name || param.param_code,
      direction: 'output'
    }))
})

const filteredAlgorithms = computed(() => {
  if (!searchKeyword.value) return algorithms.value
  return algorithms.value.filter(a =>
    a.type.includes(searchKeyword.value) ||
    a.name.includes(searchKeyword.value)
  )
})

function getGroupTagClass(groupName: string | undefined): string {
  if (!groupName) return ''
  const classes: Record<string, string> = {
    '翻译': 'pending',
    '语音识别': 'completed',
    '声纹识别': 'in-progress',
    '语音合成': 'failed'
  }
  return classes[groupName] || ''
}

watch(() => props.visible, (visible) => {
  if (visible) {
    if (effectiveMode.value === 'list') {
      loadAlgorithms()
    } else if (effectiveMode.value === 'create') {
      resetForm()
    }
    loadGroups()
    loadDimensions()
    loadOptionsSources()
  }
})

function normalizeParamFields(param: any) {
  return {
    ...param,
    param_code: param.paramCode ?? param.param_code,
    param_name: param.paramName ?? param.param_name,
    param_type: param.paramType ?? param.param_type,
    ui_group: param.uiGroup ?? param.ui_group,
    ui_order: param.uiOrder ?? param.ui_order,
    default_value: param.defaultValue ?? param.default_value,
    required: param.required,
    hidden: param.hidden,
    direction: param.direction,
    label: param.label,
    help_text: param.helpText ?? param.help_text,
    options_source: param.optionsSource ?? param.options_source,
    options_field: param.optionsField ?? param.options_field,
    options_label_field: param.optionsLabelField ?? param.options_label_field
  }
}

watch(() => [props.mode, props.editData], ([mode, editData]) => {
  console.log('watch mode:', mode, 'editData:', editData)
  if (mode === 'edit' && editData) {
    const deviceParams = ((editData.deviceParams ?? editData.device_params) || []).map(normalizeParamFields).map(p => ({ ...p }))
    const apiParams = ((editData.apiParams ?? editData.api_params) || []).map(normalizeParamFields).map(p => ({ ...p }))
    const caseParams = ((editData.caseParams ?? editData.case_params) || []).map(p => ({ ...p }))
    const refConfig = editData.reference_params ?? editData.referenceConfig ?? editData.reference_config ?? editData.referenceParams
    
    Object.assign(formState, {
      type: editData.type,
      name: editData.name,
      group_id: editData.groupId ?? editData.group_id ?? null,
      description: editData.description || '',
      status: editData.status as 'online' | 'offline',
      statusSwitch: editData.status === 'online',
      icon: editData.icon || '',
      display_order: (editData.displayOrder ?? editData.display_order) || 0,
      device_params: deviceParams,
      api_params: apiParams,
      case_params: caseParams,
      params: editData.params || [],
      mappings: JSON.parse(JSON.stringify(editData.mappings || { device: [], api: [], evaluation: [] })),
      associated_dimensions: ((editData.associatedDimensions ?? editData.associated_dimensions) || []).map((d: any) => ({
        dimension_id: d.dimensionId ?? d.dimension_id,
        weight: d.weight ?? 1.0,
        is_default: d.isDefault ?? d.is_default ?? false
      })),
      reference_params: (refConfig || []).map((p: any) => ({
        id: p.id,
        code: p.code || '',
        name: p.name || '',
        type: p.type || 'text',
        annotation_code: p.annotation_code || '',
        annotation_format: p.annotation_format || '',
        help_text: p.help_text || ''
      }))
    })
  } else if (mode === 'create') {
    resetForm()
  }
}, { immediate: true })

async function loadAlgorithms() {
  try {
    const result = await algorithmApi.getDefinitions()
    algorithms.value = result.data || []
  } catch (error) {
    console.error('加载算法列表失败:', error)
  }
}

async function loadGroups() {
  try {
    const result = await algorithmApi.getGroups()
    groups.value = result.data || []
  } catch (error) {
    console.error('加载分组列表失败:', error)
  }
}

async function loadDimensions() {
  try {
    const dimensions = await fetchAllDimensions()
    availableDimensions.value = dimensions as Dimension[]
  } catch (error) {
    console.error('加载评估维度失败:', error)
  }
}

async function loadOptionsSources() {
  try {
    const result = await algorithmApi.getOptionsSources()
    optionsSources.value = result.data || []
  } catch (error) {
    console.error('加载选项来源失败:', error)
  }
}

function resetForm() {
  formState.type = ''
  formState.name = ''
  formState.group_id = null
  formState.description = ''
  formState.status = 'online'
  formState.statusSwitch = true
  formState.icon = ''
  formState.display_order = 0
  formState.device_params = []
  formState.api_params = []
  formState.case_params = []
  formState.mappings = { device: [], api: [], evaluation: [] }
  formState.associated_dimensions = []
  formState.reference_params = []
  activeTab.value = 'basic'
  paramConfigType.value = 'device'
}

function handleCancel() {
  if (internalMode.value !== props.mode && props.mode === 'list') {
    internalMode.value = 'list'
  } else {
    emit('update:visible', false)
  }
}

async function handleOk() {
  console.log('handleOk:', { mode: effectiveMode.value, formState: JSON.stringify(formState) })
  if (effectiveMode.value === 'select') {
    if (props.editData) {
      emit('select', props.editData)
      emit('update:visible', false)
    }
    return
  }

  if (!formState.type || !formState.name || !formState.group_id) {
    alert('请填写必填字段')
    return
  }

  await saveAlgorithm()
}

async function saveAlgorithm() {
  try {
    formState.status = formState.statusSwitch ? 'online' : 'offline'
    
    const bodyData: any = {
      type: formState.type,
      name: formState.name,
      group_id: formState.group_id,
      description: formState.description,
      status: formState.status,
      icon: formState.icon,
      display_order: formState.display_order,
      device_params: formState.device_params,
      api_params: formState.api_params,
      case_params: formState.case_params,
      mappings: formState.mappings,
      associated_dimensions: formState.associated_dimensions,
      reference_params: formState.reference_params
    }

    if (effectiveMode.value === 'edit') {
      await algorithmApi.updateDefinition(formState.type, bodyData)
    } else {
      await algorithmApi.createDefinition(bodyData)
    }
    emit('success')
    emit('update:visible', false)
    loadAlgorithms()
  } catch (error) {
    console.error('操作失败:', error)
  }
}

function handleCreate() {
  resetForm()
  internalMode.value = 'create'
}

async function handleEdit(record: AlgorithmRecord) {
  try {
    const result = await algorithmApi.getDefinition(record.type)
    if (result) {
      const editData = result
      const deviceParams = ((editData.deviceParams ?? editData.device_params) || []).map(normalizeParamFields).map(p => ({ ...p }))
      const apiParams = ((editData.apiParams ?? editData.api_params) || []).map(normalizeParamFields).map(p => ({ ...p }))
      const caseParams = ((editData.caseParams ?? editData.case_params) || []).map(p => ({ ...p }))
      const refConfig = editData.reference_params ?? editData.referenceConfig ?? editData.reference_config ?? editData.referenceParams
      
      Object.assign(formState, {
        type: editData.type,
        name: editData.name,
        group_id: editData.groupId ?? editData.group_id ?? null,
        description: editData.description || '',
        status: editData.status as 'online' | 'offline',
        statusSwitch: editData.status === 'online',
        icon: editData.icon || '',
        display_order: (editData.displayOrder ?? editData.display_order) || 0,
        device_params: deviceParams,
        api_params: apiParams,
        case_params: caseParams,
        params: editData.params || [],
        mappings: JSON.parse(JSON.stringify(editData.mappings || { device: [], api: [], evaluation: [] })),
        associated_dimensions: ((editData.associatedDimensions ?? editData.associated_dimensions) || []).map((d: any) => ({
          id: d.id,
          dimension_id: d.dimensionId ?? d.dimension_id,
          weight: d.weight ?? 1.0,
          is_default: d.isDefault ?? d.is_default ?? false
        })),
        reference_params: (refConfig || []).map((p: any) => ({
          id: p.id,
          code: p.code || '',
          name: p.name || '',
          type: p.type || 'text',
          annotation_code: p.annotation_code || '',
          annotation_format: p.annotation_format || '',
          help_text: p.help_text || ''
        }))
      })
      paramConfigType.value = 'device'
      internalMode.value = 'edit'
    }
  } catch (error) {
    console.error('加载算法详情失败:', error)
  }
}

function handleSelect(record: AlgorithmRecord) {
  emit('select', record)
  emit('update:visible', false)
}

async function handleToggleStatus(record: AlgorithmRecord) {
  const newStatus = record.status === 'online' ? 'offline' : 'online'
  const action = newStatus === 'offline' ? '禁用' : '启用'
  
  try {
    await algorithmApi.updateDefinition(record.type, { status: newStatus })
    loadAlgorithms()
  } catch (error) {
    console.error(`${action}失败:`, error)
  }
}

async function confirmDelete(record: AlgorithmRecord) {
  const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
    title: '确认删除',
    content: `确定要删除算法「${record.name}」吗？此操作不可恢复。`,
    confirmText: '删除',
    cancelText: '取消',
    danger: true
  })
  
  if (confirmed) {
    await executeDelete(record)
  }
}

async function executeDelete(record: AlgorithmRecord) {
  if (!record) return
  
  try {
    await algorithmApi.deleteDefinition(record.type)
    loadAlgorithms()
  } catch (error) {
    console.error('删除失败:', error)
  }
}

function handleSearch() {
}

let paramIdCounter = 0

function handleAddParam() {
  const isCase = paramConfigType.value === 'case'
  const tempId = `temp_${++paramIdCounter}`
  if (isCase) {
    formState.case_params.push({
      tempId,
      param_code: '',
      param_name: '',
      param_type: 'text',
      component: 'input',
      options_source: '',
      options_field: '',
      options_label_field: '',
      required: false,
      default_value: '',
      ui_order: formState.case_params.length
    })
  } else {
    const params = paramConfigType.value === 'device' ? formState.device_params : formState.api_params
    params.push({
      tempId,
      param_code: '',
      param_name: '',
      direction: 'input',
      param_type: 'text',
      required: false
    })
  }
  nextTick(() => {
    const inputs = document.querySelectorAll('.param-code-input')
    if (inputs.length > 0) {
      const lastInput = inputs[inputs.length - 1] as HTMLInputElement
      lastInput.focus()
    }
  })
}

function handleRemoveCaseParam(index: number) {
  const param = formState.case_params[index]
  if (param && param.id) {
    const backup = { ...param }
    formState.case_params.splice(index, 1)
    algorithmApi.deleteCaseParam(param.id).catch(err => {
      console.error('删除用例参数失败:', err)
      formState.case_params.splice(index, 0, backup)
      alert('删除用例参数失败，已恢复')
    })
  } else {
    formState.case_params.splice(index, 1)
  }
}

function handleAddReferenceParam() {
  formState.reference_params.push({
    tempId: `temp_ref_${++paramIdCounter}`,
    code: '',
    name: '',
    type: 'text',
    annotation_code: '',
    annotation_format: '',
    help_text: ''
  })
}

function handleRemoveReferenceParam(index: number) {
  const param = formState.reference_params[index]
  if (param && param.id) {
    const backup = { ...param }
    formState.reference_params.splice(index, 1)
    algorithmApi.deleteReferenceParam(param.id, formState.type).catch(err => {
      console.error('删除参考参数失败:', err)
      formState.reference_params.splice(index, 0, backup)
      alert('删除参考参数失败，已恢复')
    })
  } else {
    formState.reference_params.splice(index, 1)
  }
}

function getDefaultComponent(paramType: string): string {
  const typeComponentMap: Record<string, string> = {
    'text': 'input',
    'number': 'input-number',
    'boolean': 'switch',
    'select': 'select',
    'textarea': 'textarea',
    'slider': 'slider'
  }
  return typeComponentMap[paramType] || 'input'
}

function handleCaseParamTypeChange(param: any, index: number) {
  if (param.param_type !== 'select') {
    param.component = getDefaultComponent(param.param_type)
    param.options_source = ''
    param.options_field = ''
    param.options_label_field = ''
  } else {
    param.component = 'select'
  }
  handleCaseParamBlur(param, index)
}

let saveTimeout: any = null
let caseParamSaveTimeout: any = null
let referenceParamSaveTimeout: any = null

async function handleParamBlur(param: any, index: number, paramType: string) {
  if (!formState.type || !param.param_code) return
  if (saveTimeout) clearTimeout(saveTimeout)
  saveTimeout = setTimeout(async () => {
    await autoSaveParams(param, paramType)
  }, 1500)
}

async function handleCaseParamBlur(param: any, index: number) {
  if (!formState.type || !param.param_code) return
  if (caseParamSaveTimeout) clearTimeout(caseParamSaveTimeout)
  caseParamSaveTimeout = setTimeout(async () => {
    await autoSaveCaseParams(param, index)
  }, 1000)
}

async function autoSaveParams(param: any, paramType: string) {
  if (!formState.type || !param.param_code) return
  try {
    const bodyData: any = {
      algorithm_type: formState.type,
      param_type_source: paramType,
      param_code: param.param_code,
      param_name: param.param_name,
      param_type: param.param_type,
      direction: param.direction,
      required: param.required,
      default_value: param.default_value,
      validation_rules: param.validation_rules,
      help_text: param.help_text,
      ui_order: param.ui_order,
      hidden: param.hidden
    }
    let result
    if (param.id) {
      result = await algorithmApi.updateParam(param.id, bodyData)
    } else {
      result = await algorithmApi.createParam(bodyData)
      param.id = result.id
    }
  } catch (error) {
    console.error('自动保存参数失败:', error)
  }
}

async function autoSaveCaseParams(param: any, index: number) {
  if (!formState.type || !param.param_code) return
  try {
    const bodyData: any = {
      algorithm_type: formState.type,
      param_code: param.param_code,
      param_name: param.param_name,
      param_type: param.param_type,
      required: param.required,
      default_value: param.default_value,
      help_text: param.help_text,
      component: param.component,
      ui_order: param.ui_order,
      hidden: param.hidden
    }
    bodyData.options_source = param.options_source || null
    bodyData.options_field = param.options_field || null
    bodyData.options_label_field = param.options_label_field || null
    let result
    if (param.id) {
      result = await algorithmApi.updateCaseParam(param.id, bodyData)
    } else {
      result = await algorithmApi.createCaseParam(bodyData)
      param.id = result.id
    }
  } catch (error) {
    console.error('自动保存用例参数失败:', error)
  }
}

async function handleReferenceParamBlur(param: any, index: number) {
  if (!formState.type || !param.code) return
  if (referenceParamSaveTimeout) clearTimeout(referenceParamSaveTimeout)
  referenceParamSaveTimeout = setTimeout(async () => {
    await autoSaveReferenceParams(param, index)
  }, 1000)
}

async function autoSaveReferenceParams(param: any, index: number) {
  if (!formState.type || !param.code) return
  try {
    const bodyData = {
      code: param.code,
      name: param.name,
      type: param.type,
      annotation_code: param.annotation_code || null,
      annotation_format: param.annotation_format || null,
      help_text: param.help_text
    }
    let result
    if (param.id) {
      result = await algorithmApi.updateReferenceParam(param.id, formState.type, bodyData)
    } else {
      result = await algorithmApi.createReferenceParam({ ...bodyData, algorithm_type: formState.type })
      param.id = result.id
    }
  } catch (error) {
    console.error('自动保存参考参数失败:', error)
  }
}

function handleRemoveParam(index: number) {
  const params = paramConfigType.value === 'device' ? formState.device_params : formState.api_params
  const param = params[index]
  if (param && param.id) {
    const backup = { ...param }
    params.splice(index, 1)
    algorithmApi.deleteParam(param.id).catch(err => {
      console.error('删除参数失败:', err)
      params.splice(index, 0, backup)
      alert('删除参数失败，已恢复')
    })
  } else {
    params.splice(index, 1)
  }
}

function updateMappings(componentType: string, mappings: any[]) {
  formState.mappings[componentType] = mappings
  console.log('更新映射:', componentType, mappings)
}

function toggleMapping(key: string) {
  mappingExpanded.value[key] = !mappingExpanded.value[key]
}

function handleAddDimension() {
  formState.associated_dimensions.push({
    tempId: `temp_dim_${++paramIdCounter}`,
    dimension_id: null,
    weight: 1.0,
    is_default: false
  })
}

function handleRemoveDimension(index: number) {
  const dim = formState.associated_dimensions[index]
  formState.associated_dimensions.splice(index, 1)
  if (effectiveMode.value === 'edit' && formState.type && dim) {
    if (dim.id) {
      algorithmApi.deleteDimensionRelation(dim.id).catch(err => {
        console.error('删除维度关联失败:', err)
      })
    } else if (dim.tempId) {
    }
  }
}

async function handleDimensionChange(index: number) {
  const dim = formState.associated_dimensions[index]
  if (!dim) return

  if (dim.is_default) {
    formState.associated_dimensions.forEach((d, i) => {
      if (i !== index && d.id) {
        d.is_default = false
        algorithmApi.updateDimensionRelation(d.id, { is_default: false }).catch(err => {
          console.error('更新默认维度失败:', err)
        })
      }
    })
  }

  if (effectiveMode.value === 'edit' && formState.type && dim.id) {
    try {
      await algorithmApi.updateDimensionRelation(dim.id, {
        weight: dim.weight,
        is_default: dim.is_default
      })
    } catch (error) {
      console.error('自动保存维度关联失败:', error)
    }
  }
}

async function handleDimensionBlur(index: number) {
  const dim = formState.associated_dimensions[index]
  if (!dim) return

  if (dim.is_default) {
    formState.associated_dimensions.forEach((d, i) => {
      if (i !== index && d.id) {
        d.is_default = false
        algorithmApi.updateDimensionRelation(d.id, { is_default: false }).catch(err => {
          console.error('更新默认维度失败:', err)
        })
      }
    })
  }

  if (effectiveMode.value === 'edit' && formState.type) {
    try {
      if (dim.id) {
        await algorithmApi.updateDimensionRelation(dim.id, {
          weight: dim.weight,
          is_default: dim.is_default,
          dimension_id: dim.dimension_id
        })
      } else if (dim.dimension_id) {
        const result = await algorithmApi.createDimensionRelation({
          algorithm_type: formState.type,
          dimension_id: dim.dimension_id,
          weight: dim.weight,
          is_default: dim.is_default
        })
        dim.id = result.id
        dim.tempId = undefined
      }
    } catch (error) {
      console.error('自动保存维度关联失败:', error)
    }
  }
}
</script>

<style scoped>
.algorithm-config-modal {
  min-height: 200px;
}

.modal-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

.modal-toolbar .search-box {
  width: 200px;
}

.mode-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.tabs-nav {
  display: flex;
  gap: var(--spacing-xs);
  border-bottom: 1px solid var(--border-color);
  padding-bottom: var(--spacing-sm);
}

.tab-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--font-size-md);
  cursor: pointer;
  border-radius: var(--border-radius-md);
  transition: all var(--transition-normal);
}

.tab-btn:hover {
  background: var(--primary-light);
  color: var(--primary-color);
}

.tab-btn.active {
  background: var(--primary-color);
  color: var(--white-color);
}

.tab-content {
  padding: var(--spacing-md) 0;
}

.form-row {
  display: flex;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.form-group {
  flex: 1;
  min-width: 200px;
}

.form-group.full-width {
  flex-basis: 100%;
}

.form-group label {
  display: block;
  margin-bottom: var(--spacing-xs);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.form-group label .required {
  color: var(--danger-color);
}

.switch-container {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  height: 36px;
}

.status-switch-group {
  display: flex;
  align-items: flex-start;
}

.status-switch-group label {
  margin-bottom: 0;
}

.status-switch-group .switch-container {
  margin-top: 4px;
}

.custom-switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
  cursor: pointer;
}

.custom-switch input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
  cursor: pointer;
}

.custom-switch input.switch-checkbox {
  position: absolute !important;
  opacity: 0 !important;
  width: 44px !important;
  height: 24px !important;
  cursor: pointer !important;
  -webkit-appearance: none !important;
  appearance: none !important;
  background: transparent !important;
  border: none !important;
  border-radius: 0 !important;
  box-shadow: none !important;
}

.switch-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--border-color);
  transition: 0.3s;
  border-radius: 24px;
}

.switch-slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.3s;
  border-radius: 50%;
}

.custom-switch input:checked + .switch-slider {
  background-color: var(--primary-color);
}

.custom-switch input:checked + .switch-slider:before {
  transform: translateX(20px);
}

.switch-label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.form-input-sm {
  padding: var(--spacing-xs) var(--spacing-sm);
  font-size: var(--font-size-sm);
  height: 32px;
}

.params-toolbar,
.dimensions-toolbar {
  margin-bottom: var(--spacing-md);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.param-type-tabs {
  display: flex;
  gap: var(--spacing-xs);
}

.param-type-tab {
  padding: var(--spacing-xs) var(--spacing-md);
  border: 1px solid var(--border-color);
  background: var(--background-primary);
  border-radius: var(--border-radius-sm);
  cursor: pointer;
  transition: all var(--transition-normal);
}

.param-type-tab:hover {
  border-color: var(--primary-color);
}

.param-type-tab.active {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.mapping-section {
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  margin-bottom: var(--spacing-sm);
}

.mapping-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--background-secondary);
  cursor: pointer;
  border-radius: var(--border-radius-md);
  transition: all var(--transition-normal);
}

.mapping-header:hover {
  background: var(--primary-light);
}

.mapping-header .expand-icon {
  transition: transform var(--transition-normal);
}

.mapping-body {
  padding: var(--spacing-md);
}

.table-actions {
  display: flex;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
}

.btn-danger {
  color: var(--danger-color);
}

.btn-danger:hover {
  background: var(--danger-light);
  color: var(--danger-color);
}

.reference-config-intro {
  background: var(--background-secondary);
  padding: var(--spacing-md);
  border-radius: var(--border-radius-md);
  margin-bottom: var(--spacing-md);
}

.reference-config-intro p {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

.reference-config-intro p + p {
  margin-top: var(--spacing-xs);
}

.reference-panels {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.reference-panel {
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  overflow: hidden;
}

.reference-panel-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--background-secondary);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.reference-panel-header i {
  color: var(--primary-color);
}

.reference-panel-body {
  padding: var(--spacing-md);
  background: var(--background-primary);
}

@media (max-width: 768px) {
  .form-row {
    flex-direction: column;
  }
  
  .form-group {
    min-width: 100%;
  }
}
</style>
