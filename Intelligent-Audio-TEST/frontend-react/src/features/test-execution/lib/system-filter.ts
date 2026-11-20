/**
 * 开始测试「系统类型」筛选命中判定（INT-2650）。
 *
 * 设备 DTO 的 system 实测有两种写法：规范值 `HarmonyOS`/`Android` 与小写别名
 * `harmony`/`android`（见 features/devices/lib/device-system.ts 归一映射）。
 * 筛选值沿用 facet 的短名（`harmony`/`android`），因此比较前必须两侧都走同一归一器，
 * 否则 `'HarmonyOS'.toLowerCase() !== 'harmony'` 会把标准值设备静默筛掉。
 * 未知系统值归一后原样回退，只与同名的 facet 值命中（与展示口径一致）。
 */
import { deviceSystemLabel } from '@/features/devices/lib/device-system'

/** 设备系统筛选项（RESOURCE_SYSTEM_OPTIONS 中作用于设备的两个值） */
export type DeviceSystemFilterValue = 'android' | 'harmony'

/** 设备原始 system 值是否命中「Android / 鸿蒙」筛选项（展示归一后比较） */
export function matchesSystemFilter(
  system: string | null | undefined,
  filter: DeviceSystemFilterValue
): boolean {
  const label = deviceSystemLabel(system)
  if (label == null) return false
  return label === deviceSystemLabel(filter)
}
