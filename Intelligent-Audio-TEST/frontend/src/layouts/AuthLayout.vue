<template>
  <div class="auth-layout">
    <!-- 登录壳：居中卡片（登录/注册页自含卡片，本壳仅提供全屏容器与背景） -->
    <main class="auth-layout__main">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.auth-layout {
  min-height: 100vh;
  background: var(--muted);
}
.auth-layout__main {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
