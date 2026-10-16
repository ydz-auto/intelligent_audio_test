/**
 * 设备系统归一映射（16_设备域.md §3.4/§9：系统列显 iOS/Android/HarmonyOS）。
 * DTO 实测 system 值可为小写别名（harmony/android）——展示归一为规范文案；
 * iOS 判定（isIos）用于行操作禁用（§3.4.1「iOS 设备不支持该操作」），
 * 归一映射修正恒不命中缺陷（P3-24 返修）。
 */
const SYSTEM_META: Record<string, { label: string; isIos: boolean }> = {
  iOS: { label: 'iOS', isIos: true },
  ios: { label: 'iOS', isIos: true },
  Android: { label: 'Android', isIos: false },
  android: { label: 'Android', isIos: false },
  HarmonyOS: { label: 'HarmonyOS', isIos: false },
  harmony: { label: 'HarmonyOS', isIos: false },
}

export function normalizeDeviceSystem(
  system: string | null | undefined
): { label: string; isIos: boolean } | null {
  if (!system) return null
  return SYSTEM_META[system] ?? { label: system, isIos: false }
}

/** 系统展示文案（未知值原样回退） */
export function deviceSystemLabel(system: string | null | undefined): string | null {
  return normalizeDeviceSystem(system)?.label ?? null
}

/** iOS 判定（大小写/别名归一后判定） */
export function isIosSystem(system: string | null | undefined): boolean {
  return normalizeDeviceSystem(system)?.isIos ?? false
}
