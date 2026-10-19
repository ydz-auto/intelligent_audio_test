/**
 * 报告分享 HTTP 客户端（infrastructure 层；15_报告域.md §3.2/§4.12）。
 * 后端暂无分享端点（POST /reports/{id}/share 实测 404）→ 本层留桩 // 待接线，
 * 桩返回符合后端 schema 的示例（token/URL/统计）；接真实端点后改为 request 调用。
 * FEAT 卡：报告分享生成/撤销/统计端点立项。
 */
import type { ShareAccess, ShareExpiry } from '@/domain/models/report-share'

/** 生成分享链接入参（权限/有效期/密码/指定访问人） */
export interface ReportShareCreateInput {
  reportId: number
  access: ShareAccess
  expiry: ShareExpiry
  password?: string
  recipients?: string
}

/** 分享信息（token + 分享 URL + 访问统计） */
export interface ReportShareInfo {
  token: string
  shareUrl: string
  visits: number
  lastVisitedAt: string | null
}

/** 生成分享链接（待接线：POST /api/v1/reports/{id}/share；桩返回示例） */
export async function createReportShare(
  input: ReportShareCreateInput
): Promise<ReportShareInfo> {
  // 待接线：真实端点立项后改为
  //   return request<ReportShareInfoDto>('POST', `/reports/${input.reportId}/share`, body)
  void input
  const token = `r${input.reportId}-${Date.now().toString(36)}`
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return {
    token,
    shareUrl: `${origin}/report/${input.reportId}?share=${token}`,
    visits: 0,
    lastVisitedAt: null,
  }
}

/** 撤销分享链接（待接线：DELETE /api/v1/reports/{id}/share/{token}；桩无副作用） */
export async function revokeReportShare(reportId: number, token: string): Promise<void> {
  // 待接线：真实端点立项后改为 request('DELETE', `/reports/${reportId}/share/${token}`)
  void reportId
  void token
}

/** 记录一次访问（分享统计；待接线：POST /api/v1/reports/{id}/share/{token}/visit，桩返回 +1） */
export async function recordReportShareVisit(
  reportId: number,
  token: string,
  currentVisits = 0
): Promise<{ visits: number; lastVisitedAt: string }> {
  // 待接线：真实端点立项后改为 request('POST', `/reports/${reportId}/share/${token}/visit`)
  void reportId
  void token
  return { visits: currentVisits + 1, lastVisitedAt: new Date().toISOString() }
}
