/**
 * 报告分享 HTTP 客户端（infrastructure 层；15_报告域.md §3.2/§4.12）。
 * 后端端点（INT-971 已部署，api_gateway/routes/report_bp.py 实测）：
 *   POST   /reports/{id}/share           生成（ReportShareCreateRequest；recipients 逗号分隔字符串）
 *   GET    /reports/{id}/share           分享列表（含 visits/last_visited_at 访问统计）
 *   DELETE /reports/{id}/share/{token}   撤销（幂等，200 {revoked:true}）
 *   GET    /reports/shared/{token}       公开读取（200 时后端原子递增 visits——访问统计唯一入口）
 * 访问统计无独立 POST /visit 端点（:15000 实测 404）：visits 由公开读取 200 计数，
 * 前端经列表端点回读展示（fetchReportShareStats）。
 */
import type { ShareAccess, ShareExpiry } from '@/domain/models/report-share'
import { request } from './client'

/** 生成分享链接入参（权限/有效期/密码/指定访问人） */
export interface ReportShareCreateInput {
  reportId: number
  access: ShareAccess
  expiry: ShareExpiry
  password?: string
  /** 指定访问人（access='specific' 时；逗号分隔用户名/邮箱，网关经 auth ListUsers 解析） */
  recipients?: string
  /** 有效期（expiry='custom' 时必填，ISO 8601；null/undefined=不传） */
  expiresAt?: string | null
}

/** 分享信息（token + 分享 URL + 访问统计 + 有效期） */
export interface ReportShareInfo {
  token: string
  shareUrl: string
  visits: number
  lastVisitedAt: string | null
  /** 过期时间（ISO 8601；null=永久） */
  expiresAt: string | null
}

/** 分享列表项（GET /reports/{id}/share 回读；含访问统计与管理态） */
export interface ReportShareListItem {
  token: string
  access: ShareAccess
  expiresAt: string | null
  passwordSet: boolean
  visits: number
  lastVisitedAt: string | null
  revoked: boolean
  createdAt: string | null
}

/** 分享端点响应 DTO（snake_case；share_url 由网关拼接，列表项含 revoked/created_at） */
interface ReportShareDto {
  token: string
  access: string
  expires_at: string | null
  password_set: boolean
  recipients: unknown
  visits: number
  last_visited_at: string | null
  revoked?: boolean
  created_at?: string | null
  share_url?: string
}

/**
 * POST /reports/{id}/share 生成分享链接（access/expiry/password/recipients 透传）。
 * recipients 后端契约是逗号分隔字符串（access 非 specific 时传空串）；
 * 响应 share_url 的 origin 取自网关请求 base_url（dev 代理下为网关而非前端），
 * 经 buildShareUrl 以当前前端 origin 归一化保证复制出的链接可打开。
 */
export async function createReportShare(
  input: ReportShareCreateInput
): Promise<ReportShareInfo> {
  const body: Record<string, unknown> = {
    access: input.access,
    expiry: input.expiry,
    password: input.password ?? '',
    recipients: input.access === 'specific' ? (input.recipients ?? '') : '',
  }
  if (input.expiry === 'custom' && input.expiresAt) {
    body.expires_at = input.expiresAt
  }
  const dto = await request<ReportShareDto>(
    'POST',
    `/reports/${input.reportId}/share`,
    body
  )
  return {
    token: dto.token,
    shareUrl: buildShareUrl(input.reportId, dto.token, dto.share_url),
    visits: dto.visits ?? 0,
    lastVisitedAt: dto.last_visited_at ?? null,
    expiresAt: dto.expires_at ?? null,
  }
}

/** DELETE /reports/{id}/share/{token} 撤销分享（幂等：已撤销再次撤销仍 200） */
export async function revokeReportShare(reportId: number, token: string): Promise<void> {
  await request('DELETE', `/reports/${reportId}/share/${token}`)
}

/**
 * 回读当前 token 的访问统计（GET /reports/{id}/share → 列表定位 token 项）。
 * 后端无独立 POST /reports/{id}/share/{token}/visit 端点（:15000 实测 404）：
 * visits 由公开读取 GET /reports/shared/{token} 的 200 响应原子递增，此处回读真实值。
 */
export async function fetchReportShareStats(
  reportId: number,
  token: string
): Promise<{ visits: number; lastVisitedAt: string | null }> {
  const dto = await request<{ shares?: ReportShareDto[] }>(
    'GET',
    `/reports/${reportId}/share`
  )
  const share = (dto.shares ?? []).find((item) => item.token === token)
  return {
    visits: share?.visits ?? 0,
    lastVisitedAt: share?.last_visited_at ?? null,
  }
}

/**
 * 分享链接归一化：后端 share_url 的 origin 来自网关请求 base_url（dev 代理下为网关
 * 而非前端），以当前前端 origin 重拼 path+query，保证复制出的链接指向运行中的前端
 * （同源部署时两者 origin 一致，归一化无副作用；backendUrl 非法时按前端路由形态兜底）。
 */
function buildShareUrl(reportId: number, token: string, backendUrl?: string): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  if (backendUrl) {
    try {
      const url = new URL(backendUrl)
      return `${origin}${url.pathname}${url.search}`
    } catch {
      // 非标准 URL → 走前端路由形态兜底
    }
  }
  return `${origin}/report/${reportId}?share=${token}`
}
