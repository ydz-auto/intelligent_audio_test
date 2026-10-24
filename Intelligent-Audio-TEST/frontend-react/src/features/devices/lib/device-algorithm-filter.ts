/**
 * 测试设备 × 全局算法过滤（16_设备域.md §2.2；INT-1622）。
 * 口径＝后端 DeviceListQuery.algorithm_type 的 `supported_algorithms` contains：
 * 列表为全量拉取（GET /test-devices?per_page=1000），故在 feature 层按同一语义过滤。
 * algorithmId 为空串＝「全部算法」（useAlgorithmStore 契约），原样返回。
 */
import type { TestDevice } from '@/domain/models/testDevice'

export function filterTestDevicesByAlgorithm(
  devices: TestDevice[],
  algorithmId: string
): TestDevice[] {
  if (!algorithmId) return devices
  return devices.filter((device) => (device.supportedAlgorithms ?? []).includes(algorithmId))
}
