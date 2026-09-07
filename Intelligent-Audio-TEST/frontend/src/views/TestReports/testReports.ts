import { ref, onMounted } from 'vue';
import { reportsPort } from '@/composables/report/reportsPort';
import type { Report } from '../../domain';
import type { PaginatedResult } from '../../domain';

export function useTestReports() {
  const reports = ref<Report[]>([]);
  const loading = ref<boolean>(false);
  const total = ref<number>(0);
  
  const fetchReports = async (params: any = {}) => {
    loading.value = true;
    try {
      const response: PaginatedResult<Report> = await reportsPort.getAll(params);
      reports.value = response.items || [];
      total.value = response.total || 0;
    } catch (err) {
      console.error('Failed to fetch reports:', err);
    } finally {
      loading.value = false;
    }
  };

  const getReportTypeLabel = (type: string): string => {
    const types: Record<string, string> = {
      'task': '任务报告',
      'comparison': '对比报告',
      'secondaryComparison': '二次对比报告'
    };
    return types[type] || type;
  };
  
  onMounted(() => {
    fetchReports();
  });
  
  return { reports, loading, total, fetchReports, getReportTypeLabel };
}
