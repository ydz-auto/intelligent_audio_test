<!-- 
  purpose: View template for the Log View page.
  MVC role: View
-->
<template>
  <div class="log-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <i class="fas fa-file-alt"></i>
          日志查看
        </h2>
        <p class="page-description">查看系统操作日志、测试执行日志和错误日志</p>
      </div>
      <div class="header-right">
        <div class="header-actions">
          <button class="btn btn-text" @click="toggleRealTimeLog" :class="{ 'active': realTimeLogEnabled }">
            <i class="fas fa-sync-alt btn-icon" :class="{ 'fa-spin': realTimeLogEnabled }"></i>
            <span>{{ realTimeLogStatus  }}</span>
          </button>
          <button class="btn btn-text" @click="refreshLogs">
            <i class="fas fa-redo-alt btn-icon"></i>
            <span>刷新日志</span>
          </button>
          <button class="btn btn-text" @click="exportLogs">
            <i class="fas fa-download btn-icon"></i>
            <span>导出日志</span>
          </button>
          <button class="btn btn-text" @click="clearLogs">
            <i class="fas fa-trash-alt btn-icon"></i>
            <span>清除日志</span>
          </button>
          <!-- INT-743：归档面板迁移至系统设置「运维设置 → 日志维护」，此处保留直达入口 -->
          <button class="btn btn-text" @click="goArchive">
            <i class="fas fa-archive btn-icon"></i>
            <span>查看归档</span>
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
          <!-- INT-974：初始加载期间以占位符替代误导性的全 0 统计 -->
          <h3 class="stat-number">{{ isInitialLoading ? '—' : totalLogs }}</h3>
          <p class="stat-label">总日志条数</p>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon error-icon">
          <i class="fas fa-exclamation-circle"></i>
        </div>
        <div class="stat-content">
          <h3 class="stat-number">{{ isInitialLoading ? '—' : logStats.error }}</h3>
          <p class="stat-label">错误日志</p>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon warning-icon">
          <i class="fas fa-exclamation-triangle"></i>
        </div>
        <div class="stat-content">
          <h3 class="stat-number">{{ isInitialLoading ? '—' : logStats.warning }}</h3>
          <p class="stat-label">警告日志</p>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon info-icon">
          <i class="fas fa-info-circle"></i>
        </div>
        <div class="stat-content">
          <h3 class="stat-number">{{ isInitialLoading ? '—' : logStats.info }}</h3>
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
                <select class="form-input-sm" v-model="markColor">
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
            <!-- INT-974：加载 / 错误 / 空三态显式 UI（加载条对齐 INT-290 A/B 域方案，
                 错误口径对齐 INT-899：友好文案 + 重试按钮，原始 RPC 异常不直出） -->
            <div v-if="isInitialLoading" class="log-loading-bar">
              <span class="loading-spinner"></span>
              正在加载日志...
            </div>
            <div v-else-if="loadError && paginatedLogs.length === 0" class="log-error-banner">
              <i class="fas fa-exclamation-triangle"></i>
              <span class="log-error-text">{{ loadError }}</span>
              <button class="btn btn-primary btn-sm" @click="fetchLogs">
                <i class="fas fa-sync-alt"></i> 重试
              </button>
            </div>
            <div v-else-if="!isLoading && paginatedLogs.length === 0" class="log-empty-state">
              <i class="fas fa-inbox"></i>
              <p>暂无日志数据</p>
            </div>
            <div v-else class="table-container">
              <table class="data-table" data-manual-sort>
                <thead>
                  <tr>
                    <th class="checkbox-col">
                      <input type="checkbox" id="selectAllLogs" @change="selectAllLogs">
                    </th>
                    <th class="expand-header"></th>
                    <th class="sortable core-col" @click="sortLogs('time')">
                      时间
                      <i class="fas fa-sort sort-icon"></i>
                    </th>
                    <th class="sortable core-col" @click="sortLogs('level')">
                      级别
                      <i class="fas fa-sort sort-icon"></i>
                    </th>
                    <th class="sortable secondary-col" @click="sortLogs('module')">
                      模块
                      <i class="fas fa-sort sort-icon"></i>
                    </th>
                    <th class="secondary-col">
                      算法
                    </th>
                    <th class="sortable secondary-col" @click="sortLogs('source')">
                      来源
                      <i class="fas fa-sort sort-icon"></i>
                    </th>
                    <th class="core-col">内容</th>
                    <th class="core-col">操作</th>
                  </tr>
                </thead>
                <tbody id="logsTable">
                  <template v-for="log in paginatedLogs" :key="log.id">
                    <!-- 日志行 -->
                    <tr class="log-row" @click="toggleLogDetails(log.id)" :class="{ 'marked': log.mark, [`marked-${log.mark}`]: log.mark }">
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
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'
import "../../assets/styles/tasks/stats.css"
import "../../assets/styles/device/device.css"
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PaginationComponent from '../../components/common/data/PaginationComponent.vue';
import LogFilterPanel from './LogFilterPanel.vue';
import { useLogView } from './logView';

// 日期时间选择器的引用（由 LogFilterPanel 暴露的 DOM 元素同步填充）
const startDateTimeRef = ref<HTMLInputElement | null>(null);
const endDateTimeRef = ref<HTMLInputElement | null>(null);
const startContainerRef = ref<HTMLElement | null>(null);
const endContainerRef = ref<HTMLElement | null>(null);

const router = useRouter();

/** INT-743：归档面板迁至系统设置「运维设置 → 日志维护」 */
function goArchive() {
  router.push('/system-settings/operations/log-maintenance');
}

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
  isLoading,
  isInitialLoading,
  loadError,
  loadErrorDetail,
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
  fetchLogs,
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
