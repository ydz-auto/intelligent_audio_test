<template>
  <div class="task-detail-modal">
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>正在加载任务详情...</p>
    </div>
    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-circle"></i>
      <p>{{ error }}</p>
    </div>
    <div v-else class="modal-content-wrapper">
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
      />

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
import { ref, onMounted, onUnmounted, computed, watch } from 'vue';
import { tasksPort } from '@/composables/task/tasksPort';
import { confirmReviewOverwrite } from '@/composables/task/useReviewOverwrite';
import { logsPort } from '@/composables/task/logsPort';
import { useTaskProgress } from '../../../composables/task/useTaskProgress';
import { useModalControl, MODAL_TYPES } from '../../../composables/modal/useModal';
import { useNotification } from '../../../composables/modal/useNotification';
import { isNotFoundOrForbidden, canEditResource } from '@/composables/visibility/useVisibility';
import { summarizeCaseStatuses } from '../../../utils/caseStatusSummary';
import TestExecutionComponent from '../../layout/TestExecutionComponent.vue';
import CherryPickDialog from './CherryPickDialog.vue';
import VisibilityBadge from '../visibility/VisibilityBadge.vue';
import type { Task, Log } from '../../../domain';
import { TaskStatus, Visibility } from '@/domain/enums';

const props = defineProps({
  taskId: {type: [String, Number], required: true}
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
        duration: tc.duration || '',
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

/** 终态任务才展示挑选入口（§10 默认仅终态任务可挑选） */
const PICKABLE_STATUSES: readonly string[] = ['completed', 'failed', 'stopped'];
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
 *  查看评估进度。与 Tasks.vue handlePickCheckedOut 同口径；无 taskId（如空来源）
 *  则仅关闭弹窗停留当前页。） */
function handleCheckedOut(payload: { action: string; taskId?: number }) {
  cherryPickVisible.value = false;
  if (payload.taskId) {
    const routeData = routerResolveTaskDetail(Number(payload.taskId));
    if (routeData) window.open(routeData, '_self');
  }
}

function routerResolveTaskDetail(taskId: number): string | null {
  try {
    // 详情路由：/tasks/:id（router/index.ts meta taskDetail）；弹窗语境直接整页跳转
    return `/tasks/${taskId}`;
  } catch {
    return null;
  }
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

onMounted(() => {
  fetchTaskDetails();
});

onUnmounted(() => {
  stopLogPolling();
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
  border-left-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-state i {
  font-size: 48px;
  color: var(--danger-color);
}

.modal-content-wrapper {
  /* 移除滚动设置，由外层BasicModal控制滚动 */
}

/* INT-467：任务可见性徽标 + 分享/设为私有切换（token 化，与 VisibilityBadge 同色系） */
.task-visibility-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  margin: 12px 0 0;
  border-top: 1px solid var(--border-color);
  background: var(--background-secondary);
}

.task-visibility-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
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
</style>
