<template>
  <Teleport to="body">
    <div v-if="visible" class="ai-review-session-overlay" @click.self="handleClose">
      <div class="ai-review-session-dialog">
        <!-- 头行（§5.2）：Sparkles + AI 复核 + Demo 徽标 + 展开到 /ai-chat + 关闭 -->
        <div class="session-header">
          <h3 class="session-title">
            <i class="fas fa-sparkles session-title-icon"></i>
            {{ AI_REVIEW_SESSION_COPY.title }} — {{ caseName || '用例' }}
          </h3>
          <span class="session-demo-badge" :title="AI_REVIEW_SESSION_COPY.demoTooltip">
            {{ AI_REVIEW_SESSION_COPY.demoBadge }}
          </span>
          <div class="session-header-actions">
            <button type="button" class="session-icon-btn" :title="AI_REVIEW_SESSION_COPY.expandToChat" @click="handleExpandToChat">
              <i class="fas fa-up-right-from-square"></i>
            </button>
            <button type="button" class="session-icon-btn" :title="AI_REVIEW_SESSION_COPY.close" @click="handleClose">
              <i class="fas fa-times"></i>
            </button>
          </div>
        </div>

        <!-- 副文（§5.2：结论供人工确认，不直接修改统计） -->
        <p class="session-tip">{{ AI_REVIEW_SESSION_COPY.subtitle }}</p>

        <!-- 会话区（独立 scope，关闭即释放） -->
        <div class="session-conversation" ref="scrollRef">
          <!-- 首条 assistant = 复核上下文摘要卡（§5.3） -->
          <div v-if="contextMessage" class="session-message-row">
            <AiReviewContextCard :context="session.context" />
          </div>

          <!-- 消息流（上下文卡之后的 user/assistant 消息） -->
          <div
            v-for="(message, idx) in tailMessages"
            :key="message.key"
            class="session-message-row"
            :class="`message--${message.from}`"
          >
            <!-- 用户：右侧气泡 -->
            <div v-if="message.from === 'user'" class="session-user-bubble">
              {{ currentContent(message) }}
            </div>

            <!-- assistant：左侧文档面（结论卡 + 正文；结论卡渲染时不重复展示纯文本） -->
            <div v-else class="session-assistant-doc">
              <AiReviewVerdictCard
                v-if="message.reviewMeta?.verdict && message.status === 'complete'"
                :content="currentContent(message)"
                :original-evaluation-status="originalEvaluationStatus"
              />
              <div v-else-if="message.status === 'loading'" class="session-loading">
                <span class="loading-spinner-small"></span>
                <span>{{ AI_REVIEW_CHAT_COPY.thinking }}</span>
              </div>
              <div v-else-if="message.status === 'error'" class="session-error">
                <i class="fas fa-circle-exclamation"></i>
                {{ currentContent(message) || AI_REVIEW_CHAT_COPY.error }}
              </div>
              <div v-else class="session-assistant-text">{{ currentContent(message) }}</div>
            </div>
          </div>

          <!-- 保存后：AI 复核记录卡（§5.5 后端落位结果） -->
          <div v-if="session.savedRecord" class="session-message-row">
            <AiReviewRecordCard
              :record="session.savedRecord"
              :original-evaluation-status="originalEvaluationStatus"
            />
          </div>

          <!-- 已有 AI 复核结论提示（幂等，§5.4） -->
          <div v-if="session.existingRecord && !session.savedRecord" class="session-existing-hint">
            <i class="fas fa-circle-info"></i>
            {{ AI_REVIEW_RECORD_COPY.hasExisting.replace('{time}', formatTime(session.existingRecord.createdAt)) }}
          </div>

          <p v-if="session.errorText" class="session-error-text">{{ session.errorText }}</p>
        </div>

        <!-- 追问快捷 chips（§5.4） -->
        <div class="session-chips" v-if="session.phase === 'ready' && !session.isGenerating">
          <button
            v-for="chip in AI_REVIEW_CHAT_COPY.quickChips"
            :key="chip"
            type="button"
            class="session-chip"
            @click="sendChip(chip)"
          >{{ chip }}</button>
        </div>

        <!-- 输入区（compact：供应商切换 + textarea + 发送/停止） -->
        <div class="session-input">
          <textarea
            ref="textareaRef"
            v-model="draftText"
            class="session-textarea"
            :placeholder="AI_REVIEW_CHAT_COPY.placeholder"
            :disabled="session.isGenerating"
            @keydown.enter.exact.prevent="handleSend"
          ></textarea>
          <div class="session-input-footer">
            <ModelProviderSwitcher
              :providers="chatStore.providers"
              :config="chatStore.config"
              @select-provider="(pid) => chatStore.updateConfig({ providerId: pid })"
              @select-model="(pid, mid) => chatStore.updateConfig({ providerId: pid, modelId: mid })"
              @manage-providers="providerManagerOpen = true"
            />
            <div class="session-input-actions">
              <button
                v-if="!session.isGenerating"
                type="button"
                class="session-send-btn"
                :disabled="!draftText.trim()"
                @click="handleSend"
              >
                <i class="fas fa-paper-plane"></i>
                <span>{{ AI_REVIEW_CHAT_COPY.send }}</span>
              </button>
              <button v-else type="button" class="session-stop-btn" @click="session.stop()">
                <i class="fas fa-square"></i>
                <span>{{ AI_REVIEW_CHAT_COPY.stop }}</span>
              </button>
            </div>
          </div>
        </div>

        <!-- 底栏（§5.5 结论落位） -->
        <div class="session-footer">
          <button type="button" class="btn btn-secondary btn-sm" :disabled="session.phase === 'saving'" @click="handleClose">
            {{ AI_REVIEW_RECORD_COPY.later }}
          </button>
          <div class="session-footer-actions">
            <template v-if="session.phase !== 'saved'">
              <button
                type="button"
                class="session-save-btn"
                :disabled="!session.canSave"
                @click="handleSave"
              >
                <i class="fas fa-floppy-disk"></i>
                {{ session.phase === 'saving' ? AI_REVIEW_RECORD_COPY.saving : AI_REVIEW_RECORD_COPY.save }}
              </button>
            </template>
            <template v-else>
              <button type="button" class="session-reject-btn" @click="handleReject">
                <i class="fas fa-times-circle"></i> {{ AI_REVIEW_RECORD_COPY.reject }}
              </button>
              <button type="button" class="session-adopt-btn" @click="handleAdopt">
                <i class="fas fa-clipboard-check"></i> {{ AI_REVIEW_RECORD_COPY.adopt }}
              </button>
            </template>
          </div>
        </div>

        <!-- 供应商管理弹窗 -->
        <ProviderManagerModal v-model:visible="providerManagerOpen" />
      </div>
    </div>
  </Teleport>
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
import '../../assets/styles/layouts/main.css'

import { computed, nextTick, reactive, ref, watch, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useAiChatStore } from '@/store/aiChatStore'
import { useAiReviewSession, type AiReviewSessionResult } from '@/composables/aiReviewSession'
import {
  AI_REVIEW_SESSION_COPY,
  AI_REVIEW_CHAT_COPY,
  AI_REVIEW_RECORD_COPY,
} from '@/domain/constants/aiReviewSession'
import type { ChatMessage } from '@/domain/model/aiChat'
import AiReviewContextCard from './AiReviewContextCard.vue'
import AiReviewVerdictCard from './AiReviewVerdictCard.vue'
import AiReviewRecordCard from './AiReviewRecordCard.vue'
import ModelProviderSwitcher from '@/views/AiChat/components/ModelProviderSwitcher.vue'
import ProviderManagerModal from '@/views/AiChat/components/ProviderManagerModal.vue'

const props = defineProps<{
  visible: boolean
  taskId: number | string
  caseId: string
  caseName?: string
  /** 发起对象结果行（缺省时组件内部经 GET /tasks/{id}/cases/{caseId}/results 拉取真实数据） */
  results?: AiReviewSessionResult[]
}>()

const emit = defineEmits<{
  (e: 'close'): void
  /** 采纳落位成功（父级刷新复核标记/统计） */
  (e: 'adopted'): void
}>()

const router = useRouter()
const chatStore = useAiChatStore()
/** reactive 包装：模板直接访问 session.phase / session.messages / session.canSave（ref 自动解包） */
const session = reactive(useAiReviewSession({
  taskId: Number(props.taskId),
  caseId: props.caseId,
  caseName: props.caseName,
  results: props.results,
  onAdopted: () => emit('adopted'),
}))

const draftText = ref('')
const providerManagerOpen = ref(false)
const scrollRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)

/** 首条 assistant（复核上下文摘要卡） */
const contextMessage = computed(() =>
  session.messages[0]?.from === 'assistant' ? session.messages[0] : null
)
/** 上下文卡之后的用户/assistant 消息流 */
const tailMessages = computed(() => session.messages.slice(contextMessage.value ? 1 : 0))

/** 原评估判定（AI 判定 vs 原评估判定对比行） */
const originalEvaluationStatus = computed(() => {
  const first = session.context?.results[0]
  return first?.evaluationStatus ?? null
})

function currentContent(message: ChatMessage): string {
  return message.versions[message.versions.length - 1]?.content ?? ''
}

function formatTime(ts?: string | null): string {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  return d.toLocaleString('zh-CN', { hour12: false })
}

function scrollToBottom(): void {
  void nextTick(() => {
    const el = scrollRef.value
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  })
}

watch(() => session.messages.length, scrollToBottom)
watch(() => session.isGenerating, (g) => { if (g) scrollToBottom() })

// 打开会话：装配真实上下文 → 首条摘要卡 + 首条用户指令；关闭即释放局部 state
watch(
  () => props.visible,
  (open) => {
    if (open) {
      void session.initialize()
    } else {
      session.reset()
      draftText.value = ''
    }
  },
  { immediate: true },
)

function handleClose(): void {
  if (session.phase === 'saving') return
  emit('close')
}

function handleSend(): void {
  const text = draftText.value.trim()
  if (!text) return
  session.sendFollowUp(text)
  draftText.value = ''
  textareaRef.value?.focus()
}

function sendChip(chip: string): void {
  session.sendFollowUp(chip)
}

function handleSave(): void {
  void session.saveConclusion()
}

async function handleAdopt(): Promise<void> {
  await session.adoptConclusion()
}

function handleReject(): void {
  void session.rejectConclusion()
}

/** 展开到 /ai-chat（§5.2：复核上下文带入主会话继续讨论；URL 契约由主会话页消费） */
function handleExpandToChat(): void {
  void router.push(`/ai-chat?task=${props.taskId}&reviewCase=${encodeURIComponent(props.caseId)}`)
  emit('close')
}

onBeforeUnmount(() => {
  session.reset()
})
</script>

<style scoped>
.ai-review-session-overlay {
  position: fixed;
  inset: 0;
  z-index: 1080;
  background: color-mix(in srgb, var(--foreground) 40%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
}

.ai-review-session-dialog {
  width: min(720px, 94vw);
  max-height: min(72dvh, 680px);
  display: flex;
  flex-direction: column;
  background: var(--background);
  border-radius: var(--radius-card);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

/* ===== 头行 ===== */
.session-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}

.session-title {
  margin: 0;
  flex: 1;
  min-width: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
  display: inline-flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-title-icon {
  color: var(--primary);
}

.session-demo-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--warning-dark, var(--foreground));
  background: var(--warning-light, color-mix(in srgb, var(--warning) 20%, transparent));
  border-radius: var(--radius-pill);
  padding: 2px 9px;
  cursor: help;
}

.session-header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.session-icon-btn {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--muted-foreground);
  font-size: 14px;
  cursor: pointer;
}

.session-icon-btn:hover {
  background: var(--muted);
  color: var(--foreground);
}

/* ===== 副文 ===== */
.session-tip {
  margin: 0;
  padding: 8px 18px 0;
  font-size: 12px;
  color: var(--muted-foreground);
}

/* ===== 会话区 ===== */
.session-conversation {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 18px;
}

.session-message-row {
  display: flex;
  margin-bottom: 8px;
}

.session-message-row.message--user {
  justify-content: flex-end;
}

.session-message-row.message--assistant {
  justify-content: flex-start;
  width: 100%;
}

.session-user-bubble {
  max-width: 85%;
  background: var(--muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  border-bottom-right-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--foreground);
  white-space: pre-wrap;
  word-break: break-word;
}

.session-assistant-doc {
  width: 100%;
  max-width: 78ch;
}

.session-assistant-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--foreground);
  white-space: pre-wrap;
  word-break: break-word;
}

.session-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
  color: var(--muted-foreground);
}

.loading-spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--primary);
  border-radius: var(--radius-full);
  animation: session-spin 0.8s linear infinite;
}

@keyframes session-spin {
  to { transform: rotate(360deg); }
}

.session-error {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid color-mix(in srgb, var(--destructive) 30%, transparent);
  border-radius: var(--radius-control);
  background: color-mix(in srgb, var(--destructive) 8%, transparent);
  color: var(--destructive);
  font-size: 12px;
}

.session-error-text {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--destructive);
}

.session-existing-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: var(--radius-control);
  background: color-mix(in srgb, var(--warning) 12%, transparent);
  color: var(--warning-dark, var(--foreground));
  font-size: 12px;
}

/* ===== 快捷 chips ===== */
.session-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 18px 8px;
}

.session-chip {
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--card);
  color: var(--muted-foreground);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}

.session-chip:hover {
  border-color: var(--primary);
  color: var(--primary);
}

/* ===== 输入区 ===== */
.session-input {
  flex-shrink: 0;
  padding: 8px 18px 10px;
  border-top: 1px solid var(--border);
}

.session-textarea {
  width: 100%;
  min-height: 44px;
  max-height: 120px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--card);
  color: var(--foreground);
  font: inherit;
  font-size: 13px;
  line-height: 1.6;
  resize: none;
  box-sizing: border-box;
}

.session-textarea:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 15%, transparent);
}

.session-textarea:disabled {
  opacity: 0.6;
}

.session-input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
}

.session-input-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.session-send-btn,
.session-stop-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 14px;
  border: none;
  border-radius: var(--radius-control);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.session-send-btn {
  background: var(--primary);
  color: var(--primary-foreground);
}

.session-send-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

.session-send-btn:disabled {
  background: var(--muted);
  color: var(--muted-foreground);
  cursor: not-allowed;
}

.session-stop-btn {
  border: 1px solid color-mix(in srgb, var(--destructive) 30%, transparent);
  background: color-mix(in srgb, var(--destructive) 10%, transparent);
  color: var(--destructive);
}

/* ===== 底栏 ===== */
.session-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 18px;
  border-top: 1px solid var(--border);
}

.session-footer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.session-save-btn,
.session-adopt-btn,
.session-reject-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 0 16px;
  border-radius: var(--radius-control);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.session-save-btn {
  border: none;
  background: var(--primary);
  color: var(--primary-foreground);
}

.session-save-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

.session-save-btn:disabled {
  background: var(--muted);
  color: var(--muted-foreground);
  cursor: not-allowed;
}

.session-adopt-btn {
  border: none;
  background: var(--primary);
  color: var(--primary-foreground);
}

.session-adopt-btn:hover {
  background: var(--primary-hover);
}

.session-reject-btn {
  border: 1px solid var(--border);
  background: var(--muted);
  color: var(--foreground);
}

.session-reject-btn:hover {
  border-color: var(--destructive);
  color: var(--destructive);
}
</style>
