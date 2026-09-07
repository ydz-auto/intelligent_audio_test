// -*- coding: utf-8 -*-
/**
 * 算法域 Application Port —— Presentation 访问算法远程操作的唯一入口
 *
 * 依赖方向：Presentation → Application(Port) → Infrastructure(api)
 * 现阶段为 algorithmApi 的直通薄封装（camelCase Domain 契约，
 * snake_case ⇄ camelCase 转换由 infrastructure/adapters 负责）；
 * 后续如需缓存 / 编排 / ReadModel，只需改本文件，消费方零改动。
 *
 * 注意：views/ 与 components/ 禁止直连 @/infrastructure/api，
 * 算法域操作一律 import { algorithmPort } from此处。
 */
import { algorithmApi } from '../../infrastructure/api'

export const algorithmPort = algorithmApi
