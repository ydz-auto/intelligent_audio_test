/**
 * 设备管理页 mock 常量（infrastructure 层）。
 * 设备/告警/分组等已切真实后端端点（devicesApi 接线 INT-644），本文件仅保留
 * 后端未立项/未覆盖的数据源：
 * - MOCK_LABORATORIES：laboratories CRUD 后端待立项（INT-487 §11-24，FEAT 证据见 INT-644）
 * - DeviceStatsPoint / MOCK_DEVICE_STATS：历史监控统计分析 vChart 采点（无实时监控指标端点）
 * 其余 mock 数据（测试/播放设备、告警、分组、状态历史）已删除，避免 mock/api 双口径并存。
 */
import type { LaboratoryDto } from '@/infrastructure/dto/laboratory.dto'
import { laboratoryFromDto } from '@/infrastructure/adapters/laboratoryAdapter'
import type { Laboratory } from '@/domain/models/laboratory'

/* ==================== 实验室（§6.26；INT-487 后端待立项，mock 先行） ==================== */

export const MOCK_LABORATORIES_DTO: LaboratoryDto[] = [
  {
    id: 1, code: 'LAB-A', name: '声学实验室 A', building: '研发中心东区', floor: '3 层',
    room_number: 'A301', description: '标准声学测试间，含消声室与远场 12 米位。', status: 'active',
    device_count: 5, playback_device_count: 2, test_case_count: 36,
    created_at: '2026-09-01T09:00:00', updated_at: '2026-10-12T10:00:00',
  },
  {
    id: 2, code: 'LAB-B', name: '多设备实验室 B', building: '研发中心东区', floor: '2 层',
    room_number: 'B205', description: '车载/多设备并行测试工位。', status: 'active',
    device_count: 3, playback_device_count: 1, test_case_count: 18,
    created_at: '2026-09-05T09:00:00', updated_at: '2026-10-10T10:00:00',
  },
  {
    id: 3, code: 'LAB-C', name: '噪声实验室 C', building: '研发中心西区', floor: '1 层',
    room_number: 'C101', description: '高噪声环境测试间，维护中。', status: 'maintenance',
    device_count: 1, playback_device_count: 0, test_case_count: 4,
    created_at: '2026-09-12T09:00:00', updated_at: '2026-10-14T10:00:00',
  },
]

export const MOCK_LABORATORIES: Laboratory[] = MOCK_LABORATORIES_DTO.map(laboratoryFromDto)

/* ==================== 历史监控统计分析（§3.7：可用性/性能/错误/使用统计 vChart 区） ==================== */

/** 统计分析采点（设备管理:411-429；mock 日粒度时间序列，接线后换实时监控指标端点） */
export interface DeviceStatsPoint {
  date: string
  availability: number
  cpu: number
  memory: number
  battery: number
  errors: number
  operations: number
}

export const MOCK_DEVICE_STATS: DeviceStatsPoint[] = [
  { date: '10-11', availability: 96, cpu: 38, memory: 52, battery: 78, errors: 1, operations: 4 },
  { date: '10-12', availability: 98, cpu: 41, memory: 55, battery: 74, errors: 0, operations: 6 },
  { date: '10-13', availability: 94, cpu: 47, memory: 61, battery: 69, errors: 2, operations: 5 },
  { date: '10-14', availability: 99, cpu: 35, memory: 48, battery: 82, errors: 0, operations: 8 },
  { date: '10-15', availability: 97, cpu: 44, memory: 58, battery: 71, errors: 1, operations: 7 },
  { date: '10-16', availability: 95, cpu: 52, memory: 66, battery: 63, errors: 3, operations: 9 },
  { date: '10-17', availability: 93, cpu: 49, memory: 62, battery: 66, errors: 2, operations: 10 },
]
