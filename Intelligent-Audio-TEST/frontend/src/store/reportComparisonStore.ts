import { ref } from 'vue';
import { ReportStatus } from '../domain/enums';
import type { Report, Task, ComparisonDevice, DeviceAPIComparisonItem, CaseExecutionItem } from '../domain/model';

/**
 * 对比报告 ReadModel（模块级单例状态）
 *
 * 职责：仅承载「报告对比视图」的跨视图共享状态与列配置。
 * 用例编排见 composables/report/useReportComparison.ts。
 */

/** 创建空白对比报告（含空汇总） */
export function createDefaultReport(): Report {
  return {
    id: '',
    name: '任务对比报告',
    type: 'comparison',
    status: ReportStatus.DRAFT,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    description: '',
    summary: {
      totalCases: 0,
      passedCases: 0,
      failedCases: 0,
      passRate: 0,
      avgScore: 0,
      allMetrics: [],
      detailedResults: [],
      deviceStats: [],
      apiStats: []
    }
  } as Report;
}

/** 当前对比报告 */
export const comparisonReport = ref<Report>(createDefaultReport());

/** 参与对比的任务列表 */
export const comparisonTasks = ref<Task[]>([]);

/** 对比面板中可选的设备/API 资源列表 */
export const comparisonDevices = ref<ComparisonDevice[]>([]);

/** 选中资源的指标对比行数据 */
export const deviceApiComparisonData = ref<DeviceAPIComparisonItem[]>([]);

/** 用例执行统计行数据 */
export const caseExecutionData = ref<CaseExecutionItem[]>([]);

/** 设备/API 对比表列配置接口（展示层契约，与 domain ComparisonColumn 用途不同） */
export interface ComparisonTableColumn {
  key: string;
  label: string;
  type: string;
  sortable: boolean;
}

/** 资源指标对比表列配置（展示层契约，字段为 DeviceAPIComparisonItem 的 key） */
export const deviceApiColumns: ComparisonTableColumn[] = [
  { key: 'name', label: '名称', type: 'text', sortable: true },
  { key: 'type', label: '类型', type: 'text', sortable: true },
  { key: 'version', label: '版本', type: 'text', sortable: true },
  { key: 'status', label: '状态', type: 'status', sortable: true },
  { key: 'totalCases', label: '总用例数', type: 'number', sortable: true },
  { key: 'successRate', label: '成功率', type: 'percentage', sortable: true },
  { key: 'avgResponseTime', label: '平均响应时间 (ms)', type: 'number', sortable: true },
  { key: 'stability', label: '稳定性', type: 'percentage', sortable: true }
];

/** 用例执行统计表列配置（展示层契约，字段为 CaseExecutionItem 的 key） */
export const caseExecutionColumns: ComparisonTableColumn[] = [
  { key: 'name', label: '名称', type: 'text', sortable: true },
  { key: 'total', label: '总用例数', type: 'number', sortable: true },
  { key: 'executed', label: '已执行', type: 'number', sortable: true },
  { key: 'completed', label: '已完成', type: 'number', sortable: true },
  { key: 'failed', label: '失败', type: 'number', sortable: true },
  { key: 'successRate', label: '成功率', type: 'percentage', sortable: true },
  { key: 'failedRate', label: '失败率', type: 'percentage', sortable: true }
];
