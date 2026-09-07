/**
 * TestCaseReportDetail —— 多轮结果编排子模块
 * 职责：多轮算法结果识别、聚合指标计算、轮次展开状态与 LLM 推理提取
 */
import { computed, ref, type ComputedRef } from 'vue';
import { parseMultiRoundResult, type RoundDetail } from '../../../utils/reportMultiRound';
import type {
  LlmEvaluationData,
  ReferenceTextField,
  TestCaseReportDetailProps,
} from './testCaseReportDetail.types';

/** 跨模块依赖上下文（由组合根注入） */
export interface MultiRoundContext {
  /** 动态参考文本字段（来自 execution 子模块） */
  referenceTextFields: ComputedRef<ReferenceTextField[]>
}

/**
 * 多轮结果编排
 */
export function useTestCaseReportDetailMultiRound(props: TestCaseReportDetailProps, ctx: MultiRoundContext) {
  const multiRoundAlgorithmResult = computed(() => {
    const algoResults = props.algorithmResults || [];
    if (algoResults.length === 0) return null;
    const first = algoResults[0];
    if (first && parseMultiRoundResult(first).isMultiRound) return first;
    for (const item of algoResults) {
      if (item?.value && typeof item.value === 'object' && parseMultiRoundResult(item.value).isMultiRound) return item.value;
    }
    return null;
  });

  const isMultiRound = computed(() => multiRoundAlgorithmResult.value !== null);

  const multiRoundData = computed(() => {
    if (!multiRoundAlgorithmResult.value) return { isMultiRound: false, rounds: [], aggregated: null, totalRounds: 0 };
    return parseMultiRoundResult(multiRoundAlgorithmResult.value);
  });

  const aggregatedMetrics = computed(() => {
    if (!multiRoundData.value.isMultiRound) return null;
    if (multiRoundData.value.aggregated) return multiRoundData.value.aggregated;
    const rounds = multiRoundData.value.rounds;
    if (!rounds || rounds.length === 0) return null;
    // rounds 已由 parseMultiRoundResult 归一化，评估数据统一在 evaluation 字段
    const evals = rounds.map(r => r.evaluation).filter(Boolean);
    // 兜底聚合结果的 key 保持与后端 aggregated 原始结构一致（snake_case），供 metricLabel 映射展示
    const result: Record<string, number> = {};
    if (evals.length > 0) {
      const werSum = evals.reduce((s, e) => s + (e.wer || 0), 0);
      result.avg_wer = werSum / evals.length;
      const llmSum = evals.reduce((s, e) => s + (e.llm_judge || 0), 0);
      if (llmSum > 0) result.avg_llm_judge = llmSum / evals.length;
    }
    const latencySum = rounds.reduce((s, r) => s + (r.latency || 0), 0);
    result.avg_latency = latencySum / rounds.length;
    const interruptionCount = rounds.filter(r => r.interruption?.detected).length;
    if (interruptionCount > 0) result.interruption_count = interruptionCount;
    return result;
  });

  const expandedRounds = ref<Record<string, boolean>>({});

  const toggleRound = (idx: string | number) => {
    expandedRounds.value[idx] = !expandedRounds.value[idx];
  };

  const metricLabel = (key: string) => {
    // key 为后端协议原值（aggregated 指标名 / evaluation 维度名），按协议值映射中文标签
    const labels: Record<string, string> = {
      avg_wer: '平均 WER',
      avg_latency: '平均延迟',
      avg_llm_judge: '平均 LLM 评分',
      interruption_count: '打断次数',
      total_latency: '总延迟',
      wer: 'WER',
      llm_judge: 'LLM 评分',
      latency: '延迟',
    };
    return labels[key] || key;
  };

  const roundEvalData = (round: RoundDetail) => {
    // rounds 已归一化：评估数据统一在 evaluation 字段（round_evaluation 为旧格式兼容，不再使用）
    return round.evaluation || null;
  };

  const hasRoundEvaluation = (round: RoundDetail) => {
    const evalData = roundEvalData(round);
    return !!evalData && typeof evalData === 'object' && Object.keys(evalData).length > 0;
  };

  const formatAggregatedValue = (value: number | string | null | undefined) => {
    if (value === null || value === undefined) return '—';
    const num = Number(value);
    if (isNaN(num)) return String(value);
    return num.toFixed(2);
  };

  const getReferenceTextForRound = (idx: number) => {
    const fields = ctx.referenceTextFields.value;
    if (fields.length > 0) return fields[0].text;
    return '';
  };

  const extractLlmReasoning = (evaluation: LlmEvaluationData | null | undefined) => {
    // raw_response 为后端协议字段名（evaluation 内指标名为后端原值，见 reportMultiRound.RoundDetail），按原结构读取
    if (!evaluation) return '';
    if (evaluation.reasoning) return evaluation.reasoning;
    if (evaluation.raw_response) {
      try {
        const parsed = typeof evaluation.raw_response === 'string' ? JSON.parse(evaluation.raw_response) : evaluation.raw_response;
        return parsed.reasoning || parsed.analysis || '';
      } catch (_e) { return ''; }
    }
    return '';
  };

  return {
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
  };
}
