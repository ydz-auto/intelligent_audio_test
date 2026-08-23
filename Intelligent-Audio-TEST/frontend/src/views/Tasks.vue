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
              { id: 'regenerate-report', label: '重新生成报告', icon: 'fa-sync', type: 'warning', show: (task: any) => ['completed', 'failed', 'stopped', 'paused', 'skipped', 'merged'].includes(task.status), disabled: (task: any) => isControlling.has(task.id) },
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
import { onMounted, ref, watch, computed } from 'vue';
import { useTasks } from './TasksLogic/tasks';
import TaskListWithPagination from '../components/TaskListWithPagination.vue';
import ComparisonTableComponent from '../components/report/ComparisonTableComponent.vue';
import CaseCategoryComparisonComponent from '../components/report/CaseCategoryComparisonComponent.vue';
import CaseTagComparisonComponent from '../components/report/CaseTagComparisonComponent.vue';
import SpecificCaseComparisonComponent from '../components/report/SpecificCaseComparisonComponent.vue';
import TaskTypeModal from './TasksLogic/TaskTypeModal.vue';

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
  algorithmOptions
} = useTasks();

// 监听图表容器ref变化，初始化图表
watch([taskTypeChartRef, taskTrendChartRef, taskStatusChartRef], () => {
  if (taskTypeChartRef.value && taskTrendChartRef.value && taskStatusChartRef.value) {
    updateCharts();
  }
}, { deep: true });

onMounted(async () => {
  await fetchTasks();
  applyFilters();
  // 初始化时获取日志
  await refreshTaskLogs();
  
  // 初始化图表
  setTimeout(() => {
    if (taskTypeChartRef.value) {
      createTaskTypeChart(taskTypeChartRef.value);
    }
    if (taskTrendChartRef.value) {
      createTaskTrendChart(taskTrendChartRef.value);
    }
    if (taskStatusChartRef.value) {
      createTaskStatusChart(taskStatusChartRef.value);
    }
  }, 100);
});

const handleNameUpdated = ({ taskId, newName }: { taskId: string | number; newName: string }) => {
  console.log('[DEBUG] handleUpdateTaskName called:', { taskId, newName });
  updateTaskName(taskId, newName);
};

const canMerge = computed(() => {
  if (selectedTasks.value.size < 2) return false;
  const selectedTasksArray = tasks.value.filter(t => selectedTasks.value.has(t.id));
  return selectedTasksArray.every(t => t.status === 'completed');
});

const mergeButtonTitle = computed(() => {
  if (selectedTasks.value.size < 2) {
    return '请至少选择两个任务进行合并';
  }
  const selectedTasksArray = tasks.value.filter(t => selectedTasks.value.has(t.id));
  const incompleteTasks = selectedTasksArray.filter(t => t.status !== 'completed');
  if (incompleteTasks.length > 0) {
    const names = incompleteTasks.map(t => t.name).join(', ');
    return `以下任务未完成，无法合并: ${names}`;
  }
  return '点击将选中的已完成任务合并为一个新任务';
});
</script>

<style scoped>
/* 只导入主样式文件，所有组件样式已包含在main.css中 */
@import '../assets/styles/main.css';

/* 图表头部样式 */
.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

/* 时间粒度选择器样式 */
.time-granularity-selector {
  display: flex;
  gap: 8px;
}

/* 时间按钮样式 */
.time-btn {
  padding: 6px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: white;
  color: #64748b;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
  outline: none;
}

/* 时间按钮悬停样式 */
.time-btn:hover {
  background: #f1f5f9;
  color: #334155;
  border-color: #cbd5e1;
}

/* 时间按钮激活样式 */
.time-btn.active {
  background: #ff6a00;
  color: white;
  border-color: #ff6a00;
}

.comparison-report-container {
  margin-top: 32px;
}

.comparison-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 20px;
  background: linear-gradient(135deg, #fafafa 0%, #f5f5f5 100%);
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  margin-bottom: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  align-items: center;
  text-align: center;
}

.comparison-title {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  color: #2c3e50;
  background: linear-gradient(135deg, #FF6A00 0%, #FF8C40 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.comparison-subtitle {
  margin: 0;
  font-size: 15px;
  color: #7f8c8d;
  line-height: 1.5;
  max-width: 600px;
}

.report-save-section {
  background: linear-gradient(to right, #e6f7ff, #ffffff);
  border: 1px solid #91d5ff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
  display: flex;
  gap: 16px;
  align-items: flex-start;
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.1);
}

.analysis-icon {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  background: white;
}

.analysis-content {
  flex: 1;
}

.analysis-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.analysis-title {
  margin: 0;
  color: #0050b3;
  font-size: 1.1rem;
  font-weight: 600;
}

.analysis-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 0.8rem;
  font-weight: 500;
  background-color: #f0f9ff;
  color: #0ea5e9;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: #0ea5e9;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(14, 165, 233, 0.7); }
  70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(14, 165, 233, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(14, 165, 233, 0); }
}

.analysis-text {
  color: #333;
  line-height: 1.6;
  font-size: 0.95rem;
  padding: 0;
  transition: all 0.3s ease;
}

.analysis-edit {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.edit-field label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #475569;
}

.edit-field input, .edit-field textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  font-size: 0.95rem;
  line-height: 1.6;
  transition: all 0.3s ease;
}

.analysis-actions {
  margin-top: 12px;
  display: flex;
  gap: 12px;
  justify-content: flex-start;
  align-items: center;
}

.comparison-selectors {
  margin-bottom: 24px;
}

.selector-title {
  margin-bottom: 16px;
  color: #333;
  font-size: 16px;
  font-weight: 600;
}

.selector-content {
  background: #ffffff;
  padding: 24px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

#unified-selector {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.device-select-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 16px;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  background: white;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  width: 130px;
  height: 150px;
  position: relative;
  overflow: hidden;
}

.device-select-item:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  border-color: #cbd5e1;
}

.device-select-item.selected {
  border-color: #FF6A00;
  background-color: #fffaf0;
}

.device-select-item.api-item.selected {
  border-color: #1677FF;
  background-color: #f0f7ff;
}

.device-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  border-radius: 50%;
  background: #f8fafc;
  transition: all 0.3s ease;
}

.device-select-item.selected .device-icon-wrapper {
  background: rgba(255, 106, 0, 0.1);
}

.device-select-item.api-item.selected .device-icon-wrapper {
  background: rgba(22, 119, 255, 0.1);
}

.device-icon-wrapper i {
  font-size: 24px;
  color: #64748b;
}

.device-select-item.selected .device-icon-wrapper i {
  color: #FF6A00;
}

.device-select-item.api-item.selected .device-icon-wrapper i {
  color: #1677FF;
}

.device-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 100%;
}

.device-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: #1e293b;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  width: 100%;
}

.device-type-tag {
  font-size: 0.75rem;
  color: #64748b;
  padding: 2px 8px;
  background: #f1f5f9;
  border-radius: 10px;
}

.selection-indicator {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0;
  transform: scale(0.5);
  transition: all 0.3s ease;
}

.device-select-item.selected .selection-indicator {
  opacity: 1;
  transform: scale(1);
}

.selection-indicator i {
  font-size: 18px;
  color: #FF6A00;
}

.device-select-item.api-item.selected .selection-indicator i {
  color: #1677FF;
}
.analysis-conclusion-card {
  background: linear-gradient(to right, #e6f7ff, #ffffff);
  border: 1px solid #91d5ff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 32px;
  display: flex;
  gap: 16px;
  align-items: flex-start;
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.1);
}

.selector-hint {
  margin-top: 16px;
  font-size: 14px;
  color: #64748b;
  display: flex;
  align-items: center;
  gap: 8px;
}

.selector-hint i {
  color: #60a5fa;
}

.comparison-section {
  margin-bottom: 24px;
}

/* 日志区域样式 */
.logs-section {
  margin-top: 32px;
}

.logs-container {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  background-color: #f8fafc;
}

.log-item {
  margin-bottom: 12px;
  padding: 16px;
  background: white;
  border-radius: 8px;
  border-left: 4px solid #64748b;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  transition: all 0.2s ease;
}

.log-item:hover {
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
  transform: translateY(-1px);
}

.log-item.debug {
  border-left-color: #64748b;
}

.log-item.info {
  border-left-color: #3b82f6;
}

.log-item.warning {
  border-left-color: #f59e0b;
}

.log-item.error {
  border-left-color: #ef4444;
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.log-time {
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
}

.log-level {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 12px;
  background-color: #f1f5f9;
}

.log-item.debug .log-level {
  color: #64748b;
  background-color: #f1f5f9;
}

.log-item.info .log-level {
  color: #3b82f6;
  background-color: #dbeafe;
}

.log-item.warning .log-level {
  color: #f59e0b;
  background-color: #fef3c7;
}

.log-item.error .log-level {
  color: #ef4444;
  background-color: #fee2e2;
}

.log-content {
  font-size: 14px;
  color: #334155;
  margin-bottom: 12px;
  line-height: 1.5;
  word-break: break-word;
}

.log-meta {
  font-size: 11px;
  color: #94a3b8;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.log-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.log-meta i {
  font-size: 10px;
}

.empty-logs {
  text-align: center;
  color: #64748b;
  padding: 40px 0;
}

.empty-logs i {
  font-size: 32px;
  margin-bottom: 12px;
  display: block;
  color: #cbd5e1;
}

.logs-filter {
  margin-bottom: 16px;
}

.logs-filter .filter-row {
  margin-top: 12px;
  gap: 12px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.logs-filter .search-input {
  width: 100%;
  max-width: 400px;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.3s ease;
}

.logs-filter .search-input:focus {
  outline: none;
  border-color: #FF6A00;
  box-shadow: 0 0 0 3px rgba(255, 106, 0, 0.1);
}

.logs-filter .filter-select {
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  background-color: white;
  color: #334155;
  cursor: pointer;
  transition: all 0.3s ease;
}

.logs-filter .filter-select:focus {
  outline: none;
  border-color: #FF6A00;
  box-shadow: 0 0 0 3px rgba(255, 106, 0, 0.1);
}
</style>
