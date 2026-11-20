/**
 * Skill 管理页文案与常量（features/agent-skills）。
 *
 * 文案全中文；页面只通过本文件取文案，避免散落魔法字符串。错误码 → 文案的
 * 映射集中在这里（方案 §4.4 的 SkillIssueCode / SkillErrorCode，INT-2549
 * 后端枚举），页面与弹窗一律按 code 查表，不散落字符串。
 */
import type { SkillScope } from '@/domain/models/agentSkill'

/** 页面路由 */
export const AGENT_SKILLS_ROUTE = '/agent-skills'

/** 管理权限码（路由守卫 / 导航 / 入口按钮同一集合，与网关注册一致） */
export const AGENT_SKILL_MANAGE_PERMISSION = 'agent:skill:manage'

/** 导入包体积上限（与后端 AGENT_SKILL_MAX_UPLOAD_BYTES 缺省一致，用于前置提示） */
export const SKILL_UPLOAD_MAX_BYTES = 5 * 1024 * 1024

/** 校验问题码 → 中文文案（SkillIssueCode；未知码回退服务端 message） */
export const SKILL_ISSUE_CODE_COPY: Record<string, string> = {
  INVALID_NAME: '名称格式不合法',
  MISSING_NAME: '缺少名称',
  NAME_CONFLICT: '与已有 Skill 重名',
  DUPLICATE_NAME: '同一作用域内重名',
  MISSING_DESCRIPTION: '缺少描述',
  MISSING_REQUIRED_SECTION: '正文缺少必需小节',
  BODY_TOO_LONG: '正文超过行数上限',
  BODY_TOO_LARGE: '正文超过体积上限',
  RESOURCE_TOO_LARGE: '单个资源超过体积上限',
  PACKAGE_TOO_LARGE: '上传包超过体积上限',
  TOO_MANY_ENTRIES: '包内文件数超过上限',
  INVALID_PATH: '包内路径非法',
  SYMLINK_REJECTED: '包内不允许软链接',
  EXTERNAL_LINK_REJECTED: '包内不允许外部链接',
  PERMISSION_ESCALATION: '权限超出本人范围',
  UNKNOWN_TOOL: 'allowed-tools 引用未注册工具',
  EMBEDDED_SECRET: '正文 / 描述含疑似凭证',
  INTERNAL_ADDRESS: '正文含内网地址',
  BINARY_CONTENT: '正文 / 资源为二进制内容',
  INJECTION_DETECTED: '内容命中注入规则',
  INVALID_FRONTMATTER: 'frontmatter 无法解析',
  DIRECTORY_NAME_MISMATCH: '目录名与名称不一致',
  L1_BUDGET_EXCEEDED: 'L1 预算超限',
  GATE_INSUFFICIENT_GOLDEN_TASKS: 'golden tasks 数量不足',
  GATE_TRIGGER_FAILED: '触发判定未通过',
  SKILLS_ROOT_MISSING: 'skills 目录缺失',
  SKILLS_ROOT_UNREADABLE: 'skills 目录不可读',
  SKILLS_ROOT_EMPTY: 'skills 目录为空',
  SKILL_FILE_MISSING: '目录缺少 SKILL.md',
  EMPTY_SKILLS_ROOT: '未装载到任何 Skill',
}

/** 接口错误码 → 中文文案（SkillErrorCode；未知码回退服务端 message） */
export const SKILL_ERROR_CODE_COPY: Record<string, string> = {
  SKILL_NAME_CONFLICT: '与已有 Skill 重名，请改名或 fork 后修改',
  SKILL_VALIDATION_FAILED: 'Skill 校验未通过',
  SKILL_PERMISSION_ESCALATION: 'Skill 权限超出你的权限，不得提权',
  SKILL_NOT_FOUND: 'Skill 不存在或不可见',
  SKILL_STATUS_INVALID: '当前状态不允许该操作',
  SKILL_IMPORT_INVALID: '导入包非法',
  SKILL_INJECTION_DETECTED: '内容命中注入规则，拒绝发布',
  SKILL_GATE_FAILED: '发布门槛未通过',
}

/** issues[].field → 表单锚点（未知字段归到顶部汇总区，不静默丢弃） */
export const SKILL_ISSUE_FIELD_ANCHOR: Record<string, string> = {
  name: 'agent-skill-name',
  description: 'agent-skill-description',
  body: 'agent-skill-body',
  'allowed-tools': 'agent-skill-allowed-tools',
  permissions: 'agent-skill-permissions',
  frontmatter: 'agent-skill-name',
  package: 'agent-skill-import-file',
}

/** 来源页签定义（顺序固定：全部 → 平台 → 我的） */
export const SKILL_SCOPE_TABS = [
  { value: 'ALL', label: '全部' },
  { value: 'PLATFORM', label: '平台内置' },
  { value: 'USER', label: '我的' },
] as const

/** 状态页签定义 */
export const SKILL_STATUS_TABS = [
  { value: 'ALL', label: '全部' },
  { value: 'DRAFT', label: '草稿' },
  { value: 'ACTIVE', label: '已发布' },
  { value: 'DISABLED', label: '已停用' },
] as const

export const AGENT_SKILLS_COPY = {
  pageTitle: 'Skill 管理',
  pageDescription:
    '创建、编辑与发布你自己的 Skill：平台内置 Skill 只读（可 fork 后修改），自定义 Skill 保存即逐项校验，发布前需通过评测门槛。',
  permissionBoundary:
    '自定义 Skill 只对本人可见；正文按不可信内容处理，发布时额外做注入检测。',

  listTitle: 'Skill 列表',
  listDescription: '来源优先级：我的 > 租户共享 > 平台内置；同名高层生效、低层标注被遮蔽。',
  loading: '正在加载 Skill…',
  loadErrorTitle: 'Skill 列表加载失败',
  retry: '重新加载',

  emptyCustomTitle: '还没有自定义 Skill',
  emptyCustomDescription:
    '新建一个空白草稿，或从下方平台内置 Skill fork 一份再改。平台 Skill 始终保持可列出。',
  emptyFilteredTitle: '当前筛选下没有 Skill',
  emptyFilteredDescription: '切换来源或状态页签查看其它 Skill。',

  createButton: '新建 Skill',
  importButton: '导入 zip',
  forkButton: 'fork',
  editButton: '编辑',
  exportButton: '导出',
  publishButton: '发布',
  disableButton: '停用',
  deleteButton: '删除',

  createTitle: '新建 Skill 草稿',
  editTitle: '编辑 Skill',
  editorDescription:
    '正文来自导出包根级 SKILL.md；保存后版本 +1，校验明细会逐项定位到对应输入项。',
  loadingDocument: '正在读取 SKILL.md…',
  loadDocumentErrorTitle: '读取 SKILL.md 失败',

  fieldName: '名称',
  fieldNameHint: '小写字母 / 数字 / 连字符，2~64 位，例如 task-diagnose-copy',
  fieldDescription: '描述',
  fieldDescriptionHint: '写给模型判断触发时机：含触发词与不适用边界。',
  fieldAllowedTools: 'allowed-tools',
  fieldAllowedToolsHint: '每行一个已注册工具名；可点击下方工具追加。',
  fieldPermissions: 'permissions',
  fieldPermissionsHint: '每行一个；必须是你自己拥有的权限，不能提权。',
  fieldBody: '正文（SKILL.md）',
  fieldBodyHint: '必须包含 `## Gotchas` 与 `## 验收` 两节，正文不超过 500 行。',
  availableTools: '可用工具',

  invalidName: '名称须匹配 ^[a-z0-9][a-z0-9-]{1,63}$（小写字母/数字/连字符，2~64 位）',
  invalidNameRequired: '请填写名称',
  invalidDescription: '请填写描述',
  invalidBody: '请填写正文',
  invalidFile: '请选择一个 zip 文件',
  importTooLarge: '导入包不能超过 {mb} MB（服务端同样拒绝超体积包）',

  save: '保存',
  saving: '保存中…',
  cancel: '取消',

  issueSummary: '校验未通过（{count} 项），未保存',
  issueBlockedSummary: '校验未通过（{count} 项）',
  requestFailedTitle: '操作未完成：',
  issueWarningSummary: '保存成功，版本已 +1；以下 {count} 项告警不阻塞保存',
  issueSummaryTop: '以下问题未定位到具体字段，请逐项检查：',
  issueUnlocated: '未定位',
  saveSuccessHint: '保存成功，版本已 +1',

  versionsTitle: '版本历史',
  versionsEmpty: '暂无版本记录',

  gateTitle: '发布门槛',
  gateNotChecked: '发布时会检查 golden tasks 与触发判定；未达标只能留作草稿。',
  gateGoldenTasks: 'golden tasks',
  gateTrigger: '触发判定',
  gatePassed: '通过',
  gateFailed: '未通过',
  gateFailures: '未达标原因',
  gateUnmetHint: '未达发布门槛：只能留作草稿，不参与自动触发。',
  gateMetHint: '已满足发布门槛。',
  gateNote: '说明',

  forkTitle: 'fork Skill',
  forkDescription: '复制所选 Skill 的内容为你的草稿；不会修改原 Skill。',
  forkName: '新 Skill 名称',
  forkSubmitting: '正在 fork…',

  importTitle: '导入 Skill zip',
  importDescription:
    '上传与平台同一格式的 zip 包（根级 SKILL.md + references/scripts/assets）。服务端逐项校验，失败逐条展示，不吞错。',
  importFile: 'zip 包',
  importSubmit: '开始导入',
  importSubmitting: '正在导入…',
  importFailed: '导入失败',
  importIssues: '导入失败原因',

  disableTitle: '停用 Skill？',
  disableDescription:
    '停用后立即从 L1 与自动触发候选中消失；已在执行的 run 按版本快照继续。',
  disableConfirm: '停用',
  deleteTitle: '删除 Skill？',
  deleteDescription: '删除后列表不再显示；历史 run 的版本快照仍可回放。',
  deleteConfirm: '删除',

  platformReadonly: '平台内置，只读（可 fork 或导出）',
  maskedByPrefix: '被同名',
  maskedBySuffix: 'Skill 遮蔽，不参与触发',
  updatedAt: '更新时间',
  contentHash: '内容哈希',
  versionShort: '版本',
} as const

/** 来源标签（列表徽标） */
export const SKILL_SCOPE_BADGE_TONE: Record<
  SkillScope,
  'default' | 'secondary' | 'outline'
> = {
  PLATFORM: 'outline',
  TENANT: 'secondary',
  USER: 'default',
}
