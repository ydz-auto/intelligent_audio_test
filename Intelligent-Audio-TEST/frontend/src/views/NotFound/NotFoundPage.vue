<template>
  <div class="not-found">
    <div class="content">
      <h1>404</h1>
      <p>页面不存在</p>
      <router-link to="/" class="back-link">返回首页</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  /* INT-295：按可视内容区高度居中，避免 60vh 留下的页脚大段留白 */
  min-height: calc(100vh - var(--header-height) - var(--footer-height));
}
.content {
  text-align: center;
}
.content h1 {
  font-size: 72px;
  color: var(--secondary);
  margin-bottom: 10px;
}
.content p {
  font-size: 18px;
  color: var(--color-gray-500);
  margin-bottom: 20px;
}
.back-link {
  display: inline-block;
  padding: 8px 24px;
  background: var(--secondary);
  color: white;
  border-radius: 4px;
  text-decoration: none;
}
.back-link:hover {
  background: var(--color-blue-600);
}
</style>
