import { ref, type Ref } from 'vue';
import { useRouter } from 'vue-router';
import { tasksApi } from '../utils/api';
import { reportService } from '../services/reportService';
import type { Task } from '../shared/types';
import { useModalControl, MODAL_TYPES } from './useModal';
import { useNotification } from './useNotification';

/**
 * 任务控制组合式函数
 *
 * 职责：
 * - 任务控制操作（pause/resume/stop/retry/reevaluate/delete）
 * - 任务详情查看、报告查看
 * - 任务编辑（名称更新）
 * - 任务操作事件分发（handleTaskAction）
 */

export function useTaskControl(
  tasks: Ref<Task[]>,
  fetchTasks: () => Promise<void>
) {
  const router = useRouter();
  const modalControl = useModalControl();
  const notification = useNotification();

  const isControlling = ref<Set<string | number>>(new Set());
  const isGeneratingReport = ref(false);

  const pauseTask = async (taskId: string | number) => {
    if (isControlling.value.has(taskId)) return;

    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '暂停任务',
      content: '确定要暂停该测试任务吗？',
      confirmText: '暂停',
      cancelText: '取消'
    });

    if (confirmed) {
      isControlling.value.add(taskId);
      try {
        await tasksApi.control(taskId, 'pause');
        await fetchTasks();
      } catch (error: any) {
        console.error('Failed to pause task:', error);
      } finally {
        isControlling.value.delete(taskId);
      }
    }
  };

  const resumeTask = async (taskId: string | number) => {
    if (isControlling.value.has(taskId)) return;

    isControlling.value.add(taskId);
    try {
      const task = tasks.value.find(t => t.id === taskId);
      if (task?.status === 'stopped') {
        await tasksApi.start(taskId);
      } else {
        await tasksApi.control(taskId, 'resume');
      }
      await fetchTasks();
    } catch (error: any) {
      console.error('Failed to resume task:', error);
    } finally {
      isControlling.value.delete(taskId);
    }
  };

  const stopTask = async (taskId: string | number) => {
    if (isControlling.value.has(taskId)) return;

    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '停止任务',
      content: '确定要停止该测试任务吗？停止后将无法恢复。',
      confirmText: '停止',
      cancelText: '取消',
      danger: true
    });

    if (confirmed) {
      isControlling.value.add(taskId);
      try {
        await tasksApi.control(taskId, 'stop');
        await fetchTasks();
      } catch (error: any) {
        console.error('Failed to stop task:', error);
      } finally {
        isControlling.value.delete(taskId);
      }
    }
  };

  const viewTaskDetails = async (taskId: string | number) => {
    try {
      modalControl.open(MODAL_TYPES.TASK_DETAIL, { taskId });
    } catch (error) {
      console.error('Failed to view task details:', error);
    }
  };

  const viewTaskReport = async (task: Task) => {
    if (router.currentRoute.value.name === 'reportView') {
      notification.info('当前已有报告打开，请先关闭当前报告');
      return;
    }
    if (isGeneratingReport.value) {
      notification.info('正在生成报告，请稍候...');
      return;
    }
    isGeneratingReport.value = true;
    notification.info('正在生成报告，请稍候...');
    try {
      const result = await reportService.viewTaskReport(task);
      if (result && result.id) {
        notification.success('报告生成成功');
        router.push({ name: 'reportView', params: { id: result.id } });
      }
    } catch (error) {
      console.error('Failed to view task report:', error);
      notification.error('报告生成失败');
    } finally {
      isGeneratingReport.value = false;
    }
  };

  const editTask = async (taskId: string | number) => {
    try {
      modalControl.open(MODAL_TYPES.TASK_DETAIL, { taskId });
    } catch (error) {
      console.error('Failed to edit task:', error);
    }
  };

  const updateTaskName = async (taskId: string | number, newName: string) => {
    console.log('[DEBUG] updateTaskName called:', { taskId, newName });
    try {
      await tasksApi.update(taskId, { name: newName });
      const taskIndex = tasks.value.findIndex(t => t.id === taskId);
      if (taskIndex !== -1) {
        tasks.value[taskIndex].name = newName;
      }
      notification.success('任务名称已更新');
    } catch (error) {
      console.error('Failed to update task name:', error);
      notification.error('更新任务名称失败');
    }
  };

  const retryTask = async (taskId: string | number) => {
    if (isControlling.value.has(taskId)) return;

    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '重试任务',
      content: '确定要重试该测试任务吗？',
      confirmText: '重试',
      cancelText: '取消'
    });

    if (confirmed) {
      isControlling.value.add(taskId);
      try {
        await tasksApi.retry(taskId);
        await fetchTasks();
      } catch (error) {
        console.error('Failed to retry task:', error);
      } finally {
        isControlling.value.delete(taskId);
      }
    }
  };

  const reevaluateTask = async (taskId: string | number) => {
    if (isControlling.value.has(taskId)) return;

    const result = await modalControl.open(MODAL_TYPES.REEVALUATE, {
      content: '请选择重新评估类型'
    });

    if (result?.reevaluateType) {
      const reevaluateType = result.reevaluateType;
      const reextractDeviceOutput = result.reextractDeviceOutput || false;
      isControlling.value.add(taskId);
      let pollInterval: any = null;

      try {
        const apiResult = await tasksApi.reevaluate(taskId, reevaluateType, reextractDeviceOutput) as any;
        console.log('reevaluate result:', apiResult);
        await fetchTasks();
        console.log('tasks after reevaluate:', tasks.value.find((t: any) => t.id === taskId));

        if (apiResult?.data?.message) {
          notification.info(apiResult.data.message);
        } else {
          notification.success('重新评估任务已提交');
        }

        pollInterval = setInterval(async () => {
          await fetchTasks();
          const task = tasks.value.find((t: any) => t.id === taskId);
          console.log('poll task status:', task?.status);
          if (task && task.status === 'completed') {
            clearInterval(pollInterval);
            pollInterval = null;
            isControlling.value.delete(taskId);
            notification.success('评估完成');
          } else if (task && task.status !== 'evaluating') {
            clearInterval(pollInterval);
            pollInterval = null;
            isControlling.value.delete(taskId);
          }
        }, 3000);

        setTimeout(() => {
          if (pollInterval) {
            clearInterval(pollInterval);
            isControlling.value.delete(taskId);
          }
        }, 120000);

      } catch (error: any) {
        console.error('Failed to reevaluate task:', error);
        notification.error(error?.response?.data?.message || error?.message || '重新评估失败，请稍后重试');
        if (pollInterval) {
          clearInterval(pollInterval);
          isControlling.value.delete(taskId);
        }
      }
    }
  };

  const deleteTask = async (taskId: string | number) => {
    if (isControlling.value.has(taskId)) return;

    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '删除任务',
      content: '确定要删除该任务吗？',
      confirmText: '删除',
      cancelText: '取消',
      danger: true
    });

    if (confirmed) {
      isControlling.value.add(taskId);
      try {
        await tasksApi.delete(taskId);
        await fetchTasks();
      } catch (error) {
        console.error('Failed to delete task:', error);
      } finally {
        isControlling.value.delete(taskId);
      }
    }
  };

  const handleTaskAction = (event: any) => {
    const { action, task } = event;
    switch (action.id) {
      case 'view-details':
        viewTaskDetails(task.id);
        break;
      case 'view-report':
        viewTaskReport(task);
        break;
      case 'retry':
        retryTask(task.id);
        break;
      case 'reevaluate':
        reevaluateTask(task.id);
        break;
      case 'delete':
        deleteTask(task.id);
        break;
      case 'pause':
        pauseTask(task.id);
        break;
      case 'resume':
        resumeTask(task.id);
        break;
      case 'stop':
        stopTask(task.id);
        break;
    }
  };

  const getStatusText = (status: string) => reportService.getStatusText(status);
  const getStatusIcon = (status: string) => {
    const icons: Record<string, string> = {
      'pending': 'clock',
      'queued': 'hourglass',
      'running': 'play-circle',
      'completed': 'check-circle',
      'failed': 'exclamation-circle',
      'paused': 'pause-circle',
      'stopped': 'stop-circle',
      'skipped': 'minus-circle'
    };
    return icons[status] || 'question-circle';
  };
  const getStepStatusText = (status: string) => {
    const texts: Record<string, string> = {
      'pending': '等待中',
      'queued': '排队中',
      'running': '执行中',
      'completed': '已完成',
      'failed': '失败',
      'paused': '已暂停',
      'stopped': '已停止',
      'skipped': '已跳过'
    };
    return texts[status] || status;
  };
  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString();
  };

  return {
    isControlling,
    isGeneratingReport,
    pauseTask,
    resumeTask,
    stopTask,
    viewTaskDetails,
    viewTaskReport,
    editTask,
    updateTaskName,
    retryTask,
    reevaluateTask,
    deleteTask,
    handleTaskAction,
    getStatusText,
    getStatusIcon,
    getStepStatusText,
    formatDate,
  };
}
