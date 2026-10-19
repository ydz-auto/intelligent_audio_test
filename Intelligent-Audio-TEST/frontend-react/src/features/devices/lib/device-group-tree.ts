/**
 * 设备分组树工具（features/devices 层；INT-864 承接 INT-832 嵌套分组）。
 * 分组列表接口返回嵌套树（adapter 按 parent_id 建），分组 facet 等扁平消费处
 * 用 flattenDeviceGroups 摊平；按分组引用查找用 findDeviceGroup（含子分组）。
 */
import type { DeviceGroup } from '@/domain/models/deviceGroup'

/** 嵌套分组树 → 扁平列表（保持先序遍历顺序） */
export function flattenDeviceGroups(
  groups: DeviceGroup[],
  acc: DeviceGroup[] = []
): DeviceGroup[] {
  for (const group of groups) {
    acc.push(group)
    flattenDeviceGroups(group.children, acc)
  }
  return acc
}

/** 在嵌套分组树中按 id 查找（含子分组；找不到返回 undefined） */
export function findDeviceGroup(
  groups: DeviceGroup[],
  id: string
): DeviceGroup | undefined {
  for (const group of groups) {
    if (group.id === id) return group
    const found = findDeviceGroup(group.children, id)
    if (found) return found
  }
  return undefined
}
