<template>
  <div class="account-settings-redirect" />
</template>

<script setup lang="ts">
/**
 * /AccountSettings 旧链 redirect → /profile（13_个人中心 §2.1/§3.5.2，INT-744）。
 * 原账号设置页并入个人中心；redirect **保留 query**（bind_ticket/bind_error）——
 * 供 OAuth 绑定回调（oauth_bp.py:30 _FRONTEND_BIND_REDIRECT 现指向 #/AccountSettings）
 * 302 回落后携票转入 /profile，页面 onMount 消化后清参。
 * 用组件内 router.replace（非路由级 redirect）：避免首屏落地时丢 search（对齐 React INT-513 实测）。
 */
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

onMounted(() => {
  router.replace({ name: 'profile', query: { ...route.query } })
})
</script>
