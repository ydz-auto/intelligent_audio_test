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

      <!-- 筛选和排序栏（对齐 V9.7.10：徽章筛选行） -->
      <section class="filter-sort-section" v-if="!showComparisonReport">
        <div class="filter-row">
          <input type="text" class="search-input" placeholder="搜索任务名称、标签..." v-model="searchTerm" @input="handleSearch">

          <BadgeFilter
            :options="STATUS_FILTER_OPTIONS"
            :model-value="filters.status"
            all-label="全部状态"
            title="执行状态"
            collapsible
            :collapsed-count="8"
            @update:model-value="handleStatusBadgeChange"
          />
        </div>

        <!-- INT-301：评估状态筛选（与执行状态并列；复用 SQL 派生口径，展示与筛选一致） -->
        <div class="filter-row">
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
            :model-value="filters.timeRange"
            all-label="全部时间"
            title="时间范围"
            @update:model-value="handleTimeRangeBadgeChange"
          />

          <!-- 自定义时间范围 -->
          <div class="filter-item custom-time-range" v-if="filters.timeRange === 'custom'">
            <div>
              <label for="start-date">开始:</label>
              <input type="date" id="task-start-date" class="date-input" v-model="customDateRange.start" @change="applyFilters">
            </div>
            <span>至</span>
            <div>
              <label for="end-date">结束:</label>
              <input type="date" id="task-end-date" class="date-input" v-model="customDateRange.end" @change="applyFilters">
            </div>
          </div>

          <div class="sort-options">
            <span>排序：</span>
            <div class="sort-item" :class="{ active: sortConfig.field === 'createdAt' }" @click="toggleSort('createdAt')">
              创建时间 <i class="fas" :class="sortConfig.field === 'createdAt' ? (sortConfig.order === 'asc' ? 'fa-sort-up' : 'fa-sort-down') : 'fa-sort'"></i>
            </div>
            <div class="sort-item" :class="{ active: sortConfig.field === 'status' }" @click="toggleSort('status')">
              状态 <i class="fas" :class="sortConfig.field === 'status' ? (sortConfig.order === 'asc' ? 'fa-sort-up' : 'fa-sort-down') : 'fa-sort'"></i>
            </div>
            <div class="sort-item" :class="{ active: sortConfig.field === 'title' }" @click="toggleSort('title')">
              名称 <i class="fas" :class="sortConfig.field === 'title' ? (sortConfig.order === 'asc' ? 'fa-sort-up' : 'fa-sort-down') : 'fa-sort'"></i>
            </div>
          </div>
        </div>

        <!-- 算法筛选（徽章单选） -->
        <div class="filter-row">
          <AlgorithmFilter
            :options="algorithmOptions"
            :model-value="filters.algorithmType"
            title="算法筛选"
            @update:model-value="handleAlgorithmBadgeChange"
          />
        </div>
        <!-- INT-215：收藏 / 回收站工具栏（对齐报告/用例交互口径；回收站不再作为状态徽章筛选项） -->
        <FavoriteTrashBar
          :favorite-only="favoriteOnly"
          :trash-mode="taskTrashMode"
          :favorite-disabled="taskTrashMode"
          @update:favorite-only="handleTaskFavoriteFilterChange"
          @update:trash-mode="toggleTaskTrashMode"
        />
      </section>

      <!-- 任务列表 -->
      <section class="tasks-container" v-if="!showComparisonReport">
        <!-- 批量操作栏 -->
        <div class="batch-actions" v-if="selectedTasks.size > 0">
          <button class="btn-danger" @click="batchDelete">
            <i class="fas fa-trash"></i> 批量删除
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
          <h3 class="task-list-title">任务列表</h3>
          <div class="task-actions">
            <button class="btn btn-primary" @click="createNewTask">
              <i class="fas fa-plus"></i> 创建新任务
            </button>
            <button class="btn btn-secondary" @click="openDataImport">
              <i class="fas fa-file-import"></i> 导入数据
            </button>
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
            :actions="[
              { id: 'view-details', label: '查看详情', icon: 'fa-eye', type: 'secondary' },
              { id: 'view-report', label: '查看报告', icon: 'fa-file-alt', type: 'primary' },
              // INT-215：收藏星标按收藏态动态生成 fas/far + 着色（对齐报告/用例行内星标口径）
              { id: 'favorite', label: '收藏', type: 'secondary', show: (task: any) => !isFavorite(task.id) && filters.status !== 'deleted', iconClass: (task: any) => isFavorite(task.id) ? 'fas fa-star' : 'far fa-star', iconStyle: (task: any) => isFavorite(task.id) ? 'color: var(--favorite-star)' : '' },
              { id: 'unfavorite', label: '取消收藏', type: 'secondary', show: (task: any) => isFavorite(task.id) && filters.status !== 'deleted', iconClass: (task: any) => isFavorite(task.id) ? 'fas fa-star' : 'far fa-star', iconStyle: (task: any) => isFavorite(task.id) ? 'color: var(--favorite-star)' : '' },
              { id: 'regenerate-report', label: '重新生成报告', icon: 'fa-sync', type: 'warning', show: (task: any) => [...FINISHED_STATUSES].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
              { id: 'pause', label: '暂停', icon: 'fa-pause', type: 'secondary', show: (task: any) => task.status === TaskStatus.RUNNING, disabled: (task: any) => isControlling.has(task.id) },
              { id: 'resume', label: '继续', icon: 'fa-play', type: 'secondary', show: (task: any) => [TaskStatus.PAUSED, TaskStatus.STOPPED].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
              { id: 'stop', label: '停止', icon: 'fa-stop', type: 'danger', show: (task: any) => [TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.QUEUED].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
              { id: 'retry', label: '重新执行', icon: 'fa-redo', type: 'success', show: (task: any) => [TaskStatus.PENDING, TaskStatus.FAILED, TaskStatus.COMPLETED, TaskStatus.STOPPED].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
              { id: 'reevaluate', label: '重新评估', icon: 'fa-sync-alt', type: 'info', show: (task: any) => [...FINISHED_STATUSES].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
              { id: 'restore', label: '恢复', icon: 'fa-undo', type: 'success', show: (task: any) => filters.status === 'deleted' },
              { id: 'purge', label: '彻底删除', icon: 'fa-fire', type: 'danger', show: (task: any) => filters.status === 'deleted' },
              { id: 'delete', label: '删除', icon: 'fa-trash', type: 'danger', disabled: (task: any) => isControlling.has(task.id) }
            ]"
            :search-query="searchTerm"
            @toggle-selection="toggleTaskSelection"
            @action="handleTaskAction"
            @name-updated="handleNameUpdated"
            @page-change="handlePageChange"
            @page-size-change="handlePageSizeChange"
          />
        </div>
      </section>
      
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
import { useTasks } from './tasks';
import { TaskStatus, TaskEvaluationStatus, FINISHED_STATUSES } from '@/domain/enums';
import TaskListWithPagination from '../../components/task/TaskListWithPagination.vue';
import TaskComparisonReport from './TaskComparisonReport.vue';
import TaskTypeModal from '../../components/common/modal/TaskTypeModal.vue';
import TaskDataExportDialog from '../../components/task/TaskDataExportDialog.vue';
import TaskDataImportDialog from '../../components/task/TaskDataImportDialog.vue';
import BadgeFilter from '../../components/common/BadgeFilter.vue';
import FavoriteTrashBar from '../../components/common/FavoriteTrashBar.vue';
import AlgorithmFilter from '../../components/algorithm/AlgorithmFilter.vue';

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

/** INT-301：评估状态筛选（与执行状态并列；值 = 任务级评估状态原值） */
const EVALUATION_FILTER_OPTIONS = [
  { value: TaskEvaluationStatus.PENDING, label: '待评估' },
  { value: TaskEvaluationStatus.EVALUATING, label: '评估中' },
  { value: TaskEvaluationStatus.COMPLETED, label: '已评估完成' },
  { value: TaskEvaluationStatus.FAILED, label: '评估失败' },
  { value: TaskEvaluationStatus.SKIPPED, label: '评估跳过' },
];

const TIME_RANGE_OPTIONS = [
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
  batchPurge,
  // INT-215：回收站工具栏（对齐报告/用例交互口径）
  taskTrashMode,
  toggleTaskTrashMode,
  handleTaskFavoriteFilterChange
} = useTasks();

// ===== 徽章筛选变更（写入 ReadModel 筛选状态后统一走 applyFilters）=====
function handleStatusBadgeChange(value: string | number) {
  filters.value.status = String(value);
  applyFilters();
}

/** INT-301：评估状态徽章筛选（与执行状态并列） */
function handleEvaluationBadgeChange(value: string | number) {
  filters.value.evaluationStatus = String(value);
  applyFilters();
}

function handleTimeRangeBadgeChange(value: string | number) {
  filters.value.timeRange = String(value);
  applyFilters();
}

function handleAlgorithmBadgeChange(value: string | number) {
  filters.value.algorithmType = String(value);
  applyFilters();
}
</script>

<style scoped>@import './Tasks.css';

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
