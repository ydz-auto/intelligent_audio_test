<template>
  <div class="specific-case-comparison">
    <div class="section-header" @click="toggleCollapse">
      <h3 class="section-title">具体用例对比 (Specific Case Comparison)</h3>
      <button class="collapse-btn" :class="{ collapsed: isCollapsed }" title="折叠/展开">
        <i class="fas fa-chevron-up" v-if="isCollapsed"></i>
        <i class="fas fa-chevron-down" v-else></i>
      </button>
    </div>

    <!-- Collapsible Content -->
    <div class="section-content" v-if="!isCollapsed">
      <div v-if="casesLoading" class="no-data-tip" style="margin-bottom: 12px;">
        正在加载用例数据...
      </div>
      <div v-else-if="casesLoadError" class="no-data-tip" style="margin-bottom: 12px; color: #ff4d4f;">
        {{ casesLoadError }}
      </div>
      <!-- Filter Section -->
      <div class="report-filter-card filter-card">
        <div class="filter-title">
          <i class="fas fa-filter" style="color: #ff6a00; font-size: 18px;"></i>
          筛选条件
        </div>
        <div class="filter-content">
          <!-- 第一行：用例名称筛选 + 用例分组 -->
          <div class="filter-row">
            <div class="filter-item" style="flex: 2;">
              <label class="filter-label">
                <i class="fas fa-search"></i> 用例名称筛选
              </label>
              <input 
                type="text" 
                class="filter-input" 
                placeholder="输入用例ID或名称关键词"
                v-model="searchKeyword"
              />
            </div>
            <div class="filter-item category-filter-section" style="flex: 1;">
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
                  @click="toggleCategoryFilter(category)"
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
          </div>
          
          <!-- 第二行：标签筛选 + 评估维度筛选（多选） + 排序方式 -->
          <div class="filter-row">
            <div class="filter-item" style="flex: 1;">
              <label class="filter-label">
                <i class="fas fa-tag" style="color: #ff6a00;"></i> 标签筛选
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
              <div class="tag-filter-orange" :class="{ 'has-pagination': paginatedTags.length > 0 }">
                <div 
                  v-for="tag in paginatedTags" 
                  :key="tag"
                  :class="['tag-filter-item-orange', { active: selectedTags.includes(tag) }]"
                  @click="toggleTag(tag)"
                >
                  {{ tag }}
                </div>
                <div v-if="filteredTags.length === 0" class="no-data-tip">
                  暂无可用的用例标签
                </div>
              </div>
              <div class="tag-pagination" v-if="filteredTags.length > tagPageSize">
                <button class="pagination-btn" @click="tagPage--" :disabled="tagPage <= 1">
                  <i class="fas fa-chevron-left"></i>
                </button>
                <span class="pagination-info">{{ tagPage }} / {{ totalTagPages }}</span>
                <button class="pagination-btn" @click="tagPage++" :disabled="tagPage >= totalTagPages">
                  <i class="fas fa-chevron-right"></i>
                </button>
              </div>
            </div>
            <div class="filter-item" style="flex: 1;">
              <label class="filter-label">
                <i class="fas fa-chart-line"></i> 评估维度筛选（多选）
                <span class="filter-hint" v-if="selectedMetrics.length === 0">(显示全部)</span>
                <span class="filter-count" v-else>已选 {{ selectedMetrics.length }} 个</span>
              </label>
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
              <div class="metric-filter" :class="{ 'has-pagination': paginatedMetrics.length > 0 }">
                <div 
                  v-for="metric in paginatedMetrics" 
                  :key="metric.name"
                  :class="['metric-filter-item', { active: selectedMetrics.includes(metric.name) }]"
                  @click="toggleMetric(metric.name)"
                >
                  <i class="fas fa-check-circle"></i>
                  {{ metric.name }}
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
            <div class="filter-item" style="flex: 1;">
              <label class="filter-label">
                <i class="fas fa-sort"></i> 排序方式
              </label>
              <div class="sort-filter">
                <div class="sort-filter-row">
                  <select class="filter-select" v-model="sortDimension">
                    <option value="name">按名称</option>
                    <option value="category">按分组</option>
                    <option value="createdAt">按创建时间</option>
                    <option value="评估维度">按评估维度</option>
                  </select>
                  <select class="filter-select" v-model="selectedSortMetric" v-if="sortDimension === '评估维度'">
                    <option v-for="metric in actualAllMetrics" :key="metric.name" :value="metric.name">{{ metric.name }}</option>
                  </select>
                  <select class="filter-select" v-model="sortOrder">
                    <option value="asc">升序</option>
                    <option value="desc">降序</option>
                  </select>
                </div>
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

    <!-- Pinned Cases Section -->
    <div v-if="pinnedCases.length > 0" class="pinned-section">
      <h4 class="pinned-title">已固定用例</h4>
      <div class="pinned-list">
        <div 
          v-for="caseItem in pinnedCases" 
          :key="caseItem.id"
          class="pinned-case-card"
        >
          <div class="pinned-case-header">
            <h5 class="pinned-case-name">{{ caseItem.name }}</h5>
            <button 
              class="unpin-btn"
              @click="togglePin(caseItem.id)"
              title="取消固定"
            >
              <i class="fas fa-thumbtack"></i>
            </button>
          </div>
          <div class="pinned-case-status">
            <span 
              v-for="res in (Array.isArray(caseItem.results) ? caseItem.results : [])"
              :key="res.resource"
              :class="['status-badge', String(res.status || '').toLowerCase()]"
            >
              {{ getResourceLabel(res.resource) }}{{ res.status}}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Case List -->
    <div class="case-list">
      <div 
        v-for="caseItem in paginatedCasesWithPreparedData" 
        :key="caseItem.id"
        class="case-card"
      >
        <!-- Case Header -->
        <div class="case-header" @click="toggleCaseExpand(caseItem.id)">
          <div class="case-info-wrapper">
            <div class="case-info">
              <div class="case-name-status">
                <span 
                  class="status-indicator"
                  :class="getOverallStatus(caseItem)"
                ></span>
                <div class="case-name">{{ caseItem.name }}</div>
                <span class="case-category">{{ caseItem.category || '未分类' }}</span>
                <span v-if="caseItem.id" class="case-id-badge" @click.stop="copyToClipboard(caseItem.id)" title="点击复制ID">
                  <i class="fas fa-copy"></i> 用例ID: {{ caseItem.id }}
                </span>
              </div>
              <div class="case-tags-container" v-if="caseItem.tags && caseItem.tags.length > 0">
                <div class="case-tags">
                  <span v-for="tag in caseItem.tags" :key="typeof tag === 'object' ? tag.name : tag" class="tag">{{ typeof tag === 'object' ? tag.name : tag }}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="case-actions">
            <button
              class="download-log-btn"
              @click.stop="downloadCaseLogZip(caseItem)"
              title="下载日志"
            >
              <i class="fas fa-download"></i>
              <span>下载日志</span>
            </button>
            <span class="expand-icon">
              <i class="fas" :class="expandedCases.includes(caseItem.id) ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
            </span>
          </div>
        </div>

        <!-- Case Details -->
        <div class="case-details" v-if="expandedCases.includes(caseItem.id)">
          <!-- Case Description -->
          <div class="case-description">
            <h5 class="detail-section-title">用例描述</h5>
            <p>{{ caseItem.description }}</p>
          </div>

          <!-- Using Unified Component for Audio, ASR, and Metrics -->
          <TestCaseReportDetail 
            :isComparison="true"
            :devices="allDevices"
            :resourceHeaders="resourceHeaders"
            :comparisonData="caseItem._preparedComparisonData"
            :metricConfigs="actualAllMetrics"
            :audioList="caseItem._preparedAudioList"
            :referenceAsr="caseItem._preparedReferenceAsr"
            :referenceTrans="caseItem._preparedReferenceTrans"
            :algorithmResults="caseItem._preparedAlgorithmResults"
            :referenceParams="caseItem._preparedReferenceParams"
            :algorithmType="caseItem._preparedAlgorithmType"
            :fieldMapping="caseItem._preparedFieldMapping"
            :results="caseItem.results || []"
          />
        </div>
      </div>
    </div>

    <PaginationComponent
      v-if="totalCases > 0"
      class="specific-case-pagination"
      :currentPage="currentPage"
      :pageSize="pageSize"
      :totalItems="totalCases"
      @prev-page="handlePrevPage"
      @next-page="handleNextPage"
      @go-to-page="handleGoToPage"
      @page-size-change="handlePageSizeChange"
    />

    <!-- Case Detail Modal -->
    <teleport to="body">
    <div v-if="currentCaseDetailWithPreparedData" class="modal-overlay">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3 class="modal-title">{{ currentCaseDetailWithPreparedData.name }} - 详情</h3>
          <button class="modal-close-btn" @click="closeCaseDetail">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <!-- Using Unified Component for Modal Detail -->
          <TestCaseReportDetail 
            :isComparison="true"
            :devices="allDevices"
            :resourceHeaders="resourceHeaders"
            :comparisonData="currentCaseDetailWithPreparedData._preparedComparisonData"
            :metricConfigs="actualAllMetrics"
            :audioList="currentCaseDetailWithPreparedData._preparedAudioList"
            :referenceAsr="currentCaseDetailWithPreparedData._preparedReferenceAsr"
            :referenceTrans="currentCaseDetailWithPreparedData._preparedReferenceTrans"
            :algorithmResults="currentCaseDetailWithPreparedData._preparedAlgorithmResults"
            :referenceParams="currentCaseDetailWithPreparedData._preparedReferenceParams"
            :algorithmType="currentCaseDetailWithPreparedData._preparedAlgorithmType"
            :fieldMapping="currentCaseDetailWithPreparedData._preparedFieldMapping"
            :results="currentCaseDetailWithPreparedData.results || []"
          />

          <!-- Detailed Logs -->
          <div class="logs-section">
            <h5 class="detail-section-title">详细日志</h5>
            <div class="logs-container">
              <pre class="logs-text">{{ currentCaseDetailWithPreparedData.logs || '暂无日志信息' }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
    </teleport>

    <!-- Audio Player Modal -->
    <AudioPlayerModal
      v-if="showAudioModal"
      :visible="showAudioModal"
      :audioId="currentAudioId"
      :audioTitle="currentAudioTitle"
      :audioType="currentAudioType"
      :title="currentAudioTypeLabel"
      :spl="currentAudioSpl"
      :playOrder="currentAudioPlayOrder"
      :noiseSpl="currentAudioNoiseSpl"
      :deviceName="currentAudioDeviceName"
      @close="showAudioModal = false"
    />

    <!-- Download Progress Modal -->
    <teleport to="body">
      <div v-if="isDownloadingLog" class="download-loading-overlay">
        <div class="download-loading-modal">
          <div class="download-loading-spinner"></div>
          <div class="download-loading-title">正在下载日志</div>
          <div class="download-loading-text">{{ downloadingCaseName }}</div>
          <div class="download-progress-bar-container">
            <div class="download-progress-bar" :style="{ width: downloadProgress + '%' }"></div>
          </div>
          <div class="download-progress-info">
            <span>{{ downloadProgress }}%</span>
            <span v-if="downloadSize && downloadTotal">{{ downloadSize }} / {{ downloadTotal }}</span>
            <span v-if="downloadSpeed">{{ downloadSpeed }}</span>
          </div>
        </div>
      </div>
    </teleport>
    </div>
  </div>
</template>

<script setup>
import AudioPlayerModal from '../common/audio/AudioPlayerModal.vue'
import TestCaseReportDetail from '../common/misc/TestCaseReportDetail.vue'
import PaginationComponent from '../common/data/PaginationComponent.vue'
import '../../assets/styles/components/report-filter-card.css'
import { useSpecificCaseComparison } from './SpecificCaseComparisonComponent'

const props = defineProps({
  reportData: {
    type: Object, default: () => ({})
  }
})

const {
  showAudioModal,
  currentAudioId,
  currentAudioTitle,
  currentAudioTypeLabel,
  currentAudioType,
  currentAudioSpl,
  currentAudioPlayOrder,
  currentAudioNoiseSpl,
  currentAudioDeviceName,
  isCollapsed,
  toggleCollapse,
  casesLoading,
  casesLoadError,
  searchKeyword,
  selectedCategories,
  categorySearchQuery,
  paginatedCategories,
  toggleCategoryFilter,
  filteredCategoriesForSelection,
  categoryPage,
  categoryPageSize,
  totalCategoryPages,
  selectedTags,
  tagSearchQuery,
  paginatedTags,
  toggleTag,
  filteredTags,
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
  sortDimension,
  selectedSortMetric,
  sortOrder,
  actualAllMetrics,
  resetFilters,
  applyFilters,
  pinnedCases,
  togglePin,
  getResourceLabel,
  resourceHeaders,
  paginatedCasesWithPreparedData,
  toggleCaseExpand,
  getOverallStatus,
  copyToClipboard,
  downloadCaseLogZip,
  expandedCases,
  allDevices,
  unpinnedFilteredCases,
  totalCases,
  currentPage,
  pageSize,
  handlePrevPage,
  handleNextPage,
  handleGoToPage,
  handlePageSizeChange,
  currentCaseDetailWithPreparedData,
  closeCaseDetail,
  isDownloadingLog,
  downloadingCaseName,
  downloadProgress,
  downloadSpeed,
  downloadSize,
  downloadTotal
} = useSpecificCaseComparison(props)
</script>

<style scoped>
@import './SpecificCaseComparisonComponent.css';
</style>
