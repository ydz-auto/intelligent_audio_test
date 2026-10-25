/**
 * 被测 API DTO（infrastructure/dto 层——snake_case 唯一出现层；10_测试执行.md §9）。
 * 形态对照 api_gateway/schemas/api.py ApiItem/ApiEndpointItem/ApiHealthCheckData 实测逐字段。
 */

/** GET /apis 端点项（api.py ApiEndpointItem） */
export interface ApiEndpointItemDto {
  id: string | null
  endpoint: string
  name: string | null
  max_process: number | null
  max_timeout: number | null
  max_audio_duration: number | null
  status: string | null
  health_score: number | null
  priority: number | null
  description: string | null
  /** 端点级密钥池摘要（INT-1177/1178：读侧只返回 count + 尾号，完整 key 一律不返回） */
  api_keys_summary: { count: number; tails: string[] } | null
}

/** GET /apis 列表项（api.py ApiItem；GET /apis 实测无后端权限门槛；INT-1223：api_url 已前后端移除） */
export interface ApiItemDto {
  id: number
  name: string
  vendor: string | null
  description: string | null
  status: string | null
  meta: Record<string, unknown>
  /** 代理配置（api.py ApiItem proxy_type/proxy_url 实测；INT-1029） */
  proxy_type: string | null
  proxy_url: string | null
  algorithm_type: string | null
  default_max_process: number | null
  default_max_timeout: number | null
  default_max_audio_duration: number | null
  health_score: number | null
  endpoints: ApiEndpointItemDto[]
  output_types: string[] | null
  /**
   * 传输协议（INT-1800 / B0 §3.2）：`apis.protocol` 列，规范值 http / websocket / sse / grpc。
   * `device_type` 已退役（后端读侧不再返回、写侧显式 400），前端不再有该字段。
   */
  protocol: string
  /** 交互形态：true = 流式，false = 非流式（`apis.streaming` 列） */
  streaming: boolean
  adapter_class: string | null
  audio_config: Record<string, unknown> | null
  rms_spl_mapping_id: number | null
  created_at: string | null
  updated_at: string | null
}

/** POST /apis/{id}/health 结果（api.py ApiHealthCheckData；INT-1223：api_url_status 已移除，端点状态取 endpoints_status） */
export interface ApiHealthCheckDataDto {
  id: number
  status: string
  health_score: number | null
  endpoints_status: string | null
  status_code: number | null
  response_time: string | null
  error: string | null
  warning: string | null
}

/* ------------------------------------------------------------------ */
/* A3（INT-1791）：proto 上传符号表 + 解析预览两个端点的 DTO            */
/* ------------------------------------------------------------------ */

/** `POST /apis/proto` 的报文字段（INT-1952 §4.3；`input_fields` / `output_fields` 同形） */
export interface ApiProtoFieldDto {
  path: string
  type: string
  repeated: boolean
}

/** proto 方法条目（`method_kind` = unary / server_stream / bidi） */
export interface ApiProtoMethodDto {
  name: string
  method_kind: string
  input_type: string
  output_type: string
  input_fields: ApiProtoFieldDto[]
  output_fields: ApiProtoFieldDto[]
}

/** proto service 条目 */
export interface ApiProtoServiceDto {
  name: string
  methods: ApiProtoMethodDto[]
}

/**
 * `POST /apis/proto` 响应 `data`（INT-1952 契约形状）。
 * ⚠️ 端点交付在 `agent/d/int-1952`，**尚未合入 origin/V9.7.31、未部署** → 前端按契约先接，
 * 上传控件在本轮 UI 上明示「尚未上线」，**禁止用假 object_key 冒充成功**。
 */
export interface ApiProtoUploadDataDto {
  object_key: string
  sha256: string
  size: number
  services: ApiProtoServiceDto[]
}

/** `POST /apis/parse-preview` 结果（`api_gateway/application/services/api/parse_preview.py:build_preview`） */
export interface ApiParsePreviewDataDto {
  extracted: Record<string, unknown>
  unresolved: string[]
}
