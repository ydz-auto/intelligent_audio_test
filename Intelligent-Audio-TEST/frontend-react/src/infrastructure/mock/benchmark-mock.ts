/**
 * Benchmark 排行页 mock 常量（红线④：数据一律 mock，不接真实后端）。
 * 字段形态对照 report_service ReadModel（benchmark_models.py BenchmarkRanking
 * 实测字段）+ api_gateway/schemas/benchmark.py——**snake_case DTO 形态**，
 * 由 infrastructure/adapters/benchmarkAdapter.ts 唯一转换为 camelCase Domain，
 * 接线时字段不返工（14_benchmark排行.md §9）。
 */
import type {
  BenchmarkCategory,
  BenchmarkDeviceType,
  BenchmarkDirection,
  BenchmarkSource,
  BenchmarkSubjectType,
} from '@/domain/models/benchmark'

/** 排行 DTO 行（后端 benchmark_rankings ReadModel 返回形态） */
export interface BenchmarkRankingDto {
  id: number
  source: BenchmarkSource
  category: BenchmarkCategory
  metric_code: string
  metric_name: string
  unit: string
  direction: BenchmarkDirection
  rank: number
  total: number
  percentile: number | null
  score100: number | null
  subject_name: string
  subject_type: BenchmarkSubjectType
  device_type: BenchmarkDeviceType | null
  benchmark_suite: string
  scenario_key: string
  metric_value: number
  gap_best: number | null
  gap_median: number | null
  delta_external: number | null
  published_task_id: number | null
  published_task_version: number | null
  report_id: number | null
  baseline_id: number | null
  computed_at: string
}

/** 指标映射 DTO（GET /metric-mappings 返回形态） */
export interface BenchmarkMetricMappingDto {
  id: number
  dimension_name: string
  metric_code: string
  metric_name: string
  unit: string
  direction: BenchmarkDirection
  scenario_tags: string[]
  active: boolean
}

/** INT-297 列表信封（单页全量：page=1, pages=1） */
export interface BenchmarkEnvelope<T> {
  success: boolean
  message: string
  data: { items: T[]; total: number; page: number; per_page: number; pages: number } | null
  code: number
}

/** 计算时刻（全部组共用一次重算，计算于同一时间） */
export const MOCK_RANKING_COMPUTED_AT = '2026-10-16T09:20:00'

/** GET /api/v1/benchmarks/ranking 排行行 mock（双轨：platform_test + external_import） */
export const MOCK_BENCHMARK_RANKING_ROWS: BenchmarkRankingDto[] = [
  // ---- ASR 语音识别 · WER 字错率（%）· 越低越好 · 场景「通用」----
  {
    id: 1001, source: 'platform_test', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 1, total: 10, percentile: 5, score100: 100,
    subject_name: '远场语音评测模型-旗舰版', subject_type: 'closed_source',
    device_type: 'physical', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 2.4, gap_best: 0, gap_median: -2.5, delta_external: -0.3,
    published_task_id: 1042, published_task_version: 3, report_id: 1201, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 1002, source: 'platform_test', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 2, total: 10, percentile: 15, score100: 96,
    subject_name: '灵犀语音引擎 V3', subject_type: 'closed_source',
    device_type: 'physical', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 3.1, gap_best: 0.7, gap_median: -1.8, delta_external: 0.5,
    published_task_id: 1041, published_task_version: 2, report_id: 1200, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 1003, source: 'platform_test', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 3, total: 10, percentile: 25, score100: 91,
    subject_name: '开源 Whisper-Large-v3', subject_type: 'open_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 3.8, gap_best: 1.4, gap_median: -1.1, delta_external: null,
    published_task_id: 1040, published_task_version: 1, report_id: 1199, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 1004, source: 'platform_test', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 4, total: 10, percentile: 35, score100: 87,
    subject_name: '声学智汇 ASR 增强版', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 4.2, gap_best: 1.8, gap_median: -0.7, delta_external: null,
    published_task_id: 1039, published_task_version: 5, report_id: 1198, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 1005, source: 'external_import', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 5, total: 10, percentile: 45, score100: 82,
    subject_name: 'Deepgram Nova-4', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 4.6, gap_best: 2.2, gap_median: -0.3, delta_external: null,
    published_task_id: null, published_task_version: null, report_id: null, baseline_id: 501,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 1006, source: 'platform_test', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 6, total: 10, percentile: 55, score100: 76,
    subject_name: '讯飞通用识别', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 5.3, gap_best: 2.9, gap_median: 0.4, delta_external: null,
    published_task_id: 1037, published_task_version: 4, report_id: 1197, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 1007, source: 'platform_test', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 7, total: 10, percentile: 65, score100: 70,
    subject_name: '云知声新一代 ASR', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 5.9, gap_best: 3.5, gap_median: 1.0, delta_external: -1.2,
    published_task_id: 1035, published_task_version: 2, report_id: 1195, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 1008, source: 'platform_test', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 8, total: 10, percentile: 75, score100: 62,
    subject_name: '流式低时延识别引擎', subject_type: 'closed_source',
    device_type: 'websocket_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 6.8, gap_best: 4.4, gap_median: 1.9, delta_external: null,
    published_task_id: 1034, published_task_version: 1, report_id: 1194, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 1009, source: 'external_import', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 9, total: 10, percentile: 85, score100: 54,
    subject_name: 'Google Speech-to-Text v2', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 7.5, gap_best: 5.1, gap_median: 2.6, delta_external: null,
    published_task_id: null, published_task_version: null, report_id: null, baseline_id: 502,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 1010, source: 'platform_test', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 10, total: 10, percentile: 95, score100: 41,
    subject_name: '开源 Whisper-small', subject_type: 'open_source',
    device_type: 'physical', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 9.1, gap_best: 6.7, gap_median: 4.2, delta_external: null,
    published_task_id: 1032, published_task_version: 3, report_id: 1192, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },

  // ---- ASR · WER 字错率（%）· 场景「噪声」----
  {
    id: 1011, source: 'platform_test', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 1, total: 6, percentile: 8, score100: 100,
    subject_name: '远场语音评测模型-旗舰版', subject_type: 'closed_source',
    device_type: 'physical', benchmark_suite: 'robustness', scenario_key: '噪声',
    metric_value: 4.9, gap_best: 0, gap_median: -1.4, delta_external: null,
    published_task_id: 1042, published_task_version: 3, report_id: 1201, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 1012, source: 'platform_test', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 2, total: 6, percentile: 25, score100: 92,
    subject_name: '灵犀语音引擎 V3', subject_type: 'closed_source',
    device_type: 'physical', benchmark_suite: 'robustness', scenario_key: '噪声',
    metric_value: 6.3, gap_best: 1.4, gap_median: 0, delta_external: null,
    published_task_id: 1041, published_task_version: 2, report_id: 1200, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 1013, source: 'platform_test', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 3, total: 6, percentile: 42, score100: 85,
    subject_name: '开源 Whisper-Large-v3', subject_type: 'open_source',
    device_type: 'http_api', benchmark_suite: 'robustness', scenario_key: '噪声',
    metric_value: 7.2, gap_best: 2.3, gap_median: 0.9, delta_external: null,
    published_task_id: 1040, published_task_version: 1, report_id: 1199, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 1014, source: 'platform_test', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 4, total: 6, percentile: 58, score100: 78,
    subject_name: '声学智汇 ASR 增强版', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'robustness', scenario_key: '噪声',
    metric_value: 8.1, gap_best: 3.2, gap_median: 1.8, delta_external: null,
    published_task_id: 1039, published_task_version: 5, report_id: 1198, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 1015, source: 'platform_test', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 5, total: 6, percentile: 75, score100: 66,
    subject_name: '讯飞通用识别', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'robustness', scenario_key: '噪声',
    metric_value: 9.6, gap_best: 4.7, gap_median: 3.3, delta_external: null,
    published_task_id: 1037, published_task_version: 4, report_id: 1197, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 1016, source: 'platform_test', category: 'asr',
    metric_code: 'wer', metric_name: '字错率', unit: '%', direction: 'lower_is_better',
    rank: 6, total: 6, percentile: 92, score100: 50,
    subject_name: '流式低时延识别引擎', subject_type: 'closed_source',
    device_type: 'websocket_api', benchmark_suite: 'robustness', scenario_key: '噪声',
    metric_value: 11.4, gap_best: 6.5, gap_median: 5.1, delta_external: null,
    published_task_id: 1034, published_task_version: 1, report_id: 1194, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },

  // ---- 语音对话 voice_llm · 末字延迟 TTLW（ms）· 越低越好 · 场景「通用」----
  {
    id: 2001, source: 'platform_test', category: 'voice_llm',
    metric_code: 'ttlw', metric_name: '末字延迟', unit: 'ms', direction: 'lower_is_better',
    rank: 1, total: 6, percentile: 8, score100: 100,
    subject_name: '对话大模型-低时延版', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 320, gap_best: 0, gap_median: -95, delta_external: -40,
    published_task_id: 1036, published_task_version: 2, report_id: 1196, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 2002, source: 'platform_test', category: 'voice_llm',
    metric_code: 'ttlw', metric_name: '末字延迟', unit: 'ms', direction: 'lower_is_better',
    rank: 2, total: 6, percentile: 25, score100: 90,
    subject_name: '语音对话助手-流式版', subject_type: 'closed_source',
    device_type: 'websocket_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 415, gap_best: 95, gap_median: 0, delta_external: 60,
    published_task_id: 1033, published_task_version: 4, report_id: 1193, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 2003, source: 'platform_test', category: 'voice_llm',
    metric_code: 'ttlw', metric_name: '末字延迟', unit: 'ms', direction: 'lower_is_better',
    rank: 3, total: 6, percentile: 42, score100: 81,
    subject_name: '开源 Qwen-Audio 对话', subject_type: 'open_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 512, gap_best: 192, gap_median: 97, delta_external: null,
    published_task_id: 1031, published_task_version: 1, report_id: 1191, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 2004, source: 'external_import', category: 'voice_llm',
    metric_code: 'ttlw', metric_name: '末字延迟', unit: 'ms', direction: 'lower_is_better',
    rank: 4, total: 6, percentile: 58, score100: 72,
    subject_name: 'GPT-4o 语音对话', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 604, gap_best: 284, gap_median: 189, delta_external: null,
    published_task_id: null, published_task_version: null, report_id: null, baseline_id: 503,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 2005, source: 'platform_test', category: 'voice_llm',
    metric_code: 'ttlw', metric_name: '末字延迟', unit: 'ms', direction: 'lower_is_better',
    rank: 5, total: 6, percentile: 75, score100: 61,
    subject_name: '多轮对话引擎-通用', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 708, gap_best: 388, gap_median: 293, delta_external: null,
    published_task_id: 1030, published_task_version: 2, report_id: 1190, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 2006, source: 'platform_test', category: 'voice_llm',
    metric_code: 'ttlw', metric_name: '末字延迟', unit: 'ms', direction: 'lower_is_better',
    rank: 6, total: 6, percentile: 92, score100: 48,
    subject_name: '端侧语音助手-离线版', subject_type: 'closed_source',
    device_type: 'physical', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 860, gap_best: 540, gap_median: 445, delta_external: null,
    published_task_id: 1029, published_task_version: 3, report_id: 1189, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },

  // ---- 语音合成 TTS · 自然度 MOS 分 · 越高越好 · 场景「通用」----
  {
    id: 3001, source: 'platform_test', category: 'tts',
    metric_code: 'mos', metric_name: '自然度 MOS 分', unit: '分', direction: 'higher_is_better',
    rank: 1, total: 5, percentile: 10, score100: 100,
    subject_name: '音色克隆合成-旗舰版', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 4.6, gap_best: 0, gap_median: 0.4, delta_external: 0.2,
    published_task_id: 1028, published_task_version: 6, report_id: 1188, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 3002, source: 'platform_test', category: 'tts',
    metric_code: 'mos', metric_name: '自然度 MOS 分', unit: '分', direction: 'higher_is_better',
    rank: 2, total: 5, percentile: 30, score100: 93,
    subject_name: '多音色 TTS 引擎', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 4.3, gap_best: 0.3, gap_median: 0.1, delta_external: null,
    published_task_id: 1027, published_task_version: 2, report_id: 1187, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 3003, source: 'external_import', category: 'tts',
    metric_code: 'mos', metric_name: '自然度 MOS 分', unit: '分', direction: 'higher_is_better',
    rank: 3, total: 5, percentile: 50, score100: 86,
    subject_name: 'ElevenLabs v2', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 4.1, gap_best: 0.5, gap_median: -0.1, delta_external: null,
    published_task_id: null, published_task_version: null, report_id: null, baseline_id: 504,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 3004, source: 'platform_test', category: 'tts',
    metric_code: 'mos', metric_name: '自然度 MOS 分', unit: '分', direction: 'higher_is_better',
    rank: 4, total: 5, percentile: 70, score100: 79,
    subject_name: '开源 ChatTTS', subject_type: 'open_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 3.8, gap_best: 0.8, gap_median: -0.4, delta_external: null,
    published_task_id: 1026, published_task_version: 1, report_id: 1186, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 3005, source: 'platform_test', category: 'tts',
    metric_code: 'mos', metric_name: '自然度 MOS 分', unit: '分', direction: 'higher_is_better',
    rank: 5, total: 5, percentile: 90, score100: 68,
    subject_name: '基础女声合成', subject_type: 'closed_source',
    device_type: 'physical', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 3.2, gap_best: 1.4, gap_median: -1.0, delta_external: null,
    published_task_id: 1025, published_task_version: 3, report_id: 1185, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },

  // ---- 翻译 translation · BLEU 分数 · 越高越好 · 场景「通用」----
  {
    id: 4001, source: 'platform_test', category: 'translation',
    metric_code: 'bleu', metric_name: 'BLEU 分数', unit: '分', direction: 'higher_is_better',
    rank: 1, total: 4, percentile: 12, score100: 100,
    subject_name: '实时翻译引擎-增强版', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 42.6, gap_best: 0, gap_median: 3.1, delta_external: 1.8,
    published_task_id: 1024, published_task_version: 2, report_id: 1184, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 4002, source: 'external_import', category: 'translation',
    metric_code: 'bleu', metric_name: 'BLEU 分数', unit: '分', direction: 'higher_is_better',
    rank: 2, total: 4, percentile: 38, score100: 91,
    subject_name: 'DeepL API', subject_type: 'closed_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 40.2, gap_best: 2.4, gap_median: 0.7, delta_external: null,
    published_task_id: null, published_task_version: null, report_id: null, baseline_id: 505,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 4003, source: 'platform_test', category: 'translation',
    metric_code: 'bleu', metric_name: 'BLEU 分数', unit: '分', direction: 'higher_is_better',
    rank: 3, total: 4, percentile: 63, score100: 82,
    subject_name: '开源 NLLB-200', subject_type: 'open_source',
    device_type: 'http_api', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 38.1, gap_best: 4.5, gap_median: -1.4, delta_external: null,
    published_task_id: 1023, published_task_version: 1, report_id: 1183, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
  {
    id: 4004, source: 'platform_test', category: 'translation',
    metric_code: 'bleu', metric_name: 'BLEU 分数', unit: '分', direction: 'higher_is_better',
    rank: 4, total: 4, percentile: 88, score100: 70,
    subject_name: '基础翻译服务', subject_type: 'closed_source',
    device_type: 'physical', benchmark_suite: 'general', scenario_key: '通用',
    metric_value: 34.5, gap_best: 8.1, gap_median: -2.2, delta_external: null,
    published_task_id: 1022, published_task_version: 5, report_id: 1182, baseline_id: null,
    computed_at: MOCK_RANKING_COMPUTED_AT,
  },
]

/** GET /api/v1/benchmarks/ranking 排行查询 mock（envelope：INT-297 单页全量） */
export const MOCK_BENCHMARK_RANKING_RESPONSE: BenchmarkEnvelope<BenchmarkRankingDto> = {
  success: true,
  message: 'ok',
  data: {
    items: MOCK_BENCHMARK_RANKING_ROWS,
    total: MOCK_BENCHMARK_RANKING_ROWS.length,
    page: 1,
    per_page: MOCK_BENCHMARK_RANKING_ROWS.length || 1,
    pages: 1,
  },
  code: 0,
}

/** GET /api/v1/benchmarks/ranking/subjects 被测主体去重清单 mock（后端返回纯字符串数组） */
export const MOCK_BENCHMARK_SUBJECTS: string[] = [
  '远场语音评测模型-旗舰版',
  '灵犀语音引擎 V3',
  '开源 Whisper-Large-v3',
  '声学智汇 ASR 增强版',
  'Deepgram Nova-4',
  '讯飞通用识别',
  '云知声新一代 ASR',
  '流式低时延识别引擎',
  'Google Speech-to-Text v2',
  '开源 Whisper-small',
  '对话大模型-低时延版',
  '语音对话助手-流式版',
  '开源 Qwen-Audio 对话',
  'GPT-4o 语音对话',
  '多轮对话引擎-通用',
  '端侧语音助手-离线版',
  '音色克隆合成-旗舰版',
  '多音色 TTS 引擎',
  'ElevenLabs v2',
  '开源 ChatTTS',
  '基础女声合成',
  '实时翻译引擎-增强版',
  'DeepL API',
  '开源 NLLB-200',
  '基础翻译服务',
]

/** 排行页算法卡 mock（GET /algorithm/definitions 形态 + 参数摘要字段——
 * 照 _algorithm_definition_schemas.py 实测：device_params/api_params/case_params
 * Optional[List[Dict]]，长度 0/缺失时参数摘要行隐藏）。 */
export interface MockRankingAlgorithmDefinition {
  type: string
  name: string
  group_name?: string
  category?: string
  description: string
  status?: string
  icon?: string
  device_params?: Array<Record<string, unknown>>
  api_params?: Array<Record<string, unknown>>
  case_params?: Array<Record<string, unknown>>
}

/** 排行页算法卡片网格数据（页内独立展示；选中态/参数摘要/离线置灰演示完整） */
export const MOCK_RANKING_ALGORITHM_DEFINITIONS: MockRankingAlgorithmDefinition[] = [
  {
    type: 'asr-v3',
    name: '通用识别引擎',
    group_name: '语音识别',
    category: 'asr',
    description: '端到端语音识别基线模型，覆盖远场/近场/噪声三类场景。',
    status: 'online',
    icon: 'audio-waveform',
    device_params: [
      { key: 'sample_rate', value: 16000 },
      { key: 'channels', value: 1 },
    ],
    api_params: [{ key: 'endpoint', value: '/v1/asr/recognize' }],
    case_params: [{ key: 'language', value: 'zh-CN' }],
  },
  {
    type: 'asr-stream',
    name: '流式识别引擎',
    group_name: '语音识别',
    category: 'asr',
    description: '低延迟流式转写引擎，适合实时字幕与对话场景。',
    status: 'online',
    icon: 'activity',
    device_params: [{ key: 'sample_rate', value: 16000 }],
    api_params: [
      { key: 'endpoint', value: '/v1/asr/stream' },
      { key: 'protocol', value: 'websocket' },
    ],
    case_params: [],
  },
  {
    type: 'eval-ensemble',
    name: '多维评估集成',
    group_name: '评估算法',
    category: 'eval',
    description: '多维度指标集成评估算法，输出 WER/LLM 评分/延迟等综合结论。',
    status: 'online',
    icon: 'gauge',
    device_params: [],
    api_params: [],
    case_params: [],
  },
  {
    type: 'legacy-gmm',
    name: '旧版 GMM 识别',
    group_name: '语音识别',
    category: 'asr',
    description: '早期高斯混合模型识别方案，已被端到端模型取代，仅供历史对比。',
    status: 'offline',
    icon: 'archive',
    device_params: [{ key: 'sample_rate', value: 8000 }],
    api_params: [],
    case_params: [],
  },
]

/** GET /api/v1/benchmarks/metric-mappings?activeOnly=true 指标映射 mock（指标筛选下拉数据源） */
export const MOCK_BENCHMARK_METRIC_MAPPINGS: BenchmarkMetricMappingDto[] = [
  {
    id: 1, dimension_name: 'WER', metric_code: 'wer', metric_name: '字错率',
    unit: '%', direction: 'lower_is_better', scenario_tags: ['普通话通用', '噪声'], active: true,
  },
  {
    id: 2, dimension_name: 'TTLW', metric_code: 'ttlw', metric_name: '末字延迟',
    unit: 'ms', direction: 'lower_is_better', scenario_tags: ['多轮对话'], active: true,
  },
  {
    id: 3, dimension_name: 'MOS', metric_code: 'mos', metric_name: '自然度 MOS 分',
    unit: '分', direction: 'higher_is_better', scenario_tags: ['TTS'], active: true,
  },
  {
    id: 4, dimension_name: 'BLEU', metric_code: 'bleu', metric_name: 'BLEU 分数',
    unit: '分', direction: 'higher_is_better', scenario_tags: ['翻译'], active: true,
  },
]
