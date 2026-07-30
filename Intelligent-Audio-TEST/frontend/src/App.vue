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
          <li><router-link to="/" class="navLink" :class="{ 'justify-center': sidebarCollapsed }">
            <i class="fas fa-home navIcon"></i>
            <span v-if="!sidebarCollapsed">首页</span>
          </router-link></li>
          <li><router-link to="/E2ETest" class="navLink" :class="{ 'justify-center': sidebarCollapsed }">
            <i class="fas fa-project-diagram navIcon"></i>
            <span v-if="!sidebarCollapsed">端到端测试</span>
          </router-link></li>
          <li><router-link to="/APITest" class="navLink" :class="{ 'justify-center': sidebarCollapsed }">
            <i class="fas fa-exchange-alt navIcon"></i>
            <span v-if="!sidebarCollapsed">API测试</span>
          </router-link></li>
          <li><router-link to="/AlgorithmConfig" class="navLink" :class="{ 'justify-center': sidebarCollapsed }">
            <i class="fas fa-cogs navIcon"></i>
            <span v-if="!sidebarCollapsed">算法配置</span>
          </router-link></li>
          <li><router-link to="/tasks" class="navLink" :class="{ 'justify-center': sidebarCollapsed }">
            <i class="fas fa-tasks navIcon"></i>
            <span v-if="!sidebarCollapsed">测试任务记录</span>
          </router-link></li>
          <li><router-link to="/history-reports" class="navLink" :class="{ 'justify-center': sidebarCollapsed }">
            <i class="fas fa-history navIcon"></i>
            <span v-if="!sidebarCollapsed">历史报告</span>
          </router-link></li>
          <li><router-link to="/TestCaseManager" class="navLink" :class="{ 'justify-center': sidebarCollapsed }">
            <i class="fas fa-tasks navIcon"></i>
            <span v-if="!sidebarCollapsed">用例管理</span>
          </router-link></li>
          <li><router-link to="/Evaluation" class="navLink" :class="{ 'justify-center': sidebarCollapsed }">
            <i class="fas fa-star navIcon"></i>
            <span v-if="!sidebarCollapsed">评估维度管理</span>
          </router-link></li>
          <li><router-link to="/Device" class="navLink" :class="{ 'justify-center': sidebarCollapsed }">
            <i class="fas fa-headphones navIcon"></i>
            <span v-if="!sidebarCollapsed">设备管理</span>
          </router-link></li>
          <li><router-link to="/AudioImport" class="navLink" :class="{ 'justify-center': sidebarCollapsed }">
            <i class="fas fa-music navIcon"></i>
            <span v-if="!sidebarCollapsed">导入音频管理</span>
          </router-link></li>
          <li><router-link to="/SPLMapping" class="navLink" :class="{ 'justify-center': sidebarCollapsed }">
            <i class="fas fa-sliders-h navIcon"></i>
            <span v-if="!sidebarCollapsed">声压级映射管理</span>
          </router-link></li>
          <li><router-link to="/LogView" class="navLink" :class="{ 'justify-center': sidebarCollapsed }">
            <i class="fas fa-file-alt navIcon"></i>
            <span v-if="!sidebarCollapsed">日志查看</span>
          </router-link></li>
          <li><router-link to="/TagManagement" class="navLink" :class="{ 'justify-center': sidebarCollapsed }">
            <i class="fas fa-tags navIcon"></i>
            <span v-if="!sidebarCollapsed">标签管理</span>
          </router-link></li>
        </ul>
      </nav>
    </aside>

    <div class="sidebar-hover-trigger" v-if="sidebarCollapsed || isHomePage" @mouseenter="handleTriggerEnter" @mouseleave="handleTriggerLeave">
      <div class="sidebar-hint">
        <i class="fas fa-chevron-right"></i>
      </div>
    </div>

    <main class="main-content" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
      <router-view :key="$route.fullPath"></router-view>
    </main>

    <!-- 全局固定元素容器 -->
    <div id="global-fixed-elements">
      <!-- 这里放置全局固定定位的元素 -->
    </div>

    <GlobalModalContainer />
    <Notification ref="notificationRef" />
  </div>
</template>

<script setup>
import { watch, computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { provideModal } from './composables/index'
import { registerGlobalModals } from './composables/modal/modalRegistration'
import { GlobalModalContainer, modalConfirm } from './composables/modalIndex'
import { useModalStore } from './store/modalStore'
import Notification from './components/common/modal/Notification.vue'
import { provideNotification } from './composables/modal/useNotification'

const notificationRef = ref(null)

onMounted(() => {
  provideNotification(notificationRef.value)
})

provideModal()

registerGlobalModals()

const router = useRouter()
const route = useRoute()
const modalStore = useModalStore()

const sidebarCollapsed = ref(true)
let hideTimeout = null
let autoHideTimeout = null
let isMouseOverSidebar = false

const isHomePage = computed(() => {
  return route.path === '/'
})

const handleTriggerEnter = () => {
  isMouseOverSidebar = true
  clearTimeout(hideTimeout)
  clearTimeout(autoHideTimeout)
  sidebarCollapsed.value = false
}

const handleTriggerLeave = () => {
  isMouseOverSidebar = false
  hideTimeout = setTimeout(() => {
    if (!isMouseOverSidebar) {
      sidebarCollapsed.value = true
    }
  }, 300)
}

const handleSidebarEnter = () => {
  isMouseOverSidebar = true
  clearTimeout(hideTimeout)
  clearTimeout(autoHideTimeout)
  sidebarCollapsed.value = false
}

const handleSidebarLeave = () => {
  isMouseOverSidebar = false
  hideTimeout = setTimeout(() => {
    if (!isMouseOverSidebar) {
      sidebarCollapsed.value = true
    }
  }, 300)
}

const resetScroll = () => {
  setTimeout(() => {
    // 只重置主内容区域的滚动位置，不影响导航栏
    const mainContent = document.querySelector('.main-content')
    if (mainContent) {
      mainContent.scrollTop = 0
    }
  }, 100)
}

// 保存侧边栏滚动位置到sessionStorage
let sidebarScrollTop = 0

// 保存侧边栏滚动位置
const saveSidebarScrollPosition = () => {
  const container = document.querySelector('.sidebar')
  if (container) {
    sidebarScrollTop = container.scrollTop
    localStorage.setItem('sidebarScrollTop', sidebarScrollTop.toString())
    console.log('Saved scroll position:', sidebarScrollTop)
  }
}

// 恢复侧边栏滚动位置
const restoreSidebarScrollPosition = () => {
  const container = document.querySelector('.sidebar')
  if (container && sidebarCollapsed.value === false) {
    // 只有当侧边栏展开时才恢复滚动位置
    const savedPosition = localStorage.getItem('sidebarScrollTop')
    if (savedPosition) {
      const scrollTop = parseInt(savedPosition, 10)
      container.scrollTop = scrollTop
      console.log('Restored scroll position:', scrollTop)
    }
  }
}

// 监听侧边栏滚动事件，实时保存滚动位置
const setupSidebarScrollListener = () => {
  const sidebar = document.querySelector('.sidebar')
  if (sidebar) {
    sidebar.addEventListener('scroll', saveSidebarScrollPosition)
  }
}

// 展开侧边栏并恢复滚动位置
const expandSidebarAndRestoreScroll = () => {
  const sidebar = document.querySelector('.sidebar')
  if (sidebar && sidebarCollapsed.value === false) {
    // 确保侧边栏完全展开
    setTimeout(() => {
      console.log('Restoring scroll position:', localStorage.getItem('sidebarScrollTop'))
      const savedPosition = localStorage.getItem('sidebarScrollTop')
      if (savedPosition) {
        const scrollTop = parseInt(savedPosition, 10)
        sidebar.scrollTop = scrollTop
        console.log('Set scrollTop to:', scrollTop, 'actual:', sidebar.scrollTop)
      }
    }, 300)
  }
}

// 监听sidebarCollapsed状态变化
watch(sidebarCollapsed, (newValue, oldValue) => {
  if (newValue !== oldValue) {
    if (newValue === false) {
      // 侧边栏展开时，恢复滚动位置
      expandSidebarAndRestoreScroll()
    }
    // 不再在侧边栏折叠时保存滚动位置，避免滚动位置被重置为0
  }
})

router.afterEach(() => {
  resetScroll()
  clearTimeout(autoHideTimeout)
  // 重置鼠标悬停状态
  isMouseOverSidebar = false
  
  // 首页默认收起，其他页默认展开后自动收起
  const shouldCollapse = isHomePage.value
  if (sidebarCollapsed.value !== shouldCollapse) {
    sidebarCollapsed.value = shouldCollapse
  }
  
  if (!isHomePage.value) {
    // 从首页切换到其他页面时，导航栏显示时间更长
    autoHideTimeout = setTimeout(() => {
      if (!isMouseOverSidebar) {
        sidebarCollapsed.value = true
      }
    }, 1000) // 1秒后自动收起
  }
  
  // 不在页面切换时恢复滚动位置，避免与状态变化时的恢复冲突
})

onMounted(() => {
  clearTimeout(autoHideTimeout)
  // 首页默认收起，其他页默认展开后自动收起
  sidebarCollapsed.value = isHomePage.value
  if (!isHomePage.value) {
    // 从首页切换到其他页面时，导航栏显示时间更长
    autoHideTimeout = setTimeout(() => {
      if (!isMouseOverSidebar) {
        sidebarCollapsed.value = true
      }
    }, 1000) // 1秒后自动收起
  }
  
  // 设置侧边栏滚动监听器
  setupSidebarScrollListener()
  
  // 页面加载时恢复滚动位置
  setTimeout(() => {
    restoreSidebarScrollPosition()
  }, 100)
})

onUnmounted(() => {
  clearTimeout(hideTimeout)
  clearTimeout(autoHideTimeout)
  // 清理侧边栏滚动监听器
  const sidebar = document.querySelector('.sidebar')
  if (sidebar) {
    sidebar.removeEventListener('scroll', saveSidebarScrollPosition)
  }
})

window.addEventListener('hashchange', resetScroll)
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
