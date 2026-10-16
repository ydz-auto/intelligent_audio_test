/**
 * API 配置域领域模型（domain 层；10_测试执行.md §9 落位）。
 * 形态对照 api_gateway/schemas/api.py ApiItem/ApiEndpointItem 实测：
 * id/name/vendor/api_url/description/status/meta/algorithm_type/default_max_process/
 * default_max_timeout/default_max_audio_duration/health_score/endpoints/device_type。
 * 本卡消费子集（被测 API 表格 + 编辑弹窗），完整配置域模型归设备管理页 API 页签。
 */

export interface ApiEndpoint {
  id: string | null
  endpoint: string
  name: string | null
  maxProcess: number | null
  maxTimeout: number | null
  status: string | null
  healthScore: number | null
  description: string | null
}

export interface ApiConfig {
  id: number
  name: string
  vendor: string | null
  apiUrl: string | null
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
  deviceType: string | null
}

/** API 连接测试结果（api.py ApiHealthCheckData 平移） */
export interface ApiHealthCheckResult {
  id: number
  status: string
  healthScore: number | null
  apiUrlStatus: string | null
  endpointsStatus: string | null
  statusCode: number | null
  responseTime: string | null
  error: string | null
  warning: string | null
}
