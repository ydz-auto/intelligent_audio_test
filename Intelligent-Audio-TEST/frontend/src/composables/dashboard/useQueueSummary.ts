// -*- coding: utf-8 -*-
/**
 * 排队状态条数据（INT-440，INT-736 工作台平台概览卡）
 *
 * 主数据源 = GET /tasks?status=queued 列表计数与队首名（近似等价队列 FIFO 口径注记）；
 * 常驻后端 `/tasks` 列表端点异常（500）时回退 GET /tasks/stats status_counts.queued 计数
 * （真实数据，非 mock），队首名置空；两路都失败静默降级 0。
 * task:read 缺失（device_admin/guest）时视图层整条隐藏。
 * 队列位置 / 插队端点待后端立项（总表 §3.3 F4），不在本卡展示。
 */
import { ref } from 'vue'
import { tasksPort } from '../task/tasksPort'
import { TaskStatus } from '../../domain/enums'

export function useQueueSummary() {
  const count = ref(0)
  const headName = ref('')
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      const result = await tasksPort.getAll({ status: TaskStatus.QUEUED, page: 1, perPage: 20 })
      count.value = result?.total ?? 0
      const items = result?.items ?? []
      // 队首 = 按创建时间升序取首条（近似等价队列 FIFO，口径注记）
      const sorted = [...items].sort((a, b) => {
        const ta = a.createdAt ? Date.parse(a.createdAt) : 0
        const tb = b.createdAt ? Date.parse(b.createdAt) : 0
        return ta - tb
      })
      headName.value = sorted[0]?.name ?? ''
    } catch {
      // /tasks 列表端点异常：回退 /tasks/stats 的 queued 计数（真实数据），队首名不可得
      try {
        const stats = await tasksPort.getDomainStats('day')
        count.value = stats?.statusCounts?.[TaskStatus.QUEUED] ?? 0
        headName.value = ''
      } catch {
        count.value = 0
        headName.value = ''
      }
    } finally {
      loading.value = false
    }
  }

  return { count, headName, loading, load }
}
