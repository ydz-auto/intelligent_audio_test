import type {
  Report,
  ComparisonDevice,
  DeviceAPIComparisonItem,
  CaseExecutionItem,
  Task,
  Device,
  APIConfig
} from '../shared/types';

export interface AggregatedMetrics {
  [key: string]: any;
}

export interface RoundDetail {
  round: number;
  input?: any;
  output?: any;
  interruption?: any;
  latency?: any;
  wait_time?: any;
  evaluation?: any;
}

export interface MultiRoundResult {
  isMultiRound: boolean;
  rounds: RoundDetail[];
  aggregated: AggregatedMetrics | null;
  totalRounds: number;
}

export type {
  Report,
  ComparisonDevice,
  DeviceAPIComparisonItem,
  CaseExecutionItem,
  Task,
  Device,
  APIConfig
};
