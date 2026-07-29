import { ref, watch, type Ref } from 'vue';
import { logsApi } from '../utils/api';
import type { Log, Task } from '../shared/types';

/**
 * 任务日志查看组合式函数
 *
 * 职责：
 * - 获取任务日志
 * - 按搜索词、级别、当前任务过滤日志
 * - 刷新日志
 */

export interface UILog extends Log {
  time: string;
}

export function useTaskLogs(filteredTasks: Ref<Task[]>) {
  const taskLogs = ref<UILog[]>([]);
  const taskLogSearchTerm = ref('');
  const taskLogLevelFilter = ref('all');
  const taskLogFilter = ref('all');
  const filteredTaskLogs = ref<UILog[]>([]);

  const filterTaskLogs = () => {
    let result = [...taskLogs.value];

    if (taskLogSearchTerm.value) {
      const term = taskLogSearchTerm.value.toLowerCase();
      result = result.filter(log =>
        log.content.toLowerCase().includes(term) ||
        (log.module?.toLowerCase().includes(term) ?? false) ||
        (log.source?.toLowerCase().includes(term) ?? false)
      );
    }

    if (taskLogLevelFilter.value !== 'all') {
      result = result.filter(log => log.level === taskLogLevelFilter.value);
    }

    if (taskLogFilter.value === 'current' && filteredTasks.value.length > 0) {
      const taskIds = new Set(filteredTasks.value.map(task => task.id));
      result = result.filter(log => taskIds.has((log as any).taskId));
    }

    filteredTaskLogs.value = result;
  };

  const fetchTaskLogs = async () => {
    try {
      const response = await logsApi.getAll({
        module: 'task',
        page: 1,
        perPage: 20
      });
      const logs = response.items || [];

      taskLogs.value = logs.map((log: Log) => {
        let formattedTime = log.time?.toString() || log.timestamp?.toString() || '';
        try {
          const date = new Date(formattedTime);
          if (!isNaN(date.getTime())) {
            formattedTime = date.toLocaleString();
          }
        } catch (e) {
          console.error('Failed to format log time:', e);
        }

        return { ...log, time: formattedTime } as UILog;
      });

      filterTaskLogs();
    } catch (error) {
      console.error('Failed to fetch task logs:', error);
    }
  };

  const refreshTaskLogs = async () => {
    await fetchTaskLogs();
  };

  watch([taskLogSearchTerm, taskLogLevelFilter, taskLogFilter, filteredTasks], () => {
    filterTaskLogs();
  });

  return {
    taskLogs,
    filteredTaskLogs,
    taskLogSearchTerm,
    taskLogLevelFilter,
    taskLogFilter,
    fetchTaskLogs,
    refreshTaskLogs,
    filterTaskLogs,
  };
}
