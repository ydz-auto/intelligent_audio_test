<template>
  <button class="agent-connect-button" data-layout-btn title="联接你的 agent" @click="goAgentConnect">
    <span class="agent-connect-button__word">
      <i class="fas fa-plug"></i>
      <span class="agent-connect-button__label">联接你的 agent</span>
    </span>
  </button>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

function goAgentConnect() {
  router.push({ name: 'agentConnect' })
}
</script>

<style scoped>
/* 「联接你的 agent」炫彩入口按钮（INT-1154）。
   照 AgentWorkbenchButton（灵犀Agent）模式逐层移植：静态渐变底 + 流光扫层 + 星尘粒子流；
   `prefers-reduced-motion` 关停动画。
   渐变/阴影色值收敛为 tokens `--ai-magic-*` 令牌，不在此硬编码。
   按钮带 `data-layout-btn` 退出 legacy button.css catch-all（见该文件 opt-out 注释）。 */
.agent-connect-button {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: var(--control-height);
  min-height: var(--control-height);
  padding: 0 14px;
  border: 0;
  border-radius: var(--radius-full);
  background: linear-gradient(
    115deg,
    var(--ai-magic-blue),
    var(--ai-magic-violet) 55%,
    var(--ai-magic-pink)
  );
  color: var(--color-white);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition:
    filter var(--transition-fast),
    transform var(--transition-fast);
  white-space: nowrap;
}
.agent-connect-button:hover {
  filter: brightness(1.1);
}
.agent-connect-button:active {
  transform: translateY(1px);
}
.agent-connect-button:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}
/* 文案层：收进内层 flex 容器避免 CJK 换行/失垂直居中（照 AgentWorkbenchButton 结构） */
.agent-connect-button__word {
  position: relative;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transform: translateZ(0);
  color: var(--color-white);
  font-size: 13px;
  font-weight: 700;
  text-shadow: var(--ai-magic-text-shadow);
}
.agent-connect-button::before,
.agent-connect-button::after {
  content: '';
  /* legacy button.css `button::before { display:none }` 会把流光层藏掉，显式复位 */
  display: block;
  position: absolute;
  pointer-events: none;
}
/* 流光层（色带 200% 循环横移） */
.agent-connect-button::before {
  inset: 0;
  z-index: -2;
  background: linear-gradient(
    110deg,
    var(--ai-magic-blue),
    var(--ai-magic-indigo) 25%,
    var(--ai-magic-purple) 50%,
    var(--ai-magic-fuchsia) 75%,
    var(--ai-magic-blue)
  );
  background-size: 200% 100%;
  animation: agent-connect-color-flow 2.8s linear infinite;
}
/* 星尘粒子流（白点径向渐变 + 横移 + 明暗交替） */
.agent-connect-button::after {
  inset: 0 auto 0 0;
  width: 200%;
  z-index: -1;
  background-image:
    radial-gradient(circle at 5% 28%, var(--color-white) 0 0.7px, transparent 1.3px),
    radial-gradient(circle at 12% 68%, var(--color-white) 0 0.6px, transparent 1.2px),
    radial-gradient(circle at 22% 18%, var(--color-white) 0 0.6px, transparent 1.3px),
    radial-gradient(circle at 30% 77%, var(--color-white) 0 0.8px, transparent 1.6px),
    radial-gradient(circle at 42% 33%, var(--color-white) 0 0.6px, transparent 1.2px),
    radial-gradient(circle at 51% 83%, var(--color-white) 0 0.6px, transparent 1.3px),
    radial-gradient(circle at 60% 20%, var(--color-white) 0 0.7px, transparent 1.3px),
    radial-gradient(circle at 73% 65%, var(--color-white) 0 0.9px, transparent 1.8px),
    radial-gradient(circle at 84% 30%, var(--color-white) 0 0.6px, transparent 1.3px),
    radial-gradient(circle at 94% 77%, var(--color-white) 0 0.6px, transparent 1.2px);
  background-size: 50% 100%;
  opacity: 0.65;
  animation:
    agent-connect-star-travel 4s linear infinite,
    agent-connect-stardust 7s ease-in-out infinite alternate;
}
@keyframes agent-connect-color-flow {
  from {
    background-position: 0% 50%;
  }
  to {
    background-position: 200% 50%;
  }
}
@keyframes agent-connect-star-travel {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(-50%);
  }
}
@keyframes agent-connect-stardust {
  0% {
    opacity: 0.45;
  }
  45% {
    opacity: 0.8;
  }
  100% {
    opacity: 0.6;
  }
}
@media (prefers-reduced-motion: reduce) {
  .agent-connect-button,
  .agent-connect-button::before,
  .agent-connect-button::after {
    animation: none;
  }
}
.agent-connect-button__label {
  display: none;
}
@media (min-width: 1280px) {
  .agent-connect-button__label {
    display: inline;
  }
}
</style>
