// -*- coding: utf-8 -*-
/**
 * 个人中心域 Application Port —— Presentation 访问个人中心远程操作的唯一入口
 * 依赖方向：Presentation → Application(Port) → Infrastructure(api)
 * 现阶段为 authApi（OAuth 绑定）+ favoritesApi（我的收藏）+ passwordApi/profileApi（待 FEAT 桩）的直通薄封装。
 * views/ 与 components/ 禁止直连 @/infrastructure/api。
 */
import { authApi } from '../../infrastructure/api'
import * as favoritesApi from '../../infrastructure/api/favoritesApi'
import { changeMyPassword } from '../../infrastructure/api/passwordApi'
import { updateMyProfile } from '../../infrastructure/api/profileApi'
import type { ChangePasswordPayload, UpdateProfilePayload } from '../../domain/model/profile'

export const profilePort = {
  // ===== OAuth 绑定（authApi 现成契约，INT-147）=====
  listPublicOAuthProviders: authApi.listPublicOAuthProviders,
  listOAuthBindings: authApi.listOAuthBindings,
  completeOAuthBinding: authApi.completeOAuthBinding,
  unbindOAuthProvider: authApi.unbindOAuthProvider,
  getOAuthAuthorizeUrl: authApi.getOAuthAuthorizeUrl,
  // ===== 我的收藏（favoritesApi）=====
  listFavoriteIds: favoritesApi.listFavoriteIds,
  // ===== 自助改密 / 自我资料更新（待 FEAT 桩）=====
  changeMyPassword: (payload: ChangePasswordPayload) => changeMyPassword(payload),
  updateMyProfile: (payload: UpdateProfilePayload) => updateMyProfile(payload),
}
