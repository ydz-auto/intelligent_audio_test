<template>
  <div class="algorithm-select">
    <div class="select-trigger" @click="toggleDropdown" :class="{ disabled, focused: isFocused }">
      <div class="select-values">
        <template v-if="multiple">
          <span v-for="value in selectedValues" :key="value" class="selected-tag">
            {{ getAlgorithmName(value) }}
            <button type="button" class="tag-close" @click.stop="removeValue(value)" v-if="!disabled">
              <i class="fas fa-times"></i>
            </button>
          </span>
          <span v-if="selectedValues.length === 0" class="placeholder">{{ placeholder }}</span>
        </template>
        <template v-else>
          <span v-if="modelValue" class="single-value">
            {{ getAlgorithmName(modelValue as string) }}
            <span v-if="showStatus" class="status-badge" :class="getSelectedStatus()">
              {{ getSelectedStatus() === 'online' ? '在线' : '离线' }}
            </span>
          </span>
          <span v-else class="placeholder">{{ placeholder }}</span>
        </template>
      </div>
      <div class="select-arrow">
        <i class="fas fa-chevron-down" :class="{ 'fa-chevron-up': isOpen }"></i>
      </div>
    </div>

    <div class="select-dropdown" v-show="isOpen" @click.stop>
      <div class="search-box" v-if="filterable">
        <i class="fas fa-search search-icon"></i>
        <input
          type="text"
          class="search-input"
          :placeholder="searchPlaceholder"
          v-model="searchQuery"
          @keydown.stop
        >
      </div>

      <div class="options-container">
        <template v-for="(algorithms, groupName) in filteredGroupedAlgorithms" :key="groupName">
          <div class="option-group">
            <div class="group-label">{{ getCategoryLabel(groupName) }}</div>
            <div
              v-for="algo in algorithms"
              :key="algo.type"
              class="option-item"
              :class="{
                selected: isSelected(algo.type),
                disabled: algo.status === 'offline'
              }"
              @click="handleSelect(algo)"
            >
              <div class="option-content">
                <span class="option-name">{{ algo.name }}</span>
                <span v-if="showStatus" class="status-tag" :class="algo.status">
                  {{ algo.status === 'online' ? '在线' : '离线' }}
                </span>
              </div>
              <i v-if="isSelected(algo.type)" class="fas fa-check check-icon"></i>
            </div>
          </div>
        </template>

        <div v-if="Object.keys(filteredGroupedAlgorithms).length === 0" class="empty-state">
          <i class="fas fa-search"></i>
          <span>无匹配结果</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { algorithmApi } from '../../utils/api'

interface Algorithm {
  type: string
  name: string
  group_id?: number
  group_name?: string
  status: 'online' | 'offline'
  description?: string
  icon?: string
}

interface Props {
  modelValue?: string | string[]
  placeholder?: string
  disabled?: boolean
  multiple?: boolean
  showStatus?: boolean
  clearable?: boolean
  filterable?: boolean
  searchPlaceholder?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  placeholder: '请选择算法类型',
  disabled: false,
  multiple: false,
  showStatus: true,
  clearable: true,
  filterable: true,
  searchPlaceholder: '搜索算法...'
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | string[]): void
  (e: 'change', algorithm: Algorithm | Algorithm[] | null): void
}>()

const isOpen = ref(false)
const isFocused = ref(false)
const searchQuery = ref('')
const algorithms = ref<Algorithm[]>([])

const selectedValues = computed(() => {
  if (props.multiple && Array.isArray(props.modelValue)) {
    return props.modelValue as string[]
  }
  return []
})

const filteredGroupedAlgorithms = computed(() => {
  const groups: Record<string, Algorithm[]> = {}

  let filteredList = algorithms.value

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filteredList = filteredList.filter(a =>
      a.name.toLowerCase().includes(query) ||
      a.type.toLowerCase().includes(query)
    )
  }

  for (const algo of filteredList) {
    const groupKey = algo.group_name || '未分组'
    if (!groups[groupKey]) {
      groups[groupKey] = []
    }
    groups[groupKey].push(algo)
  }

  return groups
})

const getCategoryLabel = (groupName: string) => {
  return groupName || '未分组'
}

const getAlgorithmName = (type: string): string => {
  const algo = algorithms.value.find(a => a.type === type)
  return algo?.name || type
}

const getSelectedStatus = (): string => {
  if (!props.modelValue || props.multiple) return ''
  const algo = algorithms.value.find(a => a.type === props.modelValue)
  return algo?.status || ''
}

const isSelected = (type: string): boolean => {
  if (props.multiple && Array.isArray(props.modelValue)) {
    return (props.modelValue as string[]).includes(type)
  }
  return props.modelValue === type
}

const handleSelect = (algo: Algorithm) => {
  if (algo.status === 'offline') return

  if (props.multiple) {
    const currentValues = Array.isArray(props.modelValue) ? [...props.modelValue] as string[] : []
    const index = currentValues.indexOf(algo.type)

    if (index > -1) {
      currentValues.splice(index, 1)
    } else {
      currentValues.push(algo.type)
    }

    emit('update:modelValue', currentValues)
    const selectedAlgorithms = algorithms.value.filter(a => currentValues.includes(a.type))
    emit('change', selectedAlgorithms)
  } else {
    emit('update:modelValue', algo.type)
    emit('change', algo)
    isOpen.value = false
  }
}

const removeValue = (type: string) => {
  if (!props.multiple || !Array.isArray(props.modelValue)) return

  const currentValues = [...props.modelValue] as string[]
  const index = currentValues.indexOf(type)

  if (index > -1) {
    currentValues.splice(index, 1)
    emit('update:modelValue', currentValues)
    const selectedAlgorithms = algorithms.value.filter(a => currentValues.includes(a.type))
    emit('change', selectedAlgorithms)
  }
}

const toggleDropdown = () => {
  if (props.disabled) return
  isOpen.value = !isOpen.value
  if (isOpen.value) {
    isFocused.value = true
  }
}

const loadAlgorithms = async () => {
  try {
    const result = await algorithmApi.getDefinitions()
    // 响应经层转为 camelCase，补回 snake_case 别名供分组/读取使用
    algorithms.value = (result.data || []).map((a: any) => ({
      ...a,
      group_id: a.groupId ?? a.group_id,
      group_name: a.groupName ?? a.group_name,
    }))
  } catch (error) {
    console.error('加载算法列表失败:', error)
  }
}

const refresh = async () => {
  await loadAlgorithms()
}

const clear = () => {
  emit('update:modelValue', props.multiple ? [] : '')
  emit('change', null)
}

const getSelectedAlgorithm = (): Algorithm | Algorithm[] | null => {
  if (!props.modelValue) return null

  if (props.multiple && Array.isArray(props.modelValue)) {
    return algorithms.value.filter(a => (props.modelValue as string[]).includes(a.type))
  }
  return algorithms.value.find(a => a.type === props.modelValue) || null
}

const handleClickOutside = (event: MouseEvent) => {
  const target = event.target as HTMLElement
  if (!target.closest('.algorithm-select')) {
    isOpen.value = false
    isFocused.value = false
  }
}

onMounted(() => {
  loadAlgorithms()
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})

defineExpose({
  refresh,
  clear,
  getSelectedAlgorithm
})
</script>

<style scoped>
.algorithm-select {
  position: relative;
  width: 100%;
}

.select-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 6px 12px;
  background-color: #ffffff;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.select-trigger:hover {
  border-color: #FF6A00;
}

.select-trigger.focused {
  border-color: #FF6A00;
  box-shadow: 0 0 0 3px rgba(255, 106, 0, 0.1);
}

.select-trigger.disabled {
  background-color: #F3F4F6;
  cursor: not-allowed;
  opacity: 0.6;
}

.select-values {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.selected-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background-color: #FFF3E6;
  color: #FF6A00;
  border-radius: 4px;
  font-size: 13px;
}

.tag-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  padding: 0;
  border: none;
  background: none;
  color: #FF6A00;
  cursor: pointer;
  border-radius: 50%;
  transition: background-color 0.2s;
}

.tag-close:hover {
  background-color: #FFE0CC;
}

.single-value {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.status-badge {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.status-badge.online {
  background-color: #D1FAE5;
  color: #059669;
}

.status-badge.offline {
  background-color: #FEE2E2;
  color: #DC2626;
}

.placeholder {
  color: #9CA3AF;
}

.select-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  color: #9CA3AF;
  transition: transform 0.2s;
}

.select-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: 4px;
  background-color: #ffffff;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  max-height: 300px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.search-box {
  position: relative;
  padding: 8px;
  border-bottom: 1px solid #E5E7EB;
}

.search-icon {
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  color: #9CA3AF;
  font-size: 12px;
}

.search-input {
  width: 100%;
  height: 32px;
  padding: 0 12px 0 32px;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}

.search-input:focus {
  border-color: #FF6A00;
}

.options-container {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.option-group {
  margin-bottom: 8px;
}

.option-group:last-child {
  margin-bottom: 0;
}

.group-label {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #6B7280;
  background-color: #F9FAFB;
}

.option-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.option-item:hover:not(.disabled) {
  background-color: #FFF3E6;
}

.option-item.selected {
  background-color: #FFF3E6;
  color: #FF6A00;
}

.option-item.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.option-content {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.option-name {
  font-size: 14px;
}

.status-tag {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.status-tag.online {
  background-color: #D1FAE5;
  color: #059669;
}

.status-tag.offline {
  background-color: #FEE2E2;
  color: #DC2626;
}

.check-icon {
  color: #FF6A00;
  font-size: 12px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: #9CA3AF;
  gap: 8px;
}

.empty-state i {
  font-size: 24px;
}
</style>
