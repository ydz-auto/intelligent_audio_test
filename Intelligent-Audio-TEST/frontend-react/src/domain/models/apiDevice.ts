/**
 * 测试 API 领域模型（domain 层；16_设备域.md §3.6 落位——「完整配置域模型归设备管理页 API 页签」）。
 * 形态对照 api_gateway/schemas/api.py ApiItem/ApiEndpointItem 实测逐字段；
 * 与 10_测试执行.md 的 ApiConfig 子集模型同源，本页消费全字段。
 * API 资源不挂实验室（迁移未给 apis 加 lab_id，INT-487 注记），本模型无 labId。
 */
export interface ApiEndpoint {
  id: string | null
  endpoint: string
  name: string | null
  maxProcess: number | null
  maxTimeout: number | null
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

export interface ApiDevice {
  id: number
  name: string
  vendor: string | null
  description: string | null
  /** 在线/离线（§3.6 状态徽章 在线=success/离线=neutral） */
  status: string | null
  /** meta 环境（development/testing/production），§3.6 环境列；协议已抬为顶层列，不再放 meta */
  meta: Record<string, unknown>
  /** 传输协议（INT-1800：读 `apis.protocol` 列，值域 http/websocket/sse/grpc；缺失为 null → 显示「—」） */
  protocol: string | null
  /** 交互形态（INT-1800：读 `apis.streaming` 列；true = 流式，false = 非流式） */
  streaming: boolean
  environment: string | null
  /** 代理类型（http/https/socks5/socks5h；空=不代理），api.py ApiItem proxy_type 实测 */
  proxyType: string | null
  /** 代理地址（契约格式 user:pass@host:port，不含 scheme 前缀；INT-1029 前端可配置） */
  proxyUrl: string | null
  algorithmType: string | null
  defaultMaxProcess: number | null
  defaultMaxTimeout: number | null
  defaultMaxAudioDuration: number | null
  healthScore: number | null
  endpoints: ApiEndpoint[]
  /** RMS-SPL 默认映射（rms_spl_mapping_id → 映射名；未关联「去配置」link → /SPLMapping?domain=digital） */
  rmsSplMappingId: number | null
  rmsSplMappingName: string | null
  /** 「测试中」占用态（INT-487：API 统计「测试中API」口径，mock 本地装饰；不占协议/环境筛选） */
  occupied: boolean
  createdAt: string | null
  updatedAt: string | null
}

/** API 协议中文映射（§3.6 协议 Badge；INT-1800 值域收敛为 B0 的 4 个规范值） */
export const API_PROTOCOL_META: Record<string, string> = {
  http: 'HTTP',
  websocket: 'WebSocket',
  sse: 'SSE',
  grpc: 'gRPC',
}

/** API 环境中文映射（§3.6 环境 Badge） */
export const API_ENV_META: Record<string, string> = {
  development: '开发',
  testing: '测试',
  production: '生产',
}
