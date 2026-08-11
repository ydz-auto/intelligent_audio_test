import { reportsApi } from '../utils/api';
import type { Report } from './reportTypes';

export async function saveReport(reportData: Partial<Report>): Promise<Report> {
  try {
    if (reportData.id) {
      const result = await reportsApi.update(reportData.id, reportData);
      return result;
    } else {
      throw new Error('报告不存在，无法保存。请先通过任务报告或批量对比生成报告。');
    }
  } catch (error) {
    console.error('保存报告失败:', error);
    throw error;
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
