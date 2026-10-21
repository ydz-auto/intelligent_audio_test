<template>
  <button
    class="agent-connect-button"
    :class="{ 'agent-connect-button--compact': compact }"
    data-layout-btn
    title="连接你的 agent"
    :aria-label="compact ? '打开连接你的 agent' : '连接你的 agent'"
    @click="goAgentConnect"
  >
    <span class="agent-connect-button__word">
      <i class="fas fa-plug"></i>
      <span class="agent-connect-button__label">连接你的 agent</span>
    </span>
  </button>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

/**
 * 炫彩「连接你的 agent」入口按钮（INT-1193 返工落位）。
 * 落点：灵犀Agent 页 /ai-chat 顶部条右上角（ai-chat-header-right）+ Agent 工作台浮窗头行
 * 右上角（awb-header，最小化/展开/关闭前）；顶栏 TopBarRight 不再保留该入口
 * （负责人 2026-10-22 裁定，按 React INT-1153 二轮返工同步）。
 * 形态照 AgentWorkbenchButton（灵犀Agent）模式逐层移植：静态渐变底 + 流光扫层 + 星尘粒子流；
 * `prefers-reduced-motion` 关停动画；`compact` 用于浮窗头行（空间紧凑，按头行高度适配）。
 * 渐变/阴影色值收敛为 tokens `--ai-magic-*` 令牌，不在此硬编码。
 * 按钮带 `data-layout-btn` 退出 legacy button.css catch-all（见该文件 opt-out 注释）。
 */
defineProps<{
  /** 浮窗头行紧凑形态（height 28px / 内边距 10px / 12px 字重 600） */
  compact?: boolean
}>()

const router = useRouter()

function goAgentConnect() {
  router.push({ name: 'agentConnect' })
}
</script>

<style scoped>
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
/* 默认隐藏文案（窄屏仅图标）；≥1280px 展开 */
.agent-connect-button__label {
  display: none;
}
@media (min-width: 1280px) {
  .agent-connect-button__label {
    display: inline;
  }
}
/* 浮窗头行 compact：按 awb-header 头行高度适配（React compact h-7 先例；
   height 28px = --control-height 32 - --spacing-xs 4，全 token 推演不硬编码） */
.agent-connect-button--compact {
  height: calc(var(--control-height) - var(--spacing-xs));
  min-height: calc(var(--control-height) - var(--spacing-xs));
  padding: 0 var(--spacing-10);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
}
.agent-connect-button--compact .agent-connect-button__word {
  gap: var(--spacing-6);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
}
/* 浮窗头行 compact：文案始终展开（浮窗宽 < 1280px，不受默认窄屏隐藏规则影响） */
.agent-connect-button--compact .agent-connect-button__label {
  display: inline;
}
</style>
