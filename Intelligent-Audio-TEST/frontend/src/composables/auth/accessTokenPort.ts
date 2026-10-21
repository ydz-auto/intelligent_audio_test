// -*- coding: utf-8 -*-
/**
 * Access Token 域 Application Port —— Application(store/composables/views)
 * 访问 Access Token 远程操作的唯一入口。
 * 依赖方向：Presentation → Application(Port) → Infrastructure(api)
 * 现阶段为 accessTokenApi 的直通薄封装（camelCase Domain 契约）。
 * views 禁止直连 @/infrastructure/api。
 */
import { accessTokenApi } from '../../infrastructure/api'

export const accessTokenPort = accessTokenApi
