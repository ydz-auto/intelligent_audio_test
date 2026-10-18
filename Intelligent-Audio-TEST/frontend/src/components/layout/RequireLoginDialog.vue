<template>
  <BasicModal
    v-if="visible"
    :visible="true"
    title="需要登录"
    :closable="true"
    :show-footer="false"
    :mask-closable="false"
    :max-width="'420px'"
    @close="handleClose"
  >
    <div class="require-login-content">
      <div class="require-login-icon">
        <i class="fas fa-lock"></i>
      </div>
      <p class="require-login-message">该功能需要登录后使用</p>
      <p class="require-login-tip">
        {{ countdown }} 秒后自动跳转登录页…
      </p>
      <div class="require-login-actions">
        <button class="btn btn-secondary" @click="handleClose">稍后再说</button>
        <button class="btn btn-primary" @click="handleGo">去登录</button>
      </div>
    </div>
  </BasicModal>
</template>

<script setup lang="ts">
import BasicModal from '../common/modal/BasicModal.vue'
import { useRequireLogin } from '../../composables/layout/useRequireLogin'

const { visible, countdown, goLogin, close } = useRequireLogin()

function handleGo() {
  goLogin()
}

function handleClose() {
  close()
}
</script>

<style scoped>
.require-login-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
  padding: 8px 0 4px;
}
.require-login-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  color: var(--primary);
}
.require-login-message {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
}
.require-login-tip {
  margin: 0;
  font-size: 13px;
  color: var(--muted-foreground);
}
.require-login-actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}
</style>
