export interface TestCaseGroup {
  name?: string;
  group?: string;
  id?: string | number;
}

export interface TestCaseGroupItem {
  name?: string;
  group?: string;
  id?: string | number;
  [key: string]: unknown;
}

export interface GroupStat {
  name: string;
  total: number;
  api: number;
  e2e: number;
}

export interface Dimension {
  id: string | number;
  name: string;
  description?: string;
  type?: string;
}

export interface TestCase {
  id?: string | number;
  name?: string;
  group_name?: string;
  group?: string;
  groupName?: string;
  group_id?: string | number;
  groupId?: string | number;
  type?: string;
  testType?: string;
  test_type?: 'api' | 'e2e';
  config?: TestCaseConfig;
}

export interface AudioItem {
  id: string | number;
  name: string;
  audioType?: string;
  tags?: string | string[];
  duration?: number | string;
  filePath?: string;
  filename?: string;
}

export interface PlaybackDevice {
  id: string | number;
  name: string;
  channelIndex?: number;
}

export interface ImportPreviewItem {
  name: string;
  type: string;
  group: string;
  operation: 'update' | 'insert';
}

export interface ImportPreviewData {
  total: number;
  items: ImportPreviewItem[];
  audioConfigsCount: number;
  dimensionsCount: number;
  tagsCount: number;
  groupsCount: number;
  sheetNames: string[];
}

// ============================================================
// rounds-as-top-level 架构核心类型
// ============================================================

/**
 * 算法参数项 — 通用算法参数容器
 * 对应后端 AlgorithmParamItem: {field_code, field_value}
 */
export interface AlgorithmParamItem {
  field_code: string;
  field_value: unknown;
}

/**
 * 按轮分组的算法参数 — 对应 test_cases.algorithm_params 列
 * 每个元素描述某一轮的算法参数集合
 */
export interface RoundAlgorithmParams {
  round_number: number;
  params: AlgorithmParamItem[];
}

/**
 * 按轮分组的参考参数路径 — 对应 test_cases.reference_params 列
 * 每个元素描述某一轮的参考参数文件路径
 */
export interface RoundReferenceParams {
  round_number: number;
  reference_params_path: string;
}

/**
 * 音频配置项 — 轮次内音频
 * testType 已移除，由父级用例的 test_type 决定
 */
export interface AudioConfig {
  audioId: string;
  playbackDeviceId?: string;
  spl?: number;
  playOrder: number;
}

/**
 * 评估维度配置
 */
export interface DimensionConfig {
  id?: string | number;
  name: string;
  weight: number;
  threshold: number;
}

/**
 * 背景噪声配置 — 新增 loop 字段
 */
export interface BackgroundNoiseConfig {
  audioId: string;
  deviceIds: string[];
  spl: number;
  loop?: boolean;
}

/**
 * 轮次评估配置
 */
export interface RoundEvaluationConfig {
  enabled: boolean;
  dimensions: DimensionConfig[];
}

/**
 * 声纹注册配置（数据层）
 * 在 algorithmParams 中拆分为多个 field_code
 */
export interface VoiceprintConfig {
  enabled: boolean;
  audioId?: string;
  playbackDeviceId?: string;
  spl: number;
  waitTime: number;
}

/**
 * 单个干扰人配置
 */
export interface InterfererConfigItem {
  audioId?: string;
  audioName?: string;
  playbackDeviceId?: string;
  /** 设备名（统一标注文件导入时无 ID，仅设备名） */
  playbackDeviceName?: string;
  spl: number;
  startDelay: number;
  loop: boolean;
}

/**
 * 打断检测配置
 */
export interface InterruptionConfig {
  enabled: boolean;
  sensitivity: number;
}

/**
 * 单轮配置项 — rounds-as-top-level 架构的核心数据结构
 * 对应后端 RoundConfigItem
 *
 * 仅保留结构性字段：roundNumber, audios, backgroundNoise, evaluation
 * 算法参数和参考参数已移至 test_cases 表的独立列：
 *   - algorithm_params: RoundAlgorithmParams[]
 *   - reference_params: RoundReferenceParams[]
 */
export interface RoundConfigItem {
  roundNumber: number;
  audios: AudioConfig[];
  backgroundNoise?: BackgroundNoiseConfig;
  evaluation?: RoundEvaluationConfig;
  [key: string]: unknown;
}

/**
 * 测试用例配置 — rounds-as-top-level 架构
 * config = { rounds: [...], dimensions: [...] }
 */
export interface TestCaseConfig {
  rounds?: RoundConfigItem[];
  dimensions?: DimensionConfig[];
  voiceprint_config?: {
    enabled?: boolean;
    audio?: { id?: string };
    device?: { id?: string };
    spl?: number;
    waitTime?: number;
  };
  /** case 级全局背景噪声（跨所有轮次持续播放，优先于 round 级） */
  background_noise?: BackgroundNoiseConfig;
  /** 源音频路径 */
  source_audio?: string;
  /** 是否自动生成 */
  auto_generated?: boolean;
  [key: string]: unknown;
}

/**
 * 表单数据 — 包含 test_type
 */
export interface TestCaseFormData {
  id?: string | number;
  name: string;
  description?: string;
  group?: string;
  groupId?: string | number;
  group_id?: string;
  groupName?: string;
  group_name?: string;
  tags?: string[];
  tagsInput?: string;
  test_type?: 'api' | 'e2e';
  algorithmType?: string;
  algorithm_type?: string;
  config: TestCaseConfig;
  /** 按轮分组的算法参数，独立于 config，对应 test_cases.algorithm_params 列 */
  algorithm_params?: RoundAlgorithmParams[];
  /** 按轮分组的参考参数路径，独立于 config，对应 test_cases.reference_params 列 */
  reference_params?: RoundReferenceParams[];
  _originalGroup?: string;
  _originalGroupId?: string;
}

export interface GroupFormData {
  name: string;
  description?: string;
  algorithmType?: string;
}

export interface ExportFormData {
  groups: string[];
  testType: string;
  format: string;
  includeConfig: boolean;
  includeDeleted: boolean;
}

export interface ImportFormData {
  file: File | null;
}

export interface AssociatedDimension {
  id: number;
  name: string;
  description?: string;
  type?: string;
  weight: number;
  is_default: boolean;
}

export interface AlgorithmOption {
  value: string;
  name: string;
  label?: string;
}
