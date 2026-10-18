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
      <div v-else-if="casesLoadError" class="no-data-tip" style="margin-bottom: 12px; color: var(--destructive);">
        {{ casesLoadError }}
      </div>
      <!-- Filter Section -->
      <div class="report-filter-card filter-card">
        <div class="filter-title">
          <i class="fas fa-filter" style="color: var(--primary); font-size: 18px;"></i>
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
            <div class="filter-item category-filter-section flex-1">
              <label class="filter-label">
                <i class="fas fa-list-check"></i> 用例分组
                <span class="filter-hint" v-if="selectedCategories.length === 0">(显示全部)</span>
                <span class="filter-count" v-else>已选 {{ selectedCategories.length }} 个</span>
              </label>
              <div class="category-search-box search-box-flex flex items-center">
                <i class="fas fa-search search-icon"></i>
                <input 
                  type="text" 
                  v-model="categorySearchQuery" 
                  placeholder="搜索分组..." 
                  class="search-input"
                />
                <button class="search-clear ml-auto" :class="{ visible: categorySearchQuery }" @click="categorySearchQuery = ''">
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
            <div class="filter-item flex-1">
              <label class="filter-label">
                <i class="fas fa-tag" style="color: var(--primary);"></i> 标签筛选
                <span class="filter-hint" v-if="selectedTags.length === 0">(显示全部)</span>
                <span class="filter-count" v-else>已选 {{ selectedTags.length }} 个</span>
              </label>
              <div class="tag-search-box search-box-flex flex items-center">
                <i class="fas fa-search search-icon"></i>
                <input 
                  type="text" 
                  v-model="tagSearchQuery" 
                  placeholder="搜索标签..." 
                  class="search-input"
                />
                <button class="search-clear ml-auto" :class="{ visible: tagSearchQuery }" @click="tagSearchQuery = ''">
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
            <div class="filter-item flex-1">
              <label class="filter-label">
                <i class="fas fa-chart-line"></i> 评估维度筛选（多选）
                <span class="filter-hint" v-if="selectedMetrics.length === 0">(显示全部)</span>
                <span class="filter-count" v-else>已选 {{ selectedMetrics.length }} 个</span>
              </label>
              <div class="metric-search-box search-box-flex flex items-center">
                <i class="fas fa-search search-icon"></i>
                <input 
                  type="text" 
                  v-model="metricSearchQuery" 
                  placeholder="搜索评估维度..." 
                  class="search-input"
                />
                <button class="search-clear ml-auto" :class="{ visible: metricSearchQuery }" @click="metricSearchQuery = ''">
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
            <div class="filter-item flex-1">
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
                  <select class="filter-select" v-model="selectedSortResource" v-if="sortDimension === '评估维度'">
                    <option value="">全部资源(平均)</option>
                    <option v-for="res in sortResourceOptions" :key="res.key" :value="res.key">{{ res.label }}</option>
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

          <!-- INT-797：复核状态筛选（§4.1 筛选） -->
          <div class="filter-row review-filter-row">
            <div class="filter-item flex-1">
              <label class="filter-label">
                <i class="fas fa-clipboard-check review-filter-icon"></i> 复核状态
              </label>
              <div class="review-filter-options">
                <button
                  v-for="opt in reviewFilterOptions"
                  :key="opt.value"
                  class="review-filter-option"
                  :class="{ active: reviewFilter === opt.value }"
                  @click="reviewFilter = opt.value"
                >
                  {{ opt.label }}
                </button>
              </div>
            </div>
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
                <CaseIdBadge v-if="caseItem.id" :case-id="caseItem.id" />
                <!-- INT-797：用例卡片「人工复核」Badge + 明细（§4.1 卡片标记/明细） -->
                <CaseReviewBadge
                  v-if="getCaseReview(caseItem).hasReview"
                  :case-name="caseItem.name"
                  :count="getCaseReview(caseItem).count"
                  :items="getCaseReview(caseItem).items"
                />
              </div>
              <div class="case-tags-container" v-if="caseItem.tags && caseItem.tags.length > 0">
                <div class="case-tags">
                  <span v-for="tag in caseItem.tags" :key="typeof tag === 'object' ? tag.name : tag" class="tag">{{ typeof tag === 'object' ? tag.name : tag }}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="case-actions">
            <!-- INT-797：双路径入口 A——跳来源任务复核（§4.2） -->
            <button
              v-if="canManualReview && hasSourceTask"
              class="review-action-btn review-manual-btn"
              @click.stop="handleManualReview(caseItem)"
              title="人工复核：改判执行/评估状态并填写原因"
            >
              <i class="fas fa-clipboard-check"></i>
              <span>人工复核</span>
            </button>
            <!-- INT-797：AI 复核入口（§4.3，待后端立项） -->
            <button
              v-if="canManualReview && hasSourceTask"
              class="review-action-btn review-ai-btn"
              @click.stop="handleAiReview(caseItem)"
              title="AI 复核：由大模型复检当前评估结果"
            >
              <i class="fas fa-sparkles"></i>
              <span>AI 复核</span>
            </button>
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

    <!-- INT-797：AI 复核发起弹窗 + 结论卡 + 人工处置（§4.3） -->
    <AiReviewDialog
      :visible="aiReviewDialogVisible"
      :case-name="aiReviewCaseName"
      :dimension-name="aiReviewDimensionName"
      :original-evaluation-status="aiReviewOriginalEvaluationStatus"
      :phase="aiReviewPhase"
      :record="aiReviewRecord"
      :error="aiReviewError"
      :initiating="aiReviewInitiating"
      @close="closeAiReviewDialog"
      @initiate="initiateAiReviewForDialog"
      @adopt="adoptAiReviewForDialog"
      @reject="rejectAiReviewForDialog"
      @ignore="ignoreAiReviewForDialog"
    />
    </div>
  </div>
</template>

<script setup>
import AudioPlayerModal from '../common/audio/AudioPlayerModal.vue'
import TestCaseReportDetail from '../common/misc/TestCaseReportDetail.vue'
import PaginationComponent from '../common/data/PaginationComponent.vue'
import CaseIdBadge from '../common/CaseIdBadge.vue'
import CaseReviewBadge from './CaseReviewBadge.vue'
import AiReviewDialog from './AiReviewDialog.vue'
import { useAuthStore } from '@/store/authStore'
import { AuthMode, getEffectiveAuthMode } from '@/domain/enums'
import { computed, ref } from 'vue'
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
  selectedSortResource,
  sortResourceOptions,
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
  downloadTotal,
  reportReviews,
  isCaseFilteredByReview,
  reviewFilter
} = useSpecificCaseComparison(props)

// INT-797：复核筛选选项
const reviewFilterOptions = [
  { value: 'all', label: '全部' },
  { value: 'reviewed', label: '已复核' },
  { value: 'unreviewed', label: '未复核' },
]

// INT-797：人工复核/AI 复核权限（按钮级 task.result.review）
const authStore = useAuthStore()
const canManualReview = computed(() => {
  // AUTH_MODE=off（后端注入 permissions=['*']）全量放行（对齐基座 §9.1 兼容口径）
  if (getEffectiveAuthMode() === AuthMode.OFF) return true
  return authStore.hasPermission('task.result.review')
})

/** 报告是否有来源任务（任务报告有 report.taskId；对比/合并报告无单一来源任务时隐藏复核入口） */
const hasSourceTask = computed(() => {
  return reportReviews.sourceTaskId.value !== ''
})

/** 取用例复核态（驱动 Badge 显隐/明细） */
const getCaseReview = (caseItem) => {
  return reportReviews.getCaseReview(caseItem?.id ?? caseItem?.testCaseId ?? '')
}

/** 双路径入口 A：跳来源任务复核（§3.2 复核弹窗） */
const handleManualReview = (caseItem) => {
  reportReviews.openManualReview(caseItem)
}

// ---- AI 复核（§4.3）弹窗状态 ----
const aiReviewDialogVisible = ref(false)
const aiReviewCase = ref(null)
const aiReviewCaseName = ref('')
const aiReviewDimensionName = ref('')
const aiReviewOriginalEvaluationStatus = ref('')
const aiReviewInitiating = ref(false)

const aiReviewPhase = ref('idle')
const aiReviewRecord = ref(null)
const aiReviewError = ref('')

const closeAiReviewDialog = () => {
  if (aiReviewPhase.value === 'running') return // 执行中不关闭
  aiReviewDialogVisible.value = false
  aiReviewCase.value = null
  aiReviewPhase.value = 'idle'
  aiReviewRecord.value = null
  aiReviewError.value = ''
}

const handleAiReview = (caseItem) => {
  aiReviewCase.value = caseItem
  aiReviewCaseName.value = caseItem?.name ?? '用例'
  aiReviewDimensionName.value = ''
  aiReviewOriginalEvaluationStatus.value = ''
  const key = String(caseItem?.id ?? '')
  const run = reportReviews.aiReviewMap.value[key]
  aiReviewPhase.value = run?.phase ?? 'idle'
  aiReviewRecord.value = run?.record ?? null
  aiReviewError.value = run?.error ?? ''
  aiReviewDialogVisible.value = true
}

const initiateAiReviewForDialog = async () => {
  if (!aiReviewCase.value) return
  aiReviewInitiating.value = true
  try {
    await reportReviews.initiateAiReview(aiReviewCase.value)
    const key = String(aiReviewCase.value?.id ?? '')
    const run = reportReviews.aiReviewMap.value[key]
    aiReviewPhase.value = run?.phase ?? 'idle'
    aiReviewRecord.value = run?.record ?? null
    aiReviewError.value = run?.error ?? ''
  } finally {
    aiReviewInitiating.value = false
  }
}

const adoptAiReviewForDialog = async () => {
  if (!aiReviewCase.value) return
  await reportReviews.adoptAiReview(aiReviewCase.value)
  const key = String(aiReviewCase.value?.id ?? '')
  const run = reportReviews.aiReviewMap.value[key]
  aiReviewPhase.value = run?.phase ?? 'idle'
  if (aiReviewPhase.value === 'adopted') {
    aiReviewDialogVisible.value = false
  }
}

const rejectAiReviewForDialog = async () => {
  if (!aiReviewCase.value) return
  await reportReviews.rejectAiReview(aiReviewCase.value)
  const key = String(aiReviewCase.value?.id ?? '')
  const run = reportReviews.aiReviewMap.value[key]
  aiReviewPhase.value = run?.phase ?? 'idle'
}

const ignoreAiReviewForDialog = () => {
  if (!aiReviewCase.value) return
  reportReviews.ignoreAiReview(aiReviewCase.value)
  aiReviewDialogVisible.value = false
}
</script>

<style scoped>@import './SpecificCaseComparisonComponent.css';



.case-tags{
flex-wrap: wrap ;
width: 100% ;
box-sizing: border-box;
}

.modal-close-btn{
  background: transparent;
  border: none;
  color: var(--color-slate-500);
  cursor: pointer;
  font-size: 20px;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.modal-close-btn:hover{
  color: var(--color-slate-700);
  background: var(--color-slate-100);
  border-radius: 4px;
}

/* detail-section-title - 自全局样式就近迁移 */


/* case-actions - 自全局样式就近迁移 */
@media (max-width: 1024px){
.case-actions {
    align-self: flex-end;
}
}

.case-actions{
display: flex;
gap: 8px;
align-items: flex-start;
justify-content: flex-end;
}

/* INT-797：复核操作按钮（人工复核 / AI 复核） */
.review-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
  border: 1px solid var(--border);
  background: var(--muted);
  color: var(--foreground);
}
.review-action-btn:hover {
  border-color: color-mix(in srgb, var(--primary) 50%, transparent);
  color: var(--primary);
}
.review-manual-btn i {
  color: var(--primary);
}
.review-ai-btn i {
  color: var(--info);
}

/* INT-797：复核状态筛选选项 */
.review-filter-row {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}
.review-filter-icon {
  color: var(--primary);
}
.review-filter-options {
  display: inline-flex;
  gap: 8px;
}
.review-filter-option {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--background);
  color: var(--foreground);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.review-filter-option:hover {
  border-color: var(--primary);
  color: var(--primary);
}
.review-filter-option.active {
  border-color: var(--primary);
  background: var(--accent);
  color: var(--primary);
  font-weight: 500;
}

</style>
