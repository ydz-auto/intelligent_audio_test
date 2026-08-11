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
  min-height: 60vh;
}
.content {
  text-align: center;
}
.content h1 {
  font-size: 72px;
  color: #4a90d9;
  margin-bottom: 10px;
}
.content p {
  font-size: 18px;
  color: #666;
  margin-bottom: 20px;
}
.back-link {
  display: inline-block;
  padding: 8px 24px;
  background: #4a90d9;
  color: white;
  border-radius: 4px;
  text-decoration: none;
}
.back-link:hover {
  background: #357abd;
}
</style>
