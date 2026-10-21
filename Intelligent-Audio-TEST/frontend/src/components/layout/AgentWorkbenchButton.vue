<template>
  <button
    class="agent-button"
    :class="{ 'agent-button--active': workbench.open }"
    data-layout-btn
    title="灵犀Agent"
    :aria-label="'打开全局 Agent 工作台'"
    @click="handleClick"
  >
    <span class="agent-button__word">
      <i class="fas fa-wand-magic-sparkles"></i>
      <span class="agent-button__label">灵犀Agent</span>
      <span class="sr-only">灵犀Agent</span>
    </span>
  </button>
</template>

<script setup lang="ts">
import { useAgentWorkbenchStore } from '@/store/agentWorkbenchStore'

const workbench = useAgentWorkbenchStore()

/**
 * 灵犀Agent 魔法按钮（右上角首位，§2.4 ①）：点击唤起/关闭全局 Agent 工作台浮窗
 * （照 React INT-415 agent-workbench-button.tsx 实测行为——toggle 浮窗而非跳转整页；
 * 浮窗「展开整页」钮承担 /ai-chat 跳转，§3.1B）。
 */
function handleClick(): void {
  if (!workbench.open) workbench.setOpen(true)
  else workbench.toggle()
}
</script>

<style scoped>
/* 照 React `ai-discount-core` 逐层移植（frontend-react/src/styles/index.css:822-944）：
   静态渐变底 + 流光扫层 + 星尘粒子流；`prefers-reduced-motion` 关停动画。
   渐变/阴影色值收敛为 tokens.css `--ai-magic-*` 令牌，不在此硬编码。
   按钮带 `data-layout-btn` 退出 legacy button.css catch-all（见该文件 opt-out 注释）。 */
.agent-button {
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
.agent-button:hover {
  filter: brightness(1.1);
}
.agent-button:active {
  transform: translateY(1px);
}
.agent-button:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}
/* 浮窗打开态：主色描边（照 React `open && 'ring-2 ring-primary/40'`） */
.agent-button--active {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 40%, transparent);
}
/* 文案层：收进内层 flex 容器避免 CJK 换行/失垂直居中（照 newAPI LocalSetupGuide 结构） */
.agent-button__word {
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
.agent-button::before,
.agent-button::after {
  content: '';
  /* legacy button.css `button::before { display:none }` 会把流光层藏掉，显式复位 */
  display: block;
  position: absolute;
  pointer-events: none;
}
/* 流光层（照 React [data-slot='button']::before：色带 200% 循环横移） */
.agent-button::before {
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
  animation: agent-button-color-flow 2.8s linear infinite;
}
/* 星尘粒子流（照 React ::after：白点径向渐变 + 横移 + 明暗交替） */
.agent-button::after {
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
    agent-button-star-travel 4s linear infinite,
    agent-button-stardust 7s ease-in-out infinite alternate;
}
@keyframes agent-button-color-flow {
  from {
    background-position: 0% 50%;
  }
  to {
    background-position: 200% 50%;
  }
}
@keyframes agent-button-star-travel {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(-50%);
  }
}
@keyframes agent-button-stardust {
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
  .agent-button,
  .agent-button::before,
  .agent-button::after {
    animation: none;
  }
}
.agent-button__label {
  display: none;
}
@media (min-width: 1280px) {
  .agent-button__label {
    display: inline;
  }
}
/* 无障碍：移动端隐藏可见文案时读屏仍可读（照 React `sr-only sm:hidden`） */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
