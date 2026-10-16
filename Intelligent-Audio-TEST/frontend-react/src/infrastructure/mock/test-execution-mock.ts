/**
 * 测试执行 mock 常量（infrastructure 层；红线④：数据一律 mock，不接真实后端）。
 * DTO 形态对照 api_gateway/schemas 实测（见 dto/ 各文件注释），经 adapters/ 转出
 * domain 模型——后续接线仅替换 infrastructure/api 桩实现，页面与 hook 不返工。
 * 数字口径与任务域/报告域 mock 保持同一世界观（任务 1042、报告 1201 同源）。
 */
import type { AlgorithmOption } from '@/domain/models/algorithm'
import type { ReportDetailData } from '@/domain/models/report'
import type { CaseExecutionDetail, RealtimeFrame } from '@/domain/models/testExecution'
import type { TestCase, EvaluationDimension } from '@/domain/models/testCase'
import { caseDetailFromDto, testCaseFromDto } from '@/infrastructure/adapters/testCaseAdapter'
import { deviceFromDto } from '@/infrastructure/adapters/deviceAdapter'
import { apiConfigFromDto } from '@/infrastructure/adapters/apiConfigAdapter'
import { frameFromDto } from '@/infrastructure/adapters/frameEventAdapter'
import type { DeviceItemDto } from '@/infrastructure/dto/device.dto'
import type { ApiItemDto } from '@/infrastructure/dto/apis.dto'
import type { TestCaseListItemDto, CaseDetailDto } from '@/infrastructure/dto/testcase.dto'
import type { FrameEventDto } from '@/infrastructure/dto/frame.dto'
import type { Device } from '@/domain/models/device'
import type { ApiConfig } from '@/domain/models/apiConfig'

/* ==================== 步骤一：算法 ==================== */

/** 算法选择项（全局 store 同源 MOCK_ALGORITHMS + 分组徽章；group 对照算法配置域分组） */
export interface TestAlgorithmOption extends AlgorithmOption {
  group: string
}

export const MOCK_TEST_ALGORITHMS: TestAlgorithmOption[] = [
  { id: 'asr-v3', name: '通用识别引擎', version: 'v3.2.0', description: '端到端语音识别基线模型', enabled: true, group: '语音识别' },
  { id: 'asr-stream', name: '流式识别引擎', version: 'v2.8.1', description: '低延迟流式转写引擎', enabled: true, group: '语音识别' },
  { id: 'eval-ensemble', name: '多维评估集成', version: 'v1.9.0', description: '多维度指标集成评估算法', enabled: true, group: '评估算法' },
  { id: 'asr-experimental', name: '实验识别引擎', version: 'v0.9.0-beta', description: '实验性模型，仅供内部验证', enabled: false, group: '语音识别' },
]

/* ==================== 步骤二：用例 ==================== */

/** 用例分组 facet（含「未分组」哨兵——空 group_name 落未分组） */
export const MOCK_CASE_GROUPS = [
  { value: 'wakeup', label: '唤醒' },
  { value: 'asr', label: '识别' },
  { value: 'noise', label: '噪声' },
  { value: 'continuity', label: '连续对话' },
]

export const MOCK_CASE_TAGS = ['旗舰回归', '远场', '多方言', '打断', '低信噪比', '连续对话', '音乐场景', '儿童音色']

export const MOCK_EVAL_DIMENSIONS: EvaluationDimension[] = [
  { id: 1, name: '唤醒成功率', type: 'main' },
  { id: 2, name: '误唤醒率', type: 'sub' },
  { id: 3, name: '识别准确率', type: 'main' },
  { id: 4, name: '平均WER', type: 'sub' },
  { id: 5, name: '平均响应时间', type: 'main' },
]

export const MOCK_TESTCASES_DTO: TestCaseListItemDto[] = [
  {
    id: 'c-001',
    name: '远场唤醒 · 3 米距离',
    description: '3 米远场环境下的唤醒词识别，覆盖客厅典型噪声。',
    group_id: 'wakeup',
    group_name: '唤醒',
    type: 'e2e',
    tags: ['远场', '旗舰回归'],
    algorithm_type: 'asr_streaming',
    total_duration: 18,
    updated_at: '2026-10-14T09:20:00',
    config: { rounds: [{ round_number: 1 }], dimensions: [] },
  },
  {
    id: 'c-002',
    name: '连续对话 · 多轮上下文保持',
    description: '连续两轮对话的上下文保持与指代消解验证。',
    group_id: 'continuity',
    group_name: '连续对话',
    type: 'e2e',
    tags: ['连续对话'],
    algorithm_type: 'asr_streaming',
    total_duration: 42,
    updated_at: '2026-10-14T11:05:00',
    config: { rounds: [{ round_number: 1 }, { round_number: 2 }], dimensions: [] },
  },
  {
    id: 'c-003',
    name: '音乐场景误唤醒抑制',
    description: '音乐播放场景下的误唤醒率验证，声压 70dB。',
    group_id: 'noise',
    group_name: '噪声',
    type: 'e2e',
    tags: ['音乐场景', '低信噪比'],
    algorithm_type: 'asr_streaming',
    total_duration: 25,
    updated_at: '2026-10-13T16:40:00',
    config: { rounds: [{ round_number: 1 }], dimensions: [] },
  },
  {
    id: 'c-004',
    name: '多方言识别抽样',
    description: '川渝/粤语/上海话三地方言抽样识别准确率。',
    group_id: 'asr',
    group_name: '识别',
    type: 'e2e',
    tags: ['多方言'],
    algorithm_type: 'asr_streaming',
    total_duration: 30,
    updated_at: '2026-10-13T14:12:00',
    config: { rounds: [{ round_number: 1 }], dimensions: [] },
  },
  {
    id: 'c-005',
    name: '打断恢复时延',
    description: '唤醒后立即打断场景的恢复时延与应答质量。',
    group_id: 'wakeup',
    group_name: '唤醒',
    type: 'e2e',
    tags: ['打断', '旗舰回归'],
    algorithm_type: 'asr_streaming',
    total_duration: 12,
    updated_at: '2026-10-12T10:30:00',
    config: { rounds: [{ round_number: 1 }, { round_number: 2 }], dimensions: [] },
  },
  {
    id: 'a-001',
    name: 'ASR 流式转写正确性',
    description: 'HTTP 流式转写接口的文本正确性与分段稳定性。',
    group_id: 'asr',
    group_name: '识别',
    type: 'api',
    tags: ['API', '流式'],
    algorithm_type: 'asr_streaming',
    total_duration: 20,
    updated_at: '2026-10-14T13:00:00',
    config: { rounds: [{ round_number: 1 }], dimensions: [] },
  },
  {
    id: 'a-002',
    name: '唤醒检测接口并发',
    description: '唤醒检测 HTTP 接口的并发处理与超时表现。',
    group_id: 'wakeup',
    group_name: '唤醒',
    type: 'api',
    tags: ['API', '并发'],
    algorithm_type: 'asr_streaming',
    total_duration: 15,
    updated_at: '2026-10-13T09:50:00',
    config: { rounds: [{ round_number: 1 }], dimensions: [] },
  },
  {
    id: 'a-003',
    name: 'TTS 音质 MOS 评估',
    description: 'TTS 合成音质 MOS 评分抽样（对齐 eval-ensemble 评估维度）。',
    group_id: 'asr',
    group_name: '识别',
    type: 'api',
    tags: ['TTS'],
    algorithm_type: 'tts_eval',
    total_duration: 35,
    updated_at: '2026-10-12T15:22:00',
    config: { rounds: [{ round_number: 1 }], dimensions: [] },
  },
]

/** 全量圈定（POST /testcases/ids）：当前筛选条件下的全部用例 id 集 */
export const MOCK_CASE_IDS: string[] = MOCK_TESTCASES_DTO.map((c) => c.id)

export const MOCK_TESTCASES: TestCase[] = MOCK_TESTCASES_DTO.map(testCaseFromDto)

/* ==================== 步骤三（E2E）：设备（混跑三类型） ==================== */

export const MOCK_DEVICES_DTO: DeviceItemDto[] = [
  {
    id: 1, name: '音箱-客厅位', model: '旗舰 S1', description: '客厅远场位，12 米半径',
    type: 'physical', system: 'harmony', system_version: '3.2.1',
    serial_number: 'SN-A001-8821', ip: '192.168.1.21', status: 'online',
    last_online_at: '2026-10-15T08:40:00', supported_algorithms: ['asr_streaming', 'wakeword_detect'], connection_type: 'usb',
  },
  {
    id: 2, name: '音箱-卧室位', model: '旗舰 S1', description: '卧室近场位',
    type: 'physical', system: 'android', system_version: '12',
    serial_number: 'SN-A001-8832', ip: '192.168.1.22', status: 'online',
    last_online_at: '2026-10-15T08:42:00', supported_algorithms: ['asr_streaming', 'wakeword_detect'], connection_type: 'wifi',
  },
  {
    id: 3, name: '音箱-入门-03', model: '入门 L2', description: '入门机型，低配算力',
    type: 'physical', system: 'android', system_version: '11',
    serial_number: 'SN-B002-7715', ip: '192.168.1.23', status: 'offline',
    last_online_at: '2026-10-14T19:10:00', supported_algorithms: ['asr_streaming'], connection_type: 'wifi',
  },
  {
    id: 4, name: 'ASR HTTP 网关', model: 'HTTP API', description: 'HTTP 协议转写网关（APISessionExecutor 承载）',
    type: 'http_api', system: null, system_version: null,
    serial_number: null, ip: '10.0.8.5', status: 'online',
    last_online_at: '2026-10-15T08:39:00', supported_algorithms: ['asr_streaming', 'wakeword_detect'], connection_type: 'network',
  },
  {
    id: 5, name: 'Realtime WS 网关', model: 'WebSocket API', description: '实时流式 WS 通道（RealtimeSessionExecutor 承载）',
    type: 'websocket_api', system: null, system_version: null,
    serial_number: null, ip: '10.0.8.6', status: 'online',
    last_online_at: '2026-10-15T08:38:00', supported_algorithms: ['asr_streaming'], connection_type: 'network',
  },
  {
    id: 6, name: '车载中控-主驾', model: 'Car Dock D1', description: '车载环境，噪声抑制验证',
    type: 'physical', system: 'android', system_version: '13',
    serial_number: 'SN-C003-1107', ip: '192.168.2.31', status: 'offline',
    last_online_at: '2026-10-14T18:02:00', supported_algorithms: ['wakeword_detect'], connection_type: 'usb',
  },
]

export const MOCK_DEVICES: Device[] = MOCK_DEVICES_DTO.map(deviceFromDto)

/* ==================== 步骤三（API）：被测 API ==================== */

export const MOCK_APIS_DTO: ApiItemDto[] = [
  {
    id: 11, name: 'ASR HTTP API', vendor: '内部 ASR 组',
    api_url: 'https://api.audio.test/v1/asr', description: 'HTTP 流式转写服务',
    status: 'online', meta: {}, algorithm_type: 'asr_streaming',
    default_max_process: 32, default_max_timeout: 60, default_max_audio_duration: 120,
    health_score: 92, output_types: ['text'], device_type: 'http_api', adapter_class: null,
    audio_config: null, rms_spl_mapping_id: null, created_at: '2026-09-01T10:00:00', updated_at: '2026-10-10T10:00:00',
    endpoints: [
      { id: 'ep-11-1', endpoint: '/v1/asr/stream', name: '流式转写', max_process: 32, max_timeout: 60, max_audio_duration: 120, status: 'online', health_score: 92, priority: 1, description: null },
      { id: 'ep-11-2', endpoint: '/v1/asr/recognize', name: '一句话识别', max_process: 16, max_timeout: 30, max_audio_duration: 60, status: 'online', health_score: 90, priority: 2, description: null },
    ],
  },
  {
    id: 12, name: 'Wakeword HTTP API', vendor: '内部唤醒组',
    api_url: 'https://api.audio.test/v1/wakeword', description: '唤醒词检测服务',
    status: 'offline', meta: {}, algorithm_type: 'asr_streaming',
    default_max_process: 16, default_max_timeout: 30, default_max_audio_duration: 60,
    health_score: 0, output_types: ['text'], device_type: 'http_api', adapter_class: null,
    audio_config: null, rms_spl_mapping_id: null, created_at: '2026-09-05T09:00:00', updated_at: '2026-10-08T09:00:00',
    endpoints: [
      { id: 'ep-12-1', endpoint: '/v1/wakeword/detect', name: '唤醒检测', max_process: 16, max_timeout: 30, max_audio_duration: 60, status: 'offline', health_score: null, priority: 1, description: null },
    ],
  },
  {
    id: 13, name: 'TTS HTTP API', vendor: 'TTS 组',
    api_url: 'https://api.audio.test/v1/tts', description: '文本转语音合成服务',
    status: 'online', meta: {}, algorithm_type: 'tts_eval',
    default_max_process: 8, default_max_timeout: 60, default_max_audio_duration: 300,
    health_score: 95, output_types: ['audio'], device_type: 'http_api', adapter_class: null,
    audio_config: null, rms_spl_mapping_id: null, created_at: '2026-09-10T08:00:00', updated_at: '2026-10-09T08:00:00',
    endpoints: [
      { id: 'ep-13-1', endpoint: '/v1/tts/synthesize', name: '合成', max_process: 8, max_timeout: 60, max_audio_duration: 300, status: 'online', health_score: 95, priority: 1, description: null },
    ],
  },
]

export const MOCK_APIS: ApiConfig[] = MOCK_APIS_DTO.map(apiConfigFromDto)

/* ==================== 步骤四：Realtime frame 增量（websocket_api 设备时启用） ==================== */

export const MOCK_FRAMES_DTO: FrameEventDto[] = [
  { case_id: 'c-001', event_type: 'user_speech_started', data: { round: 1 }, ts: '2026-10-15 09:10:01.214' },
  { case_id: 'c-001', event_type: 'ai_text_delta', data: { text_delta: '好的，', round: 1 }, ts: '2026-10-15 09:10:03.421' },
  { case_id: 'c-001', event_type: 'ai_text_delta', data: { text_delta: '正在为你播放', round: 1 }, ts: '2026-10-15 09:10:04.108' },
  { case_id: 'c-001', event_type: 'ai_audio_delta', data: { audio_progress: 38, round: 1 }, ts: '2026-10-15 09:10:05.200' },
  { case_id: 'c-001', event_type: 'ai_audio_delta', data: { audio_progress: 100, round: 1 }, ts: '2026-10-15 09:10:08.917' },
  { case_id: 'c-001', event_type: 'round_completed', data: { round: 1 }, ts: '2026-10-15 09:10:09.031' },
]

export const MOCK_FRAMES: RealtimeFrame[] = MOCK_FRAMES_DTO.map(frameFromDto)

/* ==================== 用例详情弹窗（§5.2）：多轮指标对比 + 日志分页 ==================== */

const MOCK_CASE_DETAIL_DTO: CaseDetailDto = {
  test_case_id: 'c-001',
  task_id: 1042,
  name: '远场唤醒 · 3 米距离',
  execution_status: 'completed',
  evaluation_status: 'completed',
  duration: 18.4,
  score: 94.2,
  devices: [
    {
      device_id: 1, device_name: '音箱-客厅位', status: 'pass', duration: 18.4, score: 94.2,
      metrics: [
        { dimension: '唤醒成功率', round: 1, value: '96.5' },
        { dimension: '唤醒成功率', round: 2, value: '95.8' },
        { dimension: '唤醒成功率', round: null, value: '96.1' },
        { dimension: '误唤醒率', round: null, value: '0.4' },
        { dimension: '平均响应时间', round: null, value: '412' },
      ],
      asr_reference: '小雅小雅，明天天气怎么样？',
      translation_reference: '小雅小雅，明天天气怎么样？',
      audio_results: [
        { audio_name: 'round-1-唤醒.mp3', duration: 3.2 },
        { audio_name: 'round-2-唤醒.mp3', duration: 3.1 },
      ],
    },
    {
      device_id: 2, device_name: '音箱-卧室位', status: 'pass', duration: 18.1, score: 93.1,
      metrics: [
        { dimension: '唤醒成功率', round: 1, value: '95.2' },
        { dimension: '唤醒成功率', round: 2, value: '94.6' },
        { dimension: '唤醒成功率', round: null, value: '94.9' },
        { dimension: '误唤醒率', round: null, value: '0.6' },
        { dimension: '平均响应时间', round: null, value: '428' },
      ],
      asr_reference: '小雅小雅，今天有什么新闻？',
      translation_reference: null,
      audio_results: [
        { audio_name: 'round-1-唤醒.mp3', duration: 3.0 },
        { audio_name: 'round-2-唤醒.mp3', duration: 3.3 },
      ],
    },
  ],
}

/** 用例详情 mock（经 DTO→Domain 适配产出，§5.2） */
export const MOCK_CASE_EXECUTION_DETAIL: CaseExecutionDetail = caseDetailFromDto(MOCK_CASE_DETAIL_DTO)

/* ==================== 步骤五：报告装配（INT-439 嵌入式，任务报告 mock） ==================== */

/** 报告详情 mock（对齐当前流程生成的任务报告；复用 15_报告域 domain 模型） */
export const MOCK_FLOW_REPORT: ReportDetailData = {
  id: 1205,
  name: '端到端回归 · 智能音箱第 4 轮报告',
  type: 'task',
  task_id: 1042,
  task_type: 'e2e',
  task_name: '端到端回归 · 智能音箱第 4 轮',
  algorithm_type: 'asr_streaming',
  description: '覆盖唤醒/识别/连续对话场景共 48 条用例，混跑真机 + HTTP API + Realtime WS 设备。',
  status: 'draft',
  analysis:
    '本轮执行 48 条用例，整体通过率 95.8%。远场唤醒成功率稳定在 96% 以上，音乐场景误唤醒率降至 0.3%。Realtime WS 通道平均首包时延 214ms，音频进度推送稳定。\n\n建议下一步针对低信噪比组合场景（噪声 + 远场）重点调优唤醒阈值。',
  summary: {
    total_cases: 48,
    completed_cases: 48,
    failed_cases: 2,
    resources: [],
    resource_headers: [],
    raw_data: [],
    metric_data: [],
    tag_metric_data: [],
    case_categories: [],
    all_case_tags: [],
    all_tags: [
      { tag_name: '旗舰回归' },
      { tag_name: '远场' },
      { tag_name: '多方言' },
      { tag_name: '打断' },
    ],
    all_metrics: [
      { id: 101, name: '唤醒成功率', unit: '%', decimal_places: 1, dimension_type: 'main' },
      { id: 102, name: '误唤醒率', unit: '%', decimal_places: 1, dimension_type: 'sub', parent_dimension_id: 101, parent_dimension_name: '唤醒成功率' },
      { id: 103, name: '识别准确率', unit: '%', decimal_places: 1, dimension_type: 'main' },
      { id: 105, name: '平均响应时间', unit: 'ms', decimal_places: 0, dimension_type: 'main' },
    ],
    case_type_stats: [],
    device_stats: [
      { id: 1, name: '音箱-客厅位', model: '旗舰 S1', type: 'smart_speaker', system: 'harmony', system_version: '3.2.1', status: 'online', total_cases: 48, completed_cases: 48, failed_cases: 1, success_rate: 97.9, metrics: { 唤醒成功率: 96.5, 识别准确率: 94.2, 平均响应时间: 412 } },
      { id: 2, name: '音箱-卧室位', model: '旗舰 S1', type: 'smart_speaker', system: 'android', system_version: '12', status: 'online', total_cases: 24, completed_cases: 24, failed_cases: 1, success_rate: 95.8, metrics: { 唤醒成功率: 95.4, 识别准确率: 93.1, 平均响应时间: 428 } },
    ],
    api_stats: [
      { id: 101, name: 'ASR HTTP API', status: 'active', max_process: 32, health_score: 0.92, total_cases: 48, completed_cases: 48, failed_cases: 1, success_rate: 97.9, avg_response_time: 385, stability: 0.98, metrics: { 平均响应时间: 385, 稳定性: 0.98 } },
      { id: 102, name: 'Realtime WS 网关', status: 'active', max_process: 16, health_score: 0.94, total_cases: 12, completed_cases: 12, failed_cases: 0, success_rate: 100, avg_response_time: 214, stability: 0.99, metrics: { 平均响应时间: 214, 稳定性: 0.99 } },
    ],
    devices: [
      { id: 1, name: '音箱-客厅位', model: '旗舰 S1', type: 'smart_speaker', system: 'harmony', system_version: '3.2.1', status: 'online', last_online_at: '2026-10-15T08:40:00' },
      { id: 2, name: '音箱-卧室位', model: '旗舰 S1', type: 'smart_speaker', system: 'android', system_version: '12', status: 'online', last_online_at: '2026-10-15T08:42:00' },
    ],
    apis: [
      { id: 101, name: 'ASR HTTP API', vendor: '内部 ASR 组', status: 'active', max_process: 32, health_score: 0.92 },
      { id: 102, name: 'Realtime WS 网关', vendor: '内部实时组', status: 'active', max_process: 16, health_score: 0.94 },
    ],
    tables: [],
  },
  created_at: '2026-10-15T09:20:00',
  updated_at: '2026-10-15T09:20:00',
}

/** 报告生成中/失败态切换用的可重试加载（useReportStep 消费） */
export const MOCK_REPORT_GENERATE_TASK_ID = 1042
export const MOCK_REPORT_ID = MOCK_FLOW_REPORT.id
