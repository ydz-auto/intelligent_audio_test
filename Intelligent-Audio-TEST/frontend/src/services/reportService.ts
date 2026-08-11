import { sanitizeConclusion } from '../utils/sanitize';
import {
  TASK_STATUS_MAP,
  REPORT_TYPE_MAP
} from '../shared/constants/reportConstants';

// Re-export types and state for consumers of reportService
export type {
  AggregatedMetrics,
  RoundDetail,
  MultiRoundResult,
  Report,
  ComparisonDevice,
  DeviceAPIComparisonItem,
  CaseExecutionItem,
  Task,
  Device,
  APIConfig
} from './reportTypes';

import {
  comparisonReport,
  comparisonTasks,
  deviceApiComparisonData,
  caseExecutionData,
  devices,
  deviceApiColumns,
  caseExecutionColumns
} from './reportState';

import {
  extractDevicesFromTasks,
  updateComparisonData,
  toggleDeviceSelection
} from './reportComparison';

import {
  formatStatsForCharts,
  getDefaultStats,
  getStatusText,
  getReportTypeLabelFromService,
  updateComparisonReportConclusion,
  resetReportState
} from './reportStats';

import {
  saveReport,
  exportReport,
  publishReport
} from './reportApi';

import { viewTaskReport, batchCompare } from './reportView';
import { parseMultiRoundResult, getMetricValue } from './reportHelpers';

export const reportService = {
  comparisonReport,
  comparisonTasks,
  deviceApiComparisonData,
  caseExecutionData,
  devices,
  deviceApiColumns,
  caseExecutionColumns,
  extractDevicesFromTasks,
  updateComparisonData,
  toggleDeviceSelection,
  updateComparisonReportConclusion,
  getStatusText,
  getReportTypeLabel: getReportTypeLabelFromService,
  saveReport,
  exportReport,
  publishReport,
  viewTaskReport,
  batchCompare,
  formatStatsForCharts,
  getDefaultStats,
  resetReportState,
  sanitizeConclusion,
  parseMultiRoundResult,
  getMetricValue,
  TASK_STATUS_MAP,
  REPORT_TYPE_MAP
};

export default reportService;
