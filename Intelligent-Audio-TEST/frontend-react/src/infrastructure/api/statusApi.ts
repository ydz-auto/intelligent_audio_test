/**
 * 站点状态查询（infrastructure 层，07_文档.md §7 infrastructure/api/statusApi.ts）。
 * 对位 newAPI /api/status —— 唯一 snake_case→camelCase 转换层：
 * wire 字段 api_base_url / server_address（后端 snake_case 输出契约，
 * 前后端字段命名适配机制 §3.1）在此转 camelCase DTO 后再上抛，
 * 守「前端只见 camelCase Domain」红线。
 */

/** 站点状态 DTO（camelCase，供 application 层消费） */
export type SiteStatusDto = {
  apiBaseUrl: string | null
  serverAddress: string | null
}

/** mock：平台现无 /api/status 端点，字段恒 null → 应用层回退 window.location.origin */
const MOCK_SITE_STATUS: SiteStatusDto = {
  apiBaseUrl: null,
  serverAddress: null,
}

/**
 * TODO(API 接线): GET /api/status（对位 newAPI；后端落端点后在此做
 * snake_case→camelCase 映射：{ api_base_url, server_address } → DTO）。
 * 未落前仅回退 origin（07_文档.md §2 映射表：示例地址 = 站点根 + /api/v1）。
 */
export async function fetchSiteStatus(): Promise<SiteStatusDto> {
  return MOCK_SITE_STATUS
}
