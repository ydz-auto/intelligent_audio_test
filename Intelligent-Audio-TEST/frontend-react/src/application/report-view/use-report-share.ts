/**
 * 报告分享链路（application 层；15_报告域.md §3.2/§4.12，报告管理功能设计文档.md:254-272 实测）。
 * 分享方式=生成分享链接 / 邮件分享 / 导出后分享；权限=访问权限（仅登录/指定人/公开）× 有效期 × 访问密码；
 * 分享统计=访问次数/访问时间；链接管理和撤销。数据经 infrastructure/api/report-share-api.ts
 * 获取（后端分享端点待立项 → 本层只编排不造数据；FEAT 卡跟踪）。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  createReportShare,
  recordReportShareVisit,
  revokeReportShare,
} from '@/infrastructure/api/report-share-api'
import type {
  ShareAccess,
  ShareExpiry,
  ShareMethod,
} from '@/domain/models/report-share'

export type { ShareAccess, ShareExpiry, ShareMethod } from '@/domain/models/report-share'

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
  /** 分享 token（infra 生成；撤销/统计凭据） */
  shareToken: string | null
  /** 生成的分享链接（infra 返回） */
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
  shareToken: null,
  shareUrl: null,
  visits: 0,
  lastVisitedAt: null,
}

export function useReportShare(reportId: number, _reportName: string) {
  const [state, setState] = useState<ReportShareState>(initialState)
  // 回调内读取最新 state（generate/revoke/recordVisit 依赖当前表单值）
  const stateRef = useRef(state)
  useEffect(() => {
    stateRef.current = state
  }, [state])

  const open = useCallback(
    (method: ShareMethod = 'link') => setState((s) => ({ ...s, open: true, method })),
    []
  )
  const close = useCallback(() => setState((s) => ({ ...s, open: false })), [])
  const patch = useCallback((partial: Partial<ReportShareState>) => {
    setState((s) => ({ ...s, ...partial }))
  }, [])

  /** 生成分享链接（经 infra 桩 createReportShare；成功后写 URL + 复制到剪贴板） */
  const generateShareLink = useCallback(async () => {
    const s = stateRef.current
    const info = await createReportShare({
      reportId,
      access: s.access,
      expiry: s.expiry,
      password: s.password,
      recipients: s.recipients,
    })
    setState((prev) => ({
      ...prev,
      shareToken: info.token,
      shareUrl: info.shareUrl,
      visits: info.visits,
      lastVisitedAt: info.lastVisitedAt,
    }))
    try {
      await navigator.clipboard?.writeText(info.shareUrl)
      toast.success('链接已复制')
    } catch {
      toast.success('分享链接已生成')
    }
  }, [reportId])

  /** 撤销分享链接（经 infra 桩 revokeReportShare） */
  const revokeShare = useCallback(async () => {
    const s = stateRef.current
    if (s.shareToken) {
      await revokeReportShare(reportId, s.shareToken)
    }
    setState((prev) => ({ ...prev, shareToken: null, shareUrl: null, visits: 0, lastVisitedAt: null }))
    toast.success('分享链接已撤销')
  }, [reportId])

  /** 记录一次访问（分享统计；经 infra 桩 recordReportShareVisit，演示态点击 +1） */
  const recordVisit = useCallback(async () => {
    const s = stateRef.current
    if (!s.shareToken) return
    const stat = await recordReportShareVisit(reportId, s.shareToken, s.visits)
    setState((prev) => ({ ...prev, visits: stat.visits, lastVisitedAt: stat.lastVisitedAt }))
  }, [reportId])

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
