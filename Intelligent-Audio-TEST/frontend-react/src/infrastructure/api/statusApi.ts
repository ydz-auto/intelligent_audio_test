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

/** 平台现无 /api/status 端点，字段恒 null → 应用层回退 window.location.origin */
const MOCK_SITE_STATUS: SiteStatusDto = {
  apiBaseUrl: null,
  serverAddress: null,
}

/**
 * TODO(API 接线, INT-620 done + client.ts 根路径): GET /api/status（对位 newAPI）。
 * 契约已落（INT-620 done，2026-10-18 审计通过）：根级挂载**无 /api/v1 前缀**，
 * status:read，输出 { api_base_url, server_address }（snake_case）。两重阻塞：
 * ① 本机常驻栈 2026-10-18 01:05 实测 /api/status 仍 404（INT-620 分支未合入运行栈）；
 * ② client.ts baseURL 恒 /api/v1 无法直达根路径——需基座 client.ts 支持根路径
 * （INT-641 子卡已派 React基座工程师）。可用后在此做 snake_case→camelCase 映射；
 * 未落前仅回退 origin（07_文档.md §2 映射表：示例地址 = 站点根 + /api/v1）。
 */
export async function fetchSiteStatus(): Promise<SiteStatusDto> {
  return MOCK_SITE_STATUS
}
