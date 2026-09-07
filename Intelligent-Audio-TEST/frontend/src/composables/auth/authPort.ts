// -*- coding: utf-8 -*-
/**
 * 认证域 Application Port —— Application(store/composables) 访问认证远程操作的唯一入口
 * 依赖方向：Presentation → Application(store) → Application(Port) → Infrastructure(api)
 * 现阶段为 authApi 的直通薄封装（camelCase Domain 契约）；
 * 后续如需 token 刷新/会话编排，只需改本文件，消费方零改动。
 * store/ 与 views/components 禁止直连 @/infrastructure/api。
 */
import { authApi } from '../../infrastructure/api'

export const authPort = authApi
