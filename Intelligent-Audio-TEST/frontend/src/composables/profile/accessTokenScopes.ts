/**
 * Access Token scopes 勾选目录 —— Application 层常量（INT-1155）
 *
 * 从 scripts/migrations/202608/seed_rbac.py 130 权限点中挑「业务可暴露子集」，
 * 与 INT-1140「能力覆盖清单」一致（INT-1142 评审产出）：
 *   - 覆盖：task / case(testcase) / audio / device(含 playback/spl/digital_spl/api_config/lab) /
 *            evaluation / report(含 report-studio) / algorithm / tag / group 业务接口、
 *            `*:share` 数据可见性分享点、data-transfer（task:export/import，已含在 task）、
 *            favorites / trash（INT-141，无独立权限码，由所属域 read 码覆盖）、benchmarks、report-studio。
 *   - 日志域只读倾向覆盖：仅 log:read；log:manage / log:websocket（管理/长连接推送）除外。
 *   - 除外（不暴露）：auth users/roles/permissions/oauth-providers（系统设置）、
 *     auth me/self/change-password/OAuth 绑定（个人信息）、option（系统设置）、
 *     system health/status、SSE（sse:read 长连接推送）。
 */

/** scopes 目录单项 */
export interface AccessTokenScopeItem {
  /** 权限码（seed_rbac.py 原样） */
  code: string
  /** 中文释义（seed_rbac.py description） */
  label: string
}

/** scopes 目录分组 */
export interface AccessTokenScopeGroup {
  /** 权限码模块前缀 */
  module: string
  /** 分组中文名（个人页勾选目录展示） */
  label: string
  scopes: AccessTokenScopeItem[]
}

/** 业务可暴露子集目录（按 seed_rbac.py 顺序与描述挑取） */
export const ACCESS_TOKEN_SCOPE_GROUPS: AccessTokenScopeGroup[] = [
  {
    module: 'task',
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
      { code: 'task:cherry_pick', label: '挑选合并' },
      { code: 'task.result.review', label: '人工复核测试结果' },
      { code: 'task.result.ai_review', label: 'AI 复核测试结果' },
      { code: 'task:share', label: '分享任务' },
      { code: 'task:read_execute_view', label: '查看任务执行只读视图' },
    ],
  },
  {
    module: 'published_task',
    label: '已发布任务',
    scopes: [
      { code: 'published_task:read', label: '查看已发布任务' },
      { code: 'published_task:execute', label: '执行已发布任务' },
      { code: 'published_task:version', label: '创建新版本' },
      { code: 'published_task:archive', label: '归档已发布任务' },
    ],
  },
  {
    module: 'testcase',
    label: '测试用例',
    scopes: [
      { code: 'testcase:read', label: '查看测试用例' },
      { code: 'testcase:create', label: '创建测试用例' },
      { code: 'testcase:update', label: '修改测试用例' },
      { code: 'testcase:delete', label: '删除测试用例' },
      { code: 'testcase:copy', label: '复制测试用例' },
      { code: 'testcase:preview', label: '预览测试用例' },
      { code: 'testcase:import_export', label: '导入/导出测试用例' },
      { code: 'testcase:share', label: '分享测试用例' },
    ],
  },
  {
    module: 'audio',
    label: '音频',
    scopes: [
      { code: 'audio:read', label: '查看音频' },
      { code: 'audio:upload', label: '上传音频' },
      { code: 'audio:update', label: '修改音频' },
      { code: 'audio:delete', label: '删除音频' },
      { code: 'audio:convert', label: '音频转码' },
      { code: 'audio:folder', label: '音频文件夹管理' },
      { code: 'audio:share', label: '分享音频' },
    ],
  },
  {
    module: 'device',
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
    module: 'playback',
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
    module: 'spl',
    label: '声压级',
    scopes: [
      { code: 'spl:read', label: '查看 SPL 校准' },
      { code: 'spl:create', label: '创建 SPL 校准' },
      { code: 'spl:update', label: '修改 SPL 校准' },
      { code: 'spl:delete', label: '删除 SPL 校准' },
      { code: 'spl:test_tone', label: 'SPL 测试音播放' },
    ],
  },
  {
    module: 'digital_spl',
    label: '数字域 RMS→SPL',
    scopes: [
      { code: 'digital_spl:read', label: '查看数字域映射' },
      { code: 'digital_spl:create', label: '创建数字域映射' },
      { code: 'digital_spl:update', label: '修改数字域映射' },
      { code: 'digital_spl:delete', label: '删除数字域映射' },
    ],
  },
  {
    module: 'api_config',
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
    module: 'lab',
    label: '实验室',
    scopes: [
      { code: 'lab:create', label: '创建实验室' },
      { code: 'lab:update', label: '修改实验室' },
      { code: 'lab:delete', label: '删除实验室' },
    ],
  },
  {
    module: 'report',
    label: '报告',
    scopes: [
      { code: 'report:read', label: '查看报告' },
      { code: 'report:create', label: '创建报告' },
      { code: 'report:update', label: '修改报告' },
      { code: 'report:delete', label: '删除报告' },
      { code: 'report:publish', label: '发布报告' },
      { code: 'report:compare', label: '对比报告' },
      { code: 'report:download_log', label: '下载报告日志' },
      { code: 'report:share', label: '分享报告' },
    ],
  },
  {
    module: 'report-studio',
    label: 'Report Studio',
    scopes: [
      { code: 'report:studio:create', label: '创建文档草稿' },
      { code: 'report:studio:edit', label: '编辑文档' },
      { code: 'report:studio:undo', label: '版本恢复' },
      { code: 'report:studio:export', label: '导出作业' },
    ],
  },
  {
    module: 'benchmark',
    label: 'Benchmark',
    scopes: [
      { code: 'benchmark:ranking:read', label: '查看排行/指标映射' },
      { code: 'benchmark:ranking:compute', label: '触发排行计算' },
      { code: 'benchmark:baseline:read', label: '查看外部基线' },
      { code: 'benchmark:baseline:write', label: '创建外部基线源' },
      { code: 'benchmark:baseline:publish', label: '导入/发布基线版本' },
      { code: 'benchmark:mapping:manage', label: '管理指标映射' },
      { code: 'benchmark:report:read', label: '查看 Benchmark 报告' },
      { code: 'benchmark:report:publish', label: '发布 Benchmark 报告' },
    ],
  },
  {
    module: 'evaluation',
    label: '评估',
    scopes: [
      { code: 'evaluation:read', label: '查看评估维度' },
      { code: 'evaluation:execute', label: '触发重新评估' },
      { code: 'evaluation:dim_manage', label: '维度 CRUD/批量/计算' },
      { code: 'evaluation:category_manage', label: '评估分类 CRUD' },
      { code: 'evaluation:import_export', label: '维度导入/导出' },
      { code: 'evaluation:share', label: '分享评估维度/分类' },
    ],
  },
  {
    module: 'algorithm',
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
    module: 'group',
    label: '用例分组',
    scopes: [
      { code: 'group:read', label: '查看用例分组' },
      { code: 'group:create', label: '创建分组' },
      { code: 'group:update', label: '修改分组/移动用例' },
      { code: 'group:delete', label: '删除分组' },
      { code: 'group:share', label: '分享用例分组' },
    ],
  },
  {
    module: 'tag',
    label: '标签',
    scopes: [
      { code: 'tag:read', label: '查看标签/分类' },
      { code: 'tag:create', label: '创建标签/分类' },
      { code: 'tag:update', label: '修改标签/分类' },
      { code: 'tag:delete', label: '删除标签/分类' },
      { code: 'tag:share', label: '分享标签/分类' },
    ],
  },
  {
    module: 'logs',
    label: '日志（只读）',
    scopes: [
      { code: 'log:read', label: '查看日志/统计/归档' },
    ],
  },
]

/** 全部业务可暴露权限码（勾选「全选」用） */
export const ALL_ACCESS_TOKEN_SCOPES: string[] = ACCESS_TOKEN_SCOPE_GROUPS.flatMap((g) =>
  g.scopes.map((s) => s.code),
)

/** 权限码 → 中文释义（列表掩码展示用；目录外的码原样返回） */
export function accessTokenScopeLabel(code: string): string {
  for (const group of ACCESS_TOKEN_SCOPE_GROUPS) {
    const found = group.scopes.find((s) => s.code === code)
    if (found) return found.label
  }
  return code
}
