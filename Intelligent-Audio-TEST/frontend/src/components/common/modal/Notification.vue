<template>
  <Teleport to="body">
    <div v-if="visible" class="notification-container">
      <div class="notification-content" :class="[`notification--${type}`]">
        <div class="notification-icon">
          <i :class="iconClass"></i>
        </div>
        <div class="notification-body">
          <div class="notification-message" v-html="formattedMessage"></div>
          <div v-if="details" class="notification-details">
            <div class="notification-details-header" @click="showDetails = !showDetails">
              <span>详细信息</span>
              <i :class="showDetails ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"></i>
            </div>
            <div v-if="showDetails" class="notification-details-content">
              <pre>{{ details }}</pre>
              <button class="copy-btn" @click="copyDetails">复制</button>
            </div>
          </div>
        </div>
        <button class="notification-close" @click="close">
          <i class="fas fa-times"></i>
        </button>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const visible = ref(false)
const message = ref('')
const type = ref('error')
const details = ref('')
const showDetails = ref(false)
let timer = null

const iconClass = computed(() => {
  const icons = {
    error: 'fas fa-exclamation-circle',
    warning: 'fas fa-exclamation-triangle',
    success: 'fas fa-check-circle',
    info: 'fas fa-info-circle'
  }
  return icons[type.value] || icons.info
})

const formattedMessage = computed(() => {
  return message.value.replace(/\n/g, '<br>')
})

function show(msg, msgType = 'error', msgDetails = '') {
  message.value = msg
  type.value = msgType
  details.value = msgDetails
  visible.value = true
  showDetails.value = false
  
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    close()
  }, 10000)
}

function close() {
  visible.value = false
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
}

function copyDetails() {
  navigator.clipboard.writeText(details.value).then(() => {
    const btn = document.activeElement;
    if (btn && btn.classList.contains('copy-btn')) {
      btn.textContent = '已复制!';
      setTimeout(() => btn.textContent = '复制', 1500);
    }
  })
}

function handleKeydown(e) {
  if (e.key === 'Escape' && visible.value) {
    close()
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  if (timer) clearTimeout(timer)
})

defineExpose({ show, close })
</script>

<style scoped>
.notification-container {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 10000;
  max-width: 500px;
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

.notification-content {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  background: white;
  border: 1px solid #e5e7eb;
}

.notification--error {
  border-left: 4px solid #dc2626;
}

.notification--error .notification-icon {
  color: #dc2626;
}

.notification--warning {
  border-left: 4px solid #f59e0b;
}

.notification--warning .notification-icon {
  color: #f59e0b;
}

.notification--success {
  border-left: 4px solid #10b981;
}

.notification--success .notification-icon {
  color: #10b981;
}

.notification--info {
  border-left: 4px solid #3b82f6;
}

.notification--info .notification-icon {
  color: #3b82f6;
}

.notification-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.notification-body {
  flex: 1;
  min-width: 0;
}

.notification-message {
  font-size: 14px;
  color: #1f2937;
  line-height: 1.5;
  word-break: break-word;
}

.notification-details {
  margin-top: 8px;
  border-top: 1px solid #e5e7eb;
  padding-top: 8px;
}

.notification-details-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #6b7280;
  cursor: pointer;
  padding: 4px 0;
}

.notification-details-header:hover {
  color: #374151;
}

.notification-details-content {
  margin-top: 8px;
  position: relative;
}

.notification-details-content pre {
  background: #f3f4f6;
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 4px 8px;
  font-size: 12px;
  background: #e5e7eb;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.copy-btn:hover {
  background: #d1d5db;
}

.notification-close {
  background: none;
  border: none;
  font-size: 16px;
  color: #9ca3af;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.notification-close:hover {
  color: #6b7280;
}
</style>
