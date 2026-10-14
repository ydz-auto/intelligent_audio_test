<template>
  <div v-if="visible" class="auth-mode-banner" role="alert">
    <div class="auth-mode-banner__body">
      <i class="fas fa-triangle-exclamation auth-mode-banner__icon"></i>
      <div class="auth-mode-banner__text">
        <strong>认证模式不一致</strong>
        <span>
          前端 VITE_AUTH_MODE=<code>{{ frontendMode || '（未注入，按 off 生效）' }}</code>，
          后端 AUTH_MODE=<code>{{ backendMode || '（未报告）' }}</code>。
        </span>
        <span v-if="!backendModeKnown">后端取值不在合法集合（off | dev | prod）内，请检查后端 AUTH_MODE 注入。</span>
        <span>
          修正指引：使前端注入与后端一致——本地 dev server 以进程 env 注入
          （<code>VITE_AUTH_MODE=&lt;off|dev|prod&gt; npm run dev</code>，注意
          tracked 的 <code>.env.development</code> 优先级高于
          <code>.env.local</code>，只改 .env.local 会被静默覆盖且需重启进程）；
          生产构建用 <code>VITE_AUTH_MODE=&lt;off|dev|prod&gt;</code> 或 docker
          <code>--build-arg VITE_AUTH_MODE=...</code> 重新构建。详见 docs/oauth.md。
        </span>
      </div>
    </div>
    <button type="button" class="auth-mode-banner__close" title="关闭提示" @click="visible = false">
      <i class="fas fa-xmark"></i>
    </button>
  </div>
</template>

<script setup lang="ts">
/**
 * 认证模式错位提示条（INT-180 启动自检）
 *
 * 仅提示，不阻塞应用启动与登录流程；两侧当前值 + 修正指引，
 * 可手动关闭。由 infrastructure/selfCheck/authModeSelfCheck 在检测到
 * 错位时动态挂载。
 */
import { ref } from 'vue'

defineProps<{
  frontendMode: string
  backendMode: string
  backendModeKnown: boolean
}>()

const visible = ref(true)
</script>

<style scoped>
.auth-mode-banner {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 10000;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 16px;
  background: #fff7e6;
  border-bottom: 1px solid #ffd591;
  color: #874d00;
  font-size: 13px;
  line-height: 1.6;
}

.auth-mode-banner__body {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.auth-mode-banner__icon {
  margin-top: 3px;
  color: #faad14;
}

.auth-mode-banner__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  word-break: break-all;
}

.auth-mode-banner__text code {
  padding: 0 4px;
  border-radius: 3px;
  background: #fff1d6;
  border: 1px solid #ffd591;
  font-size: 12px;
}

.auth-mode-banner__close {
  border: none;
  background: transparent;
  color: #874d00;
  cursor: pointer;
  padding: 4px 6px;
  font-size: 14px;
}

.auth-mode-banner__close:hover {
  opacity: 0.7;
}
</style>
