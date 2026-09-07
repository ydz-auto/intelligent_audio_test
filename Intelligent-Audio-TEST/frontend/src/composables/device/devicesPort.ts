// -*- coding: utf-8 -*-
/**
 * 设备域 Application Port —— Presentation 访问设备远程操作的唯一入口
 * 依赖方向：Presentation → Application(Port) → Infrastructure(api)
 * 现阶段为 devicesApi 的直通薄封装（camelCase Domain 契约）；
 * 后续如需缓存/编排/ReadModel，只需改本文件，消费方零改动。
 * views/ 与 components/ 禁止直连 @/infrastructure/api。
 */
import { devicesApi } from '../../infrastructure/api'

export const devicesPort = devicesApi

/** 批量取全部记录的查询参数（page:1 + 默认大批量 per_page），业务语义常量化后随 Port 出口 */
export { BATCH_LIST_PARAMS } from '../../infrastructure/api'