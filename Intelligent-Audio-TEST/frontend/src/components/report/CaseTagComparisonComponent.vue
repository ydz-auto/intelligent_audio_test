<template>
  <div class="case-tag-comparison">
    <div class="section-header" @click="toggleCollapse">
      <h3 class="section-title">按用例标签对比 (By Tag Comparison)</h3>
      <button class="collapse-btn" :class="{ collapsed: isCollapsed }" title="折叠/展开">
        <i class="fas fa-chevron-up" v-if="isCollapsed"></i>
        <i class="fas fa-chevron-down" v-else></i>
      </button>
    </div>

    <!-- Collapsible Content -->
    <div class="section-content" v-if="!isCollapsed">
      <!-- Filter Card -->
      <div class="filter-card">
        <div class="filter-title">
          <i class="fas fa-filter" style="color: #ff6a00; font-size: 18px;"></i>
          筛选条件
        </div>
        <div class="filter-content">
          <div class="filter-row">
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
              <div class="tag-filter" :class="{ 'has-pagination': paginatedTags.length > 0 }">
                <div 
                  v-for="tag in paginatedTags" 
                  :key="tag"
                  :class="['tag-filter-item', { active: selectedTags.includes(tag) }]"
                  @click="toggleTag(tag)"
                >
                  {{ tag }}
                </div>
                <div v-if="filteredTags.length === 0" class="no-data-tip">
                  暂无可用的用例标签
                </div>
              </div>
              <div class="tag-pagination" v-if="filteredTags.length > pageSize">
                <button class="pagination-btn" @click="tagPage--" :disabled="tagPage <= 1">
                  <i class="fas fa-chevron-left"></i>
                </button>
                <span class="pagination-info">{{ tagPage }} / {{ totalTagPages }}</span>
                <button class="pagination-btn" @click="tagPage++" :disabled="tagPage >= totalTagPages">
                  <i class="fas fa-chevron-right"></i>
                </button>
              </div>
            </div>

            <!-- 用例分组筛选器 -->
            <div class="filter-item">
              <label class="filter-label">
                <i class="fas fa-list-check"></i> 用例分组
              </label>
              <div class="case-type-filter">
                <div 
                  v-for="category in caseCategories" 
                  :key="category"
                  :class="['case-type-item', { active: selectedCategories.includes(category) }]"
                  @click="toggleCategory(category)"
                >
                  {{ category }}
                </div>
                <div v-if="caseCategories.length === 0" class="no-data-tip">
                  暂无可用的用例分组
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
        <div class="metric-table-title" @click="toggleMetricCollapse(metric.name)">
          <div class="title-content">
            <i class="fas fa-chart-bar"></i>
            <span>{{ metric.name }} 对比（单位：{{ metric.unit }}）</span>
          </div>
          <button class="metric-collapse-btn" :class="{ collapsed: collapsedMetrics[metric.name] }" title="折叠/展开">
            <i class="fas fa-chevron-up" v-if="collapsedMetrics[metric.name]"></i>
            <i class="fas fa-chevron-down" v-else></i>
          </button>
        </div>

        <!-- 图和表切换容器 -->
        <div class="metric-container-content" v-if="!collapsedMetrics[metric.name]">
          <!-- 显示类型切换 -->
          <div class="display-type-selector">
            <span class="display-type-title">显示类型:</span>
            <button 
              v-for="displayType in displayTypes" 
              :key="displayType.type"
              :class="['display-type-btn', { active: activeDisplayType === displayType.type }]"
              @click="activeDisplayType = displayType.type"
            >
              <i :class="displayType.icon"></i>
              {{ displayType.label }}
            </button>
          </div>

          <!-- 表格容器 -->
          <div v-if="activeDisplayType === 'table'" class="table-container">
            <table class="data-table">
              <thead>
                <tr>
                  <th>用例标签</th>
                  <th v-for="(device, index) in devices" :key="index">
                    <span
                      v-if="editingResourceKey !== device"
                      style="cursor: pointer;"
                      @click="startEditResource(device)"
                    >{{ processedDevices[index] }}</span>
                    <input
                      v-else
                      v-model="editingResourceValue"
                      class="filter-input"
                      style="width: 100%;"
                      @keyup.enter="commitEditResource(device)"
                      @blur="commitEditResource(device)"
                    />
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="tag in filteredTags" :key="tag">
                  <td>
                    <span
                      v-if="editingTagKey !== tag"
                      style="cursor: pointer;"
                      @click="startEditTag(tag)"
                    >{{ tag }}</span>
                    <input
                      v-else
                      v-model="editingTagValue"
                      class="filter-input"
                      style="width: 100%;"
                      @keyup.enter="commitEditTag(tag)"
                      @blur="commitEditTag(tag)"
                    />
                  </td>
                  <td v-for="device in devices" :key="device">
                    {{ getMetricDisplayValue(tag, device, metric.name) }}{{ metric.unit }}
                  </td>
                </tr>
              </tbody>
            </table>
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
import { ref, computed, watch } from 'vue'
import ChartComponent from './ChartComponent.vue'
import { reportsApi } from '../../utils/api'

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

// Props
const props = defineProps({
  reportData: {
    type: Object, default: () => ({})
  }
})

// Data
// 从reportData中获取数据，优先使用reportData直接提供的数据，然后再使用summary中的数据
// 处理allTags：如果是对象数组，提取name属性作为显示值
const getTags = (data) => {
  if (!data) return []
  const tags = data.allTags || data.summary?.allTags || data.allCaseTags || data.summary?.allCaseTags || []
  if (!Array.isArray(tags)) return []
  return tags.map(tag => typeof tag === 'object' ? tag.name : tag)
}

// 处理caseCategories：如果是对象数组，提取name属性作为显示值
const getCategories = (data) => {
  if (!data) return []
  const categories = data.caseCategories || data.summary?.caseCategories || []
  if (!Array.isArray(categories)) return []
  return categories.map(cat => typeof cat === 'object' ? cat.name : cat)
}

const allTags = ref(getTags(props.reportData))
const caseCategories = ref(getCategories(props.reportData))

const selectedTags = ref([])
const selectedCategories = ref(caseCategories.value)

// Search and pagination for tags
const tagSearchQuery = ref('')
const tagPage = ref(1)
const pageSize = ref(50)

const availableTagsForSelection = computed(() => {
  if (!tagSearchQuery.value.trim()) {
    return allTags.value
  }
  const query = tagSearchQuery.value.toLowerCase()
  return allTags.value.filter(tag => tag.toLowerCase().includes(query))
})

const totalTagPages = computed(() => Math.ceil(availableTagsForSelection.value.length / pageSize.value) || 1)

const paginatedTags = computed(() => {
  const start = (tagPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return availableTagsForSelection.value.slice(start, end)
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

// 从reportData中提取初始tagMetricData，并计算平均值
const extractInitialTagMetricData = (reportData) => {
  // 添加防御性检查
  if (!reportData) {
    return {};
  }

  // 1. 优先使用后端预计算的 tagMetricData
  const preCalculatedRows = reportData.tagMetricData || reportData.summary?.tagMetricData || 
                           reportData.tag_metric_data || reportData.summary?.tag_metric_data;
  
  if (Array.isArray(preCalculatedRows) && preCalculatedRows.length > 0) {
    const mergedData = {};
    preCalculatedRows.forEach(row => {
      if (!row) return;
      if (Array.isArray(row.tags)) {
        const resourceKey = row.resource || '0-默认资源';
        row.tags.forEach(t => {
          if (!t) return;
          const tag = t.tagName || t.tagId || '未标记';
          if (!mergedData[tag]) mergedData[tag] = {};
          if (!mergedData[tag][resourceKey]) mergedData[tag][resourceKey] = {};
          (t.metrics || []).forEach(m => {
            if (!m || !m.metric) return;
            mergedData[tag][resourceKey][m.metric] = Number(m.value ?? 0);
          });
        });
      } else {
        const tag = row.tagName || row.tagId || '未标记';
        const resourceKey = row.resource || '0-默认资源';
        if (!mergedData[tag]) mergedData[tag] = {};
        if (!mergedData[tag][resourceKey]) mergedData[tag][resourceKey] = {};
        if (Array.isArray(row.metrics)) {
          row.metrics.forEach(m => {
            if (!m || !m.metric) return;
            mergedData[tag][resourceKey][m.metric] = Number(m.value ?? 0);
          });
        } else {
          const metricName = row.metric;
          if (!metricName) return;
          mergedData[tag][resourceKey][metricName] = Number(row.value ?? 0);
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
      
      Object.keys(mergedData).forEach(tag => {
        const resources = mergedData[tag] || {};
        Object.keys(resources).forEach(resourceKey => {
          const resourceRawData = rawMap[resourceKey];
          if (!resourceRawData) return;
          Object.keys(resourceRawData).forEach(metricName => {
            mergedData[tag][resourceKey][`${metricName}_raw`] = resourceRawData[metricName];
          });
        });
      });
    }
    
    return mergedData;
  }
  
  // 3. Fallback: Reconstruct tagMetricData from reportData.summary.cases
  const cases = reportData.cases || reportData.summary?.cases;
  if (cases && Array.isArray(cases) && cases.length > 0) {
    console.log('[CaseTagComparison] Reconstructing tagMetricData from cases');
    const reconstructedData = {};
    const accumulator = {}; // { tag: { resource: { dim: { sum: 0, count: 0, values: [] } } } }

    cases.forEach(caseItem => {
      const rawTags = caseItem.tags;
      const tags = Array.isArray(rawTags) && rawTags.length > 0 ? rawTags : ['未标记'];
      const caseMetrics = caseItem.metrics || {};
      
      tags.forEach(tag => {
        const tagName = typeof tag === 'string' ? tag : tag.name;
        if (!tagName) return;

        if (!accumulator[tagName]) accumulator[tagName] = {};

        if (Array.isArray(caseMetrics)) {
          caseMetrics.forEach(group => {
            if (!group || !group.resource || !Array.isArray(group.metrics)) return;
            const resourceKey = group.resource;
            if (!accumulator[tagName][resourceKey]) accumulator[tagName][resourceKey] = {};
            group.metrics.forEach(m => {
              if (!m || !m.metric) return;
              const dim = m.metric;
              if (!accumulator[tagName][resourceKey][dim]) {
                accumulator[tagName][resourceKey][dim] = { sum: 0, count: 0, values: [] };
              }
              const val = m.value;
              if (val !== null && val !== undefined) {
                accumulator[tagName][resourceKey][dim].sum += Number(val);
                accumulator[tagName][resourceKey][dim].count += 1;
                accumulator[tagName][resourceKey][dim].values.push(Number(val));
              }
            });
          });
        } else {
          Object.keys(caseMetrics).forEach(resourceKey => {
            if (!accumulator[tagName][resourceKey]) accumulator[tagName][resourceKey] = {};
            
            const metrics = caseMetrics[resourceKey];
            Object.keys(metrics).forEach(dim => {
              if (!accumulator[tagName][resourceKey][dim]) {
                accumulator[tagName][resourceKey][dim] = { sum: 0, count: 0, values: [] };
              }
              const val = metrics[dim];
              if (val !== null && val !== undefined) {
                 accumulator[tagName][resourceKey][dim].sum += Number(val);
                 accumulator[tagName][resourceKey][dim].count += 1;
                 accumulator[tagName][resourceKey][dim].values.push(Number(val));
              }
            });
          });
        }
      });
    });

    // Calculate averages
    Object.keys(accumulator).forEach(tag => {
      reconstructedData[tag] = {};
      Object.keys(accumulator[tag]).forEach(resourceKey => {
        reconstructedData[tag][resourceKey] = {};
        Object.keys(accumulator[tag][resourceKey]).forEach(dim => {
          const stats = accumulator[tag][resourceKey][dim];
          if (stats.count > 0) {
            reconstructedData[tag][resourceKey][dim] = Number((stats.sum / stats.count).toFixed(4));
            reconstructedData[tag][resourceKey][`${dim}_raw`] = stats.values;
          } else {
            reconstructedData[tag][resourceKey][dim] = 0;
          }
        });
      });
    });
    
    return reconstructedData;
  }

  // 2. 如果没有预计算数据，则从 detailedResults 中提取 (原有逻辑)
  // 注意：不再使用reportData.tagMetricData或summary.tagMetricData，因为这会导致所有标签显示相同的平均值
  // 只从detailedResults中提取数据，确保每个标签有自己的平均值
  // 优先使用reportData.detailedResults，如果没有则使用reportData.summary?.detailedResults
  const detailedResults = reportData.detailedResults || reportData.summary?.detailedResults || [];
  if (detailedResults && detailedResults.length > 0) {
    // 从detailedResults中提取数据，计算平均值，构建tagMetricData
    const dataAccumulator = {};
    
    detailedResults.forEach(result => {
      // 获取测试用例信息，用于确定标签和类别
      const testCaseId = result.testCaseId;
      let tagObjects = [];
      let tags = [];
      
      // 1. 使用后端新添加的testCaseTags作为标签（包含ID信息）
      if (result.testCaseTags && result.testCaseTags.length > 0) {
        tagObjects = result.testCaseTags;
        tags = tagObjects.map(tag => tag.name);
      }
      // 2. 尝试从cases中获取测试用例的标签
      else if (reportData.cases) {
        const testCase = reportData.cases.find(c => c.id === testCaseId);
        if (testCase && testCase.tags) {
          tags = testCase.tags;
          tagObjects = tags.map(tag => ({ id: tag, name: tag })); // 兼容旧数据
        }
      }
      
      // 3. 如果cases中没有，从result.testCase.tags获取标签
      if (result.testCase?.tags && result.testCase.tags.length > 0) {
        tags = result.testCase.tags;
        tagObjects = tags.map(tag => ({ id: tag, name: tag })); // 兼容旧数据
      }
      
      // 4. 如果还是没有标签，使用默认标签（用于测试数据）
      if (tags.length === 0) {
        // 从referenceText中提取标签，例如使用前几个字符
        if (result.asr?.referenceText) {
          const defaultTag = result.asr.referenceText.slice(0, 5);
          tags = [defaultTag];
          tagObjects = [{ id: defaultTag, name: defaultTag }];
        } else {
          // 如果还是没有，使用测试用例ID的前5个字符作为标签
          const defaultTag = testCaseId.slice(0, 5);
          tags = [defaultTag];
          tagObjects = [{ id: defaultTag, name: defaultTag }];
        }
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
      
      // 为每个标签初始化累加器数据结构，使用标签名称作为键（保持与UI显示一致）
      tagObjects.forEach(tagObj => {
        const tagName = tagObj.name;
        
        if (!dataAccumulator[tagName]) {
          dataAccumulator[tagName] = {};
        }
        if (!dataAccumulator[tagName][resourceKey]) {
          dataAccumulator[tagName][resourceKey] = {
            counts: {},
            sums: {},
            values: {} // 保存所有值用于计算正态分布
          };
        }
        
        // 提取并累加维度得分
        if (result.dimensionScores) {
          result.dimensionScores.forEach(dim => {
            // 初始化维度数据
            if (!dataAccumulator[tagName][resourceKey].counts[dim.dimensionName]) {
              dataAccumulator[tagName][resourceKey].counts[dim.dimensionName] = 0;
              dataAccumulator[tagName][resourceKey].sums[dim.dimensionName] = 0;
              dataAccumulator[tagName][resourceKey].values[dim.dimensionName] = [];
            }
            
            // 累加计数和总和
            dataAccumulator[tagName][resourceKey].counts[dim.dimensionName]++;
            dataAccumulator[tagName][resourceKey].sums[dim.dimensionName] += dim.score;
            dataAccumulator[tagName][resourceKey].values[dim.dimensionName].push(dim.score);
          });
        } else if (result.metrics) {
          // 如果没有dimensionScores，尝试从metrics中获取
          Object.entries(result.metrics).forEach(([dimName, value]) => {
            // 初始化维度数据
            if (!dataAccumulator[tagName][resourceKey].counts[dimName]) {
              dataAccumulator[tagName][resourceKey].counts[dimName] = 0;
              dataAccumulator[tagName][resourceKey].sums[dimName] = 0;
              dataAccumulator[tagName][resourceKey].values[dimName] = [];
            }
            
            // 累加计数和总和
            dataAccumulator[tagName][resourceKey].counts[dimName]++;
            dataAccumulator[tagName][resourceKey].sums[dimName] += value;
            dataAccumulator[tagName][resourceKey].values[dimName].push(value);
          });
        }
      });
    });
    
    // 计算平均值，构建最终的tagMetricData
    const extractedTagMetricData = {};
    
    Object.entries(dataAccumulator).forEach(([tag, resources]) => {
      extractedTagMetricData[tag] = {};
      
      Object.entries(resources).forEach(([resourceKey, data]) => {
        // 提取资源名称（去掉ID前缀）
        const resourceName = resourceKey.includes('_') ? resourceKey.split('_').slice(1).join('_') : resourceKey;
        
        // 初始化标签下的资源数据
        if (!extractedTagMetricData[tag][resourceName]) {
          extractedTagMetricData[tag][resourceName] = {};
        }
        if (!extractedTagMetricData[tag][resourceKey]) {
          extractedTagMetricData[tag][resourceKey] = {};
        }
        
        // 计算每个维度的平均值 - 确保是某个标签下所有用例的某个维度平均值
        Object.entries(data.counts).forEach(([dimName, count]) => {
          const sum = data.sums[dimName];
          const average = count > 0 ? sum / count : 0;
          
          // 同时保存到资源名称和资源键下，确保getMetricValue能够找到数据
          extractedTagMetricData[tag][resourceName][dimName] = average;
          extractedTagMetricData[tag][resourceKey][dimName] = average;
          
          // 保存原始值用于正态分布图
          extractedTagMetricData[tag][resourceName][`${dimName}_raw`] = data.values[dimName];
          extractedTagMetricData[tag][resourceKey][`${dimName}_raw`] = data.values[dimName];
        });
      });
    });
    
    return extractedTagMetricData;
  }
  
  return {};
};

// 使用ref管理内部tagMetricData状态
const tagMetricData = ref({});

// 初始化和更新数据的函数
const updateData = (reportData) => {
  // 添加防御性检查
  if (!reportData) {
    reportData = {};
  }
  
  // 1. 先获取直接提供的标签，同时检查allTags和allCaseTags
  let tags = [
    ...(reportData.allTags || reportData.summary?.allTags || []),
    ...(reportData.allCaseTags || reportData.summary?.allCaseTags || [])
  ];
  
  // 处理标签：如果是对象数组，提取name属性
  tags = tags.map(tag => typeof tag === 'object' ? tag.name : tag);
  
  // 2. 从detailedResults中提取标签数据
  const extractedTagMetricData = extractInitialTagMetricData(reportData) || {};
  
  // 3. 从提取的tagMetricData中获取所有标签
  const extractedTags = Object.keys(extractedTagMetricData);
  
  // 4. 直接从detailedResults中提取所有标签，确保不遗漏
  let detailedTags = [];
  if (reportData.detailedResults) {
    reportData.detailedResults.forEach(result => {
      if (result.testCase?.tags) {
        const caseTags = result.testCase.tags.map(tag => typeof tag === 'object' ? tag.name : tag);
        detailedTags = [...detailedTags, ...caseTags];
      }
    });
  }

  if (reportData.detailedResults) {
    const hasUntaggedCase = reportData.detailedResults.some(r => {
      const tags = r?.testCase?.tags
      return !Array.isArray(tags) || tags.length === 0
    })
    if (hasUntaggedCase) detailedTags = [...detailedTags, '未标记']
  }
  
  // 5. 合并所有标签，确保不重复
  const mergedTags = [...new Set([...tags, ...extractedTags, ...detailedTags])];
  
  // 6. 更新所有数据
  allTags.value = mergedTags;
  
  // 处理caseCategories：如果是对象数组，提取name属性
  const categories = reportData.caseCategories || reportData.summary?.caseCategories || [];
  const mappedCategories = categories.map(cat => typeof cat === 'object' ? cat.name : cat);
  if (reportData.detailedResults) {
    const hasUncategorized = reportData.detailedResults.some(r => !r?.testCaseGroup)
    if (hasUncategorized && !mappedCategories.includes('未分类')) mappedCategories.push('未分类')
  }
  caseCategories.value = mappedCategories;
  
  allMetrics.value = reportData.allMetrics || reportData.summary?.allMetrics || [];
  tagMetricData.value = extractedTagMetricData;
  devices.value = getValidResources(reportData);
  
  // 7. 重置选中状态：默认不选中任何条件（显示全部）
  selectedTags.value = [];
  selectedCategories.value = [];
  selectedMetrics.value = [];
};

// 初始化数据
updateData(props.reportData);

// 监听reportData变化，更新内部状态
watch(() => props.reportData, (newReportData) => {
  updateData(newReportData);
}, { deep: true })

const displayTypes = [
  { type: 'table', label: '表格', icon: 'fas fa-table' },
  { type: 'bar', label: '柱状图', icon: 'fas fa-chart-bar' },
  { type: 'line', label: '折线图', icon: 'fas fa-chart-line' },
  { type: 'radar', label: '雷达图', icon: 'fas fa-chart-radar' },
  { type: 'distribution', label: '正态分布图', icon: 'fas fa-chart-area' }
]

const activeDisplayType = ref('table')

// Computed
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
      console.error('[CaseTagComparison] Failed to save header edits:', e)
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

const commitEditResource = (resourceKey) => {
  if (editingResourceKey.value !== resourceKey) return
  const next = String(editingResourceValue.value ?? '').trim()
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

const editingTagKey = ref(null)
const editingTagValue = ref('')

const startEditTag = (tagName) => {
  editingTagKey.value = tagName
  editingTagValue.value = String(tagName ?? '')
}

const commitEditTag = (oldName) => {
  if (editingTagKey.value !== oldName) return
  const next = String(editingTagValue.value ?? '').trim()
  editingTagKey.value = null
  if (!next || next === oldName) return

  if (tagMetricData.value && tagMetricData.value[oldName] && !tagMetricData.value[next]) {
    tagMetricData.value[next] = tagMetricData.value[oldName]
    delete tagMetricData.value[oldName]
  }
  allTags.value = allTags.value.map(t => (t === oldName ? next : t))
  selectedTags.value = selectedTags.value.map(t => (t === oldName ? next : t))

  const report = props.reportData || {}
  const summary = report.summary || report
  const tags = summary.allCaseTags || summary.all_case_tags || summary.allTags || summary.all_tags || report.allCaseTags || report.all_case_tags || []
  if (Array.isArray(tags)) {
    const target = tags.find(t => t && typeof t === 'object' && t.name === oldName)
    if (target) target.name = next
  }
  scheduleSaveSummary({ allCaseTags: tags, allTags: tags })
}

const processedDevices = computed(() => {
  return devices.value.map(device => getResourceLabel(device))
})

const filteredTags = computed(() => {
  if (selectedTags.value.length === 0) {
    return allTags.value
  }
  return selectedTags.value
})

// 根据selectedCategories过滤标签数据
const filteredTagMetricData = computed(() => {
  if (selectedCategories.value.length === 0) {
    return tagMetricData.value
  }

  const filteredData = {};

  const data = tagMetricData.value || {};
  for (const [tag, resources] of Object.entries(data)) {
    if (filteredTags.value.includes(tag)) {
      filteredData[tag] = resources
    }
  }

  return filteredData
})

const filteredMetrics = computed(() => {
  if (selectedMetrics.value.length === 0) {
    return allMetrics.value
  }
  return allMetrics.value.filter(m => selectedMetrics.value.includes(m.name))
})

// Methods
const toggleTag = (tagName) => {
  const index = selectedTags.value.indexOf(tagName)
  if (index > -1) {
    selectedTags.value.splice(index, 1)
  } else {
    selectedTags.value.push(tagName)
  }
  applyFilters()
}



const toggleCategory = (category) => {
  const index = selectedCategories.value.indexOf(category)
  if (index > -1) {
    selectedCategories.value.splice(index, 1)
  } else {
    selectedCategories.value.push(category)
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

const resetFilters = () => {
  selectedTags.value = []
  selectedCategories.value = []
  selectedMetrics.value = []
  tagSearchQuery.value = ''
  tagPage.value = 1
  metricSearchQuery.value = ''
  metricPage.value = 1
  applyFilters()
}

const applyFilters = async () => {
  console.log('应用筛选:', {
    selectedTags: selectedTags.value,
    selectedCategories: selectedCategories.value,
    selectedMetrics: selectedMetrics.value
  });
  
  try {
    // 1. 调用API获取筛选后的数据
    const taskId = props.reportData.taskId || props.reportData.summary?.taskId;
    if (taskId) {
      const result = await reportsApi.getCaseAveragesByFilters(taskId, {
        tags: selectedTags.value,
        categories: selectedCategories.value
      });
      
      console.log('API返回结果:', result);
      
      // 更新内部tagMetricData ref，触发重新渲染
      const extractedFromApi = extractInitialTagMetricData(result);
      if (extractedFromApi && Object.keys(extractedFromApi).length > 0) {
        tagMetricData.value = extractedFromApi;
        return;
      }
    } else {
      // 2. 如果没有taskId，使用本地数据进行筛选
      // 从detailedResults中提取筛选后的标签数据
      const filteredDetailedResults = [];
      
      // 筛选detailedResults，只保留符合类别条件的结果
      ;(props.reportData.detailedResults || []).forEach(result => {
        let categoryName = "未分类";
        // 处理testCaseGroup，可能是对象或字符串
        if (result.testCaseGroup) {
          if (typeof result.testCaseGroup === 'object') {
            categoryName = result.testCaseGroup.name;
          } else {
            categoryName = result.testCaseGroup;
          }
        }
        if (selectedCategories.value.includes(categoryName)) {
          filteredDetailedResults.push(result);
        }
      });
      
      // 创建临时报告数据，只包含筛选后的detailedResults
      const tempReportData = {...props.reportData, detailedResults: filteredDetailedResults};
      
      // 重新提取标签数据
      const extractedTagMetricData = extractInitialTagMetricData(tempReportData);
      
      // 更新内部tagMetricData ref，触发重新渲染
      tagMetricData.value = extractedTagMetricData;
      return;
    }

    const filteredDetailedResults = [];
    ;(props.reportData.detailedResults || []).forEach(result => {
      let categoryName = "未分类";
      if (result.testCaseGroup) {
        if (typeof result.testCaseGroup === 'object') {
          categoryName = result.testCaseGroup.name;
        } else {
          categoryName = result.testCaseGroup;
        }
      }
      if (selectedCategories.value.includes(categoryName)) {
        filteredDetailedResults.push(result);
      }
    });
    const tempReportData = { ...props.reportData, detailedResults: filteredDetailedResults };
    tagMetricData.value = extractInitialTagMetricData(tempReportData);
  } catch (error) {
    console.error('调用API失败:', error);
    
    // 3. API调用失败时，使用本地数据进行筛选
    // 从detailedResults中提取筛选后的标签数据
    const filteredDetailedResults = [];
    
    // 筛选detailedResults，只保留符合类别条件的结果
    ;(props.reportData.detailedResults || []).forEach(result => {
      let categoryName = "未分类";
      // 处理testCaseGroup，可能是对象或字符串
      if (result.testCaseGroup) {
        if (typeof result.testCaseGroup === 'object') {
          categoryName = result.testCaseGroup.name;
        } else {
          categoryName = result.testCaseGroup;
        }
      }
      if (selectedCategories.value.includes(categoryName)) {
        filteredDetailedResults.push(result);
      }
    });
    
    // 创建临时报告数据，只包含筛选后的detailedResults
    const tempReportData = {...props.reportData, detailedResults: filteredDetailedResults};
    
    // 重新提取标签数据
    const extractedTagMetricData = extractInitialTagMetricData(tempReportData);
    
    // 更新内部tagMetricData ref，触发重新渲染
    tagMetricData.value = extractedTagMetricData;
  }
}

const getMetricValue = (tag, device, metricName) => {
  // 使用过滤后的tagMetricData
  const dataToUse = filteredTagMetricData.value;
  if (dataToUse) {
    const tagData = dataToUse[tag];
    if (tagData) {
      // 首先尝试直接使用device作为key查找数据
      let deviceData = tagData[device];
      
      // 如果找不到，尝试使用resource key（包含ID前缀）查找数据
      if (!deviceData || deviceData[metricName] === undefined) {
        // 遍历tagData中的所有资源，找到名称匹配的资源
        for (const [resourceKey, data] of Object.entries(tagData)) {
          // 直接实现getResourceName的逻辑
          const currentResourceName = resourceKey.includes('_') ? resourceKey.split('_').slice(1).join('_') : resourceKey;
          if (currentResourceName === device) {
            deviceData = data;
            break;
          }
        }
      }
      
      if (deviceData && deviceData[metricName] !== undefined) {
        return deviceData[metricName];
      }
    }
  }
  
  // 如果没有真实数据，返回0作为默认值
  return 0 
}

const getMetricDisplayValue = (tag, device, metricName) => {
  return formatMetricForDisplay(metricName, getMetricValue(tag, device, metricName))
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
  // 如果是正态分布图，使用前端自己的计算逻辑
  if (activeDisplayType.value === 'distribution') {
    // 收集所有原始数据点，用于计算统计信息
    let allRawData = [];
    const deviceRawDataMap = {};
    
    // 初始化设备原始数据映射
    devices.value.forEach(device => {
      deviceRawDataMap[device] = [];
    });
    
    // 收集所有原始数据
    devices.value.forEach(device => {
      filteredTags.value.forEach(tag => {
        // 获取原始值数组
        const rawDataKey = `${metricName}_raw`;
        let rawData = [];
        
        if (filteredTagMetricData.value && filteredTagMetricData.value[tag] && filteredTagMetricData.value[tag][device]) {
          rawData = filteredTagMetricData.value[tag][device][rawDataKey] || [];
        }
        
        // 添加到设备原始数据和总原始数据中
        deviceRawDataMap[device] = deviceRawDataMap[device].concat(rawData);
        allRawData = allRawData.concat(rawData);
      });
    });
    
    // 直接使用前端计算逻辑，不再依赖后端数据
    // 计算正态分布统计信息
    const calculateNormalDistribution = (data) => {
      if (!data || data.length === 0) {
        return null;
      }
      
      // 排序数据用于计算五数概括
      const sortedData = [...data].sort((a, b) => a - b);
      
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
    
    // 生成10个数据区间
    const intervals = 10;
    const minValue = distribution.mean - 4 * distribution.stdDev;
    const maxValue = distribution.mean + 4 * distribution.stdDev;
    const intervalWidth = (maxValue - minValue) / intervals;
    
    const labels = [];
    for (let i = 0; i < intervals; i++) {
      const start = parseFloat((minValue + i * intervalWidth).toFixed(2));
      const end = parseFloat((start + intervalWidth).toFixed(2));
      labels.push(`${start}-${end}`);
    }
    
    // 为每个设备生成正态分布数据
    const chartData = {
      labels: labels, 
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
            data: Array(intervals).fill(0), 
            backgroundColor: color, 
            borderColor: borderColor, 
            borderWidth: 1, 
            fill: true, 
            tension: 0.3
          };
        }
        
        // 使用正态分布公式计算每个区间的理论数据点数量
        const values = [];
        for (let i = 0; i < intervals; i++) {
          const start = parseFloat((minValue + i * intervalWidth).toFixed(2));
          const end = parseFloat((start + intervalWidth).toFixed(2));
          const midPoint = (start + end) / 2;
          
          // 正态分布公式
          const normalDensity = (1 / (deviceDistribution.stdDev * Math.sqrt(2 * Math.PI))) * 
                              Math.exp(-0.5 * Math.pow((midPoint - deviceDistribution.mean) / deviceDistribution.stdDev, 2));
          const count = Math.round(normalDensity * deviceDistribution.totalDataPoints * intervalWidth);
          values.push(count);
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
      rawData: allRawData
    };
    
    return chartData;
  }
  
  // 非正态分布图，使用原有逻辑
  // 生成图表数据
  const chartData = {
    labels: filteredTags.value, 
    datasets: devices.value.map((device, index) => {
      // 使用预定义的颜色，根据设备索引选择，确保相同设备始终使用相同颜色
      const color = chartColors[index % chartColors.length]
      const borderColor = chartBorderColors[index % chartBorderColors.length]

      // 为每个设备生成数据，只包含筛选后的标签
      const data = filteredTags.value.map(tag => {
        // 调用getMetricValue获取数据，它会使用过滤后的tagMetricData
        return parseFloat(getMetricValue(tag, device, metricName))
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
.case-tag-comparison {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  margin-bottom: 20px;
}

.section-header {
  margin-bottom: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  padding: 12px 16px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  transition: all 0.3s ease;
}

.section-header:hover {
  background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin: 0;
  flex: 1;
}

.collapse-btn {
  background: none;
  border: none;
  font-size: 16px;
  color: #64748b;
  cursor: pointer;
  padding: 8px;
  border-radius: 6px;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: 16px;
}

.collapse-btn:hover {
  background: rgba(0, 0, 0, 0.05);
  color: #1677ff;
}

.collapse-btn.collapsed {
  transform: rotate(180deg);
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

/* Filter Card Styles */
.filter-card {
  background: white;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  padding: 20px 24px;
  margin-bottom: 24px;
  opacity: 1;
  transform: translateY(0);
  transition: all 0.5s ease;
}

.filter-title {
  font-weight: 600;
  color: #1e293b;
  font-size: 16px;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.filter-content {
  margin-bottom: 20px;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  margin-bottom: 20px;
}

.filter-item {
  flex: 1;
  min-width: 200px;
}

.filter-label {
  display: block;
  font-weight: 600;
  color: #64748b;
  font-size: 14px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.tag-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  min-height: 80px;
  width: 100%;
  box-sizing: border-box;
}

.tag-filter-item {
  padding: 6px 12px;
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  font-weight: 500;
}

.tag-filter-item:hover {
  background: #e2e8f0;
  color: #334155;
}

.tag-filter-item.active {
  background: #1677ff;
  color: white;
  border-color: #1677ff;
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.3);
}

.tag-filter-section {
  min-width: 300px;
}

.filter-hint {
  font-weight: normal;
  color: #10b981;
  font-size: 12px;
  margin-left: 8px;
}

.filter-count {
  font-weight: normal;
  color: #1677ff;
  font-size: 12px;
  margin-left: 8px;
}

.tag-search-box {
  position: relative;
  margin-bottom: 12px;
  display: block;
  width: 100%;
  min-height: 36px;
  box-sizing: border-box;
}

.tag-search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: #94a3b8;
  font-size: 14px;
}

.tag-search-input {
  width: 100%;
  padding: 8px 32px 8px 36px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
  transition: all 0.2s ease;
  box-sizing: border-box;
}

.tag-search-input:focus {
  outline: none;
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.1);
}

.tag-search-clear {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  padding: 4px;
  font-size: 12px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
}

.tag-search-clear.visible {
  opacity: 1;
  pointer-events: auto;
}

.tag-search-clear:hover {
  color: #64748b;
}

.tag-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #e2e8f0;
}

.pagination-btn {
  padding: 6px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: white;
  color: #64748b;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s ease;
}

.pagination-btn:hover:not(:disabled) {
  border-color: #1677ff;
  color: #1677ff;
}

.pagination-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pagination-info {
  font-size: 13px;
  color: #64748b;
}

.case-type-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  min-height: 80px;
  width: 100%;
  box-sizing: border-box;
}

.case-type-item {
  padding: 6px 12px;
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  font-weight: 500;
}

.case-type-item:hover {
  background: #e2e8f0;
  color: #334155;
}

.case-type-item.active {
  background: #ff6a00;
  color: white;
  border-color: #ff6a00;
  box-shadow: 0 2px 8px rgba(255, 106, 0, 0.3);
}

/* No Data Tip */
.no-data-tip {
  color: #94a3b8;
  font-size: 13px;
  font-style: italic;
  padding: 12px;
  text-align: center;
  width: 100%;
}

.filter-buttons {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}

/* Metric Selection Styles */
.metric-selection {
  background: white;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  padding: 20px 24px;
  margin-bottom: 24px;
}

.metric-selection-title {
  font-weight: 600;
  color: #1e293b;
  font-size: 16px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.metric-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.metric-tag {
  padding: 10px 20px;
  border: 2px solid #e2e8f0;
  border-radius: 25px;
  background: white;
  color: #64748b;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  position: relative;
}

.metric-tag i {
  font-size: 12px;
  opacity: 0.5;
  transition: all 0.3s ease;
}

.metric-tag:hover {
  border-color: #1677ff;
  color: #1677ff;
  box-shadow: 0 4px 12px rgba(22, 119, 255, 0.2);
}

.metric-tag.active {
  background: linear-gradient(135deg, #1677ff 0%, #3690ff 100%);
  color: white;
  border-color: #1677ff;
  box-shadow: 0 4px 12px rgba(22, 119, 255, 0.3);
}

.metric-tag.active i {
  opacity: 1;
  color: white;
}

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

.metric-search-box {
  position: relative;
  margin-bottom: 16px;
}

.metric-search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: #94a3b8;
  font-size: 14px;
}

.metric-search-input {
  width: 100%;
  max-width: 300px;
  padding: 8px 32px 8px 36px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
  transition: all 0.2s ease;
  box-sizing: border-box;
}

.metric-search-input:focus {
  outline: none;
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.1);
}

.metric-search-clear {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  padding: 4px;
  font-size: 12px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
}

.metric-search-clear.visible {
  opacity: 1;
  pointer-events: auto;
}

.metric-search-clear:hover {
  color: #64748b;
}

.metric-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}

.metric-selection-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Metric Container Styles */
.metric-container {
  background: white;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  overflow: hidden;
  margin-bottom: 24px;
}

.metric-table-title {
  color: #334155;
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  padding: 16px 24px;
  border-bottom: 2px solid #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  cursor: pointer;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  transition: all 0.3s ease;
}

.metric-table-title:hover {
  background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
}

.title-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.metric-collapse-btn {
  background: none;
  border: none;
  font-size: 14px;
  color: #64748b;
  cursor: pointer;
  padding: 8px;
  border-radius: 6px;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: auto;
}

.metric-collapse-btn:hover {
  background: rgba(0, 0, 0, 0.05);
  color: #1677ff;
}

.metric-collapse-btn.collapsed {
  transform: rotate(180deg);
}

.metric-container-content {
  padding: 0 24px 24px;
  transition: all 0.3s ease;
  animation: slideDown 0.3s ease-out;
}

/* Display Type Selector */
.display-type-selector {
  background: white;
  border-bottom: 1px solid #e2e8f0;
  padding: 16px 0;
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.display-type-title {
  font-weight: 600;
  color: #334155;
  font-size: 14px;
  margin-right: 12px;
}

.display-type-btn {
  padding: 8px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: white;
  color: #475569;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  gap: 6px;
}

.display-type-btn:hover {
  border-color: #1677ff;
  color: #1677ff;
}

.display-type-btn.active {
  background: #1677ff;
  color: white;
  border-color: #1677ff;
}

/* Table Styles */
.table-container {
  padding: 0;
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  background: white;
}

.data-table th {
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  font-weight: 600;
  padding: 16px 20px;
  text-align: left;
  border-bottom: 2px solid #e2e8f0;
  color: #1e293b;
  font-size: 14px;
}

.data-table th:not(:first-child) {
  background: linear-gradient(135deg, rgba(255, 106, 0, 0.1) 0%, rgba(255, 106, 0, 0.05) 100%);
  text-align: center;
}

.data-table td {
  padding: 16px 20px;
  text-align: left;
  border-bottom: 1px solid #f1f5f9;
  font-weight: 500;
  font-size: 15px;
}

.data-table td:not(:first-child) {
  text-align: center;
  color: #1677ff;
}

.data-table tr {
  transition: all 0.3s ease;
  border-bottom: 1px solid #f1f5f9;
}

.data-table tr:hover {
  background-color: #f8fafc;
  transform: translateX(4px);
}

/* Chart Container */
.chart-container {
  padding: 20px 0;
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

/* Flex Search Box */
.search-box-flex {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 0 12px;
  background-color: white;
  transition: all 0.2s ease;
  height: 36px;
}

.search-box-flex:focus-within {
  outline: none;
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.1);
}

.search-box-flex .search-icon {
  color: #94a3b8;
  font-size: 14px;
  flex-shrink: 0;
  margin-right: 8px;
}

.search-box-flex .search-input {
  flex-grow: 1;
  flex-shrink: 1;
  border: none;
  padding: 0 8px;
  font-size: 13px;
  outline: none;
  background: transparent;
  height: 100%;
}

.search-box-flex .search-clear {
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  padding: 4px;
  font-size: 12px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
  flex-shrink: 0;
  margin-left: auto;
}

.search-box-flex .search-clear.visible {
  opacity: 1;
  pointer-events: auto;
}

.search-box-flex .search-clear:hover {
  color: #64748b;
}
</style>
