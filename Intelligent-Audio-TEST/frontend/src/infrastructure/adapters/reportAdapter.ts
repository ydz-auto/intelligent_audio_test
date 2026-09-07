/**
 * Report Adapter —— 组合根 / 聚合口
 *
 * ReportDto(snake_case) ⇄ Report(camelCase) 映射已按职责拆分至 report.*.ts 子模块，
 * 本文件保留原模块路径与全部具名导出，仅做 import + re-export，消费方零改动。
 * 拆分结构：
 *   - report.mapping.ts  摘要子结构与聚合根子实体转换（DTO → Domain，经组合根转发对外）
 *   - report.main.ts     摘要、主转换、列表项与对比结果转换
 *   - report.dto.ts      Domain → DTO 请求体转换（snake_case）
 *   - report.search.ts   searchCases 响应转换
 *   - report.utils.ts    内部小工具
 */
export {
  toReportSummary,
  toReport,
  toReportListItem,
  toReportListData,
  toCompareResult,
} from './report.main'
export {
  toReportUpdateDto,
  toReportSummaryFieldDto,
  toReportListQueryDto,
  toReportBatchDeleteDto,
  toReportExportDto,
  toGenerateTaskReportDto,
  toGetCaseAveragesDto,
  toReportSearchCasesDto,
} from './report.dto'
export {
  toSearchCaseItem,
  toSearchCaseResult,
} from './report.search'
export {
  toMetricConfig,
  toDetailedResult,
  toDeviceStat,
  toApiStat,
  toDeviceInfo,
  toApiInfo,
  toResourceHeader,
  toRawDataGroup,
  toMetricByResource,
  toTagMetricByResource,
  toCaseTypeStatRow,
  toCaseEntity,
  toMetricStat,
  toRawDataEntity,
  toAlgorithmResultItem,
  toReferenceParamEntry,
  toReferenceParamsDict,
  toFieldMappingItem,
  toFieldMappings,
} from './report.mapping'