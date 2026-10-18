/**
 * 站点健康状态 Domain 模型 —— INT-745（关于页）
 */
export interface HealthStatus {
  /** ok / error 等 */
  status: string
  /** 服务名（api_gateway） */
  service: string
  /** 平台版本（Config.PLATFORM_VERSION，如 V9.7.31） */
  version: string
  /** 当前数据库名 */
  database: string
}
