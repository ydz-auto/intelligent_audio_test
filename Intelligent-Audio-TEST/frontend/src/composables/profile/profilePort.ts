// -*- coding: utf-8 -*-
/**
 * 个人中心域 Application Port —— Presentation 访问个人中心远程操作的唯一入口
 * 依赖方向：Presentation → Application(Port) → Infrastructure(api)
 * 现阶段为 authApi（OAuth 绑定 + getMe + 改密/资料更新）+ favoritesApi（我的收藏）的直通薄封装。
 * views/ 与 components/ 禁止直连 @/infrastructure/api。
 */
import { authApi } from '../../infrastructure/api'
import * as favoritesApi from '../../infrastructure/api/favoritesApi'
import { changeMyPassword } from '../../infrastructure/api/passwordApi'
import { updateMyProfile } from '../../infrastructure/api/profileApi'
import type { ChangePasswordPayload, UpdateProfilePayload } from '../../domain/model/profile'

export const profilePort = {
  // ===== OAuth 绑定 + 当前用户信息（authApi 现成契约，INT-147 / INT-792）=====
  listPublicOAuthProviders: authApi.listPublicOAuthProviders,
  listOAuthBindings: authApi.listOAuthBindings,
  completeOAuthBinding: authApi.completeOAuthBinding,
  unbindOAuthProvider: authApi.unbindOAuthProvider,
  getOAuthAuthorizeUrl: authApi.getOAuthAuthorizeUrl,
  getMe: authApi.getMe,
  // ===== 我的收藏（favoritesApi）=====
  listFavoriteIds: favoritesApi.listFavoriteIds,
  // ===== 自助改密（POST /auth/change-password）/ 自我资料更新（PUT /auth/self）=====
  changeMyPassword: (payload: ChangePasswordPayload) => changeMyPassword(payload),
  updateMyProfile: (payload: UpdateProfilePayload) => updateMyProfile(payload),
}
