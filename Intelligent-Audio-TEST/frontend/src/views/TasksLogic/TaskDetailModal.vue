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
import { tasksApi, logsApi } from '../../utils/api';
import { useTaskProgress } from '../../composables/useTaskProgress';
import { useModalControl, MODAL_TYPES } from '../../composables/useModal';
import { transformTestCaseStatus } from '../../utils/statusUtils';
import TestExecutionComponent from '../../components/TestExecutionComponent.vue';
import type { Task, Log } from '../../shared/types';

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
  perPage: 20,
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

const logs = computed(() => {
  // 后端返回的是倒序（最新在前），前端显示需要正序（最新在后）
  return [...localLogs.value].reverse().map((log) => ({
    id: log.id,
    time: log.timestamp ?? log.time ?? log.createdAt,
    level: log.level || 'info',
    content: log.content,
    type: log.level || 'info'
  }));
});

async function loadLogsWithRetry(page = 1, perPage = 100, maxRetries = 3, delayMs = 1000, appendToFront = false) {
  let lastError = null;
  
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      console.log(`[TaskDetailModal] 尝试加载日志 (${attempt}/${maxRetries}), 页: ${page}, 每页: ${perPage}, 追加到前面: ${appendToFront}`);
      
      const response = await logsApi.getAll({ 
        taskId: String(props.taskId),
        page: page,
        perPage: perPage
      });
      
      if (response && response.items) {
        if (page === 1) {
          localLogs.value = response.items;
        } else if (appendToFront) {
          localLogs.value = [...response.items, ...localLogs.value];
        } else {
          localLogs.value = [...localLogs.value, ...response.items];
        }
        
        logPagination.value.total = response.total || 0;
        logPagination.value.hasMore = localLogs.value.length < logPagination.value.total;
        console.log(`[TaskDetailModal] 成功加载 ${response.items.length} 条日志, 总计: ${localLogs.value.length}/${logPagination.value.total}`);
        return true;
      }
      return true;
    } catch (logErr) {
      lastError = logErr;
      console.error(`[TaskDetailModal] 加载日志失败 (${attempt}/${maxRetries}):`, logErr);
      
      if (attempt < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, delayMs * attempt));
      }
    }
  }
  
  console.error(`[TaskDetailModal] 多次重试后仍无法加载日志:`, lastError);
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
          (newLog) => !existingLogIds.has(newLog.id)
        );
        
        if (newLogs.length > 0) {
          // 将新日志添加到开头
          localLogs.value = [...newLogs, ...localLogs.value];
          console.log(`[TaskDetailModal] 轮询获取 ${newLogs.length} 条新日志`);
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
    
    // 重置分页状态并加载第一页日志
    logPagination.value.page = 1;
    logPagination.value.hasMore = true;
    await loadLogsWithRetry(1, logPagination.value.perPage);
    
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

// 加载更多日志
async function loadMoreLogs() {
  if (logPagination.value.loadingMore || !logPagination.value.hasMore) {
    return;
  }
  
  logPagination.value.loadingMore = true;
  const nextPage = logPagination.value.page + 1;
  
  try {
    const success = await loadLogsWithRetry(nextPage, logPagination.value.perPage, 3, 1000, true);
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
