import { createRouter, createWebHashHistory, RouteRecordRaw } from 'vue-router'

const routes : Array<RouteRecordRaw> = [
  { path: '/', name: 'home', component: () => import('../views/Home/Home.vue') },
  { path: '/E2ETest', name: 'e2eTest', component: () => import('../views/E2ETest/E2ETest.vue') },
  { path: '/APITest', name: 'apiTest', component: () => import('../views/APITest/APITest.vue') },
  { path: '/apitest', name: 'apiTestLower', component: () => import('../views/APITest/APITest.vue') },
  { path: '/tasks', name: 'tasks', component: () => import('../views/Tasks/Tasks.vue') },
  { path: '/history-reports', name: 'historyReports', component: () => import('../views/HistoryReports/HistoryReports.vue') },
  { path: '/test-reports', name: 'testReports', component: () => import('../views/TestReports/TestReports.vue') },
  { path: '/report/:id', name: 'reportView', component: () => import('../views/ReportView/ReportView.vue') },
  { path: '/report', name: 'reportViewQuery', component: () => import('../views/ReportView/ReportView.vue') },
  { path: '/TestCaseManager', name: 'testCaseManager', component: () => import('../views/TestCaseManager/TestCaseManager.vue') },
  { path: '/Evaluation', name: 'evaluation', component: () => import('../views/Evaluation/Evaluation.vue') },
  { path: '/Device', name: 'device', component: () => import('../views/Device/Device.vue') },
  { path: '/AudioImport', name: 'audioImport', component: () => import('../views/AudioImport/AudioImport.vue') },
  { path: '/SPLMapping', name: 'splMapping', component: () => import('../views/SPLMapping/SPLMapping.vue') },
  { path: '/LogView', name: 'logView', component: () => import('../views/LogView/LogView.vue') },
  { path: '/AlgorithmConfig', name: 'algorithmConfig', component: () => import('../views/AlgorithmConfig/AlgorithmConfigPage.vue') },
  { path: '/TagManagement', name: 'tagManagement', component: () => import('../views/TagManagement/TagManagement.vue') }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    } else {
      return { top: 0 }
    }
  }
})

router.afterEach(() => {
  window.scrollTo(0, 0)
  document.documentElement.scrollTop = 0
  document.body.scrollTop = 0
  
  const allElements = document.querySelectorAll('*')
  for (const el of allElements) {
    if (el.scrollHeight > el.clientHeight) {
      el.scrollTop = 0
    }
  }
})

// 移除全局导航守卫，因为重置函数可能在路由初始化时无法访问到ref变量
// 状态重置将在组件内部通过其他方式处理

export default router
