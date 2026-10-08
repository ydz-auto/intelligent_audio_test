<template>
  <div class="mapping-editor">
    <div class="mapping-toolbar">
      <div class="mapping-toolbar-actions">
        <button class="btn btn-primary btn-sm" @click="handleAdd()">
          <i class="fas fa-plus btn-icon"></i>添加映射
        </button>
        <div v-if="componentType === 'evaluation'" class="view-mode-tabs">
          <button type="button" class="view-mode-tab" :class="{ active: viewMode === 'flat' }" @click="switchViewMode('flat')">
            <i class="fas fa-th-list view-mode-icon"></i>
            <span>平铺视图</span>
          </button>
          <button type="button" class="view-mode-tab" :class="{ active: viewMode === 'dimension' }" @click="switchViewMode('dimension')">
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
          <option value="reference">参考参数</option>
          <option value="device">设备输出</option>
          <option value="api">API输出</option>
        </select>
        <select class="form-input mapping-filter-select" v-model="filters.transformType">
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
              <th style="width: 100px;">来源</th>
              <th style="width: 120px;">源参数代码</th>
              <th style="width: 120px;">源参数名称</th>
              <th>目标评估维度</th>
              <th>目标参数</th>
              <th style="width: 100px;">转换</th>
            </template>
            <template v-else>
              <th style="width: 120px;">源参数代码</th>
              <th style="width: 120px;">源参数名称</th>
              <th style="width: 120px;">目标参数代码</th>
              <th style="width: 120px;">目标参数名称</th>
              <th style="width: 100px;">转换</th>
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
          <template v-else v-for="(record, index) in displayRows" :key="record.__isGroupHeader ? `group-${record.__dimensionKey}` : (record.__isGroupFooter ? `group-footer-${record.__dimensionKey}` : (record.id || `${record.source || ''}-${record.sourceParam}-${record.targetParam}-${record.dimensionId || ''}`))">
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
                    <option value="reference">参考参数</option>
                    <option value="device">设备输出</option>
                    <option value="api">API输出</option>
                  </select>
                </td>
                <td>
                  <select v-model="record.sourceParam" class="form-input form-input-sm" @blur="handleSourceChange(record)">
                    <option value="">选择参数</option>
                    <option v-for="param in getSourceParams(record.source ?? 'case', record.sourceParam)" :key="param.code" :value="param.code">{{ param.code }}</option>
                  </select>
                </td>
                <td class="param-name-cell">{{ getParamName(record.sourceParam, record.source, record.paramName) }}</td>
                <td>
                  <select v-model="record.dimensionId" class="form-input form-input-sm" @blur="handleDimensionChange(record)">
                    <option :value="null">选择维度</option>
                    <option v-if="record.dimensionId && !dimensionOptionIds.has(Number(record.dimensionId))" :value="record.dimensionId">
                      {{ record.dimensionName || `已删除维度(${record.dimensionId})` }}
                    </option>
                    <option v-for="dim in (mainDimensions && mainDimensions.length > 0 ? mainDimensions : availableDimensions)" :key="dim.id" :value="dim.id">{{ dim.name }}</option>
                  </select>
                </td>
                <td>
                  <select v-model="record.targetParam" class="form-input form-input-sm" :disabled="!record.dimensionId" @blur="handleTargetChange(record)">
                    <option value="">{{ record.dimensionId ? '选择参数' : '先选维度' }}</option>
                    <option v-if="record.targetParam && !isTargetParamKnown(record)" :value="record.targetParam">
                      {{ record.targetParam }} - {{ record.targetParamName || record.targetParam }}
                    </option>
                    <option v-for="param in getTargetParamOptions(record.dimensionId ?? null, record.targetParam)" :key="param.code" :value="param.code">{{ param.code }} - {{ param.name }}</option>
                  </select>
                </td>
                <td>
                  <select v-model="record.transformType" class="form-input form-input-sm" @blur="handleTransformChange(record)">
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
                  <select v-model="record.sourceParam" class="form-input form-input-sm" @blur="handleSourceChange(record)">
                    <option value="">选择参数</option>
                    <option v-for="param in getSourceParams('case', record.sourceParam)" :key="param.code" :value="param.code">{{ param.code }}</option>
                  </select>
                </td>
                <td class="param-name-cell">{{ getParamName(record.sourceParam, 'case', record.paramName) }}</td>
                <td>
                  <select v-model="record.targetParam" class="form-input form-input-sm" @blur="handleTargetChange(record)">
                    <option value="">选择参数</option>
                    <option v-for="param in getTargetParamListForDeviceApi(componentType, record.targetParam)" :key="param.code" :value="param.code">{{ param.code }}</option>
                  </select>
                </td>
                <td class="param-name-cell">{{ getTargetParamName(record.targetParam, componentType) }}</td>
                <td>
                  <select v-model="record.transformType" class="form-input form-input-sm" @blur="handleTransformChange(record)">
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
          <tr v-if="viewMode === 'flat'" class="add-row" @click="handleAdd()">
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

    <div class="mapping-pagination" v-if="viewMode === 'flat' && filteredMappings.length > pageSize">
      <PaginationComponent
        :current-page="currentPage"
        :page-size="pageSize"
        :total-items="filteredMappings.length"
        @prev-page="handlePrevPage"
        @next-page="handleNextPage"
        @go-to-page="handleGoToPage"
        @page-size-change="handlePageSizeChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { algorithmPort } from '../../composables/algorithm/algorithmPort'
import { useNotification } from '../../composables/modal/useNotification'
import PaginationComponent from '../common/data/PaginationComponent.vue'

const { warning, error } = useNotification()

interface Mapping {
  id?: number
  /** 前端新增行的临时 ID（未入库前供列表 :key 使用，不入后端） */
  tempId?: string
  source?: 'case' | 'reference' | 'device' | 'api'
  sourceParam: string
  paramName?: string
  dimensionId?: number | null
  dimensionName?: string
  targetParam: string
  targetParamName?: string
  transformType: 'none' | 'uppercase' | 'lowercase' | 'json_parse' | 'rttm_to_obj' | 'stm_to_obj'
  sourceDirection?: string
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

// 搜索与过滤状态（顶部工具栏）
const filters = reactive({
  keyword: '',
  source: 'all',
  sourceParam: 'all',
  dimensionId: 'all',
  targetParam: 'all',
  transformType: 'all'
})

// 视图模式：平铺视图 / 评估维度视图（仅评估映射可用），默认评估维度视图
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
      (m.sourceParam || '').toLowerCase().includes(kw) ||
      (m.paramName || '').toLowerCase().includes(kw) ||
      (m.targetParam || '').toLowerCase().includes(kw) ||
      (getDimensionName(m.dimensionId || 0) || '').toLowerCase().includes(kw)
    )
  }
  if (filters.source !== 'all') {
    list = list.filter(m => m.source === filters.source)
  }
  if (filters.sourceParam !== 'all') {
    const spKw = String(filters.sourceParam).toLowerCase()
    list = list.filter(m => (m.sourceParam || '').toLowerCase().includes(spKw))
  }
  if (filters.dimensionId !== 'all') {
    const targetId = Number(filters.dimensionId)
    list = list.filter(m => m.dimensionId === targetId)
  }
  if (filters.targetParam !== 'all') {
    const tpKw = String(filters.targetParam).toLowerCase()
    list = list.filter(m => (m.targetParam || '').toLowerCase().includes(tpKw))
  }
  if (filters.transformType !== 'all') {
    list = list.filter(m => m.transformType === filters.transformType)
  }
  return list
})

// 当前页的映射（平铺视图分页切片）
const paginatedMappings = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredMappings.value.slice(start, start + pageSize.value)
})

// 实际渲染行：平铺视图直接分页切片；评估维度视图按评估维度分组并在组首插入分组头、组尾插入添加行
const displayRows = computed(() => {
  const rows: any[] = []
  if (viewMode.value === 'dimension' && props.componentType === 'evaluation') {
    const groups = new Map<string, any[]>()
    for (const m of filteredMappings.value) {
      const key = m.dimensionId == null ? '__none__' : String(m.dimensionId)
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

function handlePrevPage() {
  if (currentPage.value > 1) currentPage.value--
}

function handleNextPage() {
  if (currentPage.value < Math.ceil(filteredMappings.value.length / pageSize.value)) currentPage.value++
}

function switchViewMode(mode: 'flat' | 'dimension') {
  viewMode.value = mode
  currentPage.value = 1
}

// 过滤条件/映射数据变化时回到第一页
watch(() => [filters.keyword, filters.source, filters.sourceParam, filters.dimensionId, filters.targetParam, filters.transformType], () => {
  currentPage.value = 1
})
watch(() => props.mappings, () => {
  currentPage.value = 1
})

// 当前可用维度ID集合（用于回退显示已删除维度的映射）
const dimensionOptionIds = computed<Set<number>>(() => {
  const dims = props.mainDimensions && props.mainDimensions.length > 0
    ? props.mainDimensions
    : availableDimensions.value
  return new Set(dims.map((d: any) => Number(d.id)))
})

// 判断当前目标参数是否在维度参数列表中（不在则回退显示已存值）
function isTargetParamKnown(record: any): boolean {
  if (!record?.targetParam) return false
  const options = getTargetParamOptions(record.dimensionId, record.targetParam)
  return options.some((p: any) => p.code === record.targetParam)
}

async function loadDimensions() {
  availableDimensions.value = []

  if (props.mainDimensions && props.mainDimensions.length > 0) {
    availableDimensions.value = props.mainDimensions
    return
  }

  if (props.componentType === 'evaluation' && props.algorithmType && typeof props.algorithmType === 'string') {
    try {
      const result = await algorithmPort.getDimensions(props.algorithmType)
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
  // 编辑模式打开时，已有映射的 dimensionId 需要预加载参数列表，否则目标参数下拉框为空
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

// 当 mappings 变化时，对新出现的 dimensionId 预加载参数列表
watch(() => props.mappings, (newMappings) => {
  preloadDimensionParamsForMappings(newMappings)
}, { immediate: false, deep: false })

async function preloadDimensionParamsForMappings(list?: any[]) {
  const mappings = list || props.mappings || []
  const dimIds = new Set<number>()
  for (const m of mappings) {
    if (m.dimensionId && !dimensionParamsMap.value[m.dimensionId]) {
      dimIds.add(m.dimensionId)
    }
  }
  // 并行预加载所有未加载过的维度参数
  await Promise.all(Array.from(dimIds).map(id => loadDimensionParams(id)))
}

async function loadDimensionParams(dimensionId: number) {
  if (dimensionParamsMap.value[dimensionId] || loadingDimensionParams.value[dimensionId]) return
  loadingDimensionParams.value[dimensionId] = true
  try {
    const result = await algorithmPort.getDimensionParams(dimensionId)
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
    record.sourceParam = ''
    record.paramName = ''
    if (record.source === 'case') {
      record.dimensionId = null
      record.dimensionName = ''
    }
    emit('update', [...props.mappings])
    autoSaveMapping(record, index)
  }
}

function handleSourceChange(record: any) {
  const index = props.mappings.indexOf(record)
  if (record) {
    record.paramName = getParamName(record.sourceParam, record.source)
    emit('update', [...props.mappings])
    if (!checkDuplicateMapping(index)) return
    autoSaveMapping(record, index)
  }
}

function handleDimensionChange(record: any) {
  const index = props.mappings.indexOf(record)
  if (record) {
    record.dimensionName = getDimensionName(record.dimensionId || 0)
    record.targetParam = ''
    if (record.dimensionId) {
      loadDimensionParams(record.dimensionId)
    }
    emit('update', [...props.mappings])
    if (!checkDuplicateMapping(index)) return
    autoSaveMapping(record, index)
  }
}

// 与后端唯一约束对齐的判重：同一 (source, sourceParam, dimensionId) 视为重复
function effectiveSource(record: Mapping): string | null {
  if (props.componentType === 'evaluation') return record.source || null
  return props.componentType || null
}

function findDuplicateMapping(index: number): Mapping | null {
  const record = props.mappings[index]
  const src = effectiveSource(record)
  if (!src || !record.sourceParam) return null
  const dimKey = record.dimensionId ?? null
  for (let i = 0; i < props.mappings.length; i++) {
    if (i === index) continue
    const other = props.mappings[i]
    if (!other) continue
    if (effectiveSource(other) !== src) continue
    if (other.sourceParam !== record.sourceParam) continue
    if ((other.dimensionId ?? null) !== dimKey) continue
    return other
  }
  return null
}

function checkDuplicateMapping(index: number): boolean {
  const dup = findDuplicateMapping(index)
  if (dup) {
    const dim = dup.dimensionId
      ? `，维度=${dup.dimensionName || dup.dimensionId}`
      : ''
    warning(`映射已存在：来源=${effectiveSource(dup) || '-'}，源参数=${dup.sourceParam}${dim}，同一来源+源参数+维度不允许重复`)
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

  // 提交 camelCase Domain 字段，algorithmPort 内部做 snake_case 转换
  const mappingData = {
    algorithmType: props.algorithmType,
    sourceType: source,
    source,
    sourceParam: record.sourceParam,
    sourceDirection: record.sourceDirection || 'output',
    dimensionId: record.dimensionId,
    targetParam: record.targetParam,
    transformType: record.transformType || 'none'
  }

  // source 必须是合法值（case/reference/device/api），为空时不保存
  if (!source || !mappingData.sourceParam || !mappingData.targetParam) {
    return
  }

  // 入库前防御性校验：同一 (source, sourceParam, dimensionId) 禁止重复
  if (!checkDuplicateMapping(index)) {
    return
  }

  try {
    if (record.id) {
      await algorithmPort.updateMapping(record.id, mappingData)
    } else {
      const result = await algorithmPort.createMapping(mappingData)
      record.id = result.id
    }
  } catch (saveError) {
    console.error('自动保存映射失败:', saveError)
    error(`自动保存映射失败: ${(saveError as any)?.message || saveError}`)
  }
}

function handleAdd(dimensionId?: number | null) {
  const tempId = `temp_mapping_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
  const newMapping: Mapping = props.componentType === 'evaluation' ? {
    tempId,
    source: 'case',
    sourceParam: '',
    paramName: '',
    dimensionId: dimensionId ?? null,
    dimensionName: dimensionId ? getDimensionName(dimensionId) : '',
    targetParam: '',
    transformType: 'none'
  } : {
    tempId,
    sourceParam: '',
    paramName: '',
    targetParam: '',
    transformType: 'none'
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
    algorithmPort.deleteMapping(mapping.id).catch(err => console.error('删除映射失败:', err))
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
