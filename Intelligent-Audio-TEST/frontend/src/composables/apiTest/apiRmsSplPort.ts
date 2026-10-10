// -*- coding: utf-8 -*-
/**
 * 接口测试域 Application Port —— API RMS→SPL 映射（数字域灵敏度校准）远程操作入口
 * 依赖方向：Presentation → Application(Port) → Infrastructure(api)
 * 现阶段为 apiRmsSplApi 的直通薄封装（camelCase Domain 契约）；
 * 后续如需缓存/编排/ReadModel，只需改本文件，消费方零改动。
 * views/ 与 components/ 禁止直连 @/infrastructure/api。
 */
import { apiRmsSplApi } from '../../infrastructure/api'

export const apiRmsSplPort = apiRmsSplApi
