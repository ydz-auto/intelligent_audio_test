/**
 * TestCaseReportDetail 类型定义（输入形状 + 渲染形状 + props 契约）
 * 注意：全部为 camelCase Domain/视图模型（snake_case 已由 Infrastructure adapter 归一化），
 * 字段解析与映射见 execution/metrics/multiRound 子模块
 */
import type { AudioInfo } from '../../../domain/model/audio';
import type { CaseResultAudio } from '../../../domain/model/taskCaseDetail';
import type {
  ComparisonColumn,
  ReportAlgorithmResultItem,
  ReportFieldMapping,
  ReportFieldMappingItem,
  ReportMetricConfig,
  ReportReferenceParamEntry,
  ReportResourceHeader,
} from '../../../domain/model/report';

// ===== 输入形状（经 adapter 归一化的 camelCase Domain/视图模型） =====

/** 维度评估结果条目 */
export interface DimensionMetricInput {
  id?: string | number
  name?: string
  value?: number | string
  score?: number
  errorMessage?: string | null
}

/** 单选指标结果条目 */
export interface SingleMetricResultInput {
  id?: number | string | null
  metric: string
  value: number | string
}

/** 指标配置（Domain ReportMetricConfig，小数位唯一契约 decimalPlaces） */
export type MetricConfigInput = ReportMetricConfig

/** 资源头（兼容后端 resource 字段） */
export type ResourceHeaderInput = ReportResourceHeader & { resource?: string | null }

/** 参考参数条目（Domain ReportReferenceParamEntry；字典键为参数 code 数据 key，保留原样） */
export type ReferenceParamData = ReportReferenceParamEntry

/** 动态字段映射项（Domain ReportFieldMappingItem） */
export type FieldMappingItem = ReportFieldMappingItem

/** 算法字段映射快照（Domain ReportFieldMapping） */
export type { ReportFieldMapping }

/** 算法结果项（Domain ReportAlgorithmResultItem；value 载荷为数据驱动结构，原样保留） */
export type AlgorithmResultItem = ReportAlgorithmResultItem

/** 指标对比条目（裸值 或 保留维度归组信息的对象值；前端视图模型 camelCase） */
export type ComparisonMetricEntry =
  | number
  | string
  | {
      value: number | string
      dimensionType?: string
      parentDimensionId?: number | string | null
      parentDimensionName?: string | null
    }

/** 设备指标对比数据 */
export interface ComparisonDeviceData {
  metrics?: Record<string, ComparisonMetricEntry>
}

/** LLM 评估数据（extractLlmReasoning 使用；raw_response 为后端协议值，原样保留） */
export interface LlmEvaluationData {
  reasoning?: string
  raw_response?: string | { reasoning?: string; analysis?: string }
}

// ===== 内部渲染形状 =====

/** 展示指标（统一 dimensions/metrics 的渲染形状） */
export interface DisplayMetric {
  id?: string | number | null
  metric: string
  value: number | string
  score?: number | null
  errorMessage?: string | null
}

/** 参考文本字段（paramCode/paramType 为后端协议标识） */
export interface ReferenceTextField extends FieldMappingItem {
  paramCode: string
  label: string
  paramType: string
  roundNumber?: number
  text: string
}

/** 可展开结果文本字段 */
export interface ResultTextField extends FieldMappingItem {
  paramCode: string
  label: string
  paramType: string
  roundNumber?: number
  dimensionName?: string | null
  getValue: (device: string) => string
}

/** 结果文本分组 */
export interface ResultFieldGroup {
  key: string
  label: string
  fields: ResultTextField[]
}

/** 对比表格列（复用 domain ComparisonColumn，本组件不需要 editable） */
export type ReportDetailColumn = Omit<ComparisonColumn, 'editable'>

/** 轮次 Tab（评分指标区 / 执行结果区共享） */
export interface RoundTab {
  key: string
  label: string
  /** 'round:N' | 'overall' | null（null 表示无轮次标记的单轮场景） */
  roundTag: string | null
  order: number
}

/** 归组指标项（分组表格行来源） */
export interface GroupedMetricItem {
  metricKey: string
  base: string
  dimType: string
  parentName: string
  parentId: number | string | null
}

/** 主维度分组（子维度归入父维度组） */
export interface GroupedMetricGroup {
  groupLabel: string
  mainItem: GroupedMetricItem | null
  subItems: GroupedMetricItem[]
}

/** 分组表格行（含主维度标题行/子维度行标志） */
export interface GroupedMetricRow {
  _rowId: string
  metricName: string
  isGroupHeader?: boolean
  isSubDim?: boolean
  [device: string]: number | string | boolean | undefined
}

/** 路径音频（stream-by-path 打开） */
export interface PathAudioItem {
  path: string
  label?: string
  type?: string
}

/** 播放器当前音频（音频列表项展开 或 路径音频两种来源） */
export type PlayingAudio = (AudioInfo & { index?: number; spl?: number; offset?: number }) | PathAudioItem

/** 组件 props 契约（与 TestCaseReportDetail.vue defineProps 对齐） */
export interface TestCaseReportDetailProps {
  dimensions?: DimensionMetricInput[]
  metrics?: SingleMetricResultInput[]
  audioPath?: string
  asrResult?: string
  transResult?: string
  isComparison: boolean
  devices: string[]
  comparisonData: Record<string, ComparisonDeviceData>
  metricConfigs: MetricConfigInput[]
  audioList: AudioInfo[]
  referenceAsr?: string
  referenceTrans?: string
  resourceHeaders: ResourceHeaderInput[]
  algorithmResults: AlgorithmResultItem[]
  referenceParams: Record<string, ReferenceParamData>
  algorithmType: string
  results: unknown[]
  fieldMapping: ReportFieldMapping
  resultAudios: Record<string, CaseResultAudio[]>
}
