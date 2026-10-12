/**
 * 时长格式化 —— 与后端 shared/utils/event_manager/_base.py::_format_duration 同语义。
 *
 * 后端契约：start 响应 expected_total_time 为「秒」（int）；Socket/任务详情通道的
 * 同名字段为已格式化文本（如 "5分钟30秒"）。本模块是前端唯一的时长格式化出口，
 * 保证两通道对同一字段呈现一致（INT-203：数字一律按秒解释，禁止按分钟拼接）。
 */

/** 秒 → 展示文本：<=0 → "0分钟"；<60 → "X秒"；<3600 → "X分钟Y秒"；否则 "X小时Y分钟" */
export function formatDurationSeconds(secondsValue: number): string {
  const seconds = Math.floor(Number(secondsValue) || 0)
  if (seconds <= 0) return '0分钟'
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const remainSeconds = seconds % 60
    return remainSeconds > 0 ? `${minutes}分钟${remainSeconds}秒` : `${minutes}分钟`
  }
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return minutes > 0 ? `${hours}小时${minutes}分钟` : `${hours}小时`
}

/** 未知形态时长值 → 展示文本：数字按秒（start 契约）；字符串视为后端已格式化文本原样透传；空值 → '' */
export function formatDurationText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'number' && Number.isFinite(value)) return formatDurationSeconds(value)
  return String(value).trim()
}
