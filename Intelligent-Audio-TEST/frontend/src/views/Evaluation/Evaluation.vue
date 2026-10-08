<template>
  <div class="evaluation-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-star"></i>
          评估维度管理
        </h2>
        <p class="page-description">管理语音测试的评估维度和权重</p>
      </div>
      <div class="header-right">
        <div class="header-actions">
          <button class="btn btn-text btn-link" @click="openAddModal">
            <i class="fas fa-plus btn-icon"></i>
            新增维度
          </button>
          <div class="btn-group" ref="batchMenuRef">
            <button class="btn btn-text btn-link dropdown-toggle" @click="toggleBatchMenu">
              <i class="fas fa-cogs btn-icon"></i>
              批量操作
            </button>
            <div class="dropdown-menu" id="batchMenu">
              <button class="dropdown-item" @click="batchEnable">批量启用</button>
              <button class="dropdown-item" @click="batchDisable">批量禁用</button>
              <div class="dropdown-divider"></div>
              <button class="dropdown-item text-danger" @click="batchDelete">批量删除</button>
            </div>
          </div>
          <div class="btn-group" ref="importExportMenuRef">
            <button class="btn btn-text btn-link dropdown-toggle" @click="toggleImportExportMenu">
              <i class="fas fa-exchange-alt btn-icon"></i>
              导入/导出
            </button>
            <div class="dropdown-menu" id="importExportMenu">
              <button class="dropdown-item" @click="importDimensions">导入维度</button>
              <button class="dropdown-item" @click="exportDimensions">导出维度</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 主要内容区 - 单栏布局 -->
    <div class="content-wrapper">
      <!-- 维度列表区 -->
      <section class="content-middle">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">评估维度列表</h3>
            <div class="card-header-right">
              <div class="view-switcher">
                <button class="btn-toggle" :class="{ active: viewMode === 'list' }" @click="viewMode = 'list'" title="列表视图">
                  <i class="fas fa-list"></i>
                  列表视图
                </button>
                <button class="btn-toggle" :class="{ active: viewMode === 'group' }" @click="viewMode = 'group'" title="分组视图">
                  <i class="fas fa-folder"></i>
                  分组视图
                </button>
              </div>
              <div class="card-actions">
                <div class="filter-sort-section">
                  <div class="filter-row">
                    <div class="filter-item search-filter-item">
                      <div class="search-box">
                        <i class="fas fa-search search-icon"></i>
                        <input type="text" class="search-input" placeholder="搜索评估维度..." v-model="searchKeyword" @input="searchDimensions">
                      </div>
                    </div>
                    <BadgeFilter
                      :options="STATUS_FILTER_OPTIONS"
                      :model-value="filterStatus"
                      all-label="全部状态"
                      title="状态"
                      @update:model-value="setStatusFilter"
                    />
                    <BadgeFilter
                      :options="CATEGORY_FILTER_OPTIONS"
                      :model-value="filterCategory"
                      all-label="全部分类"
                      title="分类"
                      @update:model-value="setCategoryFilter"
                    />
                    <AlgorithmFilter :options="algorithms" v-model="filterAlgorithm" title="关联算法" />
                    <div class="filter-item reset-filter-item">
                      <button class="btn btn-text btn-primary" @click="resetFilters">重置筛选</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="card-body">
            <!-- 列表视图 -->
            <template v-if="viewMode === 'list'">
              <EvaluationDimensionTable
                :items="hierarchicalDimensions"
                :selected-dimensions="selectedDimensions"
                :is-all-selected="isAllSelected"
                :can-move-up="canMoveUp"
                :can-move-down="canMoveDown"
                :get-algorithm-label="getAlgorithmLabel"
                :is-llm-judge="isLlmJudge"
                @toggle-select-all="toggleSelectAll"
                @toggle-selection="toggleDimensionSelection"
                @edit="openEditModal"
                @test-api="testApiHealth"
                @delete="deleteDimension"
                @add-sub="(payload) => openAddModal(payload.categoryId, payload.id)"
                @weight-change="(payload) => updateWeight(payload.id, payload.weight)"
                @move="(payload) => moveDimension(payload.id, payload.direction)"
              />
              <div v-if="!loading && hierarchicalDimensions.length === 0" class="empty-dimensions">
                <i class="fas fa-inbox"></i>
                <p>暂无评估维度数据</p>
              </div>
            </template>

            <!-- 分组视图：按分类聚合，分类内保留主/子维度层级 -->
            <template v-else>
              <div v-if="loading" class="empty-dimensions">
                <i class="fas fa-spinner fa-spin"></i>
                <p>加载中...</p>
              </div>
              <template v-else>
                <div
                  v-for="group in groupedDimensions"
                  :key="group.key"
                  class="group-card"
                >
                  <div class="group-header" @click="toggleGroupExpanded(group.key)">
                    <div class="group-header-left">
                      <input
                        type="checkbox"
                        class="group-checkbox"
                        :checked="groupAllSelected(group)"
                        @click.stop
                        @change="toggleGroupSelectAll(group)"
                        title="全选该分组"
                      >
                      <i class="fas fa-chevron-down group-toggle" :class="{ expanded: isGroupExpanded(group.key) }"></i>
                      <i :class="group.category?.icon || 'fas fa-folder'" class="group-icon"></i>
                      <h4 class="group-title">{{ group.category?.name || '未分类' }}</h4>
                      <span class="group-count">{{ group.items.length }}</span>
                      <span v-if="group.category?.description" class="group-desc">{{ group.category.description }}</span>
                    </div>
                    <div class="group-header-actions" @click.stop>
                      <button class="btn btn-text btn-primary btn-sm" @click="openAddModal(group.category?.id)">
                        <i class="fas fa-plus btn-icon"></i>
                        添加维度
                      </button>
                    </div>
                  </div>
                  <div v-show="isGroupExpanded(group.key)" class="group-content">
                    <EvaluationDimensionTable
                      :items="group.items"
                      :selected-dimensions="selectedDimensions"
                      :show-header-checkbox="false"
                      :can-move-up="canMoveUp"
                      :can-move-down="canMoveDown"
                      :get-algorithm-label="getAlgorithmLabel"
                      :is-llm-judge="isLlmJudge"
                      @toggle-selection="toggleDimensionSelection"
                      @edit="openEditModal"
                      @test-api="testApiHealth"
                      @delete="deleteDimension"
                      @add-sub="(payload) => openAddModal(payload.categoryId, payload.id)"
                      @weight-change="(payload) => updateWeight(payload.id, payload.weight)"
                      @move="(payload) => moveDimension(payload.id, payload.direction)"
                    />
                  </div>
                </div>

                <div v-if="groupedDimensions.length === 0" class="empty-dimensions">
                  <i class="fas fa-inbox"></i>
                  <p>暂无评估维度数据</p>
                </div>
              </template>
            </template>
          </div>
        </div>
        <!-- 分页控件 - 显示在卡片下方 -->
        <div class="pagination-container">
          <pagination-component 
            :current-page="currentPage"
            :page-size="pageSize"
            :total-items="totalItems"
            :total-pages="totalPages"
            @prev-page="prevPage"
            @next-page="nextPage"
            @go-to-page="goToPage"
            @page-size-change="onPageSizeChange"
          ></pagination-component>
        </div>
      </section>
    </div>


  </div>
</template>

<script setup>
// 导入分页组件
import PaginationComponent from '../../components/common/data/PaginationComponent.vue';
import BadgeFilter from '../../components/common/BadgeFilter.vue';
// 关联算法筛选组件
import AlgorithmFilter from '../../components/algorithm/AlgorithmFilter.vue';
// 评估维度表格公共组件（列表/分组视图共用）
import EvaluationDimensionTable from '../../components/EvaluationDimensionTable.vue';

// 导入组件逻辑
import { useEvaluation } from './evaluation';

const {
  batchMenuRef,
  importExportMenuRef,
  searchKeyword,
  filterStatus,
  filterCategory,
  filterAlgorithm,
  algorithms,
  selectedDimensions,
  currentPage,
  pageSize,
  dimensions,
  newDimension,
  apiHealthResult,
  apiSettings,
  importSettings,
  showImportPreview,
  importPreview,
  newCategory,
  editingCategory,
  editingDimension,
  filteredDimensions,
  hierarchicalDimensions,
  groupedDimensions,
  viewMode,
  isGroupExpanded,
  toggleGroupExpanded,
  groupAllSelected,
  toggleGroupSelectAll,
  totalPages,
  totalItems,
  isAllSelected,
  saveDimension,
  deleteDimension,
  moveDimension,
  canMoveUp,
  canMoveDown,
  toggleSelectAll,
  toggleDimensionSelection,
  batchEnable,
  batchDisable,
  batchDelete,
  toggleBatchMenu,
  toggleImportExportMenu,
  testAPIHealth,
  updateWeight,
  searchDimensions,
  filterDimensions,
  resetFilters,
  onPageSizeChange,
  previewImportData,
  handleImport,
  saveAPISettings,
  toggleCategory,
  toggleGroupSelection,
  selectAllInGroup,
  toggleSelectAllInCategory,
  deleteGroup,
  saveCategory,
  prevPage,
  nextPage,
  goToPage,
  fetchData,
  getAlgorithmLabel,
  // 模态框操作函数
  openAddModal,
  openEditModal,
  closeModal,
  importDimensions,
  exportDimensions,
  openAPISettingsModal,
  openRuleEditorModal,
  initEvaluation,
  cleanupEvaluation,
  loading,
  isLlmJudge,
} = useEvaluation();

// ===== 徽章筛选选项（原下拉框硬编码迁移为常量）=====
const STATUS_FILTER_OPTIONS = [
  { value: 'active', label: '启用' },
  { value: 'inactive', label: '禁用' },
];

const CATEGORY_FILTER_OPTIONS = [
  { value: '性能指标', label: '性能指标' },
  { value: '功能指标', label: '功能指标' },
  { value: '质量指标', label: '质量指标' },
  { value: '环境适应性', label: '环境适应性' },
];

function setStatusFilter(value) {
  filterStatus.value = String(value);
  filterDimensions();
}

function setCategoryFilter(value) {
  filterCategory.value = String(value);
  filterDimensions();
}
</script>

<style scoped>
@import './Evaluation.css';


                           
.btn-group{
    position: relative;
    display: inline-block;
}

/* content-wrapper - 自全局样式就近迁移 */
.content-wrapper{
    display: grid;
    grid-template-columns: 1fr;
    gap: var(--spacing-lg);
    margin-bottom: var(--spacing-xl);
    transition: all var(--transition-normal);
    width: auto;
    min-width: 100%;
    box-sizing: border-box;
    overflow-x: visible;
}

/* evaluation-view - 自全局样式就近迁移 */


</style>
