/**
 * API 配置域领域模型（domain 层；10_测试执行.md §9 落位）。
 * 形态对照 api_gateway/schemas/api.py ApiItem/ApiEndpointItem 实测：
 * id/name/vendor/description/status/meta/algorithm_type/default_max_process/
 * default_max_timeout/default_max_audio_duration/health_score/endpoints/device_type
 * （INT-1223：api_url 已前后端全量移除，api_endpoints 为唯一端点配置入口）。
 * 本卡消费子集（被测 API 表格 + 编辑弹窗），完整配置域模型归设备管理页 API 页签。
 */

import type { DeviceType } from './device'

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
  deviceType: string | null
}

/** API 连接测试结果（api.py ApiHealthCheckData 平移；端点状态取 endpoints_status，INT-1223） */
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

/** API 目标设备类型派生（INT-1433）：显式 deviceType（http_api/websocket_api）优先；
 * 未显式时按首个端点协议派生（ws/wss:// → websocket_api，其余 → http_api，缺省 http_api）。
 * 建任务 case_devices 组装与 API 卡徽章/协议筛选同口径——websocket_api Realtime 路由前置。 */
export function deriveApiTargetDeviceType(
  api: Pick<ApiConfig, 'deviceType' | 'endpoints'>
): DeviceType {
  if (api.deviceType === 'websocket_api' || api.deviceType === 'http_api') return api.deviceType
  const first = api.endpoints[0]?.endpoint ?? ''
  return /^wss?:\/\//i.test(first) ? 'websocket_api' : 'http_api'
}
