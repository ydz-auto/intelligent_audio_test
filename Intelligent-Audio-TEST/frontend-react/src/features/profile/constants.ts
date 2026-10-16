/**
 * 个人中心页常量（features/profile，13_个人中心.md §6 文案全量 + §4.2 权限码门槛）。
 * 文案全中文硬编码（AGENTS.md §3.1）；权限码与 RBAC 矩阵同源。
 */

/** 页面级 */
export const PROFILE_PAGE_TITLE = '个人中心'
export const PROFILE_LOADING_ARIA = '正在加载个人信息'

/** 用户身份卡 */
export const COPY_USER_ID_ARIA = '复制用户 ID'
export const COPY_USER_ID_TOAST = '用户 ID 已复制'

/** 个人数据快捷条 */
export const QUICK_STAT_LABELS = {
  favorites: '我的收藏',
  tasks: '我的任务',
  reports: '我的报告',
} as const
export const QUICK_STAT_DESCRIPTIONS = {
  favorites: '任务 · 报告 · 用例',
  tasks: '我创建的任务',
  reports: '我生成的报告',
} as const
/** 任务/报告计数待后端立项前显示「查看全部」（§3.3） */
export const QUICK_STAT_PENDING_VALUE = '查看全部'

/** 收藏明细 Popover */
export const FAVORITES_POPOVER_TITLE = '我的收藏'
export const FAVORITE_ROW_LABELS = {
  task: '收藏的任务',
  report: '收藏的报告',
  testcase: '收藏的用例',
} as const
export const FAVORITES_EMPTY_TITLE = '暂无收藏内容'
export const FAVORITES_EMPTY_DESCRIPTION = '在列表页点击收藏，相关内容会显示在这里'

/** 个人信息卡 */
export const PERSONAL_INFO_TITLE = '个人信息'
export const PERSONAL_INFO_DESCRIPTION = '账号基础信息与权限概览'
export const EMAIL_PENDING_VALUE = '—'
export const EMAIL_PENDING_TOOLTIP = '邮箱展示功能开发中'
export const PERSONAL_INFO_FOOTNOTE =
  '当前页面为只读展示。如需修改用户名、邮箱或重置密码，请联系平台管理员。'

/** 权限概览 Popover */
export const PERMISSION_POPOVER_TITLE = '权限清单'
export const PERMISSION_POPOVER_DESCRIPTION = '当前账号在角色权限基础上生效的权限码'
export const PERMISSION_WILDCARD_COPY = '超级管理员持有全部权限（通配 *）'

/** 账号安全卡 */
export const ACCOUNT_SECURITY_TITLE = '账号安全'
export const ACCOUNT_SECURITY_DESCRIPTION = '登录密码与第三方账号绑定'
export const AUTH_SECTION_TITLE = '登录与认证'
export const CHANGE_PASSWORD_TITLE = '修改密码'
export const CHANGE_PASSWORD_DESCRIPTION = '更新登录密码，保护账号安全'
export const CHANGE_PASSWORD_BUTTON = '修改密码'
export const BINDINGS_SECTION_TITLE = '第三方账号绑定'
export const BINDINGS_SECTION_DESCRIPTION = '绑定后可使用对应第三方账号直接登录本账号'
export const BINDING_UNBOUND_VALUE = '未绑定'
export const BINDING_BOUND_BADGE = '已绑定'
export const BIND_BUTTON = '绑定'
export const UNBIND_BUTTON = '解绑'
export const UNBIND_CONFIRM_TITLE = '确认解绑'
export const UNBIND_CONFIRM_ACTION = '解绑'
export const UNBIND_CONFIRM_CANCEL = '取消'
export const BINDING_PROCESSING_ARIA = '正在处理'
export const BINDINGS_EMPTY_TITLE = '当前没有可绑定的第三方登录方式'
export const BINDINGS_EMPTY_DESCRIPTION = '请联系管理员在系统设置中添加 OAuth 提供方'

/** 修改密码对话框（端点就绪后；§3.5.1 未落端点前入口隐藏） */
export const CHANGE_PASSWORD_DIALOG_TITLE = '修改密码'
export const CHANGE_PASSWORD_DIALOG_FIELD_CURRENT = '当前密码'
export const CHANGE_PASSWORD_DIALOG_PLACEHOLDER_CURRENT = '请输入当前密码'
export const CHANGE_PASSWORD_DIALOG_FIELD_NEW = '新密码'
export const CHANGE_PASSWORD_DIALOG_PLACEHOLDER_NEW = '请输入新密码（至少 6 位）'
export const CHANGE_PASSWORD_DIALOG_FIELD_CONFIRM = '确认新密码'
export const CHANGE_PASSWORD_DIALOG_PLACEHOLDER_CONFIRM = '请再次输入新密码'
export const CHANGE_PASSWORD_MIN_LENGTH_MESSAGE = '新密码长度不能少于 6 位'
export const CHANGE_PASSWORD_MISMATCH_MESSAGE = '两次输入的密码不一致'
export const CHANGE_PASSWORD_SAME_MESSAGE = '新密码不能与当前密码相同'
export const CHANGE_PASSWORD_CANCEL = '取消'
export const CHANGE_PASSWORD_SAVE = '保存'
export const CHANGE_PASSWORD_SAVING = '保存中…'
export const CHANGE_PASSWORD_SUCCESS_TOAST = '密码已修改，请使用新密码重新登录'

/** 快捷入口卡 */
export const QUICK_LINKS_TITLE = '快捷入口'
export const QUICK_LINK_COPY = {
  dashboard: { label: '工作台', description: '平台概览与快捷操作' },
  settings: { label: '系统设置', description: '站点、用户与权限、认证、外观与主题等' },
  guide: { label: '使用文档', description: '使用手册与 API 手册' },
  about: { label: '关于平台', description: '平台版本与服务状态' },
} as const

/** 外观提示卡 */
export const APPEARANCE_ALERT_TITLE = '外观与主题'
export const APPEARANCE_ALERT_DESCRIPTION =
  '主题、字体、圆角、密度等外观偏好，可在右上角主题面板或「系统设置 → 外观与主题」中调整。'
