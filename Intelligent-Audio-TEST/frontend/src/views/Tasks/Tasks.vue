<template>
  <div class="tasks-view">
    <!-- 页面标题 -->
    <section class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-tasks"></i>
          测试任务记录
        </h2>
        <p class="page-description">管理和跟踪所有测试任务的进度和状态</p>
      </div>
      <!-- 已发布任务发布入口（已发布页签内，对齐原独立页头部） -->
      <div class="header-right" v-if="activeTab === 'published' && can(PermissionPoint.TASK_PUBLISH)">
        <button class="btn btn-primary" :disabled="published.actionLoading" @click="openPublishModal">
          <i class="fas fa-bookmark"></i> 发布任务
        </button>
      </div>
    </section>

    <!-- 内容区域：三栏布局 -->
    <div class="tasks-content-wrapper">
      <!-- 统计卡片和图表的三栏布局 -->
      <div class="stats-charts-row" v-if="!showComparisonReport">
        <!-- 统计卡片 -->
        <div class="stats-panel">
          <h3>统计信息</h3>

          <!-- 任务数量统计 -->
            <div class="stats-cards">
              <div class="stat-card">
                <div class="stat-value">{{ domainTotal }}</div>
                <div class="stat-label">总任务数</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ pendingTasks }}</div>
                <div class="stat-label">待处理</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ queuedTasks }}</div>
                <div class="stat-label">排队中</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ inProgressTasks }}</div>
                <div class="stat-label">进行中</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ completedTasks }}</div>
                <div class="stat-label">已完成</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ failedTasks }}</div>
                <div class="stat-label">执行失败</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ deletedTasks }}</div>
                <div class="stat-label">已删除</div>
              </div>
            </div>

          <!-- 任务标签云 -->
          <div class="tags-section">
            <h4>任务标签</h4>
            <div class="tags-cloud" id="tags-cloud">
              <span v-for="tag in currentTags" :key="tag" class="tag-item" @click="toggleTag(tag)">
                {{ tag }}
              </span>
            </div>
            <!-- 标签分页控件 -->
            <div class="tags-pagination" id="tags-pagination">
              <button class="tag-page-btn" :disabled="tagCurrentPage === 1" @click="tagCurrentPage--">
                <i class="fas fa-chevron-left"></i>
              </button>
              <span class="tag-page-info" id="tag-page-info">第 {{ tagCurrentPage }} 页，共 {{ totalTagPages }} 页</span>
              <button class="tag-page-btn" :disabled="tagCurrentPage === totalTagPages" @click="tagCurrentPage++">
                <i class="fas fa-chevron-right"></i>
              </button>
            </div>
          </div>
        </div>

        <!-- 任务统计图表区域 -->
        <section class="stats-charts-container">
          <!-- 任务类型分布 -->
          <div class="chart-card">
            <h3>任务类型分布</h3>
            <div class="chart-container">
              <canvas ref="taskTypeChartRef"></canvas>
            </div>
          </div>

          <!-- 任务完成趋势 -->
          <div class="chart-card">
            <div class="chart-header">
              <h3>任务完成趋势</h3>
              <div class="time-granularity-selector">
                <button class="time-btn" :class="{ active: isActive('day') }" @click="changeTimeGranularity('day')">日</button>
                <button class="time-btn" :class="{ active: isActive('week') }" @click="changeTimeGranularity('week')">周</button>
                <button class="time-btn" :class="{ active: isActive('month') }" @click="changeTimeGranularity('month')">月</button>
                <button class="time-btn" :class="{ active: isActive('year') }" @click="changeTimeGranularity('year')">年</button>
              </div>
            </div>
            <div class="chart-container">
              <canvas ref="taskTrendChartRef"></canvas>
            </div>
          </div>

          <!-- 任务状态分布 -->
          <div class="chart-card">
            <h3>任务状态分布</h3>
            <div class="chart-container">
              <canvas ref="taskStatusChartRef"></canvas>
            </div>
          </div>
        </section>
      </div>

      <!-- 页签（INT-298：日常 / 已发布 / 合并 / 收藏，对齐 V9.7.10 页签组织） -->
      <section class="tasks-container" v-if="!showComparisonReport">
        <div class="task-tabs">
          <button class="task-tab" :class="{ active: activeTab === 'daily' }" @click="switchTab('daily')">
            <i class="fas fa-tasks"></i> 日常任务
          </button>
          <button
            v-if="can(PermissionPoint.PUBLISHED_TASK_READ)"
            class="task-tab"
            :class="{ active: activeTab === 'published' }"
            @click="switchTab('published')"
          >
            <i class="fas fa-bookmark"></i> 已发布任务
            <span v-if="published.total > 0" class="task-tab-count">{{ published.total }}</span>
          </button>
          <button class="task-tab" :class="{ active: activeTab === 'merged' }" @click="switchTab('merged')">
            <i class="fas fa-object-group"></i> 合并任务
            <span v-if="mergedTasks.total > 0" class="task-tab-count">{{ mergedTasks.total }}</span>
          </button>
          <button class="task-tab" :class="{ active: activeTab === 'favorite' }" @click="switchTab('favorite')">
            <i class="fas fa-star"></i> 收藏
            <span v-if="favoriteIds.size > 0" class="task-tab-count">{{ favoriteIds.size }}</span>
          </button>
        </div>
      </section>

      <!-- 筛选和排序栏（日常 / 已发布 / 合并 / 收藏 四视图统一，对齐 V9.7.10 共享筛选栏） -->
      <section class="filter-sort-section" v-if="!showComparisonReport">
        <div class="filter-row">
          <input type="text" class="search-input" placeholder="搜索任务名称、标签..." v-model="currentFilter.search" @input="applyCurrentFilter">

          <!-- INT-148：任务类型筛选（已发布视图，服务端按发布冻结列过滤） -->
          <BadgeFilter
            v-if="activeTab === 'published'"
            :options="published.typeOptions"
            :model-value="currentFilter.type"
            all-label="全部类型"
            title="任务类型"
            @update:model-value="handleBadgeFilterChange('type', $event)"
          />

          <BadgeFilter
            :options="currentStatusOptions"
            :model-value="currentFilter.status"
            all-label="全部状态"
            title="执行状态"
            collapsible
            :collapsed-count="8"
            @update:model-value="handleBadgeFilterChange('status', $event)"
          />
        </div>

        <!-- INT-301：评估状态筛选（日常/收藏视图；与执行状态并列，复用 SQL 派生口径） -->
        <div class="filter-row" v-if="activeTab === 'daily' || activeTab === 'favorite'">
          <BadgeFilter
            :options="EVALUATION_FILTER_OPTIONS"
            :model-value="filters.evaluationStatus"
            all-label="全部评估"
            title="评估状态"
            @update:model-value="handleEvaluationBadgeChange"
          />
        </div>

        <div class="filter-row">
          <BadgeFilter
            :options="TIME_RANGE_OPTIONS"
            :model-value="currentFilter.timeRange"
            all-label="全部时间"
            title="时间范围"
            @update:model-value="handleBadgeFilterChange('timeRange', $event)"
          />

          <!-- 自定义时间范围 -->
          <div class="filter-item custom-time-range" v-if="currentFilter.timeRange === 'custom'">
            <div>
              <label for="start-date">开始:</label>
              <input type="date" id="task-start-date" class="date-input" v-model="currentFilter.customRange.start" @change="applyCurrentFilter">
            </div>
            <span>至</span>
            <div>
              <label for="end-date">结束:</label>
              <input type="date" id="task-end-date" class="date-input" v-model="currentFilter.customRange.end" @change="applyCurrentFilter">
            </div>
          </div>

          <div class="sort-options">
            <span>排序：</span>
            <div class="sort-item" :class="{ active: currentFilter.sort.field === sortFieldKey }" @click="toggleViewSort(sortFieldKey)">
              {{ sortFieldKey === 'publishedAt' ? '发布时间' : '创建时间' }} <i class="fas" :class="currentFilter.sort.field === sortFieldKey ? (currentFilter.sort.order === 'asc' ? 'fa-sort-up' : 'fa-sort-down') : 'fa-sort'"></i>
            </div>
            <div class="sort-item" :class="{ active: currentFilter.sort.field === 'status' }" @click="toggleViewSort('status')">
              状态 <i class="fas" :class="currentFilter.sort.field === 'status' ? (currentFilter.sort.order === 'asc' ? 'fa-sort-up' : 'fa-sort-down') : 'fa-sort'"></i>
            </div>
            <div class="sort-item" :class="{ active: currentFilter.sort.field === 'title' || currentFilter.sort.field === 'name' }" @click="toggleViewSort(activeTab === 'published' ? 'name' : 'title')">
              名称 <i class="fas" :class="(currentFilter.sort.field === 'title' || currentFilter.sort.field === 'name') ? (currentFilter.sort.order === 'asc' ? 'fa-sort-up' : 'fa-sort-down') : 'fa-sort'"></i>
            </div>
          </div>
        </div>

        <!-- 算法筛选（徽章单选） -->
        <div class="filter-row">
          <AlgorithmFilter
            :options="activeTab === 'daily' || activeTab === 'favorite' || activeTab === 'merged' ? algorithmOptions : undefined"
            :model-value="currentFilter.algorithmType"
            title="算法筛选"
            @update:model-value="handleAlgorithmBadgeChange"
          />
        </div>

        <!-- INT-215：收藏 / 回收站工具栏（日常视图专属；收藏视图承载于「收藏」页签，回收站不再作为状态徽章筛选项） -->
        <FavoriteTrashBar
          v-if="activeTab === 'daily'"
          :favorite-only="favoriteOnly"
          :trash-mode="taskTrashMode"
          :favorite-disabled="taskTrashMode"
          @update:favorite-only="handleTaskFavoriteFilterChange"
          @update:trash-mode="toggleTaskTrashMode"
        />
      </section>

      <!-- 任务列表（按页签分发） -->
      <section class="tasks-container" v-if="!showComparisonReport">
        <!-- 日常任务 / 收藏任务面板（共用日常任务列表与批量操作） -->
        <template v-if="activeTab === 'daily' || activeTab === 'favorite'">
        <!-- 批量操作栏 -->
        <div class="batch-actions" v-if="selectedTasks.size > 0">
          <button class="btn-danger" @click="batchDelete">
            <i class="fas fa-trash"></i> 批量删除
          </button>
          <button v-if="activeTab === 'daily' && can(PermissionPoint.TASK_PUBLISH)" class="btn-primary" @click="batchPublish" :disabled="published.actionLoading">
            <i class="fas fa-bookmark"></i> 发布
          </button>
          <button class="btn-primary" @click="batchCompare" :disabled="selectedTasks.size < 2">
            <i class="fas fa-exchange-alt"></i> 任务对比
          </button>
          <button class="btn-primary" @click="batchMerge" :disabled="!canMerge" :title="mergeButtonTitle">
            <i class="fas fa-object-ungroup"></i> 合并任务
          </button>
          <button class="btn-primary" @click="openDataExport">
            <i class="fas fa-file-export"></i> 导出数据
          </button>
          <button class="btn-primary" @click="batchRestore" :style="{ display: filters.status === 'deleted' ? 'inline-block' : 'none' }">
            <i class="fas fa-undo"></i> 批量恢复
          </button>
          <button class="btn-danger" @click="batchPurge" :style="{ display: filters.status === 'deleted' ? 'inline-block' : 'none' }">
            <i class="fas fa-fire"></i> 批量彻底删除
          </button>
          <button class="btn-secondary" @click="cancelSelect">
            <i class="fas fa-times"></i> 取消选择
          </button>
        </div>

        <!-- 任务列表头部 -->
        <div class="task-list-header">
          <h3 class="task-list-title">{{ activeTab === 'favorite' ? '收藏任务' : '任务列表' }}</h3>
          <div class="task-actions" v-if="activeTab === 'daily'">
            <button class="btn btn-primary" @click="createNewTask">
              <i class="fas fa-plus"></i> 创建新任务
            </button>
            <button class="btn btn-secondary" @click="openDataImport">
              <i class="fas fa-file-import"></i> 导入数据
            </button>
          </div>
          <label class="btn btn-secondary select-all-btn">
            <input
              type="checkbox"
              class="select-all-checkbox"
              :checked="isAllSelected"
              @change="toggleSelectAll"
              @click.stop
            >
            <span>全选</span>
          </label>
        </div>

        <!-- 任务列表容器 -->
        <div id="tasks-container">
          <TaskListWithPagination
            :tasks="filteredTasks.map(task => ({
              id: task.id,
              name: task.name,
              title: task.name,
              description: task.description,
              status: task.status,
              // INT-301：双状态徽章字段直通（执行状态 + 评估状态）
              executionStatus: task.executionStatus,
              evaluationStatus: task.evaluationStatus,
              createdAt: formatDate(task.createdAt),
              tags: task.tags,
              deviceCount: task.deviceCount,
              caseCount: task.caseCount,
              completedCases: task.completedCases,
              totalCases: task.totalCases,
              algorithmType: task.algorithmType,
              algorithmParams: task.algorithmParams,
              sourceTasks: task.sourceTasks,
              // INT-215：回收站字段（已删除徽章 + 删除人/删除时间展示）；INT-239：删除时间改由 TaskCard 卡内 formatDate，视图层直通
              deleted: task.deleted,
              deletedAt: task.deletedAt,
              deletedByUserId: task.deletedByUserId
            }))"
            :is-selected="(task: any) => selectedTasks.has(task.id)"
            :show-checkbox="true"
            :show-config="false"
            :current-page="currentPage"
            :page-size="pageSize"
            :total-items="totalTasks"
            :total-pages="totalPages"
            :actions="taskActions"
            :search-query="searchTerm"
            @toggle-selection="toggleTaskSelection"
            @action="handleTaskAction"
            @name-updated="handleNameUpdated"
            @page-change="handlePageChange"
            @page-size-change="handlePageSizeChange"
          />
        </div>
        </template>

        <!-- 已发布任务面板 -->
        <template v-else-if="activeTab === 'published'">
          <PublishedTaskPanel ref="publishedPanelRef" :pt="published" />
        </template>

        <!-- 合并任务面板 -->
        <template v-else-if="activeTab === 'merged'">
          <MergedTaskPanel
            :merged="mergedTasks"
            :task-actions="taskActions"
            @task-action="handleTaskAction"
            @name-updated="handleMergedNameUpdated"
          />
        </template>      </section>

      <!-- 任务对比报告区域 -->
      <TaskComparisonReport
        v-if="showComparisonReport"
        v-model:report-name="reportName"
        v-model:report-conclusion="reportConclusion"
        :report-service-data="reportServiceData"
        :report-devices="reportDevices"
        :is-editing-report="isEditingReport"
        :is-editing-conclusion="isEditingConclusion"
        :device-api-columns="deviceApiColumns"
        :device-api-comparison-data="deviceApiComparisonData"
        :case-execution-columns="caseExecutionColumns"
        :case-execution-data="caseExecutionData"
        @toggle-edit-report="toggleEditReport"
        @save-report="saveComparisonReport"
        @cancel-edit-report="cancelEditReport"
        @toggle-device="toggleDeviceSelection"
        @toggle-edit-conclusion="toggleEditConclusion"
        @save-conclusion="saveConclusion"
        @cancel-edit-conclusion="cancelEditConclusion"
        @publish-report="publishComparisonReport"
        @close="closeComparisonReport"
      />
    </div>

    <!-- 任务类型选择弹窗 -->
    <TaskTypeModal
      v-if="isTaskTypeModalVisible"
      modalId="task-type-modal"
      @close="isTaskTypeModalVisible = false"
      @confirm="handleCreateTask"
    />

    <!-- 任务数据导出弹窗（INT-25） -->
    <TaskDataExportDialog
      v-if="isDataExportDialogVisible"
      :tasks="selectedTasksForExport"
      @close="isDataExportDialogVisible = false"
    />

    <!-- 任务数据导入弹窗（INT-25） -->
    <TaskDataImportDialog
      v-if="isDataImportDialogVisible"
      @close="isDataImportDialogVisible = false"
      @imported="handleDataImported"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useTasks } from './tasks';
import { TaskStatus, TaskEvaluationStatus, FINISHED_STATUSES, PermissionPoint } from '@/domain/enums';
import { useAuthStore } from '../../store/authStore';
import { usePublishedTasks } from '../../composables/publishedTask/usePublishedTasks';
import { useMergedTasks } from '../../composables/task/useMergedTasks';
import { useModalControl, MODAL_TYPES } from '../../composables/modal/useModal';
import { useNotification } from '../../composables/modal/useNotification';
import TaskListWithPagination from '../../components/task/TaskListWithPagination.vue';
import TaskComparisonReport from './TaskComparisonReport.vue';
import TaskTypeModal from '../../components/common/modal/TaskTypeModal.vue';
import TaskDataExportDialog from '../../components/task/TaskDataExportDialog.vue';
import TaskDataImportDialog from '../../components/task/TaskDataImportDialog.vue';
import PublishedTaskPanel from './PublishedTaskPanel.vue';
import MergedTaskPanel from './MergedTaskPanel.vue';
import BadgeFilter from '../../components/common/BadgeFilter.vue';
import FavoriteTrashBar from '../../components/common/FavoriteTrashBar.vue';
import AlgorithmFilter from '../../components/algorithm/AlgorithmFilter.vue';

const route = useRoute();
const router = useRouter();
const { hasPermission: can } = useAuthStore();
const notification = useNotification();
const modalControl = useModalControl();

// ===== 页签（INT-298：日常 / 已发布 / 合并 / 收藏，对齐 V9.7.10 页签组织）=====
type TaskTab = 'daily' | 'published' | 'merged' | 'favorite';
const TAB_QUERY_VALUES: TaskTab[] = ['daily', 'published', 'merged', 'favorite'];
const activeTab = ref<TaskTab>('daily');
const published = usePublishedTasks();
const mergedTasks = useMergedTasks();
const publishedPanelRef = ref<InstanceType<typeof PublishedTaskPanel> | null>(null);

/** 页签切换：选中集清空 + URL query 同步（/tasks?tab=published 兼容旧链接）。
 *  已发布/合并面板随 v-else-if 挂载自拉列表（面板 onMounted 承担首次刷新） */
function switchTab(tab: TaskTab) {
  if (activeTab.value === tab) return;
  activeTab.value = tab;
  selectedTasks.value.clear();
  router.replace({ query: { ...route.query, tab: tab === 'daily' ? undefined : tab } });
}

// ===== 收藏视图（INT-298：与 C 域收藏语义一致，favorite=true 过滤任务）=====
// INT-320：进出逻辑迁协调层 tasks.ts（loadFavoriteView 含回收站态入口清空，
// leaveFavoriteView 对称还原），本组件经 useTasks 解构调用
// ===== 筛选选项（组件级 UI 常量，对齐 V9.7.10 徽章筛选行）=====
// INT-215：「已删除（回收站）」自状态徽章移除——回收站入口统一为工具栏按钮（toggleTaskTrashMode）
// INT-301：原「任务状态」行更名「执行状态」——评估过渡（evaluating/reevaluate_*）
// 改由下方评估状态筛选行承载（后端按任务级评估状态过滤，与徽章口径一致）；
// 原 status 值继续有效（历史入口/收藏的旧筛选值不受影响）。
const STATUS_FILTER_OPTIONS = [
  { value: TaskStatus.PENDING, label: '待执行' },
  { value: TaskStatus.QUEUED, label: '排队中' },
  { value: TaskStatus.RUNNING, label: '执行中' },
  { value: TaskStatus.EVALUATING, label: '评估中' },
  { value: TaskStatus.REEVALUATE_QUEUED, label: '重新评估排队中' },
  { value: TaskStatus.REEVALUATING, label: '重新评估中' },
  { value: TaskStatus.COMPLETED, label: '已完成' },
  { value: TaskStatus.FAILED, label: '执行失败' },
  { value: TaskStatus.MERGED, label: '已合并' },
];

/** INT-298：合并视图状态选项（对齐 V9.7.10 MERGED_STATUS_OPTIONS） */
const MERGED_STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: TaskStatus.COMPLETED, label: '已完成' },
  { value: TaskStatus.MERGED, label: '已合并' },
];

/** INT-301：评估状态筛选（与执行状态并列；值 = 任务级评估状态原值） */
const EVALUATION_FILTER_OPTIONS = [
  { value: TaskEvaluationStatus.PENDING, label: '待评估' },
  { value: TaskEvaluationStatus.EVALUATING, label: '评估中' },
  { value: TaskEvaluationStatus.COMPLETED, label: '已评估完成' },
  { value: TaskEvaluationStatus.FAILED, label: '评估失败' },
  { value: TaskEvaluationStatus.SKIPPED, label: '评估跳过' },
];

const TIME_RANGE_OPTIONS = [
  { value: 'all', label: '全部时间' },
  { value: 'today', label: '今日' },
  { value: 'yesterday', label: '昨日' },
  { value: 'week', label: '近7天' },
  { value: 'month', label: '近30天' },
  { value: 'custom', label: '自定义' },
];

const {
  tasks,
  filteredTasks, selectedTasks, sortConfig,
  currentPage, pageSize, totalPages,
  searchTerm, filters, customDateRange, tagCurrentPage, tagPageSize,
  showComparisonReport, isEditingConclusion,
  totalTagPages, currentTags, totalTasks, domainTotal, pendingTasks, queuedTasks,
  inProgressTasks, completedTasks, failedTasks, deletedTasks,
  isAllSelected, formatDate, applyFilters, handleSearch, toggleSort,
  toggleTag, toggleTaskSelection, toggleSelectAll, cancelSelect, createNewTask, handleCreateTask,
  handleTaskAction, updateTaskName, batchDelete,
  batchCompare, batchMerge, batchRestore, closeComparisonReport, saveComparisonReport,
  publishComparisonReport, saveConclusion, toggleEditConclusion, reevaluateTask,
  cancelEditConclusion, toggleEditReport, cancelEditReport,
  deviceApiColumns, caseExecutionColumns,
  toggleDeviceSelection, fetchTasks,
  isEditingReport,
  reportConclusion,
  handlePageChange,
  handlePageSizeChange,
  reportServiceData,
  reportName,
  reportDevices,
  deviceApiComparisonData,
  caseExecutionData,
  isTaskTypeModalVisible,
  currentTask,
  isControlling,
  changeTimeGranularity,
  isActive,
  createTaskTypeChart, createTaskTrendChart, createTaskStatusChart,
  updateCharts,
  // 图表refs
  taskTypeChartRef,
  taskTrendChartRef,
  taskStatusChartRef,
  // 日志相关
  taskLogs, filteredTaskLogs, taskLogSearchTerm, taskLogLevelFilter, taskLogFilter,
  refreshTaskLogs, filterTaskLogs,
  // 算法选项
  algorithmOptions,
  // 协调逻辑
  handleNameUpdated,
  canMerge,
  mergeButtonTitle,
  // 任务数据导入导出（INT-25）
  isDataExportDialogVisible,
  isDataImportDialogVisible,
  openDataExport,
  openDataImport,
  selectedTasksForExport,
  handleDataImported,
  // 收藏 / 回收站（INT-141）
  favoriteOnly,
  isFavorite,
  favoriteIds,
  batchPurge,
  // INT-215：回收站工具栏（对齐报告/用例交互口径）
  taskTrashMode,
  toggleTaskTrashMode,
  handleTaskFavoriteFilterChange,
  // INT-320：收藏页签进出（协调层承载，含回收站态入口清空）
  loadFavoriteView,
  leaveFavoriteView
} = useTasks();

// ========== 四视图统一筛选排序（日常 / 已发布 / 合并 / 收藏，对齐 V9.7.10）==========

/**
 * 任务操作定义（INT-298：日常列表卡片与合并任务卡片/源任务行共用，保证行为一致）。
 * INT-215：收藏星标按收藏态动态生成 fas/far + 着色（对齐报告/用例行内星标口径）；
 * 恢复/彻底删除仅在回收站态（filters.status==='deleted'）可见。
 */
const taskActions = [
  { id: 'view-details', label: '查看详情', icon: 'fa-eye', type: 'secondary' },
  { id: 'view-report', label: '查看报告', icon: 'fa-file-alt', type: 'primary' },
  { id: 'favorite', label: '收藏', type: 'secondary', show: (task: any) => !isFavorite(task.id) && filters.value.status !== 'deleted', iconClass: (task: any) => isFavorite(task.id) ? 'fas fa-star' : 'far fa-star', iconStyle: (task: any) => isFavorite(task.id) ? 'color: var(--favorite-star)' : '' },
  { id: 'unfavorite', label: '取消收藏', type: 'secondary', show: (task: any) => isFavorite(task.id) && filters.value.status !== 'deleted', iconClass: (task: any) => isFavorite(task.id) ? 'fas fa-star' : 'far fa-star', iconStyle: (task: any) => isFavorite(task.id) ? 'color: var(--favorite-star)' : '' },
  { id: 'regenerate-report', label: '重新生成报告', icon: 'fa-sync', type: 'warning', show: (task: any) => [...FINISHED_STATUSES].includes(task.status), disabled: (task: any) => isControlling.value.has(task.id) },
  { id: 'pause', label: '暂停', icon: 'fa-pause', type: 'secondary', show: (task: any) => task.status === TaskStatus.RUNNING, disabled: (task: any) => isControlling.value.has(task.id) },
  { id: 'resume', label: '继续', icon: 'fa-play', type: 'secondary', show: (task: any) => [TaskStatus.PAUSED, TaskStatus.STOPPED].includes(task.status), disabled: (task: any) => isControlling.value.has(task.id) },
  { id: 'stop', label: '停止', icon: 'fa-stop', type: 'danger', show: (task: any) => [TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.QUEUED].includes(task.status), disabled: (task: any) => isControlling.value.has(task.id) },
  { id: 'retry', label: '重新执行', icon: 'fa-redo', type: 'success', show: (task: any) => [TaskStatus.PENDING, TaskStatus.FAILED, TaskStatus.COMPLETED, TaskStatus.STOPPED].includes(task.status), disabled: (task: any) => isControlling.value.has(task.id) },
  { id: 'reevaluate', label: '重新评估', icon: 'fa-sync-alt', type: 'info', show: (task: any) => [...FINISHED_STATUSES].includes(task.status), disabled: (task: any) => isControlling.value.has(task.id) },
  { id: 'restore', label: '恢复', icon: 'fa-undo', type: 'success', show: (task: any) => filters.value.status === 'deleted' },
  { id: 'purge', label: '彻底删除', icon: 'fa-fire', type: 'danger', show: (task: any) => filters.value.status === 'deleted' },
  { id: 'delete', label: '删除', icon: 'fa-trash', type: 'danger', disabled: (task: any) => isControlling.value.has(task.id) },
];

/** 各视图筛选状态适配为统一结构（search/type/algorithmType/status/timeRange/customRange/sort），
 *  使顶部筛选排序栏在四视图间可复用同一套控件 */
const dailyFilterState = reactive({
  get search() { return searchTerm.value; },
  set search(v: string) { searchTerm.value = v; },
  type: 'all',
  get algorithmType() { return filters.value.algorithmType || 'all'; },
  set algorithmType(v: string) { filters.value.algorithmType = v === 'all' ? '' : v; },
  get status() { return filters.value.status; },
  set status(v: string) { filters.value.status = v === 'all' ? '' : v; },
  get timeRange() { return filters.value.timeRange; },
  set timeRange(v: string) { filters.value.timeRange = v; },
  get customRange() { return customDateRange.value; },
  set customRange(v: { start: string; end: string }) { customDateRange.value = v; },
  get sort() { return sortConfig.value; },
  set sort(v: { field: string; order: string }) { sortConfig.value = v; },
});

const publishedFilterState = reactive({
  get search() { return published.filters.keyword; },
  set search(v: string) { published.filters.keyword = v; },
  get type() { return published.filters.type; },
  set type(v: string) { published.filters.type = v; },
  get algorithmType() { return published.filters.algorithmType; },
  set algorithmType(v: string) { published.filters.algorithmType = v; },
  get status() { return published.filters.status; },
  set status(v: string) { published.filters.status = v; },
  get timeRange() { return published.filters.timeRange; },
  set timeRange(v: string) { published.filters.timeRange = v; },
  get customRange() { return published.filters.customRange; },
  set customRange(v: { start: string; end: string }) { published.filters.customRange = v; },
  get sort() { return published.filters.sort; },
  set sort(v: { field: string; order: 'asc' | 'desc' }) { published.filters.sort = v; },
});

const mergedFilterState = reactive({
  get search() { return mergedTasks.filters.search; },
  set search(v: string) { mergedTasks.filters.search = v; },
  type: 'merged',
  get algorithmType() { return mergedTasks.filters.algorithmType; },
  set algorithmType(v: string) { mergedTasks.filters.algorithmType = v; },
  get status() { return mergedTasks.filters.status; },
  set status(v: string) { mergedTasks.filters.status = v; },
  get timeRange() { return mergedTasks.filters.timeRange; },
  set timeRange(v: string) { mergedTasks.filters.timeRange = v; },
  get customRange() { return mergedTasks.filters.customRange; },
  set customRange(v: { start: string; end: string }) { mergedTasks.filters.customRange = v; },
  get sort() { return mergedTasks.filters.sort; },
  set sort(v: { field: string; order: 'asc' | 'desc' }) { mergedTasks.filters.sort = v; },
});

/** 当前视图的筛选状态（筛选排序栏统一绑定；收藏视图与日常视图共用日常列表数据源） */
const currentFilter = computed(() => {
  if (activeTab.value === 'published') return publishedFilterState;
  if (activeTab.value === 'merged') return mergedFilterState;
  return dailyFilterState;
});

/** 当前视图的状态选项 */
const currentStatusOptions = computed(() => {
  if (activeTab.value === 'published') return published.statusOptions;
  if (activeTab.value === 'merged') return MERGED_STATUS_OPTIONS;
  return STATUS_FILTER_OPTIONS;
});

/** 当前视图的创建时间排序字段（发布任务用 publishedAt） */
const sortFieldKey = computed(() => (activeTab.value === 'published' ? 'publishedAt' : 'createdAt'));

/** 筛选变更：按当前视图触发对应列表拉取 */
function applyCurrentFilter() {
  if (activeTab.value === 'published') {
    published.page = 1;
    published.fetchList();
  } else if (activeTab.value === 'merged') {
    mergedTasks.apply();
  } else {
    applyFilters();
  }
}

/** 算法徽章筛选变更（单选） */
function handleAlgorithmBadgeChange(value: string | number) {
  currentFilter.value.algorithmType = String(value);
  applyCurrentFilter();
}

/** 徽章筛选变更（单选）：写入当前视图对应筛选字段并刷新 */
function handleBadgeFilterChange(key: 'type' | 'status' | 'timeRange', value: string | number) {
  currentFilter.value[key] = String(value);
  applyCurrentFilter();
}

/** INT-301：评估状态徽章筛选（日常/收藏视图，与执行状态并列） */
function handleEvaluationBadgeChange(value: string | number) {
  filters.value.evaluationStatus = String(value);
  applyFilters();
}

/** 排序变更：按当前视图触发对应排序 */
function toggleViewSort(field: string) {
  if (activeTab.value === 'published') {
    published.toggleSort(field);
  } else if (activeTab.value === 'merged') {
    mergedTasks.toggleSort(field);
  } else {
    toggleSort(field);
  }
}

// ========== 日常任务批量发布（对齐 V9.7.10 batchPublish；发布弹窗/批量发布双入口）==========

/** 可发布状态（对齐后端 PUBLISHABLE_STATUSES） */
const PUBLISHABLE_STATUSES = ['completed', 'failed', 'stopped', 'pending'];

/** 勾选批量发布：名称沿用源任务名，不可发布状态自动跳过（对齐 V9.7.10） */
async function batchPublish() {
  const selected = tasks.value.filter((t: any) => selectedTasks.value.has(t.id));
  if (selected.length === 0) return;
  let confirmed = false;
  try {
    confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '批量发布',
      content: `将为选中的 ${selected.length} 个任务发布（名称沿用源任务名，不可发布状态自动跳过）。是否继续？`,
      confirmText: '发布',
      cancelText: '取消',
    });
  } catch {
    return; // 用户取消
  }
  if (!confirmed) return;

  let successCount = 0;
  const failedNames: string[] = [];
  for (const task of selected) {
    try {
      await published.publish(Number(task.id), task.name || `任务${task.id}`, task.description);
      successCount += 1;
    } catch (error: any) {
      failedNames.push(task.name || `#${task.id}`);
    }
  }
  if (successCount > 0) {
    notification.success(`批量发布完成：成功 ${successCount} 个${failedNames.length ? `，失败 ${failedNames.length} 个` : ''}`);
    await published.fetchList();
  } else {
    notification.error('批量发布失败，请确认任务状态是否可发布');
  }
  if (failedNames.length > 0) {
    console.warn('批量发布失败的任务:', failedNames);
  }
}

/** 发布弹窗入口（已发布页签头部按钮；面板 expose 同一能力） */
function openPublishModal() {
  publishedPanelRef.value?.openPublishModal();
}

// ========== 合并任务：卡片/源行操作分发与重命名（对齐 V9.7.10 交互） ==========

/** 合并任务重命名（复用日常任务重命名接口，对齐 V9.7.10） */
async function handleMergedNameUpdated({ taskId, newName }: { taskId: string | number; newName: string }) {
  try {
    await updateTaskName(taskId, newName);
    mergedTasks.refresh();
  } catch (error: any) {
    notification.error(error?.message || '更新任务名称失败');
  }
}

// 监听图表容器ref变化，初始化图表
watch([taskTypeChartRef, taskTrendChartRef, taskStatusChartRef], () => {
  if (taskTypeChartRef.value && taskTrendChartRef.value && taskStatusChartRef.value) {
    updateCharts();
  }
}, { deep: true });

// INT-298：旧链接 /tasks?tab=published|merged|favorite 直达对应页签（无权限回落日常）
onMounted(() => {
  const tabParam = String(route.query.tab ?? '');
  if ((TAB_QUERY_VALUES as string[]).includes(tabParam)) {
    const target = tabParam as TaskTab;
    if (target !== 'published' || can(PermissionPoint.PUBLISHED_TASK_READ)) {
      activeTab.value = target;
    }
  }
});

// INT-298：收藏视图进出联动 favoriteOnly（发布/合并页签数据拉取在 switchTab 内完成）
watch(activeTab, (tab, prev) => {
  if (tab === 'favorite' && prev !== 'favorite') {
    loadFavoriteView();
  } else if (prev === 'favorite' && tab !== 'favorite') {
    leaveFavoriteView();
  }
});
</script>

<style scoped>@import './Tasks.css';

/* ===== 页签（INT-298，对齐 V9.7.10 task-tabs）===== */
.task-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--color-slate-200, #e2e8f0);
  padding-bottom: 12px;
}

.task-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border: 1px solid var(--color-slate-200, #e2e8f0);
  border-radius: 8px 8px 0 0;
  background: var(--color-slate-50, #f8fafc);
  color: var(--color-slate-500, #64748b);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  border-bottom: none;
}

.task-tab:hover {
  background: var(--color-slate-100, #f1f5f9);
  color: var(--color-slate-700, #334155);
}

.task-tab.active {
  background: var(--background-primary, #fff);
  color: var(--primary, #FF6A00);
  border-color: var(--primary, #FF6A00);
  box-shadow: 0 -2px 0 0 var(--primary, #FF6A00) inset;
  font-weight: 600;
}

.task-tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border-radius: 9px;
  background: var(--primary, #ff6a00);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.chart-card{
    transition: all 0.3s ease;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    background: var(--background-primary);
    border-radius: var(--border-radius-lg);
    border: 1px solid var(--border-color);
    padding: var(--spacing-lg);
    margin-bottom: var(--spacing-xl);
    box-shadow: 0 1px 3px color-mix(in srgb, var(--color-black) 5%, transparent);
}

.chart-card:hover{
    transform: translateY(-5px);
    box-shadow: 0 8px 24px color-mix(in srgb, var(--color-black) 12%, transparent);
}

.chart-card h3{
    margin-bottom: 20px;
    font-size: 18px;
    font-weight: 600;
    color: var(--foreground);
}

.stats-panel{
    background: white;
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 2px 12px color-mix(in srgb, var(--color-black) 8%, transparent);
}

.stats-panel h3{
    margin-bottom: 20px;
    font-size: 18px;
    font-weight: 600;
    color: var(--foreground);
}

.tags-section{
    margin-top: 24px;
}

.tags-section h4{
    margin-bottom: 16px;
    font-size: 16px;
    font-weight: 600;
    color: var(--foreground);
}

.tags-cloud{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 16px;
    min-height: 40px;
}
/* stats-charts-container - 自全局样式就近迁移 */
.stats-charts-container{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 24px;
    margin-bottom: 24px;
}

@media (max-width: 1024px){
.stats-charts-container {
        grid-template-columns: repeat(2, 1fr);
}
}

@media (max-width: 767px){
.stats-charts-container {
        grid-template-columns: 1fr;
}
}
/* stats-charts-row - 自全局样式就近迁移 */
.stats-charts-row{
    display: grid;
    grid-template-columns: 1fr;
    gap: 24px;
    margin-bottom: 24px;
    align-items: start;
}

/* stats-cards - 自全局样式就近迁移 */
.stats-cards{
display: grid;
grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
gap: 16px;
margin-bottom: 24px;
align-items: center;
}

@media (max-width: 1279px){
.stats-cards {
        grid-template-columns: repeat(3, 1fr);
}
}

@media (max-width: 1023px){
.stats-cards {
        grid-template-columns: repeat(2, 1fr);
}
}

@media (max-width: 767px){
.stats-cards {
        grid-template-columns: 1fr;
}
}
/* tags-pagination - 自全局样式就近迁移 */
.tags-pagination{
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 12px;
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid var(--gray-light);
}

/* time-granularity-selector - 自全局样式就近迁移 */


/* tasks-container - 自全局样式就近迁移 */
.tasks-container{
    overflow: visible ;
    padding: 0 ;
}

/* task-list-header - 自全局样式就近迁移 */
.task-list-header{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    gap: 16px;
}

</style>
