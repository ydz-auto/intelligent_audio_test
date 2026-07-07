<template>
  <div class="algorithm-selector">
    <div class="options-grid">
      <div class="option-item full-width">
        <label>关联算法 <span class="hint" v-if="!props.single">(可多选)</span></label>
        <div class="algorithm-multi-select" ref="dropdownRef">
          <div class="select-header" @click="toggleDropdown">
            <div class="selected-tags" v-if="selectedAlgorithms.length > 0">
              <span 
                v-for="algo in selectedAlgorithms" 
                :key="algo.algorithmType" 
                class="algo-tag"
                :class="{ 'is-primary': algo.isPrimary && !props.single }"
              >
                <span class="algo-name">{{ getAlgorithmName(algo.algorithmType) }}</span>
                <span v-if="algo.isPrimary && !props.single" class="primary-badge">主</span>
                <i class="fas fa-times" @click.stop="removeAlgorithm(algo.algorithmType)"></i>
              </span>
            </div>
            <span v-else class="placeholder">请选择算法</span>
            <i class="fas fa-chevron-down dropdown-icon" :class="{ 'rotated': showDropdown }"></i>
          </div>
          <Teleport to="body">
            <div class="dropdown-menu" v-if="showDropdown" ref="dropdownMenuRef" :style="dropdownMenuStyle">
              <div class="dropdown-search">
                <input 
                  type="text" 
                  v-model="searchQuery" 
                  placeholder="搜索算法..."
                  class="search-input"
                  @click.stop
                >
              </div>
              <div class="dropdown-list">
                <template v-if="filteredGroups.length > 0">
                  <template v-for="group in filteredGroups" :key="group.name">
                    <div class="group-header" v-if="group.algorithms.length > 0">
                      <span class="group-name">{{ group.name }}</span>
                      <span class="group-count">{{ group.algorithms.length }}</span>
                    </div>
                    <div 
                      v-for="opt in group.algorithms" 
                      :key="opt.value" 
                      class="dropdown-item"
                      :class="{ selected: isAlgorithmSelected(opt.value) }"
                      @click="toggleAlgorithm(opt.value)"
                    >
                      <div class="item-checkbox">
                        <i :class="props.single ? (isAlgorithmSelected(opt.value) ? 'fas fa-check-circle' : 'far fa-circle') : (isAlgorithmSelected(opt.value) ? 'fas fa-check-square' : 'far fa-square')"></i>
                      </div>
                      <span class="item-name">{{ opt.name }}</span>
                      <button 
                        v-if="isAlgorithmSelected(opt.value) && !props.single" 
                        class="set-primary-btn"
                        :class="{ primary: isPrimaryAlgorithm(opt.value) }"
                        @click.stop="setPrimaryAlgorithm(opt.value)"
                      >
                        {{ isPrimaryAlgorithm(opt.value) ? '主算法' : '设为主' }}
                      </button>
                    </div>
                  </template>
                </template>
                <div v-else class="dropdown-empty">
                  未找到匹配的算法
                </div>
              </div>
            </div>
          </Teleport>
        </div>
      </div>
    </div>
    
    <div v-if="primaryAlgorithmType && algorithmFormSchema && props.showParams" class="algorithm-params-section">
      <h4 class="section-title">算法参数配置 <span class="algo-type-hint">({{ getAlgorithmName(primaryAlgorithmType) }})</span></h4>
      <DynamicForm
        v-if="algorithmFormSchema.fields && algorithmFormSchema.fields.length > 0"
        ref="dynamicFormRef"
        :schema="algorithmFormSchema"
        :initial-values="algorithmParams"
        :show-group-header="true"
        :default-expanded-groups="['basic', 'model']"
        @field-change="onFieldChange"
      />
      <div v-else class="empty-state">
        <p>该算法暂无参数配置</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed, onUnmounted, nextTick } from 'vue'
import DynamicForm from '../algorithm/DynamicForm.vue'
import { useAlgorithmConfig } from '../../composables/useAlgorithmConfig'
import { algorithmApi } from '../../utils/api'

interface AlgorithmOption {
  value: string
  name: string
  group_id?: number
  group_name?: string
}

interface AlgorithmRelation {
  algorithmType: string
  isPrimary: boolean
  weight: number
  params?: Record<string, any>
}

interface Props {
  modelValue?: string
  algorithmRelations?: AlgorithmRelation[]
  initialParams?: Record<string, any>
  showParams?: boolean
  single?: boolean
}

interface Emits {
  (e: 'update:modelValue', value: string): void
  (e: 'update:algorithmRelations', value: AlgorithmRelation[]): void
  (e: 'paramsChange', params: Record<string, any>): void
  (e: 'algorithmTypeChange', value: string): void
  (e: 'dimensionsChange', dimensions: any[], dimensionIds: number[]): void
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  algorithmRelations: () => [],
  initialParams: () => ({}),
  showParams: true,
  single: false
})

const emit = defineEmits<Emits>()

const algorithmConfig = useAlgorithmConfig()
const getAlgorithmOptions = algorithmConfig.getAlgorithmOptions
const getFormSchema = algorithmConfig.getFormSchema
const getAssociatedDimensions = algorithmConfig.getAssociatedDimensions
const getCaseAlgorithmParams = algorithmConfig.getCaseAlgorithmParams
const caseAlgorithmParamsDef = ref<any[]>([])

interface AlgorithmGroup {
  name: string
  algorithms: AlgorithmOption[]
}

const algorithmOptions = ref<AlgorithmOption[]>([])
const selectedAlgorithms = ref<AlgorithmRelation[]>([...props.algorithmRelations])
const algorithmFormSchema = ref<any>(null)
const algorithmParams = ref<Record<string, any>>({ ...props.initialParams })
const dynamicFormRef = ref<InstanceType<typeof DynamicForm> | null>(null)
const showDropdown = ref(false)
const searchQuery = ref('')
const dropdownRef = ref<HTMLElement | null>(null)
const dropdownMenuRef = ref<HTMLElement | null>(null)
const dropdownMenuStyle = ref<Record<string, string>>({})

function updateDropdownPosition() {
  if (!dropdownRef.value || !showDropdown.value) return
  const rect = dropdownRef.value.getBoundingClientRect()
  const viewportHeight = window.innerHeight
  const menuMaxHeight = 300
  const spaceBelow = viewportHeight - rect.bottom
  const spaceAbove = rect.top
  const openUpward = spaceBelow < menuMaxHeight && spaceAbove > spaceBelow
  dropdownMenuStyle.value = {
    position: 'fixed',
    left: `${rect.left}px`,
    width: `${rect.width}px`,
    zIndex: '14000',
    ...(openUpward
      ? { bottom: `${viewportHeight - rect.top + 4}px`, top: 'auto' }
      : { top: `${rect.bottom + 4}px`, bottom: 'auto' })
  }
}

function toggleDropdown() {
  showDropdown.value = !showDropdown.value
  if (showDropdown.value) {
    searchQuery.value = ''
    nextTick(() => updateDropdownPosition())
  }
}

const primaryAlgorithmType = computed(() => {
  const primary = selectedAlgorithms.value.find(a => a.isPrimary)
  return primary ? primary.algorithmType : selectedAlgorithms.value[0]?.algorithmType || ''
})

const filteredGroups = computed(() => {
  const groups: Map<string, AlgorithmGroup> = new Map()
  
  const filtered = searchQuery.value 
    ? algorithmOptions.value.filter(opt => 
        opt.name.toLowerCase().includes(searchQuery.value.toLowerCase()) || 
        opt.value.toLowerCase().includes(searchQuery.value.toLowerCase())
      )
    : algorithmOptions.value
  
  filtered.forEach(opt => {
    const groupName = opt.group_name || '其他算法'
    if (!groups.has(groupName)) {
      groups.set(groupName, { name: groupName, algorithms: [] })
    }
    groups.get(groupName)!.algorithms.push(opt)
  })
  
  return Array.from(groups.values())
})

function getAlgorithmName(type: string): string {
  const opt = algorithmOptions.value.find(o => o.value === type)
  return opt ? opt.name : type
}

function isAlgorithmSelected(type: string): boolean {
  return selectedAlgorithms.value.some(a => a.algorithmType === type)
}

function isPrimaryAlgorithm(type: string): boolean {
  const algo = selectedAlgorithms.value.find(a => a.algorithmType === type)
  return algo ? algo.isPrimary : false
}

function closeDropdown(event: MouseEvent) {
  const target = event.target as Node
  if (dropdownRef.value && !dropdownRef.value.contains(target) &&
      dropdownMenuRef.value && !dropdownMenuRef.value.contains(target)) {
    showDropdown.value = false
  }
}

function toggleAlgorithm(type: string) {
  if (props.single) {
    if (selectedAlgorithms.value.length === 1 && selectedAlgorithms.value[0].algorithmType === type) {
      selectedAlgorithms.value = []
    } else {
      selectedAlgorithms.value = [{
        algorithmType: type,
        isPrimary: true,
        weight: 1.0
      }]
    }
  } else {
    const index = selectedAlgorithms.value.findIndex(a => a.algorithmType === type)
    if (index >= 0) {
      selectedAlgorithms.value.splice(index, 1)
      if (selectedAlgorithms.value.length > 0 && !selectedAlgorithms.value.some(a => a.isPrimary)) {
        selectedAlgorithms.value[0].isPrimary = true
      }
    } else {
      const isFirst = selectedAlgorithms.value.length === 0
      selectedAlgorithms.value.push({
        algorithmType: type,
        isPrimary: isFirst,
        weight: 1.0
      })
    }
  }
  emitChanges()
}

function removeAlgorithm(type: string) {
  const index = selectedAlgorithms.value.findIndex(a => a.algorithmType === type)
  if (index >= 0) {
    const wasPrimary = selectedAlgorithms.value[index].isPrimary
    selectedAlgorithms.value.splice(index, 1)
    if (wasPrimary && selectedAlgorithms.value.length > 0) {
      selectedAlgorithms.value[0].isPrimary = true
    }
    emitChanges()
  }
}

function setPrimaryAlgorithm(type: string) {
  selectedAlgorithms.value.forEach(a => {
    a.isPrimary = a.algorithmType === type
  })
  emitChanges()
}

function emitChanges() {
  const primaryType = primaryAlgorithmType.value
  emit('update:modelValue', primaryType)
  emit('update:algorithmRelations', [...selectedAlgorithms.value])
  emit('algorithmTypeChange', primaryType)
  
  if (primaryType) {
    loadAlgorithmFormSchema(primaryType)
  } else {
    algorithmFormSchema.value = null
    emit('dimensionsChange', [], [])
  }
}

async function loadAlgorithmOptions() {
  try {
    const options = await getAlgorithmOptions()
    algorithmOptions.value = (options || []).map((opt: any) => ({
      value: opt.value,
      name: opt.name || opt.label || opt.value,
      group_id: opt.group_id,
      group_name: opt.group_name
    }))
  } catch (error) {
    console.error('加载算法选项失败:', error)
    algorithmOptions.value = []
  }
}

async function loadAlgorithmFormSchema(algorithmType: string) {
  if (!algorithmType) {
    algorithmFormSchema.value = null
    caseAlgorithmParamsDef.value = []
    if (Object.keys(algorithmParams.value).length === 0) {
      algorithmParams.value = {}
    }
    emit('dimensionsChange', [], [])
    return
  }

  const savedParams = { ...algorithmParams.value }

  try {
    const [schema, caseParamsDef] = await Promise.all([
      getFormSchema(algorithmType),
      getCaseAlgorithmParams(algorithmType)
    ])
    algorithmFormSchema.value = schema
    caseAlgorithmParamsDef.value = caseParamsDef

    const newParams: Record<string, any> = {}
    
    if (schema?.fields) {
      schema.fields.forEach((field: any) => {
        const fieldCode = field.fieldCode
        if (savedParams[fieldCode] !== undefined) {
          newParams[fieldCode] = savedParams[fieldCode]
        } else if (field.defaultValue !== undefined) {
          newParams[fieldCode] = field.defaultValue
        }
      })
      
      for (const [key, value] of Object.entries(savedParams)) {
        if (newParams[key] === undefined) {
          newParams[key] = value
        }
      }
    }
    
    algorithmParams.value = newParams
    emit('paramsChange', {
      ...algorithmParams.value,
      caseAlgorithmParams: caseAlgorithmParamsDef.value,
      algorithmFormSchema: schema
    })
  } catch (error) {
    console.error('加载算法表单Schema失败:', error)
    algorithmFormSchema.value = null
    caseAlgorithmParamsDef.value = []
  }

  try {
    const dimensionsData = await getAssociatedDimensions(algorithmType)
    if (dimensionsData) {
      const dimensions = dimensionsData.dimensions || []
      const dimensionIds = dimensionsData.dimension_ids || []
      emit('dimensionsChange', dimensions, dimensionIds)
    } else {
      emit('dimensionsChange', [], [])
    }
  } catch (error) {
    console.error('加载关联评估维度失败:', error)
    emit('dimensionsChange', [], [])
  }
}

function onFieldChange(field: string, value: any) {
  algorithmParams.value[field] = value
  emit('paramsChange', {
    ...algorithmParams.value,
    caseAlgorithmParams: caseAlgorithmParamsDef.value,
    algorithmFormSchema: algorithmFormSchema.value
  })
}

watch(() => props.modelValue, (newValue) => {
  if (newValue && !selectedAlgorithms.value.some(a => a.algorithmType === newValue)) {
    selectedAlgorithms.value = [{
      algorithmType: newValue,
      isPrimary: true,
      weight: 1.0
    }]
  }
  if (newValue) {
    loadAlgorithmFormSchema(newValue)
  }
})

watch(() => props.algorithmRelations, (newValue) => {
  if (newValue && newValue.length > 0) {
    selectedAlgorithms.value = [...newValue]
    const primary = newValue.find(a => a.isPrimary)
    if (primary) {
      loadAlgorithmFormSchema(primary.algorithmType)
    }
  }
}, { deep: true })

watch(() => props.initialParams, (newValue) => {
  if (newValue && Object.keys(newValue).length > 0) {
    algorithmParams.value = { ...newValue }
    if (primaryAlgorithmType.value) {
      loadAlgorithmFormSchema(primaryAlgorithmType.value)
    }
  }
}, { deep: true })

onMounted(async () => {
  document.addEventListener('click', closeDropdown)
  window.addEventListener('resize', updateDropdownPosition)
  window.addEventListener('scroll', updateDropdownPosition, true)
  await loadAlgorithmOptions()
  
  if (props.algorithmRelations && props.algorithmRelations.length > 0) {
    selectedAlgorithms.value = [...props.algorithmRelations]
    const primary = props.algorithmRelations.find(a => a.isPrimary)
    if (primary) {
      await loadAlgorithmFormSchema(primary.algorithmType)
    }
  } else if (props.modelValue) {
    selectedAlgorithms.value = [{
      algorithmType: props.modelValue,
      isPrimary: true,
      weight: 1.0
    }]
    await loadAlgorithmFormSchema(props.modelValue)
  }
})

onUnmounted(() => {
  document.removeEventListener('click', closeDropdown)
  window.removeEventListener('resize', updateDropdownPosition)
  window.removeEventListener('scroll', updateDropdownPosition, true)
})

defineExpose({
  algorithmParams,
  selectedAlgorithms,
  primaryAlgorithmType
})
</script>

<style scoped>
.algorithm-selector {
  margin: 16px 0;
}

.options-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 20px;
}

.option-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-item.full-width {
  grid-column: 1 / -1;
}

.option-item label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.option-item label .hint {
  font-weight: normal;
  color: var(--text-light);
  font-size: 12px;
}

.algorithm-multi-select {
  position: relative;
}

.select-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 42px;
  padding: 8px 12px;
  border: 2px solid var(--border-color);
  border-radius: var(--border-radius-md);
  background: var(--white-color);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.select-header:hover {
  border-color: var(--secondary-color);
}

.selected-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex: 1;
}

.algo-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: var(--secondary-light);
  color: var(--secondary-color);
  border-radius: var(--border-radius-sm);
  font-size: 12px;
  font-weight: 500;
}

.algo-tag.is-primary {
  background: var(--secondary-color);
  color: white;
}

.algo-tag .primary-badge {
  background: rgba(255, 255, 255, 0.3);
  padding: 0 4px;
  border-radius: 2px;
  font-size: 10px;
}

.algo-tag i {
  cursor: pointer;
  opacity: 0.7;
  transition: opacity var(--transition-fast);
}

.algo-tag i:hover {
  opacity: 1;
}

.placeholder {
  color: var(--text-disabled);
  font-size: 14px;
}

.dropdown-icon {
  color: var(--text-light);
  transition: transform var(--transition-fast);
  margin-left: 8px;
}

.dropdown-icon.rotated {
  transform: rotate(180deg);
}

.dropdown-menu {
  background: var(--white-color);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  box-shadow: var(--shadow-lg);
  max-height: 300px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.dropdown-search {
  padding: 8px;
  border-bottom: 1px solid var(--border-color);
}

.search-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
  font-size: 13px;
  outline: none;
}

.search-input:focus {
  border-color: var(--secondary-color);
}

.dropdown-list {
  overflow-y: auto;
  max-height: 240px;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px 4px;
  background: var(--background-secondary);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  position: sticky;
  top: 0;
  z-index: 1;
}

.group-name {
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.group-count {
  background: var(--border-color);
  color: var(--text-light);
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 11px;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.dropdown-item:hover {
  background: var(--background-secondary);
}

.dropdown-item.selected {
  background: var(--secondary-light);
}

.item-checkbox {
  color: var(--text-light);
  font-size: 16px;
}

.dropdown-item.selected .item-checkbox {
  color: var(--secondary-color);
}

.item-name {
  flex: 1;
  font-size: 14px;
  color: var(--text-primary);
}

.set-primary-btn {
  padding: 4px 8px;
  font-size: 11px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-sm);
  background: var(--white-color);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.set-primary-btn:hover {
  border-color: var(--secondary-color);
  color: var(--secondary-color);
}

.set-primary-btn.primary {
  background: var(--secondary-color);
  border-color: var(--secondary-color);
  color: white;
}

.dropdown-empty {
  padding: 20px;
  text-align: center;
  color: var(--text-light);
  font-size: 14px;
}

.algorithm-params-section {
  margin-top: 16px;
  padding: 12px;
  background: #f9f9f9;
  border-radius: 4px;
}

.section-title {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.algo-type-hint {
  font-weight: normal;
  color: var(--text-secondary);
  font-size: 12px;
}

.empty-state {
  padding: 20px;
  text-align: center;
  color: #999;
}
</style>
