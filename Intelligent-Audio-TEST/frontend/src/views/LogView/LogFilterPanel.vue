<!--
  purpose: 筛选与高级过滤面板子组件。
  MVC role: View
-->
<template>
  <div class="filter-section">
    <div class="filter-bar advanced">
      <!-- 第一行：搜索、分类、模块 -->
      <div class="filter-row main-row">
        <div class="search-box">
          <i class="fas fa-search search-icon"></i>
          <input type="text" class="search-input" placeholder="搜索日志内容..." :value="searchTerm" @input="onSearchInput">
          <button v-if="searchTerm" class="search-clear" @click="clearSearch">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="filter-group">
          <label class="filter-label">分类:</label>
          <div class="filter-select">
            <select class="form-input" v-model="filters.logCategory" @change="filterLogs">
              <option v-for="option in LOGCategoryOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </div>
        </div>

        <div class="filter-group">
          <label class="filter-label">模块:</label>
          <div class="filter-select">
            <select class="form-input" v-model="filters.logModule" @change="filterLogs">
              <option v-for="option in LOGModuleOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </div>
        </div>
      </div>

      <!-- 第二行：时间范围、标记筛选、算法类型 -->
      <div class="filter-row secondary-row">
        <div class="filter-group time-range-group">
          <label class="filter-label">时间范围:</label>
          <div class="date-time-inputs">
            <div class="filter-select" ref="startContainer">
              <input type="datetime-local" class="form-input" ref="startInput" v-model="filters.startDateTime" @change="filterLogs">
            </div>
            <span class="date-separator">至</span>
            <div class="filter-select" ref="endContainer">
              <input type="datetime-local" class="form-input" ref="endInput" v-model="filters.endDateTime" @change="filterLogs">
            </div>
          </div>
        </div>

        <div class="filter-group">
          <label class="filter-label">标记筛选:</label>
          <div class="filter-select">
            <select class="form-input" v-model="filters.markFilter" @change="filterLogs">
              <option v-for="option in LOGMarkOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </div>
        </div>

        <div class="filter-group">
          <label class="filter-label">算法类型:</label>
          <div class="filter-select">
            <select class="form-input" v-model="filters.algorithmType" @change="filterLogs">
              <option v-for="option in algorithmOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </div>
        </div>

        <div class="spacer"></div>

        <button class="btn btn-text" @click="toggleAdvancedFilter">
          <i class="fas fa-sliders-h btn-icon"></i>
          <span>{{ advancedFilterText }}</span>
        </button>

        <button class="btn btn-text" @click="clearAllFilters">
          <i class="fas fa-eraser btn-icon"></i>
          清除过滤器
        </button>
      </div>

      <!-- 第三行：日志级别 -->
      <div class="filter-row level-row">
        <div class="filter-group full-width">
          <label class="filter-label">日志级别:</label>
          <div class="level-tags">
            <span v-for="level in logLevels" :key="level.value"
                  class="level-tag"
                  :class="[level.value, { active: selectedLevels.includes(level.value) }]"
                  @click="toggleLevel(level.value)">
              {{ level.label }}
              <i v-if="selectedLevels.includes(level.value)" class="fas fa-times close-icon"></i>
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 高级过滤面板 -->
  <div class="advanced-filter-panel" v-show="showAdvancedFilter">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">高级过滤</h3>
      </div>
      <div class="card-body">
        <div class="filter-bar advanced">
          <div class="filter-row filter-grid">
            <div class="filter-group">
              <label class="filter-label">设备ID:</label>
              <div class="filter-select">
                <input type="text" class="form-input" v-model="advancedFilters.deviceId" placeholder="输入设备ID" @input="filterLogs">
              </div>
            </div>

            <div class="filter-group">
              <label class="filter-label">任务ID:</label>
              <div class="filter-select">
                <input type="text" class="form-input" v-model="advancedFilters.taskId" placeholder="输入任务ID" @input="filterLogs">
              </div>
            </div>
          </div>

          <div class="filter-row filter-grid">
            <div class="filter-group">
              <label class="filter-label">用户ID:</label>
              <div class="filter-select">
                <input type="text" class="form-input" v-model="advancedFilters.userId" placeholder="输入用户ID" @input="filterLogs">
              </div>
            </div>

            <div class="filter-group">
              <label class="filter-label">线程ID:</label>
              <div class="filter-select">
                <input type="text" class="form-input" v-model="advancedFilters.threadId" placeholder="输入线程ID" @input="filterLogs">
              </div>
            </div>
          </div>

          <div class="filter-row filter-grid">
            <div class="filter-group">
              <label class="filter-label">日志内容包含:</label>
              <div class="filter-select">
                <input type="text" class="form-input" v-model="advancedFilters.contentInclude" placeholder="包含文本" @input="filterLogs">
              </div>
            </div>

            <div class="filter-group">
              <label class="filter-label">日志内容不包含:</label>
              <div class="filter-select">
                <input type="text" class="form-input" v-model="advancedFilters.contentExclude" placeholder="不包含文本" @input="filterLogs">
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  filters: any
  advancedFilters: any
  searchTerm: any
  logLevels: any[]
  selectedLevels: any[]
  showAdvancedFilter: boolean
  LOGCategoryOptions: any[]
  LOGModuleOptions: any[]
  LOGMarkOptions: any[]
  algorithmOptions: any[]
  advancedFilterText: string
}>()

const emit = defineEmits<{
  (e: 'search-logs'): void
  (e: 'clear-search'): void
  (e: 'filter-logs'): void
  (e: 'toggle-advanced-filter'): void
  (e: 'clear-all-filters'): void
  (e: 'toggle-level', level: string): void
  (e: 'update:searchTerm', value: string): void
}>()

// 模板事件桥接：将 DOM 事件转发为父组件可监听的 emits
const onSearchInput = (event: Event) => {
  emit('update:searchTerm', (event.target as HTMLInputElement).value)
  emit('search-logs')
}
const searchLogs = () => emit('search-logs')
const clearSearch = () => emit('clear-search')
const filterLogs = () => emit('filter-logs')
const toggleAdvancedFilter = () => emit('toggle-advanced-filter')
const clearAllFilters = () => emit('clear-all-filters')
const toggleLevel = (level: string) => emit('toggle-level', level)

// 日期时间输入与容器引用，暴露给父组件供 composable 绑定点击事件
const startInput = ref<HTMLInputElement | null>(null)
const endInput = ref<HTMLInputElement | null>(null)
const startContainer = ref<HTMLElement | null>(null)
const endContainer = ref<HTMLElement | null>(null)

defineExpose({ startInput, endInput, startContainer, endContainer })
</script>
