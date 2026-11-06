/**
 * 声压映射「可关联集合」过滤（INT-2347；播放设备编辑抽屉选项源）。
 * 与关联弹窗（INT-2343）同源：GET /spl 全量后按后端 associate_spl 的校验规则收窄——
 * `mapping.device_id` 为空或等于本设备、`device_type` 为空或等于设备类型；
 * 后端对归属他机 / 类型不匹配的映射直接 400，故不列入选项。
 * 例外：当前已关联的映射恒保留（即便归属/类型已不匹配），否则 Select 只能回显裸 id。
 */
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { SplMapping } from '@/domain/models/splMapping'

export interface SplAssociableFilter {
  /** 本播放设备 id（新增态无设备，调用方不传选项） */
  deviceId: number
  /** 本设备类型（dry/noise；未知时不做类型收窄） */
  deviceType: PlaybackDevice['deviceType'] | null
  /** 设备当前已关联的映射 id（恒保留在选项内） */
  currentMappingId?: number | null
}

export function filterAssociableSplMappings(
  mappings: SplMapping[],
  filter: SplAssociableFilter
): SplMapping[] {
  const { deviceId, deviceType, currentMappingId } = filter
  return mappings.filter((mapping) => {
    if (currentMappingId != null && mapping.id === currentMappingId) return true
    if (mapping.deviceId != null && mapping.deviceId !== deviceId) return false
    if (deviceType && mapping.deviceType && mapping.deviceType !== deviceType) return false
    return true
  })
}
