<template>
  <div class="mapping-editor">
    <div class="mapping-toolbar">
      <div class="mapping-toolbar-actions">
        <div v-if="componentType === 'evaluation'" class="view-mode-tabs">
          <button class="view-mode-tab" :class="{ active: viewMode === 'flat' }" @click="switchViewMode('flat')">
            <i class="fas fa-th-list view-mode-icon"></i>
            <span>平铺视图</span>
          </button>
          <button class="view-mode-tab" :class="{ active: viewMode === 'dimension' }" @click="switchViewMode('dimension')">
            <i class="fas fa-layer-group view-mode-icon"></i>
            <span>评估维度视图</span>
          </button>
        </div>
        <div class="search-box">
          <i class="fas fa-search search-icon"></i>
          <input
            type="text"
            class="search-input"
            placeholder="搜索映射..."
            v-model="filters.keyword"
          >
        </div>
        <select v-if="componentType === 'evaluation'" class="form-input mapping-filter-select" v-model="filters.source">
          <option value="all">全部来源</option>
          <option value="case">用例参数</option>
          <option value="case_config">用例配置</option>
          <option value="reference">参考参数</option>
          <option value="device">设备输出</option>
          <option value="api">API输出</option>
        </select>
        <select class="form-input mapping-filter-select" v-model="filters.transform_type">
          <option value="all">全部转换</option>
          <option value="none">无转换</option>
          <option value="uppercase">转大写</option>
          <option value="lowercase">转小写</option>
          <option value="json_parse">JSON解析</option>
          <option value="rttm_to_obj">RTTM转对象</option>
          <option value="stm_to_obj">STM转对象</option>
        </select>
      </div>
    </div>

    <div class="table-container">
      <table class="data-table">
        <thead>
          <tr>
            <template v-if="componentType === 'evaluation'">
              <th style="width: 100px;">
                来源
                <ColumnFilter
                  v-model="filters.source"
                  label="来源"
                  :options="sourceOptions"
                  :active="filters.source !== 'all'"
                />
              </th>
              <th style="width: 120px;">
                源参数代码
                <ColumnFilter
                  v-model="filters.source_param"
                  label="源参数代码"
                  :options="distinctValues(props.mappings, 'source_param')"
                  :active="filters.source_param !== 'all'"
                />
              </th>
              <th style="width: 120px;">源参数名称</th>
              <th>
                目标评估维度
                <ColumnFilter
                  v-model="filters.dimension_id"
                  label="目标评估维度"
                  :options="dimensionFilterOptions"
                  :active="filters.dimension_id !== 'all'"
                />
              </th>
              <th>
                目标参数
                <ColumnFilter
                  v-model="filters.target_param"
                  label="目标参数"
                  :options="distinctValues(props.mappings, 'target_param')"
                  :active="filters.target_param !== 'all'"
                />
              </th>
              <th style="width: 100px;">
                转换
                <ColumnFilter
                  v-model="filters.transform_type"
                  label="转换"
                  :options="transformOptions"
                  :active="filters.transform_type !== 'all'"
                />
              </th>
            </template>
            <template v-else>
              <th style="width: 120px;">
                源参数代码
                <ColumnFilter
                  v-model="filters.source_param"
                  label="源参数代码"
                  :options="distinctValues(props.mappings, 'source_param')"
                  :active="filters.source_param !== 'all'"
                />
              </th>
              <th style="width: 120px;">源参数名称</th>
              <th style="width: 120px;">
                目标参数代码
                <ColumnFilter
                  v-model="filters.target_param"
                  label="目标参数代码"
                  :options="distinctValues(props.mappings, 'target_param')"
                  :active="filters.target_param !== 'all'"
                />
              </th>
              <th style="width: 120px;">目标参数名称</th>
              <th style="width: 100px;">
                转换
                <ColumnFilter
                  v-model="filters.transform_type"
                  label="转换"
                  :options="transformOptions"
                  :active="filters.transform_type !== 'all'"
                />
              </th>
            </template>
            <th style="width: 60px;">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="mappings.length === 0">
            <td :colspan="colspanCount" class="empty-row">暂无映射</td>
          </tr>
          <tr v-else-if="filteredMappings.length === 0">
            <td :colspan="colspanCount" class="empty-row">无匹配映射</td>
          </tr>
          <template v-else v-for="(record, index) in displayRows" :key="record.__isGroupHeader ? `group-${record.__dimensionKey}` : (record.__isGroupFooter ? `group-footer-${record.__dimensionKey}` : (record.id || `${record.source || ''}-${record.source_param}-${record.target_param}-${record.dimension_id || ''}`))">
            <tr v-if="record.__isGroupHeader" class="dimension-group-header-row">
              <td :colspan="colspanCount">
                <span class="dimension-group-title">
                  <i class="fas fa-layer-group dimension-group-icon"></i>
                  <span class="dimension-group-name">{{ record.__dimensionName }}</span>
                  <span class="dimension-group-count">共 {{ record.__count }} 条</span>
                </span>
              </td>
            </tr>
            <tr v-else-if="record.__isGroupFooter" class="add-row dimension-group-add-row" @click="handleAdd(record.__dimensionId)">
              <td :colspan="colspanCount">
                <span class="add-row-content">
                  <span class="add-row-icon"><i class="fas fa-plus"></i></span>
                  <span>添加映射</span>
                </span>
              </td>
            </tr>
            <tr v-else>
            <template v-if="componentType === 'evaluation'">
              <td>
                <select v-model="record.source" class="form-input form-input-sm" @blur="handleSourceTypeChange(record)">
                  <option value="case">用例参数</option>
                  <option value="case_config">用例配置</option>
                  <option value="reference">参考参数</option>
                  <option value="device">设备输出</option>
                  <option value="api">API输出</option>
                </select>
              </td>
              <td>
                <select v-model="record.source_param" class="form-input form-input-sm" @blur="handleSourceChange(record)">
                  <option value="">选择参数</option>
                  <option v-for="param in getSourceParams(record.source, record.source_param)" :key="param.code" :value="param.code">{{ param.code }}</option>
                </select>
              </td>
              <td class="param-name-cell">{{ getParamName(record.source_param, record.source, record.param_name) }}</td>
              <td>
                <select v-model="record.dimension_id" class="form-input form-input-sm" @blur="handleDimensionChange(record)">
                  <option :value="null">选择维度</option>
                  <option v-if="record.dimension_id && !dimensionOptionIds.has(Number(record.dimension_id))" :value="record.dimension_id">
                    {{ record.dimension_name || `已删除维度(${record.dimension_id})` }}
                  </option>
                  <option v-for="dim in (mainDimensions && mainDimensions.length > 0 ? mainDimensions : availableDimensions)" :key="dim.id" :value="dim.id">{{ dim.name }}</option>
                </select>
              </td>
              <td>
                <select v-model="record.target_param" class="form-input form-input-sm" :disabled="!record.dimension_id" @blur="handleTargetChange(record)">
                  <option value="">{{ record.dimension_id ? '选择参数' : '先选维度' }}</option>
                  <option v-if="record.target_param && !isTargetParamKnown(record)" :value="record.target_param">
                    {{ record.target_param }} - {{ record.target_param_name || record.target_param }}
                  </option>
                  <option v-for="param in getTargetParamOptions(record.dimension_id, record.target_param)" :key="param.code" :value="param.code">{{ param.code }} - {{ param.name }}</option>
                </select>
              </td>
              <td>
                <select v-model="record.transform_type" class="form-input form-input-sm" @blur="handleTransformChange(record)">
                  <option value="none">无转换</option>
                  <option value="uppercase">转大写</option>
                  <option value="lowercase">转小写</option>
                  <option value="json_parse">JSON解析</option>
                  <option value="rttm_to_obj">RTTM转对象</option>
                  <option value="stm_to_obj">STM转对象</option>
                </select>
              </td>
            </template>
            <template v-else>
              <td>
                <select v-model="record.source_param" class="form-input form-input-sm" @blur="handleSourceChange(record)">
                  <option value="">选择参数</option>
                  <option v-for="param in getSourceParams('case', record.source_param)" :key="param.code" :value="param.code">{{ param.code }}</option>
                </select>
              </td>
              <td class="param-name-cell">{{ getParamName(record.source_param, 'case', record.param_name) }}</td>
              <td>
                <select v-model="record.target_param" class="form-input form-input-sm" @blur="handleTargetChange(record)">
                  <option value="">选择参数</option>
                  <option v-for="param in getTargetParamListForDeviceApi(componentType, record.target_param)" :key="param.code" :value="param.code">{{ param.code }}</option>
                </select>
              </td>
              <td class="param-name-cell">{{ getTargetParamName(record.target_param, componentType) }}</td>
              <td>
                <select v-model="record.transform_type" class="form-input form-input-sm" @blur="handleTransformChange(record)">
                  <option value="none">无转换</option>
                  <option value="uppercase">转大写</option>
                  <option value="lowercase">转小写</option>
                  <option value="json_parse">JSON解析</option>
                  <option value="rttm_to_obj">RTTM转对象</option>
                  <option value="stm_to_obj">STM转对象</option>
                </select>
              </td>
            </template>
            <td>
              <button class="btn btn-text btn-sm btn-danger" @click="handleRemove(record)">
                <i class="fas fa-trash btn-icon"></i>
              </button>
            </td>
            </tr>
          </template>
          <tr v-if="viewMode !== 'dimension'" class="add-row" @click="handleAdd()">
            <td :colspan="colspanCount">
              <span class="add-row-content">
                <span class="add-row-icon"><i class="fas fa-plus"></i></span>
                <span>添加映射</span>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="mapping-pagination" v-if="viewMode !== 'dimension' && filteredMappings.length > pageSize">
      <PaginationComponent
        :current-page="currentPage"
        :page-size="pageSize"
        :total-items="filteredMappings.length"
        @prev-page="currentPage--"
        @next-page="currentPage++"
        @go-to-page="handleGoToPage"
        @page-size-change="handlePageSizeChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { algorithmApi } from '../../utils/api'
import { useNotification } from '../../composables/useNotification'
import ColumnFilter from './ColumnFilter.vue'
import PaginationComponent from '../common/PaginationComponent.vue'

const { warning, error } = useNotification()

interface Mapping {
  id?: number
  source?: 'case' | 'case_config' | 'reference' | 'device' | 'api'
  source_param: string
  param_name?: string
  dimension_id?: number | null
  dimension_name?: string
  target_param: string
  transform_type: 'none' | 'uppercase' | 'lowercase' | 'json_parse' | 'rttm_to_obj' | 'stm_to_obj'
}

interface Props {
  mappings: Mapping[]
  componentType: string
  algorithmType?: string
  caseParams?: any[]
  referenceParams?: any[]
  deviceParams?: any[]
  apiParams?: any[]
  mainDimensions?: any[]
}

const props = withDefaults(defineProps<Props>(), {
  mappings: () => [],
  componentType: '',
  algorithmType: '',
  caseParams: () => [],
  referenceParams: () => [],
  deviceParams: () => [],
  apiParams: () => [],
  mainDimensions: () => []
})

const emit = defineEmits<{
  (e: 'update', mappings: Mapping[]): void
}>()

const availableDimensions = ref<any[]>([])
const dimensionParamsMap = ref<Record<number, any[]>>({})
const loadingDimensionParams = ref<Record<number, boolean>>({})

// 搜索与过滤状态（顶部工具栏 + 列头过滤共用）
const filters = reactive({
  keyword: '',
  source: 'all',
  source_param: 'all',
  dimension_id: 'all',
  target_param: 'all',
  transform_type: 'all'
})

// 视图模式：平铺视图 / 评估维度视图（仅评估映射可用）
const viewMode = ref<'flat' | 'dimension'>('dimension')
// 分页状态
const currentPage = ref(1)
const pageSize = ref(10)

const colspanCount = computed(() => (props.componentType === 'evaluation' ? 7 : 6))

// 过滤后的映射列表（全量，用于分页总条数）
const filteredMappings = computed(() => {
  let list = props.mappings
  const kw = filters.keyword.trim().toLowerCase()
  if (kw) {
    list = list.filter(m =>
      (m.source_param || '').toLowerCase().includes(kw) ||
      (m.param_name || '').toLowerCase().includes(kw) ||
      (m.target_param || '').toLowerCase().includes(kw) ||
      (getDimensionName(m.dimension_id || 0) || '').toLowerCase().includes(kw)
    )
  }
  if (filters.source !== 'all') {
    list = list.filter(m => m.source === filters.source)
  }
  if (filters.source_param !== 'all') {
    const spKw = String(filters.source_param).toLowerCase()
    list = list.filter(m => (m.source_param || '').toLowerCase().includes(spKw))
  }
  if (filters.dimension_id !== 'all') {
    const targetId = Number(filters.dimension_id)
    list = list.filter(m => m.dimension_id === targetId)
  }
  if (filters.target_param !== 'all') {
    const tpKw = String(filters.target_param).toLowerCase()
    list = list.filter(m => (m.target_param || '').toLowerCase().includes(tpKw))
  }
  if (filters.transform_type !== 'all') {
    list = list.filter(m => m.transform_type === filters.transform_type)
  }
  return list
})

// 当前页的映射（平铺视图分页切片）
const paginatedMappings = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredMappings.value.slice(start, start + pageSize.value)
})

// 实际渲染行：平铺视图直接分页切片；评估维度视图按评估维度分组并在组首插入分组头
const displayRows = computed(() => {
  const rows: any[] = []
  if (viewMode.value === 'dimension' && props.componentType === 'evaluation') {
    const groups = new Map<string, any[]>()
    for (const m of filteredMappings.value) {
      const key = m.dimension_id == null ? '__none__' : String(m.dimension_id)
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(m)
    }
    const ordered = Array.from(groups.entries()).sort((a, b) => {
      const nameA = dimensionNameForGroup(a[0])
      const nameB = dimensionNameForGroup(b[0])
      return nameA.localeCompare(nameB)
    })
    for (const [key, mappings] of ordered) {
      rows.push({
        __isGroupHeader: true,
        __dimensionKey: key,
        __dimensionId: key === '__none__' ? null : Number(key),
        __dimensionName: dimensionNameForGroup(key),
        __count: mappings.length
      })
      rows.push(...mappings)
      // 分组末尾追加整行"添加映射"按钮
      rows.push({
        __isGroupFooter: true,
        __dimensionKey: key,
        __dimensionId: key === '__none__' ? null : Number(key)
      })
    }
    return rows
  }
  return paginatedMappings.value
})

function dimensionNameForGroup(key: string): string {
  if (key === '__none__') return '未指定维度'
  const dim = availableDimensions.value.find(d => d.id === Number(key))
  return dim?.name || `维度(${key})`
}

function handleGoToPage(page: number) {
  currentPage.value = page
}

function handlePageSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
}

function switchViewMode(mode: 'flat' | 'dimension') {
  viewMode.value = mode
  currentPage.value = 1
}

// 过滤条件/映射数据变化时回到第一页
watch(() => [filters.keyword, filters.source, filters.source_param, filters.dimension_id, filters.target_param, filters.transform_type], () => {
  currentPage.value = 1
})
watch(() => props.mappings, () => {
  currentPage.value = 1
})

// 列头过滤下拉的可选值
const sourceOptions = [
  { value: 'case', label: '用例参数' },
  { value: 'case_config', label: '用例配置' },
  { value: 'reference', label: '参考参数' },
  { value: 'device', label: '设备输出' },
  { value: 'api', label: 'API输出' }
]
const transformOptions = [
  { value: 'none', label: '无转换' },
  { value: 'uppercase', label: '转大写' },
  { value: 'lowercase', label: '转小写' },
  { value: 'json_parse', label: 'JSON解析' },
  { value: 'rttm_to_obj', label: 'RTTM转对象' },
  { value: 'stm_to_obj', label: 'STM转对象' }
]
const dimensionFilterOptions = computed(() =>
  (props.mainDimensions && props.mainDimensions.length > 0 ? props.mainDimensions : availableDimensions.value)
    .map(d => ({ value: String(d.id), label: d.name }))
)

// 列头下拉过滤选项：返回某列的非空去重取值
function distinctValues(list: any[], key: string): string[] {
  const set = new Set<string>()
  for (const item of list) {
    const v = item?.[key]
    if (v !== undefined && v !== null && String(v).trim() !== '') {
      set.add(String(v))
    }
  }
  return Array.from(set)
}

// 当前可用维度ID集合（用于回退显示已删除维度的映射）
const dimensionOptionIds = computed<Set<number>>(() => {
  const dims = props.mainDimensions && props.mainDimensions.length > 0
    ? props.mainDimensions
    : availableDimensions.value
  return new Set(dims.map((d: any) => Number(d.id)))
})

// 判断当前目标参数是否在维度参数列表中（不在则回退显示已存值）
function isTargetParamKnown(record: any): boolean {
  if (!record?.target_param) return false
  const options = getTargetParamOptions(record.dimension_id, record.target_param)
  return options.some((p: any) => p.code === record.target_param)
}

// 用例配置(config.rounds)可映射的结构性字段：评估时从 test_case.config.rounds 按轮读取
const CASE_CONFIG_FIELD_PRESETS = [
  { code: 'audios', name: '被播放音频' }
]

async function loadDimensions() {
  availableDimensions.value = []
  
  if (props.mainDimensions && props.mainDimensions.length > 0) {
    availableDimensions.value = props.mainDimensions
    return
  }
  
  if (props.componentType === 'evaluation' && props.algorithmType && typeof props.algorithmType === 'string') {
    try {
      const result = await algorithmApi.getDimensions(props.algorithmType)
      if (result && result.dimensions) {
        availableDimensions.value = result.dimensions || []
      }
    } catch (error) {
      console.error('加载评估维度失败:', error)
    }
  }
}

onMounted(() => {
  loadDimensions()
  // 编辑模式打开时，已有映射的 dimension_id 需要预加载参数列表，否则目标参数下拉框为空
  preloadDimensionParamsForMappings()
})

watch(() => props.algorithmType, () => {
  loadDimensions()
})

watch(() => props.mainDimensions, (newVal) => {
  if (newVal && newVal.length > 0) {
    availableDimensions.value = newVal
  }
}, { immediate: true })

// 当 mappings 变化时，对新出现的 dimension_id 预加载参数列表
watch(() => props.mappings, (newMappings) => {
  preloadDimensionParamsForMappings(newMappings)
}, { immediate: false, deep: false })

async function preloadDimensionParamsForMappings(list?: any[]) {
  const mappings = list || props.mappings || []
  const dimIds = new Set<number>()
  for (const m of mappings) {
    if (m.dimension_id && !dimensionParamsMap.value[m.dimension_id]) {
      dimIds.add(m.dimension_id)
    }
  }
  // 并行预加载所有未加载过的维度参数
  await Promise.all(Array.from(dimIds).map(id => loadDimensionParams(id)))
}

async function loadDimensionParams(dimensionId: number) {
  if (dimensionParamsMap.value[dimensionId] || loadingDimensionParams.value[dimensionId]) return
  loadingDimensionParams.value[dimensionId] = true
  try {
    const result = await algorithmApi.getDimensionParams(dimensionId)
    if (result && result.params) {
      dimensionParamsMap.value[dimensionId] = result.params || []
    }
  } catch (error) {
    console.error('加载维度参数失败:', error)
    dimensionParamsMap.value[dimensionId] = []
  } finally {
    loadingDimensionParams.value[dimensionId] = false
  }
}

function getSourceParams(source: string, currentParam?: string): any[] {
  let params: any[]
  switch (source) {
    case 'case': params = props.caseParams || []; break
    case 'case_config': params = [...CASE_CONFIG_FIELD_PRESETS]; break
    case 'reference': params = props.referenceParams || []; break
    case 'device': params = props.deviceParams || []; break
    case 'api': params = props.apiParams || []; break
    default: params = []
  }
  if (currentParam && !params.some(p => p.code === currentParam)) {
    params = [{ code: currentParam, name: currentParam }, ...params]
  }
  return params
}

function getAllSourceParams(): any[] {
  const allParams = [
    ...(props.caseParams || []),
    ...CASE_CONFIG_FIELD_PRESETS,
    ...(props.referenceParams || []),
    ...(props.deviceParams || []),
    ...(props.apiParams || [])
  ]
  const uniqueParams = new Map()
  allParams.forEach(param => {
    if (param.code) {
      uniqueParams.set(param.code, param)
    }
  })
  return Array.from(uniqueParams.values())
}

function getTargetParams(dimensionId: number | null): any[] {
  if (!dimensionId) return []
  const params = dimensionParamsMap.value[dimensionId]
  if (params && params.length > 0) {
    return params
  }
  return []
}

function getTargetParamOptions(dimensionId: number | null, currentTargetParam: string): any[] {
  const params = getTargetParams(dimensionId)
  if (params.length > 0) {
    return params
  }
  if (currentTargetParam) {
    return [{ code: currentTargetParam, name: currentTargetParam }]
  }
  return []
}

function getTargetParamListForDeviceApi(componentType: string, currentTargetParam: string): any[] {
  const params = componentType === 'device' ? (props.deviceParams || []) : (props.apiParams || [])
  if (currentTargetParam && !params.some(p => p.code === currentTargetParam)) {
    return [{ code: currentTargetParam, name: currentTargetParam }, ...params]
  }
  return params
}

function getParamName(code: string, source?: string, fallbackName?: string): string {
  if (!code) return '-'
  const allParams = getAllSourceParams()
  const param = allParams.find(p => p.code === code)
  return param?.name || fallbackName || code
}

function getTargetParamName(code: string, componentType: string): string {
  if (!code) return '-'
  const params = componentType === 'device' ? props.deviceParams : props.apiParams
  const param = params?.find(p => p.code === code)
  return param?.name || code
}

function getDimensionName(id: number): string {
  if (!id) return ''
  const dim = availableDimensions.value.find(d => d.id === id)
  return dim?.name || ''
}

function handleSourceTypeChange(record: any) {
  const index = props.mappings.indexOf(record)
  if (record) {
    record.source_param = ''
    record.param_name = ''
    if (record.source === 'case' || record.source === 'case_config') {
      record.dimension_id = null
      record.dimension_name = ''
    }
    emit('update', [...props.mappings])
    autoSaveMapping(record, index)
  }
}

function handleSourceChange(record: any) {
  const index = props.mappings.indexOf(record)
  if (record) {
    record.param_name = getParamName(record.source_param, record.source)
    emit('update', [...props.mappings])
    if (!checkDuplicateMapping(index)) return
    autoSaveMapping(record, index)
  }
}

function handleDimensionChange(record: any) {
  const index = props.mappings.indexOf(record)
  if (record) {
    record.dimension_name = getDimensionName(record.dimension_id || 0)
    record.target_param = ''
    if (record.dimension_id) {
      loadDimensionParams(record.dimension_id)
    }
    emit('update', [...props.mappings])
    if (!checkDuplicateMapping(index)) return
    autoSaveMapping(record, index)
  }
}

// 与后端唯一约束对齐的判重：同一 (source, source_param, dimension_id) 视为重复
function effectiveSource(record: Mapping): string | null {
  if (props.componentType === 'evaluation') return record.source || null
  return props.componentType || null
}

function findDuplicateMapping(index: number): Mapping | null {
  const record = props.mappings[index]
  const src = effectiveSource(record)
  if (!src || !record.source_param) return null
  const dimKey = record.dimension_id ?? null
  for (let i = 0; i < props.mappings.length; i++) {
    if (i === index) continue
    const other = props.mappings[i]
    if (!other) continue
    if (effectiveSource(other) !== src) continue
    if (other.source_param !== record.source_param) continue
    if ((other.dimension_id ?? null) !== dimKey) continue
    return other
  }
  return null
}

function checkDuplicateMapping(index: number): boolean {
  const dup = findDuplicateMapping(index)
  if (dup) {
    const dim = dup.dimension_id
      ? `，维度=${dup.dimension_name || dup.dimension_id}`
      : ''
    warning(`映射已存在：来源=${effectiveSource(dup) || '-'}，源参数=${dup.source_param}${dim}，同一来源+源参数+维度不允许重复`)
    return false
  }
  return true
}

function handleTargetChange(record: any) {
  const index = props.mappings.indexOf(record)
  if (record) {
    // 重复时不清空选择，仅提示并阻止入库，让用户保留已选项去修改来源/维度
    if (!checkDuplicateMapping(index)) return
    emit('update', [...props.mappings])
    autoSaveMapping(record, index)
  }
}

function handleTransformChange(record: any) {
  const index = props.mappings.indexOf(record)
  if (record) {
    emit('update', [...props.mappings])
    autoSaveMapping(record, index)
  }
}

async function autoSaveMapping(record: any, index: number) {
  if (!props.algorithmType) return

  const source = effectiveSource(record) || ''

  const mappingData = {
    algorithm_type: props.algorithmType,
    source_type: source,
    source: source,
    source_param: record.source_param,
    source_direction: record.source_direction || 'output',
    dimension_id: record.dimension_id,
    target_param: record.target_param,
    transform_type: record.transform_type || 'none'
  }

  // source 必须是合法值（case/case_config/reference/device/api），为空时不保存
  if (!source || !mappingData.source_param || !mappingData.target_param) {
    return
  }

  // 入库前防御性校验：同一 (source, source_param, dimension_id) 禁止重复
  if (!checkDuplicateMapping(index)) {
    return
  }

  try {
    if (record.id) {
      await algorithmApi.updateMapping(record.id, mappingData)
    } else {
      const result = await algorithmApi.createMapping(mappingData)
      record.id = result.id
    }
  } catch (saveError) {
    console.error('自动保存映射失败:', saveError)
    error(`自动保存映射失败: ${saveError?.message || saveError}`)
  }
}

function handleAdd(dimensionId?: number | null) {
  const tempId = `temp_mapping_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
  const newMapping: Mapping = props.componentType === 'evaluation' ? {
    tempId,
    source: 'case',
    source_param: '',
    param_name: '',
    dimension_id: dimensionId ?? null,
    dimension_name: dimensionId ? getDimensionName(dimensionId) : '',
    target_param: '',
    transform_type: 'none'
  } : {
    tempId,
    source_param: '',
    param_name: '',
    target_param: '',
    transform_type: 'none'
  }
  emit('update', [...props.mappings, newMapping])
}

function handleRemove(record: any) {
  const index = props.mappings.indexOf(record)
  if (index < 0) return
  const mapping = props.mappings[index]
  const newMappings = [...props.mappings]
  newMappings.splice(index, 1)
  emit('update', newMappings)
  
  if (mapping?.id) {
    algorithmApi.deleteMapping(mapping.id).catch(err => console.error('删除映射失败:', err))
  }
}
</script>

<style scoped>
.mapping-editor { width: 100%; }
.mapping-toolbar { margin-bottom: var(--spacing-sm); }
.mapping-toolbar-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

/* 视图模式切换（平铺/评估维度） */
.view-mode-tabs {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-full);
  padding: 3px;
  background: var(--background-secondary);
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.04);
}
.view-mode-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  border: none;
  background: transparent;
  border-radius: var(--border-radius-full);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}
.view-mode-tab .view-mode-icon {
  font-size: 12px;
}
.view-mode-tab:hover {
  color: var(--primary-color);
  background: rgba(99, 102, 241, 0.08);
}
.view-mode-tab.active {
  background: var(--primary-gradient, linear-gradient(135deg, #6366f1, #8b5cf6));
  color: #fff;
  box-shadow: 0 2px 6px rgba(99, 102, 241, 0.35);
}

/* 评估维度分组头行 */
.dimension-group-header-row td {
  background: var(--primary-light) !important;
  font-weight: var(--font-weight-medium);
  color: var(--primary-color);
  padding: 6px 12px;
}
.dimension-group-icon {
  margin-right: 6px;
  font-size: 12px;
}
.dimension-group-name {
  font-size: var(--font-size-sm);
}
.dimension-group-count {
  margin-left: 8px;
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
}

/* 分组末尾整行添加按钮 */
.dimension-group-add-row td {
  background: var(--background-secondary) !important;
  color: var(--text-secondary);
  border-top: 1px dashed var(--border-color);
}
.dimension-group-add-row:hover td {
  background: var(--primary-light) !important;
  color: var(--primary-color);
}
.dimension-group-add-row .add-row-icon {
  background: var(--primary-light);
  color: var(--primary-color);
}
.dimension-group-add-row:hover .add-row-icon {
  background: var(--primary-gradient, linear-gradient(135deg, #6366f1, #8b5cf6));
  color: #fff;
}

.mapping-pagination {
  margin-top: var(--spacing-sm);
}

.mapping-toolbar-actions .search-box {
  width: 220px;
  height: 32px;
  margin-bottom: 0;
}
.mapping-toolbar-actions .search-box .search-input {
  width: 220px;
  height: 32px;
}
.mapping-toolbar-actions .btn-sm:not(.btn-text):not(.btn-icon-only) {
  height: 32px !important;
  min-height: 32px !important;
  padding: 0 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  box-sizing: border-box;
}
.mapping-filter-select {
  width: auto;
  min-width: 96px;
  height: 32px;
  box-sizing: border-box;
}

.table-container { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: var(--font-size-sm); }
.data-table th, .data-table td { padding: var(--spacing-sm); text-align: left; border-bottom: 1px solid var(--border-color); }
.data-table th { background: var(--background-secondary); font-weight: var(--font-weight-medium); color: var(--text-secondary); }
.data-table tbody tr:hover { background: var(--background-hover); }
.empty-row { text-align: center; color: var(--text-muted); padding: var(--spacing-lg); }
.param-name-cell { color: var(--text-secondary); font-size: var(--font-size-sm); }

/* 表格底部"添加"行：整行可点击 */
.add-row {
  cursor: pointer;
}

.add-row:hover {
  transform: none !important;
}

.add-row td {
  display: table-cell !important;
  min-width: 0 !important;
  padding: 10px 12px !important;
  border-bottom: none !important;
  background: transparent;
  text-align: center;
  transition: background var(--transition-normal);
}

.add-row:hover td {
  background: var(--primary-light);
}

.add-row:active td {
  background: var(--primary-light);
}

.add-row-content {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  transition: color var(--transition-normal);
}

.add-row-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: var(--border-radius-full);
  background: var(--primary-light);
  color: var(--primary-color);
  font-size: 11px;
  transition: all var(--transition-normal);
}

.add-row:hover .add-row-content {
  color: var(--primary-color);
}

.add-row:hover .add-row-icon {
  background: var(--primary-gradient);
  color: #fff;
}
.form-input-sm { width: 100%; padding: var(--spacing-xs) var(--spacing-sm); font-size: var(--font-size-sm); height: 32px; border: 1px solid var(--border-color); border-radius: var(--border-radius-sm); background: var(--white-color); color: var(--text-primary); transition: all var(--transition-fast); }
.form-input-sm:focus { outline: none; border-color: var(--primary-color); box-shadow: 0 0 0 2px var(--primary-light); }
.form-input-sm::placeholder { color: var(--text-muted); }
.btn-danger { color: var(--danger-color); }
.btn-danger:hover { background: var(--danger-light); color: var(--danger-color); }
</style>
