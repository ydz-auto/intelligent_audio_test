/**
 * 测试设备连接方式展示文案（16_设备域.md §9：USB连接/远程连接）。
 * 接口 connection_type 可为 null（实测 id 12），null / 未知值与「USB连接」区分，
 * 统一返回 null 由调用方显「—」，避免显示与筛选口径不一致（INT-2187）。
 */
const CONNECTION_TYPE_LABELS: Record<string, string> = {
  usb: 'USB连接',
  remote: '远程连接',
}

export function connectionTypeLabel(
  value: string | null | undefined
): string | null {
  return value ? (CONNECTION_TYPE_LABELS[value] ?? null) : null
}
