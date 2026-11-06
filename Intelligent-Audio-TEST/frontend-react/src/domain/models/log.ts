/**
 * 日志查看领域模型（domain 层；INT-693 接线落地）。
 * 形态对照 api_gateway/schemas/log.py 实测：LogItem（snake_case 序列化，
 * 经 infrastructure/dto/log.dto.ts 唯一转换层转 camelCase 进本层）、
 * LogListData(items/total/page/per_page/pages)、LogStatsData(total/debug/info/
 * warning/error/critical)、LogRefreshData(items/count/new_count/last_id)。
 * 日志页筛选条件（LogQuery）与后端 LogListQuery 逐字段对齐。
 */

export type LogItem = {
  id: number
  time: string
  level: string
  category: string
  module: string
  source: string
  content: string
  mark: string | null
  deviceId: number | null
  taskId: number | null
  apiId: number | null
  testCaseId: string | null
  threadId: string | null
  algorithmType: string | null
}

/** 日志级别（后端 LogItem.level 取值；页面列色映射见 features/logs/constants） */
export const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const

/** 日志统计（对应后端 LogStatsData；页面收敛展示 total/error/warning/info 四枚） */
export type LogStats = {
  total: number
  debug: number
  info: number
  warning: number
  error: number
  critical: number
}

export const EMPTY_LOG_STATS: LogStats = {
  total: 0,
  debug: 0,
  info: 0,
  warning: 0,
  error: 0,
  critical: 0,
}

/** 日志分页结果（对应后端 LogListData = PaginatedData[LogItem]） */
export type LogPage = {
  items: LogItem[]
  total: number
  page: number
  perPage: number
  pages: number
}

export const EMPTY_LOG_PAGE: LogPage = {
  items: [],
  total: 0,
  page: 1,
  perPage: 20,
  pages: 1,
}

/** 日志刷新结果（对应后端 LogRefreshData + db_max_id/reset_required 增量基准语义） */
export type LogRefreshResult = {
  items: LogItem[]
  count: number
  newCount: number
  lastId: number
  dbMaxId?: number
  resetRequired?: boolean
}

/**
 * 日志列表/统计查询条件（前端 Domain，camelCase；发往后端时由
 * infrastructure/dto/log.dto.ts toLogQueryDto 转 snake_case）。
 * 字段对齐后端 LogListQuery；userId 为「仅自己」视图范围附加参数
 * （后端当前无 user 维度过滤，见 INT-693 交付评论 §后端缺口）。
 */
export type LogQuery = {
  page?: number
  perPage?: number
  level?: string
  module?: string
  category?: string
  keyword?: string
  contentInclude?: string
  contentExclude?: string
  startTime?: string
  endTime?: string
  mark?: string
  deviceId?: number | string
  taskId?: number | string
  apiId?: number | string
  testCaseId?: string
  threadId?: string
  algorithmType?: string
  evaluationId?: string
  round?: string
  userId?: number | string
}

/**
 * 审计文件日志游标下界（后端 shared/logging/audit_reader.py `CURSOR_FLOOR = 10 ** 12`）。
 * id ≥ 该值的行来自审计 JSONL 文件，不属于 logs 表自增 id 空间（实测 max 6.9e6）：
 * 后端只读、不可标记——PUT /logs/mark 对纯文件游标返回 200 + data.updated=0
 * 与专用文案（契约 INT-1812 / INT-1903）。前端据此不给文件日志行标记入口，
 * 并按 updated 区分「假成功」（INT-1945）。
 */
export const LOG_FILE_CURSOR_FLOOR = 10 ** 12

/** 是否文件日志行（id 落在审计游标空间；不可标记） */
export function isFileLogId(id: number | string): boolean {
  const value = typeof id === 'number' ? id : Number(id)
  return Number.isFinite(value) && value >= LOG_FILE_CURSOR_FLOOR
}

/** 日志标记入参（PUT /logs/mark；mark 默认 'flagged' 与后端 LogMarkRequest 一致） */
export type LogMarkInput = {
  logIds: Array<string | number>
  mark?: string
}

/**
 * 行内标记点击后的目标标记值（V9.7.10 `LogViewLogic/logView.ts:418-428` 同色二次点击
 * 清除语义）：点当前已持有的同色 → `''`（`PUT /logs/mark {mark:''}` 由后端置空），
 * 否则 → 该颜色。空串不是 falsy 兜底能覆盖的值——`toLogMarkDto` 用 `??` 而非 `||`，
 * 不会被默认值 'flagged' 顶掉。
 */
export function nextLogMark(
  current: string | null | undefined,
  color: string
): string {
  return (current ?? '') === color ? '' : color
}

/**
 * 日志标记结果（PUT /logs/mark → data.updated = 实际更新行数）。
 * 文件游标行不落库 → 0（INT-1903 起后端恒带 data.updated）；混合批次按 legacy 行计数。
 * updated 为 null 表示后端未返 data（INT-1903 部署前的旧包），调用方按请求行里的
 * 历史库行数推定——不能把「没有 data」当成标记失败。
 */
export type LogMarkResult = {
  updated: number | null
}

/** 日志清除入参（POST /logs/clear；对应后端 LogClearRequest） */
export type LogClearInput = {
  beforeDatetime?: string | null
  keepMarked?: boolean
}

/** 日志导出格式（后端 LogExportRequest.format 取值 txt/json/csv/excel；中文标签选项见 features/logs/constants） */
export type LogExportFormat = 'txt' | 'json' | 'csv' | 'excel'

export type LogExportInput = {
  logIds?: Array<string | number>
  format?: LogExportFormat
}

/** 实时监控配置（§7.11；默认值 DEFAULT_REALTIME_CONFIG / 轮询档位 REALTIME_POLL_INTERVALS 见 features/logs/constants） */
export type LogRealtimeConfig = {
  /** 轮询间隔（仅 WS 不可用降级 refresh 轮询时生效；默认跟随 VITE_LOG_POLL_IDLE_MAX_MS 语义） */
  pollIntervalMs: number
  autoScroll: boolean
  /** 新日志计数 toast 开关 */
  notifyNewLogs: boolean
}

/** 日志模块选项（§4.2 模块 Select；值 = 后端 Log.module 原值；INT-1298 起移除 E2E 概念） */
export const LOG_MODULE_OPTIONS = [
  { value: 'api', label: 'API模块' },
  { value: 'device', label: '设备管理' },
] as const

/** 标记颜色选项（§4.2 标记 Select + §4.5 批量标记） */
export const LOG_MARK_OPTIONS = [
  { value: 'yellow', label: '黄色' },
  { value: 'red', label: '红色' },
  { value: 'green', label: '绿色' },
  { value: 'blue', label: '蓝色' },
] as const
