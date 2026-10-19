<template>
  <div class="evaluation-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title page-title-primary">
          <i class="fas fa-star"></i>
          评估维度管理
        </h2>
        <p class="page-description">管理语音测试的评估维度和权重</p>
      </div>
      <div class="header-right">
        <div class="header-actions">
          <button class="btn btn-text btn-link" @click="openAddModal()">
            <i class="fas fa-plus btn-icon"></i>
            新增维度
          </button>
          <button class="btn btn-text btn-link" @click="openAddCategoryModal">
            <i class="fas fa-folder-plus btn-icon"></i>
            新增分类
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
                      :options="categoryFilterOptions"
                      :model-value="filterCategory"
                      all-label="全部分类"
                      title="分类"
                      @update:model-value="setCategoryFilter"
                    />
                    <!-- INT-423/467：可见性筛选（全部/共享/私有；纯前端派生） -->
                    <BadgeFilter
                      :options="VISIBILITY_FILTER_OPTIONS"
                      :model-value="filterVisibility || 'all'"
                      all-label="全部"
                      title="可见性"
                      @update:model-value="setVisibilityFilter"
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
            <div class="auto-merge-hint">
              <i class="fas fa-info-circle"></i>
              同一分类下、评估服务与请求模板一致的维度，评估时会自动合并为一次请求，共用一次判定结果。
            </div>
            <!-- INT-290：加载/错误态（对齐 A/B 域 Device 错误条方案；列表/分组视图统一消费 loading/error）。
                 交互决策（INT-290 记录）：列表视图不再使用基线 InfiniteScrollList 无限滚动（组件已移除），
                 INT-281 起全量拉取 + 前端过滤，列表直接平铺渲染全部维度（维度量级小，千条内无需分页/无限滚动）。 -->
            <div v-if="loading" class="evaluation-loading-bar">
              <span class="loading-spinner"></span>
              正在加载评估维度...
            </div>
            <div v-else-if="error" class="evaluation-error-banner">
              <i class="fas fa-exclamation-triangle"></i>
              <span class="evaluation-error-text">{{ error }}</span>
              <button class="btn btn-primary btn-sm" @click="fetchData">
                <i class="fas fa-sync-alt"></i> 重试
              </button>
            </div>
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
                @test-api="testAPIHealth"
                @delete="deleteDimension"
                @add-sub="(payload) => openAddModal(payload.categoryId, payload.id)"
                @weight-change="(payload) => updateWeight(payload.id, payload.weight)"
                @move="(payload) => moveDimension(payload.id, payload.direction)"
                @toggle-visibility="toggleDimensionVisibility"
              />
              <div v-if="!loading && !error && hierarchicalDimensions.length === 0" class="empty-dimensions">
                <i class="fas fa-inbox"></i>
                <p>暂无评估维度数据</p>
              </div>
            </template>

            <!-- 分组视图：按分类聚合，分类内保留主/子维度层级 -->
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
                    @test-api="testAPIHealth"
                    @delete="deleteDimension"
                    @add-sub="(payload) => openAddModal(payload.categoryId, payload.id)"
                    @weight-change="(payload) => updateWeight(payload.id, payload.weight)"
                    @move="(payload) => moveDimension(payload.id, payload.direction)"
                    @toggle-visibility="toggleDimensionVisibility"
                  />
                </div>
              </div>

              <div v-if="!loading && !error && groupedDimensions.length === 0" class="empty-dimensions">
                <i class="fas fa-inbox"></i>
                <p>暂无评估维度数据</p>
              </div>
            </template>
          </div>
        </div>
      </section>
    </div>


  </div>
</template>

<script setup>
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/progress.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { computed } from 'vue';
import BadgeFilter from '../../components/common/BadgeFilter.vue';
import VisibilityBadge from '../../components/common/visibility/VisibilityBadge.vue';
import { VISIBILITY_FILTER_OPTIONS } from '../../composables/visibility/useVisibility';
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
  categories,
  filterStatus,
  filterVisibility,
  filterCategory,
  filterAlgorithm,
  algorithms,
  selectedDimensions,
  hierarchicalDimensions,
  groupedDimensions,
  viewMode,
  isGroupExpanded,
  toggleGroupExpanded,
  groupAllSelected,
  toggleGroupSelectAll,
  isAllSelected,
  deleteDimension,
  toggleDimensionVisibility,
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
  getAlgorithmLabel,
  // 模态框操作函数
  openAddModal,
  openAddCategoryModal,
  openEditModal,
  importDimensions,
  exportDimensions,
  loading,
  // INT-290：加载/错误态（错误横幅渲染 + 重试按钮）
  error,
  fetchData,
  isLlmJudge,
} = useEvaluation();

// ===== 徽章筛选选项（原下拉框硬编码迁移为常量）=====
const STATUS_FILTER_OPTIONS = [
  { value: 'active', label: '启用' },
  { value: 'inactive', label: '禁用' },
];

// 分类筛选选项：由接口加载的分类动态生成（对齐 V9.7.10），value 为分类 ID（后端 categoryId 过滤）
const categoryFilterOptions = computed(() =>
  (categories.value || []).map(cat => ({ value: cat.id, label: cat.name }))
);

function setStatusFilter(value) {
  filterStatus.value = String(value);
  filterDimensions();
}

function setCategoryFilter(value) {
  filterCategory.value = String(value);
  filterDimensions();
}

/** INT-423/467：可见性筛选切换（全部/共享/私有；纯前端派生） */
function setVisibilityFilter(value) {
  filterVisibility.value = String(value) === 'all' ? '' : String(value);
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

/* INT-290 加载/错误态（对齐 A/B 域 Device 错误条方案） */
.evaluation-loading-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    margin-bottom: var(--spacing-lg);
    background: color-mix(in srgb, var(--primary-color) 5%, transparent);
    border-radius: var(--border-radius-lg);
    color: var(--text-secondary);
    font-size: 14px;
}

.evaluation-loading-bar .loading-spinner {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid color-mix(in srgb, var(--primary-color) 30%, transparent);
    border-top-color: var(--primary-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}

.evaluation-error-banner {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    margin-bottom: var(--spacing-lg);
    background: color-mix(in srgb, var(--danger-color, #f5222d) 8%, transparent);
    border: 1px solid color-mix(in srgb, var(--danger-color, #f5222d) 30%, transparent);
    border-radius: var(--border-radius-lg);
    color: var(--danger-color, #f5222d);
    font-size: 14px;
}

.evaluation-error-text {
    flex: 1;
}

.evaluation-error-banner .btn-sm {
    padding: 4px 12px;
    font-size: 12px;
}

</style>
