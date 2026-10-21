<template>
  <div class="authenticated-layout">
    <header class="authenticated-header">
      <SystemBrand />
      <TopNav class="authenticated-header__nav" />
      <TopBarRight mode="authenticated" />
    </header>

    <div class="authenticated-body">
      <AppSidebar v-model:collapsed="sidebarCollapsed" />
      <main class="main-content" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
        <router-view />
      </main>
    </div>

    <!-- 全局 Agent 工作台浮窗（§3.1B：渲染于壳根部、不随路由卸载——登录壳任意页面可开，
         切换页面浮窗保持打开、会话不丢；开关由右上角魔法按钮控制，最小化胶囊右下角） -->
    <AgentWorkbench />
  </div>
</template>

<script setup lang="ts">
import '../assets/styles/components/navigation.css'
import '../assets/styles/layouts/main.css'

import { ref } from 'vue'
import SystemBrand from '../components/layout/SystemBrand.vue'
import TopNav from '../components/layout/TopNav.vue'
import TopBarRight from '../components/layout/TopBarRight.vue'
import AppSidebar from '../components/layout/AppSidebar.vue'
import AgentWorkbench from '../views/AiChat/components/AgentWorkbench.vue'
import { SIDEBAR_STATE_KEY } from '../config/navigation'

// 侧栏「固定/收起」偏好（INT-894）：默认展开，localStorage 持久化、刷新/重登保持。
// 语义照 React `getCookie('iatp:sidebar:v1:state') !== 'false'`——存「展开」布尔，缺省展开。
// 显式切换由 AppSidebar 写回；本值同时接收 hover 临时展开的 display 态（内容区随之平移）。
function readSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_STATE_KEY) === 'false'
  } catch {
    return false
  }
}

const sidebarCollapsed = ref(readSidebarCollapsed())
</script>

<style scoped>
.authenticated-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: var(--background);
}
.authenticated-header {
  display: flex;
  align-items: center;
  gap: 24px;
  height: var(--header-height);
  padding: 0 var(--page-margin);
  background: var(--card);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  z-index: 100;
}
.authenticated-header__nav {
  flex: 1;
  min-width: 0;
}
.authenticated-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}
/* 覆盖 layouts/main.css 的 .main-content 全局规则：flex 布局下高度交由容器约束 */
.authenticated-body :deep(.main-content) {
  min-height: 0;
}
</style>
