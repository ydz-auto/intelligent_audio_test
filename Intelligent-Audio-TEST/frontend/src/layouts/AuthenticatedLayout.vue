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

const sidebarCollapsed = ref(true)
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
