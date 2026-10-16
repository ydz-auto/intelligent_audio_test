// -*- coding: utf-8 -*-
/**
 * Benchmark 报告域 Application Port —— Presentation 访问 Benchmark 报告远程操作的唯一入口
 * 依赖方向：Presentation → Application(Port) → Infrastructure(api)
 * 现阶段为 benchmarkReportsApi 的直通薄封装（camelCase Domain 契约）；
 * views/ 与 components/ 禁止直连 @/infrastructure/api。
 */
import { benchmarkReportsApi } from '../../infrastructure/api'

export const benchmarkReportsPort = benchmarkReportsApi
