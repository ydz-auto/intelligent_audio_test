<template>
  <div class="ai-chat-message" :class="[`message--${message.from}`, { 'message--error': message.status === 'error' }]">
    <div class="message-row">
      <!-- 消息编辑器（§3.4 编辑器全套：编辑态在原位展开——assistant/user 消息均可编辑，照 React 语义） -->
      <div v-if="isEditing" class="message-edit-block" :class="`message-edit-block--${message.from}`">
        <div class="message-edit">
          <div class="message-edit-header">
            <span class="message-edit-label">{{ MESSAGE_COPY.editTitle }}</span>
            <span class="message-edit-dirty" :class="{ 'message-edit-dirty--active': hasChanged }">
              {{ hasChanged ? MESSAGE_COPY.editDirty : MESSAGE_COPY.editClean }}
            </span>
          </div>
          <textarea
            v-model="editContent"
            class="message-edit-textarea"
            rows="4"
            @keydown.enter.prevent="saveEdit(false)"
          ></textarea>
          <div class="message-edit-actions">
            <button v-if="hasChanged" type="button" class="btn btn-sm btn-primary" @click="saveEdit(true)">
              <i class="fas fa-paper-plane"></i>
              <span>{{ MESSAGE_COPY.saveAndResend }}</span>
            </button>
            <button type="button" class="btn btn-sm btn-primary" @click="saveEdit(false)">
              <i class="fas fa-check"></i>
              <span>{{ MESSAGE_COPY.save }}</span>
            </button>
            <button v-if="hasChanged" type="button" class="btn btn-sm btn-secondary" @click="resetEdit">
              <i class="fas fa-rotate-left"></i>
              <span>{{ MESSAGE_COPY.reset }}</span>
            </button>
            <button type="button" class="btn btn-sm btn-text" @click="handleCancelEdit">
              <i class="fas fa-xmark"></i>
              <span>{{ MESSAGE_COPY.cancel }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 用户消息：右侧气泡 -->
      <div v-else-if="message.from === 'user'" class="message-bubble user-bubble">
        <div class="message-text">{{ currentContent }}</div>
      </div>

      <!-- 助手消息：左侧文档面 -->
      <div v-else class="message-doc">
        <!-- 工具调用卡（DSH 工具，§3.4；待后端立项） -->
        <div v-if="message.toolCalls && message.toolCalls.length" class="tool-cards">
          <div
            v-for="tool in message.toolCalls"
            :key="tool.id"
            class="tool-card"
          >
            <div class="tool-card-header">
              <i class="fas fa-bolt tool-card-icon"></i>
              <span class="tool-card-label">{{ tool.label }}</span>
              <span class="tool-card-status" :class="`tool-status--${tool.status}`">
                {{ AGENT_TOOL_STATUS_LABELS[tool.status] }}
              </span>
            </div>
            <div v-if="tool.summary" class="tool-card-summary">{{ tool.summary }}</div>
          </div>
        </div>

        <!-- 文档变更卡（studio_apply_edit/restore；待后端立项） -->
        <div v-if="message.documentChanges && message.documentChanges.length" class="document-change-card">
          <i class="fas fa-file-pen document-change-icon"></i>
          <span>文档已更新 · 版本 {{ message.documentChanges[0].version }}</span>
          <button
            v-if="!isGenerating"
            type="button"
            class="btn btn-text btn-sm"
            @click="emit('view-document')"
          >{{ MESSAGE_ACTION_LABELS.viewDocument }}</button>
        </div>

        <!-- 思考过程（DSH 推理事件待后端立项，版式先行） -->
        <div v-if="message.reasoning" class="reasoning-block">
          <i class="fas fa-brain reasoning-icon"></i>
          <span class="reasoning-title">
            {{ message.isReasoningStreaming ? MESSAGE_COPY.thinking : MESSAGE_COPY.replied.replace('{n}', String(message.reasoning.duration)) }}
          </span>
        </div>

        <!-- 正文 -->
        <div v-if="message.status === 'loading'" class="message-loading">
          <span class="loading-spinner-small"></span>
          <span class="loading-text">正在回复...</span>
        </div>
        <template v-else>
          <!-- 源码视图（§3.4 CodeBlock「原始回复」collapsedLines=24）：替换正文显示 -->
          <div v-if="isSourceVisible && currentContent && message.status !== 'error'" class="message-source">
            <div class="message-source-header">
              <i class="fas fa-code message-source-icon"></i>
              <span class="message-source-title">{{ MESSAGE_ACTION_LABELS.sourceTitle }}</span>
              <span class="message-source-spacer"></span>
              <button type="button" class="message-source-toggle" @click="sourceExpanded = !sourceExpanded">
                {{ sourceExpanded ? MESSAGE_ACTION_LABELS.collapseSource : MESSAGE_ACTION_LABELS.expandSource }}
              </button>
            </div>
            <pre class="message-source-body" :class="{ 'message-source-body--expanded': sourceExpanded }">{{ currentContent }}</pre>
          </div>
          <div v-else-if="message.status !== 'error'" class="message-text message-text--doc">{{ currentContent }}</div>
          <!-- 元数据（时间 + 响应时长） -->
          <div v-if="message.status === 'complete' && message.createdAt" class="message-metadata">
            <span>{{ formatTime(message.createdAt) }}</span>
            <span v-if="message.durationMs !== undefined" class="metadata-duration">
              {{ MESSAGE_COPY.responseTime.replace('{duration}', formatDuration(message.durationMs)) }}
            </span>
          </div>
          <!-- 错误态 -->
          <div v-if="message.status === 'error'" class="message-error">
            <i class="fas fa-circle-exclamation message-error-icon"></i>
            <span>{{ currentContent || ERROR_MESSAGES.generic }}</span>
          </div>
        </template>

        <!-- 消息操作（assistant hover 显 / 最后一条恒显） -->
        <div
          v-if="message.from === 'assistant' && !isEditing"
          class="message-actions"
          :class="{ 'message-actions--always': alwaysShowActions }"
        >
          <button
            type="button"
            class="action-btn"
            title="复制"
            :disabled="isGenerating"
            @click="copyContent"
          >
            <i class="fas fa-copy"></i>
          </button>
          <button
            v-if="currentContent && message.status !== 'error'"
            type="button"
            class="action-btn"
            :title="isSourceVisible ? MESSAGE_ACTION_LABELS.showPreview : MESSAGE_ACTION_LABELS.showSource"
            :disabled="isGenerating"
            @click="emit('toggle-source', message.key)"
          >
            <i class="fas fa-code"></i>
          </button>
          <button
            type="button"
            class="action-btn"
            title="重新生成"
            :disabled="isGenerating"
            @click="emit('regenerate', message.key)"
          >
            <i class="fas fa-rotate"></i>
          </button>
          <button
            v-if="message.status === 'error'"
            type="button"
            class="action-btn"
            title="重试"
            :disabled="isGenerating"
            @click="emit('regenerate', message.key)"
          >
            <i class="fas fa-arrow-rotate-right"></i>
          </button>
          <button
            type="button"
            class="action-btn"
            title="编辑"
            :disabled="isGenerating"
            @click="emit('edit', message.key)"
          >
            <i class="fas fa-pen"></i>
          </button>
          <button
            type="button"
            class="action-btn action-btn--danger"
            title="删除"
            @click="emit('delete', message.key)"
          >
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/components/form.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/progress.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

import { computed, onUnmounted, ref, watch } from 'vue'
import type { ChatMessage } from '@/domain/model/aiChat'
import {
  AGENT_TOOL_STATUS_LABELS,
  ERROR_MESSAGES,
  MESSAGE_ACTION_LABELS,
  MESSAGE_COPY,
} from '@/domain/constants/aiChat'
import { useModalControl } from '@/composables/modal/useModal'
import { MODAL_TYPES } from '@/composables/modal/constants'

const props = defineProps<{
  message: ChatMessage
  isGenerating: boolean
  isEditing: boolean
  isSourceVisible: boolean
  alwaysShowActions: boolean
}>()

const emit = defineEmits<{
  (e: 'regenerate', key: string): void
  (e: 'edit', key: string): void
  (e: 'delete', key: string): void
  (e: 'save-edit', content: string, resend: boolean): void
  (e: 'cancel-edit'): void
  (e: 'toggle-source', key: string): void
  (e: 'view-document'): void
}>()

const modalControl = useModalControl()

const editContent = ref('')
const sourceExpanded = ref(false)

const currentContent = computed(
  () => props.message.versions[props.message.versions.length - 1]?.content ?? ''
)

/** 编辑是否有未保存更改（§3.4：驱动「保存并重发」/「重置」显隐 + beforeunload 守卫） */
const hasChanged = computed(() => editContent.value !== currentContent.value)

watch(
  () => props.message.versions,
  () => {
    editContent.value = currentContent.value
  },
  { immediate: true, deep: true }
)

watch(
  () => props.isEditing,
  (editing) => {
    if (editing) {
      editContent.value = currentContent.value
      sourceExpanded.value = false
    }
  }
)

/** beforeunload 守卫：编辑中有未保存更改时拦截刷新/离开（§3.4 编辑器全套） */
function handleBeforeUnload(event: BeforeUnloadEvent): void {
  event.preventDefault()
  event.returnValue = ''
}

watch(
  () => props.isEditing && hasChanged.value,
  (dirty) => {
    if (dirty) {
      window.addEventListener('beforeunload', handleBeforeUnload)
    } else {
      window.removeEventListener('beforeunload', handleBeforeUnload)
    }
  }
)

onUnmounted(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
})

function formatTime(ts: number): string {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

async function copyContent(): Promise<void> {
  const text = currentContent.value
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // 剪贴板权限被拒：静默（不影响对话）
  }
}

function saveEdit(resend: boolean): void {
  const content = editContent.value
  if (!content.trim()) return
  emit('save-edit', content, resend)
}

function resetEdit(): void {
  editContent.value = currentContent.value
}

/** 取消：有未保存更改 → 离开确认（ConfirmDialog，§3.4）；无更改直接退出编辑 */
async function handleCancelEdit(): Promise<void> {
  if (hasChanged.value) {
    try {
      await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: MESSAGE_COPY.leaveConfirmTitle,
        content: MESSAGE_COPY.leaveConfirm,
        confirmText: MESSAGE_COPY.leave,
        cancelText: MESSAGE_COPY.stay,
        danger: true,
      })
      emit('cancel-edit')
    } catch {
      // 留在编辑态
    }
  } else {
    emit('cancel-edit')
  }
}
</script>

<style scoped>
.ai-chat-message {
  width: 100%;
  margin-bottom: 8px;
}

.message-row {
  display: flex;
  flex-direction: column;
}

/* ===== 用户消息：右侧气泡 ===== */
.message--user .message-row {
  align-items: flex-end;
}

.user-bubble {
  max-width: 85%;
  background: var(--muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  border-bottom-right-radius: var(--radius-sm);
  padding: 10px 14px;
  box-shadow: var(--shadow-sm);
}

/* ===== 助手消息：左侧文档面 ===== */
.message--assistant .message-row {
  align-items: flex-start;
}

.message-doc {
  width: 100%;
  max-width: 78ch;
}

.message-text {
  font-size: 0.95rem;
  line-height: 1.6;
  color: var(--foreground);
  white-space: pre-wrap;
  word-break: break-word;
}

.message-text--doc {
  color: var(--foreground);
}

/* ===== 消息编辑器（§3.4 编辑器全套：标题 + 未保存提示 + 钮组 + 守卫） ===== */
.message-edit-block {
  width: 100%;
  max-width: 78ch;
}

.message-edit-block--user {
  margin-left: auto;
  max-width: 85%;
}

.message-edit-block--assistant {
  margin-right: auto;
}

.message-edit {
  margin-top: 6px;
}

.message-edit-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.message-edit-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--foreground);
}

.message-edit-dirty {
  font-size: 11px;
  color: var(--muted-foreground);
}

.message-edit-dirty--active {
  color: var(--warning-dark, var(--muted-foreground));
}

.message-edit-textarea {
  width: 100%;
  min-height: 72px;
  padding: 10px;
  border: 1px solid var(--input);
  border-radius: var(--radius-sm);
  font: inherit;
  font-size: 13px;
  line-height: 1.6;
  color: var(--foreground);
  background: var(--card);
  resize: vertical;
  box-sizing: border-box;
}

.message-edit-textarea:focus {
  outline: none;
  border-color: var(--ring);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--ring) 20%, transparent);
}

.message-edit-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

/* ===== 源码视图（§3.4 CodeBlock「原始回复」collapsedLines=24） ===== */
.message-source {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--card);
  overflow: hidden;
}

.message-source-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--muted);
}

.message-source-icon {
  color: var(--muted-foreground);
  font-size: 12px;
}

.message-source-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--foreground);
}

.message-source-spacer {
  flex: 1;
}

.message-source-toggle {
  border: none;
  background: transparent;
  color: var(--primary);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
  padding: 0;
}

.message-source-toggle:hover {
  color: var(--primary-hover);
}

.message-source-body {
  margin: 0;
  padding: 10px 12px;
  font-family: var(--font-mono, Consolas, 'Courier New', monospace);
  font-size: 12px;
  line-height: 1.6;
  color: var(--foreground);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: calc(1.6em * 24);
  overflow: hidden;
}

.message-source-body--expanded {
  max-height: none;
  overflow-y: auto;
}

.message-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  color: var(--muted-foreground);
  font-size: 13px;
}

.loading-spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--primary);
  border-radius: var(--radius-full);
  animation: ai-chat-spin 0.8s linear infinite;
}

@keyframes ai-chat-spin {
  to {
    transform: rotate(360deg);
  }
}

.message-metadata {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
  font-size: 11px;
  color: var(--muted-foreground);
}

.message-error {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 8px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--destructive) 30%, transparent);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--destructive) 8%, transparent);
  color: var(--destructive);
  font-size: 13px;
}

.message-error-icon {
  margin-top: 2px;
}

/* ===== 工具调用卡（§3.4；待后端立项） ===== */
.tool-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
}

.tool-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--card);
  padding: 8px 12px;
}

.tool-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tool-card-icon {
  color: var(--secondary);
  font-size: 12px;
}

.tool-card-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
}

.tool-card-status {
  margin-left: auto;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.tool-status--pending,
.tool-status--running {
  background: var(--warning-light, color-mix(in srgb, var(--warning) 15%, transparent));
  color: var(--warning-dark, var(--foreground));
}

.tool-status--completed {
  background: var(--success-light, color-mix(in srgb, var(--success) 15%, transparent));
  color: var(--success-dark, var(--foreground));
}

.tool-status--error {
  background: color-mix(in srgb, var(--destructive) 12%, transparent);
  color: var(--destructive);
}

.tool-card-summary {
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted-foreground);
}

.document-change-card {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--card);
  font-size: 13px;
  color: var(--foreground);
}

.document-change-icon {
  color: var(--primary);
}

.reasoning-block {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--primary);
}

/* ===== 消息操作 ===== */
.message-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  opacity: 0;
  transition: opacity 0.2s;
}

.message--assistant:hover .message-actions,
.message-actions--always {
  opacity: 1;
}

.action-btn {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--muted-foreground);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}

.action-btn:hover:not(:disabled) {
  background: var(--muted);
  color: var(--foreground);
}

.action-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.action-btn--danger:hover:not(:disabled) {
  color: var(--destructive);
}
</style>
