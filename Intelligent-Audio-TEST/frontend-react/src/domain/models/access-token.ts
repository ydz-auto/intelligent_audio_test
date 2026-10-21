/**
 * Access Token 领域模型（domain 层，INT-1140/INT-1153）。
 *
 * 事实来源：INT-1140 数据模型草案 + INT-1142 可行性评审（对齐 new-api
 * user_access_tokens：只存哈希、明文创建显示一次、scopes、expires_at）。
 * 后端表字段（auth_service access_tokens）：id / user_id / name / token_hash /
 * token_hint / scopes(JSON) / expires_at(0=永不过期) / status(enabled|disabled) /
 * last_used_at / last_used_ip / created_at / deleted_at（软删 + status）。
 *
 * scopes 目录：INT-1140「能力覆盖与除外边界」业务可暴露子集（seed_rbac.py 130
 * 权限点中挑），前端个人页按目录勾选；空列表 = 继承用户全部权限（后端语义）。
 */
import type { PermissionModule } from './permission'

export type AccessTokenStatus = 'enabled' | 'disabled'

export type AccessToken = {
  id: string
  name: string
  /** 明文末 4 位（列表掩码展示；后端只存哈希） */
  tokenHint: string
  /** 权限点列表；空数组 = 继承用户全部权限 */
  scopes: string[]
  /** 有效时间（Unix 秒）；0 = 永不过期 */
  expiresAt: number
  status: AccessTokenStatus
  /** 最近使用时间（Unix 秒）；null = 从未使用 */
  lastUsedAt: number | null
  /** 最近使用 IP；null = 从未使用 */
  lastUsedIp: string | null
  /** 创建时间（Unix 秒） */
  createdAt: number
  deletedAt: number | null
}

/**
 * 业务可暴露 scopes 目录（INT-1140 能力覆盖清单子集，负责人验收时核对）：
 * 覆盖 task / published_task / testcase / audio / device / playback / spl /
 * digital_spl / api_config / report（含 report-studio）/ benchmark / evaluation /
 * algorithm / group / tag / lab / log:read / home:read；
 * 除外 iam（user/role/permission/auth:manage_provider）、auth（登录/回调/刷新/
 * 登出/me）、option（系统选项）、status（站点状态）、sse（长连接推送）、
 * log:manage / log:websocket（日志管理）、home:refresh（统计刷新）、通配 *。
 */
export const ACCESS_TOKEN_SCOPE_CATALOG: PermissionModule[] = [
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
      { code: 'task.result.review', name: '人工复核测试结果', module: '任务' },
      { code: 'task.result.ai_review', name: 'AI 复核测试结果', module: '任务' },
      { code: 'task:share', name: '分享任务（数据可见性）', module: '任务' },
      { code: 'task:read_execute_view', name: '查看任务执行只读视图', module: '任务' },
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
      { code: 'testcase:share', name: '分享测试用例（数据可见性）', module: '测试用例' },
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
      { code: 'audio:share', name: '分享音频（数据可见性）', module: '音频' },
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
      { code: 'report:studio:create', name: 'Report Studio 创建文档草稿', module: '报告' },
      { code: 'report:studio:edit', name: 'Report Studio 编辑文档', module: '报告' },
      { code: 'report:studio:undo', name: 'Report Studio 版本恢复', module: '报告' },
      { code: 'report:studio:export', name: 'Report Studio 导出作业', module: '报告' },
      { code: 'report:share', name: '分享报告（数据可见性）', module: '报告' },
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
      { code: 'benchmark:report:read', name: '查看 Benchmark 报告', module: 'Benchmark 排行' },
      { code: 'benchmark:report:publish', name: '发布 Benchmark 报告', module: 'Benchmark 排行' },
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
      { code: 'evaluation:share', name: '分享评估维度/分类（数据可见性）', module: '评估' },
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
      { code: 'group:share', name: '分享用例分组（数据可见性）', module: '用例分组' },
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
      { code: 'tag:share', name: '分享标签/分类（数据可见性）', module: '标签' },
    ],
  },
  {
    id: 'lab',
    name: '实验室',
    permissions: [
      { code: 'lab:create', name: '创建实验室', module: '实验室' },
      { code: 'lab:update', name: '修改实验室', module: '实验室' },
      { code: 'lab:delete', name: '删除实验室', module: '实验室' },
    ],
  },
  {
    id: 'log',
    name: '日志',
    permissions: [
      { code: 'log:read', name: '查看日志/统计/归档（只读）', module: '日志' },
    ],
  },
  {
    id: 'home',
    name: '首页',
    permissions: [
      { code: 'home:read', name: '查看首页统计', module: '首页' },
    ],
  },
]

/** 目录扁平视图（已选计数 / token scopes 校验用） */
export const ACCESS_TOKEN_SCOPE_FLAT: { code: string; name: string }[] =
  ACCESS_TOKEN_SCOPE_CATALOG.flatMap((module) => module.permissions)
