<template>
  <div class="case-category-comparison">
    <div class="section-header" @click="toggleCollapse">
      <h3 class="section-title">按用例分组对比 (By Group Comparison)</h3>
      <button class="collapse-btn" :class="{ collapsed: isCollapsed }" title="折叠/展开">
        <i class="fas fa-chevron-up" v-if="isCollapsed"></i>
        <i class="fas fa-chevron-down" v-else></i>
      </button>
    </div>

    <!-- Collapsible Content -->
    <div class="section-content" v-if="!isCollapsed">
      <!-- Filter Card -->
      <div class="report-filter-card filter-card">
        <div class="filter-title">
          <i class="fas fa-filter" style="color: #ff6a00; font-size: 18px;"></i>
          筛选条件
        </div>
        <div class="filter-content">
          <div class="filter-row">
            <!-- 用例名称筛选器 -->
            <div class="filter-item case-name-filter-section">
              <label class="filter-label">
                <i class="fas fa-search"></i> 用例名称
              </label>
              <div class="case-name-search-box search-box-flex" style="display: flex; align-items: center;">
                <i class="fas fa-search search-icon"></i>
                <input
                  type="text"
                  v-model="caseNameSearchQuery"
                  placeholder="搜索用例名称..."
                  class="search-input"
                />
                <button class="search-clear" :class="{ visible: caseNameSearchQuery }" @click="caseNameSearchQuery = ''" style="margin-left: auto;">
                  <i class="fas fa-times"></i>
                </button>
              </div>
            </div>
          </div>
          <div class="filter-row">
            <!-- 用例分组筛选器 -->
            <div class="filter-item category-filter-section">
              <label class="filter-label">
                <i class="fas fa-list-check"></i> 用例分组
                <span class="filter-hint" v-if="selectedCategories.length === 0">(显示全部)</span>
                <span class="filter-count" v-else>已选 {{ selectedCategories.length }} 个</span>
              </label>
              <div class="category-search-box search-box-flex" style="display: flex; align-items: center;">
                <i class="fas fa-search search-icon"></i>
                <input
                  type="text"
                  v-model="categorySearchQuery"
                  placeholder="搜索分组..."
                  class="search-input"
                />
                <button class="search-clear" :class="{ visible: categorySearchQuery }" @click="categorySearchQuery = ''" style="margin-left: auto;">
                  <i class="fas fa-times"></i>
                </button>
              </div>
              <div class="tag-filter" :class="{ 'has-pagination': paginatedCategories.length > 0 }">
                <div
                  v-for="category in paginatedCategories"
                  :key="category"
                  :class="['tag-filter-item', { active: selectedCategories.includes(category) }]"
                  @click="toggleCategory(category)"
                >
                  {{ category }}
                </div>
                <div v-if="filteredCategoriesForSelection.length === 0" class="no-data-tip">
                   暂无可用的用例分组
                 </div>
              </div>
              <div class="category-pagination" v-if="filteredCategoriesForSelection.length > categoryPageSize">
                <button class="pagination-btn" @click="categoryPage--" :disabled="categoryPage <= 1">
                  <i class="fas fa-chevron-left"></i>
                </button>
                <span class="pagination-info">{{ categoryPage }} / {{ totalCategoryPages }}</span>
                <button class="pagination-btn" @click="categoryPage++" :disabled="categoryPage >= totalCategoryPages">
                  <i class="fas fa-chevron-right"></i>
                </button>
              </div>
            </div>

            <!-- 用例标签筛选器 -->
            <div class="filter-item tag-filter-section">
              <label class="filter-label">
                <i class="fas fa-tag"></i> 用例标签
                <span class="filter-hint" v-if="selectedTags.length === 0">(显示全部)</span>
                <span class="filter-count" v-else>已选 {{ selectedTags.length }} 个</span>
              </label>
              <div class="tag-search-box search-box-flex" style="display: flex; align-items: center;">
                <i class="fas fa-search search-icon"></i>
                <input
                  type="text"
                  v-model="tagSearchQuery"
                  placeholder="搜索标签..."
                  class="search-input"
                />
                <button class="search-clear" :class="{ visible: tagSearchQuery }" @click="tagSearchQuery = ''" style="margin-left: auto;">
                  <i class="fas fa-times"></i>
                </button>
              </div>
              <div class="case-type-filter" :class="{ 'has-pagination': paginatedTags.length > 0 }">
                <div
                  v-for="tag in paginatedTags"
                  :key="tag"
                  :class="['case-type-item', { active: selectedTags.includes(tag) }]"
                  @click="toggleTag(tag)"
                >
                  {{ tag }}
                </div>
                <div v-if="filteredTagsForSelection.length === 0" class="no-data-tip">
                  暂无可用的用例标签
                </div>
              </div>
              <div class="tag-pagination" v-if="filteredTagsForSelection.length > tagPageSize">
                <button class="pagination-btn" @click="tagPage--" :disabled="tagPage <= 1">
                  <i class="fas fa-chevron-left"></i>
                </button>
                <span class="pagination-info">{{ tagPage }} / {{ totalTagPages }}</span>
                <button class="pagination-btn" @click="tagPage++" :disabled="tagPage >= totalTagPages">
                  <i class="fas fa-chevron-right"></i>
                </button>
              </div>
            </div>
          </div>
          <div class="filter-buttons">
            <button class="btn btn-secondary" @click="resetFilters">
              <i class="fas fa-undo"></i> 重置
            </button>
            <button class="btn btn-primary" @click="applyFilters">
              <i class="fas fa-check"></i> 应用筛选
            </button>
          </div>
        </div>
      </div>

      <!-- 评估维度选择区域 -->
      <div class="metric-selection">
        <div class="metric-selection-title">
          <i class="fas fa-chart-line" style="color: #1677ff; font-size: 18px;"></i>
          选择评估维度（可多选）
          <span class="filter-hint" v-if="selectedMetrics.length === 0">(显示全部)</span>
          <span class="filter-count" v-else>已选 {{ selectedMetrics.length }} 个</span>
        </div>
        <div class="metric-search-box search-box-flex" style="display: flex; align-items: center;">
          <i class="fas fa-search search-icon"></i>
          <input
            type="text"
            v-model="metricSearchQuery"
            placeholder="搜索评估维度..."
            class="search-input"
          />
          <button class="search-clear" :class="{ visible: metricSearchQuery }" @click="metricSearchQuery = ''" style="margin-left: auto;">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="metric-tags" id="metric-tags-container">
          <div
            v-for="(metric, index) in paginatedMetrics"
            :key="metric.name"
            :id="`metric-tag-${index}`"
            :data-metric="metric.name"
            :class="['metric-tag', { active: selectedMetrics.includes(metric.name) }]"
            @click="toggleMetric(metric.name)"
          >
            <i class="fas fa-check-circle"></i>
            {{ metric.name }}（{{ metric.unit }}）
          </div>
          <div v-if="filteredMetricsForDisplay.length === 0" class="no-data-tip">
            暂无可用的评估维度
          </div>
        </div>
        <div class="metric-pagination" v-if="filteredMetricsForDisplay.length > metricPageSize">
          <button class="pagination-btn" @click="metricPage--" :disabled="metricPage <= 1">
            <i class="fas fa-chevron-left"></i>
          </button>
          <span class="pagination-info">{{ metricPage }} / {{ totalMetricPages }}</span>
          <button class="pagination-btn" @click="metricPage++" :disabled="metricPage >= totalMetricPages">
            <i class="fas fa-chevron-right"></i>
          </button>
        </div>
      </div>

      <!-- 评估维度卡片 -->
      <div v-if="filteredMetrics.length === 0" id="no-metrics-selected" class="no-metrics-selected">
        <i class="fas fa-exclamation-circle"></i>
        暂无可用的评估维度
      </div>
      <div
        v-for="(metric, index) in filteredMetrics"
        :key="metric.name"
        class="metric-container"
        :data-chart-id="`chart-${index}`"
      >
        <!-- 维度标题 -->
        <div class="metric-table-title">
          <div class="title-content" @click="toggleMetricCollapse(metric.name)">
            <i class="fas fa-chart-bar"></i>
            <span>{{ metric.name }} 对比（单位：{{ metric.unit }}）</span>
          </div>
          <div class="title-actions">
            <div class="display-type-selector" v-if="!collapsedMetrics[metric.name]">
              <button
                v-for="displayType in displayTypes"
                :key="displayType.type"
                :class="['display-type-btn', { active: activeDisplayType === displayType.type }]"
                @click.stop="activeDisplayType = displayType.type"
              >
                <i :class="displayType.icon"></i>
              </button>
            </div>
            <button class="metric-collapse-btn" :class="{ collapsed: collapsedMetrics[metric.name] }" title="折叠/展开" @click.stop="toggleMetricCollapse(metric.name)">
              <i class="fas fa-chevron-up" v-if="collapsedMetrics[metric.name]"></i>
              <i class="fas fa-chevron-down" v-else></i>
            </button>
          </div>
        </div>

        <!-- 图和表切换容器 -->
        <div class="metric-container-content" v-if="!collapsedMetrics[metric.name]">
          <!-- 表格容器 -->
          <div v-if="activeDisplayType === 'table'" class="table-container">
            <DataTable
              :ref="el => setTableRef(metric.name, el)"
              :columns="getTableColumns(metric.name)"
              :data="getTableData(metric.name)"
              :resizable="true"
              :min-column-width="60"
              :default-column-width="{ first: 200, others: 150 }"
              table-class="report-data-table"
              row-key="category"
              @header-save="handleHeaderSave"
              @cell-save="handleCellSave"
            >
              <!-- 自定义第一列（用例分组） -->
              <template #cell-category="{ row, value, rowIndex, colIndex }">
                <span
                  class="editable-cell"
                  @click.stop="handleCategoryCellClick(metric.name, rowIndex, colIndex, row)"
                >{{ row.category }}</span>
              </template>

              <!-- 自定义数据列 -->
              <template #cell-value="{ row, value, column }">
                {{ value }}{{ metric.unit }}
              </template>

              <!-- 空状态 -->
              <template #empty>
                <div style="padding: 40px; text-align: center; color: #94a3b8;">
                  暂无数据
                </div>
              </template>
            </DataTable>
          </div>

          <!-- 图表容器 -->
          <div v-else class="metric-chart-container">
            <ChartComponent
              :type="activeDisplayType"
              :data="getChartData(metric.name)"
              :height="400"
              :title="metric.name"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { inject, watch } from 'vue'
import ChartComponent from './ChartComponent.vue'
import DataTable from '../common/data/DataTable.vue'
import '../../assets/styles/components/report-filter-card.css'
import { useCaseCategoryComparison } from './CaseCategoryComparisonComponent'

const props = defineProps({
  reportData: {
    type: Object, default: () => ({})
  }
})

// 导出模式：导出时展开所有折叠区块
const isExporting = inject('isExporting', false)

const {
  isCollapsed,
  toggleCollapse,
  collapsedMetrics,
  toggleMetricCollapse,
  setTableRef,
  caseNameSearchQuery,
  selectedCategories,
  categorySearchQuery,
  paginatedCategories,
  toggleCategory,
  filteredCategoriesForSelection,
  categoryPage,
  categoryPageSize,
  totalCategoryPages,
  selectedTags,
  tagSearchQuery,
  paginatedTags,
  toggleTag,
  filteredTagsForSelection,
  tagPage,
  tagPageSize,
  totalTagPages,
  selectedMetrics,
  metricSearchQuery,
  paginatedMetrics,
  toggleMetric,
  filteredMetricsForDisplay,
  metricPage,
  metricPageSize,
  totalMetricPages,
  filteredMetrics,
  displayTypes,
  activeDisplayType,
  getTableColumns,
  getTableData,
  handleHeaderSave,
  handleCellSave,
  handleCategoryCellClick,
  getChartData,
  resetFilters,
  applyFilters
} = useCaseCategoryComparison(props)

// 导出模式：展开本区块 + 展开所有维度卡片 + 强制使用表格模式（canvas 图表无法克隆到静态 HTML）
watch(isExporting, (exporting) => {
  if (exporting) {
    isCollapsed.value = false
    collapsedMetrics.value = {}
    activeDisplayType.value = 'table'
  }
}, { immediate: true })
</script>

<style scoped>
@import './CaseCategoryComparisonComponent.css';
</style>
