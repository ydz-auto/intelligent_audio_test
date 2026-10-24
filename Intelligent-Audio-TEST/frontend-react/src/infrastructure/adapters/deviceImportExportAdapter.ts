/**
 * 导入结果 DTO→Domain 适配器（infrastructure/adapters 层；INT-1624 接 INT-816）。
 * 消费 device-import-export.dto.ts 的 snake_case 类型，产出 domain 模型；
 * 后端 errors 可能为 null（无错误行），统一收敛为空数组。
 */
import type { DeviceImportResult } from '@/domain/models/deviceImportExport'
import type { DeviceImportResultDto } from '@/infrastructure/dto/device-import-export.dto'

export function deviceImportResultFromDto(dto: DeviceImportResultDto): DeviceImportResult {
  return {
    importedCount: dto.imported_count ?? 0,
    updatedCount: dto.updated_count ?? 0,
    skippedCount: dto.skipped_count ?? 0,
    errors: (dto.errors ?? []).map((item) => String(item)),
  }
}
