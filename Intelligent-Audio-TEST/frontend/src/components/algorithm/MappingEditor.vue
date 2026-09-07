<template>
  <div class="mapping-editor">
    <div class="mapping-toolbar">
      <button class="btn btn-primary btn-sm" @click="handleAdd">
        <i class="fas fa-plus btn-icon"></i>添加映射
      </button>
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
            <td :colspan="componentType === 'evaluation' ? 7 : 6" class="empty-row">暂无映射</td>
          </tr>
          <tr v-else v-for="(record, index) in mappings" :key="record.id || `${record.source || ''}-${record.sourceParam}-${record.targetParam}`">
            <template v-if="componentType === 'evaluation'">
              <td>
                <select v-model="record.source" class="form-input form-input-sm" @blur="handleSourceTypeChange(index)">
                  <option value="case">用例参数</option>
                  <option value="reference">参考参数</option>
                  <option value="device">设备输出</option>
                  <option value="api">API输出</option>
                </select>
              </td>
              <td>
                <select v-model="record.sourceParam" class="form-input form-input-sm" @blur="handleSourceChange(index)">
                  <option value="">选择参数</option>
                  <option v-for="param in getSourceParams(record.source ?? 'case', record.sourceParam)" :key="param.code" :value="param.code">{{ param.code }}</option>
                </select>
              </td>
              <td class="param-name-cell">{{ getParamName(record.sourceParam, record.source) }}</td>
              <td>
                <select v-model="record.dimensionId" class="form-input form-input-sm" @blur="handleDimensionChange(index)">
                  <option :value="null">选择维度</option>
                  <option v-for="dim in (mainDimensions && mainDimensions.length > 0 ? mainDimensions : availableDimensions)" :key="dim.id" :value="dim.id">{{ dim.name }}</option>
                </select>
              </td>
              <td>
                <select v-model="record.targetParam" class="form-input form-input-sm" :disabled="!record.dimensionId" @blur="handleTargetChange(index)">
                  <option value="">{{ record.dimensionId ? '选择参数' : '先选维度' }}</option>
                  <option v-for="param in getTargetParamOptions(record.dimensionId ?? null, record.targetParam)" :key="param.code" :value="param.code">{{ param.code }} - {{ param.name }}</option>
                </select>
              </td>
              <td>
                <select v-model="record.transformType" class="form-input form-input-sm" @blur="handleTransformChange(index)">
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
                <select v-model="record.sourceParam" class="form-input form-input-sm" @blur="handleSourceChange(index)">
                  <option value="">选择参数</option>
                  <option v-for="param in getSourceParams('case', record.sourceParam)" :key="param.code" :value="param.code">{{ param.code }}</option>
                </select>
              </td>
              <td class="param-name-cell">{{ getParamName(record.sourceParam, 'case') }}</td>
              <td>
                <select v-model="record.targetParam" class="form-input form-input-sm" @blur="handleTargetChange(index)">
                  <option value="">选择参数</option>
                  <option v-for="param in getTargetParamListForDeviceApi(componentType, record.targetParam)" :key="param.code" :value="param.code">{{ param.code }}</option>
                </select>
              </td>
              <td class="param-name-cell">{{ getTargetParamName(record.targetParam, componentType) }}</td>
              <td>
                <select v-model="record.transformType" class="form-input form-input-sm" @blur="handleTransformChange(index)">
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
              <button class="btn btn-text btn-sm btn-danger" @click="handleRemove(index)">
                <i class="fas fa-trash btn-icon"></i>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { algorithmPort } from '../../composables/algorithm/algorithmPort'
import { useNotification } from '../../composables/modal/useNotification'

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
})

watch(() => props.algorithmType, () => {
  loadDimensions()
})

watch(() => props.mainDimensions, (newVal) => {
  if (newVal && newVal.length > 0) {
    availableDimensions.value = newVal
  }
}, { immediate: true })

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

function getParamName(code: string, source?: string): string {
  if (!code) return '-'
  const allParams = getAllSourceParams()
  const param = allParams.find(p => p.code === code)
  return param?.name || code
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

function handleSourceTypeChange(index: number) {
  const record = props.mappings[index]
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

function handleSourceChange(index: number) {
  const record = props.mappings[index]
  if (record) {
    record.paramName = getParamName(record.sourceParam, record.source)
    emit('update', [...props.mappings])
    autoSaveMapping(record, index)
  }
}

function handleDimensionChange(index: number) {
  const record = props.mappings[index]
  if (record) {
    record.dimensionName = getDimensionName(record.dimensionId || 0)
    record.targetParam = ''
    if (record.dimensionId) {
      loadDimensionParams(record.dimensionId)
    }
    emit('update', [...props.mappings])
    autoSaveMapping(record, index)
  }
}

function checkDuplicateTargetParam(index: number): boolean {
  const record = props.mappings[index]
  if (!record || !record.targetParam) return true

  // 全局按 targetParam 判重，不同维度也不允许同一目标参数代码被多源映射
  const targetKey = record.targetParam

  for (let i = 0; i < props.mappings.length; i++) {
    if (i === index) continue
    const other = props.mappings[i]
    if (!other || !other.targetParam) continue
    if (other.targetParam === targetKey) {
      warning(`目标参数"${record.targetParam}"已被其他映射占用，同一目标参数代码禁止被多源参数代码映射`)
      return false
    }
  }
  return true
}

function handleTargetChange(index: number) {
  const record = props.mappings[index]
  if (record) {
    if (!checkDuplicateTargetParam(index)) {
      // 清空冲突的目标参数，阻止入库
      record.targetParam = ''
      emit('update', [...props.mappings])
      return
    }
    emit('update', [...props.mappings])
    autoSaveMapping(record, index)
  }
}

function handleTransformChange(index: number) {
  const record = props.mappings[index]
  if (record) {
    emit('update', [...props.mappings])
    autoSaveMapping(record, index)
  }
}

async function autoSaveMapping(record: any, index: number) {
  if (!props.algorithmType) return

  // source 非空校验：防止脏数据入库
  if (!record.source) {
    return
  }

  // 提交 camelCase Domain 字段，algorithmPort 内部做 snake_case 转换
  const mappingData = {
    algorithmType: props.algorithmType,
    sourceType: record.source,
    source: record.source,
    sourceParam: record.sourceParam,
    sourceDirection: record.sourceDirection || 'output',
    dimensionId: record.dimensionId,
    targetParam: record.targetParam,
    transformType: record.transformType || 'none'
  }

  if (!mappingData.sourceParam || !mappingData.targetParam) {
    return
  }

  // 入库前防御性校验：同一目标参数代码禁止被多源参数代码映射
  if (!checkDuplicateTargetParam(index)) {
    error('保存已取消：目标参数代码重复，同一目标参数代码禁止被多源参数代码映射')
    return
  }

  try {
    if (record.id) {
      await algorithmPort.updateMapping(record.id, mappingData)
    } else {
      const result = await algorithmPort.createMapping(mappingData)
      record.id = result.id
    }
  } catch (error) {
    console.error('自动保存映射失败:', error)
  }
}

function handleAdd() {
  const tempId = `temp_mapping_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
  const newMapping: Mapping = props.componentType === 'evaluation' ? {
    tempId,
    source: 'case',
    sourceParam: '',
    paramName: '',
    dimensionId: null,
    dimensionName: '',
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

function handleRemove(index: number) {
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
.table-container { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: var(--font-size-sm); }
.data-table th, .data-table td { padding: var(--spacing-sm); text-align: left; border-bottom: 1px solid var(--border-color); }
.data-table th { background: var(--background-secondary); font-weight: var(--font-weight-medium); color: var(--text-secondary); }
.data-table tbody tr:hover { background: var(--background-hover); }
.empty-row { text-align: center; color: var(--text-muted); padding: var(--spacing-lg); }
.param-name-cell { color: var(--text-secondary); font-size: var(--font-size-sm); }
.form-input-sm { width: 100%; padding: var(--spacing-xs) var(--spacing-sm); font-size: var(--font-size-sm); height: 32px; border: 1px solid var(--border-color); border-radius: var(--border-radius-sm); background: var(--white-color); color: var(--text-primary); transition: all var(--transition-fast); }
.form-input-sm:focus { outline: none; border-color: var(--primary-color); box-shadow: 0 0 0 2px var(--primary-light); }
.form-input-sm::placeholder { color: var(--text-muted); }
.btn-danger { color: var(--danger-color); }
.btn-danger:hover { background: var(--danger-light); color: var(--danger-color); }
</style>
