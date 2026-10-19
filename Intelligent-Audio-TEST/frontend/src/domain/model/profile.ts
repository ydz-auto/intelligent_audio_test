/**
 * 个人中心域模型 —— camelCase
 * 契约对位 13_个人中心（INT-358）§2.0 实测：
 *  - /auth/me → { user_id, username, role_id, permissions }（无 email、无 roleName；
 *    roleName 由前端 auth store 会话缓存兜底，authStore.ts:126 注释实测）
 *  - /auth/oauth/bindings → { bindings: [...] }（OAuthBinding 复用 domain/model/auth）
 *  - /favorites → { data: { task: [ids], report: [ids], testcase: [ids] } }
 * 本文件零后端依赖，snake_case 转换收敛在 infrastructure 层。
 */

/** 我的收藏计数（GET /favorites → data 三类 id 数组 length，per-user） */
export interface FavoriteCounts {
  task: number
  report: number
  testcase: number
}

/** 修改密码提交载荷（POST /auth/change-password，INT-794；新密码长度下限 AUTH_PASSWORD_MIN_LENGTH=6） */
export interface ChangePasswordPayload {
  currentPassword: string
  newPassword: string
}

/** 自我资料更新提交载荷（PUT /auth/self，INT-792；仅 email 白名单字段，空串=不修改） */
export interface UpdateProfilePayload {
  /** 邮箱（/auth/me INT-792 起回传；保存后即时生效） */
  email?: string
}
