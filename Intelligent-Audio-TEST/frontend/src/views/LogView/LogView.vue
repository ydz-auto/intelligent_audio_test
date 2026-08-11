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

    <!-- 筛选和操作栏 + 高级过滤面板 -->
    <LogFilterPanel
      ref="filterPanelRef"
      :filters="filters"
      :advancedFilters="advancedFilters"
      :searchTerm="searchTerm"
      :logLevels="logLevels"
      :selectedLevels="selectedLevels"
      :showAdvancedFilter="showAdvancedFilter"
      :LOGCategoryOptions="LOGCategoryOptions"
      :LOGModuleOptions="LOGModuleOptions"
      :LOGMarkOptions="LOGMarkOptions"
      :algorithmOptions="algorithmOptions"
      :advancedFilterText="advancedFilterText"
      @search-logs="searchLogs"
      @clear-search="clearSearch"
      @filter-logs="filterLogs"
      @toggle-advanced-filter="toggleAdvancedFilter"
      @clear-all-filters="clearAllFilters"
      @toggle-level="toggleLevel"
    />

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
import { ref, onMounted } from 'vue';
import PaginationComponent from '../../components/common/data/PaginationComponent.vue';
import LogFilterPanel from './LogFilterPanel.vue';
import { useLogView } from './logView';

// 日期时间选择器的引用（由 LogFilterPanel 暴露的 DOM 元素同步填充）
const startDateTimeRef = ref<HTMLInputElement | null>(null);
const endDateTimeRef = ref<HTMLInputElement | null>(null);
const startContainerRef = ref<HTMLElement | null>(null);
const endContainerRef = ref<HTMLElement | null>(null);

// LogFilterPanel 组件实例引用
const filterPanelRef = ref<InstanceType<typeof LogFilterPanel> | null>(null);

// 子组件先于父组件挂载，故在其 onMounted 之前同步 DOM 引用，
// 供 useLogView composable 的 onMounted 绑定点击事件使用。
onMounted(() => {
  const panel = filterPanelRef.value;
  if (panel) {
    startDateTimeRef.value = panel.startInput;
    endDateTimeRef.value = panel.endInput;
    startContainerRef.value = panel.startContainer;
    endContainerRef.value = panel.endContainer;
  }
});

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
  LOGCategoryOptions,
  LOGModuleOptions,
  LOGMarkOptions,
  getAlgorithmLabel,
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
  algorithmOptions
} = useLogView({ startDateTimeRef, endDateTimeRef, startContainerRef, endContainerRef });
</script>

<style>
@import '../../assets/styles/main.css';
</style>

<style scoped>
@import './LogView.css';
</style>
