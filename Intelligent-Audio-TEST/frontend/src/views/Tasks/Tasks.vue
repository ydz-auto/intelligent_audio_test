<template>
  <div class="tasks-view">
    <!-- 页面标题（INT-738：文案对齐 React 09_任务域「任务管理」） -->
    <section class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-tasks"></i>
          任务管理
        </h2>
        <p class="page-description">管理和跟踪所有测试任务的进度和状态</p>
      </div>
      <!-- 已发布任务发布入口（已发布页签内，对齐原独立页头部） -->
      <div class="header-right" v-if="activeTab === 'published' && can(PermissionPoint.TASK_PUBLISH)">
        <button class="btn btn-primary" :disabled="published.actionLoading" @click="openPublishModal">
          <i class="fas fa-bookmark"></i> 发布任务
        </button>
      </div>
      <!-- INT-577 §8：全局购物车入口（角标计数，task:read 可见；打开全局抽屉，增删链 task:cherry_pick 承载） -->
      <div class="header-right" v-if="can('task:read')">
        <button class="btn btn-secondary pick-cart-entry" @click="cartDrawerState.open()">
          <i class="fas fa-shopping-cart"></i> 挑选购物车
          <span v-if="pickCartCount > 0" class="pick-cart-badge">{{ pickCartCount }}</span>
        </button>
      </div>
    </section>

    <!-- 内容区域 -->
    <div class="tasks-content-wrapper">
      <!-- INT-738：7 统计卡 + 三图已移交工作台（02_工作台卡 B02 承接），本页不再保留；
           图表能力保留在 composables/task/useTaskCharts 供工作台卡复用 -->
      <!-- 页签（INT-738 重定基到集成基线：四页签 = 日常 / 已发布 / 挑选合并 / 收藏——
           合并页签收编进挑选合并（INT-577 裁定①），收藏独立页签（INT-298 主库恢复）；
           交付原口径「收藏收编为筛选」与集成基线差异见 INT-738 交付评论） -->
      <section class="tasks-container" v-if="!showComparisonReport">
        <div class="task-tabs">
          <button class="task-tab" :class="{ active: activeTab === 'daily' }" @click="switchTab('daily')">
            <i class="fas fa-tasks"></i> 日常
          </button>
          <button
            v-if="can(PermissionPoint.PUBLISHED_TASK_READ)"
            class="task-tab"
            :class="{ active: activeTab === 'published' }"
            @click="switchTab('published')"
          >
            <i class="fas fa-bookmark"></i> 已发布
            <span v-if="published.total > 0" class="task-tab-count">{{ published.total }}</span>
          </button>
          <button class="task-tab" :class="{ active: activeTab === 'cherryPick' }" @click="switchTab('cherryPick')">
            <i class="fas fa-shopping-cart"></i> 挑选合并
            <span v-if="containers.total > 0" class="task-tab-count">{{ containers.total }}</span>
          </button>
          <!-- 收藏页签（主库恢复：INT-298 收藏收编工具条后由负责人本地回改独立页签） -->
          <button class="task-tab" :class="{ active: activeTab === 'favorite' }" @click="switchTab('favorite')">
            <i class="fas fa-star"></i> 收藏
            <span v-if="favoriteIds.size > 0" class="task-tab-count">{{ favoriteIds.size }}</span>
          </button>
        </div>
      </section>

      <!-- 筛选和排序栏（日常 / 已发布 / 挑选合并 / 收藏 四页签统一，对齐 V9.7.10 共享筛选栏） -->
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

          <!-- INT-273：任务类型筛选（日常视图；派生口径 api/e2e/mixed，对齐 V9.7.10 基线徽章） -->
          <BadgeFilter
            v-if="activeTab === 'daily'"
            :options="TYPE_OPTIONS"
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
            :options="activeTab === 'daily' || activeTab === 'favorite' || activeTab === 'cherryPick' ? algorithmOptions : undefined"
            :model-value="currentFilter.algorithmType"
            title="算法筛选"
            @update:model-value="handleAlgorithmBadgeChange"
          />
        </div>

        <!-- INT-423/467：可见性筛选（全部/共享/私有；服务端 ?visibility= 行级过滤） -->
        <div class="filter-row" v-if="activeTab === 'daily'">
          <BadgeFilter
            :options="VISIBILITY_FILTER_OPTIONS"
            :model-value="visibilityFilter || 'all'"
            all-label="全部"
            title="可见性"
            @update:model-value="handleTaskVisibilityFilterChange"
          />
        </div>

        <!-- INT-215：收藏 / 回收站工具栏（日常视图专属；INT-400 #13 收藏收编为工具条筛选，
             回收站不再作为状态徽章筛选项） -->
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
          <!-- INT-577 §2.2 裁定②：批量「合并任务」钮撤销，吸收为「加入挑选」（task:cherry_pick 判定，
               任务级整任务加购 → 打开挑选向导并预选该批任务，等价旧合并任务入口） -->
          <button v-if="can(PermissionPoint.TASK_CHERRY_PICK)" class="btn-primary" @click="batchAddToPick" :disabled="!canAddToPick" :title="addToPickTitle">
            <i class="fas fa-cart-plus"></i> 加入挑选
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
              deletedByUserId: task.deletedByUserId,
              // INT-423/467：可见性徽标直通（私有带锁图标）
              visibility: task.visibility,
              createdByUserId: task.createdByUserId,
              // INT-423/467：编辑/删除入口可见性（私有资源仅 owner 可编辑）
              canEdit: canEditResource(task)
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

        <!-- 挑选合并面板（INT-577：统一容器页签，merged ∪ cherry_pick + 合并方式 facet + 页内四步向导） -->
        <template v-else-if="activeTab === 'cherryPick'">
          <CherryPickPanel
            ref="cherryPickPanelRef"
            :containers="containers"
            :task-actions="taskActions"
            :is-favorite="isFavorite"
            @task-action="handleTaskAction"
            @name-updated="handleMergedNameUpdated"
            @checked-out="handlePickCheckedOut"
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
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'
import "../../assets/styles/tasks/charts.css"
import "../../assets/styles/tasks/task-card.css"
import "../../assets/styles/tasks/task-status.css"
import "../../assets/styles/tasks/filter-sort.css"
import "../../assets/styles/tasks/stats.css"
import { ref, computed, reactive, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useTasks } from './tasks';
import { TaskStatus, TaskEvaluationStatus, FINISHED_STATUSES, REEXECUTE_ELIGIBLE_STATUSES, PermissionPoint, TestType } from '@/domain/enums';
import { useAuthStore } from '../../store/authStore';
import { usePublishedTasks } from '../../composables/publishedTask/usePublishedTasks';
import { useCherryPickContainers } from '../../composables/task/useCherryPickContainers';
import { useCartDrawerState } from '../../composables/task/cartDrawerState';
import { useModalControl, MODAL_TYPES } from '../../composables/modal/useModal';
import { useNotification } from '../../composables/modal/useNotification';
import TaskListWithPagination from '../../components/task/TaskListWithPagination.vue';
import TaskComparisonReport from './TaskComparisonReport.vue';
import '../../assets/styles/reports/base.css';
import '../../assets/styles/reports/reports.css';
import TaskTypeModal from '../../components/common/modal/TaskTypeModal.vue';
import TaskDataExportDialog from '../../components/task/TaskDataExportDialog.vue';
import TaskDataImportDialog from '../../components/task/TaskDataImportDialog.vue';
import PublishedTaskPanel from './PublishedTaskPanel.vue';
import CherryPickPanel from './CherryPickPanel.vue';
import { usePickCart } from '../../composables/task/usePickCart';
import { requestPickWizard, clearPickWizardRequest } from '../../composables/task/usePickWizardRequest';
import BadgeFilter from '../../components/common/BadgeFilter.vue';
import FavoriteTrashBar from '../../components/common/FavoriteTrashBar.vue';
import AlgorithmFilter from '../../components/algorithm/AlgorithmFilter.vue';
import { VISIBILITY_FILTER_OPTIONS } from '../../composables/visibility/useVisibility';
import { canEditResource } from '../../composables/visibility/useVisibility';

const route = useRoute();
const router = useRouter();
const { hasPermission: can } = useAuthStore();
const notification = useNotification();
const modalControl = useModalControl();

// ===== 页签（INT-577 §2.2 裁定①：合并页签收编；主库恢复收藏页签 → 终态四页签 = 日常/已发布/挑选合并/收藏）=====
type TaskTab = 'daily' | 'published' | 'cherryPick' | 'favorite';
const TAB_QUERY_VALUES: TaskTab[] = ['daily', 'published', 'cherryPick', 'favorite'];
const activeTab = ref<TaskTab>('daily');
const published = usePublishedTasks();
// INT-577：统一合并容器列表（merged ∪ cherry_pick + merge_type facet + stats）
const containers = useCherryPickContainers();
const pickCart = usePickCart();
const cartDrawerState = useCartDrawerState();
const cherryPickPanelRef = ref<InstanceType<typeof CherryPickPanel> | null>(null);
/** 购物车条目数（ComputedRef 解包为 number 供模板比较） */
const pickCartCount = computed(() => pickCart.cartCount.value ?? 0);
const publishedPanelRef = ref<InstanceType<typeof PublishedTaskPanel> | null>(null);

/** 页签切换：选中集清空 + URL query 同步（/tasks?tab=cherry-picks 兼容旧链接）。
 *  已发布/挑选合并面板随 v-else-if 挂载自拉列表（面板 onMounted 承担首次刷新） */
function switchTab(tab: TaskTab) {
  if (activeTab.value === tab) return;
  activeTab.value = tab;
  selectedTasks.value.clear();
  const tabParam = tab === 'daily' ? undefined : (tab === 'cherryPick' ? 'cherry-picks' : tab);
  router.replace({ query: { ...route.query, tab: tabParam } });
}

// ===== 收藏视图（INT-298：与 C 域收藏语义一致，favorite=true 过滤任务）=====
// INT-320：进出逻辑迁协调层 tasks.ts（loadFavoriteView 含回收站态入口清空，
// leaveFavoriteView 对称还原），本组件经 useTasks 解构调用
// ===== 筛选选项（组件级 UI 常量，对齐 V9.7.10 徽章筛选行）=====
// INT-215：「已删除（回收站）」自状态徽章移除——回收站入口统一为工具栏按钮（toggleTaskTrashMode）
// INT-301：原「任务状态」行更名「执行状态」——UX 审计 F1 打回修正：
// ① 三个评估过渡 chip（evaluating/reevaluate_queued/reevaluating）移除，
//    评估侧统一由下方评估状态筛选行承载（同口径 SQL 派生表达式）；
// ② 执行筛选改走 execution_status 派生参数（命中行执行徽章 == 所选筛选值），
//    不再按原始 Task.status 裸匹配（原始态口径与派生徽章双向错位）。
const STATUS_FILTER_OPTIONS = [
  { value: TaskStatus.PENDING, label: '待执行' },
  { value: TaskStatus.QUEUED, label: '排队中' },
  { value: TaskStatus.RUNNING, label: '执行中' },
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
  { value: 'all', label: '全部时间' },
  { value: 'today', label: '今日' },
  { value: 'yesterday', label: '昨日' },
  { value: 'week', label: '近7天' },
  { value: 'month', label: '近30天' },
  { value: 'custom', label: '自定义' },
];

/** INT-273：任务类型选项（派生口径 api/e2e/mixed，对齐 /tasks/stats type_counts 分布；
 *  V9.7.10 基线 TYPE_OPTIONS 为 e2e/api，mixed 为 device_type 派生新增类别） */
const TYPE_OPTIONS = [
  { value: TestType.E2E, label: '端到端测试' },
  { value: TestType.API, label: 'API测试' },
  { value: 'mixed', label: '混合测试' },
];

const {
  tasks,
  filteredTasks, selectedTasks, sortConfig,
  currentPage, pageSize, totalPages,
  searchTerm, filters, customDateRange,
  showComparisonReport, isEditingConclusion,
  totalTasks,
  isAllSelected, formatDate, applyFilters, handleSearch, toggleSort,
  toggleTaskSelection, toggleSelectAll, cancelSelect, createNewTask, handleCreateTask,
  handleTaskAction, updateTaskName, batchDelete,
  batchCompare, batchRestore, closeComparisonReport, saveComparisonReport,
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
  // 日志相关
  taskLogs, filteredTaskLogs, taskLogSearchTerm, taskLogLevelFilter, taskLogFilter,
  refreshTaskLogs, filterTaskLogs,
  // 算法选项
  algorithmOptions,
  // 协调逻辑
  handleNameUpdated,
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
  // INT-423/467：可见性筛选
  visibilityFilter,
  handleTaskVisibilityFilterChange,
  // INT-215：回收站工具栏（对齐报告/用例交互口径）
  taskTrashMode,
  toggleTaskTrashMode,
  handleTaskFavoriteFilterChange,
  // INT-320：收藏页签进出（协调层承载，含回收站态入口清空）
  loadFavoriteView,
  leaveFavoriteView
} = useTasks();

// ========== 四视图统一筛选排序（日常 / 已发布 / 挑选合并 / 收藏，对齐 V9.7.10）==========

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
  // INT-423/467：私有任务非 owner（含 admin）隐藏删除入口
  { id: 'delete', label: '删除', icon: 'fa-trash', type: 'danger', show: (task: any) => canEditResource(task), disabled: (task: any) => isControlling.value.has(task.id) },
];

/** 各视图筛选状态适配为统一结构（search/type/algorithmType/status/timeRange/customRange/sort），
 *  使顶部筛选排序栏在四视图间可复用同一套控件 */
const dailyFilterState = reactive({
  get search() { return searchTerm.value; },
  set search(v: string) { searchTerm.value = v; },
  // INT-273：任务类型（派生口径 api/e2e/mixed；'all' 归一为空串不下发）
  get type() { return filters.value.type || 'all'; },
  set type(v: string) { filters.value.type = v === 'all' ? '' : v; },
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

const cherryPickFilterState = reactive({
  get search() { return containers.filters.search; },
  set search(v: string) { containers.filters.search = v; },
  type: 'all',
  get algorithmType() { return containers.filters.algorithmType; },
  set algorithmType(v: string) { containers.filters.algorithmType = v; },
  get status() { return containers.filters.status; },
  set status(v: string) { containers.filters.status = v; },
  get timeRange() { return containers.filters.timeRange; },
  set timeRange(v: string) { containers.filters.timeRange = v; },
  get customRange() { return containers.filters.customRange; },
  set customRange(v: { start: string; end: string }) { containers.filters.customRange = v; },
  get sort() { return containers.filters.sort; },
  set sort(v: { field: string; order: 'asc' | 'desc' }) { containers.filters.sort = v; },
});

/** 当前视图的筛选状态（筛选排序栏统一绑定；收藏视图与日常视图共用日常列表数据源） */
const currentFilter = computed(() => {
  if (activeTab.value === 'published') return publishedFilterState;
  if (activeTab.value === 'cherryPick') return cherryPickFilterState;
  return dailyFilterState;
});

/** INT-339：挑选合并视图状态选项（容器创建即 completed） */
const CHERRY_PICK_STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: TaskStatus.COMPLETED, label: '已完成' },
];

/** 当前视图的状态选项 */
const currentStatusOptions = computed(() => {
  if (activeTab.value === 'published') return published.statusOptions;
  if (activeTab.value === 'cherryPick') return CHERRY_PICK_STATUS_OPTIONS;
  return STATUS_FILTER_OPTIONS;
});

/** 当前视图的创建时间排序字段（发布任务用 publishedAt） */
const sortFieldKey = computed(() => (activeTab.value === 'published' ? 'publishedAt' : 'createdAt'));

/** 筛选变更：按当前视图触发对应列表拉取 */
function applyCurrentFilter() {
  if (activeTab.value === 'published') {
    published.page = 1;
    published.fetchList();
  } else if (activeTab.value === 'cherryPick') {
    containers.apply();
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
  } else if (activeTab.value === 'cherryPick') {
    containers.toggleSort(field);
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

// ========== 合并容器：卡片/源行操作分发与重命名（对齐 V9.7.10 交互） ==========

/** 合并容器重命名（复用日常任务重命名接口，对齐 V9.7.10） */
async function handleMergedNameUpdated({ taskId, newName }: { taskId: string | number; newName: string }) {
  try {
    await updateTaskName(taskId, newName);
    containers.refresh();
  } catch (error: any) {
    notification.error(error?.message || '更新任务名称失败');
  }
}

// ===== INT-577 §2.2 裁定②：批量「合并任务」→「加入挑选」 =====

/** 可加入挑选状态（对齐后端 PickableTaskStatus 终态集合） */
const PICKABLE_TASK_STATUSES = [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED];

/** 批量「加入挑选」准入：全部选中任务为终态（completed/failed/stopped） */
const canAddToPick = computed(() => {
  if (selectedTasks.value.size === 0) return false;
  const selected = tasks.value.filter((t: any) => selectedTasks.value.has(t.id));
  return selected.length > 0 && selected.every((t: any) => PICKABLE_TASK_STATUSES.includes(t.status));
});

const addToPickTitle = computed(() => {
  if (selectedTasks.value.size === 0) return '请先选择任务';
  if (!canAddToPick.value) return '仅已完成、执行失败、已停止的终态任务可加入挑选';
  return '将所选任务加入挑选购物车（任务级整任务加购）';
});

/** 批量「加入挑选」：打开挑选向导并预选该批任务（任务级粒度，等价旧「合并任务」入口） */
function batchAddToPick() {
  if (selectedTasks.value.size === 0) return;
  const selected = tasks.value.filter((t: any) => selectedTasks.value.has(t.id));
  if (!canAddToPick.value) {
    notification.warning(addToPickTitle.value);
    return;
  }
  // 经共享状态传预选任务 id（P0 修复）：App.vue `<router-view :key="$route.fullPath">`
  // 在 query 变化时整树重挂载，本实例的 cherryPickPanelRef/wizardOpen 会被销毁——
  // 旧实现「导航后经 ref 打开向导」开到导航前的实例 A 上即被重挂载销毁（测试实证）。
  // 不再手动切 activeTab：交给导航后新实例按 query.tab 归位，避免面板先于导航挂载
  // 消费请求后又随重挂载销毁；新面板经 usePickWizardRequest immediate watch 自开向导。
  requestPickWizard({ presetTaskIds: selected.map((t: any) => t.id) });
  selectedTasks.value.clear();
  router.replace({ query: { ...route.query, tab: 'cherry-picks' } })
    .catch(() => clearPickWizardRequest());
}

// ===== INT-577：挑选合并下单成功处理 =====

/**
 * 下单成功（设计 §9：下单成功 → 购物车出清 → 按出口跳转）：
 * - merge 跳转新任务详情（容器任务详情）；
 * - reexecute 跳转重执行任务详情；
 * - reevaluate 跳转首个来源任务详情查看评估进度（无来源则刷新挑选合并列表）。
 * 购物车出清由 usePickCart.refreshCart 同步角标；容器列表 invalidate（页签计数 +1）。
 */
async function handlePickCheckedOut(payload: { action: string; taskId?: number }) {
  await pickCart.refreshCart();
  containers.refresh();
  if (payload.taskId) {
    router.push(`/tasks/${payload.taskId}`);
    return;
  }
  if (activeTab.value === 'cherryPick') {
    containers.refresh();
  }
}

// INT-738：统计卡与三图已移交工作台（02_工作台卡 B02），本页不再渲染图表——
// 图表 ref 依赖 watch 一并移除，图表能力保留在 composables/task/useTaskCharts 供工作台卡复用。

// INT-577 §2.2 裁定①：旧链接 redirect（?tab=merged → ?tab=cherry-picks；?tab=cherry-picks
// 归一为内部 cherryPick）；无权限回落日常；?tab=favorite 直达收藏页签（主库恢复独立收藏页签）。
onMounted(() => {
  const tabParam = String(route.query.tab ?? '');
  // ?tab=merged（旧「合并」页签）→ redirect 到挑选合并页签并切换页签态
  if (tabParam === 'merged') {
    if (can('task:read')) {
      router.replace({ query: { ...route.query, tab: 'cherry-picks' } });
      activeTab.value = 'cherryPick';
    }
  } else if (tabParam === 'cherry-picks' || tabParam === 'cherryPick') {
    if (can('task:read')) {
      activeTab.value = 'cherryPick';
    }
  } else if ((TAB_QUERY_VALUES as string[]).includes(tabParam)) {
    const target = tabParam as TaskTab;
    if (target !== 'published' || can(PermissionPoint.PUBLISHED_TASK_READ)) {
      activeTab.value = target;
    }
  }
  // INT-401：页面加载即同步购物车角标（usePickCart 模块级单例跨弹窗共享；此前仅
  // 打开挑选向导才 refresh，刷新页面后角标初始为 0 与实际购物车不一致）
  pickCart.refreshCart();
  // INT-577：挑选合并页签容器计数（进入即拉一次，面板 onMounted 亦拉，双保险防角标滞后）
  if (activeTab.value === 'cherryPick') {
    containers.fetchList();
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
  border-radius: var(--border-radius-md) var(--border-radius-md) 0 0;
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
  border-radius: var(--border-radius-full);
  background: var(--primary, #ff6a00);
  color: var(--color-white);
  font-size: 11px;
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

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

/* ===== INT-339：挑选购物车入口 ===== */
.pick-cart-entry {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.pick-cart-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border-radius: var(--border-radius-full);
  background: var(--primary, #ff6a00);
  color: var(--color-white);
  font-size: 11px;
  font-weight: 600;
}

</style>
