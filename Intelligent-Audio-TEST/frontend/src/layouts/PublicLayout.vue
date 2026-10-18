<template>
  <div class="public-layout">
    <header class="public-layout__header">
      <SystemBrand />
      <TopNav class="public-layout__nav" />
      <TopBarRight mode="public" />
    </header>

    <main class="public-layout__main">
      <router-view />
    </main>

    <footer class="public-layout__footer">
      <div class="public-layout__footer-brand">
        <i class="fas fa-headset"></i>
        <span>{{ footerText }}</span>
      </div>
      <p class="public-layout__footer-copy">
        © 2026 智能语音测试系统 · 保留所有权利
      </p>
    </footer>
  </div>
</template>

<script setup lang="ts">
import SystemBrand from '../components/layout/SystemBrand.vue'
import TopNav from '../components/layout/TopNav.vue'
import TopBarRight from '../components/layout/TopBarRight.vue'

const footerText = '智能语音测试系统'
</script>

<style scoped>
.public-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--background);
}
.public-layout__header {
  display: flex;
  align-items: center;
  gap: 24px;
  height: var(--header-height);
  padding: 0 var(--page-margin);
  background: var(--card);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
}
.public-layout__nav {
  flex: 1;
  min-width: 0;
}
.public-layout__main {
  flex: 1;
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: var(--page-margin);
}
.public-layout__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px var(--page-margin);
  background: var(--muted);
  border-top: 1px solid var(--border);
}
.public-layout__footer-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}
.public-layout__footer-brand i {
  color: var(--primary);
  font-size: 16px;
}
.public-layout__footer-copy {
  margin: 0;
  color: var(--text-tertiary);
  font-size: 12px;
}
</style>
