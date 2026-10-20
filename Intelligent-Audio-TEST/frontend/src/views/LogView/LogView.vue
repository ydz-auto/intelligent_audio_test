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
      @update:searchTerm="searchTerm = $event"
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
    <div class="monitor-indicator" v-show="showMonitorIndicator"
         title="任务维度轮询在空闲时按指数退避（VITE_LOG_POLL_IDLE_MAX_MS 可配）；列表/统计共享短 TTL 扫描缓存，新日志展示可能有至多一个 TTL 窗口的时延">
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
    <div class="stats-grid"
         title="统计与列表共享短 TTL 扫描缓存（LOG_BUSINESS_SCAN_CACHE_TTL_SECONDS，默认 3 秒，0 关闭），展示可能存在至多一个 TTL 窗口的时延">
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

    <!-- 日志归档管理面板（INT-548：对接后端 5 个归档端点） -->
    <LogArchivePanel />

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
              <!-- INT-288 加载态：首屏/无数据拉取期间显示 spinner（非裸文本行） -->
              <div v-if="isLoading && paginatedLogs.length === 0" class="lv-loading-state">
                <div class="lv-loading-spinner"></div>
                <p>正在加载日志...</p>
              </div>
              <!-- INT-288 错误态：无数据且拉取失败 → 错误条 + 重试（区别于空态） -->
              <LoadErrorState v-else-if="error && paginatedLogs.length === 0" :message="error" @retry="fetchLogs" />
              <!-- INT-288 空态：无日志时给出「暂无日志」占位（不再空白表格） -->
              <div v-else-if="paginatedLogs.length === 0" class="lv-empty-state">
                <i class="fas fa-file-alt"></i>
                <p>暂无日志</p>
                <p class="lv-empty-hint">当前筛选条件下没有匹配的日志</p>
              </div>
              <!-- 有数据：错误时错误条悬于表格上方，旧数据保留不清空 -->
              <template v-else>
                <LoadErrorState v-if="error" :message="error" @retry="fetchLogs" />
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
              </template>
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
import LogArchivePanel from './LogArchivePanel.vue';
import LoadErrorState from '../../components/common/misc/LoadErrorState.vue';
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
  // INT-288：加载态 / 错误态（模板消费三态：加载 spinner / 错误条 + 重试 / 空态）
  isLoading,
  error,
  fetchLogs,
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
  sortLogs,
  removeLevel,
  toggleLevel,
  algorithmOptions
} = useLogView({ startDateTimeRef, endDateTimeRef, startContainerRef, endContainerRef });
</script>

<style scoped>
@import './LogView.css';

/* ===== INT-288：日志列表加载 / 空态（lv- 前缀命名空间，对齐 tr-/rv- 方案避免全局泄漏） ===== */
.lv-loading-state,
.lv-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 30vh;
  text-align: center;
  color: var(--text-tertiary, #9ca3af);
  padding: 40px 16px;
}

.lv-loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--color-slate-200, #e2e8f0);
  border-top-color: var(--secondary, #ff6a00);
  border-radius: 50%;
  animation: lv-spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes lv-spin {
  to { transform: rotate(360deg); }
}

.lv-loading-state p,
.lv-empty-state p {
  margin: 8px 0 0;
}

.lv-empty-state i {
  font-size: 32px;
  margin-bottom: 8px;
  color: var(--text-disabled, #d1d5db);
}

.lv-empty-hint {
  font-size: 12px;
  color: var(--text-tertiary, #9ca3af);
}


/* sort-icon - 自全局样式就近迁移 */
.sort-icon {
    margin-left: 5px;
    font-size: 12px;
    color: var(--color-gray-400);
}

.sortable:hover .sort-icon {
    color: var(--color-blue-500);
}

.sort-icon {
    margin-left: var(--spacing-xs);
    font-size: var(--font-size-sm);
    color: var(--text-light);
    transition: all var(--transition-normal);
}

.sortable:hover .sort-icon {
    color: var(--primary-color);
}
/* log-checkbox - 自全局样式就近迁移 */
.log-checkbox {
    width: 20px;
    height: 20px;
    cursor: pointer;
}

/* log-module - 自全局样式就近迁移 */
.log-module {
    font-weight: var(--font-weight-medium);
    color: var(--text-primary);
}

/* monitor-indicator - 自全局样式就近迁移 */
.monitor-indicator {
    margin-bottom: var(--spacing-xl);
    padding: var(--spacing-md);
    background-color: var(--background-secondary);
    border-radius: var(--border-radius-lg);
    box-shadow: var(--shadow-sm);
    display: flex;
    align-items: center;
    justify-content: space-between;
    transition: all var(--transition-normal);
}

/* monitor-status - 自全局样式就近迁移 */
.monitor-status {
    display: flex;
    align-items: center;
    gap: var(--spacing-md);
}

/* monitor-icon - 自全局样式就近迁移 */
.monitor-icon {
    font-size: var(--font-size-xs);
    color: var(--success-color);
    animation: pulse 2s infinite;
}

/* error-icon - 自全局样式就近迁移 */
.error-icon {
    font-size: 48px;
    color: var(--danger-color);
    margin-bottom: var(--spacing-md);
}

/* warning-icon - 自全局样式就近迁移 */
.warning-icon {
    font-size: 48px;
    color: var(--warning-color);
    margin-bottom: var(--spacing-md);
}

</style>
