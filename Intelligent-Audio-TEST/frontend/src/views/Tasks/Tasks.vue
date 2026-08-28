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
                <div class="stat-value">{{ totalTasks }}</div>
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

      <!-- 筛选和排序栏 -->
      <section class="filter-sort-section" v-if="!showComparisonReport">
        <div class="filter-row">
          <input type="text" class="search-input" placeholder="搜索任务名称、标签..." v-model="searchTerm" @input="handleSearch">
          
          <div class="filter-item">
            <label for="type-filter">任务类型：</label>
            <select class="filter-select" id="type-filter" v-model="filters.type" @change="applyFilters">
              <option value="all">全部类型</option>
              <option value="e2e">端到端测试</option>
              <option value="api">API测试</option>
            </select>
          </div>
          
          <div class="filter-item">
            <label for="algorithm-filter">算法类型：</label>
            <select class="filter-select" id="algorithm-filter" v-model="filters.algorithmType" @change="applyFilters">
              <option v-for="option in algorithmOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </div>
          
          <div class="filter-item">
            <label for="status-filter">任务状态：</label>
            <select class="filter-select" id="status-filter" v-model="filters.status" @change="applyFilters">
              <option value="all">全部状态</option>
              <option value="pending">待执行</option>
              <option value="queued">排队中</option>
              <option value="running">执行中</option>
              <option value="evaluating">评估中</option>
              <option value="reevaluate_queued">重新评估排队中</option>
              <option value="reevaluating">重新评估中</option>
              <option value="completed">已完成</option>
              <option value="failed">执行失败</option>
              <option value="deleted">已删除</option>
              <option value="merged">已合并</option>
            </select>
          </div>
        </div>
        
        <div class="filter-row">
          <div class="filter-item">
            <label for="time-filter">时间范围：</label>
            <select class="filter-select" id="time-filter" v-model="filters.timeRange" @change="applyFilters">
              <option value="all">全部时间</option>
              <option value="today">今日</option>
              <option value="yesterday">昨日</option>
              <option value="week">近7天</option>
              <option value="month">近30天</option>
              <option value="custom">自定义</option>
            </select>
          </div>
          
          <!-- 自定义时间范围 -->
          <div class="filter-item custom-time-range" v-if="filters.timeRange === 'custom'">
            <div>
              <label for="start-date">开始:</label>
              <input type="date" id="task-start-date" class="date-input" v-model="customDateRange.start">
            </div>
            <span>至</span>
            <div>
              <label for="end-date">结束:</label>
              <input type="date" id="task-end-date" class="date-input" v-model="customDateRange.end">
            </div>
          </div>
          
          <div class="sort-options">
            <span>排序：</span>
            <div class="sort-item" :class="{ active: sortConfig.field === 'created_at' }" @click="toggleSort('created_at')">
              创建时间 <i class="fas" :class="sortConfig.field === 'created_at' ? (sortConfig.order === 'asc' ? 'fa-sort-up' : 'fa-sort-down') : 'fa-sort'"></i>
            </div>
            <div class="sort-item" :class="{ active: sortConfig.field === 'status' }" @click="toggleSort('status')">
              状态 <i class="fas" :class="sortConfig.field === 'status' ? (sortConfig.order === 'asc' ? 'fa-sort-up' : 'fa-sort-down') : 'fa-sort'"></i>
            </div>
            <div class="sort-item" :class="{ active: sortConfig.field === 'title' }" @click="toggleSort('title')">
              名称 <i class="fas" :class="sortConfig.field === 'title' ? (sortConfig.order === 'asc' ? 'fa-sort-up' : 'fa-sort-down') : 'fa-sort'"></i>
            </div>
          </div>
        </div>
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
          <button class="btn-primary" @click="batchRestore" :style="{ display: filters.status === 'deleted' ? 'inline-block' : 'none' }">
            <i class="fas fa-undo"></i> 批量恢复
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
              type: task.type,
              status: task.status,
              createdAt: formatDate(task.created_at),
              tags: task.tags,
              deviceCount: task.device_count,
              caseCount: task.case_count,
              completedCases: task.completed_cases,
              totalCases: task.total_cases,
              algorithmType: task.algorithm_type,
              algorithmParams: task.algorithm_params
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
              { id: 'regenerate-report', label: '重新生成报告', icon: 'fa-sync', type: 'warning', show: (task: any) => [...FINISHED_STATUSES].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
              { id: 'pause', label: '暂停', icon: 'fa-pause', type: 'secondary', show: (task: any) => task.status === TaskStatus.RUNNING, disabled: (task: any) => isControlling.has(task.id) },
              { id: 'resume', label: '继续', icon: 'fa-play', type: 'secondary', show: (task: any) => [TaskStatus.PAUSED, TaskStatus.STOPPED].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
              { id: 'stop', label: '停止', icon: 'fa-stop', type: 'danger', show: (task: any) => [TaskStatus.RUNNING, TaskStatus.PAUSED, 'queued'].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
              { id: 'retry', label: '重新执行', icon: 'fa-redo', type: 'success', show: (task: any) => [TaskStatus.PENDING, TaskStatus.FAILED, TaskStatus.COMPLETED, TaskStatus.STOPPED].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
              { id: 'reevaluate', label: '重新评估', icon: 'fa-sync-alt', type: 'info', show: (task: any) => [...FINISHED_STATUSES].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
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
        :report-service="reportService"
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
  </div>
</template>

<script setup lang="ts">
import { useTasks } from './tasks';
import { TaskStatus, FINISHED_STATUSES } from '@/shared/types/enums';
import TaskListWithPagination from '../../components/task/TaskListWithPagination.vue';
import TaskComparisonReport from './TaskComparisonReport.vue';
import TaskTypeModal from '../../components/common/modal/TaskTypeModal.vue';

const {
  tasks,
  filteredTasks, selectedTasks, sortConfig,
  currentPage, pageSize, totalPages,
  searchTerm, filters, customDateRange, tagCurrentPage, tagPageSize,
  showComparisonReport, isEditingConclusion,
  totalTagPages, currentTags, totalTasks, pendingTasks, queuedTasks,
  inProgressTasks, completedTasks, failedTasks, deletedTasks,
  isAllSelected, formatDate, applyFilters, handleSearch, toggleSort,
  toggleTag, toggleTaskSelection, toggleSelectAll, cancelSelect, createNewTask, handleCreateTask,
  handleTaskAction, updateTaskName, batchDelete,
  batchCompare, batchMerge, batchRestore, closeComparisonReport, saveComparisonReport,
  publishComparisonReport, saveConclusion, toggleEditConclusion, reevaluateTask,
  cancelEditConclusion, toggleEditReport, cancelEditReport,
  deviceApiColumns, caseExecutionColumns,
  toggleDeviceSelection, fetchTasks,
  reportService,
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
  mergeButtonTitle
} = useTasks();
</script>

<style scoped>
@import './Tasks.css';
</style>
