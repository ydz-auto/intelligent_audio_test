/**
 * 权限点目录领域模型（domain 层）。
 * 事实来源：seed_rbac.py:46-168 权限点全量 + 中文描述原值（INT-347 §2.0 实测）。
 * 权限点目录由 seed 管理，后端只读暴露（role_bp.py 注释「权限点仅只读暴露」）——
 * 本平台不设权限点 CRUD；矩阵行按角色 permissions 列表渲染，permission:read 缺失
 * 时仅缺 Tooltip 描述。
 */

export type Permission = {
  code: string
  name: string
  /** 所属业务模块（矩阵 Collapsible 分组键） */
  module: string
}

export type PermissionModule = {
  /** 模块键（22 个业务模块） */
  id: string
  /** 模块中文名（矩阵分组头） */
  name: string
  permissions: Permission[]
}

/** 权限点目录（22 模块全量；* 通配独立成组，WILDCARD_FORBIDDEN 约束见 user.ts） */
export const PERMISSION_CATALOG: PermissionModule[] = [
  {
    id: 'task',
    name: '任务',
    permissions: [
      { code: 'task:read', name: '查看任务', module: '任务' },
      { code: 'task:create', name: '创建任务', module: '任务' },
      { code: 'task:update', name: '修改任务', module: '任务' },
      { code: 'task:delete', name: '删除任务', module: '任务' },
      { code: 'task:execute', name: '执行/控制任务', module: '任务' },
      { code: 'task:merge', name: '合并任务', module: '任务' },
      { code: 'task:batch', name: '批量任务', module: '任务' },
      { code: 'task:reextract', name: '重新提取任务结果', module: '任务' },
      { code: 'task:publish', name: '发布已发布任务', module: '任务' },
      { code: 'task:export', name: '导出任务数据', module: '任务' },
      { code: 'task:import', name: '导入任务数据', module: '任务' },
      { code: 'task:cherry_pick', name: '挑选合并', module: '任务' },
    ],
  },
  {
    id: 'published_task',
    name: '已发布任务',
    permissions: [
      { code: 'published_task:read', name: '查看已发布任务', module: '已发布任务' },
      { code: 'published_task:execute', name: '执行已发布任务', module: '已发布任务' },
      { code: 'published_task:version', name: '创建已发布任务新版本', module: '已发布任务' },
      { code: 'published_task:archive', name: '归档已发布任务', module: '已发布任务' },
    ],
  },
  {
    id: 'testcase',
    name: '测试用例',
    permissions: [
      { code: 'testcase:read', name: '查看测试用例', module: '测试用例' },
      { code: 'testcase:create', name: '创建测试用例', module: '测试用例' },
      { code: 'testcase:update', name: '修改测试用例', module: '测试用例' },
      { code: 'testcase:delete', name: '删除测试用例', module: '测试用例' },
      { code: 'testcase:copy', name: '复制测试用例', module: '测试用例' },
      { code: 'testcase:preview', name: '预览测试用例', module: '测试用例' },
      { code: 'testcase:import_export', name: '导入/导出测试用例', module: '测试用例' },
    ],
  },
  {
    id: 'audio',
    name: '音频',
    permissions: [
      { code: 'audio:read', name: '查看音频', module: '音频' },
      { code: 'audio:upload', name: '上传音频', module: '音频' },
      { code: 'audio:update', name: '修改音频', module: '音频' },
      { code: 'audio:delete', name: '删除音频', module: '音频' },
      { code: 'audio:convert', name: '音频转码', module: '音频' },
      { code: 'audio:folder', name: '音频文件夹管理', module: '音频' },
    ],
  },
  {
    id: 'device',
    name: '被测设备',
    permissions: [
      { code: 'device:read', name: '查看被测设备', module: '被测设备' },
      { code: 'device:create', name: '创建被测设备', module: '被测设备' },
      { code: 'device:update', name: '修改被测设备', module: '被测设备' },
      { code: 'device:delete', name: '删除被测设备', module: '被测设备' },
      { code: 'device:control', name: '控制被测设备', module: '被测设备' },
    ],
  },
  {
    id: 'playback',
    name: '播放设备',
    permissions: [
      { code: 'playback:read', name: '查看播放设备', module: '播放设备' },
      { code: 'playback:create', name: '创建播放设备', module: '播放设备' },
      { code: 'playback:update', name: '修改播放设备', module: '播放设备' },
      { code: 'playback:delete', name: '删除播放设备', module: '播放设备' },
      { code: 'playback:control', name: '控制播放设备', module: '播放设备' },
    ],
  },
  {
    id: 'spl',
    name: '声压级',
    permissions: [
      { code: 'spl:read', name: '查看 SPL 校准', module: '声压级' },
      { code: 'spl:create', name: '创建 SPL 校准', module: '声压级' },
      { code: 'spl:update', name: '修改 SPL 校准', module: '声压级' },
      { code: 'spl:delete', name: '删除 SPL 校准', module: '声压级' },
      { code: 'spl:test_tone', name: 'SPL 测试音播放', module: '声压级' },
    ],
  },
  {
    id: 'digital_spl',
    name: '数字域 RMS→SPL',
    permissions: [
      { code: 'digital_spl:read', name: '查看数字域 RMS→SPL 映射', module: '数字域 RMS→SPL' },
      { code: 'digital_spl:create', name: '创建数字域 RMS→SPL 映射', module: '数字域 RMS→SPL' },
      { code: 'digital_spl:update', name: '修改数字域 RMS→SPL 映射', module: '数字域 RMS→SPL' },
      { code: 'digital_spl:delete', name: '删除数字域 RMS→SPL 映射', module: '数字域 RMS→SPL' },
    ],
  },
  {
    id: 'api_config',
    name: 'API 配置',
    permissions: [
      { code: 'api_config:read', name: '查看 API 配置', module: 'API 配置' },
      { code: 'api_config:create', name: '创建 API 配置', module: 'API 配置' },
      { code: 'api_config:update', name: '修改 API 配置', module: 'API 配置' },
      { code: 'api_config:delete', name: '删除 API 配置', module: 'API 配置' },
      { code: 'api_config:test', name: '测试 API 连接', module: 'API 配置' },
    ],
  },
  {
    id: 'report',
    name: '报告',
    permissions: [
      { code: 'report:read', name: '查看报告', module: '报告' },
      { code: 'report:create', name: '创建报告', module: '报告' },
      { code: 'report:update', name: '修改报告', module: '报告' },
      { code: 'report:delete', name: '删除报告', module: '报告' },
      { code: 'report:publish', name: '发布报告', module: '报告' },
      { code: 'report:compare', name: '对比报告', module: '报告' },
      { code: 'report:download_log', name: '下载报告日志', module: '报告' },
    ],
  },
  {
    id: 'benchmark',
    name: 'Benchmark 排行',
    permissions: [
      { code: 'benchmark:ranking:read', name: '查看 Benchmark 排行/指标映射', module: 'Benchmark 排行' },
      { code: 'benchmark:ranking:compute', name: '触发 Benchmark 排行计算', module: 'Benchmark 排行' },
      { code: 'benchmark:baseline:read', name: '查看外部基线数据源/基线', module: 'Benchmark 排行' },
      { code: 'benchmark:baseline:write', name: '创建外部基线数据源', module: 'Benchmark 排行' },
      { code: 'benchmark:baseline:publish', name: '导入/发布外部基线版本', module: 'Benchmark 排行' },
      { code: 'benchmark:mapping:manage', name: '管理指标映射', module: 'Benchmark 排行' },
    ],
  },
  {
    id: 'evaluation',
    name: '评估',
    permissions: [
      { code: 'evaluation:read', name: '查看评估维度', module: '评估' },
      { code: 'evaluation:execute', name: '触发重新评估', module: '评估' },
      { code: 'evaluation:dim_manage', name: '维度 CRUD/批量/计算', module: '评估' },
      { code: 'evaluation:category_manage', name: '评估分类 CRUD', module: '评估' },
      { code: 'evaluation:import_export', name: '维度导入/导出', module: '评估' },
    ],
  },
  {
    id: 'algorithm',
    name: '算法配置',
    permissions: [
      { code: 'algorithm:read', name: '查看算法配置', module: '算法配置' },
      { code: 'algorithm:definition_manage', name: '算法定义 CRUD', module: '算法配置' },
      { code: 'algorithm:group_manage', name: '算法分组 CRUD', module: '算法配置' },
      { code: 'algorithm:param_manage', name: '算法参数 CRUD', module: '算法配置' },
      { code: 'algorithm:case_param_manage', name: '用例算法参数 CRUD', module: '算法配置' },
    ],
  },
  {
    id: 'group',
    name: '用例分组',
    permissions: [
      { code: 'group:read', name: '查看用例分组', module: '用例分组' },
      { code: 'group:create', name: '创建分组', module: '用例分组' },
      { code: 'group:update', name: '修改分组/移动用例', module: '用例分组' },
      { code: 'group:delete', name: '删除分组', module: '用例分组' },
    ],
  },
  {
    id: 'tag',
    name: '标签',
    permissions: [
      { code: 'tag:read', name: '查看标签/分类', module: '标签' },
      { code: 'tag:create', name: '创建标签/分类', module: '标签' },
      { code: 'tag:update', name: '修改标签/分类', module: '标签' },
      { code: 'tag:delete', name: '删除标签/分类', module: '标签' },
    ],
  },
  {
    id: 'log',
    name: '日志',
    permissions: [
      { code: 'log:read', name: '查看日志/统计/归档', module: '日志' },
      { code: 'log:manage', name: '标记/刷新/清空/归档日志', module: '日志' },
      { code: 'log:websocket', name: '订阅 WebSocket 日志推送', module: '日志' },
    ],
  },
  {
    id: 'home',
    name: '首页',
    permissions: [
      { code: 'home:read', name: '查看首页统计', module: '首页' },
      { code: 'home:refresh', name: '刷新首页统计', module: '首页' },
    ],
  },
  {
    id: 'sse',
    name: 'SSE',
    permissions: [{ code: 'sse:read', name: '订阅 SSE 事件流', module: 'SSE' }],
  },
  {
    id: 'iam',
    name: '用户/角色/权限管理',
    permissions: [
      { code: 'user:read', name: '查看用户列表/详情', module: '用户/角色/权限管理' },
      { code: 'user:create', name: '创建用户', module: '用户/角色/权限管理' },
      { code: 'user:update', name: '修改用户信息/状态/密码', module: '用户/角色/权限管理' },
      { code: 'user:delete', name: '禁用/删除用户', module: '用户/角色/权限管理' },
      { code: 'user:assign_role', name: '分配用户角色', module: '用户/角色/权限管理' },
      { code: 'user:grant_permission', name: '授予/撤销用户额外权限', module: '用户/角色/权限管理' },
      { code: 'auth:manage_provider', name: '管理自定义 OAuth 提供方', module: '用户/角色/权限管理' },
      { code: 'role:read', name: '查看角色列表/详情/权限', module: '用户/角色/权限管理' },
      { code: 'role:create', name: '创建自定义角色', module: '用户/角色/权限管理' },
      { code: 'role:update', name: '修改角色信息/权限分配', module: '用户/角色/权限管理' },
      { code: 'role:delete', name: '删除自定义角色', module: '用户/角色/权限管理' },
      { code: 'permission:read', name: '查看所有权限点', module: '用户/角色/权限管理' },
    ],
  },
  {
    id: 'auth',
    name: '认证',
    permissions: [
      { code: 'auth:login', name: '登录', module: '认证' },
      { code: 'auth:callback', name: 'OAuth 回调', module: '认证' },
      { code: 'auth:refresh', name: '刷新令牌', module: '认证' },
      { code: 'auth:logout', name: '登出', module: '认证' },
      { code: 'auth:me', name: '获取当前用户信息', module: '认证' },
    ],
  },
  {
    id: 'wildcard',
    name: '超级通配',
    permissions: [
      { code: '*', name: '超级权限（通配所有操作）', module: '超级通配' },
    ],
  },
]

/** 目录扁平视图（权限矩阵已选计数/角色 permissions 解析用） */
export const ALL_PERMISSIONS: Permission[] = PERMISSION_CATALOG.flatMap(
  (module) => module.permissions
)

/** 按权限码取目录项描述（无 permission:read 时矩阵行缺 Tooltip） */
export function findPermission(code: string): Permission | undefined {
  return ALL_PERMISSIONS.find((permission) => permission.code === code)
}
