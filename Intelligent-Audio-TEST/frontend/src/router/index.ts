import { createRouter, createWebHashHistory, RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../store/authStore'

/**
 * 路由表 + meta 权限配置
 *
 * meta.permission: 访问该路由所需权限（任一满足即可），undefined 表示不需要权限
 * meta.public:     是否为公开路由（无需登录，如登录页）
 * meta.title:       页面标题
 */
const routes: Array<RouteRecordRaw> = [
  { path: '/login', name: 'login', component: () => import('../views/Login/LoginPage.vue'), meta: { public: true, title: '登录' } },
  { path: '/', name: 'home', component: () => import('../views/Home/Home.vue'), meta: { permission: 'home:read', title: '首页' } },
  { path: '/E2ETest', name: 'e2eTest', component: () => import('../views/E2ETest/E2ETest.vue'), meta: { permission: 'task:execute', title: '端到端测试' } },
  { path: '/APITest', name: 'apiTest', component: () => import('../views/APITest/APITest.vue'), meta: { permission: 'task:execute', title: 'API测试' } },
  { path: '/tasks', name: 'tasks', component: () => import('../views/Tasks/Tasks.vue'), meta: { permission: 'task:read', title: '测试任务记录' } },
  { path: '/history-reports', name: 'historyReports', component: () => import('../views/HistoryReports/HistoryReports.vue'), meta: { permission: 'report:read', title: '历史报告' } },
  { path: '/test-reports', name: 'testReports', component: () => import('../views/TestReports/TestReports.vue'), meta: { permission: 'report:read', title: '测试报告' } },
  { path: '/report/:id', name: 'reportView', component: () => import('../views/ReportView/ReportView.vue'), meta: { permission: 'report:read', title: '报告查看' } },
  { path: '/report', name: 'reportViewQuery', component: () => import('../views/ReportView/ReportView.vue'), meta: { permission: 'report:read', title: '报告查看' } },
  { path: '/TestCaseManager', name: 'testCaseManager', component: () => import('../views/TestCaseManager/TestCaseManager.vue'), meta: { permission: 'testcase:read', title: '用例管理' } },
  { path: '/Evaluation', name: 'evaluation', component: () => import('../views/Evaluation/Evaluation.vue'), meta: { permission: 'evaluation:read', title: '评估维度管理' } },
  { path: '/Device', name: 'device', component: () => import('../views/Device/Device.vue'), meta: { permission: 'device:read', title: '设备管理' } },
  { path: '/AudioImport', name: 'audioImport', component: () => import('../views/AudioImport/AudioImport.vue'), meta: { permission: 'audio:read', title: '导入音频管理' } },
  { path: '/SPLMapping', name: 'splMapping', component: () => import('../views/SPLMapping/SPLMapping.vue'), meta: { permission: 'spl:read', title: '声压级映射管理' } },
  { path: '/LogView', name: 'logView', component: () => import('../views/LogView/LogView.vue'), meta: { permission: 'log:read', title: '日志查看' } },
  { path: '/AlgorithmConfig', name: 'algorithmConfig', component: () => import('../views/AlgorithmConfig/AlgorithmConfigPage.vue'), meta: { permission: 'algorithm:read', title: '算法配置' } },
  { path: '/TagManagement', name: 'tagManagement', component: () => import('../views/TagManagement/TagManagement.vue'), meta: { permission: 'tag:read', title: '标签管理' } },
  // 404 兜底
  { path: '/:pathMatch(.*)*', name: 'notFound', component: () => import('../views/NotFound/NotFoundPage.vue'), meta: { public: true, title: '页面不存在' } },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  }
})

/**
 * 路由守卫：
 * 1. 公开路由直接放行
 * 2. AUTH_MODE=off（后端无认证）时直接放行（前端无 token 也可用）
 * 3. 需要登录的路由：无 token 跳登录页
 * 4. 需要权限的路由：无权限跳 403 页
 */
router.beforeEach((to, _from, next) => {
  // 设置页面标题
  if (to.meta.title) {
    document.title = `${to.meta.title} - 智能语音测试系统`
  }

  // 公开路由直接放行
  if (to.meta.public) {
    return next()
  }

  // 读取 auth store
  const auth = useAuthStore()

  // 后端 AUTH_MODE=off 时前端无 token，直接放行（向后兼容）
  // 只有当后端启用了认证（前端有 token 流程）时才做拦截
  if (!auth.isLoggedIn) {
    // 尝试判断后端是否开启了认证：通过环境变量 VITE_AUTH_MODE
    // 未配置或 off 时，放行（向后兼容）
    const authMode = (import.meta as any).env?.VITE_AUTH_MODE || 'off'
    if (authMode === 'off') {
      return next()
    }
    // 认证开启但未登录 → 跳登录页
    return next({ name: 'login', query: { redirect: to.fullPath } })
  }

  // 已登录：检查权限
  if (to.meta.permission && !auth.hasPermission(to.meta.permission as string)) {
    // 无权限 → 跳 403 或首页
    return next({ name: 'home' })
  }

  next()
})

// 路由切换后重置主内容区滚动（精简版，不再遍历全 DOM）
router.afterEach(() => {
  requestAnimationFrame(() => {
    const main = document.querySelector('.main-content')
    if (main) main.scrollTop = 0
  })
})

export default router
