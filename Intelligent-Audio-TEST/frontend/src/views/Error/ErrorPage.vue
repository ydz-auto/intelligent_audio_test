<template>
  <div class="error-page">
    <div class="error-card">
      <h1 class="error-code">{{ code }}</h1>
      <p class="error-title">{{ title }}</p>
      <p class="error-desc">{{ description }}</p>
      <div class="error-actions">
        <router-link to="/" class="btn btn-secondary">返回首页</router-link>
        <button v-if="code !== '401' && code !== '403'" class="btn btn-primary" @click="goBack">返回上一页</button>
        <button v-if="code === '401' || code === '403'" class="btn btn-primary" @click="goLogin">去登录</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'

import { computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps<{
  code: number | string
}>()

const router = useRouter()

const CODE_INFO: Record<string, { title: string; description: string }> = {
  '401': { title: '未登录或登录已过期', description: '请先登录后再访问该页面。' },
  '403': { title: '没有访问权限', description: '您没有权限访问该页面，请联系管理员。' },
  '404': { title: '页面不存在', description: '您访问的页面不存在或已被移除。' },
  '500': { title: '服务器内部错误', description: '服务器开小差了，请稍后再试。' },
  '503': { title: '服务暂不可用', description: '服务正在维护中，请稍后再试。' },
}

const code = computed(() => String(props.code))
const title = computed(() => CODE_INFO[code.value]?.title || '发生错误')
const description = computed(() => CODE_INFO[code.value]?.description || '未知错误，请稍后再试。')

function goBack() {
  router.back()
}

function goLogin() {
  router.push({ name: 'login' })
}
</script>

<style scoped>
.error-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--muted);
  padding: 24px;
}
.error-card {
  text-align: center;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  padding: 48px 56px;
  max-width: 480px;
  width: 100%;
}
.error-code {
  font-size: 72px;
  font-weight: 700;
  color: var(--primary);
  margin: 0;
  line-height: 1;
}
.error-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--foreground);
  margin: 16px 0 8px;
}
.error-desc {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0 0 24px;
}
.error-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}
</style>
