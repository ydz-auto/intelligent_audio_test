import type { CaseExecutionItem, Task } from './reportTypes';
import {
  comparisonReport,
  comparisonTasks,
  deviceApiComparisonData,
  caseExecutionData,
  devices,
  createDefaultReport
} from './reportState';
import {
  getTaskStatusLabel,
  getReportTypeLabel
} from '../shared/constants/reportConstants';
import { updateComparisonData } from './reportComparison';

export function formatStatsForCharts(stats: any) {
  if (!stats) return null;

  const total = stats.total ?? 0;
  const completed = stats.completed ?? 0;
  const failed = stats.failed ?? 0;
  return { total, completed, failed, successRate: total ? Math.round((completed / total) * 100) : 0 };
}

export function getDefaultStats(): CaseExecutionItem[] {
  return [
    {
      id: 'total',
      name: '全部用例',
      total: 100,
      executed: 100,
      completed: 85,
      failed: 15,
      successRate: 85,
      failedRate: 15
    },
    {
      id: 'device1',
      name: '默认设备',
      total: 100,
      executed: 100,
      completed: 100,
      failed: 0,
      successRate: 100,
      failedRate: 0
    }
  ];
}

export function getStatusText(status: string): string {
  return getTaskStatusLabel(status);
}

export function getReportTypeLabelFromService(type: string): string {
  return getReportTypeLabel(type);
}

export function updateComparisonReportConclusion(tasks: any[]): void {
  const taskCount = tasks.length;
  if (taskCount === 0) {
    comparisonReport.value.conclusion = '根据对比分析，共选择了 0 个测试任务进行对比。这些任务涵盖了 API 测试和端到端测试类型，状态包括进行中、已完成和失败。从设备数量和用例数量来看，各任务之间存在明显差异，建议进一步分析任务执行效率和质量。通过对比不同任务的执行结果，可以识别出系统性能瓶颈和质量问题，为后续优化提供依据。';
    return;
  }

  const taskTypes = new Set<string>();
  const taskStatuses = new Set<string>();
  let totalDevices = 0;
  let totalCases = 0;

  tasks.forEach(task => {
    if (task) {
      taskTypes.add(task.type);
      taskStatuses.add(task.status);
      totalDevices += task.deviceCount || 0;
      totalCases += task.caseCount || 0;
    }
  });

  const typeText = Array.from(taskTypes).join('、');
  const statusText = Array.from(taskStatuses).map(status => getStatusText(status)).join('、');

  comparisonReport.value.conclusion = `根据对比分析，共选择了 ${taskCount} 个测试任务进行对比。这些任务涵盖了 ${typeText} 测试类型，状态包括 ${statusText}。从设备数量（共 ${totalDevices} 台）和用例数量（共 ${totalCases} 个）来看，各任务之间存在明显差异，建议进一步分析任务执行效率和质量。通过对比不同任务的执行结果，可以识别出系统性能瓶颈和质量问题，为后续优化提供依据。`;
}

export function resetReportState(): void {
  comparisonTasks.value = [];
  deviceApiComparisonData.value = [];
  caseExecutionData.value = [];
  devices.value = [];
  comparisonReport.value = createDefaultReport();
  console.log('[ReportService] 报告状态已重置');
}

export function toggleDeviceSelectionWrapper(deviceId: string | number): void {
  const device = devices.value.find(d => d.id === deviceId);
  if (device) {
    device.selected = !device.selected;
    updateComparisonData();
  }
}
