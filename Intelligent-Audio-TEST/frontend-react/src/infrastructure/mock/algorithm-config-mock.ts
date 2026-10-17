/**
 * 算法配置 mock 数据（infrastructure 层；17_配置运维.md §3.4 列表 + §6 编辑表单数据源）。
 * 红线④：mock 常量，不接真实后端。形态对照 api_gateway/schemas/algorithm.py；
 * 与全局算法切换器数据源（GET /algorithm/definitions）同源语义，定义中 type 与
 * domain/models/algorithm.ts MOCK_ALGORITHMS 的 id 对齐（asr-v3/asr-stream/eval-ensemble/asr-experimental）。
 */
import type {
  AlgorithmDefinition,
  AlgorithmGroup,
  DeviceApiParam,
  CaseParam,
  ReferenceParam,
  DimensionRelation,
} from '@/domain/models/algorithmConfig'

/* ───────────────────────── 算法分组 ───────────────────────── */

export const MOCK_ALGORITHM_GROUPS: AlgorithmGroup[] = [
  {
    id: 1,
    name: '语音识别',
    description: '端到端语音识别与转写算法',
    icon: 'audio-wave',
    displayOrder: 1,
    algorithmCount: 3,
    createdAt: '2026-08-01T08:00:00Z',
    updatedAt: '2026-09-28T10:12:00Z',
  },
  {
    id: 2,
    name: '流式处理',
    description: '低延迟流式与端点检测算法',
    icon: 'stream',
    displayOrder: 2,
    algorithmCount: 2,
    createdAt: '2026-08-01T08:00:00Z',
    updatedAt: '2026-09-30T14:05:00Z',
  },
  {
    id: 3,
    name: '评估分析',
    description: '多维指标评估与质量分析算法',
    icon: 'gauge',
    displayOrder: 3,
    algorithmCount: 1,
    createdAt: '2026-08-05T08:00:00Z',
    updatedAt: '2026-10-01T09:30:00Z',
  },
  {
    id: 4,
    name: '实验预研',
    description: '实验性算法，仅供内部验证',
    icon: 'flask',
    displayOrder: 4,
    algorithmCount: 1,
    createdAt: '2026-08-20T08:00:00Z',
    updatedAt: '2026-09-15T11:20:00Z',
  },
]

/* ───────────────────────── 参数样例 ───────────────────────── */

function deviceParam(
  id: number,
  paramCode: string,
  paramName: string,
  direction: DeviceApiParam['direction'],
  paramType: string,
  required = false,
  helpText = ''
): DeviceApiParam {
  return {
    id,
    paramCode,
    paramName,
    label: paramName,
    paramType,
    direction,
    required,
    defaultValue: null,
    helpText,
    uiOrder: id,
    hidden: false,
  }
}

function caseParam(
  id: number,
  paramCode: string,
  paramName: string,
  paramType: CaseParam['paramType'],
  scope: CaseParam['scope'],
  overrides: Partial<CaseParam> = {}
): CaseParam {
  return {
    id,
    paramCode,
    paramName,
    label: paramName,
    paramType,
    scope,
    required: false,
    defaultValue: null,
    helpText: '',
    uiOrder: id,
    hidden: false,
    minValue: null,
    maxValue: null,
    step: null,
    unit: null,
    annotationCode: null,
    fieldPath: null,
    ...overrides,
  }
}

function referenceParam(
  id: number,
  code: string,
  name: string,
  type: ReferenceParam['type'],
  overrides: Partial<ReferenceParam> = {}
): ReferenceParam {
  return {
    id,
    code,
    name,
    type,
    annotationCode: null,
    annotationFormat: null,
    fieldPath: null,
    mergeMode: null,
    helpText: '',
    ...overrides,
  }
}

function dimensionRelation(
  id: number,
  dimensionId: number,
  dimensionName: string,
  weight: number,
  isDefault = false
): DimensionRelation {
  return { id, dimensionId, dimensionName, weight, isDefault }
}

/* ───────────────────────── 算法定义 ───────────────────────── */

export const MOCK_ALGORITHM_DEFINITIONS: AlgorithmDefinition[] = [
  {
    id: 1,
    type: 'asr-v3',
    name: '通用识别引擎',
    groupId: 1,
    groupName: '语音识别',
    category: null,
    description: '端到端语音识别基线模型，支持普通话与中英混说场景，输出带时间戳的转写文本。',
    status: 'online',
    icon: null,
    displayOrder: 1,
    deviceParams: [
      deviceParam(101, 'input_audio', '输入音频', 'input', 'audio_file', true, '待识别音频文件（wav/mp3/flac）'),
      deviceParam(102, 'sample_rate', '采样率', 'input', 'text', false, '音频采样率，默认 16000'),
      deviceParam(103, 'output_text', '转写文本', 'output', 'text', false, '识别输出的转写文本'),
    ],
    apiParams: [
      deviceParam(201, 'language', '语言', 'input', 'text', false, '识别语言，默认 zh'),
      deviceParam(202, 'enable_timestamp', '输出时间戳', 'input', 'text', false, '是否输出词级时间戳'),
    ],
    caseParams: [
      caseParam(301, 'source_language', '源语言', 'select', 'common', {
        defaultValue: 'zh',
        helpText: '测试语料源语言',
      }),
      caseParam(302, 'target_language', '目标语言', 'select', 'common', {
        defaultValue: 'en',
      }),
      caseParam(303, 'noise_level', '噪声等级', 'slider', 'common', {
        defaultValue: '0.5',
        minValue: 0,
        maxValue: 1,
        step: 0.1,
        unit: '档',
      }),
      caseParam(304, 'speaker_count', '说话人数', 'number', 'api', {
        defaultValue: '1',
        minValue: 1,
        maxValue: 8,
      }),
      caseParam(305, 'audio_file', '音频文件', 'audio_select', 'e2e', {
        fieldPath: 'audio',
        helpText: 'E2E 场景注入的音频文件',
      }),
    ],
    referenceParams: [
      referenceParam(401, 'ref_text', '参考文本', 'text', { helpText: '标准参考转写文本' }),
      referenceParam(402, 'ref_audio', '参考音频', 'audio', { fieldPath: 'segments[].audio' }),
    ],
    mappings: {
      device: [
        { id: 501, sourceParam: 'audio_file', targetParam: 'input_audio', transformType: 'none' },
        { id: 502, sourceParam: 'noise_level', targetParam: 'sample_rate', transformType: 'none' },
      ],
      api: [{ id: 503, sourceParam: 'source_language', targetParam: 'language', transformType: 'none' }],
      evaluation: [
        { id: 504, sourceParam: 'output_text', targetParam: '识别准确率', transformType: 'none' },
      ],
    },
    associatedDimensions: [
      dimensionRelation(601, 3, '识别准确率', 1, true),
      dimensionRelation(602, 4, '平均WER', 0.8),
    ],
    caseCount: 50,
    hasDraft: true,
    createdAt: '2026-08-10T08:30:00Z',
    updatedAt: '2026-10-12T16:40:00Z',
  },
  {
    id: 2,
    type: 'asr-stream',
    name: '流式识别引擎',
    groupId: 2,
    groupName: '流式处理',
    category: null,
    description: '低延迟流式转写引擎，面向实时会议与直播场景，支持增量结果推送。',
    status: 'online',
    icon: null,
    displayOrder: 2,
    deviceParams: [
      deviceParam(111, 'stream_input', '音频流', 'input', 'audio_stream', true, '实时音频流输入'),
      deviceParam(112, 'chunk_ms', '分片时长', 'input', 'text', false, '每分片时长（毫秒），默认 1000'),
      deviceParam(113, 'partial_text', '增量文本', 'output', 'text', false, '实时增量识别结果'),
    ],
    apiParams: [
      deviceParam(211, 'stream_mode', '流式模式', 'input', 'text', false, 'full / partial'),
      deviceParam(212, 'vad_enabled', '端点检测', 'input', 'text', false, '是否启用 VAD 切分'),
    ],
    caseParams: [
      caseParam(311, 'vad_sensitivity', '端点灵敏度', 'slider', 'common', {
        defaultValue: '0.6',
        minValue: 0,
        maxValue: 1,
        step: 0.1,
      }),
      caseParam(312, 'max_idle_ms', '最大静音', 'number', 'common', {
        defaultValue: '1500',
        minValue: 200,
        maxValue: 5000,
        step: 100,
        unit: 'ms',
      }),
      caseParam(313, 'continuity_mode', '连续对话', 'switch', 'api', { defaultValue: 'true' }),
    ],
    referenceParams: [
      referenceParam(411, 'context_segment', '上下文片段', 'text', { mergeMode: 'concat' }),
    ],
    mappings: {
      device: [{ id: 511, sourceParam: 'max_idle_ms', targetParam: 'chunk_ms', transformType: 'none' }],
      api: [
        { id: 512, sourceParam: 'continuity_mode', targetParam: 'stream_mode', transformType: 'none' },
        { id: 513, sourceParam: 'vad_sensitivity', targetParam: 'vad_enabled', transformType: 'uppercase' },
      ],
      evaluation: [{ id: 514, sourceParam: 'partial_text', targetParam: '实时率', transformType: 'none' }],
    },
    associatedDimensions: [
      dimensionRelation(611, 5, '平均响应时间', 1, true),
    ],
    caseCount: 30,
    createdAt: '2026-08-12T09:10:00Z',
    updatedAt: '2026-10-09T11:22:00Z',
  },
  {
    id: 3,
    type: 'eval-ensemble',
    name: '多维评估集成',
    groupId: 3,
    groupName: '评估分析',
    category: null,
    description: '多维度指标集成评估算法，聚合识别、唤醒与噪声场景输出综合得分。',
    status: 'online',
    icon: null,
    displayOrder: 3,
    deviceParams: [
      deviceParam(121, 'report_in', '评估报告', 'input', 'json', true, '待评估的 JSON 报告'),
      deviceParam(122, 'score_out', '综合得分', 'output', 'text', false, '输出综合评估得分'),
    ],
    apiParams: [
      deviceParam(221, 'metric_weights', '指标权重', 'input', 'json', false, '各维度权重 JSON'),
    ],
    caseParams: [
      caseParam(321, 'evaluation_mode', '评估模式', 'select', 'common', {
        defaultValue: 'full',
        helpText: 'full / quick',
      }),
      caseParam(322, 'report_threshold', '阈值', 'slider', 'common', {
        defaultValue: '0.8',
        minValue: 0,
        maxValue: 1,
        step: 0.05,
      }),
    ],
    referenceParams: [],
    mappings: {
      device: [{ id: 521, sourceParam: 'evaluation_mode', targetParam: 'report_in', transformType: 'json_parse' }],
      api: [{ id: 522, sourceParam: 'report_threshold', targetParam: 'metric_weights', transformType: 'none' }],
      evaluation: [{ id: 523, sourceParam: 'score_out', targetParam: '综合得分', transformType: 'none' }],
    },
    associatedDimensions: [
      dimensionRelation(621, 1, '唤醒成功率', 1),
      dimensionRelation(622, 3, '识别准确率', 1, true),
    ],
    caseCount: 20,
    createdAt: '2026-08-15T10:00:00Z',
    updatedAt: '2026-10-10T15:15:00Z',
  },
  {
    id: 4,
    type: 'asr-experimental',
    name: '实验识别引擎',
    groupId: 4,
    groupName: '实验预研',
    category: null,
    description: '实验性模型，仅供内部验证，不参与正式任务分发。',
    status: 'offline',
    icon: null,
    displayOrder: 4,
    deviceParams: [
      deviceParam(131, 'experiment_input', '实验输入', 'input', 'audio_file', true),
    ],
    apiParams: [deviceParam(231, 'flag', '实验开关', 'input', 'text', false)],
    caseParams: [
      caseParam(331, 'beta_flag', 'Beta 标识', 'switch', 'api', { defaultValue: 'false' }),
    ],
    referenceParams: [],
    mappings: {
      device: [],
      api: [{ id: 531, sourceParam: 'beta_flag', targetParam: 'flag', transformType: 'none' }],
      evaluation: [],
    },
    associatedDimensions: [],
    caseCount: 15,
    createdAt: '2026-08-20T08:00:00Z',
    updatedAt: '2026-09-15T11:20:00Z',
  },
  {
    id: 5,
    type: 'tts-v1',
    name: '语音合成引擎',
    groupId: 1,
    groupName: '语音识别',
    category: null,
    description: '文本转语音合成引擎，支持多种音色与语速调节。',
    status: 'online',
    icon: null,
    displayOrder: 5,
    deviceParams: [
      deviceParam(141, 'text_input', '合成文本', 'input', 'text', true, '待合成的文本内容'),
      deviceParam(142, 'audio_out', '合成音频', 'output', 'audio_file', false),
    ],
    apiParams: [
      deviceParam(241, 'voice', '音色', 'input', 'text', false, '音色标识，默认 default'),
      deviceParam(242, 'speed', '语速', 'input', 'text', false, '0.5~2.0'),
    ],
    caseParams: [
      caseParam(341, 'voice_gender', '音色性别', 'select', 'common', { defaultValue: 'female' }),
      caseParam(342, 'speech_speed', '语速', 'slider', 'common', {
        defaultValue: '1.0',
        minValue: 0.5,
        maxValue: 2,
        step: 0.1,
        unit: 'x',
      }),
    ],
    referenceParams: [
      referenceParam(441, 'g2p_dict', '发音词典', 'json', { fieldPath: 'dict' }),
    ],
    mappings: {
      device: [{ id: 541, sourceParam: 'speech_speed', targetParam: 'speed', transformType: 'none' }],
      api: [{ id: 542, sourceParam: 'voice_gender', targetParam: 'voice', transformType: 'none' }],
      evaluation: [],
    },
    associatedDimensions: [],
    caseCount: 12,
    createdAt: '2026-09-01T09:00:00Z',
    updatedAt: '2026-10-08T10:30:00Z',
  },
  {
    id: 6,
    type: 'vad-v2',
    name: '端点检测引擎',
    groupId: 2,
    groupName: '流式处理',
    category: null,
    description: '语音活动检测引擎，识别说话起始与结束端点，辅助流式转写分片。',
    status: 'online',
    icon: null,
    displayOrder: 6,
    deviceParams: [
      deviceParam(151, 'audio_in', '音频输入', 'input', 'audio_stream', true),
      deviceParam(152, 'segments_out', '语音片段', 'output', 'json', false),
    ],
    apiParams: [
      deviceParam(251, 'threshold', '能量阈值', 'input', 'text', false),
    ],
    caseParams: [
      caseParam(351, 'noise_floor', '底噪', 'slider', 'common', {
        defaultValue: '0.3',
        minValue: 0,
        maxValue: 1,
        step: 0.1,
      }),
    ],
    referenceParams: [],
    mappings: {
      device: [{ id: 551, sourceParam: 'noise_floor', targetParam: 'threshold', transformType: 'none' }],
      api: [],
      evaluation: [],
    },
    associatedDimensions: [],
    caseCount: 8,
    createdAt: '2026-09-05T08:40:00Z',
    updatedAt: '2026-10-02T13:50:00Z',
  },
  {
    id: 7,
    type: 'wake-word',
    name: '唤醒词识别',
    groupId: 1,
    groupName: '语音识别',
    category: null,
    description: '本地唤醒词识别引擎，支持自定义唤醒词与多唤醒词切换。',
    status: 'offline',
    icon: null,
    displayOrder: 7,
    deviceParams: [
      deviceParam(161, 'wake_audio', '唤醒音频', 'input', 'audio_stream', true),
    ],
    apiParams: [deviceParam(261, 'wake_words', '唤醒词表', 'input', 'json', false)],
    caseParams: [
      caseParam(361, 'wake_word', '唤醒词', 'select', 'common', {
        defaultValue: '小度小度',
        helpText: '待验证的唤醒词',
      }),
    ],
    referenceParams: [
      referenceParam(461, 'wake_audio_ref', '唤醒参考音频', 'audio'),
    ],
    mappings: {
      device: [],
      api: [{ id: 561, sourceParam: 'wake_word', targetParam: 'wake_words', transformType: 'json_parse' }],
      evaluation: [{ id: 562, sourceParam: 'wake_word', targetParam: '唤醒成功率', transformType: 'none' }],
    },
    associatedDimensions: [
      dimensionRelation(661, 1, '唤醒成功率', 1, true),
      dimensionRelation(662, 2, '误唤醒率', 0.5),
    ],
    caseCount: 3,
    createdAt: '2026-09-10T10:20:00Z',
    updatedAt: '2026-09-28T09:45:00Z',
  },
]

/** 评估维度选项（§6.6 关联维度 Select 选项；主维度，dimensionType≠sub 过滤） */
export const MOCK_AVAILABLE_DIMENSIONS = [
  { id: 1, name: '唤醒成功率' },
  { id: 2, name: '误唤醒率' },
  { id: 3, name: '识别准确率' },
  { id: 4, name: '平均WER' },
  { id: 5, name: '平均响应时间' },
]

/** 功能特性快捷开关（§6.3 用例参数页签；勾选自动批量添加/删除对应参数） */
export const MOCK_FEATURE_BUNDLES = [
  {
    key: 'translation',
    label: '翻译',
    params: ['source_language', 'target_language'],
  },
  {
    key: 'noise',
    label: '噪声',
    params: ['noise_level'],
  },
  {
    key: 'speaker',
    label: '说话人',
    params: ['speaker_count', 'max_idle_ms'],
  },
  {
    key: 'streaming',
    label: '流式',
    params: ['vad_sensitivity', 'continuity_mode'],
  },
]

/** 用例参数代码预设（§6.3 datalist 预设，新建用例参数 placeholder 建议） */
export const MOCK_CASE_PARAM_CODE_PRESETS = [
  'source_language',
  'target_language',
  'noise_level',
  'speaker_count',
  'audio_file',
  'vad_sensitivity',
  'max_idle_ms',
  'continuity_mode',
  'wake_word',
  'speech_speed',
]
