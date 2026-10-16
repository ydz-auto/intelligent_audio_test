/**
 * 个人中心域模型（domain 层，13_个人中心.md §7）。
 * 形态对照 api_gateway/schemas 实测契约：
 *  - /auth/me → { user_id, username, role_id, permissions }（无 email、无 roleName）
 *  - /auth/oauth/bindings → { bindings: [{ provider_id, provider_name, provider_slug,
 *    provider_icon, provider_user_id }] }
 *  - /favorites → { data: { task: [ids], report: [ids], testcase: [ids] } }
 * roleName 由前端 auth store 会话缓存兜底（authStore.ts:126 注释实测）。
 */

/** 当前用户信息（profile 页消费；email 待后端立项 /auth/me 扩展后补） */
export type ProfileUserInfo = {
  id: string
  username: string
  /** 角色中文名；取前端 auth store 会话缓存，取不到显示「—」 */
  roleName: string
  /** 权限码集合；'*' 为超级通配 */
  permissions: string[]
  /** 邮箱展示待后端立项（/auth/me 不含 email），未开放前恒 undefined */
  email?: string
}

/** 第三方账号绑定（GET /auth/oauth/bindings 契约，provider_user_id 原样保留） */
export type OAuthBinding = {
  providerId: string
  providerName: string
  providerSlug: string
  providerIcon: string
  providerUserId: string
}

/** 我的收藏计数（GET /favorites → data 三类 id 数组 length） */
export type FavoriteCounts = {
  task: number
  report: number
  testcase: number
}

/** 个人数据快捷区格子（§3.3 三格，权限门槛见 permission-gate） */
export type ProfileQuickStat = {
  key: 'favorites' | 'tasks' | 'reports'
  /** 点击落点（scope=mine 等 URL 参数由列表页卡消费，未落前纯路由） */
  to: string
  /** 是否需要对应实体 read 权限（tasks→task:read / reports→report:read；收藏格恒显） */
  permission?: 'task:read' | 'report:read'
}

/** 快捷入口卡行（§3.6 四行） */
export type ProfileQuickLink = {
  key: 'dashboard' | 'settings' | 'guide' | 'about'
  to: string
  /** 系统设置行需设置域权限（SYSTEM_SETTINGS_PERMISSIONS），不满足整行隐藏 */
  permission?: string[]
}
