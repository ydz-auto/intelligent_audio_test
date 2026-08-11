import { ref } from 'vue';
import { useModalControl } from '../composables/modal/useModal';
import type {
  Report,
  ComparisonDevice,
  DeviceAPIComparisonItem,
  CaseExecutionItem,
  Task
} from './reportTypes';

export const modalManager = useModalControl();

export const createDefaultReport = (): Report => ({
  id: '',
  name: '任务对比报告',
  type: 'comparison',
  status: 'draft',
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  description: '',
  summary: {totalCases: 0, passedCases: 0, failedCases: 0, passRate: 0, avgScore: 0, allMetrics: [], detailedResults: [], deviceStats: [], apiStats: []}
});

export const comparisonReport = ref<Report>(createDefaultReport());

export const comparisonTasks = ref<Task[]>([]);

export const deviceApiComparisonData = ref<DeviceAPIComparisonItem[]>([]);
export const caseExecutionData = ref<CaseExecutionItem[]>([]);
export const devices = ref<ComparisonDevice[]>([]);

export const deviceApiColumns = [
  { key: 'name', label: '名称', type: 'text', sortable: true },
  { key: 'type', label: '类型', type: 'text', sortable: true },
  { key: 'version', label: '版本', type: 'text', sortable: true },
  { key: 'status', label: '状态', type: 'status', sortable: true },
  { key: 'totalCases', label: '总用例数', type: 'number', sortable: true },
  { key: 'successRate', label: '成功率', type: 'percentage', sortable: true },
  { key: 'avgResponseTime', label: '平均响应时间 (ms)', type: 'number', sortable: true },
  { key: 'stability', label: '稳定性', type: 'percentage', sortable: true }
];

export const caseExecutionColumns = [
  { key: 'name', label: '名称', type: 'text', sortable: true },
  { key: 'total', label: '总用例数', type: 'number', sortable: true },
  { key: 'executed', label: '已执行', type: 'number', sortable: true },
  { key: 'completed', label: '已完成', type: 'number', sortable: true },
  { key: 'failed', label: '失败', type: 'number', sortable: true },
  { key: 'successRate', label: '成功率', type: 'percentage', sortable: true },
  { key: 'failedRate', label: '失败率', type: 'percentage', sortable: true }
];
