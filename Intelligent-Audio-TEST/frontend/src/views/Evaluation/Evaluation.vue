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
            <div class="card-actions">
              <div class="filter-sort-section">
                <div class="filter-row">
                  <div class="filter-item">
                    <div class="search-box">
                      <i class="fas fa-search search-icon"></i>
                      <input type="text" class="search-input" placeholder="搜索评估维度..." v-model="searchKeyword" @input="searchDimensions">
                    </div>
                  </div>
                  <div class="filter-item">
                    <div class="filter-select">
                      <select class="form-input" v-model="filterStatus" @change="filterDimensions">
                        <option value="all">全部状态</option>
                        <option value="active">启用</option>
                        <option value="inactive">禁用</option>
                      </select>
                    </div>
                  </div>
                  <div class="filter-item">
                    <div class="filter-select">
                      <select class="form-input" v-model="filterCategory" @change="filterDimensions">
                        <option value="all">全部分类</option>
                        <option value="性能指标">性能指标</option>
                        <option value="功能指标">功能指标</option>
                        <option value="质量指标">质量指标</option>
                        <option value="环境适应性">环境适应性</option>
                      </select>
                    </div>
                  </div>
                  <div class="filter-item">
                    <button class="btn btn-text btn-primary" @click="resetFilters">重置筛选</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="card-body">
            <div class="table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th class="checkbox-column" style="width: 50px;">
                      <input type="checkbox" id="selectAll" v-model="isAllSelected" @change="toggleSelectAll">
                    </th>
                    <th class="dimension-name-col sortable" style="width: 200px;">维度名称</th>
                    <th class="dimension-description-col" style="width: 250px;">描述</th>
                    <th class="dimension-category-col sortable" style="width: 120px;">分类</th>
                    <th class="dimension-algorithms-col" style="width: 180px;">关联算法</th>
                    <th class="dimension-weight-col sortable" style="width: 150px;">权重</th>
                    <th class="dimension-api-status-col sortable" style="width: 120px;">API状态</th>
                    <th class="dimension-status-col sortable" style="width: 100px;">状态</th>
                    <th class="dimension-actions-col" style="width: auto;">操作</th>
                  </tr>
                </thead>
                <tbody id="dimensionsTable">
                  <tr v-for="dimension in filteredDimensions" :key="dimension.id" @click="toggleDimensionSelection(dimension.id)">
                    <td class="checkbox-column"><input type="checkbox" class="dimension-checkbox" v-model="selectedDimensions" :value="dimension.id" @click.stop></td>
                    <td class="dimension-name-col" @click.stop="openEditModal(dimension.id)">{{ dimension.name }}</td>
                    <td class="dimension-description-col text-truncate" :title="dimension.description">{{ dimension.description || '-' }}</td>
                    <td class="dimension-category-col">{{ dimension.category || dimension.type }}</td>
                    <td class="dimension-algorithms-col">
                      <div class="algorithm-tags" v-if="dimension.associatedAlgorithms && dimension.associatedAlgorithms.length > 0">
                        <span class="algo-tag" v-for="algo in dimension.associatedAlgorithms" :key="algo.algorithmType" :class="{ 'is-default': algo.isDefault }">
                          {{ getAlgorithmLabel(algo.algorithmType) }}
                        </span>
                      </div>
                      <span v-else class="text-muted">-</span>
                    </td>
                    <td class="dimension-weight-col">
                      <div class="weight-control">
                        <input type="range" class="weight-slider" min="1" max="10" v-model="dimension.weight" @input="updateWeight(dimension.id, dimension.weight)" @click.stop>
                        <span class="weight-value">{{ dimension.weight }}</span>
                      </div>
                    </td>
                    <td class="dimension-api-status-col">
                      <span v-if="isLlmJudge(dimension)" class="api-status llm-judge">
                        <i class="fas fa-robot"></i> LLM Judge
                      </span>
                      <span v-else class="api-status" :class="dimension.apiStatus">
                        <i class="fas fa-circle" :class="dimension.apiStatus === 'online' ? 'online-indicator' : 'offline-indicator'"></i> {{ dimension.apiStatus === 'online' ? '在线' : '离线' }}
                      </span>
                    </td>
                    <td class="dimension-status-col"><span class="status-badge" :class="dimension.status ? 'active' : 'inactive'">{{ dimension.status ? '启用' : '禁用' }}</span></td>
                    <td class="dimension-actions-col">
                      <div class="action-buttons">
                        <button class="btn btn-text btn-primary" @click.stop="openEditModal(dimension.id)">
                          <i class="fas fa-edit btn-icon"></i>
                          编辑
                        </button>
                        <button class="btn btn-text btn-info" @click.stop="testApiHealth(dimension.id)">
                          <i class="fas fa-heartbeat btn-icon"></i>
                          测试API
                        </button>
                        <button class="btn btn-text btn-danger" @click.stop="deleteDimension(dimension.id)">
                          <i class="fas fa-trash btn-icon"></i>
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
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
// 只导入主样式文件，所有组件样式已包含在main.css中
import '../../assets/styles/main.css';

// 导入分页组件
import PaginationComponent from '../../components/common/data/PaginationComponent.vue';

// 导入组件逻辑
import { useEvaluation } from './evaluation';

const {
  batchMenuRef,
  importExportMenuRef,
  searchKeyword,
  filterStatus,
  filterCategory,
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
  totalPages,
  totalItems,
  isAllSelected,
  saveDimension,
  deleteDimension,
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
</script>

<style scoped>
@import './Evaluation.css';
</style>
