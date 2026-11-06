/**
 * Access Token 管理区常量（features/profile/components/access-token，INT-1153）。
 * 文案全中文硬编码（AGENTS.md §3.1），对齐 INT-1140 规格与 new-api 令牌管理做法。
 */

/** 卡片级 */
export const ACCESS_TOKENS_TITLE = 'Access Token'
export const ACCESS_TOKENS_DESCRIPTION =
  '使用 Access Token 让外部 agent（Claude Code / Codex 等）经 skill / MCP 调用平台能力。每个 Token 只拥有你选择的权限。'
export const ACCESS_TOKENS_CREATE_BUTTON = '创建 Access Token'
export const ACCESS_TOKENS_CREATE_ARIA = '创建新的 Access Token'

/** 列表 */
export const ACCESS_TOKEN_EXPIRED_LABEL = '已过期'
export const ACCESS_TOKEN_NEVER_EXPIRES_LABEL = '永不过期'
export const ACCESS_TOKEN_NEVER_USED_LABEL = '从未使用'
export const ACCESS_TOKEN_LAST_USED_LABEL = '最近使用'
export const ACCESS_TOKEN_ENABLED_BADGE = '已启用'
export const ACCESS_TOKEN_DISABLED_BADGE = '已停用'
export const ACCESS_TOKEN_TOGGLE_ABLE = '启用'
export const ACCESS_TOKEN_TOGGLE_DISABLE = '停用'
export const ACCESS_TOKEN_EDIT_ARIA = '编辑 Access Token'
export const ACCESS_TOKEN_DELETE_ARIA = '删除 Access Token'
export const ACCESS_TOKEN_MORE_ARIA = '打开 Access Token 操作菜单'

/** 空态 */
export const ACCESS_TOKENS_EMPTY_TITLE = '暂无 Access Token'
export const ACCESS_TOKENS_EMPTY_DESCRIPTION =
  '创建后可在入口页面下载 skill，让外部 agent 通过 skill / MCP 调用平台能力。'

/** 加载 / 错误 */
export const ACCESS_TOKENS_LOADING_ARIA = '正在加载 Access Token 列表'
export const ACCESS_TOKENS_ERROR_TITLE = 'Access Token 加载失败'
export const ACCESS_TOKENS_RETRY = '重试'

/** 创建对话框 */
export const ACCESS_TOKEN_CREATE_TITLE = '创建 Access Token'
export const ACCESS_TOKEN_CREATE_DESCRIPTION =
  'Token 明文只显示一次，请创建后立即复制保存。'
export const ACCESS_TOKEN_NAME_FIELD = '名称'
export const ACCESS_TOKEN_NAME_PLACEHOLDER = '例如：Claude Code 脚本'
export const ACCESS_TOKEN_NAME_REQUIRED = '请输入名称'
export const ACCESS_TOKEN_NAME_TOO_LONG = '名称不能超过 64 个字符'
export const ACCESS_TOKEN_EXPIRY_FIELD = '有效时间'
export const ACCESS_TOKEN_EXPIRY_PRESETS = [
  { value: '30d', label: '30 天' },
  { value: '90d', label: '90 天' },
  { value: '180d', label: '180 天' },
  { value: '1y', label: '1 年' },
  { value: 'custom', label: '自定义' },
  { value: 'never', label: '永不过期' },
] as const
export const ACCESS_TOKEN_EXPIRY_NEVER_HINT =
  '永不过期的 Token 一直有效，直到你手动删除。建议尽可能设置有效时间。'
export const ACCESS_TOKEN_CUSTOM_EXPIRY_REQUIRED = '请选择自定义有效时间'
export const ACCESS_TOKEN_CUSTOM_EXPIRY_MIN_HINT = '有效时间需晚于当前时间至少 1 小时'
export const ACCESS_TOKEN_SCOPES_FIELD = '权限'
export const ACCESS_TOKEN_SCOPES_REQUIRED = '请至少选择一个权限'
export const ACCESS_TOKEN_CANCEL = '取消'
export const ACCESS_TOKEN_CREATE_SUBMIT = '创建'
export const ACCESS_TOKEN_CREATING = '创建中…'
export const ACCESS_TOKEN_CREATE_SUCCESS = 'Access Token 已创建'

/** 明文展示对话框 */
export const ACCESS_TOKEN_REVEAL_TITLE = 'Access Token 已创建'
export const ACCESS_TOKEN_REVEAL_DESCRIPTION =
  '请立即复制保存。此明文只会显示一次，之后无法再次查看。'
export const ACCESS_TOKEN_FIELD = 'Token'
export const ACCESS_TOKEN_COPY = '复制 Token'
export const ACCESS_TOKEN_COPIED = '已复制'
export const ACCESS_TOKEN_CLOSE = '关闭'

/** 编辑对话框 */
export const ACCESS_TOKEN_EDIT_TITLE = '编辑 Access Token'
export const ACCESS_TOKEN_EDIT_DESCRIPTION =
  '修改名称、权限与有效时间；停用后使用该 Token 的请求将立即失效。'
export const ACCESS_TOKEN_EDIT_SAVE = '保存'
export const ACCESS_TOKEN_EDIT_SAVING = '保存中…'
export const ACCESS_TOKEN_EDIT_SAVE_SUCCESS = 'Access Token 已更新'

/** 删除确认 */
export const ACCESS_TOKEN_DELETE_TITLE = '删除 Access Token'
export const ACCESS_TOKEN_DELETE_DESCRIPTION =
  '删除后使用该 Token 的脚本将立即失效，且无法恢复。确定删除？'
export const ACCESS_TOKEN_DELETE_CONFIRM = '删除'
export const ACCESS_TOKEN_DELETE_SUCCESS = 'Access Token 已删除'
