/**
 * 算法多轮结果解析（纯函数，无副作用）
 *
 * 算法结果存在两种轮次字段形态：
 * - round：0 基索引（直接使用）
 * - roundNumber：1 基序号（需减 1 归一化）
 */

/** 单轮明细（字段为算法结果的原始结构，evaluation 内指标名为后端原值） */
export interface RoundDetail {
  round: number;
  input?: any;
  output?: any;
  interruption?: any;
  latency?: any;
  /** 后端原值 wait_time（分钟延迟字段，保留原始 key） */
  wait_time?: any;
  evaluation?: any;
}

/** 聚合指标（指标名为后端原始 key，走宽松索引） */
export interface AggregatedMetrics {
  [key: string]: any;
}

/** 多轮结果解析产物 */
export interface MultiRoundResult {
  isMultiRound: boolean;
  rounds: RoundDetail[];
  aggregated: AggregatedMetrics | null;
  totalRounds: number;
}

/**
 * 解析算法结果为多轮结构
 * 非多轮（无 rounds 数组）时返回 isMultiRound: false 的空结构
 */
export function parseMultiRoundResult(algorithmResult: any): MultiRoundResult {
  const isMultiRound = algorithmResult
    && typeof algorithmResult === 'object'
    && 'rounds' in algorithmResult
    && Array.isArray(algorithmResult.rounds);

  if (!isMultiRound) {
    return { isMultiRound: false, rounds: [], aggregated: null, totalRounds: 0 };
  }

  const rounds: RoundDetail[] = algorithmResult.rounds.map((item: any): RoundDetail => {
    if ('round' in item) {
      return {
        round: item.round,
        input: item.input,
        output: item.output,
        interruption: item.interruption,
        latency: item.latency,
        wait_time: item.wait_time,
        evaluation: item.evaluation
      };
    }
    if ('roundNumber' in item) {
      return {
        round: item.roundNumber - 1,
        input: item.input,
        output: item.output,
        interruption: item.interruption,
        latency: item.latency,
        wait_time: item.wait_time,
        evaluation: item.evaluation
      };
    }
    return { round: 0 };
  });

  return {
    isMultiRound: true,
    rounds,
    aggregated: algorithmResult.aggregated || null,
    // 后端原值 total_rounds 兜底，缺失时用 rounds 长度
    totalRounds: algorithmResult.total_rounds || algorithmResult.rounds.length
  };
}

/**
 * 从算法结果中提取指定指标值
 * 优先级：聚合值 > avg_ 前缀聚合 > 维度列表（后端原值 dimension_name）
 */
export function getMetricValue(
  algorithmResult: any,
  metricName: string,
  dimensions?: any[]
): number | null {
  const parsed = parseMultiRoundResult(algorithmResult);

  if (parsed.isMultiRound && parsed.aggregated) {
    if (parsed.aggregated[metricName] !== undefined) {
      return parsed.aggregated[metricName];
    }
    const avgKey = `avg_${metricName}`;
    if (parsed.aggregated[avgKey] !== undefined) {
      return parsed.aggregated[avgKey];
    }
    return null;
  }

  if (dimensions && Array.isArray(dimensions)) {
    // dimension_name 为后端原始返回字段
    const dim = dimensions.find((d: any) => d.dimension_name === metricName);
    if (dim && dim.value !== undefined) {
      return dim.value;
    }
  }

  return null;
}
