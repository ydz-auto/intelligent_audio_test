import type { MultiRoundResult, RoundDetail, AggregatedMetrics } from './reportTypes';

export function parseMultiRoundResult(algorithmResult: any): MultiRoundResult {
  const isMultiRound = algorithmResult && typeof algorithmResult === 'object' && 'rounds' in algorithmResult && Array.isArray(algorithmResult.rounds);

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
    totalRounds: algorithmResult.total_rounds || algorithmResult.rounds.length
  };
}

export function getMetricValue(algorithmResult: any, metricName: string, dimensions?: any[]): number | null {
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
    const dim = dimensions.find((d: any) => d.dimension_name === metricName);
    if (dim && dim.value !== undefined) {
      return dim.value;
    }
  }

  return null;
}
