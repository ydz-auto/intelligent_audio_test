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
        @update:active-tab="newTab => activeTab = newTab"
        @test-case-click="showTestCaseDetails"
        @pause-test="pauseTest"
        @resume-test="resumeTest"
        @stop-test="stopTest"
        @load-more-logs="loadMoreLogs"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue';
import { tasksApi, logsApi } from '../../../utils/api';
import { useTaskProgress } from '../../../composables/task/useTaskProgress';
import { useModalControl, MODAL_TYPES } from '../../../composables/modal/useModal';
import { transformTestCaseStatus } from '../../../utils/statusUtils';
import TestExecutionComponent from '../../layout/TestExecutionComponent.vue';
import type { Task, Log } from '../../../shared/types';

const props = defineProps({
  taskId: {type: [String, Number], required: true}
});

const modalControl = useModalControl();

const loading = ref(true);
const error = ref<string | null>(null);
type TaskDetail = Task & Record<string, any>;
const task = ref<TaskDetail | null>(null);
const activeTab = ref('cases');
const isPaused = ref(false);
const localLogs = ref<Log[]>([]);

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

const taskType = computed<'API' | 'E2E'>(() => (task.value?.type === 'api' ? 'API' : 'E2E'));

const {
  progressPercentage,
  completedTests,
  inProgressTests,
  pendingTests,
  executionFailedTests,
  evaluationFailedTests,
  totalTestCases,
  taskStatus,
  elapsedTime,
  estimatedTime,
  expectedCompleteTime,
  associatedCases
} = useTaskProgress({
  testType: taskType.value,
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
    time: formatLogTime(log.timestamp ?? log.time ?? log.createdAt),
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
      
      const response = await logsApi.getAll({ 
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
      const response = await logsApi.getAll({ 
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
    apiCount: t?.type === 'api' ? (t?.apiIds?.length || t?.apis?.length || 0) : 0,
    deviceCount: t?.type === 'e2e' ? (t?.deviceIds?.length || t?.devices?.length || 0) : 0,
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
  if (task.value?.type === 'e2e') {
    return task.value?.devices || []
  }
  return task.value?.apis || []
});

async function fetchTaskDetails() {
  loading.value = true;
  error.value = null;
  try {
    const taskData = await tasksApi.getOne(props.taskId);
    if (!taskData) {
      error.value = '未找到任务详情';
      loading.value = false;
      return;
    }
    
    task.value = taskData;

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

    if (taskData.cases && taskData.cases.length > 0) {
      associatedCases.value = taskData.cases.map((tc: any) => {
        const transformed = transformTestCaseStatus(tc);
        return {
          id: tc.caseId || tc.id,
          name: tc.name,
          status: transformed.status,
          duration: tc.duration || '',
          executionStatus: transformed.executionStatus,
          evaluationStatus: transformed.evaluationStatus
        };
      });
    }
    
    if (taskData.type === 'e2e') {
      associatedDevices.value = taskData.devices || [];
    } else {
      associatedDevices.value = taskData.apis || [];
    }
    
    totalTestCases.value = associatedCases.value.length;
    
    const caseList = associatedCases.value;
    // 只计算真正完成的用例（status为completed且不是失败状态）
    completedTests.value = caseList.filter((tc) => tc.status === 'completed' && tc.executionStatus !== 'failed' && tc.evaluationStatus !== 'failed').length;
    // 计算进行中的用例
    inProgressTests.value = caseList.filter((tc) => 
      tc.status === 'in_progress' || 
      tc.status === 'calculating' ||
      tc.status === 'queued'
    ).length;
    // 计算执行失败的用例
    executionFailedTests.value = caseList.filter((tc) => tc.executionStatus === 'failed').length;
    // 计算评估失败的用例
    evaluationFailedTests.value = caseList.filter((tc) => tc.evaluationStatus === 'failed' && tc.executionStatus !== 'failed').length;
    // 计算待执行的用例
    pendingTests.value = caseList.filter((tc) => 
      tc.executionStatus === 'pending' && 
      tc.evaluationStatus === 'pending' &&
      tc.status !== 'completed' &&
      tc.status !== 'failed'
    ).length;
    // 重新计算总进度，只基于完成的用例
    if (totalTestCases.value > 0) {
      progressPercentage.value = Math.round((completedTests.value / totalTestCases.value) * 100);
    }
    
    // 重置分页状态并加载最新日志（page 1 = 最新）
    logPagination.value.page = 1;
    logPagination.value.hasMore = true;
    
    const firstResponse = await logsApi.getAll({
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
    
    if (String(taskData.status) === 'running' || String(taskData.status) === 'starting') {
      startLogPolling();
    }
    
  } catch (err) {
    console.error('Failed to fetch task details:', err);
    error.value = '加载任务详情失败';
  } finally {
    loading.value = false;
  }
}

async function pauseTest() {
  try {
    await tasksApi.control(props.taskId, 'pause');
    isPaused.value = true;
  } catch (err) {
    console.error('暂停任务失败:', err);
  }
}

async function resumeTest() {
  try {
    await tasksApi.control(props.taskId, 'resume');
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
      await tasksApi.stop(props.taskId);
      stopLogPolling();
    }
  } catch (err) {
    if (err !== 'canceled') {
      console.error('停止任务失败:', err);
    }
  }
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
  if (String(newStatus) === 'running' || String(newStatus) === 'starting') {
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
  border: 4px solid rgba(0, 0, 0, 0.1);
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
</style>
