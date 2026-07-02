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
import { ref, computed, watch, onUnmounted } from 'vue'
import ChartComponent from './ChartComponent.vue'
import DataTable from '../common/DataTable.vue'
import { reportsApi } from '../../utils/api'
import '../../assets/styles/components/report-filter-card.css'


// Collapse state
const isCollapsed = ref(false)

// Collapse toggle method
const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

// 评估维度折叠状态
const collapsedMetrics = ref({})

// 切换评估维度折叠状态
const toggleMetricCollapse = (metricName) => {
  collapsedMetrics.value[metricName] = !collapsedMetrics.value[metricName]
}

// 表格引用
const tableRefs = ref({})

// 设置表格引用
const setTableRef = (metricName, el) => {
  tableRefs.value[metricName] = el
}

// Props
const props = defineProps({
  reportData: {
    type: Object, default: () => ({})
  }
})

// Data
// 从reportData中获取数据，优先使用reportData直接提供的数据，然后再使用summary中的数据
// 处理caseCategories：如果是对象数组，提取name属性作为显示值
const getCategories = (data) => {
  if (!data) return []
  const categories = data.caseCategories || data.summary?.caseCategories || []
  if (!Array.isArray(categories)) return []
  return categories.map(cat => typeof cat === 'object' ? cat.name : cat)
}

// 处理allCaseTags：如果是对象数组，提取name属性作为显示值
const getTags = (data) => {
  if (!data) return []
  const tags = data.allCaseTags || data.summary?.allCaseTags || []
  if (!Array.isArray(tags)) return []
  return tags.map(tag => typeof tag === 'object' ? tag.name : tag)
}

// 保存所有可用的类别和标签，不受用户选择影响
const allAvailableCategories = ref(getCategories(props.reportData))
const allAvailableTags = ref(getTags(props.reportData))

// 用户选择的类别和标签 - 默认空数组（显示全部）
const selectedCategories = ref([])
const selectedTags = ref([])

// Case name search
const caseNameSearchQuery = ref('')

// Search and pagination for categories
const categorySearchQuery = ref('')
const categoryPage = ref(1)
const categoryPageSize = ref(50)

const filteredCategoriesForSelection = computed(() => {
  if (!categorySearchQuery.value.trim()) {
    return allAvailableCategories.value
  }
  const query = categorySearchQuery.value.toLowerCase()
  return allAvailableCategories.value.filter(cat => cat.toLowerCase().includes(query))
})

const totalCategoryPages = computed(() => Math.ceil(filteredCategoriesForSelection.value.length / categoryPageSize.value) || 1)

const paginatedCategories = computed(() => {
  const start = (categoryPage.value - 1) * categoryPageSize.value
  const end = start + categoryPageSize.value
  return filteredCategoriesForSelection.value.slice(start, end)
})

// Search and pagination for tags
const tagSearchQuery = ref('')
const tagPage = ref(1)
const tagPageSize = ref(50)

const filteredTagsForSelection = computed(() => {
  if (!tagSearchQuery.value.trim()) {
    return allAvailableTags.value
  }
  const query = tagSearchQuery.value.toLowerCase()
  return allAvailableTags.value.filter(tag => tag.toLowerCase().includes(query))
})

const totalTagPages = computed(() => Math.ceil(filteredTagsForSelection.value.length / tagPageSize.value) || 1)

const paginatedTags = computed(() => {
  const start = (tagPage.value - 1) * tagPageSize.value
  const end = start + tagPageSize.value
  return filteredTagsForSelection.value.slice(start, end)
})

// Metrics configuration
const allMetrics = ref(props.reportData.allMetrics || props.reportData.summary?.allMetrics || [])

const selectedMetrics = ref([])

// Search and pagination for metrics
const metricSearchQuery = ref('')
const metricPage = ref(1)
const metricPageSize = ref(30)

const filteredMetricsForDisplay = computed(() => {
  if (!metricSearchQuery.value.trim()) {
    return allMetrics.value
  }
  const query = metricSearchQuery.value.toLowerCase()
  return allMetrics.value.filter(metric => metric.name.toLowerCase().includes(query))
})

const totalMetricPages = computed(() => Math.ceil(filteredMetricsForDisplay.value.length / metricPageSize.value) || 1)

const paginatedMetrics = computed(() => {
  const start = (metricPage.value - 1) * metricPageSize.value
  const end = start + metricPageSize.value
  return filteredMetricsForDisplay.value.slice(start, end)
})

const metricDecimalPlacesMap = computed(() => {
  const map = {}
  const list = Array.isArray(allMetrics.value) ? allMetrics.value : []
  list.forEach(m => {
    if (!m || !m.name) return
    const dp = m.decimalPlaces ?? m.decimal_places
    if (Number.isInteger(dp) && dp >= 0) map[String(m.name)] = dp
  })
  return map
})

const formatMetricForDisplay = (metricName, value) => {
  if (value === '-' || value === null || value === undefined) return '-'
  const num = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(num)) return String(value)
  const dp = metricDecimalPlacesMap.value?.[String(metricName)]
  if (Number.isInteger(dp) && dp >= 0) return num.toFixed(dp)
  return String(num)
}

// 同时使用设备和API作为资源，API任务可能没有设备，设备任务可能没有API
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



// 从reportData中提取初始metricData，并计算平均值
const extractInitialMetricData = (reportData) => {
  // 1. 优先使用后端预计算的 metricData (通常在 comparison report 的 summary 中)
  // 后端返回的 metric_data (snake_case) 会被转换为 metricData (camelCase)
  const preCalculatedRows = reportData.metricData || reportData.summary?.metricData || 
                           reportData.metric_data || reportData.summary?.metric_data;
  
  if (Array.isArray(preCalculatedRows) && preCalculatedRows.length > 0) {
    const mergedData = {};
    preCalculatedRows.forEach(row => {
      if (!row) return;
      if (Array.isArray(row.categories)) {
        const resourceKey = row.resource || '0-默认资源';
        row.categories.forEach(c => {
          if (!c) return;
          const category = c.categoryName || c.categoryId || '未分类';
          if (!mergedData[category]) mergedData[category] = {};
          if (!mergedData[category][resourceKey]) mergedData[category][resourceKey] = {};
          (c.metrics || []).forEach(m => {
            if (!m || !m.metric) return;
            mergedData[category][resourceKey][m.metric] = Number(m.value ?? 0);
          });
        });
      } else {
        const category = row.categoryName || row.categoryId || '未分类';
        const resourceKey = row.resource || '0-默认资源';
        if (!mergedData[category]) mergedData[category] = {};
        if (!mergedData[category][resourceKey]) mergedData[category][resourceKey] = {};
        if (Array.isArray(row.metrics)) {
          row.metrics.forEach(m => {
            if (!m || !m.metric) return;
            mergedData[category][resourceKey][m.metric] = Number(m.value ?? 0);
          });
        } else {
          const metricName = row.metric;
          if (!metricName) return;
          mergedData[category][resourceKey][metricName] = Number(row.value ?? 0);
        }
      }
    });
    
    const rawRows = reportData.rawData || reportData.summary?.rawData || 
                   reportData.raw_data || reportData.summary?.raw_data || [];
    if (Array.isArray(rawRows) && rawRows.length > 0) {
      const rawMap = {};
      rawRows.forEach(r => {
        if (!r || !r.resource) return;
        if (!rawMap[r.resource]) rawMap[r.resource] = {};
        if (Array.isArray(r.metrics)) {
          r.metrics.forEach(m => {
            if (!m || !m.metric) return;
            rawMap[r.resource][m.metric] = Array.isArray(m.values) ? m.values : [];
          });
        } else if (r.metric) {
          rawMap[r.resource][r.metric] = Array.isArray(r.values) ? r.values : [];
        }
      });
      
      Object.keys(mergedData).forEach(category => {
        const resources = mergedData[category] || {};
        Object.keys(resources).forEach(resourceKey => {
          const resourceRawData = rawMap[resourceKey];
          if (!resourceRawData) return;
          Object.keys(resourceRawData).forEach(metricName => {
            mergedData[category][resourceKey][`${metricName}_raw`] = resourceRawData[metricName];
          });
        });
      });
    }
    
    return mergedData;
  }

  // 3. Fallback: Reconstruct metricData from reportData.summary.cases if available
  // This handles the case where backend doesn't return metric_data directly (e.g. older version or filtered out)
  const cases = reportData.cases || reportData.summary?.cases;
  if (cases && Array.isArray(cases) && cases.length > 0) {
    console.log('[CaseCategoryComparison] Reconstructing metricData from cases');
    const reconstructedData = {};
    const accumulator = {}; // { category: { resource: { dim: { sum: 0, count: 0, values: [] } } } }

    cases.forEach(caseItem => {
      const category = caseItem.category || 'Uncategorized';
      const caseMetrics = caseItem.metrics || {};

      if (!accumulator[category]) accumulator[category] = {};
      
      if (Array.isArray(caseMetrics)) {
        caseMetrics.forEach(group => {
          if (!group || !group.resource || !Array.isArray(group.metrics)) return;
          const resourceKey = group.resource;
          if (!accumulator[category][resourceKey]) accumulator[category][resourceKey] = {};
          group.metrics.forEach(m => {
            if (!m || !m.metric) return;
            const dim = m.metric;
            if (!accumulator[category][resourceKey][dim]) {
              accumulator[category][resourceKey][dim] = { sum: 0, count: 0, values: [] };
            }
            const val = m.value;
            if (val !== null && val !== undefined) {
              accumulator[category][resourceKey][dim].sum += Number(val);
              accumulator[category][resourceKey][dim].count += 1;
              accumulator[category][resourceKey][dim].values.push(Number(val));
            }
          });
        });
      } else {
        Object.keys(caseMetrics).forEach(resourceKey => {
          if (!accumulator[category][resourceKey]) accumulator[category][resourceKey] = {};
          
          const metrics = caseMetrics[resourceKey];
          Object.keys(metrics).forEach(dim => {
            if (!accumulator[category][resourceKey][dim]) {
              accumulator[category][resourceKey][dim] = { sum: 0, count: 0, values: [] };
            }
            const val = metrics[dim];
            if (val !== null && val !== undefined) {
               accumulator[category][resourceKey][dim].sum += Number(val);
               accumulator[category][resourceKey][dim].count += 1;
               accumulator[category][resourceKey][dim].values.push(Number(val));
            }
          });
        });
      }
    });

    // Calculate averages and populate reconstructedData
    Object.keys(accumulator).forEach(category => {
      reconstructedData[category] = {};
      Object.keys(accumulator[category]).forEach(resourceKey => {
        reconstructedData[category][resourceKey] = {};
        Object.keys(accumulator[category][resourceKey]).forEach(dim => {
          const stats = accumulator[category][resourceKey][dim];
          if (stats.count > 0) {
            reconstructedData[category][resourceKey][dim] = Number((stats.sum / stats.count).toFixed(4));
            // Also store raw values for distribution chart
            reconstructedData[category][resourceKey][`${dim}_raw`] = stats.values;
          } else {
            reconstructedData[category][resourceKey][dim] = 0;
          }
        });
      });
    });
    
    return reconstructedData;
  }

  // 2. 如果没有预计算数据，则从 detailedResults 中提取 (原有逻辑)
  const dataAccumulator = {};
  
  // 从detailedResults中提取数据，优先使用reportData.detailedResults，如果没有则使用reportData.summary.detailedResults
  const detailedResults = reportData.detailedResults || reportData.summary?.detailedResults || [];
  if (detailedResults && detailedResults.length > 0) {
    detailedResults.forEach(result => {
          // 获取测试用例信息，用于确定类别和标签
          const testCaseId = result.testCaseId;
          let category = '其他';
          let categoryId = 'default';
          let tags = [];
          
          // 1. 使用后端新添加的testCaseGroup作为类别
          if (result.testCaseGroup) {
            category = result.testCaseGroup.name;
            categoryId = result.testCaseGroup.id;
          }
          // 2. 从testCaseTags中获取标签
          if (result.testCaseTags) {
            tags = result.testCaseTags.map(tag => tag.name);
          }
          // 3. 使用testCaseName作为类别
          else if (result.testCaseName) {
            // 使用测试用例名称作为类别
            category = result.testCaseName;
            categoryId = testCaseId;
          }
      
      // 确定资源信息（设备或API）
      let resourceId = '';
      let resourceName = '';
      if (result.device) {
        resourceId = result.device.id;
        resourceName = result.device.name;
      } else if (result.api) {
        resourceId = result.api.id;
        resourceName = result.api.name;
      } else {
        resourceId = 'default';
        resourceName = '默认资源';
      }
      
      // 使用ID作为资源的唯一标识符
      const resourceKey = `${resourceId}_${resourceName}`;
      
      // 初始化累加器数据结构，使用类别名称作为键（保持与UI显示一致）
      if (!dataAccumulator[category]) {
        dataAccumulator[category] = {};
      }
      if (!dataAccumulator[category][resourceKey]) {
        dataAccumulator[category][resourceKey] = {
          counts: {},
          sums: {},
          values: {} // 保存所有值用于计算正态分布
        };
      }
      
      // 提取并累加维度得分
      if (result.dimensionScores) {
        result.dimensionScores.forEach(dim => {
          // 初始化维度数据
          if (!dataAccumulator[category][resourceKey].counts[dim.dimensionName]) {
            dataAccumulator[category][resourceKey].counts[dim.dimensionName] = 0;
            dataAccumulator[category][resourceKey].sums[dim.dimensionName] = 0;
            dataAccumulator[category][resourceKey].values[dim.dimensionName] = [];
          }
          
          // 累加计数和总和
          dataAccumulator[category][resourceKey].counts[dim.dimensionName]++;
          dataAccumulator[category][resourceKey].sums[dim.dimensionName] += dim.score;
          dataAccumulator[category][resourceKey].values[dim.dimensionName].push(dim.score);
        });
      } else if (result.metrics) {
        // 如果没有dimensionScores，尝试从metrics中获取
        Object.entries(result.metrics).forEach(([dimName, value]) => {
          // 初始化维度数据
          if (!dataAccumulator[category][resourceKey].counts[dimName]) {
            dataAccumulator[category][resourceKey].counts[dimName] = 0;
            dataAccumulator[category][resourceKey].sums[dimName] = 0;
            dataAccumulator[category][resourceKey].values[dimName] = [];
          }
          
          // 累加计数和总和
          dataAccumulator[category][resourceKey].counts[dimName]++;
          dataAccumulator[category][resourceKey].sums[dimName] += value;
          dataAccumulator[category][resourceKey].values[dimName].push(value);
        });
      }
    });
  }
  
  // 计算平均值，构建最终的metricData
  const extractedMetricData = {};
  
  Object.entries(dataAccumulator).forEach(([category, resources]) => {
    extractedMetricData[category] = {};
    
    Object.entries(resources).forEach(([resourceKey, data]) => {
      // 初始化资源数据 - 仅使用 resourceKey (ID_Name) 以确保唯一性
      if (!extractedMetricData[category][resourceKey]) {
        extractedMetricData[category][resourceKey] = {};
      }
      
      // 计算每个维度的平均值
      Object.entries(data.counts).forEach(([dimName, count]) => {
        const sum = data.sums[dimName];
        const average = count > 0 ? sum / count : 0;
        
        extractedMetricData[category][resourceKey][dimName] = average;
        
        // 保存原始值用于正态分布图
        extractedMetricData[category][resourceKey][`${dimName}_raw`] = data.values[dimName];
      });
    });
  });
  
  // 注意：不再从summary.rawData中提取数据，因为这会导致所有类别显示相同的平均值
  // 只使用detailedResults中的数据，确保每个类别有自己的平均值

  
  return extractedMetricData;
};

// 使用ref管理内部metricData状态
const metricData = ref(extractInitialMetricData(props.reportData));

// 监听reportData变化，更新内部状态
watch(() => props.reportData, (newReportData) => {
  console.log('[CaseCategoryComparisonComponent] reportData变化:', newReportData);
  // 只更新所有可用的类别和标签，不受用户选择影响
  allAvailableCategories.value = getCategories(newReportData)
  allAvailableTags.value = getTags(newReportData)
  allMetrics.value = newReportData.allMetrics || newReportData.summary?.allMetrics || []
  // 更新metricData
  metricData.value = extractInitialMetricData(newReportData);
  // 同时使用设备和API作为资源，API任务可能没有设备，设备任务可能没有API
  devices.value = getValidResources(newReportData);
  
  // 重置选中状态：默认不选中任何条件（显示全部）
  selectedCategories.value = []
  selectedTags.value = []
  selectedMetrics.value = []
}, { deep: true })

// Display types
const displayTypes = ref([
  { type: 'table', label: '表格', icon: 'fas fa-table' },
  { type: 'bar', label: '柱状图', icon: 'fas fa-chart-bar' },
  { type: 'line', label: '折线图', icon: 'fas fa-chart-line' },
  { type: 'radar', label: '雷达图', icon: 'fas fa-hexagon' },
  { type: 'distribution', label: '正态分布图', icon: 'fas fa-chart-area' }
])

const activeDisplayType = ref('table')

// Computed
const filteredCategories = computed(() => {
  if (selectedCategories.value.length === 0) {
    return allAvailableCategories.value
  }
  return selectedCategories.value
})

const filteredMetrics = computed(() => {
  if (selectedMetrics.value.length === 0) {
    return allMetrics.value
  }
  return allMetrics.value.filter(m => selectedMetrics.value.includes(m.name))
})

const reportId = computed(() => props.reportData?.id || props.reportData?.reportId)

let saveTimer = null
const scheduleSaveSummary = (partialSummary) => {
  const id = reportId.value
  if (!id) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    try {
      await reportsApi.update(id, { id, summary: partialSummary })
    } catch (e) {
      console.error('[CaseCategoryComparison] Failed to save header edits:', e)
    }
  }, 200)
}

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

  if (typeof resourceKey === 'string' && /^t\d+-\d{12}-/.test(resourceKey)) {
    const parts = resourceKey.split('-')
    if (parts.length >= 4) {
      const name = parts.slice(3).join('-')
      if (name) return name
    }
  }

  if (typeof resourceKey === 'string' && resourceKey.includes('_')) {
    const parts = resourceKey.split('_')
    const prefix = parts[0]
    const name = parts.slice(1).join('_')
    if (/^\d{14}$/.test(prefix)) {
      const month = prefix.substring(4, 6)
      const day = prefix.substring(6, 8)
      const hour = prefix.substring(8, 10)
      const minute = prefix.substring(10, 12)
      return `${month}-${day} ${hour}:${minute} ${name}`
    }
    return name
  }

  return resourceKey
}

const editingResourceKey = ref(null)
const editingResourceValue = ref('')

const startEditResource = (resourceKey) => {
  editingResourceKey.value = resourceKey
  editingResourceValue.value = String(getResourceLabel(resourceKey) ?? '')
}

const commitEditResource = (resourceKey, newValue) => {
  const next = newValue !== undefined ? String(newValue ?? '').trim() : String(editingResourceValue.value ?? '').trim()
  if (editingResourceKey.value !== resourceKey && newValue === undefined) return
  editingResourceKey.value = null
  if (!next) return

  const report = props.reportData || {}
  const summary = report.summary || report
  const headers = summary.resourceHeaders || summary.resource_headers || report.resourceHeaders || report.resource_headers || []
  if (Array.isArray(headers)) {
    const target = headers.find(h => h && (h.key === resourceKey || h.resource === resourceKey))
    if (target) {
      target.label = next
    }
  }
  scheduleSaveSummary({ resourceHeaders: headers })
}

const editingCategoryKey = ref(null)
const editingCategoryValue = ref('')

const startEditCategory = (categoryName) => {
  editingCategoryKey.value = categoryName
  editingCategoryValue.value = String(categoryName ?? '')
}

const commitEditCategory = (oldName, newValue) => {
  const next = newValue !== undefined ? String(newValue ?? '').trim() : String(editingCategoryValue.value ?? '').trim()
  if (editingCategoryKey.value !== oldName && newValue === undefined) return
  editingCategoryKey.value = null
  if (!next || next === oldName) return

  if (metricData.value && metricData.value[oldName] && !metricData.value[next]) {
    metricData.value[next] = metricData.value[oldName]
    delete metricData.value[oldName]
  }
  allAvailableCategories.value = allAvailableCategories.value.map(c => (c === oldName ? next : c))
  selectedCategories.value = selectedCategories.value.map(c => (c === oldName ? next : c))

  const report = props.reportData || {}
  const summary = report.summary || report
  const cats = summary.caseCategories || summary.case_categories || report.caseCategories || report.case_categories || []
  if (Array.isArray(cats)) {
    const target = cats.find(c => c && typeof c === 'object' && c.name === oldName)
    if (target) target.name = next
  }
  scheduleSaveSummary({ caseCategories: cats })
}

const processedDevices = computed(() => {
  return devices.value.map(device => getResourceLabel(device))
})

// Methods
const toggleCategory = (category) => {
  const index = selectedCategories.value.indexOf(category)
  if (index > -1) {
    selectedCategories.value.splice(index, 1)
  } else {
    selectedCategories.value.push(category)
  }
  applyFilters()
}

const toggleTag = (tag) => {
  const index = selectedTags.value.indexOf(tag)
  if (index > -1) {
    selectedTags.value.splice(index, 1)
  } else {
    selectedTags.value.push(tag)
  }
  applyFilters()
}

const toggleMetric = (metricName) => {
  const index = selectedMetrics.value.indexOf(metricName)
  if (index > -1) {
    selectedMetrics.value.splice(index, 1)
  } else {
    selectedMetrics.value.push(metricName)
  }
}

// 重置筛选条件
const resetFilters = () => {
  selectedCategories.value = []
  selectedTags.value = []
  selectedMetrics.value = []
  caseNameSearchQuery.value = ''
  categorySearchQuery.value = ''
  categoryPage.value = 1
  tagSearchQuery.value = ''
  tagPage.value = 1
  metricSearchQuery.value = ''
  metricPage.value = 1
  applyFilters()
}

const computeMetricDataFromCases = (cases) => {
  const reconstructedData = {}
  const accumulator = {}

  const selectedCategorySet = new Set(selectedCategories.value || [])
  const selectedTagSet = new Set(selectedTags.value || [])
  const includeUntagged = selectedTagSet.has('无标签') || selectedTagSet.has('未标记')
  selectedTagSet.delete('无标签')
  selectedTagSet.delete('未标记')
  const useCategoryFilter = selectedCategorySet.size > 0 && selectedCategorySet.size !== (allAvailableCategories.value || []).length
  const useTagFilter =
    (selectedTagSet.size > 0 || includeUntagged) &&
    ((selectedTags.value || []).length !== (allAvailableTags.value || []).length)

  ;(cases || []).forEach(caseItem => {
    if (!caseItem) return
    const category = caseItem.category || '未分类'
    if (useCategoryFilter && !selectedCategorySet.has(category)) return

    const caseTagsRaw = caseItem.tags || []
    const caseTagNames = Array.isArray(caseTagsRaw)
      ? caseTagsRaw.map(t => (typeof t === 'object' ? t?.name : t)).filter(Boolean)
      : []
    if (useTagFilter) {
      const hasTagMatch = caseTagNames.some(t => selectedTagSet.has(t))
      const isUntagged = caseTagNames.length === 0
      if (!hasTagMatch && !(includeUntagged && isUntagged)) return
    }

    const caseMetrics = caseItem.metrics || {}
    if (!accumulator[category]) accumulator[category] = {}

    if (Array.isArray(caseMetrics)) {
      caseMetrics.forEach(group => {
        if (!group || !group.resource || !Array.isArray(group.metrics)) return
        const resourceKey = group.resource
        if (!accumulator[category][resourceKey]) accumulator[category][resourceKey] = {}
        group.metrics.forEach(m => {
          if (!m || !m.metric) return
          const dim = m.metric
          if (!accumulator[category][resourceKey][dim]) {
            accumulator[category][resourceKey][dim] = { sum: 0, count: 0, values: [] }
          }
          const val = m.value
          if (val !== null && val !== undefined) {
            accumulator[category][resourceKey][dim].sum += Number(val)
            accumulator[category][resourceKey][dim].count += 1
            accumulator[category][resourceKey][dim].values.push(Number(val))
          }
        })
      })
    } else {
      Object.keys(caseMetrics).forEach(resourceKey => {
        if (!accumulator[category][resourceKey]) accumulator[category][resourceKey] = {}
        const metrics = caseMetrics[resourceKey] || {}
        Object.keys(metrics).forEach(dim => {
          if (!accumulator[category][resourceKey][dim]) {
            accumulator[category][resourceKey][dim] = { sum: 0, count: 0, values: [] }
          }
          const val = metrics[dim]
          if (val !== null && val !== undefined) {
            accumulator[category][resourceKey][dim].sum += Number(val)
            accumulator[category][resourceKey][dim].count += 1
            accumulator[category][resourceKey][dim].values.push(Number(val))
          }
        })
      })
    }
  })

  Object.keys(accumulator).forEach(category => {
    reconstructedData[category] = {}
    Object.keys(accumulator[category]).forEach(resourceKey => {
      reconstructedData[category][resourceKey] = {}
      Object.keys(accumulator[category][resourceKey]).forEach(dim => {
        const stats = accumulator[category][resourceKey][dim]
        if (stats.count > 0) {
          reconstructedData[category][resourceKey][dim] = Number((stats.sum / stats.count).toFixed(4))
          reconstructedData[category][resourceKey][`${dim}_raw`] = stats.values
        } else {
          reconstructedData[category][resourceKey][dim] = 0
        }
      })
    })
  })

  return reconstructedData
}

// 应用筛选条件
const applyFilters = async () => {
  console.log('应用筛选条件', {
    categories: selectedCategories.value,
    tags: selectedTags.value
  });
  
  try {
    const selectedTagList = selectedTags.value || []
    const includeUntagged = selectedTagList.includes('无标签') || selectedTagList.includes('未标记')
    const normalizedTags = selectedTagList.filter(t => t !== '无标签' && t !== '未标记')

    // 调用API获取筛选后的数据
    const reportData = props.reportData || {}
    const taskId =
      reportData.taskId ||
      reportData.task_id ||
      reportData.summary?.taskId ||
      reportData.summary?.task_id

    if (taskId) {
      const result = await reportsApi.getCaseAveragesByFilters(taskId, {
        category: selectedCategories.value.length > 0 ? selectedCategories.value[0] : null,
        tags: normalizedTags,
        includeUntagged,
        categories: selectedCategories.value
      });
      
      console.log('API返回结果:', result);
      
      // 更新内部metricData ref，触发重新渲染
      metricData.value = extractInitialMetricData(result);
      return
    }

    const reportId = reportData.id || reportData.reportId || reportData.report_id
    if (reportId) {
      const body = {
        page: 1,
        per_page: 5000,
        tags: normalizedTags,
        includeUntagged,
        category: (selectedCategories.value || []).length === 1 ? selectedCategories.value[0] : null
      }

      const res = await reportsApi.searchCases(reportId, body)
      const cases = res?.items || res?.data?.items || []
      metricData.value = computeMetricDataFromCases(cases)
      return
    }
  } catch (error) {
    console.error('调用API失败:', error);
  }
}

const getMetricValue = (category, device, metricName) => {
  // device 可能是 "ID_Name" 格式的字符串，也可能是包含 id 和 name 的对象
  if (metricData.value) {
    const categoryData = metricData.value[category];
    if (categoryData) {
      // 1. 尝试直接使用 device 查找（如果 device 是 "ID_Name" 字符串）
      if (categoryData[device] && categoryData[device][metricName] !== undefined) {
        return categoryData[device][metricName];
      }
      
      // 2. 如果 device 是对象，尝试构建 key 查找
      if (typeof device === 'object' && device !== null) {
        const resourceKey = `${device.id}_${device.name}`;
        if (categoryData[resourceKey] && categoryData[resourceKey][metricName] !== undefined) {
          return categoryData[resourceKey][metricName];
        }
      }
      
      // 3. 兜底：如果还是找不到，尝试按名称匹配（不推荐，但在数据不全时可用）
      const deviceName = typeof device === 'object' ? (device.name || device.deviceName) : 
                        (device.includes('_') ? device.split('_').slice(1).join('_') : device);
      
      const entries = Object.entries(categoryData);
      for (const [key, data] of entries) {
        const currentResourceName = key.includes('_') ? key.split('_').slice(1).join('_') : key;
        if (currentResourceName === deviceName && data[metricName] !== undefined) {
          return data[metricName];
        }
      }
    }
  }
  
  return 0 
}

const getMetricDisplayValue = (category, device, metricName) => {
  return formatMetricForDisplay(metricName, getMetricValue(category, device, metricName))
}

const getMetricUnit = (metricName) => {
  const metric = allMetrics.value.find(m => m.name === metricName)
  return metric?.unit || ''
}

const getTableColumns = (metricName) => {
  const unit = getMetricUnit(metricName)
  const columns = [
    {
      key: 'category',
      label: '用例分组',
      editable: true,
      resize: true,
      class: 'category-column'
    }
  ]

  devices.value.forEach((device, index) => {
    columns.push({
      key: `device-${index}`,
      label: processedDevices.value[index],
      editable: true,
      resize: true,
      class: 'device-column',
      color: '#1677ff',
      unit: unit
    })
  })

  return columns
}

const getTableData = (metricName) => {
  return filteredCategories.value.map(category => {
    const row = {
      category: category
    }

    devices.value.forEach((device, index) => {
      row[`device-${index}`] = getMetricDisplayValue(category, device, metricName)
    })

    return row
  })
}

const handleHeaderSave = ({ colIndex, value, column }) => {
  // 如果是第一列（用例分组），则调用 commitEditCategory
  if (colIndex === 0) {
    if (column && column.key === 'category') {
      const oldName = column.label
      if (value !== oldName) {
        commitEditCategory(oldName, value)
      }
    }
    return
  }
  // 如果是设备列，则调用 commitEditResource
  const deviceIndex = colIndex - 1
  if (deviceIndex >= 0 && deviceIndex < devices.value.length) {
    const device = devices.value[deviceIndex]
    commitEditResource(device, value)
  }
}

const handleCellSave = ({ rowIndex, colIndex, value }) => {
  if (colIndex === 0) {
    const category = filteredCategories.value[rowIndex]
    if (category) {
      commitEditCategory(category, value)
    }
  }
}

// 处理行头（用例分组）单元格点击
const handleCategoryCellClick = (metricName, rowIndex, colIndex, row) => {
  const tableRef = tableRefs.value[metricName]
  if (tableRef) {
    tableRef.startEditCell(rowIndex, colIndex)
  }
}

// 预定义的颜色数组，确保相同设备始终使用相同颜色
const chartColors = [
  'rgba(22, 119, 255, 0.6)',  // 科技蓝
  'rgba(255, 106, 0, 0.6)',   // 活力橙
  'rgba(82, 196, 26, 0.6)',   // 清新绿
  'rgba(250, 173, 20, 0.6)',   // 温暖黄
  'rgba(19, 194, 194, 0.6)',   // 冷静青
  'rgba(114, 46, 209, 0.6)'    // 优雅紫
]

// 预定义的边框颜色数组
const chartBorderColors = [
  'rgba(22, 119, 255, 1)',     // 科技蓝
  'rgba(255, 106, 0, 1)',      // 活力橙
  'rgba(82, 196, 26, 1)',      // 清新绿
  'rgba(250, 173, 20, 1)',      // 温暖黄
  'rgba(19, 194, 194, 1)',      // 冷静青
  'rgba(114, 46, 209, 1)'       // 优雅紫
]

const getChartData = (metricName) => {
  // 如果是正态分布图，生成不同的数据结构
  if (activeDisplayType.value === 'distribution') {
    // 收集所有原始数据点用于正态分布计算
    let allRawData = [];
    const deviceRawDataMap = {};
    
    // 初始化设备原始数据映射
    devices.value.forEach(device => {
      deviceRawDataMap[device] = [];
    });
    
    // 收集所有原始数据
    devices.value.forEach(device => {
      // 后端返回的raw_data是按资源维度的，会被复制到每个类别下（同一数组引用），
      // 需要按引用去重，避免同一份数据被重复累加N次（N=类别数）
      const seenArrays = new Set();
      filteredCategories.value.forEach(category => {
        // 获取原始值数组
        const rawDataKey = `${metricName}_raw`;
        let rawData = [];

        if (metricData.value && metricData.value[category] && metricData.value[category][device]) {
          rawData = metricData.value[category][device][rawDataKey] || [];
        }

        // 跳过已处理的相同数组引用（后端数据被复制到每个类别的情况）
        if (seenArrays.has(rawData)) return;
        seenArrays.add(rawData);

        // 添加到设备原始数据和总原始数据中
        deviceRawDataMap[device] = deviceRawDataMap[device].concat(rawData);
        allRawData = allRawData.concat(rawData);
      });
    });
    
    // 过滤掉非数值数据，确保统计计算正确
    allRawData = allRawData.filter(v => typeof v === 'number' && !isNaN(v) && isFinite(v));
    Object.keys(deviceRawDataMap).forEach(device => {
      deviceRawDataMap[device] = deviceRawDataMap[device].filter(v => typeof v === 'number' && !isNaN(v) && isFinite(v));
    });

    // 计算正态分布统计信息
    const calculateNormalDistribution = (data) => {
      if (!data || data.length === 0) {
        return null;
      }

      // 计算平均值
      const mean = data.reduce((sum, value) => sum + value, 0) / data.length;

      // 计算方差
      const variance = data.reduce((sum, value) => sum + Math.pow(value - mean, 2), 0) / data.length;

      // 计算标准差
      const stdDev = Math.sqrt(variance);

      return {mean, stdDev, totalDataPoints: data.length};
    };

    const distribution = calculateNormalDistribution(allRawData);
    if (!distribution) {
      return {labels: [], datasets: [], rawData: allRawData};
    }
    
    // 按标准差划分区间：以mean为中心，向两侧按σ/2步长划分，共16个区间
    // 区间边界包含0和mean，使[0, mean)和[mean, mean+4σ]清晰可见
    const step = distribution.stdDev / 2; // 每个区间宽度 = σ/2
    let minValue = distribution.mean - 8 * step; // mean - 4σ
    const maxValue = distribution.mean + 8 * step; // mean + 4σ
    // 如果所有数据都非负，横轴从0开始
    if (!allRawData.some(v => v < 0)) {
      minValue = 0;
    }
    const intervals = Math.round((maxValue - minValue) / step);

    // 为每个设备生成正态分布数据
    const chartData = {
      labels: [],
      datasets: devices.value.map((device, index) => {
        const color = chartColors[index % chartColors.length];
        const borderColor = chartBorderColors[index % chartBorderColors.length];

        // 获取该设备的所有原始数据点
        const deviceRawData = deviceRawDataMap[device] || [];

        // 计算设备的正态分布参数
        const deviceDistribution = calculateNormalDistribution(deviceRawData);
        if (!deviceDistribution) {
          return {
          label: getResourceLabel(device),
            data: Array.from({ length: intervals }, (_, i) => ({ x: minValue + i * step, y: 0 })),
            backgroundColor: color,
            borderColor: borderColor,
            borderWidth: 1,
            fill: true,
            tension: 0.3
          };
        }

        // 统计每个区间内实际数据点数量
        const values = [];
        for (let i = 0; i < intervals; i++) {
          const intervalStart = minValue + i * step;
          const midPoint = minValue + (i + 0.5) * step;
          // 统计落在该区间内的实际数据点数（最后一个区间包含上界）
          const count = deviceRawData.filter(v => i === intervals - 1 ? v >= intervalStart : v >= intervalStart && v < intervalStart + step).length;
          values.push({ x: parseFloat(midPoint.toFixed(2)), y: count });
        }

        return {
          label: getResourceLabel(device),
          data: values,
          backgroundColor: color,
          borderColor: borderColor,
          borderWidth: 1,
          fill: false,
          tension: 0.3
        };
      }),
      // 添加rawData字段，用于正态分布统计计算
      rawData: allRawData,
      // 按设备分开的原始数据，用于按设备分别统计
      deviceRawData: Object.fromEntries(
        devices.value.map(d => [getResourceLabel(d), deviceRawDataMap[d] || []])
      )
    };
    
    return chartData;
  }
  
  // 非正态分布图，使用原有逻辑
  // 生成图表数据
  const chartData = {
    labels: filteredCategories.value, 
    datasets: devices.value.map((device, index) => {
      // 使用预定义的颜色，根据设备索引选择，确保相同设备始终使用相同颜色
      const color = chartColors[index % chartColors.length]
      const borderColor = chartBorderColors[index % chartBorderColors.length]

      // 为每个设备生成数据
      const data = filteredCategories.value.map(category => {
        // 调用getMetricValue获取平均值数据
        return parseFloat(getMetricValue(category, device, metricName))
      })

      return {
        label: getResourceLabel(device),
        data: data, 
        backgroundColor: color, 
        borderColor: borderColor, 
        borderWidth: 1
      }
    })
  }

  return chartData
}
</script>

<style scoped>
.case-category-comparison {
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

/* Filter Card Styles - Now using shared report-filter-card.css */

/* No Metrics Selected */
.no-metrics-selected {
  background: #fef3c7;
  border: 1px solid #fbbf24;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
  text-align: center;
  color: #92400e;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}

/* Metric Container Styles */
.metric-container {
  overflow: hidden;
  margin-bottom: 24px;
  width: 100%;
}

.metric-table-title {
  color: #334155;
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  padding: 12px 16px;
  border-bottom: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: white;
  width: 100%;
  box-sizing: border-box;
  border-radius: 16px 16px 0 0;
  border: 1px solid #e2e8f0;
  border-bottom: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.title-content {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  flex: 1;
  min-width: 0;
}

.title-content span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.title-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.metric-collapse-btn {
  background: none;
  border: none;
  font-size: 14px;
  color: #64748b;
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.metric-collapse-btn:hover {
  background: rgba(0, 0, 0, 0.05);
  color: #1677ff;
}

.metric-collapse-btn.collapsed {
  transform: rotate(180deg);
}

.metric-container-content {
  padding: 0;
  transition: all 0.3s ease;
  animation: slideDown 0.3s ease-out;
}

/* Display Type Selector */
.display-type-selector {
  display: flex;
  gap: 2px;
  align-items: center;
}

.display-type-btn {
  width: 28px;
  height: 28px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: white;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
}

.display-type-btn:hover {
  border-color: #1677ff;
  color: #1677ff;
  background: rgba(22, 119, 255, 0.05);
}

.display-type-btn.active {
  background: #1677ff;
  color: white;
  border-color: #1677ff;
}

/* Responsive Styles */
@media (max-width: 768px) {
  .filter-row {
    flex-direction: column;
  }
  
  .filter-item {
    width: 100%;
  }
  
  .metric-tags {
    justify-content: center;
  }
  
  .display-type-selector {
    justify-content: center;
  }
}
</style>
