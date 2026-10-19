<template>
  <button
    type="button"
    class="agent-magic-button"
    :class="{ 'agent-magic-button--active': workbench.open }"
    :aria-label="'打开全局 Agent 工作台'"
    @click="workbench.toggle"
  >
    <span class="agent-magic-word">
      <i class="fas fa-wand-magic-sparkles"></i>
      <span class="agent-magic-text">灵犀Agent</span>
    </span>
  </button>
</template>

<script setup lang="ts">
import { useAgentWorkbenchStore } from '@/store/agentWorkbenchStore'

const workbench = useAgentWorkbenchStore()
</script>

<style scoped>
/* 炫彩魔法按钮（照 xagents_new_api ai-discount-core/ai-discount-word 实测 CSS，
 * 08_AI对话页 §3.1B；固定渐变硬编码，非品牌色 token——对齐「复用不发明」口径） */
.agent-magic-button {
  position: relative;
  isolation: isolate;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  padding: 0 16px;
  border: 0;
  border-radius: var(--radius-full);
  color: #ffffff;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  background: linear-gradient(115deg, #4f7cff, #9145ee 55%, #cd4bdb);
  transition: filter 0.2s;
}

.agent-magic-button:hover {
  filter: brightness(1.1);
}

.agent-magic-button--active {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 40%, transparent);
}

.agent-magic-word {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.agent-magic-text {
  white-space: nowrap;
}

/* 光斑旋转动画（prefers-reduced-motion 关停） */
.agent-magic-button::before {
  content: '';
  position: absolute;
  inset: -2px;
  z-index: -1;
  border-radius: inherit;
  background: conic-gradient(
    from 0deg,
    transparent 0%,
    rgba(255, 255, 255, 0.35) 20%,
    transparent 40%
  );
  animation: agent-ultra-gradient-flow 2.4s linear infinite;
}

@keyframes agent-ultra-gradient-flow {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .agent-magic-button::before {
    animation: none;
  }
}
</style>
