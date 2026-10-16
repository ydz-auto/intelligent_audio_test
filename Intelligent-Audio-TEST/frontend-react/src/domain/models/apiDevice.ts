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
}

export interface ApiDevice {
  id: number
  name: string
  vendor: string | null
  apiUrl: string | null
  description: string | null
  /** 在线/离线（§3.6 状态徽章 在线=success/离线=neutral） */
  status: string | null
  /** meta 协议（http/https/ws/wss）与环境（开发/测试/生产），§3.6 协议/环境列 */
  meta: Record<string, unknown>
  protocol: string | null
  environment: string | null
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

/** API 协议中文映射（§3.6 协议 Badge） */
export const API_PROTOCOL_META: Record<string, string> = {
  http: 'HTTP',
  https: 'HTTPS',
  ws: 'WS',
  wss: 'WSS',
}

/** API 环境中文映射（§3.6 环境 Badge） */
export const API_ENV_META: Record<string, string> = {
  development: '开发',
  testing: '测试',
  production: '生产',
}
