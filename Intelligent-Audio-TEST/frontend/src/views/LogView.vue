<!-- 
  purpose: View template for the Log View page.
  MVC role: View
-->
<template>
  <div class="log-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-file-alt"></i>
          日志查看
        </h2>
        <p class="page-description">查看系统操作日志、测试执行日志和错误日志</p>
      </div>
      <div class="header-right">
        <div class="header-actions">
          <button class="btn btn-text" @click="toggleRealTimeLog" :class="{ 'active': realTimeLogEnabled }" style="color: var(--primary-color);">
            <i class="fas fa-sync-alt btn-icon" :class="{ 'fa-spin': realTimeLogEnabled }" style="color: var(--primary-color);"></i>
            <span style="color: var(--primary-color);">{{ realTimeLogStatus  }}</span>
          </button>
          <button class="btn btn-text" @click="refreshLogs" style="color: var(--primary-color);">
            <i class="fas fa-redo-alt btn-icon" style="color: var(--primary-color);"></i>
            <span style="color: var(--primary-color);">刷新日志</span>
          </button>
          <button class="btn btn-text" @click="exportLogs" style="color: var(--primary-color);">
            <i class="fas fa-download btn-icon" style="color: var(--primary-color);"></i>
            <span style="color: var(--primary-color);">导出日志</span>
          </button>
          <button class="btn btn-text delete" @click="clearLogs" style="color: var(--primary-color);">
            <i class="fas fa-trash-alt btn-icon" style="color: var(--primary-color);"></i>
            <span style="color: var(--primary-color);">清除日志</span>
          </button>
        </div>
      </div>
    </div>

    <!-- 筛选和操作栏 -->
    <div class="filter-section">
      <div class="filter-bar advanced">
        <!-- 第一行：搜索、分类、模块、日志大小和操作 -->
        <div class="filter-row main-row">
          <div class="search-box">
            <i class="fas fa-search search-icon"></i>
            <input type="text" class="search-input" placeholder="搜索日志内容..." v-model="searchTerm" @input="searchLogs">
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
        
        <!-- 第二行：时间范围、标记筛选 -->
        <div class="filter-row secondary-row">
          <div class="filter-group time-range-group">
            <label class="filter-label">时间范围:</label>
            <div class="date-time-inputs">
              <div class="filter-select" ref="startContainerRef">
                <input type="datetime-local" class="form-input" ref="startDateTimeRef" v-model="filters.startDateTime" @change="filterLogs">
              </div>
              <span class="date-separator">至</span>
              <div class="filter-select" ref="endContainerRef">
                <input type="datetime-local" class="form-input" ref="endDateTimeRef" v-model="filters.endDateTime" @change="filterLogs">
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

    <!-- 实时监控指示器 -->
    <div class="monitor-indicator" v-show="showMonitorIndicator">
      <div class="monitor-status">
        <i class="fas fa-circle monitor-icon" :class="{ 'connected': connectionStatus === '已连接', 'disconnected': connectionStatus !== '已连接' }"></i>
        <span class="monitor-text">实时监控中</span>
        <span class="monitor-stats">
          <span class="stat-item">连接: <span>{{ connectionStatus }}</span></span>
          <span class="stat-item">速率: <span>{{ logRate }}</span> 条/秒</span>
          <span class="stat-item">延迟: <span>{{ logDelay }}ms</span></span>
        </span>
        <div class="monitor-controls">
        <button class="btn btn-secondary" @click="toggleAutoScroll">
          <i class="fas fa-sort-amount-down btn-icon"></i>
          <span>{{ autoScrollText }}</span>
        </button>
        <button class="btn btn-secondary" @click="openMonitorConfig">
          <i class="fas fa-cog btn-icon"></i>
          配置
        </button>
      </div>
      </div>
    </div>

    <!-- 日志统计概览 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon total-icon">
          <i class="fas fa-file-alt"></i>
        </div>
        <div class="stat-content">
          <h3 class="stat-number">{{ totalLogs }}</h3>
          <p class="stat-label">总日志条数</p>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon error-icon">
          <i class="fas fa-exclamation-circle"></i>
        </div>
        <div class="stat-content">
          <h3 class="stat-number">{{ logStats.error }}</h3>
          <p class="stat-label">错误日志</p>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon warning-icon">
          <i class="fas fa-exclamation-triangle"></i>
        </div>
        <div class="stat-content">
          <h3 class="stat-number">{{ logStats.warning }}</h3>
          <p class="stat-label">警告日志</p>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon info-icon">
          <i class="fas fa-info-circle"></i>
        </div>
        <div class="stat-content">
          <h3 class="stat-number">{{ logStats.info }}</h3>
          <p class="stat-label">信息日志</p>
        </div>
      </div>
    </div>

    <!-- 单栏布局 -->
    <div class="single-column-layout">
      <!-- 日志内容区 -->
      <section class="logs-content">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">系统日志</h3>
            <div class="card-actions">
              <div class="marking-options">
                <select class="form-input-sm" v-model="markColor" style="margin-left: 12px; margin-right: 12px;">
                  <option value="yellow">黄色</option>
                  <option value="red">红色</option>
                  <option value="green">绿色</option>
                  <option value="blue">蓝色</option>
                </select>
                <button class="btn btn-secondary" @click="batchMarkLogs()">
                  <i class="fas fa-tags btn-icon"></i>
                  批量标记
                </button>
              </div>
            </div>
          </div>
          <div class="card-body">
            <div class="table-container">
              <table class="data-table" data-manual-sort>
                <thead>
                  <tr>
                    <th class="checkbox-col" style="width: 40px; min-width: 40px;">
                      <input type="checkbox" id="selectAllLogs" @change="selectAllLogs">
                    </th>
                    <th class="expand-header" style="width: 30px; min-width: 30px;"></th>
                    <th class="sortable core-col" @click="sortLogs('time')" style="width: 150px; min-width: 150px;">
                      时间
                      <i class="fas fa-sort sort-icon"></i>
                    </th>
                    <th class="sortable core-col" @click="sortLogs('level')" style="width: 100px; min-width: 100px;">
                      级别
                      <i class="fas fa-sort sort-icon"></i>
                    </th>
                    <th class="sortable secondary-col" @click="sortLogs('module')" style="width: 120px; min-width: 120px;">
                      模块
                      <i class="fas fa-sort sort-icon"></i>
                    </th>
                    <th class="secondary-col" style="width: 100px; min-width: 100px;">
                      算法
                    </th>
                    <th class="sortable secondary-col" @click="sortLogs('source')" style="width: 120px; min-width: 120px;">
                      来源
                      <i class="fas fa-sort sort-icon"></i>
                    </th>
                    <th class="core-col" style="flex: 1; min-width: 200px;">内容</th>
                    <th class="core-col" style="width: 200px; min-width: 200px;">操作</th>
                  </tr>
                </thead>
                <tbody id="logsTable">
                  <template v-for="log in paginatedLogs" :key="log.id">
                    <!-- 日志行 -->
                    <tr class="log-row" @click="toggleLogDetails(log.id)" :class="{ 'marked': log.mark, [`marked-${log.mark}`]: log.mark }" style="cursor: pointer;">
                      <td class="checkbox-col">
                        <input type="checkbox" class="log-checkbox" v-model="log.selected" @click.stop>
                      </td>
                      <td class="expand-col">
                        <i class="fas fa-chevron-down expand-icon" :class="{ 'fa-chevron-up': log.isExpanded }"></i>
                      </td>
                      <td @click.stop="toggleLogDetails(log.id)">{{ log.time }}</td>
                      <td @click.stop="toggleLogDetails(log.id)"><span class="log-level" :class="log.level">{{ log.level.toUpperCase() }}</span></td>
                      <td @click.stop="toggleLogDetails(log.id)"><span class="log-module">{{ log.module }}</span></td>
                      <td @click.stop="toggleLogDetails(log.id)"><span v-if="log.algorithmType" class="log-algorithm" :class="log.algorithmType">{{ getAlgorithmLabel(log.algorithmType) }}</span><span v-else>-</span></td>
                      <td @click.stop="toggleLogDetails(log.id)"><span class="log-source" :class="log.source">{{ log.source }}</span></td>
                      <td @click.stop="toggleLogDetails(log.id)" title="{{ log.content }}">
                        <span v-if="log.mark" class="log-mark" :class="log.mark"></span>
                        {{ log.content }}
                      </td>
                      <td>
                        <button class="btn btn-secondary" @click.stop="markLog(log.id)">
                          <i class="fas fa-tag btn-icon"></i>
                          标记
                        </button>
                        <button class="btn btn-secondary" @click.stop="copyLog(log.id)">
                          <i class="fas fa-copy btn-icon"></i>
                          复制
                        </button>
                      </td>
                    </tr>
                    <!-- 详情行 - 紧跟在对应日志行之后 -->
                    <tr class="log-details" :style="{ display: log.isExpanded ? 'table-row' : 'none' }">
                      <td colspan="9">
                        <div class="log-details-content">
                          <h4>详细信息</h4>
                          <p><strong>时间:</strong> {{ log.time }}</p>
                          <p><strong>级别:</strong> <span class="log-level" :class="log.level">{{ log.level.toUpperCase() }}</span></p>
                          <p><strong>分类:</strong> {{ log.category }}</p>
                          <p><strong>模块:</strong> <span class="log-module">{{ log.module }}</span></p>
                          <p><strong>算法类型:</strong> {{ log.algorithmType ? getAlgorithmLabel(log.algorithmType) : '-' }}</p>
                          <p><strong>来源:</strong> <span class="log-source" :class="log.source">{{ log.source }}</span></p>
                          <p><strong>设备ID:</strong> {{ log.deviceId || '-' }}</p>
                      <p><strong>任务ID:</strong> {{ log.taskId || '-' }}</p>
                      <p><strong>线程ID:</strong> {{ log.threadId || '-' }}</p>
                          <p><strong>内容:</strong> {{ log.content }}</p>
                          <h5>上下文信息</h5>
                          <pre>{{ JSON.stringify({ category: log.category, deviceDeviceId: log.deviceId, taskTaskId: log.taskId, threadThreadId: log.threadId, algorithmType: log.algorithmType }, null, 2) }}</pre>
                        </div>
                      </td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>
          </div>
          <div class="card-footer">
            <PaginationComponent 
              :current-page="currentPage"
              :page-size="pageSize"
              :total-items="totalLogs"
              @prev-page="handlePrevPage"
              @next-page="handleNextPage"
              @go-to-page="handleGoToPage"
              @page-size-change="handlePageSizeChange"
            />
          </div>
        </div>
      </section>
    </div>
    

  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, nextTick, watch, type Ref } from 'vue';
import { useRoute } from 'vue-router';
import PaginationComponent from '../components/common/PaginationComponent.vue';

// 日期时间选择器的引用
const startDateTimeRef = ref<HTMLInputElement | null>(null);
const endDateTimeRef = ref<HTMLInputElement | null>(null);
const startContainerRef = ref<HTMLElement | null>(null);
const endContainerRef = ref<HTMLElement | null>(null);

// 打开日期时间选择器
const openDateTimePicker = (inputRef: Ref<HTMLInputElement | null>) => {
  if (inputRef && inputRef.value) {
    // 直接调用输入框的showPicker方法（现代浏览器支持）
    if (typeof (inputRef.value as any).showPicker === 'function') {
      try {
        (inputRef.value as any).showPicker();
      } catch (error) {
        // 如果showPicker不可用，回退到模拟点击
        inputRef.value.focus();
        const event = new MouseEvent('click', {
          bubbles: true,
          cancelable: true,
          view: window
        });
        inputRef.value.dispatchEvent(event);
      }
    } else {
      // 回退方案：模拟点击
      inputRef.value.focus();
      const event = new MouseEvent('click', {
        bubbles: true,
        cancelable: true,
        view: window
      });
      inputRef.value.dispatchEvent(event);
    }
  }
};

// 定义命名事件处理函数
const handleStartDateClick = () => {
  openDateTimePicker(startDateTimeRef);
};

const handleEndDateClick = () => {
  openDateTimePicker(endDateTimeRef);
};

// 添加事件监听器
onMounted(() => {
  // 为开始时间容器添加点击事件
  if (startContainerRef.value) {
    startContainerRef.value.addEventListener('click', handleStartDateClick);
  }
  
  // 为结束时间容器添加点击事件
  if (endContainerRef.value) {
    endContainerRef.value.addEventListener('click', handleEndDateClick);
  }
});

// 清理事件监听器
onBeforeUnmount(() => {
  if (startContainerRef.value) {
    startContainerRef.value.removeEventListener('click', handleStartDateClick);
  }
  
  // 为结束时间容器添加点击事件
  if (endContainerRef.value) {
    endContainerRef.value.removeEventListener('click', handleEndDateClick);
  }
});

import { useLogView } from './LogViewLogic/logView';

const {
  realTimeLogEnabled,
  showMonitorIndicator,
  logRate,
  logDelay,
  connectionStatus,
  autoScrollEnabled,
  filters,
  advancedFilters,
  searchTerm,
  logLevels,
  selectedLevels,
  showAdvancedFilter,
  showLevelDropdown,
  markColor,
  logs,
  totalLogs,
  logStats,
  paginatedLogs,
  currentPage,
  pageSize,
  handlePrevPage,
  handleNextPage,
  handleGoToPage,
  handlePageSizeChange,
  realTimeLogStatus,
  advancedFilterText,
  autoScrollText,
  selectedLevelObjects,
  filterLogs,
  searchLogs,
  clearSearch,
  toggleAdvancedFilter,
  toggleLevelDropdown,
  selectAllLevels,
  clearAllLevels,
  clearAllFilters,
  refreshLogs,
  clearLogs,
  exportLogs,
  toggleRealTimeLog,
  toggleAutoScroll,
  openMonitorConfig,
  toggleLogDetails,
  selectAllLogs,
  markLog,
  batchMarkLogs,
  copyLog,
  deleteLog,
  sortLogs,
  removeLevel,
  toggleLevel,
  initLogView,
  cleanupLogView,
  algorithmOptions
} = useLogView();

// 日志配置默认值
const LOGCategoryOptions = [{ value: 'all', label: '所有分类' }, { value: 'system', label: '系统日志' }, { value: 'test', label: '测试日志' }, { value: 'error', label: '错误日志' }];
const LOGModuleOptions = [{ value: 'all', label: '所有模块' }, { value: 'api', label: 'API模块' }, { value: 'e2e', label: 'E2E测试' }, { value: 'device', label: '设备管理' }];
const LOGMarkOptions = [{ value: 'all', label: '所有标记' }, { value: 'yellow', label: '黄色标记' }, { value: 'red', label: '红色标记' }, { value: 'green', label: '绿色标记' }, { value: 'blue', label: '蓝色标记' }];

const getAlgorithmLabel = (algorithmType: string): string => {
  const option = algorithmOptions.value.find(opt => opt.value === algorithmType);
  return option ? option.label : algorithmType;
};

// 组件挂载时初始化日志视图
onMounted(async () => {
  await initLogView();
  // 组件挂载后强制重新计算高度
  nextTick(() => {
    adjustFilterCardHeight();
  });
});

// 组件卸载时清理
onBeforeUnmount(() => {
  cleanupLogView();
});

// 监听路由变化，确保组件可见时重新计算高度
const route = useRoute();
watch(
  () => route.path,
  () => {
    if (route.path === '/LogView') {
      nextTick(() => {
        adjustFilterCardHeight();
      });
    }
  }
);

// 调整筛选卡片高度的函数
function adjustFilterCardHeight() {
  const filterBar = document.querySelector('.log-view > .filter-section > .filter-bar') as HTMLElement;
  if (filterBar) {
    // 重置高度以触发重新计算
    filterBar.style.height = 'auto';
    // 强制重排
    filterBar.offsetHeight;
    // 再次设置为auto确保内容能正确撑开
    filterBar.style.height = 'auto';
  }
}
</script>

<style>
@import '../assets/styles/main.css';
</style>

<style scoped>
.single-column-layout {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  width: 100%;
}

.logs-content {
  width: 100%;
}

.logs-content .card {
  width: 100%;
}

.log-algorithm {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.log-algorithm.translation {
  background: #e6f7ff;
  color: #1890ff;
}

.log-algorithm.asr {
  background: #f6ffed;
  color: #52c41a;
}

.log-algorithm.speaker_recognition {
  background: #fff7e6;
  color: #fa8c16;
}

.log-algorithm.tts {
  background: #fff1f0;
  color: #f5222d;
}
</style>
