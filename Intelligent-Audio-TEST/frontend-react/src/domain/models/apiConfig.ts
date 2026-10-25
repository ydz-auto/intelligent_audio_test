/**
 * API 配置域领域模型（domain 层；10_测试执行.md §9 落位）。
 * 形态对照 api_gateway/schemas/api.py ApiItem/ApiEndpointItem 实测：
 * id/name/vendor/description/status/meta/algorithm_type/default_max_process/
 * default_max_timeout/default_max_audio_duration/health_score/endpoints/protocol/streaming
 * （INT-1223：api_url 已前后端全量移除，api_endpoints 为唯一端点配置入口；
 *  INT-1800：`device_type` 退役，协议与流式性改为两个独立维度）。
 * 本卡消费子集（被测 API 表格 + 编辑弹窗），完整配置域模型归设备管理页 API 页签。
 */

import type { DeviceApiParam, ParamMapping } from './algorithmConfig'
import type { DeviceType } from './device'
import type { ApiProtocol } from './apiProtocol'

export interface ApiEndpoint {
  id: string | null
  endpoint: string
  name: string | null
  maxProcess: number | null
  maxTimeout: number | null
  /** 端点级音频时长/优先级（api_test_service _validate_endpoint_obj 要求四整数合法；INT-1362 补全） */
  maxAudioDuration: number | null
  priority: number | null
  status: string | null
  healthScore: number | null
  description: string | null
  /** 端点级密钥池摘要（读侧：count + 尾号 4 位；完整密钥后端一律不返回/前端不回显） */
  apiKeysSummary: { count: number; tails: string[] } | null
  /** 写侧瞬态：端点级密钥池（textarea 草稿，每行一个 key；adapter 拆行转 api_keys） */
  apiKeysText?: string
  /** 写侧显式密钥池（数组兜底；留空不传 api_keys 保留既有池） */
  apiKeys?: string[]
}

export interface ApiConfig {
  id: number
  name: string
  vendor: string | null
  description: string | null
  /** 在线/离线（列表状态徽章；schema status 实测） */
  status: string | null
  algorithmType: string | null
  defaultMaxProcess: number | null
  defaultMaxTimeout: number | null
  defaultMaxAudioDuration: number | null
  healthScore: number | null
  endpoints: ApiEndpoint[]
  /** 端点级聚合最大并发（端点 max_process 最大值；并发参数卡自动求合用） */
  maxConcurrent: number
  /**
   * 传输协议（INT-1800 / B0 §3.2）：只读 `apis.protocol` 列，值域 http / websocket / sse / grpc。
   * 不再读 `meta.protocol`、不再按端点前缀派生、不再有 `deviceType` 三值枚举。
   * 读侧契约恒有值；后端未升级到含该列的版本时为 null（界面显示「—」，不猜协议），
   * 因为前后端必须同批上线，猜一个默认值只会掩盖版本不匹配。
   */
  protocol: ApiProtocol | null
  /** 交互形态（INT-1800 / B0 §3.2）：true = 流式（= 实时），false = 非流式；执行道只由它派生 */
  streaming: boolean
  /**
   * 原始 meta（INT-1777）：后端保存为整块 replace，前端以读侧 meta 为 base 做键级合并，
   * 页签只覆盖自己声明的键，未触碰 meta 时不回传该键（避免 {} 清空全表）。
   */
  meta: Record<string, unknown>
  /**
   * 目标音频格式声明（INT-1777）：顶层列 apis.audio_config（不是 meta.audio_config），
   * 键 = sample_rate / bit_depth / channels / container（AudioContainer / AudioBitDepth 枚举）。
   */
  audioConfig: Record<string, unknown> | null
}

/**
 * API 参数声明（INT-1778，输出字段页签只读视图）。
 * = 算法配置域 DeviceApiParam + C2（INT-1747）新增的 field_path：
 * 「声明表」的唯一来源是 algorithm_api_params(direction=output)，
 * field_path 非空按路径取厂商原始响应值，为空按 param_code 取顶层键（`shared/utils/api_output_extractor.py`）。
 * 未落库（老数据）时 fieldPath 为 null，界面显示「—」。
 */
export type AlgorithmApiParam = DeviceApiParam & { fieldPath: string | null }

/**
 * 参数映射行（INT-1778，映射页签只读视图）。
 * 复用算法配置域 ParamMapping 全字段；`/algorithm/mappings` 只下发 PO 列（无 dimension_name），
 * 维度名由读侧按 dimension_id 补齐，取不到时 element 显示「—」。
 */
export type AlgorithmApiMapping = ParamMapping

/**
 * API 连接测试结果（api.py ApiHealthCheckData 平移；端点状态取 endpoints_status，INT-1223）
 */
export interface ApiHealthCheckResult {
  id: number
  status: string
  healthScore: number | null
  endpointsStatus: string | null
  statusCode: number | null
  responseTime: string | null
  error: string | null
  warning: string | null
}

/* ------------------------------------------------------------------ */
/* A3（INT-1791）：gRPC 符号表 + 响应解析预览两个读侧模型               */
/* ------------------------------------------------------------------ */

/** proto 报文的一个字段（`path` 已含嵌套层级，如 `request.text`） */
export interface ApiProtoField {
  path: string
  type: string
  repeated: boolean
}

/** proto 方法（`methodKind` 与 `meta.grpc.method_kind` 同值域） */
export interface ApiProtoMethod {
  name: string
  methodKind: string
  inputType: string
  outputType: string
  inputFields: ApiProtoField[]
  outputFields: ApiProtoField[]
}

export interface ApiProtoService {
  name: string
  methods: ApiProtoMethod[]
}

/**
 * `POST /apis/proto` 上传结果 = 内容寻址存储 key + 符号表（INT-1952 §4.3）。
 * 前端只用它回填 `meta.grpc` 的 proto 三元组与 service / method 下拉。
 */
export interface ApiProtoSymbolTable {
  objectKey: string
  sha256: string
  size: number
  services: ApiProtoService[]
}

/**
 * 响应解析预览结果（INT-1772 `POST /apis/parse-preview` 纯函数端点）：
 * `extracted` 的键 = 请求里的配置字段名，`unresolved` = 路径没命中的字段（不静默丢）。
 */
export interface ApiParsePreviewResult {
  extracted: Record<string, unknown>
  unresolved: string[]
}

/**
 * API 目标亲和域令牌派生（INT-1433 起、INT-1800 改口径）：B0 §3.3 唯一派生规则 =
 * 只看 `streaming` —— 流式 → websocket_api（需要实例亲和），非流式 → http_api（无状态）。
 * 不再看显式 deviceType、不再看端点协议前缀：协议与执行道是两维，协议不参与道判断。
 */
export function deriveApiTargetDeviceType(api: Pick<ApiConfig, 'streaming'>): DeviceType {
  return api.streaming ? 'websocket_api' : 'http_api'
}
