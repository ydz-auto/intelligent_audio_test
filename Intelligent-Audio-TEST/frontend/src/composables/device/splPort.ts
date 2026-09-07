// -*- coding: utf-8 -*-
/**
 * SPL 域 Application Port —— Presentation 访问 SPL 操作的唯一入口
 * 依赖方向：Presentation → Application(Port) → Infrastructure(api)
 * 现阶段为 splApi 的直通薄封装（camelCase Domain 契约）；
 * 后续如需缓存/编排/ReadModel，只需改本文件，消费方零改动。
 * views/ 与 components/ 禁止直连 @/infrastructure/api。
 */
import { splApi } from '../../infrastructure/api'

export const splPort = splApi