// -*- coding: utf-8 -*-
/**
 * 工作台统计域 Application Port 组合 —— /dashboard 页面取数入口（INT-736）
 *
 * 依赖方向：Presentation → Application(Port) → Infrastructure(api)
 * 聚合 statsPort（/home/stats/details|summary|refresh）的 camelCase Domain 契约，
 * 供工作台平台概览/双面板/引导卡分区消费；单卡失败收敛为 error，不阻断整页
 * （逐卡降级口径照 React 04_控制台 §3.3）。
 */
import { ref } from 'vue'
import { statsPort } from '../report/statsPort'
import type { HomeStatsDetails, HomeStatsSummary } from '../../domain/model/stats'

export function useDashboardStats() {
  const details = ref<HomeStatsDetails | null>(null)
  const summary = ref<HomeStatsSummary | null>(null)
  const loadingDetails = ref(false)
  const loadingSummary = ref(false)
  const detailsError = ref<string | null>(null)
  const summaryError = ref<string | null>(null)

  async function loadDetails() {
    loadingDetails.value = true
    detailsError.value = null
    try {
      details.value = await statsPort.getStatsDetails()
    } catch (e: any) {
      detailsError.value = e?.message || '统计暂不可用'
    } finally {
      loadingDetails.value = false
    }
  }

  async function loadSummary() {
    loadingSummary.value = true
    summaryError.value = null
    try {
      summary.value = await statsPort.getStatsSummary()
    } catch (e: any) {
      summaryError.value = e?.message || '摘要暂不可用'
    } finally {
      loadingSummary.value = false
    }
  }

  async function loadAll() {
    await Promise.all([loadDetails(), loadSummary()])
  }

  /** 刷新统计（home:refresh → POST /home/stats/refresh；成功重拉全部） */
  async function refreshStats(): Promise<{ ok: boolean; message?: string }> {
    try {
      await statsPort.refreshStats()
      await loadAll()
      return { ok: true }
    } catch (e: any) {
      return { ok: false, message: e?.message || '刷新统计失败' }
    }
  }

  return {
    details,
    summary,
    loadingDetails,
    loadingSummary,
    detailsError,
    summaryError,
    loadDetails,
    loadSummary,
    loadAll,
    refreshStats,
  }
}
