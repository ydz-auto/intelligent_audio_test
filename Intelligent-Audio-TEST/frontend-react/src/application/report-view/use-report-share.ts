/**
 * 报告分享链路（application 层；15_报告域.md §3.2/§4.12，报告管理功能设计文档.md:254-272 实测）。
 * 分享方式=生成分享链接 / 导出后分享（邮件分享本版本不实现，前端隐藏入口）；
 * 权限=访问权限（仅登录/指定人/公开）× 有效期 × 访问密码；
 * 分享统计=访问次数/访问时间；链接管理和撤销。数据经 infrastructure/api/report-share-api.ts
 * 获取（INT-971 端点已部署：生成 POST /reports/{id}/share、撤销 DELETE …/share/{token}、
 * 统计 GET /reports/{id}/share 回读）。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  createReportShare,
  fetchReportShareStats,
  revokeReportShare,
} from '@/infrastructure/api/report-share-api'
import { ApiError } from '@/infrastructure/api/api-error'
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
  /** 自定义有效期（expiry='custom' 时必填；datetime-local naive 形态 ISO 8601，后端按东八区解析） */
  expiresAt: string | null
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
  expiresAt: null,
  shareToken: null,
  shareUrl: null,
  visits: 0,
  lastVisitedAt: null,
}

export function useReportShare(reportId: number, _reportName: string) {
  const [state, setState] = useState<ReportShareState>(initialState)
  // 回调内读取最新 state（generate/revoke/refreshStats 依赖当前表单值）
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

  /** 生成分享链接（POST /reports/{id}/share；成功后写 URL + 复制到剪贴板；失败 toast 后端文案） */
  const generateShareLink = useCallback(async () => {
    const s = stateRef.current
    if (s.expiry === 'custom' && !s.expiresAt) {
      toast.error('请选择自定义有效期的日期时间')
      return
    }
    try {
      const info = await createReportShare({
        reportId,
        access: s.access,
        expiry: s.expiry,
        expiresAt: s.expiry === 'custom' ? s.expiresAt : null,
        password: s.password,
        recipients: s.recipients,
      })
      setState((prev) => ({
        ...prev,
        shareToken: info.token,
        shareUrl: info.shareUrl,
        visits: info.visits,
        lastVisitedAt: info.lastVisitedAt,
        expiresAt: info.expiresAt,
      }))
      try {
        await navigator.clipboard?.writeText(info.shareUrl)
        toast.success('链接已复制')
      } catch {
        toast.success('分享链接已生成')
      }
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.userMessage : '生成分享链接失败，请重试'
      )
    }
  }, [reportId])

  /** 撤销分享链接（DELETE /reports/{id}/share/{token}；失败 toast 不清态） */
  const revokeShare = useCallback(async () => {
    const s = stateRef.current
    if (!s.shareToken) {
      setState((prev) => ({ ...prev, shareToken: null, shareUrl: null, visits: 0, lastVisitedAt: null, expiresAt: null }))
      toast.success('分享链接已撤销')
      return
    }
    try {
      await revokeReportShare(reportId, s.shareToken)
      setState((prev) => ({ ...prev, shareToken: null, shareUrl: null, visits: 0, lastVisitedAt: null, expiresAt: null }))
      toast.success('分享链接已撤销')
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.userMessage : '撤销分享链接失败，请重试'
      )
    }
  }, [reportId])

  /** 刷新分享统计（GET /reports/{id}/share 回读当前 token 的 visits/last_visited_at；后端无独立 visit 端点） */
  const refreshStats = useCallback(async () => {
    const s = stateRef.current
    if (!s.shareToken) return
    try {
      const stat = await fetchReportShareStats(reportId, s.shareToken)
      setState((prev) => ({ ...prev, visits: stat.visits, lastVisitedAt: stat.lastVisitedAt }))
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.userMessage : '刷新分享统计失败，请重试'
      )
    }
  }, [reportId])

  return {
    shareState: state,
    openShare: open,
    closeShare: close,
    patchShare: patch,
    generateShareLink,
    revokeShare,
    refreshStats,
  }
}
