/**
 * 报告分享链路（application 层；15_报告域.md §3.2/§4.12，报告管理功能设计文档.md:254-272 实测）。
 * 分享方式=生成分享链接 / 邮件分享 / 导出后分享；权限=访问权限（仅登录/指定人/公开）× 有效期 × 访问密码；
 * 分享统计=访问次数/访问时间；链接管理和撤销。数据 mock（红线④），TODO(API 接线) 换真实端点。
 */
import { useCallback, useState } from 'react'
import { toast } from 'sonner'

export type ShareAccess = 'login' | 'specific' | 'public'
export type ShareMethod = 'link' | 'email' | 'export'
export type ShareExpiry = 'none' | '7d' | '30d' | 'custom'

export interface ReportShareState {
  open: boolean
  method: ShareMethod
  access: ShareAccess
  expiry: ShareExpiry
  password: string
  /** 指定访问人（access='specific' 时；逗号分隔用户名/邮箱，INT-596 P3：落 state 不丢弃） */
  recipients: string
  /** 邮件分享收件人（method='email' 时） */
  emailTo: string
  /** 生成的分享链接（mock 形态） */
  shareUrl: string | null
  /** 分享统计 */
  visits: number
  lastVisitedAt: string | null
}

const initialState: ReportShareState = {
  open: false,
  method: 'link',
  access: 'login',
  expiry: 'none',
  password: '',
  recipients: '',
  emailTo: '',
  shareUrl: null,
  visits: 0,
  lastVisitedAt: null,
}

export function useReportShare(reportId: number, _reportName: string) {
  const [state, setState] = useState<ReportShareState>(initialState)

  const open = useCallback(
    (method: ShareMethod = 'link') => setState((s) => ({ ...s, open: true, method })),
    []
  )
  const close = useCallback(() => setState((s) => ({ ...s, open: false })), [])
  const patch = useCallback((partial: Partial<ReportShareState>) => {
    setState((s) => ({ ...s, ...partial }))
  }, [])

  /** 生成分享链接（mock：仅登录/指定人/公开 × 有效期 × 密码；复制到剪贴板） */
  const generateShareLink = useCallback(async () => {
    const token = `r${reportId}-${Date.now().toString(36)}`
    const shareUrl = `${window.location.origin}/report/${reportId}?share=${token}`
    setState((s) => ({ ...s, shareUrl, visits: 0, lastVisitedAt: null }))
    try {
      await navigator.clipboard?.writeText(shareUrl)
      toast.success('链接已复制')
    } catch {
      toast.success('分享链接已生成')
    }
    // TODO(API 接线): POST /reports/{id}/share（权限/有效期/密码落库），撤销 DELETE
  }, [reportId])

  const revokeShare = useCallback(() => {
    setState((s) => ({ ...s, shareUrl: null, visits: 0, lastVisitedAt: null }))
    toast.success('分享链接已撤销')
  }, [])

  /** 模拟访问统计（分享统计=访问次数/访问时间；演示态点击即 +1） */
  const recordVisit = useCallback(() => {
    setState((s) => ({
      ...s,
      visits: s.visits + 1,
      lastVisitedAt: new Date().toISOString(),
    }))
  }, [])

  return {
    shareState: state,
    openShare: open,
    closeShare: close,
    patchShare: patch,
    generateShareLink,
    revokeShare,
    recordVisit,
  }
}
