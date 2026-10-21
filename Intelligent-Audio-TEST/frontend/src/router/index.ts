import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../store/authStore'
import { AuthMode, getEffectiveAuthMode } from '../domain/enums'

/**
 * 路由表 + meta 配置（UX设计-VUE 总表 §2.1/§2.3 落地）
 *
 * meta.layout: 'public' | 'auth' | 'authenticated' | 缺省（无壳，错误页）
 * meta.permission: 访问该路由所需权限（任一满足），undefined 表示不需要权限
 * meta.permissions: 多权限任一（hasAnyPermission）
 * meta.public: 公开路由（无需登录）
 * meta.title: 页面标题
 *
 * 壳与路由总表由 INT-735 基座壳卡落地；公共页实页（首页门户/文档/关于/排行榜）由 INT-745
 * 落地、报告域三页实页（/reports /report-center /report-statistics）由 INT-741 落地，
 * /start-test 合并入口由 INT-737 落地。
 */

declare module 'vue-router' {
  interface RouteMeta {
    layout?: 'public' | 'auth' | 'authenticated'
    public?: boolean
    permission?: string
    permissions?: string[]
    title?: string
  }
}

const routes: Array<RouteRecordRaw> = [
  // ===== 认证壳 AuthLayout =====
  { path: '/login', name: 'login', component: () => import('../views/Login/LoginPage.vue'), meta: { public: true, layout: 'auth', title: '登录' } },
  { path: '/register', name: 'register', component: () => import('../views/Register/RegisterPage.vue'), meta: { public: true, layout: 'auth', title: '注册' } },

  // ===== 公共壳 PublicLayout =====
  { path: '/', name: 'home', component: () => import('../views/Home/Home.vue'), meta: { public: true, layout: 'public', title: '首页' } },
  { path: '/user-guide', name: 'userGuide', component: () => import('../views/UserGuide/UserGuide.vue'), meta: { public: true, layout: 'public', title: '使用手册' } },
  { path: '/user-guide-api', name: 'userGuideApi', component: () => import('../views/UserGuide/UserGuideApi.vue'), meta: { public: true, layout: 'public', title: 'API 手册' } },
  { path: '/about', name: 'about', component: () => import('../views/About/About.vue'), meta: { public: true, layout: 'public', title: '关于' } },
  { path: '/rankings', name: 'rankings', component: () => import('../views/BenchmarkRanking/BenchmarkRanking.vue'), meta: { public: true, layout: 'public', title: '排行榜' } },
  { path: '/benchmarks', name: 'benchmarkRankingLegacy', redirect: '/rankings' },

  // ===== 工作台壳 AuthenticatedLayout =====
  // INT-736：工作台概览聚合页实页（算法卡片网格 + 引导卡 + 平台概览 + 双面板 + 任务统计图表区）
  { path: '/dashboard', name: 'dashboard', component: () => import('../views/Dashboard/Dashboard.vue'), meta: { permission: 'home:read', layout: 'authenticated', title: '工作台' } },
  // INT-737：开始测试合并入口 /start-test（E2E+API 单流程，四步，无选算法步骤）
  { path: '/start-test', name: 'startTest', component: () => import('../views/StartTest/StartTest.vue'), meta: { permissions: ['task:execute', 'algorithm:read'], layout: 'authenticated', title: '开始测试' } },
  // INT-742/INT-1109：灵犀Agent /ai-chat 对话工作台实页（INT-742 建页，INT-1109 落地路由；
  // URL 契约 /ai-chat?report={id}|task={id}|reviewCase= 由页面 onMounted 消费）
  { path: '/ai-chat', name: 'aiChat', component: () => import('../views/AiChat/AiChatPage.vue'), meta: { permission: 'report:read', layout: 'authenticated', title: '灵犀Agent' } },
  { path: '/tasks', name: 'tasks', component: () => import('../views/Tasks/Tasks.vue'), meta: { permission: 'task:read', layout: 'authenticated', title: '任务管理' } },
  // INT-577 §2.2 裁定①：旧路径式页签 redirect——「合并」页签收编进「挑选合并」，
  // /tasks/merged 与 /tasks/cherry-picks 均归一到 /tasks?tab=cherry-picks（query 态页签）
  { path: '/tasks/merged', name: 'tasksMergedLegacy', redirect: { name: 'tasks', query: { tab: 'cherry-picks' } } },
  { path: '/tasks/cherry-picks', name: 'tasksCherryPicks', redirect: { name: 'tasks', query: { tab: 'cherry-picks' } } },
  { path: '/tasks/:id(\\d+)', name: 'taskDetail', component: () => import('../views/Tasks/TaskDetailView.vue'), meta: { permission: 'task:read', layout: 'authenticated', title: '任务详情' } },
  // INT-298：已发布任务并入任务页「已发布任务」页签；独立路由重定向保留旧链接/收藏夹兼容
  { path: '/published-tasks', name: 'publishedTasks', redirect: { name: 'tasks', query: { tab: 'published' } } },
  // 报告域（07 卡合并 History/TestReports 至报告中心；INT-741 实页落地，现路由重定向保留旧链）
  { path: '/reports', name: 'reports', component: () => import('../views/Reports/ReportShowcase.vue'), meta: { permission: 'report:read', layout: 'authenticated', title: '报告' } },
  { path: '/report-center', name: 'reportCenter', component: () => import('../views/ReportCenter/ReportCenter.vue'), meta: { permission: 'report:read', layout: 'authenticated', title: '报告中心' } },
  { path: '/report-statistics', name: 'reportStatistics', component: () => import('../views/ReportStatistics/ReportStatistics.vue'), meta: { permission: 'report:read', layout: 'authenticated', title: '报告统计分析' } },
  { path: '/history-reports', name: 'historyReports', redirect: '/report-center' },
  { path: '/test-reports', name: 'testReports', redirect: '/report-center' },
  { path: '/report/:id', name: 'reportView', component: () => import('../views/ReportView/ReportView.vue'), meta: { permission: 'report:read', layout: 'authenticated', title: '报告查看' } },
  { path: '/report', name: 'reportViewQuery', component: () => import('../views/ReportView/ReportView.vue'), meta: { permission: 'report:read', layout: 'authenticated', title: '报告查看' } },
  // 用例域
  { path: '/testcases', name: 'testcases', component: () => import('../views/TestCaseManager/TestCaseManager.vue'), meta: { permission: 'testcase:read', layout: 'authenticated', title: '用例管理' } },
  { path: '/TestCaseManager', name: 'testCaseManager', redirect: '/testcases' },
  { path: '/Evaluation', name: 'evaluation', component: () => import('../views/Evaluation/Evaluation.vue'), meta: { permission: 'evaluation:read', layout: 'authenticated', title: '评估维度管理' } },
  { path: '/TagManagement', name: 'tagManagement', component: () => import('../views/TagManagement/TagManagement.vue'), meta: { permission: 'tag:read', layout: 'authenticated', title: '标签管理' } },
  // 设备域
  { path: '/devices', name: 'devices', component: () => import('../views/Device/Device.vue'), meta: { permission: 'device:read', layout: 'authenticated', title: '设备管理' } },
  { path: '/Device', name: 'device', redirect: '/devices' },
  { path: '/audio-import', name: 'audioImport', component: () => import('../views/AudioImport/AudioImport.vue'), meta: { permission: 'audio:read', layout: 'authenticated', title: '音频管理' } },
  { path: '/AudioImport', name: 'audioImportLegacy', redirect: '/audio-import' },
  { path: '/SPLMapping', name: 'splMapping', component: () => import('../views/splMapping/SPLMapping.vue'), meta: { permissions: ['spl:read', 'digital_spl:read'], layout: 'authenticated', title: 'SPL 映射管理' } },
  // 配置运维
  { path: '/AlgorithmConfig', name: 'algorithmConfig', component: () => import('../views/AlgorithmConfig/AlgorithmConfigPage.vue'), meta: { permission: 'algorithm:read', layout: 'authenticated', title: '算法配置' } },
  { path: '/logs', name: 'logs', component: () => import('../views/LogView/LogView.vue'), meta: { permission: 'log:read', layout: 'authenticated', title: '日志查看' } },
  { path: '/LogView', name: 'logView', redirect: '/logs' },
  // 系统设置 drill-in（INT-743 六域；域级门槛由侧栏树过滤，路由仅需登录）
  {
    path: '/system-settings',
    name: 'systemSettings',
    component: () => import('../views/SystemSettings/SystemSettingsLayout.vue'),
    meta: { layout: 'authenticated', title: '系统设置' },
    children: [
      { path: '', redirect: { path: '/system-settings/site/info' } },
      { path: 'site/info', name: 'systemSettingsSiteInfo', component: () => import('../views/SystemSettings/site/SiteInfoSection.vue'), meta: { title: '站点信息' } },
      { path: 'site/notice', name: 'systemSettingsSiteNotice', component: () => import('../views/SystemSettings/site/SiteNoticeSection.vue'), meta: { title: '站点公告' } },
      { path: 'site/navigation', name: 'systemSettingsSiteNavigation', component: () => import('../views/SystemSettings/site/SiteNavigationSection.vue'), meta: { title: '导航模块' } },
      { path: 'iam/users', name: 'systemSettingsUsers', component: () => import('../views/SystemSettings/iam/UsersSection.vue'), meta: { title: '用户管理' } },
      { path: 'iam/roles', name: 'systemSettingsRoles', component: () => import('../views/SystemSettings/iam/RolesSection.vue'), meta: { title: '角色权限管理' } },
      { path: 'auth/methods', name: 'systemSettingsAuthMethods', component: () => import('../views/SystemSettings/auth/AuthMethodsSection.vue'), meta: { title: '认证方式' } },
      { path: 'auth/oauth-providers', name: 'systemSettingsOAuthProviders', component: () => import('../views/SystemSettings/auth/OAuthProvidersSection.vue'), meta: { title: 'OAuth 提供方' } },
      { path: 'appearance/presets', name: 'systemSettingsAppearancePresets', component: () => import('../views/SystemSettings/appearance/PresetsSection.vue'), meta: { title: '主题预设' } },
      { path: 'appearance/fine-tuning', name: 'systemSettingsAppearanceFineTuning', component: () => import('../views/SystemSettings/appearance/FineTuningSection.vue'), meta: { title: '外观微调' } },
      { path: 'security/access-control', name: 'systemSettingsSecurityAccessControl', component: () => import('../views/SystemSettings/security/AccessControlSection.vue'), meta: { title: '访问控制' } },
      { path: 'operations/log-maintenance', name: 'systemSettingsLogMaintenance', component: () => import('../views/SystemSettings/operations/LogMaintenanceSection.vue'), meta: { title: '日志维护' } },
    ],
  },
  // OAuth 提供方收编认证设置域（旧链 redirect）
  { path: '/OAuthProviders', name: 'oauthProvidersLegacy', redirect: '/system-settings/auth/oauth-providers' },
  // 个人中心
  // INT-744：个人中心 /profile（承接 /AccountSettings 并入；旧链用组件内 router.replace 保留 query 供 OAuth 绑定回调）
  { path: '/profile', name: 'profile', component: () => import('../views/Profile/ProfileView.vue'), meta: { layout: 'authenticated', title: '个人中心' } },
  { path: '/AccountSettings', name: 'accountSettings', component: () => import('../views/Account/AccountSettings.vue'), meta: { layout: 'authenticated', title: '账号设置' } },
  // 测试执行旧链（INT-737 合并入口落地后翻转 redirect：侧栏「测试执行 → 开始测试」单入口）
  { path: '/E2ETest', name: 'e2eTest', redirect: '/start-test', meta: { permission: 'task:execute', layout: 'authenticated', title: '开始测试' } },
  { path: '/APITest', name: 'apiTest', redirect: '/start-test', meta: { permission: 'task:execute', layout: 'authenticated', title: '开始测试' } },

  // ===== 无壳错误页五件 =====
  { path: '/401', name: 'error401', component: () => import('../views/Error/ErrorPage.vue'), props: { code: 401 }, meta: { public: true, title: '未登录' } },
  { path: '/403', name: 'error403', component: () => import('../views/Error/ErrorPage.vue'), props: { code: 403 }, meta: { public: true, title: '无权限' } },
  { path: '/404', name: 'error404', component: () => import('../views/Error/ErrorPage.vue'), props: { code: 404 }, meta: { public: true, title: '页面不存在' } },
  { path: '/500', name: 'error500', component: () => import('../views/Error/ErrorPage.vue'), props: { code: 500 }, meta: { public: true, title: '服务器错误' } },
  { path: '/503', name: 'error503', component: () => import('../views/Error/ErrorPage.vue'), props: { code: 503 }, meta: { public: true, title: '服务不可用' } },
  // 根路由 404 兜底（无壳）
  { path: '/:pathMatch(.*)*', name: 'notFound', component: () => import('../views/Error/ErrorPage.vue'), props: { code: 404 }, meta: { public: true, title: '页面不存在' } },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  }
})

/**
 * 路由守卫（K01 三分支）：
 * 1. 已登录访问登录/注册 → redirect 工作台
 * 2. 公开路由直接放行
 * 3. AUTH_MODE=off（后端无认证）时直接放行（前端无 token 也可用，一切全显）
 * 4. 需要登录的路由：无 token 跳登录页（携带 redirect）
 * 5. 需要权限的路由：无权限跳 /403?from=（替代现「静默跳首页」）
 */
router.beforeEach((to, _from, next) => {
  // 设置页面标题
  if (to.meta.title) {
    document.title = `${to.meta.title} - 智能语音测试系统`
  }

  const auth = useAuthStore()

  // 已登录访问登录/注册页 → redirect 工作台（OAuth 回调携 token 时放行处理）
  if ((to.name === 'login' || to.name === 'register') && auth.isLoggedIn && !to.query.oauth_token) {
    return next({ path: '/dashboard' })
  }

  // 公开路由直接放行
  if (to.meta.public) {
    return next()
  }

  // 后端 AUTH_MODE=off 时前端无 token，直接放行（向后兼容；一切全显）
  if (!auth.isLoggedIn) {
    const authMode = getEffectiveAuthMode()
    if (authMode === AuthMode.OFF) {
      return next()
    }
    // 认证开启但未登录 → 跳登录页
    return next({ name: 'login', query: { redirect: to.fullPath } })
  }

  // 已登录：检查权限（无权限 → /403?from=）
  if (to.meta.permission && !auth.hasPermission(to.meta.permission)) {
    return next({ path: '/403', query: { from: to.fullPath } })
  }
  if (to.meta.permissions && !auth.hasAnyPermission(...to.meta.permissions)) {
    return next({ path: '/403', query: { from: to.fullPath } })
  }

  next()
})

// 路由切换后重置主内容区滚动（精简版，不再遍历全 DOM）
// INT-745 P1 修复：公共页滚动容器为 .public-layout（挂 .app-container 壳内自管滚动），一并重置
router.afterEach(() => {
  requestAnimationFrame(() => {
    const main = document.querySelector('.main-content')
    if (main) main.scrollTop = 0
    const pub = document.querySelector('.public-layout')
    if (pub) pub.scrollTop = 0
  })
})

export default router
