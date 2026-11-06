/**
 * 日志导出文件名（application 层；INT-1947）。
 * 日期取**本地时区**——原实现用 `toISOString().slice(0, 10)`（UTC），CST 00:00–08:00
 * 导出会落到前一天（实测 2026-10-26 04:0x CST 导出得到 logs_2026-10-25.txt）。
 * 文件名口径与其它导出页一致：`logs_{YYYY-MM-DD}.{format}`。
 */

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

/** 本地时区的 YYYY-MM-DD（不经过 UTC 换算） */
export function toLocalDateString(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** 导出文件名：logs_{本地日期}.{format} */
export function formatLogsExportFilename(date: Date, format: string): string {
  return `logs_${toLocalDateString(date)}.${format}`
}
