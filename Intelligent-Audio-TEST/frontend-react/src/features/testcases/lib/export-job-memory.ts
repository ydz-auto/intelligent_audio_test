/**
 * 在办导出作业的本地记忆（INT-2315 契约第 8 条）。
 *
 * 导出作业在服务端跑，关弹窗 / 切页 / 刷新都不影响；但后端没有「列出我的作业」端点，
 * 重开弹窗时只能靠本地记下的 task_id 继续跟踪。用 sessionStorage（同标签页跨刷新保留、
 * 不跨标签页串味），键带版本号与域前缀，取值失败（隐私模式 / 配额满）一律当作没有记忆。
 */

const STORAGE_KEY = 'iatp:testcase-export:job:v1'

/** 记忆有效期：产物 TTL 2h，超过这个时间的记录不再提示（任务多半已过期） */
const MEMORY_TTL_MS = 60 * 60 * 1000

export interface ActiveExportJobRecord {
  taskId: string
  /** 提交时的请求条数（用于进度区 / 成功文案兜底） */
  total: number
  /** 提交时的格式（重新跟踪时的 MIME 与音频核对口径） */
  format: string
  /** 提交时是否勾了「包含音频文件」 */
  includeAudios: boolean
  /** 提交时间（epoch ms） */
  startedAt: number
}

function readRaw(): unknown {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

/** 读取在办作业记忆（无记录 / 记录损坏 / 已超时 → null） */
export function readActiveExportJob(now = Date.now()): ActiveExportJobRecord | null {
  const value = readRaw()
  if (value == null || typeof value !== 'object') return null
  const record = value as Partial<ActiveExportJobRecord>
  if (typeof record.taskId !== 'string' || record.taskId === '') return null
  if (typeof record.startedAt !== 'number') return null
  if (now - record.startedAt > MEMORY_TTL_MS) {
    clearActiveExportJob()
    return null
  }
  return {
    taskId: record.taskId,
    total: typeof record.total === 'number' ? record.total : 0,
    format: typeof record.format === 'string' ? record.format : 'zip',
    includeAudios: record.includeAudios === true,
    startedAt: record.startedAt,
  }
}

/** 记下在办作业（终态时清除） */
export function rememberActiveExportJob(record: ActiveExportJobRecord): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(record))
  } catch {
    // 存不下不影响本次跟踪，只是重开弹窗后无法续跟
  }
}

/** 清除在办作业记忆（完成 / 失败 / 过期） */
export function clearActiveExportJob(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // 忽略
  }
}
