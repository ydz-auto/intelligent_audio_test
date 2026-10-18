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
/* INT-745 P1 修复：公共页挂 .app-container（height:100vh; overflow:hidden）壳内，
   .public-layout 自管滚动（与业务页 .main-content overflow-y:auto 同口径），
   站头 sticky 在滚动视口内吸附顶部，页脚随内容滚动可达。 */
.public-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow-y: auto;
  background: var(--background);
  color: var(--foreground);
}
.public-main {
  flex: 1;
}
</style>
