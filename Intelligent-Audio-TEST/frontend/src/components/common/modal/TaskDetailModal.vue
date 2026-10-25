<template>
  <div ref="rootRef" class="task-detail-modal">
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>正在加载任务详情...</p>
    </div>
    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-circle"></i>
      <p>{{ error }}</p>
    </div>
    <div v-else class="modal-content-wrapper">
      <!-- INT-738：任务详情「生成 AI 报告」入口——随 08_灵犀Agent 卡落地 /ai-chat 路由，
           先留按钮契约（→ /ai-chat?task={id}）；路由未注册前点击落 404 兜底，注册后直达灵犀Agent 工作台 -->
      <div class="task-detail-actions">
        <button
          class="btn btn-primary task-detail-actions-report"
          :disabled="!task"
          :title="!task ? '任务信息加载中' : '基于本任务生成 AI 报告（灵犀Agent）'"
          @click="openAiChat"
        >
          <i class="fas fa-robot"></i> 生成 AI 报告
        </button>
        <!-- INT-1838 规范 18 §6：挑选合并容器的「再次挑选」入口（与「生成 AI 报告」并列）。
             两入口同需 task:cherry_pick；无权限角色（algo_engineer / guest）整组隐藏，
             信息头与组成区照常只读可见。非容器任务不渲染。 -->
        <template v-if="isContainer && canPick">
          <button
            class="btn btn-primary"
            :disabled="reuseAdding"
            :title="reuseAdding ? '正在加入购物车…' : '把本容器全部源结果重新交给购物车（不复制容器、不新建任务）'"
            @click="reuseResultsToCart"
          >
            <i class="fas" :class="reuseAdding ? 'fa-spinner fa-spin' : 'fa-cart-plus'"></i>
            复用本次结果重新挑选
          </button>
          <button
            class="btn btn-secondary"
            title="打开挑选向导阶段 1（不预筛选任何来源任务）"
            @click="startPicking"
          >
            <i class="fas fa-layer-group"></i> 开始挑选
          </button>
        </template>
      </div>

      <TestExecutionComponent
        :test-type="taskType"
        :task-info="taskInfoData"
        :progress-info="progressInfoData"
        :associated-cases="associatedCases"
        :associated-devices="computedAssociatedDevices"
        :logs="logs"
        :show-logs="true"
        :is-paused="isPaused"
        :active-tab="activeTab"
        :connection-fallback="isProgressPolling"
        :task-status="taskStatus"
        :execution-status="executionStatus"
        :evaluation-status="evaluationStatus"
        :task-id="props.taskId"
        :container-source="containerSource ?? undefined"
        :failed-cases="Number(task?.failedCases ?? 0)"
        :case-count="Number(task?.caseCount ?? task?.totalCases ?? 0)"
        :created-at="task?.createdAt || ''"
        @update:active-tab="newTab => activeTab = newTab"
        @test-case-click="showTestCaseDetails"
        @pause-test="pauseTest"
        @resume-test="resumeTest"
        @stop-test="stopTest"
        @retry-task="retryTask"
        @reevaluate-task="reevaluateTask"
        @pick-results="openCherryPick"
        @remove-case="removeCase"
        @load-more-logs="loadMoreLogs"
        @refresh-review="fetchTaskDetails"
      >
        <!-- INT-1833 规范 18 §2.4：容器形态「组成」首屏主区（紧跟任务信息卡、位于关联折叠区之前）。
             四视图只读树由 ContainerComposition 承载，条目由 source + 本详情组装（零额外请求）。 -->
        <template #composition>
          <ContainerComposition
            v-if="containerSource"
            ref="compositionRef"
            :class="{ [COMPOSITION_FOCUS_HIGHLIGHT_CLASS]: compositionHighlighted }"
            :entries="compositionEntries"
            :source-task-count="containerSource.groups.length"
            @trace="openCompositionTrace"
          />
        </template>
      </TestExecutionComponent>

      <!-- INT-1837 规范 18 §7/§8.2：容器详情「报告」区——容器无执行过程、不自动生成报告，
           空态引导手动生成；非容器不渲染（普通任务保持现状） -->
      <ContainerReportCard v-if="isContainer" :task-id="props.taskId" />

      <!-- INT-467：任务可见性徽标 + 分享/设为私有切换（owner/admin 可切换；
           非 owner 私有任务 403 提示；切换成功 emit save → 列表即时刷新徽标） -->
      <div v-if="task" class="task-visibility-bar">
        <span class="task-visibility-label"><i class="fas fa-eye"></i> 可见性</span>
        <VisibilityBadge :visibility="taskVisibility" />
        <span v-if="visibilityDenied" class="task-visibility-denied">
          <i class="fas fa-lock"></i> 该任务为私有，仅创建者和管理员可切换
        </span>
        <button
          v-else-if="canToggleVisibility"
          type="button"
          class="btn btn-secondary btn-sm"
          :title="taskVisibility === Visibility.PRIVATE ? '将任务改为共享（所有有权限用户可见）' : '将任务设为私有（仅创建者和管理员可见）'"
          @click="toggleVisibility"
        >
          <i class="fas" :class="taskVisibility === Visibility.PRIVATE ? 'fa-users' : 'fa-lock'"></i>
          {{ taskVisibility === Visibility.PRIVATE ? '设为共享' : '设为私有' }}
        </button>
      </div>

      <!-- INT-339：挑选合并三步向导（挑选 → 购物车 → 下单三出口）。
           INT-401：presetTaskId 预筛选——任务详情「加入购物车」打开向导即定位本任务执行结果
           （设计 §9 入口粒度：结果列表级勾选，非全局候选列表从头再筛） -->
      <CherryPickDialog
        v-if="cherryPickVisible"
        @close="cherryPickVisible = false"
        @checked-out="handleCheckedOut"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/form.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/progress.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'

import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { tasksPort } from '@/composables/task/tasksPort';
import { confirmReviewOverwrite } from '@/composables/task/useReviewOverwrite';
import { logsPort } from '@/composables/task/logsPort';
import { useTaskProgress } from '../../../composables/task/useTaskProgress';
// INT-1832：挑选合并容器识别（source 端点，异常归一 null = 非容器静默）
import { useContainerComposition } from '../../../composables/task/useContainerComposition';
// INT-1838 规范 18 §6：再次挑选入口（批量加购 + 挑选向导阶段 1）
import { usePickCart } from '../../../composables/task/usePickCart';
import { useCartDrawerState } from '../../../composables/task/cartDrawerState';
import { requestPickWizard } from '../../../composables/task/usePickWizardRequest';
import { useAuthStore } from '../../../store/authStore';
import { PermissionPoint } from '../../../domain/enums';
import { useModalControl, MODAL_TYPES } from '../../../composables/modal/useModal';
import { useNotification } from '../../../composables/modal/useNotification';
import { isNotFoundOrForbidden, canEditResource } from '@/composables/visibility/useVisibility';
import { summarizeCaseStatuses } from '../../../utils/caseStatusSummary';
import TestExecutionComponent from '../../layout/TestExecutionComponent.vue';
// INT-1837 规范 18 §7：容器详情「报告」区（空态引导手动生成）
import ContainerReportCard from '../../layout/ContainerReportCard.vue';
import ContainerComposition from '../../task/pick/ContainerComposition.vue';
import { toCompositionEntries } from '../../task/pick/compositionTree';
import CherryPickDialog from './CherryPickDialog.vue';
import VisibilityBadge from '../visibility/VisibilityBadge.vue';
import type { Task, Log } from '../../../domain';
import { TaskStatus, Visibility, PICKABLE_STATUSES, type TaskStatusType } from '@/domain/enums';
// INT-1835 规范 18 §3.1：下单成功落点——组成区滚动定位与 1.2s 高亮
import {
  COMPOSITION_FOCUS_HIGHLIGHT_CLASS,
  COMPOSITION_FOCUS_HIGHLIGHT_MS,
  scrollCompositionIntoView,
  taskDetailLocation,
} from '../../../utils/compositionFocus';

const props = defineProps({
  taskId: {type: [String, Number], required: true},
  /** 落点聚焦区（INT-1835）：`composition` = 下单成功后落到组成区；null = 常规打开 */
  focusSection: {type: String as () => 'composition' | null, default: null},
  /** 全局模态栈中的实例 id（GlobalModalContainer 透传；路由页语境为空） */
  modalId: {type: String, default: ''},
  /** INT-1838 §6 溯源定位：打开后把该来源用例滚到可视区并高亮（空 = 不定位） */
  focusCaseId: {type: [String, Number], default: ''}
});

const emit = defineEmits<{
  (e: 'save', payload: { taskId: string | number; visibilityOnly: true; visibility: string }): void
}>();

const modalControl = useModalControl();
const notification = useNotification();

const loading = ref(true);
const error = ref<string | null>(null);
type TaskDetail = Task & Record<string, any>;
const task = ref<TaskDetail | null>(null);
const activeTab = ref('cases');
// INT-1832 规范 18 §2.3：容器识别写死——详情接口无 is_cherry_pick / merge_type，
// 一律由 source 溯源端点判定；4xx（站内普通任务常态）/5xx/网络异常 → null，详情保持现状。
const { source: containerSource, settled: containerSettled, isContainer } = useContainerComposition(computed(() => props.taskId));

/**
 * INT-1833 组成条目：source.groups[].results[] ← 详情 cases[]/devices[]/apis[] join
 * （用例名 / 设备 API 名 / 分组 / 标签；状态按 §4.6 降级口径，零额外请求）。
 */
const compositionEntries = computed(() => toCompositionEntries(
  containerSource.value,
  task.value?.cases ?? [],
  task.value?.devices ?? [],
  task.value?.apis ?? [],
));

/** 组成区叶行「溯源」：打开源任务详情（模态窗可叠层，不离开当前容器详情）。
 *  INT-1838 §6：并带上来源用例，详情打开后把该用例定位到可视区（1.2s 描边高亮）。 */
function openCompositionTrace(resultId: number) {
  const entry = compositionEntries.value.find((e) => e.resultId === resultId);
  if (!entry) return;
  modalControl.open(MODAL_TYPES.TASK_DETAIL, {
    taskId: entry.sourceTaskId,
    focusCaseId: entry.sourceCaseId ?? '',
  });
}

// ===== INT-1835 规范 18 §3.1：下单成功落点（?focus=composition）=====

const compositionRef = ref<InstanceType<typeof ContainerComposition> | null>(null);
/** 组成区高亮态（外描边 1.2s 后消退，样式含 reduced-motion 分支） */
const compositionHighlighted = ref(false);
let highlightTimer: ReturnType<typeof setTimeout> | null = null;
/** 每次任务切换只自动定位一次（刷新 / 重新下单可再来一次） */
let focusApplied = false;

/**
 * 可定位条件：宿主请求了组成区落点 + 详情加载完成 + 容器判定已结束且确为容器。
 * 非容器（source 归一 null）时条件永不成立 → 静默忽略，不报错、不滚动、无高亮（§3.1）。
 */
const compositionFocusReady = computed(() =>
  props.focusSection === 'composition'
  && !focusApplied
  && !loading.value
  && containerSettled.value
  && containerSource.value !== null);

function clearCompositionHighlight() {
  compositionHighlighted.value = false;
  if (highlightTimer) {
    clearTimeout(highlightTimer);
    highlightTimer = null;
  }
}

/** 滚到组成区顶部（滚动容器 = 模态窗内容区 / 布局主内容区，不是 window）并高亮 1.2s */
async function applyCompositionFocus() {
  focusApplied = true;
  await nextTick();
  const el = compositionRef.value?.$el;
  if (!(el instanceof HTMLElement)) return;
  scrollCompositionIntoView(el);
  compositionHighlighted.value = true;
  highlightTimer = setTimeout(() => {
    compositionHighlighted.value = false;
    highlightTimer = null;
  }, COMPOSITION_FOCUS_HIGHLIGHT_MS);
}

watch(compositionFocusReady, (ready) => {
  if (ready) void applyCompositionFocus();
}, { flush: 'post' });

// 详情模态窗可连续切任务（同组件复用）：切换后重新允许定位并清掉上一轮高亮
watch(() => props.taskId, () => {
  focusApplied = false;
  clearCompositionHighlight();
});

const isPaused = ref(false);
const localLogs = ref<Log[]>([]);

// ===== INT-467：任务可见性徽标 + 分享/设为私有切换 =====

/** 当前任务的可见性（缺省 shared） */
const taskVisibility = computed(() =>
  task.value?.visibility || Visibility.SHARED);

/** 403 守卫：私有任务且非 owner（admin 豁免，见 canEditResource） */
const visibilityDenied = computed(() => {
  if (!task.value) return false;
  if (taskVisibility.value !== Visibility.PRIVATE) return false;
  return !canEditResource({
    visibility: taskVisibility.value,
    createdByUserId: task.value.createdByUserId,
  });
});

/** 是否可切换可见性（owner 或 admin；私有非 owner 无权限） */
const canToggleVisibility = computed(() => {
  if (!task.value) return false;
  return canEditResource({
    visibility: taskVisibility.value,
    createdByUserId: task.value.createdByUserId,
  });
});

/** 分享 / 设为私有：PATCH /tasks/{id}/visibility（需 task:share + owner 校验） */
async function toggleVisibility() {
  if (!task.value || !canToggleVisibility.value) return;
  const next = taskVisibility.value === Visibility.SHARED
    ? Visibility.PRIVATE
    : Visibility.SHARED;
  try {
    await tasksPort.updateVisibility(props.taskId, next);
    task.value.visibility = next;
    notification.success(next === Visibility.SHARED ? '已改为共享' : '已设为私有');
    // 列表语境（从任务列表打开）由 useTaskControl 注入的 onSave → fetchTasks 即时刷新徽标；
    // 路由页语境（/tasks/:id）无 onSave 监听，仅本地状态更新
    emit('save', { taskId: props.taskId, visibilityOnly: true, visibility: next });
  } catch (error: any) {
    notification.error(error?.message || '切换可见性失败，请确认您有该任务的分享权限');
  }
}

// 日志分页状态
const logPagination = ref({
  page: 1,
  perPage: 100,
  total: 0,
  hasMore: true,
  loadingMore: false
});

const showTestCaseDetails = (caseId: string | number) => {
    modalControl.open(MODAL_TYPES.TEST_CASE_DETAIL, {
      title: '测试用例详情',
      width: '1200px',
      maxWidth: '95vw',
      maxHeight: '90vh',
      taskId: props.taskId,
      caseId
    });
};

// 展示口径由用例级被测设备类型派生（差异#2 收尾：取代 task.type）
const taskType = computed<'API' | 'E2E' | '混合'>(() => {
  const dts: string[] = task.value?.deviceTypes || [];
  const hasPhysical = dts.includes('physical');
  const hasApi = dts.includes('http_api') || dts.includes('websocket_api');
  if (hasPhysical && hasApi) return '混合';
  if (hasPhysical) return 'E2E';
  return 'API';
});

const {
  progressPercentage,
  completedTests,
  inProgressTests,
  pendingTests,
  executionFailedTests,
  evaluationFailedTests,
  totalTestCases,
  taskStatus,
  taskExecutionStatus: executionStatus,
  taskEvaluationStatus: evaluationStatus,
  elapsedTime,
  estimatedTime,
  expectedCompleteTime,
  associatedCases,
  isProgressPolling
} = useTaskProgress({
  currentTaskId: computed(() => props.taskId as string | number | null),
  onCompleted: (_data) => {
    console.log('任务已完成');
  },
  onFailed: (_data) => {
    console.log('任务执行失败');
  }
});

function getLogTimestamp(log: any): number {
  const timeStr = log.timestamp ?? log.time ?? log.createdAt;
  return timeStr ? new Date(timeStr).getTime() || 0 : 0;
}

function formatLogTime(timeStr: string): string {
  if (!timeStr) return '';
  const date = new Date(timeStr);
  if (isNaN(date.getTime())) return String(timeStr);
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  const ms = String(date.getMilliseconds()).padStart(3, '0');
  return `${month}-${day} ${hours}:${minutes}:${seconds}.${ms}`;
}

const logs = computed(() => {
  // localLogs 按时间升序存储（最老在前，最新在后），直接映射即可
  return localLogs.value.map((log) => ({
    id: log.id,
    time: formatLogTime(String(log.timestamp ?? log.time ?? log.createdAt ?? '')),
    level: log.level || 'info',
    content: log.content,
    type: log.level || 'info'
  }));
});

// 加载指定页的历史日志（更高页码 = 更老的日志），去重后 prepend 到 localLogs 头部
async function loadOlderLogs(page: number, perPage = 100, maxRetries = 3, delayMs = 1000): Promise<boolean> {
  let lastError = null;
  
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      console.log(`[TaskDetailModal] 尝试加载历史日志 (${attempt}/${maxRetries}), 页: ${page}`);
      
      const response = await logsPort.getAll({ 
        taskId: String(props.taskId),
        page: page,
        perPage: perPage
      });
      
      if (response && response.items) {
        // 后端返回 DESC（最新在前），反转为 ASC（最老在前）
        const olderLogs = [...response.items].reverse();
        
        // 去重：排除已存在的日志
        const existingIds = new Set(localLogs.value.map((l: Log) => l.id));
        const newItems = olderLogs.filter((item: Log) => !existingIds.has(item.id));
        
        if (newItems.length > 0) {
          // 更老的日志插入到数组头部
          localLogs.value = [...newItems, ...localLogs.value];
        }
        
        logPagination.value.total = response.total || 0;
        logPagination.value.hasMore = localLogs.value.length < logPagination.value.total;
        console.log(`[TaskDetailModal] 成功加载 ${newItems.length} 条历史日志, 总计: ${localLogs.value.length}/${logPagination.value.total}`);
        return true;
      }
      return true;
    } catch (logErr) {
      lastError = logErr;
      console.error(`[TaskDetailModal] 加载历史日志失败 (${attempt}/${maxRetries}):`, logErr);
      
      if (attempt < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, delayMs * attempt));
      }
    }
  }
  
  console.error(`[TaskDetailModal] 多次重试后仍无法加载历史日志:`, lastError);
  return false;
}

let pollInterval: ReturnType<typeof setInterval> | null = null;

async function startLogPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
  }
  
  pollInterval = setInterval(async () => {
    try {
      // 只获取最新的日志，避免重复加载
      const response = await logsPort.getAll({ 
        taskId: String(props.taskId), 
        page: 1, 
        perPage: 50 
      });
      
      if (response && response.items && response.items.length > 0) {
        const existingLogIds = new Set(localLogs.value.map(log => log.id));
        const newLogs = response.items.filter(
          (newLog: Log) => !existingLogIds.has(newLog.id)
        );
        
        if (newLogs.length > 0) {
          // 新日志按时间升序追加到尾部（localLogs 为 ASC 顺序）
          const sortedNew = [...newLogs].sort((a: Log, b: Log) => getLogTimestamp(a) - getLogTimestamp(b));
          localLogs.value = [...localLogs.value, ...sortedNew];
          console.log(`[TaskDetailModal] 轮询获取 ${newLogs.length} 条新日志, 总计: ${localLogs.value.length}`);
        }
      }
    } catch (err) {
      console.error('[TaskDetailModal] 轮询日志失败:', err);
    }
  }, 10000); // 增加轮询间隔到10秒
}

function stopLogPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

const taskInfoData = computed(() => {
  const t = task.value;
  return {
    taskName: t?.name || '测试任务',
    expectedTotalTime: estimatedTime.value,
    usedTime: elapsedTime.value,
    expectedCompleteTime: expectedCompleteTime.value,
    apiCount: t?.apis?.length || 0,
    deviceCount: t?.devices?.length || 0,
    totalTestCases: totalTestCases.value,
    concurrentTasks: t?.concurrentTasks || 1,
    testDate: t?.createdAt ? new Date(t.createdAt).toLocaleDateString() : new Date().toLocaleDateString(),
    creator: t?.creator || '系统管理员'
  };
});

const progressInfoData = computed(() => ({
  totalProgress: progressPercentage.value,
  completed: completedTests.value,
  inProgress: inProgressTests.value,
  pending: pendingTests.value,
  executionFailed: executionFailedTests.value,
  evaluationFailed: evaluationFailedTests.value
}));

const associatedDevices = ref<any[]>([]);

const computedAssociatedDevices = computed(() => {
  if (associatedDevices.value && associatedDevices.value.length > 0) {
    return associatedDevices.value
  }
  // 混合任务同时展示被测设备与被测 API
  return [...(task.value?.devices || []), ...(task.value?.apis || [])]
});

async function fetchTaskDetails() {
  loading.value = true;
  error.value = null;
  try {
    const taskData = await tasksPort.getOne(props.taskId);
    if (!taskData) {
      error.value = '未找到任务详情';
      loading.value = false;
      return;
    }
    
    task.value = taskData;

    // INT-301：详情首屏即带双状态（进度事件到达前的初始徽章）
    if (taskData.executionStatus) {
      executionStatus.value = String(taskData.executionStatus);
    }
    if (taskData.evaluationStatus) {
      evaluationStatus.value = String(taskData.evaluationStatus);
    }

    // INT-401 P1-3：以 GET /tasks/{id} 返回的 status 初始化 taskStatus。
    // socket 对已终态任务订阅后不重发 task_progress，HTTP 兜底进度又可能被
    // generation 竞态丢弃（见 useTaskProgress 修复）——不初始化会停在 PENDING，
    // 终态任务挑选入口不显示、暂停/停止误显。终态任务一开即正确，活跃任务由
    // 后续 socket/轮询事件覆盖。
    if (taskData.status) {
      taskStatus.value = taskData.status as TaskStatusType;
    }

    // 用后端返回的时间字段更新显示
    if (taskData.expectedTotalTime) {
      estimatedTime.value = String(taskData.expectedTotalTime);
    }
    if (taskData.expectedCompleteTime) {
      expectedCompleteTime.value = String(taskData.expectedCompleteTime);
    }
    if (taskData.usedTime) {
      elapsedTime.value = String(taskData.usedTime);
    }

  // Task 域类型为 camelCase，cases 为详情接口扩展字段（camelCase，无需转换）
  // INT-305：空数组也要覆盖（移除末例后刷新 cases=[]，length>0 守卫会把旧用例留在表里）
  // INT-405：双状态独立透传（不再前端合成单值展示状态）；status 为后端
  // derive_task_case_status 派生的复合结果态，仅供筛选/行底色等数据口径。
  if (Array.isArray(taskData.cases)) {
    associatedCases.value = taskData.cases.map((tc: any) => {
      return {
        id: tc.caseId || tc.id,
        name: tc.name,
        status: tc.status || '',
        duration: tc.duration ?? '',
        executionStatus: tc.executionStatus || '',
        evaluationStatus: tc.evaluationStatus || '',
        groupName: tc.groupName,
        tags: tc.tags,
        algorithmType: tc.algorithmType,
        // INT-340：透传人工复核标记（用例行「已复核」徽章依赖）
        reviewed: tc.reviewed || false
      };
    });
  }
    
    associatedDevices.value = [...(taskData.devices || []), ...(taskData.apis || [])];
    
    totalTestCases.value = associatedCases.value.length;
    
    // INT-405：首屏计数收敛到双状态分桶单一源（与 useTaskProgress 同口径）
    const summary = summarizeCaseStatuses(associatedCases.value);
    completedTests.value = summary.completed;
    inProgressTests.value = summary.inProgress;
    executionFailedTests.value = summary.executionFailed;
    evaluationFailedTests.value = summary.evaluationFailed;
    pendingTests.value = summary.pending;
    // 重新计算总进度，只基于完成的用例
    if (totalTestCases.value > 0) {
      progressPercentage.value = Math.round((completedTests.value / totalTestCases.value) * 100);
    }
    
    // 重置分页状态并加载最新日志（page 1 = 最新）
    logPagination.value.page = 1;
    logPagination.value.hasMore = true;
    
    const firstResponse = await logsPort.getAll({
      taskId: String(props.taskId),
      page: 1,
      perPage: logPagination.value.perPage
    });
    
    if (firstResponse && firstResponse.items) {
      // 后端返回 DESC（最新在前），反转为 ASC（最老在前，最新在后）
      localLogs.value = [...firstResponse.items].reverse();
      logPagination.value.total = firstResponse.total || 0;
      logPagination.value.hasMore = localLogs.value.length < logPagination.value.total;
      console.log(`[TaskDetailModal] 初始加载 ${localLogs.value.length}/${logPagination.value.total} 条最新日志`);
    }
    
    if (String(taskData.status) === TaskStatus.RUNNING || String(taskData.status) === TaskStatus.STARTING) {
      startLogPolling();
    }
    
  } catch (err) {
    console.error('Failed to fetch task details:', err);
    // INT-423/467：私有任务非 owner 路由直达 → 后端 404；统一文案不泄露资源名
    error.value = isNotFoundOrForbidden(err) ? '资源不存在或无权访问' : '加载任务详情失败';
  } finally {
    loading.value = false;
  }
}

async function pauseTest() {
  try {
    await tasksPort.control(props.taskId, 'pause');
    isPaused.value = true;
  } catch (err) {
    console.error('暂停任务失败:', err);
  }
}

async function resumeTest() {
  try {
    await tasksPort.control(props.taskId, 'resume');
    isPaused.value = false;
  } catch (err) {
    console.error('恢复任务失败:', err);
  }
}

async function stopTest() {
  try {
    const result = await modalControl.open<{ confirmed: boolean }>(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认停止',
      content: '确定要停止该任务吗？',
      danger: true,
      confirmText: '停止',
      cancelText: '取消'
    });
    if (result?.confirmed === true) {
      await tasksPort.stop(props.taskId);
      stopLogPolling();
    }
  } catch (err) {
    if (err !== 'canceled') {
      console.error('停止任务失败:', err);
    }
  }
}

// ===== INT-302：执行详情模态窗内的重执行/重评估（带范围选择模态窗，语义与任务卡片入口一致） =====

interface ReexecuteSelection {
  mode: 'selected' | 'failed_only' | 'all'
  caseIds: (string | number)[]
  dimensionIds: number[]
  /** F4：重新提取设备输出（仅重评估；缺省 false 与旧默认一致） */
  reextractDeviceOutput?: boolean
}

async function retryTask() {
  try {
    const selection = await modalControl.open<ReexecuteSelection>(MODAL_TYPES.REEXECUTE_OPTIONS, {
      title: '重新执行',
      content: '请选择重新执行范围',
      actionType: 'retry',
      taskId: props.taskId,
    });
    if (!selection?.mode) return;
    // INT-340：存在人工复核结果时硬确认覆盖提醒（不做静默覆盖）
    const reviewOk = await confirmReviewOverwrite(modalControl, props.taskId, selection, '重新执行');
    if (!reviewOk) return;
    await tasksPort.retry(props.taskId, selection.mode === 'all' ? undefined : {
      caseIds: selection.caseIds,
      mode: selection.mode,
    });
    await fetchTaskDetails();
  } catch (err) {
    console.error('重新执行任务失败:', err);
  }
}

async function reevaluateTask() {
  try {
    const selection = await modalControl.open<ReexecuteSelection>(MODAL_TYPES.REEXECUTE_OPTIONS, {
      title: '重新评估',
      content: '请选择重新评估范围',
      actionType: 'reevaluate',
      taskId: props.taskId,
    });
    if (!selection?.mode) return;
    // INT-340：存在人工复核结果时硬确认覆盖提醒（不做静默覆盖）
    const reviewOk = await confirmReviewOverwrite(modalControl, props.taskId, selection, '重新评估');
    if (!reviewOk) return;
    // INT-302 范围 → 既有 reevaluate_type 口径映射（同 useTaskControl.reevaluateTask）：
    // failed_only → 'failed'；selected → 'all' + caseIds；all → 'all' 无 selection。
    // dimensionIds 为空数组 = 维度全选（不过滤）。
    // F4：重新提取设备输出恢复为模态窗勾选项（默认 false 与旧默认一致）。
    const reevaluateType = selection.mode === 'failed_only' ? 'failed' : 'all';
    const hasSelection = selection.mode === 'selected' || selection.dimensionIds.length > 0;
    await tasksPort.reevaluate(props.taskId, reevaluateType, selection.reextractDeviceOutput === true, hasSelection ? {
      caseIds: selection.mode === 'selected' ? selection.caseIds : [],
      dimensionIds: selection.dimensionIds,
      mode: selection.mode,
    } : undefined);
    await fetchTaskDetails();
  } catch (err) {
    console.error('重新评估任务失败:', err);
  }
}

// ===== INT-339：挑选合并入口（加入购物车 → 下单三出口） =====

const cherryPickVisible = ref(false);
const router = useRouter();

/** 终态任务才展示挑选入口（§10 默认仅终态任务可挑选；INT-553 P3-4 与入口可见性同源 PICKABLE_STATUSES） */
const isPickableTask = computed(() =>
  PICKABLE_STATUSES.includes(String(task.value?.status ?? '')));

function openCherryPick() {
  if (!isPickableTask.value) {
    notification.warning('仅已完成/失败/停止的任务支持挑选执行结果');
    return;
  }
  cherryPickVisible.value = true;
}

/** 下单成功后跳转（设计 §9：下单成功 → 购物车出清 → 按出口跳转。
 *  merge 跳新任务详情；reexecute 跳重执行任务详情；reevaluate 跳首个来源任务详情
 *  查看评估进度。与 Tasks.vue handlePickCheckedOut 同口径——前端为 hash 路由，
 *  必须走 router.push（裸 path window.open 会把 hash 读空落到首页，INT-401 验收 P1-1）；
 *  无 taskId（如空来源）则仅关闭弹窗停留当前页。）
 *  INT-1835 规范 18 §3.1：merge 出口带 `?focus=composition` 落到组成区（与任务列表同一出口口径），
 *  reexecute / reevaluate 出口不带参数（行为不变）。 */
function handleCheckedOut(payload: { action: string; taskId?: number }) {
  cherryPickVisible.value = false;
  if (payload.taskId) {
    router.push(taskDetailLocation(payload.action, Number(payload.taskId)));
  }
}

// ===== INT-738：生成 AI 报告入口（随 08_灵犀Agent 落地 /ai-chat 路由；先留按钮契约） =====

/** 跳转灵犀Agent 工作台并携带本任务 ID（→ /ai-chat?task={id}） */
function openAiChat() {
  if (!props.taskId) return;
  router.push({ path: '/ai-chat', query: { task: String(props.taskId) } });
}

// ===== INT-1838：挑选合并容器「再次挑选」入口（规范 18 §6） =====

const route = useRoute();
const pickCart = usePickCart();
const cartDrawerState = useCartDrawerState();
const { hasPermission: can } = useAuthStore();

/** 权限门控（§6 权限列）：无 task:cherry_pick 的角色（algo_engineer / guest）两入口整组隐藏 */
const canPick = computed(() => can(PermissionPoint.TASK_CHERRY_PICK));

/** 容器全部源结果 ID（source.groups[].results[]；失效行一并提交，由后端按 missing 回显） */
const containerResultIds = computed<number[]>(() => (containerSource.value?.groups ?? [])
  .flatMap((group) => (group.results ?? []).map((r) => Number(r.resultId)))
  .filter((id) => Number.isInteger(id) && id > 0));

const reuseAdding = ref(false);
/** 本模态的遮罩元素（抽屉宿主的取定依据）；非模态语境（路由页打开详情）为 null */
const drawerLayerHost = ref<HTMLElement | null>(null);

/**
 * 「复用本次结果重新挑选」：把该容器全部 result_id 批量加购 → toast → 打开购物车抽屉。
 * 不复制容器、不新建任务；重复点击由后端幂等跳过（toast 回显「重复 k 条已跳过」）。
 * 模态语境下抽屉挂进本模态遮罩的层叠上下文（与 React 版把 CartDrawer 渲染在详情内同口径），
 * 否则抽屉（全局层 z-index 1000）会被模态遮罩（13000 档）压住，「去复核」不可点（INT-1838 P2-1）。
 */
async function reuseResultsToCart() {
  if (!canPick.value || reuseAdding.value) return;
  const resultIds = containerResultIds.value;
  if (resultIds.length === 0) {
    notification.warning('该任务没有合并来源记录');
    return;
  }
  reuseAdding.value = true;
  try {
    const outcome = await pickCart.addToCart(resultIds);
    const added = outcome?.added?.length ?? 0;
    const missing = outcome?.missing?.length ?? 0;
    const duplicated = outcome?.duplicated?.length ?? 0;
    if (missing > 0) {
      notification.warning(`已加入购物车 ${added} 条（${missing} 条源结果已失效未加入）`);
    } else if (duplicated > 0) {
      notification.success(`已加入购物车 ${added} 条（重复 ${duplicated} 条已跳过）`);
    } else {
      notification.success(`已加入购物车 ${added} 条`);
    }
    drawerLayerHost.value = (rootRef.value?.closest('.modal-overlay') as HTMLElement | null) ?? null;
    cartDrawerState.open({
      layerHost: drawerLayerHost.value,
      // 抽屉「去复核」时先收起本详情：复核向导在路由页层，模态不收就会开在它后面
      dismissHost: () => modalControl.close(props.modalId || undefined),
    });
  } catch (error: any) {
    notification.error(error?.message || '加入购物车失败');
  } finally {
    reuseAdding.value = false;
  }
}

/**
 * 「开始挑选」：打开挑选向导阶段 1（CherryPickWizard，step='pick'），不预筛任何来源任务。
 * 与面板工具栏「开始挑选」/ 购物车「去复核」同一套跨挂载机制：写共享请求 → 切到挑选合并
 * 页签，CherryPickPanel 挂载后消费请求自开向导。前端为 hash 路由，跳转必须走 router.push。
 */
function startPicking() {
  if (!canPick.value) return;
  requestPickWizard({ step: 'pick' });
  // 模态语境：先从全局模态栈移除本详情（路由页语境为空操作，随后导航离开）
  modalControl.close(props.modalId || undefined);
  const query: Record<string, string> = { ...route.query, tab: 'cherry-picks' } as Record<string, string>;
  delete query.wizard;
  router.push({ path: '/tasks', query });
}

// ===== INT-305：移除用例（四阶段全允许，按任务阶段说明删除后果） =====

interface RemoveCaseEvent {
  caseId: string | number
  name?: string
}

/**
 * 按任务阶段给出删除后果说明（对齐验收口径）：
 * - 待执行（pending/queued）：直接消失（物理删除）；
 * - 执行中（running/queued 活跃/评估中/暂停）：当前轮次中断 + 结果作废；
 * - 已完成/评估完成（终态）：报告聚合重算剔除，结果 excluded 保审计；
 * - 任务仅剩 1 个用例时二次确认（任务将空）。
 */
function buildRemoveCaseConsequence(): string {
  const status = String(task.value?.status ?? '');
  const activeStatuses = ['pending', 'queued', 'running', 'evaluating', 'reevaluate_queued', 'reevaluating', 'paused'];
  if (activeStatuses.includes(status)) {
    if (status === 'pending' || status === 'queued') {
      return '该任务尚未开始执行，用例将被直接移除。';
    }
    return '该任务正在执行：若该用例正在执行，其当前轮次将被中断，已产出的执行/评估数据将作废（结果标记排除）。';
  }
  return '该任务已结束：用例将从本任务移除，其执行/评估结果将被标记为排除（保审计），报告聚合将重算剔除该用例。';
}

async function removeCase(evt: RemoveCaseEvent) {
  const caseId = evt?.caseId;
  if (caseId === undefined || caseId === null || caseId === '') return;

  const caseName = evt.name || `用例 ${caseId}`;
  let confirmed: { confirmed: boolean } | null;
  try {
    confirmed = await modalControl.open<{ confirmed: boolean }>(MODAL_TYPES.BASIC_CONFIRM, {
      title: '移除用例',
      content: `确定从任务中移除「${caseName}」吗？${buildRemoveCaseConsequence()}`,
      danger: true,
      confirmText: '移除',
      cancelText: '取消'
    });
  } catch {
    return; // 用户取消
  }
  if (confirmed?.confirmed !== true) return;

  // 边界：任务只剩 1 个用例时二次确认（任务将空，提示是否连任务一并停止）。
  // 语义：确认=移除并停止任务；取消按钮（仅移除用例）=继续移除但不停止；
  // 仅关闭弹窗（X/ESC，promise 悬置不落 reject）视为放弃。
  if (associatedCases.value.length === 1) {
    let stopConfirmed: { confirmed: boolean } | null = null;
    try {
      stopConfirmed = await modalControl.open<{ confirmed: boolean }>(MODAL_TYPES.BASIC_CONFIRM, {
        title: '任务将变空',
        content: '这是任务中最后一个用例，移除后任务将不含任何用例。是否连任务一并停止（后续可在任务列表删除该任务）？',
        danger: true,
        confirmText: '移除并停止任务',
        cancelText: '仅移除用例'
      });
    } catch {
      // 「仅移除用例」按钮走 ModalConfirm cancel→reject 路径：按仅移除语义继续（不停止任务）
      stopConfirmed = null;
    }
    if (stopConfirmed?.confirmed === true) {
      try {
        await tasksPort.stop(props.taskId);
      } catch (err) {
        console.error('停止任务失败:', err);
      }
    }
  }

  try {
    await tasksPort.removeCase(props.taskId, caseId);
    // 本地即时剔除 + 计数联动（WS task_progress 推送会再次校正）
    associatedCases.value = associatedCases.value.filter(tc => String(tc.id) !== String(caseId));
    recountFromAssociatedCases();
    await fetchTaskDetails();
  } catch (err: any) {
    console.error('移除用例失败:', err);
    notification.error(err?.message || '移除用例失败');
  }
}

/** 移除后基于现存用例重算本模态窗计数/进度（INT-405：双状态分桶单一源，与 fetchTaskDetails 同口径） */
function recountFromAssociatedCases() {
  const summary = summarizeCaseStatuses(associatedCases.value);
  totalTestCases.value = associatedCases.value.length;
  completedTests.value = summary.completed;
  inProgressTests.value = summary.inProgress;
  executionFailedTests.value = summary.executionFailed;
  evaluationFailedTests.value = summary.evaluationFailed;
  pendingTests.value = summary.pending;
  progressPercentage.value = totalTestCases.value > 0
    ? Math.round((completedTests.value / totalTestCases.value) * 100)
    : 0;
}

// 加载更多日志（向上滚动加载更老的历史日志：page+1 = 更老的数据）
async function loadMoreLogs() {
  if (logPagination.value.loadingMore || !logPagination.value.hasMore) {
    return;
  }
  
  const nextPage = logPagination.value.page + 1;
  logPagination.value.loadingMore = true;
  
  try {
    const success = await loadOlderLogs(nextPage, logPagination.value.perPage);
    if (success) {
      logPagination.value.page = nextPage;
    }
  } catch (err) {
    console.error('加载更多日志失败:', err);
  } finally {
    logPagination.value.loadingMore = false;
  }
}

watch(() => task.value?.status, (newStatus) => {
  if (String(newStatus) === TaskStatus.RUNNING || String(newStatus) === TaskStatus.STARTING) {
    startLogPolling();
  } else {
    stopLogPolling();
  }
});

// ===== INT-1838 §6：溯源定位（来源用例滚入可视区 + 1.2s 描边高亮）=====

const rootRef = ref<HTMLElement | null>(null);
const FOCUS_HIGHLIGHT_MS = 1200;
/** 长距离定位不做平滑滚动（视口高度倍数）：长列表（138 用例、3.5 万 px）平滑滚动约 1.5s 才到位，
 *  1.2s 描边会在半路熄灭 —— 改为瞬移，描边从落位起算 */
const FOCUS_SMOOTH_MAX_VIEWPORTS = 1.5;
/** 平滑滚动的兜底等待上限（浏览器不支持 scrollend 时按此估算到位时间） */
const FOCUS_SCROLL_SETTLE_MS = 1200;
const focusTimers = new Set<number>();

/** 按「用例ID」徽章的 aria-label 精确定位来源用例卡（不改公共组件，仅读 DOM） */
function findCaseCard(caseId: string): HTMLElement | null {
  const root = rootRef.value;
  if (!root) return null;
  const badges = Array.from(root.querySelectorAll<HTMLElement>('.case-id-badge'));
  const hit = badges.find((b) => (b.getAttribute('aria-label') || '').includes(caseId));
  if (!hit) return null;
  return (hit.closest('.case-card') as HTMLElement | null) ?? hit;
}

/** 等平滑滚动落位：优先 scrollend（捕获阶段收元素滚动），不支持/无事件时按上限兜底 */
function waitScrollSettle(behavior: ScrollBehavior): Promise<void> {
  if (behavior === 'auto' || typeof window === 'undefined' || !('onscrollend' in window)) {
    return new Promise((resolve) => { window.setTimeout(resolve, behavior === 'auto' ? 0 : FOCUS_SCROLL_SETTLE_MS); });
  }
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      window.clearTimeout(timer);
      window.removeEventListener('scrollend', finish, true);
      resolve();
    };
    const timer = window.setTimeout(finish, FOCUS_SCROLL_SETTLE_MS);
    window.addEventListener('scrollend', finish, true);
  });
}

/** 用例清单由详情 + 进度两路异步装配，行可能晚于详情到位 → 限时轮询到命中为止 */
let focusToken = 0;
async function applyFocusCaseRow(caseId: string) {
  const token = ++focusToken;
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    const card = findCaseCard(caseId);
    if (token !== focusToken) return;
    if (card) {
      const reduceMotion = typeof window !== 'undefined'
        && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      // 高亮从「滚到位」起算：长距离瞬移、近距离平滑等落位后再描边（P3-2）
      const viewportH = window.innerHeight || 0;
      const rect = card.getBoundingClientRect();
      const alreadyVisible = rect.top >= 0 && rect.bottom > 0 && rect.bottom <= viewportH;
      const distance = Math.abs(rect.top - viewportH / 2);
      const behavior: ScrollBehavior = reduceMotion || distance > viewportH * FOCUS_SMOOTH_MAX_VIEWPORTS
        ? 'auto'
        : 'smooth';
      const canScroll = typeof card.scrollIntoView === 'function';
      if (canScroll) card.scrollIntoView({ block: 'center', behavior });
      if (canScroll && !alreadyVisible) await waitScrollSettle(behavior);
      if (token !== focusToken) return;
      card.classList.add('tdm-focus-highlight');
      const timer = window.setTimeout(() => {
        focusTimers.delete(timer);
        card.classList.remove('tdm-focus-highlight');
      }, FOCUS_HIGHLIGHT_MS);
      focusTimers.add(timer);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
}

watch(
  [() => task.value, () => String(props.focusCaseId ?? '')],
  ([loadedTask, caseId]) => {
    if (!loadedTask || !caseId) return;
    // 用例行在「关联用例」页签（容器形态为「用例清单」折叠区）内
    activeTab.value = 'cases';
    void nextTick().then(() => applyFocusCaseRow(String(caseId)));
  },
  { immediate: true },
);

onMounted(() => {
  fetchTaskDetails();
});

onUnmounted(() => {
  stopLogPolling();
  // INT-1835：高亮计时器随组件销毁清理（连续开关详情不残留）
  if (highlightTimer) {
    clearTimeout(highlightTimer);
    highlightTimer = null;
  }
  focusToken += 1; // 停止溯源定位轮询
  focusTimers.forEach((timer) => window.clearTimeout(timer));
  focusTimers.clear();
  // 抽屉挂在本模态遮罩内（P2-1）：遮罩随模态卸载前先收起，避免 Teleport 目标消失留下孤儿层
  if (drawerLayerHost.value && cartDrawerState.layerHost.value === drawerLayerHost.value) {
    cartDrawerState.close();
  }
});
</script>

<style scoped>
.task-detail-modal {
  min-height: 400px;
  padding: 0; /* 移除内边距，让内容填充模态框 */
}

.loading-state, .error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400px;
  gap: 16px;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid color-mix(in srgb, var(--color-black) 10%, transparent);
  border-left-color: var(--primary);
  border-radius: var(--radius-pill);
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-state i {
  font-size: 48px;
  color: var(--destructive);
}

.modal-content-wrapper {
  /* 移除滚动设置，由外层BasicModal控制滚动 */
}

/* INT-738：任务详情头部动作区（「生成 AI 报告」入口，对齐任务详情页主形态） */
.task-detail-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 0 16px;
}

.task-detail-actions .btn {
  min-height: 32px;
}

/* INT-1838：动作区左侧「生成 AI 报告」，右侧容器再次挑选入口（规范 18 §8.2 线框） */
.task-detail-actions-report {
  margin-right: auto;
}

/* INT-1838 §6：溯源定位高亮（用例卡属子组件节点，须 :deep 穿透；1.2s 后由脚本移除类） */
:deep(.tdm-focus-highlight) {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 40%, transparent);
  transition: box-shadow 0.3s ease;
}

/* INT-467：任务可见性徽标 + 分享/设为私有切换（token 化，与 VisibilityBadge 同色系） */
.task-visibility-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  margin: 12px 0 0;
  border-top: 1px solid var(--border);
  background: var(--muted);
}

.task-visibility-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--muted-foreground);
}

.task-visibility-denied {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-red-700);
}

.task-visibility-denied i {
  font-size: 12px;
}

/* INT-1835 规范 18 §3.1/§8.4：落点①组成区外描边高亮（1.2s 渐隐，深浅通用；reduced-motion 无动画）。
   宿主在 slot 内容里，用 :deep 命中组成区根节点（ContainerComposition 的 section#composition）。 */
.modal-content-wrapper :deep(.is-composition-focus) {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 40%, transparent);
  animation: composition-focus-highlight 1.2s ease-out forwards;
}

@media (prefers-reduced-motion: reduce) {
  .modal-content-wrapper :deep(.is-composition-focus) {
    animation: none;
  }
}

@keyframes composition-focus-highlight {
  0% {
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 40%, transparent);
  }
  100% {
    box-shadow: 0 0 0 2px transparent;
  }
}
</style>
