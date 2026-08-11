import type { Ref } from 'vue';
import type { AudioUploadTask } from '../../shared/types';

/**
 * 本地任务持久化（localStorage）
 */

export function getLocalTasks(): AudioUploadTask[] {
  try {
    const stored = localStorage.getItem('audioUploadTasks');
    return stored ? JSON.parse(stored) : [];
  } catch (e) {
    console.error('Failed to get local tasks:', e);
    return [];
  }
}

export function saveLocalTask(
  task: AudioUploadTask,
  uploadTasks: Ref<AudioUploadTask[]>
): void {
  if (!task.id) return;
  try {
    const tasks = getLocalTasks();
    const index = tasks.findIndex(t => t.id === task.id);
    if (index !== -1) {
      tasks[index] = task;
    } else {
      tasks.push(task);
    }
    localStorage.setItem('audioUploadTasks', JSON.stringify(tasks));
    uploadTasks.value = tasks;
  } catch (e) {
    console.error('Failed to save local task:', e);
  }
}

export function pathBasename(filePath: string): string {
  if (!filePath) return '';
  const parts = filePath.split(/[\\/]/);
  return parts[parts.length - 1];
}
