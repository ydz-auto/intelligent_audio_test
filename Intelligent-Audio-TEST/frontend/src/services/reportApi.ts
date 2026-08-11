import { reportsApi } from '../utils/api';
import type { Report, Task } from './reportTypes';
import { devices } from './reportState';

export async function saveReport(reportData: Partial<Report>): Promise<Report> {
  try {
    if (reportData.id) {
      const result = await reportsApi.update(reportData.id, reportData);
      return result;
    } else {
      const result = await reportsApi.create(reportData);
      return result;
    }
  } catch (error) {
    console.error('保存报告失败:', error);
    throw error;
  }
}

export async function createComparisonReport(tasks: Task[]) {
  try {
    const reportData = {name: `任务对比报告_${new Date().toLocaleString()}`,
      type: 'comparison',
      taskIds: tasks.map(t => t.id),
      config: {devices: devices.value.filter(d => d.selected).map(d => ({ id: d.id, name: d.name, type: d.type}))}
    };

    const response = await reportsApi.create(reportData);
    return response;
  } catch (err: any) {
    console.error('Failed to create comparison report:', err);
    throw err;
  }
}

export async function exportReport(reportId: string | number, format = 'excel'): Promise<Blob> {
  try {
    const blob = await reportsApi.export([reportId], format);
    return blob;
  } catch (error) {
    console.error('导出报告失败:', error);
    throw error;
  }
}

export async function publishReport(reportId: string | number): Promise<any> {
  try {
    const result = await reportsApi.publish(reportId);
    return result;
  } catch (error) {
    console.error('发布报告失败:', error);
    throw error;
  }
}
