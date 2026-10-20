<template>
  <div class="login-required-modal">
    <div class="lr-icon">
      <i class="fas fa-lock"></i>
    </div>
    <p class="lr-description">请登录后查看{{ moduleName ? ` ${moduleName}。` : '。' }}</p>
    <p class="lr-countdown">将在 <strong>{{ countdown }}</strong> 秒后跳转到登录页。</p>
    <div class="lr-actions">
      <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
      <button type="button" class="btn btn-primary" @click="handleConfirm">立即登录</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/log.css'

import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useModalControl } from '../../../composables/modal/useModal'

/**
 * 公开页「需要登录」引导（INT-745，受限项 Dialog）
 * 由 GlobalModalContainer 承载（BasicModal 内），5 秒倒计时后自动 confirm，
 * 调用方（useLoginRequired）负责跳转登录页并带 redirect。
 */
const props = defineProps({
  modalId: { type: String, required: true },
  /** 模块名（用于「请登录后查看 {模块名}。」） */
  moduleName: { type: String, default: '' },
  /** 登录后回跳路径（由调用方消费，本组件不直接导航） */
  redirect: { type: String, default: '/' },
})

const emit = defineEmits(['close', 'confirm', 'cancel'])

const modalManager = useModalControl()

const COUNTDOWN_SECONDS = 5
const countdown = ref(COUNTDOWN_SECONDS)
let timer: ReturnType<typeof setInterval> | null = null

function clearTimer() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function handleConfirm() {
  clearTimer()
  emit('confirm', { confirmed: true, redirect: props.redirect })
}

function handleCancel() {
  clearTimer()
  emit('cancel', { confirmed: false })
}

onMounted(() => {
  timer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) {
      clearTimer()
      emit('confirm', { confirmed: true, redirect: props.redirect })
    }
  }, 1000)
})

onBeforeUnmount(() => {
  clearTimer()
})
</script>

<style scoped>
.login-required-modal {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
  padding: 4px 0;
}
.lr-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: var(--primary);
}
.lr-description {
  margin: 0;
  font-size: 15px;
  color: var(--foreground);
  line-height: 1.6;
}
.lr-countdown {
  margin: 0;
  font-size: 13px;
  color: var(--muted-foreground);
}
.lr-countdown strong {
  color: var(--primary);
}
.lr-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 4px;
}
</style>
