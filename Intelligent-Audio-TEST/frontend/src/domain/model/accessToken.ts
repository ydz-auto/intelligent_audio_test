/**
 * Access Token 领域模型（INT-1140 联接你的 agent）
 *
 * 对应后端 auth_service access_tokens CRUD（/api/v1/auth/access-tokens）：
 * 明文仅创建响应返回一次，库中只存 SHA-256 哈希 + 末 4 位 token_hint；
 * scopes 为空 = 继承用户全部权限；expires_at=0 表示永不过期。
 * 本层 camelCase，snake_case→camelCase 转换由 infrastructure 层 adapter 承担。
 */

/** 列表/详情里安全返回的 token（掩码，无明文/哈希） */
export interface AccessToken {
  id: number
  userId: number
  name: string
  /** 明文末 4 位（列表展示掩码如 at_xxxx·…abcd） */
  tokenHint: string
  /** RBAC 权限码列表；空数组 = 继承用户全部权限 */
  scopes: string[]
  status: AccessTokenStatus
  /** 0 = 永不过期，否则 ISO 时间字符串 */
  expiresAt: number | string
  lastUsedAt: string | null
  lastUsedIp: string | null
  createdAt: string | null
}

/** 创建响应（明文仅此一次，展示后不再持久化） */
export interface AccessTokenCreated extends AccessToken {
  /** 明文 token（at_ + 32 hex），仅创建响应返回一次 */
  token: string
}

export type AccessTokenStatus = 'enabled' | 'disabled'

export interface AccessTokenCreatePayload {
  name: string
  /** 权限码列表；空/缺省 = 继承用户全部权限 */
  scopes?: string[]
  /** 0=永不过期；缺省 = 后端默认有效期；ISO 字符串 = 显式过期时间 */
  expiresAt?: number | string
}

export interface AccessTokenUpdatePayload {
  name?: string | null
  /** 空数组 = 清空继承用户全部；缺省 = 不修改 */
  scopes?: string[] | null
  status?: AccessTokenStatus | null
  /** 0=永不过期；ISO 字符串 = 显式过期时间；缺省 = 不修改 */
  expiresAt?: number | string | null
}

// =====================================================================
// scopes 目录（个人配置页按目录勾选）
//
// 数据源：scripts/migrations/202608/seed_rbac.py 130 权限点中挑「业务可
// 暴露子集」——对齐 INT-1140 能力覆盖清单（INT-1142 评审产出）：
//   - 覆盖：task / case / audio / device / evaluation / report / algorithm
//     / tag / group 业务接口、:share 数据可见性分享点、data-transfer
//     （task:export/import）、favorites / trash（INT-141）、benchmarks、
//     report-studio；含上述业务域相邻子域（published_task / playback /
//     spl / digital_spl / api_config，负责人口径「覆盖平台所有能力」）。
//   - 除外：auth users/roles/permissions/oauth-providers（系统设置）、
//     auth me/self/change-password/OAuth 绑定（个人信息）、option / status
//     / sse（系统设置/长连接）、log:manage / log:websocket（倾向除外）。
//   - log:read 倾向覆盖（负责人验收核对范围）。
// 值与 seed_rbac.py 一致，禁止改动。
// =====================================================================
export interface ScopeCatalogEntry {
  code: string
  label: string
}

export interface ScopeCatalogGroup {
  key: string
  label: string
  scopes: ScopeCatalogEntry[]
}

export const ACCESS_TOKEN_SCOPES: ScopeCatalogGroup[] = [
  {
    key: 'task',
    label: '任务',
    scopes: [
      { code: 'task:read', label: '查看任务' },
      { code: 'task:create', label: '创建任务' },
      { code: 'task:update', label: '修改任务' },
      { code: 'task:delete', label: '删除任务' },
      { code: 'task:execute', label: '执行/控制任务' },
      { code: 'task:merge', label: '合并任务' },
      { code: 'task:batch', label: '批量任务' },
      { code: 'task:reextract', label: '重新提取任务结果' },
      { code: 'task:publish', label: '发布已发布任务' },
      { code: 'task:export', label: '导出任务数据' },
      { code: 'task:import', label: '导入任务数据' },
      { code: 'task:cherry_pick', label: '挑选合并（购物车/下单三出口）' },
      { code: 'task.result.review', label: '人工复核测试结果' },
      { code: 'task.result.ai_review', label: 'AI 复核测试结果' },
      { code: 'task:share', label: '分享任务（数据可见性）' },
      { code: 'task:read_execute_view', label: '查看任务执行只读视图' },
    ],
  },
  {
    key: 'published_task',
    label: '已发布任务',
    scopes: [
      { code: 'published_task:read', label: '查看已发布任务' },
      { code: 'published_task:execute', label: '执行已发布任务' },
      { code: 'published_task:version', label: '创建已发布任务新版本' },
      { code: 'published_task:archive', label: '归档已发布任务' },
    ],
  },
  {
    key: 'testcase',
    label: '测试用例',
    scopes: [
      { code: 'testcase:read', label: '查看测试用例' },
      { code: 'testcase:create', label: '创建测试用例' },
      { code: 'testcase:update', label: '修改测试用例' },
      { code: 'testcase:delete', label: '删除测试用例' },
      { code: 'testcase:copy', label: '复制测试用例' },
      { code: 'testcase:preview', label: '预览测试用例' },
      { code: 'testcase:import_export', label: '导入/导出测试用例' },
      { code: 'testcase:share', label: '分享测试用例（数据可见性）' },
    ],
  },
  {
    key: 'audio',
    label: '音频',
    scopes: [
      { code: 'audio:read', label: '查看音频' },
      { code: 'audio:upload', label: '上传音频' },
      { code: 'audio:update', label: '修改音频' },
      { code: 'audio:delete', label: '删除音频' },
      { code: 'audio:convert', label: '音频转码' },
      { code: 'audio:folder', label: '音频文件夹管理' },
      { code: 'audio:share', label: '分享音频（数据可见性）' },
    ],
  },
  {
    key: 'device',
    label: '被测设备',
    scopes: [
      { code: 'device:read', label: '查看被测设备' },
      { code: 'device:create', label: '创建被测设备' },
      { code: 'device:update', label: '修改被测设备' },
      { code: 'device:delete', label: '删除被测设备' },
      { code: 'device:control', label: '控制被测设备' },
    ],
  },
  {
    key: 'playback',
    label: '播放设备',
    scopes: [
      { code: 'playback:read', label: '查看播放设备' },
      { code: 'playback:create', label: '创建播放设备' },
      { code: 'playback:update', label: '修改播放设备' },
      { code: 'playback:delete', label: '删除播放设备' },
      { code: 'playback:control', label: '控制播放设备' },
    ],
  },
  {
    key: 'spl',
    label: '声压级映射',
    scopes: [
      { code: 'spl:read', label: '查看 SPL 校准' },
      { code: 'spl:create', label: '创建 SPL 校准' },
      { code: 'spl:update', label: '修改 SPL 校准' },
      { code: 'spl:delete', label: '删除 SPL 校准' },
      { code: 'spl:test_tone', label: 'SPL 测试音播放' },
    ],
  },
  {
    key: 'digital_spl',
    label: '数字域 RMS→SPL',
    scopes: [
      { code: 'digital_spl:read', label: '查看数字域 RMS→SPL 映射' },
      { code: 'digital_spl:create', label: '创建数字域 RMS→SPL 映射' },
      { code: 'digital_spl:update', label: '修改数字域 RMS→SPL 映射' },
      { code: 'digital_spl:delete', label: '删除数字域 RMS→SPL 映射' },
    ],
  },
  {
    key: 'api_config',
    label: 'API 配置',
    scopes: [
      { code: 'api_config:read', label: '查看 API 配置' },
      { code: 'api_config:create', label: '创建 API 配置' },
      { code: 'api_config:update', label: '修改 API 配置' },
      { code: 'api_config:delete', label: '删除 API 配置' },
      { code: 'api_config:test', label: '测试 API 连接' },
    ],
  },
  {
    key: 'report',
    label: '报告',
    scopes: [
      { code: 'report:read', label: '查看报告' },
      { code: 'report:create', label: '创建报告' },
      { code: 'report:update', label: '修改报告' },
      { code: 'report:delete', label: '删除报告' },
      { code: 'report:publish', label: '发布报告' },
      { code: 'report:compare', label: '对比报告' },
      { code: 'report:download_log', label: '下载报告日志' },
      { code: 'report:share', label: '分享报告（数据可见性）' },
    ],
  },
  {
    key: 'report_studio',
    label: 'Report Studio',
    scopes: [
      { code: 'report:studio:create', label: 'Report Studio 创建文档草稿' },
      { code: 'report:studio:edit', label: 'Report Studio 编辑文档' },
      { code: 'report:studio:undo', label: 'Report Studio 版本恢复' },
      { code: 'report:studio:export', label: 'Report Studio 导出作业' },
    ],
  },
  {
    key: 'benchmark',
    label: 'Benchmark',
    scopes: [
      { code: 'benchmark:ranking:read', label: '查看 Benchmark 排行/指标映射' },
      { code: 'benchmark:ranking:compute', label: '触发 Benchmark 排行计算' },
      { code: 'benchmark:baseline:read', label: '查看外部基线数据源/基线' },
      { code: 'benchmark:baseline:write', label: '创建外部基线数据源' },
      { code: 'benchmark:baseline:publish', label: '导入/发布外部基线版本' },
      { code: 'benchmark:mapping:manage', label: '管理指标映射' },
      { code: 'benchmark:report:read', label: '查看 Benchmark 报告' },
      { code: 'benchmark:report:publish', label: '发布 Benchmark 报告' },
    ],
  },
  {
    key: 'evaluation',
    label: '评估',
    scopes: [
      { code: 'evaluation:read', label: '查看评估维度' },
      { code: 'evaluation:execute', label: '触发重新评估' },
      { code: 'evaluation:dim_manage', label: '维度 CRUD/批量/计算' },
      { code: 'evaluation:category_manage', label: '评估分类 CRUD' },
      { code: 'evaluation:import_export', label: '维度导入/导出' },
      { code: 'evaluation:share', label: '分享评估维度/分类（数据可见性）' },
    ],
  },
  {
    key: 'algorithm',
    label: '算法配置',
    scopes: [
      { code: 'algorithm:read', label: '查看算法配置' },
      { code: 'algorithm:definition_manage', label: '算法定义 CRUD' },
      { code: 'algorithm:group_manage', label: '算法分组 CRUD' },
      { code: 'algorithm:param_manage', label: '算法参数 CRUD' },
      { code: 'algorithm:case_param_manage', label: '用例算法参数 CRUD' },
    ],
  },
  {
    key: 'group',
    label: '用例分组',
    scopes: [
      { code: 'group:read', label: '查看用例分组' },
      { code: 'group:create', label: '创建分组' },
      { code: 'group:update', label: '修改分组/移动用例' },
      { code: 'group:delete', label: '删除分组' },
      { code: 'group:share', label: '分享用例分组（数据可见性）' },
    ],
  },
  {
    key: 'tag',
    label: '标签',
    scopes: [
      { code: 'tag:read', label: '查看标签/分类' },
      { code: 'tag:create', label: '创建标签/分类' },
      { code: 'tag:update', label: '修改标签/分类' },
      { code: 'tag:delete', label: '删除标签/分类' },
      { code: 'tag:share', label: '分享标签/分类（数据可见性）' },
    ],
  },
  {
    key: 'log',
    label: '日志（只读）',
    scopes: [
      { code: 'log:read', label: '查看日志/统计/归档' },
    ],
  },
]

/** 目录 key → 组（编辑回显/勾选态查询用） */
export const SCOPE_GROUP_BY_KEY: Record<string, ScopeCatalogGroup> =
  Object.fromEntries(ACCESS_TOKEN_SCOPES.map(g => [g.key, g]))

/** 全部业务可暴露权限码（用于「全选」与掩码回显） */
export const ALL_ACCESS_TOKEN_SCOPE_CODES: string[] = ACCESS_TOKEN_SCOPES.flatMap(g => g.scopes.map(s => s.code))
