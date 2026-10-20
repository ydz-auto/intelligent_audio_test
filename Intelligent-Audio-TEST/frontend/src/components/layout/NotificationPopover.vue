<template>
  <div class="notification-popover" ref="rootRef">
    <button class="header-icon-btn" data-layout-btn :title="'通知'" @click.stop="handleBellClick">
      <i class="far fa-bell"></i>
      <span v-if="unreadCount > 0" class="notification-badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
    </button>

    <div v-if="open" class="notification-panel" @click.stop>
      <div class="notification-tabs">
        <button class="notification-tab" data-layout-btn :class="{ 'notification-tab--active': activeTab === 'notice' }" @click="switchTab('notice')">
          通知
        </button>
        <button class="notification-tab" data-layout-btn :class="{ 'notification-tab--active': activeTab === 'announce' }" @click="switchTab('announce')">
          公告
        </button>
      </div>

      <!-- 通知页签：SSE 事件流 -->
      <div v-if="activeTab === 'notice'" class="notification-body">
        <ul v-if="events.length" class="notification-list">
          <li v-for="(ev, idx) in events" :key="idx" class="notification-item">
            <span class="notification-item__tag" :class="`notification-item__tag--${tagClass(ev.event)}`">{{ ev.event }}</span>
            <span class="notification-item__time">{{ formatTime(ev.receivedAt) }}</span>
            <p class="notification-item__text">{{ summarize(ev) }}</p>
          </li>
        </ul>
        <div v-else class="notification-empty">
          <i class="fas fa-inbox"></i>
          <p>暂无实时通知</p>
        </div>
      </div>

      <!-- 公告页签：site.notice -->
      <div v-else class="notification-body">
        <div v-if="noticeContent" class="notice-content">
          <p class="notice-text">{{ noticeContent }}</p>
          <p class="notice-meta">站点公告</p>
        </div>
        <div v-else class="notification-empty">
          <i class="fas fa-bullhorn"></i>
          <p>暂无公告</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '../../store/authStore'
import { useRequireLogin } from '../../composables/layout/useRequireLogin'
import { connectSseEvents, type SseConnection } from '../../infrastructure/api/notificationApi'
import { getSiteNotice } from '../../infrastructure/api/optionsApi'
import type { SseNotificationEvent } from '../../domain/model/notification'

const authStore = useAuthStore()
const requireLogin = useRequireLogin()

const open = ref(false)
const activeTab = ref<'notice' | 'announce'>('notice')
const events = ref<SseNotificationEvent[]>([])
const noticeContent = ref('')
const rootRef = ref<HTMLElement | null>(null)
let connection: SseConnection | null = null

const READ_KEY = 'iatp:notice:read:v1'
const unreadCount = ref(0)

function tagClass(event: string): string {
  if (event.includes('report')) return 'report'
  if (event.includes('import')) return 'import'
  if (event.includes('progress') || event.includes('task')) return 'task'
  return 'other'
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function summarize(ev: SseNotificationEvent): string {
  const data = ev.data || {}
  const keys = ['message', 'title', 'name', 'status', 'event']
  for (const k of keys) {
    if (typeof data[k] === 'string' && (data[k] as string).length) return data[k] as string
  }
  return JSON.stringify(data).slice(0, 80)
}

function onSseEvent(ev: SseNotificationEvent) {
  // 忽略 heartbeat 与 progress 噪音类事件（展示层收敛为有意义的通知）
  if (ev.event === 'task_progress' || ev.event === 'import_progress' || ev.event === 'realtime_frame') {
    if (ev.event === 'import_progress' && ev.data?.stage) {
      // 保留导入进度事件
    } else {
      return
    }
  }
  events.value = [ev, ...events.value].slice(0, 50)
  // 未读计数：仅当面板关闭期间到达的事件计为未读
  if (!open.value) {
    unreadCount.value += 1
  }
}

function openConnection() {
  if (connection) return
  connection = connectSseEvents(onSseEvent)
}

function closeConnection() {
  if (connection) {
    connection.close()
    connection = null
  }
}

function handleBellClick() {
  if (!authStore.isLoggedIn) {
    requireLogin.open()
    return
  }
  open.value = !open.value
  if (open.value) {
    // 打开：连接 SSE + 拉公告 + 清未读
    openConnection()
    loadNotice()
    markRead()
  } else {
    closeConnection()
  }
}

async function loadNotice() {
  // guest 等无 option:read 角色不拉取系统选项，避免 /api/option/ 403 控制台报错
  // （INT-978）；无权限/拉取失败时展示空公告态
  if (!authStore.hasPermission('option:read')) {
    noticeContent.value = ''
    return
  }
  try {
    noticeContent.value = await getSiteNotice()
  } catch {
    noticeContent.value = ''
  }
}

function markRead() {
  unreadCount.value = 0
  try {
    localStorage.setItem(READ_KEY, Date.now().toString())
  } catch { /* 忽略 */ }
}

function switchTab(tab: 'notice' | 'announce') {
  activeTab.value = tab
  if (tab === 'announce') loadNotice()
}

function handleOutsideClick(event: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(event.target as Node)) {
    open.value = false
    closeConnection()
  }
}

onMounted(() => document.addEventListener('click', handleOutsideClick))
onUnmounted(() => {
  document.removeEventListener('click', handleOutsideClick)
  closeConnection()
})
</script>

<style scoped>
.header-icon-btn {
  width: var(--control-height);
  height: var(--control-height);
  border-radius: var(--radius-control);
  border: none;
  background: transparent;
  color: var(--muted-foreground);
  font-size: 16px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  position: relative;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.header-icon-btn:hover {
  background: var(--gray-light);
  color: var(--foreground);
}
.notification-badge {
  position: absolute;
  top: 2px;
  right: 0;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: var(--radius-pill);
  background: var(--destructive);
  color: var(--color-white);
  font-size: 10px;
  line-height: 16px;
  text-align: center;
}
.notification-popover {
  position: relative;
}
.notification-panel {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  width: 340px;
  background: var(--popover);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-index-popover);
  overflow: hidden;
}
.notification-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
}
.notification-tab {
  flex: 1;
  padding: 10px 0;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  font-size: 14px;
  color: var(--muted-foreground);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.notification-tab:hover {
  color: var(--foreground);
}
.notification-tab--active {
  color: var(--primary);
  font-weight: 600;
  border-bottom-color: var(--primary);
}
.notification-body {
  max-height: 320px;
  overflow-y: auto;
}
.notification-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.notification-item {
  padding: 10px 14px;
  border-bottom: 1px solid var(--gray-light);
}
.notification-item__tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: var(--radius-tag);
  font-size: 11px;
  margin-right: 8px;
  background: var(--gray-light);
  color: var(--muted-foreground);
}
.notification-item__tag--report { background: var(--success-light); color: var(--success-dark); }
.notification-item__tag--import { background: var(--warning-light); color: var(--warning-dark); }
.notification-item__tag--task { background: var(--secondary-light); color: var(--secondary-deep); }
.notification-item__time {
  font-size: 12px;
  color: var(--text-tertiary);
}
.notification-item__text {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--foreground);
  line-height: 1.5;
}
.notice-content {
  padding: 16px 14px;
}
.notice-text {
  margin: 0;
  font-size: 14px;
  color: var(--foreground);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.notice-meta {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}
.notification-empty {
  padding: 32px 0;
  text-align: center;
  color: var(--text-tertiary);
}
.notification-empty i {
  font-size: 28px;
  margin-bottom: 8px;
  opacity: 0.6;
}
.notification-empty p {
  margin: 0;
  font-size: 13px;
}
</style>
