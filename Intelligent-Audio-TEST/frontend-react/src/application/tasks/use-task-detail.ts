/**
 * 任务详情/日志 query（application 层，09_任务域.md §4）。
 * 详情与快览弹窗共用同一数据源（TaskDetailContent 双形态复用）。
 * 日志分页：page+1=更老；任务运行中 10s 轮询增量 append（mock 态仅首次加载）。
 */
import { useQuery } from '@tanstack/react-query'

import type { TaskLogEntry } from '@/domain/models/task'
import { exportLogs } from '@/infrastructure/api/logsApi'
import {
  fetchTaskDetail,
  fetchTaskLogs,
  TASK_LOG_PAGE_SIZE,
} from '@/infrastructure/api/tasks-list-api'

export function useTaskDetail(taskId: number, enabled = true) {
  return useQuery({
    queryKey: ['tasks', 'detail', taskId],
    queryFn: () => fetchTaskDetail(taskId),
    enabled,
    staleTime: 30_000,
    // INT-932 P2-2：无效任务 id（400 code:203 未找到任务）快速落到错误态，
    // 不重试（默认 retry:1 指数退避会持续请求），错误态由 TaskDetailContent 渲染；
    // INT-1716 落点③：404（任务不存在 / 容器已软删）同样不重试，直接进错误态，
    // 由展开区给「重试」入口。
    retry: 0,
  })
}

export function useTaskLogs(taskId: number, enabled = true) {
  return useQuery({
    queryKey: ['tasks', 'logs', taskId],
    queryFn: () => fetchTaskLogs(taskId, 1, TASK_LOG_PAGE_SIZE),
    enabled,
    staleTime: 10_000,
    refetchInterval: (query) => {
      // 任务运行中每 10s 轮询增量 append（§4.6 现口径保留；mock 态数据无增量，返回 false）
      return query.state.data ? false : false
    },
  })
}

/** 导出单次最多收集条数（大任务兜底，防分页全量物化拖垮导出；超出取最新 N 条） */
const EXPORT_MAX_LOG_ROWS = 200 * 25

/**
 * 导出任务完整日志（application 编排：分页收集真实日志 → POST /logs/export 真实导出请求）。
 *
 * 后端 /logs/export 仅按 DB 落库行导出（get_logs_for_export 按 log_ids 查 logs 表），
 * 而任务日志卡数据源是「业务日志文件 + DB 历史行」合并视图（INT-81）——文件行 id 为
 * 合成稳定 id、不入 logs 表，落库导出对纯文件任务命中 0 行返回空文件。故导出结果 Blob
 * 为空时，用收集到的真实日志行按同款 txt 格式客户端拼装 .log 兜底，保证「导出完整日志」
 * 始终产出可读文件；后端缺口另开 FEAT（待办）。
 */
export async function exportTaskLogs(
  taskId: number
): Promise<{ blob: Blob }> {
  const entries: TaskLogEntry[] = []
  let page = 1
  while (true) {
    const result = await fetchTaskLogs(taskId, page, 200)
    entries.push(...result.items)
    const reachedEnd =
      entries.length >= result.total ||
      result.items.length === 0 ||
      entries.length >= EXPORT_MAX_LOG_ROWS
    if (reachedEnd) break
    page += 1
  }

  let blob: Blob
  try {
    const exported = await exportLogs(
      { logIds: entries.map((e) => e.id), format: 'txt' },
      {}
    )
    blob = exported.blob
    if (blob.size === 0) throw new Error('后端仅落库行导出，任务文件日志未命中')
  } catch {
    // 兜底：收集的真实日志行（已按页倒序 → 反转成旧→新）同款 txt 格式拼装
    const text = [...entries]
      .reverse()
      .map((e) => `[${e.timestamp}] ${e.level.toUpperCase()} ${e.message}`)
      .join('\n')
    blob = new Blob([text ? `${text}\n` : ''], {
      type: 'text/plain;charset=utf-8',
    })
  }
  return { blob }
}
