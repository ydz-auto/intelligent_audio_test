<template>
  <div class="ai-chat-message" :class="[`message--${message.from}`, { 'message--error': message.status === 'error' }]">
    <div class="message-row">
      <!-- 用户消息：右侧气泡 -->
      <div v-if="message.from === 'user'" class="message-bubble user-bubble">
        <span v-if="isEditing" class="message-edit-label">{{ MESSAGE_ACTION_LABELS.edit }}</span>
        <div v-if="!isEditing" class="message-text">{{ currentContent }}</div>
        <div v-else class="message-edit">
          <textarea
            v-model="editContent"
            class="message-edit-textarea"
            rows="4"
            @keydown.enter.prevent="saveEdit"
          ></textarea>
          <div class="message-edit-actions">
            <button type="button" class="btn btn-sm btn-primary" @click="saveEdit">{{ MESSAGE_COPY.save }}</button>
            <button type="button" class="btn btn-sm btn-secondary" @click="cancelEdit">{{ MESSAGE_COPY.reset }}</button>
          </div>
        </div>
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
          <div class="message-text message-text--doc">{{ currentContent }}</div>
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
import { computed, ref, watch } from 'vue'
import type { ChatMessage } from '@/domain/model/aiChat'
import {
  AGENT_TOOL_STATUS_LABELS,
  ERROR_MESSAGES,
  MESSAGE_ACTION_LABELS,
  MESSAGE_COPY,
} from '@/domain/constants/aiChat'

const props = defineProps<{
  message: ChatMessage
  isGenerating: boolean
  isEditing: boolean
  alwaysShowActions: boolean
}>()

const emit = defineEmits<{
  (e: 'regenerate', key: string): void
  (e: 'edit', key: string): void
  (e: 'delete', key: string): void
  (e: 'save-edit', content: string, resend: boolean): void
  (e: 'cancel-edit'): void
  (e: 'view-document'): void
}>()

const editContent = ref('')

const currentContent = computed(
  () =>
    props.message.versions[props.message.versions.length - 1]?.content ?? ''
)

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
    if (editing) editContent.value = currentContent.value
  }
)

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

function saveEdit(): void {
  const content = editContent.value
  if (!content.trim()) return
  emit('save-edit', content, false)
}

function cancelEdit(): void {
  emit('cancel-edit')
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
  box-shadow: 0 1px 2px color-mix(in srgb, var(--color-black) 6%, transparent);
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

.message-edit-label {
  font-size: 12px;
  color: var(--muted-foreground);
}

.message-edit {
  margin-top: 6px;
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
  gap: 8px;
  margin-top: 8px;
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
  border-radius: 50%;
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
  border-radius: 999px;
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
