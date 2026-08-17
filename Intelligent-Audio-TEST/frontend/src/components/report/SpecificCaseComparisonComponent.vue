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
                placeholder="输入用例名称关键词" 
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
                    <option value="tags">按用例标签</option>
                    <option value="createdAt">按创建时间</option>
                    <option value="评估维度">按评估维度</option>
                    <option value="多维度值">按多维度值</option>
                  </select>
                  <select class="filter-select" v-model="selectedSortMetric" v-if="sortDimension === '评估维度' || sortDimension === '多维度值'">
                    <option v-for="metric in actualAllMetrics" :key="metric.name" :value="metric.name">{{ metric.name }}</option>
                  </select>
                  <select class="filter-select" v-model="secondSortMetric" v-if="sortDimension === '多维度值'">
                    <option value="">无</option>
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
            :results="caseItem.results || []"
          />
        </div>
      </div>
    </div>

    <PaginationComponent
      v-if="unpinnedFilteredCases.length > 0"
      class="specific-case-pagination"
      :currentPage="currentPage"
      :pageSize="pageSize"
      :totalItems="unpinnedFilteredCases.length"
      @prev-page="handlePrevPage"
      @next-page="handleNextPage"
      @go-to-page="handleGoToPage"
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
import { ref, computed, watch, onUnmounted } from 'vue'
import AudioPlayerModal from '../common/AudioPlayerModal.vue'
import TestCaseReportDetail from '../common/TestCaseReportDetail.vue'
import PaginationComponent from '../common/PaginationComponent.vue'
import { reportsApi } from '../../utils/api'
import { API_CONFIG } from '../../utils/config'
import { useNotification } from '../../composables/useNotification'
import '../../assets/styles/components/report-filter-card.css'

// Audio player state
const showAudioModal = ref(false)
const currentAudioId = ref(null)
const currentAudioTitle = ref('')
const currentAudioTypeLabel = ref('')
const currentAudioType = ref('api')
const currentAudioSpl = ref(null)
const currentAudioPlayOrder = ref(null)
const currentAudioNoiseSpl = ref(null)
const currentAudioDeviceName = ref(null)

const playAudio = (audio, typeLabel = '', type = 'api') => {
  if (!audio || (!audio.id && !audio.url)) return
  currentAudioId.value = audio.id
  currentAudioTitle.value = audio.filename || audio.label || '未知音频'
  currentAudioTypeLabel.value = typeLabel || audio.label || '测试音频'
  currentAudioType.value = type
  currentAudioSpl.value = audio.spl || null
  currentAudioPlayOrder.value = audio.play_order || null
  currentAudioNoiseSpl.value = audio.noise_spl || null
  currentAudioDeviceName.value = audio.device_name || null
  showAudioModal.value = true
}

// Collapse state
const isCollapsed = ref(false)

// Collapse toggle method
const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

// Props
const props = defineProps({
  reportData: {
    type: Object, default: () => ({})
  }
})

const resourceHeaders = computed(() => {
  const data = props.reportData || {}
  return (
    data.resourceHeaders ||
    data.resource_headers ||
    data.summary?.resourceHeaders ||
    data.summary?.resource_headers ||
    []
  )
})

const resourceHeaderMap = computed(() => {
  const data = props.reportData || {}
  const headers =
    data.resourceHeaders ||
    data.resource_headers ||
    data.summary?.resourceHeaders ||
    data.summary?.resource_headers ||
    []

  const map = {}
  if (Array.isArray(headers)) {
    headers.forEach(h => {
      if (!h) return
      const key = h.key || h.resource
      const label = h.label || h.name || key
      if (key) map[String(key)] = String(label || key)
    })
  }
  return map
})

const getResourceLabel = (resourceKey) => {
  const key = String(resourceKey ?? '')
  const mapped = resourceHeaderMap.value?.[key]
  if (mapped) return mapped
  return resourceKey
}

// Data
const searchKeyword = ref('')
const selectedCategories = ref([])
const categorySearchQuery = ref('')
const categoryPage = ref(1)
const categoryPageSize = ref(50)

const filteredCategoriesForSelection = computed(() => {
  if (!categorySearchQuery.value.trim()) {
    return categories.value
  }
  const query = categorySearchQuery.value.toLowerCase()
  return categories.value.filter(cat => cat.toLowerCase().includes(query))
})

const totalCategoryPages = computed(() => Math.ceil(filteredCategoriesForSelection.value.length / categoryPageSize.value) || 1)

const paginatedCategories = computed(() => {
  const start = (categoryPage.value - 1) * categoryPageSize.value
  const end = start + categoryPageSize.value
  return filteredCategoriesForSelection.value.slice(start, end)
})

// 处理标签：如果是对象数组，提取name属性
const processTags = (tags) => {
  if (!tags) return []
  if (!Array.isArray(tags)) return []
  return tags.map(tag => typeof tag === 'object' ? tag.name : tag)
}

// 处理类别：如果是对象数组，提取name属性
const processCategories = (categories) => {
  if (!categories) return []
  if (!Array.isArray(categories)) return []
  return categories.map(cat => typeof cat === 'object' ? cat.name : cat)
}

const selectedTags = ref([])
const selectedMetrics = ref([])
const sortDimension = ref('name')
const selectedSortMetric = ref('')
const secondSortMetric = ref('')  // 第二个排序维度（用于多维度排序）
const sortOrder = ref('asc')
const expandedCases = ref([])
const pinnedCases = ref([])
const currentCaseDetail = ref(null)
const casesLoading = ref(false)
const casesLoadError = ref('')
const isDownloadingLog = ref(false)
const downloadingCaseName = ref('')
const downloadProgress = ref(0)
const downloadSpeed = ref('')
const downloadSize = ref('')
const downloadTotal = ref('')

const currentCaseDetailWithPreparedData = computed(() => {
  if (!currentCaseDetail.value) return null
  const caseItem = currentCaseDetail.value
  return {
    ...caseItem,
    _preparedComparisonData: prepareComparisonData(caseItem),
    _preparedAudioList: prepareAudioList(caseItem),
    _preparedReferenceAsr: caseItem.asr?.referenceText || caseItem.asr?.reference_text || '',
    _preparedReferenceTrans: caseItem.translation?.referenceText || caseItem.translation?.reference_text || '',
    _preparedAlgorithmResults: getAlgorithmResults(caseItem),
    _preparedReferenceParams: caseItem.referenceParams || caseItem.reference_params || {},
    _preparedAlgorithmType: caseItem.algorithmType || caseItem.algorithm_type || ''
  }
})

// Search and pagination for tags
const tagSearchQuery = ref('')
const tagPage = ref(1)
const tagPageSize = ref(50)

const filteredTags = computed(() => {
  if (!tagSearchQuery.value.trim()) {
    return allTags.value
  }
  const query = tagSearchQuery.value.toLowerCase()
  return allTags.value.filter(tag => tag.toLowerCase().includes(query))
})

const totalTagPages = computed(() => Math.ceil(filteredTags.value.length / tagPageSize.value) || 1)

const paginatedTags = computed(() => {
  const start = (tagPage.value - 1) * tagPageSize.value
  const end = start + tagPageSize.value
  return filteredTags.value.slice(start, end)
})

// Search and pagination for metrics
const metricSearchQuery = ref('')
const metricPage = ref(1)
const metricPageSize = ref(30)

const filteredMetricsForDisplay = computed(() => {
  if (!metricSearchQuery.value.trim()) {
    return actualAllMetrics.value
  }
  const query = metricSearchQuery.value.toLowerCase()
  return actualAllMetrics.value.filter(metric => metric.name.toLowerCase().includes(query))
})

const totalMetricPages = computed(() => Math.ceil(filteredMetricsForDisplay.value.length / metricPageSize.value) || 1)

const paginatedMetrics = computed(() => {
  const start = (metricPage.value - 1) * metricPageSize.value
  const end = start + metricPageSize.value
  return filteredMetricsForDisplay.value.slice(start, end)
})

// 从reportData中获取数据，优先使用reportData直接提供的数据，然后再使用summary中的数据
// 注意：二次对比报告中用例分组存储在caseCategories字段中，而不是categories字段中
const categories = ref(processCategories(props.reportData.categories || props.reportData.summary?.categories || props.reportData.summary?.caseCategories))
const allTags = ref(processTags(props.reportData.allTags || props.reportData.summary?.allTags || props.reportData.summary?.allCaseTags))

// 所有评测维度，确保至少有一个默认维度
const allMetrics = ref(props.reportData.allMetrics || props.reportData.summary?.allMetrics || [])

// 计算实际使用的评测维度
const actualAllMetrics = computed(() => {
  // 优先使用props提供的维度
  let metrics = allMetrics.value || [];
  
  console.log('actualAllMetrics - allMetrics.value:', allMetrics.value)
  console.log('actualAllMetrics - cases.value:', cases.value)
  
  // 如果没有提供维度，从cases数据中提取所有维度
  if (metrics.length === 0 && cases.value.length > 0) {
    const dimensionSet = new Set();
    cases.value.forEach(caseItem => {
      console.log('actualAllMetrics - caseItem.metrics:', caseItem.metrics)
      // 支持新的数组格式和旧的对象格式
      const metricsData = caseItem.metrics
      if (Array.isArray(metricsData)) {
        metricsData.forEach(m => {
          if (m && m.metric) {
            dimensionSet.add(m.metric);
          }
        });
      } else if (metricsData && typeof metricsData === 'object') {
        Object.keys(metricsData).forEach(dimName => {
          dimensionSet.add(dimName);
        });
      }
    });
    
    console.log('actualAllMetrics - dimensionSet:', dimensionSet)
    
    // 将提取的维度转换为所需格式
    metrics = Array.from(dimensionSet).map(dimName => ({
      name: dimName,
      unit: '%' // 默认单位
    }));
  }
  
  // 如果仍然没有维度，添加默认维度
  if (metrics.length === 0) {
    metrics = [{ name: 'WER', unit: '%' }];
  }

  const usedMetricNames = new Set()
  const allCases = cases.value || []
  if (allCases.length > 0) {
    allCases.forEach(caseItem => {
      const metricsData = caseItem.metrics
      if (Array.isArray(metricsData)) {
        metricsData.forEach(m => {
          if (m && m.metric && typeof m.value === 'number') {
            usedMetricNames.add(m.metric)
          }
        })
      } else if (metricsData && typeof metricsData === 'object') {
        Object.entries(metricsData).forEach(([metricName, metricValue]) => {
          const n = typeof metricValue === 'number' ? metricValue : Number(metricValue)
          if (Number.isFinite(n)) usedMetricNames.add(metricName)
        })
      }
    })
  }

  if (usedMetricNames.size > 0) {
    metrics = metrics.filter(m => m?.name && usedMetricNames.has(m.name))
    if (metrics.length === 0) {
      metrics = [{ name: 'WER', unit: '%' }]
    }
  }
  
  console.log('actualAllMetrics - final metrics:', metrics)
  return metrics;
})

// 设备/API列表
// 使用??替代||，并检查数组长度，确保空数组不会被当作有效值
const getValidResources = (data) => {
  const resources = [
    data.resources,
    data.devices,
    data.apis,
    data.summary?.resources,
    data.summary?.apis,
    data.summary?.devices
  ];
  
  for (const resource of resources) {
    if (Array.isArray(resource) && resource.length > 0) {
      return resource;
    }
  }
  return [];
};

const devices = ref(getValidResources(props.reportData));

const normalizeAudioFields = (caseItem, taskType) => {
  if (!caseItem || typeof caseItem !== 'object') return caseItem
  const normalized = { ...caseItem }

  // 用例级 testType 是测试用例/任务的属性，作为音频类型的兜底
  const caseTestType = normalized.testType ?? normalized.test_type ?? taskType ?? 'api'

  if (normalized.audios && Array.isArray(normalized.audios) && normalized.audios.length > 0) {
    normalized.audioList = normalized.audios.map((audio, idx) => {
      let typeLabel = '测试音频'
      const audioType = audio.testType ?? audio.audioType ?? audio.test_type ?? audio.audio_type ?? caseTestType
      if (audioType === 'api') {
        typeLabel = 'API测试音频'
      } else if (audioType === 'e2e') {
        typeLabel = 'E2E测试音频'
      } else if (audioType === 'noise') {
        typeLabel = '噪声'
      } else if (audioType === 'dry') {
        typeLabel = '干声'
      }
      
      return {
        id: audio.id,
        path: audio.url ?? audio.path,
        label: audio.label ?? audio.filename ?? `${typeLabel} ${idx + 1}`,
        type: audioType,
        filename: audio.filename,
        duration: audio.duration,
        spl: audio.spl,
        playOrder: audio.playOrder ?? audio.play_order,
        noiseSpl: audio.noiseSpl ?? audio.noise_spl,
        deviceId: audio.playbackDeviceId ?? audio.deviceId ?? audio.device_id,
        deviceName: audio.playbackDeviceName ?? audio.deviceName ?? audio.device_name,
        timelineStart: audio.timelineStart ?? audio.timeline_start ?? 0,
        timelineEnd: audio.timelineEnd ?? audio.timeline_end ?? (audio.timelineStart ?? 0 + (audio.duration || 0)),
        roundNumber: audio.roundNumber ?? audio.round_number
      }
    })
  }

  return normalized
}

// 从reportData中提取用例数据
// 优先级：1. /api/v1/reports/{id}/cases/search API 2. testReportsCases 3. reportData.cases 4. summary.cases 5. detailedResults
const extractCasesFromReportData = (reportData) => {
  // 优先级1: 使用 test_reports_cases 字段（新格式）
  if (reportData.testReportsCases && Array.isArray(reportData.testReportsCases) && reportData.testReportsCases.length > 0) {
    console.log('从 testReportsCases 提取用例数据')
    const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
    return reportData.testReportsCases.map(c => normalizeAudioFields(c, taskType))
  }
  
  // 优先级2: 使用 reportData.cases
  if (reportData.cases && Array.isArray(reportData.cases) && reportData.cases.length > 0) {
    console.log('从 reportData.cases 提取用例数据')
    const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
    return reportData.cases.map(c => normalizeAudioFields(c, taskType))
  }
  
  // 优先级3: 使用 summary.cases
  if (reportData.summary?.cases && Array.isArray(reportData.summary.cases) && reportData.summary.cases.length > 0) {
    console.log('从 summary.cases 提取用例数据')
    const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
    return reportData.summary.cases.map(c => normalizeAudioFields(c, taskType))
  }
  
  // 优先级4: 使用 detailedResults
  if (reportData.detailedResults && Array.isArray(reportData.detailedResults) && reportData.detailedResults.length > 0) {
    console.log('从 detailedResults 提取用例数据')
    // 从detailedResults中提取数据，构建cases
    const casesMap = new Map();
    
    reportData.detailedResults.forEach(result => {
      // 兼容后端返回的 test_case_id 格式
      const testCaseId = result.testCaseId ?? result.test_case_id ?? result.testCase?.id;
      const testCaseName = result.testCaseName ?? result.test_case_name ?? result.testCase?.name ?? '未知用例';
      
      if (!testCaseId) return;
      
      // 确定资源名称（设备或API）
      let resourceName = '';
      let resourceKey = '';
      if (result.device) {
        resourceName = result.device.name;
        resourceKey = `${result.device.id}_${resourceName}`;
      } else if (result.api) {
        resourceName = result.api.name;
        resourceKey = `${result.api.id}_${resourceName}`;
      } else {
        resourceName = '默认资源';
        resourceKey = `default_${resourceName}`;
      }
      
      // 初始化或获取caseItem
      let caseItem = casesMap.get(testCaseId);
      if (!caseItem) {
        const asrRef = result.asr?.referenceText ?? result.asr?.reference_text ?? ''
        const tranRef = result.translation?.referenceText ?? result.translation?.reference_text ?? ''

        caseItem = {
          id: testCaseId, 
          name: testCaseName, 
          category: result.testCaseGroup?.name ?? result.test_case_group?.name ?? result.testCaseType ?? result.test_case_type ?? '其他', 
          description: result.description || '', 
          tags: processTags(result.testCaseTags ?? result.test_case_tags ?? []),
          audios: result.audios ?? [],
          asr: {
            referenceText: asrRef,
            results: {}
          },
          translation: {
            referenceText: tranRef,
            results: {}
          },
          metrics: {},
          results: [],
          logs: result.logs ?? ''
        };
        casesMap.set(testCaseId, caseItem);
      }
      
      // 更新audios字段
      if ((!caseItem.audios || caseItem.audios.length === 0) && Array.isArray(result.audios) && result.audios.length > 0) {
        caseItem.audios = result.audios;
      }
      
      // 更新ASR结果
      if (result.asr) {
        caseItem.asr.results[resourceKey] = {text: result.asr.resultText ?? result.asr.result_text ?? '', score: 0};
      }
      
      // 更新翻译结果
      if (result.translation) {
        caseItem.translation.results[resourceKey] = {text: result.translation.resultText ?? result.translation.result_text ?? '', score: 0};
      }
      
      // 更新metrics
      if (!caseItem.metrics[resourceKey]) {
        caseItem.metrics[resourceKey] = {};
      }
      
      // 提取维度得分
      const dimensionScores = result.dimensionScores ?? result.dimension_scores;
      if (Array.isArray(dimensionScores)) {
        dimensionScores.forEach(dim => {
          const dimName = dim.dimensionName ?? dim.dimension_name;
          if (dimName) {
            caseItem.metrics[resourceKey][dimName] = dim.score;
          }
        });
      } else if (result.metrics) {
        // 如果没有dimensionScores，尝试从metrics中获取
        Object.entries(result.metrics).forEach(([dimName, value]) => {
          caseItem.metrics[resourceKey][dimName] = value;
        });
      }
      
      // 更新results状态
      const createdAt = result.createdAt ?? result.created_at ?? 0;
      if (!Array.isArray(caseItem.results)) {
        caseItem.results = [];
      }
      const existing = caseItem.results.find(r => r.resource === resourceKey);
      const row = { resource: resourceKey, status: result.status || '未知', startTime: createdAt, endTime: createdAt };
      if (existing) {
        Object.assign(existing, row);
      } else {
        caseItem.results.push(row);
      }
    });
    
    const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
    return Array.from(casesMap.values()).map(c => normalizeAudioFields(c, taskType));
  }
  
  // 备选方案：使用reportData中的cases或summary中的cases
  if (reportData.cases) {
    const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
    return (reportData.cases || []).map(c => normalizeAudioFields(c, taskType));
  } else if (reportData.summary?.cases) {
    const taskType = reportData?.taskType || props.reportData?.taskType || 'all'
    return (reportData.summary.cases || []).map(c => normalizeAudioFields(c, taskType));
  }
  
  return [];
};

// 获取用例数据
const cases = ref([])

const normalizeCasesForUi = (caseItems) => {
  const taskType = props.reportData?.taskType || 'all'
  try {
    return (caseItems || []).map(c0 => {
      const c = normalizeAudioFields(c0, taskType)
      if (!c || typeof c !== 'object') return c
      const metricsMap = toMetricsMap(c)
      const asrMap = toTextMap(c.asr)
      const tranMap = toTextMap(c.translation)
      
      const algoResults = c.algorithmResults || c.algorithm_results || c.algorithmResults || []
      const refParams = c.referenceParams || c.reference_params || c.referenceParams || {}
      
      return {
        ...c,
        metrics: metricsMap,
        asr: c.asr ? { ...c.asr, results: asrMap } : c.asr,
        translation: c.translation ? { ...c.translation, results: tranMap } : c.translation,
        algorithm_results: algoResults,
        algorithmType: c.algorithmType || c.algorithm_type || '',
        reference_params: refParams,
        rttmRes: c.rttmRes,
        stmRes: c.stmRes,
        rttmRef: c.rttmRef,
        stmRef: c.stmRef
      }
    })
  } catch (e) {
    console.error('normalizeCasesForUi error:', e)
    return caseItems || []
  }
}

const loadCasesFromApi = async (reportId) => {
  casesLoading.value = true
  casesLoadError.value = ''
  try {
    const perPage = 200
    let page = 1
    let pages = 1
    const allItems = []
    while (page <= pages) {
      const data = await reportsApi.searchCases(reportId, { page, per_page: perPage })
      const items = data?.items || []
      pages = data?.pages || 1
      allItems.push(...items)
      page += 1
      if (allItems.length >= 5000) break
    }
    cases.value = normalizeCasesForUi(allItems)
  } catch (e) {
    console.error('加载报告用例失败:', e)
    casesLoadError.value = e?.message || '加载用例失败'
  } finally {
    casesLoading.value = false
  }
}

// 初始化时优先调用 API 获取用例数据
const initializeCases = async () => {
  const reportId = props.reportData?.id || props.reportData?.reportId
  if (reportId) {
    // 优先调用 API
    console.log('优先调用 /api/v1/reports/{id}/cases/search API 获取用例数据')
    await loadCasesFromApi(reportId)
  }
  
  // 如果 API 返回空数据，尝试从本地数据提取
  if (!cases.value || cases.value.length === 0) {
    console.log('API 返回空数据，尝试从本地数据提取')
    cases.value = extractCasesFromReportData(props.reportData)
  }
}

// 页面加载时初始化 —— 由下方 watch immediate 覆盖，不需要单独调用
// initializeCases() 已移除，避免与 watch immediate 重复调用 search 接口

watch(actualAllMetrics, (newMetrics) => {
  const names = (newMetrics || []).map(m => m?.name).filter(Boolean)
  if (selectedMetrics.value.length > 0) {
    selectedMetrics.value = selectedMetrics.value.filter(n => names.includes(n))
  }
  if (selectedSortMetric.value && !names.includes(selectedSortMetric.value)) {
    selectedSortMetric.value = ''
  }
}, { immediate: true })

// 调试信息：确保cases数据被正确获取
console.log('SpecificCaseComparisonComponent - reportData:', props.reportData)
console.log('SpecificCaseComparisonComponent - cases:', cases.value)
console.log('SpecificCaseComparisonComponent - caseItem.metrics sample:', cases.value.length > 0 ? JSON.stringify(Object.values(cases.value[0].metrics || {})) : 'no cases')
console.log('SpecificCaseComparisonComponent - actualAllMetrics:', actualAllMetrics.value)
console.log('SpecificCaseComparisonComponent - devices:', devices.value)

// 防止同一 reportId 重复加载
let loadedReportId = null

// 监听reportData变化，更新内部状态
watch([
  () => props.reportData?.id,
  () => props.reportData?.reportId,
  () => props.reportData?.cases?.length,
  () => props.reportData?.testReportsCases?.length,
  () => props.reportData?.summary?.cases?.length
], async ([id, reportId, casesLen, testReportsCasesLen, summaryCasesLen], [oldId, oldReportId]) => {
  const newReportData = props.reportData
  
  categories.value = processCategories(newReportData.categories || newReportData.summary?.categories || newReportData.summary?.caseCategories)
  allTags.value = processTags(newReportData.allTags || newReportData.summary?.allTags || newReportData.summary?.allCaseTags)
  allMetrics.value = newReportData.allMetrics || newReportData.summary?.allMetrics || []
  devices.value = getValidResources(newReportData);
  
  const effectiveReportId = id || reportId
  if (effectiveReportId) {
    // 只有在 id 变化时才重新加载用例数据，且跳过已加载过的 reportId
    if (effectiveReportId !== loadedReportId && effectiveReportId !== oldId && effectiveReportId !== oldReportId) {
      loadedReportId = effectiveReportId
      console.log('watch: 优先调用 /api/v1/reports/{id}/cases/search API 获取用例数据')
      await loadCasesFromApi(effectiveReportId)
      
      // 如果 API 返回空数据，尝试从本地数据提取
      if (!cases.value || cases.value.length === 0) {
        console.log('watch: API 返回空数据，尝试从本地数据提取')
        cases.value = extractCasesFromReportData(newReportData)
      }
    }
  } else {
    cases.value = extractCasesFromReportData(newReportData)
  }
  
  // 重置选中状态：默认不选中任何标签/维度（显示全部）
  selectedTags.value = []
  selectedMetrics.value = []
  selectedCategories.value = []
  categorySearchQuery.value = ''
  categoryPage.value = 1
  tagSearchQuery.value = ''
  tagPage.value = 1
  metricSearchQuery.value = ''
  metricPage.value = 1
}, { immediate: true })

const _metricsMapCache = new WeakMap()
const _textMapCache = new WeakMap()

function toMetricsMap(caseItem) {
  if (!caseItem || typeof caseItem !== 'object') return {}
  if (_metricsMapCache.has(caseItem)) {
    return _metricsMapCache.get(caseItem)
  }
  const metrics = caseItem?.metrics
  let result = {}
  if (Array.isArray(metrics)) {
    if (metrics.length > 0 && metrics[0]?.resource) {
      const map = {}
      metrics.forEach(group => {
        if (!group || !group.resource) return
        const resource = group.resource
        if (!map[resource]) map[resource] = {}
        if (Array.isArray(group.metrics)) {
          group.metrics.forEach(m => {
            if (!m || !m.metric) return
            map[resource][m.metric] = m.value
          })
        }
      })
      result = map
    } else {
      const flatMap = {}
      metrics.forEach(m => {
        if (!m || !m.metric) return
        flatMap[m.metric] = m.value
      })
      result = flatMap
    }
  } else {
    result = metrics || {}
  }
  _metricsMapCache.set(caseItem, result)
  return result
}

function toTextMap(objWithResults) {
  if (!objWithResults || typeof objWithResults !== 'object') return {}
  if (_textMapCache.has(objWithResults)) {
    return _textMapCache.get(objWithResults)
  }
  const results = objWithResults?.results
  let result = {}
  if (Array.isArray(results)) {
    const map = {}
    results.forEach(r => {
      if (!r || !r.resource) return
      map[r.resource] = { text: r.text || '' }
    })
    result = map
  } else {
    result = results || {}
  }
  _textMapCache.set(objWithResults, result)
  return result
}

// Computed
const allDevices = computed(() => {
  // 从所有可能的cases数据源中获取设备和API名称
  const allCases = cases.value || []
  if (allCases.length > 0) {
    const resourcesSet = new Set()
    allCases.forEach(caseItem => {
      if (caseItem.asr) {
        const asrMap = toTextMap(caseItem.asr)
        Object.keys(asrMap).forEach(resource => resourcesSet.add(resource))
      }
      if (caseItem.translation) {
        const tranMap = toTextMap(caseItem.translation)
        Object.keys(tranMap).forEach(resource => resourcesSet.add(resource))
      }
      if (caseItem.metrics) {
        const metricsMap = toMetricsMap(caseItem)
        Object.keys(metricsMap).forEach(resource => resourcesSet.add(resource))
      }
    })
    return Array.from(resourcesSet)
  }
  // 如果没有cases，使用devices或resources作为备选
  return devices.value || []
})

// Helper function to extract device/API name from resource key
const getResourceName = (resourceKey) => {
  // 如果资源键包含下划线，提取下划线后面的部分作为显示名称
  // 注意：在对比模式下，后端现在返回 TaskName_ResourceName
  if (resourceKey.includes('_')) {
    const parts = resourceKey.split('_');
    if (parts.length >= 2) {
      // 如果是对比报告，显示 "任务名 - 设备名"
      return `${parts[0]} - ${parts.slice(1).join('_')}`;
    }
    return parts.slice(1).join('_');
  }
  return resourceKey;
}

const filteredCases = computed(() => {
  // 使用我们新定义的cases.value获取案例数据，否则使用空数组
  const caseData = cases.value || []
  
  // First, filter cases based on keyword, category, and tags
  let filtered = caseData.filter(caseItem => {
    // Keyword filter
    const keywordMatch = !searchKeyword.value || 
      caseItem.name.toLowerCase().includes(searchKeyword.value.toLowerCase()) ||
      (caseItem.description && caseItem.description.toLowerCase().includes(searchKeyword.value.toLowerCase()))
    
    // Category filter
    const categoryMatch = selectedCategories.value.length === 0 || 
      selectedCategories.value.includes(caseItem.category)
    
    // Tag filter - if all tags are selected, match all cases
    const allTagsSelected = selectedTags.value.length === allTags.value.length
    const tagMatch = allTagsSelected || selectedTags.value.length === 0 || 
      selectedTags.value.some(tag => {
        if (!caseItem.tags) return false
        const tagNames = caseItem.tags.map(t => typeof t === 'object' ? t.name : t)
        return tagNames.includes(tag)
      })
    
    // Metric filter - if all metrics are selected, match all cases
    const allMetricsSelected = selectedMetrics.value.length === actualAllMetrics.value.length
    const metricMatch = allMetricsSelected || selectedMetrics.value.length === 0 || 
      selectedMetrics.value.every(metric => {
        // Check if at least one device has this metric
          const metricsMap = toMetricsMap(caseItem)
          return Object.values(metricsMap).some(deviceMetrics => deviceMetrics && typeof deviceMetrics[metric] === 'number')
      })
    
    return keywordMatch && categoryMatch && tagMatch && metricMatch
  })
  
  // Then, sort the filtered cases
  filtered.sort((a, b) => {
    let aVal, bVal
    
    // Determine the value to sort by
    if (sortDimension.value === '评估维度') {
      // Calculate average of the selected metric across devices
      const aMap = toMetricsMap(a)
      const bMap = toMetricsMap(b)
      aVal = Object.values(aMap).reduce((sum, metrics) => sum + (metrics?.[selectedSortMetric.value] || 0), 0) / (Object.values(aMap).length || 1)
      bVal = Object.values(bMap).reduce((sum, metrics) => sum + (metrics?.[selectedSortMetric.value] || 0), 0) / (Object.values(bMap).length || 1)
    } else {
      // Traditional sorting by other dimensions
      switch (sortDimension.value) {
        case 'name':
          aVal = a.name.toLowerCase()
          bVal = b.name.toLowerCase()
          break
        case 'category':
          aVal = (a.category || '').toLowerCase()
          bVal = (b.category || '').toLowerCase()
          break
        case 'tags':
          // Sort by the first tag in alphabetical order
          const aTags = a.tags ? a.tags.map(t => typeof t === 'object' ? t.name : t) : []
          const bTags = b.tags ? b.tags.map(t => typeof t === 'object' ? t.name : t) : []
          aVal = aTags.length > 0 ? aTags[0].toLowerCase() : ''
          bVal = bTags.length > 0 ? bTags[0].toLowerCase() : ''
          break
        case 'createdAt':
          // 使用startTime作为createdAt的代理
          aVal = Object.values(a.results || {})[0]?.startTime || 0
          bVal = Object.values(b.results || {})[0]?.startTime || 0
          break
        default:
          aVal = 0
          bVal = 0
      }
    }
    
    // Apply sort order
    if (aVal < bVal) {
      return sortOrder.value === 'asc' ? -1 : 1
    }
    if (aVal > bVal) {
      return sortOrder.value === 'asc' ? 1 : -1
    }
    return 0
  })
  
  return filtered
})

const unpinnedFilteredCases = computed(() => {
  const pinnedIds = new Set((pinnedCases.value || []).map(p => p?.id))
  return (filteredCases.value || []).filter(c => c && !pinnedIds.has(c.id))
})

const pageSize = ref(10)
const currentPage = ref(1)

const totalPages = computed(() => {
  const total = unpinnedFilteredCases.value.length
  return Math.max(1, Math.ceil(total / pageSize.value))
})

watch([unpinnedFilteredCases, pageSize], () => {
  if (currentPage.value > totalPages.value) currentPage.value = totalPages.value
  if (currentPage.value < 1) currentPage.value = 1
})

const paginatedCases = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return unpinnedFilteredCases.value.slice(start, start + pageSize.value)
})

const paginatedCasesWithPreparedData = computed(() => {
  return paginatedCases.value.map(caseItem => ({
    ...caseItem,
    _preparedComparisonData: prepareComparisonData(caseItem),
    _preparedAudioList: prepareAudioList(caseItem),
    _preparedReferenceAsr: caseItem.asr?.referenceText || caseItem.asr?.reference_text || '',
    _preparedReferenceTrans: caseItem.translation?.referenceText || caseItem.translation?.reference_text || '',
    _preparedAlgorithmResults: getAlgorithmResults(caseItem),
    _preparedReferenceParams: caseItem.referenceParams || caseItem.reference_params || {},
    _preparedAlgorithmType: caseItem.algorithmType || caseItem.algorithm_type || ''
  }))
})

const handlePrevPage = () => {
  if (currentPage.value > 1) currentPage.value -= 1
}

const handleNextPage = () => {
  if (currentPage.value < totalPages.value) currentPage.value += 1
}

const handleGoToPage = (page) => {
  const p = Number(page)
  if (!Number.isFinite(p)) return
  currentPage.value = Math.min(Math.max(1, p), totalPages.value)
}

// Methods
const toggleCaseExpand = (caseId) => {
  const index = expandedCases.value.indexOf(caseId)
  if (index > -1) {
    expandedCases.value.splice(index, 1)
    console.log('Case collapsed:', caseId, 'Expanded cases:', expandedCases.value)
  } else {
    expandedCases.value.push(caseId)
    console.log('Case expanded:', caseId, 'Expanded cases:', expandedCases.value)
  }
}

const toggleTag = (tag) => {
  const index = selectedTags.value.indexOf(tag)
  if (index > -1) {
    selectedTags.value.splice(index, 1)
  } else {
    selectedTags.value.push(tag)
  }
}

const toggleCategoryFilter = (category) => {
  const index = selectedCategories.value.indexOf(category)
  if (index > -1) {
    selectedCategories.value.splice(index, 1)
  } else {
    selectedCategories.value.push(category)
  }
}

const togglePin = (caseId) => {
  const caseItem = cases.value.find(c => c.id === caseId) || filteredCases.value.find(c => c.id === caseId)
  if (!caseItem) return
  
  const pinnedIndex = pinnedCases.value.findIndex(p => p.id === caseId)
  if (pinnedIndex > -1) {
    pinnedCases.value.splice(pinnedIndex, 1)
  } else {
    pinnedCases.value.push(caseItem)
  }
}

const openCaseDetail = (caseItem) => {
  currentCaseDetail.value = caseItem
}

const closeCaseDetail = () => {
  currentCaseDetail.value = null
}

// 监听键盘事件，处理 ESC 退出
const handleKeyDown = (event) => {
  if (event.key === 'Escape' && currentCaseDetail.value) {
    closeCaseDetail();
  }
};

watch(() => currentCaseDetail.value, (newVal) => {
  if (newVal) {
    window.addEventListener('keydown', handleKeyDown);
  } else {
    window.removeEventListener('keydown', handleKeyDown);
  }
}, { immediate: true });

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown);
});

const getOverallStatus = (caseItem) => {
  const statuses = (Array.isArray(caseItem.results) ? caseItem.results : []).map(r => r.status)
  if (statuses.includes('失败') || statuses.includes('Failed')) return 'failed'
  if (statuses.includes('警告') || statuses.includes('Warning')) return 'warning'
  return 'success'
}

const getCaseTaskId = (caseItem) => {
  return caseItem.taskId || caseItem.task_id || props.reportData?.taskId || props.reportData?.summary?.taskId || ''
}

const copyToClipboard = (text) => {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => {
      const notification = useNotification()
      notification.success('ID已复制到剪贴板')
    }).catch(() => {
      const notification = useNotification()
      notification.error('复制失败')
    })
  }
}

const formatFileSize = (bytes) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const downloadCaseLogZip = async (caseItem) => {
  const notification = useNotification()
  const reportId = props.reportData?.id || props.reportData?.reportId
  if (!reportId) {
    console.error('无法获取报告ID')
    notification.error('无法获取报告ID')
    return
  }

  const caseId = caseItem.id
  if (!caseId) {
    console.error('无法获取用例ID')
    notification.error('无法获取用例ID')
    return
  }

  isDownloadingLog.value = true
  downloadingCaseName.value = caseItem.name || caseId
  downloadProgress.value = 0
  downloadSpeed.value = ''
  downloadSize.value = ''
  downloadTotal.value = ''

  try {
    const downloadUrl = reportsApi.getCaseLogsDownloadUrl(reportId, caseId)
    const response = await fetch(downloadUrl)
    
    if (!response.ok) {
      let errorMsg = '下载日志失败'
      try {
        const errorData = await response.json()
        errorMsg = errorData?.message || errorData?.detail || errorMsg
      } catch {
        if (response.status === 404) {
          errorMsg = '未找到用例日志目录'
        } else if (response.status === 500) {
          errorMsg = '服务器内部错误'
        }
      }
      notification.error(errorMsg)
      return
    }

    const contentLength = response.headers.get('content-length')
    const totalBytes = contentLength ? parseInt(contentLength, 10) : 0
    downloadTotal.value = formatFileSize(totalBytes)

    if (!response.body) {
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `case_${caseId}_logs.zip`)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      notification.success('日志下载成功')
      return
    }

    const reader = response.body.getReader()
    const chunks = []
    let receivedBytes = 0
    let lastTime = Date.now()
    let lastBytes = 0

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      
      chunks.push(value)
      receivedBytes += value.length
      downloadSize.value = formatFileSize(receivedBytes)
      
      if (totalBytes > 0) {
        downloadProgress.value = Math.round((receivedBytes / totalBytes) * 100)
      }

      const now = Date.now()
      const timeDiff = now - lastTime
      if (timeDiff >= 500) {
        const bytesDiff = receivedBytes - lastBytes
        const speed = bytesDiff / (timeDiff / 1000)
        downloadSpeed.value = formatFileSize(speed) + '/s'
        lastTime = now
        lastBytes = receivedBytes
      }
    }

    const blob = new Blob(chunks, { type: 'application/zip' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `case_${caseId}_logs.zip`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    
    downloadProgress.value = 100
    notification.success('日志下载成功')
  } catch (error) {
    console.error('下载日志失败:', error)
    const errorMsg = error?.message || '下载日志失败，请稍后重试'
    notification.error(errorMsg)
  } finally {
    setTimeout(() => {
      isDownloadingLog.value = false
      downloadingCaseName.value = ''
      downloadProgress.value = 0
      downloadSpeed.value = ''
      downloadSize.value = ''
      downloadTotal.value = ''
    }, 500)
  }
}

// 为 TestCaseReportDetail 准备数据
const prepareComparisonData = (caseItem) => {
  const data = {}
  const metricsMap = toMetricsMap(caseItem)  // 扁平格式: {WER: 63.0, wer_zh: 0.0}
  const asrMap = toTextMap(caseItem.asr)
  const tranMap = toTextMap(caseItem.translation)
  
  // 判断 metrics 是否是扁平格式（不在设备分组内）
  const isFlatFormat = !Object.keys(metricsMap).some(k => allDevices.value.includes(k))
  
  allDevices.value.forEach(device => {
    if (isFlatFormat) {
      // 扁平格式：所有设备共享相同的指标数据
      data[device] = {
        metrics: metricsMap,  // 使用完整的指标对象
        asr: { text: asrMap?.[device]?.text || '-' },
        trans: { text: tranMap?.[device]?.text || '-' }
      }
    } else {
      // 按设备分组的格式
      data[device] = {
        metrics: metricsMap[device] || {},
        asr: { text: asrMap?.[device]?.text || '-' },
        trans: { text: tranMap?.[device]?.text || '-' }
      }
    }
  })
  return data
}

/**
 * 从 caseItem 提取 algorithm_results，返回扁平列表格式
 * 
 * 新后端格式（report_controller_task.py >= 当前版本）：已经是扁平列表
 * 旧后端格式（快照数据）：dict {resource: {param_key: value}}
 * 
 * 返回值：[{device, param_code, param_type, label, value}, ...]
 */
const getAlgorithmResults = (caseItem) => {
  const algoResults = caseItem.algorithm_results || caseItem.algorithmResults;
  
  // 新格式：已经是扁平列表，直接返回
  if (Array.isArray(algoResults)) {
    return algoResults;
  }
  
  // 旧格式：dict {resource: {param_key: value}}，转换为扁平列表
  const result = [];
  const excludedKeys = new Set([
    'evaluation_data', 'eval_data', 'raw_response', 'result_type',
    'error_message', 'status', 'duration', 'adjusted_reference_params',
    'reference_params', 'config'
  ]);
  
  if (algoResults && typeof algoResults === 'object') {
    for (const [resource, data] of Object.entries(algoResults)) {
      if (data && typeof data === 'object') {
        for (const [paramKey, paramValue] of Object.entries(data)) {
          if (paramValue && !excludedKeys.has(paramKey)) {
            result.push({
              device: resource,
              param_code: paramKey,
              param_type: _inferParamType(paramKey),
              label: paramKey,
              value: paramValue
            });
          }
        }
      }
    }
  }
  
  // 从 caseItem 获取直接的时间轴数据（兼容更旧的数据结构）
  const directKeys = ['rttmRes', 'stmRes', 'rttm_res', 'stm_res', 'rttm_hyp', 'stm_hyp', 'rttmHyp', 'stmHyp'];
  for (const key of directKeys) {
    if (caseItem[key]) {
      result.push({
        device: 'default',
        param_code: key,
        param_type: _inferParamType(key),
        label: key,
        value: caseItem[key]
      });
    }
  }
  
  return result;
};

/**
 * 根据参数键名推断 param_type
 */
const _inferParamType = (paramKey) => {
  const lower = paramKey.toLowerCase();
  if (lower.includes('rttm')) return 'rttm';
  if (lower.includes('stm')) return 'stm';
  if (lower.includes('audio')) return 'audio';
  return 'text';
};

const prepareAudioList = (caseItem) => {
  const taskType = props.reportData?.taskType || 'all' // 'api', 'e2e' or 'all'

  if (!caseItem.audioList || !Array.isArray(caseItem.audioList) || caseItem.audioList.length === 0) {
    return []
  }

  return caseItem.audioList.filter(audio => {
    if (taskType === 'api') {
      return audio.type === 'api'
    } else if (taskType === 'e2e') {
      return audio.type === 'e2e' || audio.type === 'noise'
    } else {
      return true // all: 显示所有
    }
  })
}

const formatTime = (timestamp) => {
  return new Date(timestamp).toLocaleString()
}

const toggleMetric = (metricName) => {
  const index = selectedMetrics.value.indexOf(metricName)
  if (index > -1) {
    selectedMetrics.value.splice(index, 1)
  } else {
    selectedMetrics.value.push(metricName)
  }
}

const resetFilters = () => {
  searchKeyword.value = ''
  selectedCategories.value = []
  categorySearchQuery.value = ''
  categoryPage.value = 1
  selectedTags.value = []
  selectedMetrics.value = []
  sortDimension.value = 'name'
  selectedSortMetric.value = ''
  sortOrder.value = 'asc'
  tagSearchQuery.value = ''
  tagPage.value = 1
  metricSearchQuery.value = ''
  metricPage.value = 1
}

const applyFilters = () => {
  // 这里可以添加筛选逻辑
  console.log('应用筛选:', {
    searchKeyword: searchKeyword.value,
    selectedCategories: selectedCategories.value,
    selectedTags: selectedTags.value,
    selectedMetrics: selectedMetrics.value,
    sortDimension: sortDimension.value,
    selectedSortMetric: selectedSortMetric.value,
    sortOrder: sortOrder.value
  })
}
</script>

<style scoped>
.audio-quick-btn.api-audio {
  color: #1976d2;
}
.audio-quick-btn.api-audio:hover {
  background-color: #e3f2fd;
}
.audio-quick-btn.e2e-audio {
  color: #7b1fa2;
}
.audio-quick-btn.e2e-audio:hover {
  background-color: #f3e5f5;
}

.audio-btns-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: transparent;
  padding: 16px;
  border-radius: 8px;
}

.audio-play-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.audio-type-label {
  font-size: 0.9rem;
  font-weight: 600;
  color: #495057;
  min-width: 90px;
}

.audio-action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  border-radius: 20px;
  border: 1px solid #1976d2;
  background: #fff;
  color: #1976d2;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  font-weight: 500;
}

.audio-action-btn:hover {
  background: #1976d2;
  color: #fff;
}

.audio-action-btn.e2e-theme {
  border-color: #9c27b0;
  color: #9c27b0;
  background: #fff;
}

.audio-action-btn.e2e-theme:hover {
  background: #9c27b0;
  color: #fff;
}

.audio-filename {
  font-size: 0.8rem;
  color: #6c757d;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 260px;
}

.no-audio-info {
  font-size: 0.85rem;
  color: #adb5bd;
  font-style: italic;
  padding: 4px 0;
}

.audio-section {
  margin-top: 15px;
  padding: 0;
  border: none;
  background: transparent;
}

.audio-container {
  margin-top: 8px;
}

.specific-case-comparison {
  background: transparent;
  padding: 0;
  margin-bottom: 24px;
  width: 100%;
}

.section-content {
  animation: slideDown 0.3s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.pinned-section {
  background: var(--warning-light);
  border: 1px dashed var(--warning-color);
  border-radius: var(--border-radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-xl);
}

.pinned-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--warning-color);
  margin: 0 0 var(--spacing-md) 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.pinned-list {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.pinned-case-card {
  background: #fff;
  border: 1px solid #ffe58f;
  border-radius: 8px;
  padding: 12px;
  min-width: 200px;
  box-shadow: 0 2px 8px rgba(250, 140, 22, 0.05);
}

.pinned-case-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.pinned-case-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.unpin-btn {
  background: none;
  border: none;
  font-size: 14px;
  color: #fa8c16;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s;
}

.unpin-btn:hover {
  background: #fff7e6;
  color: #ff7a45;
}

.pinned-case-status {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.case-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
}

.case-list .case-card {
  padding: 0;
  overflow: hidden;
  background: white;
  border-radius: 16px;
  width: 100%;
}

.case-header {
  padding: 16px 20px;
  width: 100%;
  box-sizing: border-box;
}

.case-info-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
}

.case-name-status {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-indicator {
  width: 10px;
  height: 10px;
  border-radius: var(--border-radius-full);
  flex-shrink: 0;
}

.status-indicator.success { background: var(--success-color); }
.status-indicator.failed { background: var(--error-color); }
.status-indicator.warning { background: var(--warning-color); }

.case-category {
  padding: 2px 10px;
  background: white;
  color: var(--text-secondary);
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.case-id-badge {
  padding: 2px 10px;
  background: white;
  color: #1677ff;
  border-radius: var(--border-radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.case-id-badge:hover {
  background: #f8fafc;
  color: #1677ff;
}

.case-id-badge .fa-copy {
  font-size: 10px;
}

.download-log-btn {
  background: #FF6A00;
  border: 1px solid #FF6A00;
  color: #fff;
  cursor: pointer;
  padding: 10px 20px;
  border-radius: 6px;
  transition: all 0.2s;
  font-size: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 500;
  gap: 8px;
}

.download-log-btn i {
  font-size: 18px;
}

.download-log-btn:hover {
  background: #ff8533;
  border-color: #ff8533;
}

.expand-icon {
  color: #94a3b8;
  transition: transform 0.3s;
  font-size: 12px;
  width: 16px;
  text-align: center;
}

.case-details {
  border-top: 1px solid var(--background-secondary);
  padding: var(--spacing-lg);
}

.detail-section-title {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  margin: 0 0 12px 0;
  padding-bottom: 6px;
  border-bottom: 1px solid #f0f0f0;
}

.logs-section {
  margin-top: 20px;
}

.logs-container {
  background: #000;
  border-radius: 4px;
  overflow: auto;
}

.logs-text {
  color: #00ff00;
  font-size: 12px;
  line-height: 1.5;
  padding: 16px;
  margin: 0;
  font-family: 'Courier New', Courier, monospace;
  white-space: pre-wrap;
  word-break: break-all;
}

@media (max-width: 768px) {
  .filter-row {
    flex-direction: column;
    gap: 16px;
  }
  
  .results-grid,
  .asr-results,
  .translation-results {
    grid-template-columns: 1fr;
  }
  
  .case-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  
  .case-header-right {
    width: 100%;
    justify-content: space-between;
  }
}

.download-loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999;
}

.download-loading-modal {
  background: white;
  border-radius: 12px;
  padding: 32px 48px;
  text-align: center;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  animation: fadeIn 0.2s ease;
  min-width: 400px;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.download-loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #e9ecef;
  border-top-color: #1677ff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.download-loading-title {
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 8px;
}

.download-loading-text {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 4px;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.download-loading-hint {
  font-size: 13px;
  color: #9ca3af;
}

.download-progress-bar-container {
  width: 100%;
  height: 8px;
  background: #e9ecef;
  border-radius: 4px;
  margin: 16px 0 8px;
  overflow: hidden;
}

.download-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #1677ff, #40a9ff);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.download-progress-info {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #6b7280;
  width: 100%;
}
</style>
