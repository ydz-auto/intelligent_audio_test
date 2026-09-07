/**
 * TestCaseReportDetail —— 组合根（Composition Root）
 *
 * 原超大 composable 已按职责拆分至同目录 testCaseReportDetail.*.ts：
 * - types      类型定义（输入形状 + 渲染形状 + props 契约）
 * - multiRound 多轮算法结果编排（识别、聚合指标、轮次展开、LLM 推理提取）
 * - fields     动态文本字段（参考文本 / 结果文本 / 维度分组）
 * - metrics    评分指标与对比表格（设备名解析、指标格式化）
 * - round      轮次编排（轮次 Tab、主维度归组表格、执行结果轮次过滤）
 * - timeline   时间轴与音频数据
 * - actions    交互状态与面板控制（维度 tab、文本折叠、JSON 辅助、音频播放器、执行结果判定）
 * 本文件仅负责模块组装与类型再导出，保持原模块路径与全部具名导出不变，消费方零改动。
 */

// ===== 类型再导出（保持原导出面） =====
export type {
  DimensionMetricInput,
  SingleMetricResultInput,
  MetricConfigInput,
  ResourceHeaderInput,
  ReferenceParamData,
  FieldMappingItem,
  ReportFieldMapping,
  AlgorithmResultItem,
  ComparisonMetricEntry,
  ComparisonDeviceData,
  LlmEvaluationData,
  DisplayMetric,
  ReferenceTextField,
  ResultTextField,
  ResultFieldGroup,
  ReportDetailColumn,
  RoundTab,
  GroupedMetricItem,
  GroupedMetricGroup,
  GroupedMetricRow,
  PathAudioItem,
  PlayingAudio,
  TestCaseReportDetailProps,
} from './testCaseReportDetail.types';

import type { TestCaseReportDetailProps } from './testCaseReportDetail.types';
import { useTestCaseReportDetailMultiRound } from './testCaseReportDetail.multiRound';
import { useTestCaseReportDetailTextFields } from './testCaseReportDetail.fields';
import { useTestCaseReportDetailMetrics } from './testCaseReportDetail.metrics';
import { useTestCaseReportDetailRound } from './testCaseReportDetail.round';
import { useTestCaseReportDetailTimeline } from './testCaseReportDetail.timeline';
import { useTestCaseReportDetailActions } from './testCaseReportDetail.actions';

export function useTestCaseReportDetail(props: TestCaseReportDetailProps) {
  // ===== 动态文本字段（fields） =====
  const {
    referenceTextFields,
    resultTextFields,
    subDimToParent,
    groupFieldsByDimension,
    groupedResultTextFields,
    dimResultGroups,
    generalResultGroup,
  } = useTestCaseReportDetailTextFields(props);

  // ===== 多轮结果编排（multiRound） =====
  const {
    isMultiRound,
    multiRoundData,
    aggregatedMetrics,
    expandedRounds,
    toggleRound,
    metricLabel,
    roundEvalData,
    hasRoundEvaluation,
    formatAggregatedValue,
    getReferenceTextForRound,
    extractLlmReasoning,
  } = useTestCaseReportDetailMultiRound(props, { referenceTextFields });

  // ===== 时间轴与音频数据（timeline） =====
  const {
    hasTimelineData,
    hasAudio,
    audioListWithTimeline,
    hasResultAudioData,
  } = useTestCaseReportDetailTimeline(props);

  // ===== 评分指标与对比表格（metrics） =====
  const {
    hasMetrics,
    allMetricNames,
    displayMetrics,
    comparisonTableColumns,
    comparisonTableData,
    singleTableColumns,
    singleTableData,
    formatValue,
    calculateScore,
    getDeviceName,
    getMetricValue,
    getMetricDisplayValue,
  } = useTestCaseReportDetailMetrics(props);

  // ===== 轮次编排（round）：轮次 Tab + 主维度归组 + 执行结果轮次过滤 =====
  const {
    roundTabs,
    activeRoundTab,
    groupedMetricsForCurrentRound,
    currentRoundTableData,
    isMultiRoundFields,
    currentRoundResultTextFields,
    currentRoundReferenceTextFields,
    roundDimResultGroups,
    roundGeneralResultGroup,
  } = useTestCaseReportDetailRound(props, {
    allMetricNames,
    getMetricDisplayValue,
    resultTextFields,
    referenceTextFields,
    subDimToParent,
    groupFieldsByDimension,
  });

  // ===== 交互状态与面板控制（actions） =====
  const {
    hasExecutionResults,
    activeDimTab,
    isJsonString,
    formatJson,
    expandedTexts,
    toggleText,
    showAudioModal,
    currentPlayingAudio,
    openPathAudio,
    closeAudioModal,
  } = useTestCaseReportDetailActions({
    // 轮次感知的维度分组：切换轮次时 tab 越界自动重置
    dimResultGroups: roundDimResultGroups,
    referenceTextFields,
    resultTextFields,
    hasTimelineData,
    hasAudio,
    hasResultAudioData,
  });

  return {
    // 评分指标
    hasMetrics,
    allMetricNames,
    displayMetrics,
    comparisonTableColumns,
    comparisonTableData,
    singleTableColumns,
    singleTableData,
    formatValue,
    calculateScore,
    // 轮次编排（评分指标区 + 执行结果区共享）
    roundTabs,
    activeRoundTab,
    currentRoundTableData,
    isMultiRoundFields,
    currentRoundReferenceTextFields,
    // 多轮结果
    isMultiRound,
    multiRoundData,
    aggregatedMetrics,
    formatAggregatedValue,
    expandedRounds,
    toggleRound,
    getReferenceTextForRound,
    hasRoundEvaluation,
    roundEvalData,
    metricLabel,
    extractLlmReasoning,
    // 执行结果（轮次感知分组覆盖全量分组）
    hasExecutionResults,
    referenceTextFields: currentRoundReferenceTextFields,
    resultTextFields,
    groupedResultTextFields,
    dimResultGroups: roundDimResultGroups,
    generalResultGroup: roundGeneralResultGroup,
    activeDimTab,
    getDeviceName,
    hasTimelineData,
    hasAudio,
    audioListWithTimeline,
    hasResultAudioData,
    isJsonString,
    formatJson,
    expandedTexts,
    toggleText,
    // 音频播放器
    showAudioModal,
    currentPlayingAudio,
    openPathAudio,
    closeAudioModal,
  };
}