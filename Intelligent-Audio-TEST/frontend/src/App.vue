<template>
  <div class="app-container">
    <aside class="sidebar" :class="{ 'sidebar-collapsed': sidebarCollapsed }" @mouseenter="handleSidebarEnter" @mouseleave="handleSidebarLeave">
      <div class="sidebar-header">
        <div class="logo-container" v-if="!sidebarCollapsed">
          <h1 class="logo">
            <i class="fas fa-headset"></i>
            智能语音测试系统
          </h1>
        </div>
        <div class="logo-icon-only" v-else>
          <i class="fas fa-headset"></i>
        </div>
      </div>

      <nav>
        <ul>
          <li v-for="item in visibleNavItems" :key="item.path">
            <router-link :to="item.path" class="navLink" :class="{ 'justify-center': sidebarCollapsed }">
              <i :class="item.icon"></i>
              <span v-if="!sidebarCollapsed">{{ item.label }}</span>
            </router-link>
          </li>
        </ul>
      </nav>

      <!-- 用户信息 + 登出 -->
      <div v-if="authStore.isLoggedIn && !sidebarCollapsed" class="sidebar-footer">
        <span class="user-name">{{ authStore.username }}</span>
        <span class="user-role" v-if="authStore.roleName">{{ authStore.roleName }}</span>
        <button class="logout-btn" @click="handleLogout">登出</button>
      </div>
    </aside>

    <div class="sidebar-hover-trigger" v-if="sidebarCollapsed || isHomePage" @mouseenter="handleTriggerEnter" @mouseleave="handleTriggerLeave">
      <div class="sidebar-hint">
        <i class="fas fa-chevron-right"></i>
      </div>
    </div>

    <main class="main-content" :class="{ 'sidebar-collapsed': sidebarCollapsed }" ref="mainContentRef">
      <router-view :key="$route.fullPath"></router-view>
    </main>

    <div id="global-fixed-elements"></div>
    <GlobalModalContainer />
    <Notification ref="notificationRef" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { provideModal } from './composables/index'
import { registerGlobalModals } from './composables/modal/modalRegistration'
import { GlobalModalContainer } from './composables/modalIndex'
import { useAuthStore } from './store/authStore'
import Notification from './components/common/modal/Notification.vue'
import { provideNotification } from './composables/modal/useNotification'

// ===== 导航配置 =====
interface NavItem {
  path: string
  label: string
  icon: string
  permission: string
}

const navItems: NavItem[] = [
  { path: '/', label: '首页', icon: 'fas fa-home navIcon', permission: 'home:read' },
  { path: '/E2ETest', label: '端到端测试', icon: 'fas fa-project-diagram navIcon', permission: 'task:execute' },
  { path: '/APITest', label: 'API测试', icon: 'fas fa-exchange-alt navIcon', permission: 'task:execute' },
  { path: '/AlgorithmConfig', label: '算法配置', icon: 'fas fa-cogs navIcon', permission: 'algorithm:read' },
  { path: '/tasks', label: '测试任务记录', icon: 'fas fa-tasks navIcon', permission: 'task:read' },
  { path: '/history-reports', label: '历史报告', icon: 'fas fa-history navIcon', permission: 'report:read' },
  { path: '/TestCaseManager', label: '用例管理', icon: 'fas fa-tasks navIcon', permission: 'testcase:read' },
  { path: '/Evaluation', label: '评估维度管理', icon: 'fas fa-star navIcon', permission: 'evaluation:read' },
  { path: '/Device', label: '设备管理', icon: 'fas fa-headphones navIcon', permission: 'device:read' },
  { path: '/AudioImport', label: '导入音频管理', icon: 'fas fa-music navIcon', permission: 'audio:read' },
  { path: '/SPLMapping', label: '声压级映射管理', icon: 'fas fa-sliders-h navIcon', permission: 'spl:read' },
  { path: '/LogView', label: '日志查看', icon: 'fas fa-file-alt navIcon', permission: 'log:read' },
  { path: '/TagManagement', label: '标签管理', icon: 'fas fa-tags navIcon', permission: 'tag:read' },
]

// ===== Stores & refs =====
const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()
const notificationRef = ref(null)
const mainContentRef = ref<HTMLElement | null>(null)

// 按权限过滤导航
const visibleNavItems = computed(() => {
  if (!authStore.isLoggedIn) {
    // 未登录（AUTH_MODE=off 兼容）：显示全部
    return navItems
  }
  return navItems.filter(item => authStore.hasPermission(item.permission))
})

// 侧边栏折叠状态
const sidebarCollapsed = ref(true)
let hideTimeout: ReturnType<typeof setTimeout> | null = null
let autoHideTimeout: ReturnType<typeof setTimeout> | null = null
let isMouseOverSidebar = false

const isHomePage = computed(() => route.path === '/')

function clearTimers() {
  if (hideTimeout) clearTimeout(hideTimeout)
  if (autoHideTimeout) clearTimeout(autoHideTimeout)
}

function handleTriggerEnter() {
  isMouseOverSidebar = true
  clearTimers()
  sidebarCollapsed.value = false
}

function handleTriggerLeave() {
  isMouseOverSidebar = false
  hideTimeout = setTimeout(() => {
    if (!isMouseOverSidebar) sidebarCollapsed.value = true
  }, 300)
}

function handleSidebarEnter() {
  isMouseOverSidebar = true
  clearTimers()
  sidebarCollapsed.value = false
}

function handleSidebarLeave() {
  isMouseOverSidebar = false
  hideTimeout = setTimeout(() => {
    if (!isMouseOverSidebar) sidebarCollapsed.value = true
  }, 300)
}

function handleLogout() {
  authStore.logout()
  router.push('/')
}

// 路由切换：重置滚动 + 侧边栏自动折叠
watch(() => route.fullPath, () => {
  if (mainContentRef.value) {
    mainContentRef.value.scrollTop = 0
  }
  clearTimers()
  isMouseOverSidebar = false
  sidebarCollapsed.value = isHomePage.value
  if (!isHomePage.value) {
    autoHideTimeout = setTimeout(() => {
      if (!isMouseOverSidebar) sidebarCollapsed.value = true
    }, 1000)
  }
})

onMounted(() => {
  provideNotification(notificationRef.value)
  provideModal()
  registerGlobalModals()

  // 恢复用户信息：token 存在时从后端 /auth/me 拉取最新权限
  authStore.init()

  sidebarCollapsed.value = isHomePage.value
  if (!isHomePage.value) {
    autoHideTimeout = setTimeout(() => {
      if (!isMouseOverSidebar) sidebarCollapsed.value = true
    }, 1000)
  }
})

onUnmounted(() => {
  clearTimers()
})
</script>

<style scoped>
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--spacing-xl);
  padding-bottom: var(--spacing-lg);
  border-bottom: 1px solid var(--gray-light-color);
  flex-shrink: 0;
}

.logo-container {
  flex: 1;
  overflow: hidden;
}

.logo-icon-only {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--primary-light);
  border-radius: 10px;
  flex-shrink: 0;
}

.logo-icon-only i {
  font-size: 20px;
  color: var(--primary-color);
}

.sidebar-footer {
  margin-top: auto;
  padding: var(--spacing-md);
  border-top: 1px solid var(--gray-light-color);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: 13px;
}

.user-name {
  font-weight: 600;
  color: var(--text-primary);
}

.user-role {
  color: var(--text-secondary);
  background: var(--gray-light-color);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
}

.logout-btn {
  margin-left: auto;
  background: none;
  border: 1px solid var(--gray-color);
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  color: var(--text-secondary);
}

.logout-btn:hover {
  border-color: var(--danger-color);
  color: var(--danger-color);
}

.navLink.justify-center {
  justify-content: center;
  padding: var(--spacing-md);
}

.navLink.justify-center .navIcon {
  margin-right: 0;
}

@media (max-width: 768px) {
  .sidebar-header {
    padding: var(--spacing-sm);
  }
}
</style>
