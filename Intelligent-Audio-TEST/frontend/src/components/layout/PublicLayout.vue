<template>
  <div class="public-layout">
    <PublicHeader />
    <main class="public-main">
      <router-view />
    </main>
    <PublicFooter />
  </div>
</template>

<script setup lang="ts">
import PublicHeader from './PublicHeader.vue'
import PublicFooter from './PublicFooter.vue'
</script>

<style scoped>
.public-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--background);
  color: var(--foreground);
}
.public-main {
  flex: 1;
}
</style>
