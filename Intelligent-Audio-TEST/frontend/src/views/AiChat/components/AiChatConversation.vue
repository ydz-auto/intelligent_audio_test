<template>
  <div class="ai-chat-conversation" ref="scrollRef">
    <!-- 空态：全能力入口/分组 -->
    <AiChatEmptyState v-if="messages.length === 0" @fill-prompt="emit('fill-prompt', $event)" />

    <!-- 消息流 -->
    <div v-else class="message-list">
      <AiChatMessageItem
        v-for="(message, idx) in renderedMessages"
        :key="message.key"
        :message="message"
        :is-generating="isGenerating"
        :is-editing="editingKey === message.key"
        :is-source-visible="sourceVisibleKeys.has(message.key)"
        :always-show-actions="idx === renderedMessages.length - 1 && message.from === 'assistant'"
        @regenerate="emit('regenerate', $event)"
        @edit="emit('edit', $event)"
        @delete="emit('delete', $event)"
        @save-edit="(content, resend) => emit('save-edit', content, resend)"
        @cancel-edit="emit('cancel-edit')"
        @toggle-source="handleToggleSource"
        @view-document="emit('view-document')"
      />
    </div>

    <!-- 回到底部悬浮钮 -->
    <button
      v-if="showScrollButton"
      type="button"
      class="scroll-bottom-btn"
      title="回到底部"
      @click="scrollToBottom(true)"
    >
      <i class="fas fa-arrow-down"></i>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted } from 'vue'
import type { ChatMessage } from '@/domain/model/aiChat'
import { MAX_RENDERED_HISTORY_MESSAGES } from '@/domain/constants/aiChat'
import AiChatEmptyState from './AiChatEmptyState.vue'
import AiChatMessageItem from './AiChatMessageItem.vue'

const props = defineProps<{
  messages: ChatMessage[]
  isGenerating: boolean
  editingKey: string | null
}>()

const emit = defineEmits<{
  (e: 'fill-prompt', prompt: string): void
  (e: 'regenerate', key: string): void
  (e: 'edit', key: string): void
  (e: 'delete', key: string): void
  (e: 'save-edit', content: string, resend: boolean): void
  (e: 'cancel-edit'): void
  (e: 'view-document'): void
}>()

const scrollRef = ref<HTMLElement | null>(null)
const showScrollButton = ref(false)
/** 源码视图展开的消息 key 集合（§3.4：显示源码/显示预览切换，per-message） */
const sourceVisibleKeys = ref<Set<string>>(new Set())
let isNearBottom = true

/** 历史渲染上限 24 条截断（§3.4 MAX_RENDERED_HISTORY_MESSAGES 照搬） */
const renderedMessages = computed(() => {
  if (props.messages.length <= MAX_RENDERED_HISTORY_MESSAGES) return props.messages
  return props.messages.slice(-MAX_RENDERED_HISTORY_MESSAGES)
})

/** 显示源码/显示预览切换（§3.4 per-message 视图态，照 React sourceMessageKeys 语义） */
function handleToggleSource(key: string): void {
  const next = new Set(sourceVisibleKeys.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  sourceVisibleKeys.value = next
}

function scrollToBottom(smooth = true): void {
  const el = scrollRef.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
}

function handleScroll(): void {
  const el = scrollRef.value
  if (!el) return
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  isNearBottom = distance < 80
  showScrollButton.value = distance > 120
}

// 消息变化（发送/流式/编辑）自动粘底
watch(
  () => props.messages,
  () => {
    if (isNearBottom) {
      void nextTick(() => scrollToBottom(false))
    }
  },
  { deep: false }
)

watch(
  () => props.isGenerating,
  () => {
    if (props.isGenerating) {
      void nextTick(() => scrollToBottom(true))
    }
  }
)

onMounted(() => {
  void nextTick(() => scrollToBottom(false))
})
</script>

<style scoped>
.ai-chat-conversation {
  position: relative;
  height: 100%;
  overflow-y: auto;
  padding: 16px;
  box-sizing: border-box;
}

.message-list {
  max-width: 860px;
  margin: 0 auto;
  padding-bottom: 8px;
}

.scroll-bottom-btn {
  position: absolute;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  background: var(--card);
  color: var(--muted-foreground);
  font-size: 13px;
  cursor: pointer;
  box-shadow: var(--shadow-md, 0 2px 8px color-mix(in srgb, var(--color-black) 12%, transparent));
  transition: color 0.2s, border-color 0.2s;
}

.scroll-bottom-btn:hover {
  color: var(--primary);
  border-color: var(--primary);
}
</style>
