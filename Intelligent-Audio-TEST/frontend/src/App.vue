<template>
  <div class="app-root">
    <!-- 布局壳按路由 meta.layout 选择；无壳（错误页）直接渲染 router-view -->
    <component :is="layoutComponent" v-if="layoutComponent" />
    <router-view v-else />

    <div id="global-fixed-elements"></div>
    <GlobalModalContainer />
    <Notification ref="notificationRef" />
    <RequireLoginDialog />
    <!-- INT-577 §4.4：全局购物车抽屉（Tasks/CherryPickPanel 入口；「去复核」跳到挑选合并页签复核步骤） -->
    <CartDrawer
      :visible="cartDrawerState.visible.value"
      @close="cartDrawerState.close()"
      @go-review="goCartReview"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { provideModal } from './composables/index'
import { registerGlobalModals } from './components/common/modal/modalRegistration'
import GlobalModalContainer from './components/common/modal/GlobalModalContainer.vue'
import { useAuthStore } from './store/authStore'
import { useThemeStore } from './store/themeStore'
import Notification from './components/common/modal/Notification.vue'
import { provideNotification, type NotificationInstance } from './composables/modal/useNotification'
import RequireLoginDialog from './components/layout/RequireLoginDialog.vue'
import PublicLayout from './layouts/PublicLayout.vue'
import AuthLayout from './layouts/AuthLayout.vue'
import AuthenticatedLayout from './layouts/AuthenticatedLayout.vue'
import CartDrawer from './components/task/pick/CartDrawer.vue'
import { useCartDrawerState } from './composables/task/cartDrawerState'
import { requestPickWizard } from './composables/task/usePickWizardRequest'

// provide() 必须在 setup 同步阶段调用，提供模态框管理器供子孙组件 inject
provideModal()
registerGlobalModals()

const route = useRoute()
const router = useRouter()
const notificationRef = ref<NotificationInstance | null>(null)
const cartDrawerState = useCartDrawerState()

/** 按路由 meta.layout 选择布局壳（无 meta.layout = 无壳错误页） */
const layoutComponent = computed(() => {
  switch (route.meta.layout) {
    case 'public': return PublicLayout
    case 'auth': return AuthLayout
    case 'authenticated': return AuthenticatedLayout
    default: return null
  }
})

/** INT-577：购物车抽屉「去复核」→ 挑选合并页签复核步骤 */
function goCartReview() {
  cartDrawerState.close()
  // P0 修复同款机制：经共享请求自开复核向导（:key=fullPath 重挂载下 URL 参数方案
  // 会在清参时再次重挂载丢向导态）；query 保留现有参数只归一 tab
  requestPickWizard({ step: 'review' })
  const query: Record<string, string> = { ...route.query, tab: 'cherry-picks' } as Record<string, string>
  delete query.wizard
  router.push({ path: '/tasks', query })
}

onMounted(() => {
  if (notificationRef.value) {
    provideNotification(notificationRef.value)
  }

  // 恢复用户信息：token 存在时从后端 /auth/me 拉取最新权限
  useAuthStore().init()

  // 主题初始化：挂 .dark（localStorage iatp:theme:v1），须在渲染前生效
  useThemeStore().init()
})

onUnmounted(() => {
  // 无清理逻辑（模态框等由全局单例持有）
})
</script>

<style scoped>
/* 根容器只提供背景；滚动由各布局自管（AuthenticatedLayout 内部滚动，Public/错误页自然滚动） */
.app-root {
  min-height: 100vh;
  background: var(--background);
}
</style>
