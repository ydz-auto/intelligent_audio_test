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
              createdAt: formatDate(task.createdAt),
              tags: task.tags,
              deviceCount: task.deviceCount,
              caseCount: task.caseCount,
              completedCases: task.completedCases,
              totalCases: task.totalCases,
              algorithmType: task.algorithmType,
              algorithmParams: task.algorithmParams
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
              { id: 'pause', label: '暂停', icon: 'fa-pause', type: 'secondary', show: (task: any) => task.status === 'running', disabled: (task: any) => isControlling.has(task.id) },
              { id: 'resume', label: '继续', icon: 'fa-play', type: 'secondary', show: (task: any) => ['paused', 'stopped'].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
              { id: 'stop', label: '停止', icon: 'fa-stop', type: 'danger', show: (task: any) => ['running', 'paused', 'queued'].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
              { id: 'retry', label: '重新执行', icon: 'fa-redo', type: 'success', show: (task: any) => ['pending', 'failed', 'completed', 'stopped'].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
              { id: 'reevaluate', label: '重新评估', icon: 'fa-sync-alt', type: 'info', show: (task: any) => ['completed', 'failed', 'stopped', 'paused', 'skipped', 'merged'].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
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
      <section class="comparison-report-container" id="task-comparison-report-container" v-if="showComparisonReport">
        <div class="comparison-header">
          <h3 class="comparison-title">任务对比报告</h3>
          <p class="comparison-subtitle">对比分析所选任务的执行情况和结果，帮助您识别系统性能瓶颈和质量问题，为后续优化提供依据。</p>
        </div>
        
        <!-- 报告保存区域 -->
        <div class="report-save-section analysis-conclusion-card">
          <!-- 图标区域 -->
          <div class="analysis-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" stroke="#1890ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" stroke="#1890ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M10 2v20" stroke="#1890ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M14 2v20" stroke="#1890ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          
          <!-- 内容区域 -->
          <div class="analysis-content">
            <!-- 标题和操作按钮 -->
            <div class="analysis-header">
              <h4 class="analysis-title">{{ reportName || '任务对比报告' }}</h4>
              <div class="analysis-status">
                <span class="status-dot"></span>
                {{ reportServiceData?.status === 'draft' ? '草稿' : '已发布' }}
              </div>
            </div>
            
            <!-- 非编辑模式下显示静态文本 -->
            <div v-if="!isEditingReport" class="analysis-text">
              <div>
                {{ reportServiceData?.description || '请输入报告描述' }}
              </div>
            </div>
            
            <!-- 编辑模式下显示输入框 -->
            <div v-else class="analysis-edit">
              <div class="edit-field">
                <label for="report-name">报告名称</label>
                <input type="text" id="report-name" placeholder="请输入报告名称" v-model="reportName">
              </div>
              <div class="edit-field">
                <label for="report-description">报告描述</label>
                <textarea id="report-description" placeholder="请输入报告描述" rows="3" v-model="reportServiceData!.description"></textarea>
              </div>
            </div>
            
            <!-- 操作按钮 -->
            <div class="analysis-actions">
              <button v-if="!isEditingReport" class="btn btn-primary" @click="toggleEditReport">
                <i class="fas fa-edit"></i> 编辑
              </button>
              <template v-else>
                <button class="btn btn-primary" @click="saveComparisonReport">
                  <i class="fas fa-save"></i> 保存
                </button>
                <button class="btn btn-secondary" @click="cancelEditReport">
                  <i class="fas fa-times"></i> 取消
                </button>
              </template>
            </div>
          </div>
        </div>
        
        <!-- 统一的设备和API选择器 -->
        <div class="comparison-selectors">
          <h4 class="selector-title">
            <i class="fas fa-list"></i> 选择要对比的设备和API
          </h4>
          <div class="selector-content">
            <div id="unified-selector">
              <div v-for="device in reportDevices" :key="device.id"
                   class="device-select-item" :class="{ 'selected': device.selected, 'api-item': device.type === 'API' }"
                   @click="toggleDeviceSelection(device.id)">
                <!-- 设备/API图标 -->
                <div class="device-icon-wrapper">
                  <i :class="device.type === '设备' ? 'fas fa-headphones' : 'fas fa-exchange-alt'"></i>
                </div>
                <!-- 名称和类型 -->
                <div class="device-info">
                  <span class="device-name">{{ device.name }}</span>
                  <span class="device-type-tag">{{ device.type }}</span>
                </div>
                <!-- 选择状态标识 -->
                <div class="selection-indicator">
                  <i class="fas fa-check-circle"></i>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 分析结论 -->
        <div class="analysis-conclusion-card">
          <div class="analysis-icon">
            <i class="fas fa-chart-line"></i>
          </div>
          <div class="analysis-content">
            <div class="analysis-header">
              <h4 class="analysis-title">分析结论</h4>
              <div class="analysis-status" :class="reportServiceData.status">
                <span class="status-dot"></span>
                {{ reportServiceData.status === 'draft' ? '草稿' : '已发布' }}
              </div>
            </div>
            <div v-if="!isEditingConclusion" class="analysis-text" id="task-analysis-conclusion" v-html="reportConclusion"></div>
            <div v-else class="analysis-edit">
              <textarea 
                id="task-analysis-conclusion-edit" 
                class="analysis-textarea" 
                v-model="reportConclusion" 
                placeholder="请输入分析结论...">
              </textarea>
            </div>
            <div class="analysis-actions">
              <button v-if="!isEditingConclusion" class="btn btn-primary" @click="toggleEditConclusion">
                <i class="fas fa-edit"></i> 编辑
              </button>
              <template v-else>
                <button class="btn btn-primary" id="task-save-conclusion-btn" @click="saveConclusion">
                  <i class="fas fa-save"></i> 保存
                </button>
                <button class="btn btn-secondary" id="task-cancel-edit-btn" @click="cancelEditConclusion">
                  <i class="fas fa-times"></i> 取消
                </button>
              </template>
            </div>
          </div>
        </div>
        
        <!-- 设备/API信息对比 -->
        <div class="comparison-section">
          <ComparisonTableComponent 
            title="设备/API信息对比"
            :columns="deviceApiColumns"
            :data="deviceApiComparisonData"
            :default-collapsed="true"
            :show-search="false"
          />
        </div>
        
        <!-- 用例执行数量对比 -->
        <div class="comparison-section">
          <ComparisonTableComponent 
            title="用例执行数量对比"
            :columns="caseExecutionColumns"
            :data="caseExecutionData"
            :default-collapsed="true"
            :show-search="false"
          />
        </div>
        

        
        <!-- 按用例分组对比 -->
        <div class="comparison-section">
          <caseCategoryComparisonComponent :report-data="reportService.comparisonReport.value" />
        </div>
        
        <!-- 按用例标签对比 -->
        <div class="comparison-section">
          <caseTagComparisonComponent :report-data="reportService.comparisonReport.value" />
        </div>
        
        <!-- 具体用例对比 -->
        <div class="comparison-section">
          <specificCaseComparisonComponent :report-data="reportService.comparisonReport.value" />
        </div>
      </section>
    </div>

    <!-- 任务类型选择弹窗 -->
    <TaskTypeModal 
      v-if="isTaskTypeModalVisible"
      modalId="task-type-modal"
      @close="isTaskTypeModalVisible = false"
      @confirm="handleCreateTask"
    />
  </div>

  <!-- 操作按钮区域 -->
  <teleport to="#global-fixed-elements">
    <div id="floating-report-actions" v-if="showComparisonReport" style="position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; justify-content: center; gap: 16px; z-index: 9999; padding: 16px 24px; background: rgba(255, 255, 255, 0.95); border-radius: 12px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15); backdrop-filter: blur(10px); border: 1px solid rgba(226, 232, 240, 0.8);">
      <button class="btn btn-primary" id="keep-report-btn" @click="saveComparisonReport">
        <i class="fas fa-save"></i> 保存
      </button>
      <button class="btn btn-success" id="publish-report-btn" @click="publishComparisonReport">
        <i class="fas fa-paper-plane"></i> 发布
      </button>
      <button class="btn btn-secondary" id="close-comparison-report" @click="closeComparisonReport">
        <i class="fas fa-times"></i> 关闭对比报告
      </button>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { useTasks } from './tasks';
import TaskListWithPagination from '../../components/task/TaskListWithPagination.vue';
import ComparisonTableComponent from '../../components/report/ComparisonTableComponent.vue';
import CaseCategoryComparisonComponent from '../../components/report/CaseCategoryComparisonComponent.vue';
import CaseTagComparisonComponent from '../../components/report/CaseTagComparisonComponent.vue';
import SpecificCaseComparisonComponent from '../../components/report/SpecificCaseComparisonComponent.vue';
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
