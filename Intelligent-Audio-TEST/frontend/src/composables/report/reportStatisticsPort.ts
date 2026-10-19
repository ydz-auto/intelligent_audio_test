// -*- coding: utf-8 -*-
/**
 * 报告统计分析 Application Port —— Presentation 访问统计端点的唯一入口
 * 依赖方向：Presentation → Application(Port) → Infrastructure(api)
 * reportStatisticsApi 直通薄封装（camelCase Domain 契约）；
 * views/ 与 components/ 禁止直连 @/infrastructure/api。
 */
import { reportStatisticsApi } from '../../infrastructure/api'

export const reportStatisticsPort = reportStatisticsApi
