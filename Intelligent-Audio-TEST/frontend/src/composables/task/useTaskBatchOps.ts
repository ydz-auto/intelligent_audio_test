import { type Ref } from 'vue';
import { tasksApi } from '../../utils/api';
import { reportService } from '../../services/reportService';
import type { Task } from '../../shared/types';
import { useModalControl, MODAL_TYPES } from '../modal/useModal';


/**
 * 任务批量操作组合式函数
 *
 * 职责：
 * - 批量删除/恢复/导出/对比/合并任务
 * - 批量对比报告生成
 */

export function useTaskBatchOps(
  tasks: Ref<Task[]>,
  selectedTasks: Ref<Set<string | number>>,
  fetchTasks: () => Promise<void>
) {
  const modalControl = useModalControl();

  const batchDelete = async () => {
    if (selectedTasks.value.size === 0) return;
    if (confirm(`确定要删除选中的 ${selectedTasks.value.size} 个任务吗？`)) {
      try {
        const ids = Array.from(selectedTasks.value);
        await tasksApi.batchAction('delete', ids as any);
        selectedTasks.value.clear();
        await fetchTasks();
      } catch (error) {
        console.error('Failed to batch delete tasks:', error);
      }
    }
  };

  const batchExport = async () => {
    if (selectedTasks.value.size === 0) return;
    try {
      const ids = Array.from(selectedTasks.value);
      const result = await modalControl.open(MODAL_TYPES.IMPORT_EXPORT, {
        mode: 'export',
        title: '批量导出任务',
        supportedFormats: ['excel', 'json'],
        exportFields: [
          { key: 'id', label: '任务ID', defaultChecked: true },
          { key: 'name', label: '任务名称', defaultChecked: true },
          { key: 'description', label: '任务描述', defaultChecked: false },
          { key: 'type', label: '任务类型', defaultChecked: true },
          { key: 'status', label: '任务状态', defaultChecked: true },
          { key: 'createdAt', label: '创建时间', defaultChecked: true },
          { key: 'tags', label: '任务标签', defaultChecked: false },
          { key: 'deviceCount', label: '设备数量', defaultChecked: true },
          { key: 'caseCount', label: '用例数量', defaultChecked: true }
        ],
        advancedOptions: [
          {
            key: 'includeDetails',
            label: '包含详细信息',
            type: 'boolean',
            defaultValue: false
          },
          {
            key: 'format',
            label: '导出格式',
            type: 'select',
            defaultValue: 'excel',
            options: [
              { value: 'excel', label: 'Excel' },
              { value: 'json', label: 'JSON' }
            ]
          }
        ]
      });

      if (result) {
        const format = result.config.format || 'excel';
        const blob = await reportService.exportReport(ids[0], format);
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `tasks_export_${new Date().getTime()}.${format === 'excel' ? 'xlsx' : format}`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    } catch (error) {
      console.error('Failed to batch export tasks:', error);
    }
  };

  const batchCompare = async () => {
    if (selectedTasks.value.size < 2) {
      alert('请至少选择两个任务进行对比');
      return;
    }
    try {
      const selectedTasksArray = tasks.value.filter(t => selectedTasks.value.has(t.id));
      const taskIds = selectedTasksArray.map(t => t.id);
      await reportService.batchCompare(taskIds, selectedTasksArray);
      // 滚动到报告区域
      setTimeout(() => {
        const reportElement = document.getElementById('task-comparison-report-container');
        if (reportElement) {
          reportElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }, 100);
    } catch (error) {
      console.error('Failed to batch compare tasks:', error);
      alert('生成对比报告失败，请稍后重试');
    }
  };

  const batchRestore = async () => {
    if (selectedTasks.value.size === 0) return;
    try {
      const ids = Array.from(selectedTasks.value);
      await tasksApi.batchAction('restore', ids as any);
      selectedTasks.value.clear();
      await fetchTasks();
    } catch (error) {
      console.error('Failed to batch restore tasks:', error);
    }
  };

  const batchMerge = async () => {
    if (selectedTasks.value.size < 2) {
      alert('请至少选择两个任务进行合并');
      return;
    }

    const selectedTasksArray = tasks.value.filter(t => selectedTasks.value.has(t.id));
    const incompleteTasks = selectedTasksArray.filter(t => t.status !== 'completed');
    if (incompleteTasks.length > 0) {
      const names = incompleteTasks.map(t => t.name).join(', ');
      alert(`以下任务未完成，无法合并: ${names}`);
      return;
    }

    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '合并任务',
      content: `确定要合并选中的 ${selectedTasks.value.size} 个任务吗？合并后将会创建一个新的任务，原任务将被标记为已合并。`,
      confirmText: '合并',
      cancelText: '取消'
    });

    if (!confirmed) return;

    try {
      const ids = Array.from(selectedTasks.value);
      const result = await tasksApi.mergeTasks(ids as any) as any;
      selectedTasks.value.clear();
      await fetchTasks();
      alert(`合并成功！新任务: ${result.merged_task_name || result.name || '合并任务'}`);
    } catch (error: any) {
      console.error('Failed to merge tasks:', error);
      alert(error.message || '合并失败，请稍后重试');
    }
  };

  return {
    batchDelete,
    batchExport,
    batchCompare,
    batchRestore,
    batchMerge,
  };
}
