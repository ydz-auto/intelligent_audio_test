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
import DynamicForm from '../../algorithm/DynamicForm.vue'
import { useAlgorithmSelector } from './AlgorithmSelector'

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

const {
  selectedAlgorithms,
  showDropdown,
  searchQuery,
  dropdownRef,
  dropdownMenuRef,
  dropdownMenuStyle,
  toggleDropdown,
  filteredGroups,
  getAlgorithmName,
  isAlgorithmSelected,
  isPrimaryAlgorithm,
  toggleAlgorithm,
  removeAlgorithm,
  setPrimaryAlgorithm,
  primaryAlgorithmType,
  algorithmFormSchema,
  algorithmParams,
  dynamicFormRef,
  onFieldChange
} = useAlgorithmSelector(props, emit)

defineExpose({
  algorithmParams,
  selectedAlgorithms,
  primaryAlgorithmType
})
</script>

<style scoped>
@import './AlgorithmSelector.css';
</style>
