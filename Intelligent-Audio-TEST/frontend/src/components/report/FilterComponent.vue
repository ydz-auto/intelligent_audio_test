<template>
  <div class="filter-component-container">
    <div class="filter-header" v-if="showHeader">
      <h3 class="filter-title">{{ title }}</h3>
      <div class="filter-actions">
        <button class="btn btn-secondary" @click="resetFilters">
          <i class="fas fa-times"></i> 重置筛选
        </button>
        <button class="btn btn-primary" @click="applyFilters">
          <i class="fas fa-check"></i> 应用筛选
        </button>
      </div>
    </div>
    
    <div class="filter-content">
      <!-- 条件筛选 -->
      <div class="filter-group" v-for="group in filterGroups" :key="group.key">
        <h4 class="filter-group-title">{{ group.label }}</h4>
        
        <!-- 文本输入筛选 -->
        <div class="filter-item" v-if="group.type === 'text'">
          <input 
            type="text" 
            :placeholder="group.placeholder || '请输入...'"
            v-model="filterValues[group.key]"
            @input="handleFilterChange"
            class="filter-input"
          />
        </div>
        
        <!-- 下拉选择筛选 -->
        <div class="filter-item" v-else-if="group.type === 'select'">
          <select 
            v-model="filterValues[group.key]"
            @change="handleFilterChange"
            class="filter-select"
          >
            <option value="">全部</option>
            <option 
              v-for="option in group.options" 
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </div>
        
        <!-- 单选按钮组筛选 -->
        <div class="filter-item" v-else-if="group.type === 'radio'">
          <div class="radio-group">
            <label 
              v-for="option in group.options" 
              :key="option.value"
              class="radio-label"
            >
              <input 
                type="radio" 
                :name="group.key"
                :value="option.value"
                v-model="filterValues[group.key]"
                @change="handleFilterChange"
              >
              <span class="radio-text">{{ option.label }}</span>
            </label>
          </div>
        </div>
        
        <!-- 多选框组筛选 -->
        <div class="filter-item" v-else-if="group.type === 'checkbox'">
          <div class="checkbox-group">
            <label 
              v-for="option in group.options" 
              :key="option.value"
              class="checkbox-label"
            >
              <input 
                type="checkbox" 
                :value="option.value"
                v-model="filterValues[group.key]"
                @change="handleFilterChange"
              >
              <span class="checkbox-text">{{ option.label }}</span>
            </label>
          </div>
        </div>
        
        <!-- 日期范围筛选 -->
        <div class="filter-item" v-else-if="group.type === 'dateRange'">
          <div class="date-range-container">
            <div class="date-input-group">
              <label :for="group.key + '-start-date'">开始日期:</label>
              <input 
                type="date" 
                :id="group.key + '-start-date'"
                v-model="filterValues[group.key].start"
                @change="handleFilterChange"
                class="filter-date-input"
              />
            </div>
            <span class="date-separator">至</span>
            <div class="date-input-group">
              <label :for="group.key + '-end-date'">结束日期:</label>
              <input 
                type="date" 
                :id="group.key + '-end-date'"
                v-model="filterValues[group.key].end"
                @change="handleFilterChange"
                class="filter-date-input"
              />
            </div>
          </div>
        </div>
        
        <!-- 滑块筛选 -->
        <div class="filter-item" v-else-if="group.type === 'range'">
          <div class="range-container">
            <div class="range-inputs">
              <div class="range-input-group">
                <label for="min-range">最小值:</label>
                <input 
                  type="number" 
                  id="min-range"
                  :min="group.min"
                  :max="group.max"
                  :step="group.step || 1"
                  v-model="filterValues[group.key].min"
                  @input="handleFilterChange"
                  class="filter-number-input"
                />
              </div>
              <span class="range-separator">-</span>
              <div class="range-input-group">
                <label for="max-range">最大值:</label>
                <input 
                  type="number" 
                  id="max-range"
                  :min="group.min"
                  :max="group.max"
                  :step="group.step || 1"
                  v-model="filterValues[group.key].max"
                  @input="handleFilterChange"
                  class="filter-number-input"
                />
              </div>
            </div>
            <div class="range-slider-container">
              <input 
                type="range" 
                :min="group.min"
                :max="group.max"
                :step="group.step || 1"
                v-model="filterValues[group.key].min"
                @input="handleFilterChange"
                class="range-slider"
              />
              <input 
                type="range" 
                :min="group.min"
                :max="group.max"
                :step="group.step || 1"
                v-model="filterValues[group.key].max"
                @input="handleFilterChange"
                class="range-slider"
              />
            </div>
          </div>
        </div>
        
        <!-- 标签云筛选 -->
        <div class="filter-item" v-else-if="group.type === 'tagCloud'">
          <div class="tag-cloud-container">
            <span 
              v-for="tag in group.options" 
              :key="tag.value"
              class="tag-item"
              :class="{ 'tag-selected': filterValues[group.key].includes(tag.value) }"
              @click="toggleTag(group.key, tag.value)"
            >
              <span class="tag-name">{{ tag.label }}</span>
              <span class="tag-count">({{ tag.count }})</span>
            </span>
          </div>
        </div>
      </div>
    </div>
    
    <div class="filter-footer" v-if="showFooter">
      <div class="active-filters" v-if="activeFilterCount > 0">
        <h4 class="active-filters-title">已选条件 ({{ activeFilterCount }})</h4>
        <div class="active-filters-list">
          <span 
            v-for="(value, key) in getActiveFilters()" 
            :key="key"
            class="active-filter-item"
          >
            <span class="filter-label">{{ getFilterLabel(key) }}:</span>
            <span class="filter-value">{{ getFilterDisplayValue(key, value) }}</span>
            <button class="filter-remove-btn" @click="removeFilter(key)">
              <i class="fas fa-times"></i>
            </button>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useFilterComponent } from './FilterComponent'

const props = defineProps({
  title: {
    type: String, default: '筛选条件'
  },
  filterGroups: {
    type: Array, required: true, default: () => []
  },
  showHeader: {
    type: Boolean, default: true
  },
  showFooter: {
    type: Boolean, default: true
  }
})

const emit = defineEmits(['filterChange', 'apply', 'reset'])

const {
  filterValues,
  activeFilterCount,
  handleFilterChange,
  applyFilters,
  resetFilters,
  toggleTag,
  removeFilter,
  getActiveFilters,
  getFilterLabel,
  getFilterDisplayValue
} = useFilterComponent(props, emit)
</script>

<style scoped>
@import './FilterComponent.css';
</style>