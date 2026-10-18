// -*- coding: utf-8 -*-
/**
 * 任务域全量聚合统计 —— 工作台「任务统计图表」区数据源（INT-736）
 * 自 /tasks 移交（总表 §3 B02 / React 04_控制台 §3.8），
 * 消费 GET /tasks/stats?granularity= 的 camelCase Domain（TaskDomainStats）。
 */
import { ref } from 'vue'
import { tasksPort } from '../task/tasksPort'
import type { TaskDomainStats } from '../../domain/model/task'

export function useTaskDomainStats() {
  const stats = ref<TaskDomainStats | null>(null)
  const granularity = ref('day')
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load(g: string = granularity.value) {
    granularity.value = g
    loading.value = true
    error.value = null
    try {
      stats.value = await tasksPort.getDomainStats(g)
    } catch (e: any) {
      error.value = e?.message || '任务统计暂不可用'
    } finally {
      loading.value = false
    }
  }

  function changeGranularity(g: string) {
    return load(g)
  }

  return { stats, granularity, loading, error, load, changeGranularity }
}
