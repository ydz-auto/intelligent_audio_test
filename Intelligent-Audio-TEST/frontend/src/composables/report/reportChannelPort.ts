/**
 * ReportChannel Port —— 报告生成 Socket 通道的应用层出口
 *
 * 薄直通封装（与 taskChannelPort 一致）：Infrastructure 的 reportChannel 单点收敛于此，
 * Presentation/Application 只许 import 本 Port；
 * 后续缓存 / 编排只需改本文件，消费方零改动。
 */
import {
  connect,
  onReportGenerated,
  offReportGenerated,
  onSecondaryCompareGenerated,
  offSecondaryCompareGenerated,
} from '../../infrastructure/socket/reportChannel'

export const reportChannelPort = {
  connect,
  onReportGenerated,
  offReportGenerated,
  onSecondaryCompareGenerated,
  offSecondaryCompareGenerated,
}
