<template>
  <div class="agent-connect">
    <div class="page-header">
      <h2 class="page-title">
        <i class="fas fa-robot"></i>
        连接你的 agent
      </h2>
      <p class="page-description">
        下载智能音频测试 skill，让外部 agent（Claude Code / Codex 等）经 skill / MCP 调用本系统能力
      </p>
    </div>

    <p v-if="error" class="error-msg">{{ error }}</p>

    <div class="section-card">
      <h3>使用说明</h3>
      <ol class="guide-list">
        <li>
          在「账号设置 → Access Token」创建访问令牌（可配置权限 scopes 与有效时间
          expires_at），复制明文并妥善保存——明文只在创建时显示一次。
        </li>
        <li>在下方确认本系统的服务地址（默认取当前浏览器地址栏，可改为外部 agent 可达的 IP / http(s) 地址）。</li>
        <li>点击「下载 skill」下载 zip 包（SKILL.md + MCP 配置模板），按包内说明安装到你的 agent。</li>
        <li>调用时以 <code>Authorization: Bearer &lt;你的 Access Token&gt;</code> 经 skill / MCP 访问平台能力。</li>
      </ol>
    </div>

    <div class="section-card">
      <h3>skill 服务地址配置</h3>
      <p class="section-hint">
        该地址将写入 skill 内 URL 路径（base_url），外部 agent 用它在你的网络环境中访问本系统。默认取当前浏览器地址栏，多网络环境可修改。
      </p>
      <div class="url-row">
        <input
          v-model="baseUrl"
          type="text"
          class="url-input"
          placeholder="http(s)://ip:port"
          @keyup.enter="handleDownload"
        />
        <button
          type="button"
          class="btn-magic"
          :disabled="downloading"
          @click="handleDownload"
        >
          <i class="fas fa-download"></i>
          <span v-if="downloading">下载中…</span>
          <span v-else>下载 skill</span>
        </button>
      </div>
      <p v-if="downloadError" class="error-msg">{{ downloadError }}</p>
      <p v-if="downloaded" class="success-msg">
        已下载 {{ fileName }}，请按包内说明安装 skill / 配置 MCP。
      </p>
    </div>

    <div class="section-card">
      <h3>Access Token 指引</h3>
      <p class="section-hint">
        Access Token 用于 skill 与 MCP 调用本系统能力时鉴权；创建 / 复制 / 管理（权限、有效时间、启停、删除）均在个人配置页完成。
      </p>
      <button type="button" class="btn-secondary" @click="goAccountSettings">
        <i class="fas fa-key"></i>
        前往个人配置页管理 Access Token
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { agentSkillPort, SKILL_DOWNLOAD_FILENAME } from '../../composables/agent/agentSkillPort'
import { downloadBlob } from '../../utils/utils'

const router = useRouter()

/** skill 服务地址：默认取浏览器地址栏（origin），可改为外部 agent 可达地址 */
const baseUrl = ref(window.location.origin)

const downloading = ref(false)
const downloaded = ref(false)
const fileName = ref(SKILL_DOWNLOAD_FILENAME)
const downloadError = ref('')
const error = ref('')

function goAccountSettings() {
  router.push({ path: '/AccountSettings', query: { tab: 'access-tokens' } })
}

async function handleDownload() {
  const url = baseUrl.value.trim()
  if (!url) {
    downloadError.value = '请先填写 skill 服务地址'
    return
  }
  downloading.value = true
  downloadError.value = ''
  downloaded.value = false
  try {
    const blob = await agentSkillPort.downloadSkill(url)
    downloadBlob(blob, fileName.value)
    downloaded.value = true
  } catch (e: any) {
    downloadError.value = e?.detail || e?.message || '下载 skill 失败'
  } finally {
    downloading.value = false
  }
}

onMounted(() => {
  // 重置下载提示（重新进入页面不残留上次成功态）
  downloaded.value = false
  downloadError.value = ''
})
</script>

<style scoped>
.agent-connect {
  padding: 24px;
  max-width: 900px;
  margin: 0 auto;
}
.page-header {
  margin-bottom: 20px;
}
.page-title {
  font-size: 20px;
  color: var(--primary-color, var(--foreground));
}
.page-title i {
  margin-right: 8px;
}
.page-description {
  margin-top: 4px;
  font-size: 13px;
  color: var(--color-gray-500);
}
.section-card {
  background: var(--card, #ffffff);
  border: 1px solid var(--color-gray-300);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}
.section-card h3 {
  margin: 0 0 12px;
  font-size: 16px;
}
.section-hint {
  font-size: 12px;
  color: var(--color-gray-400);
  margin: -6px 0 12px;
  line-height: 1.6;
}
.guide-list {
  margin: 0;
  padding-left: 20px;
  font-size: 14px;
  line-height: 2;
  color: var(--foreground, #333);
}
.guide-list code {
  background: var(--muted, #f5f5f5);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 12px;
}
.url-row {
  display: flex;
  gap: 10px;
  align-items: center;
}
.url-input {
  flex: 1;
  min-width: 0;
  padding: 8px 12px;
  font-size: 14px;
  border: 1px solid var(--color-gray-300);
  border-radius: 6px;
  background: var(--background, #fff);
  color: var(--foreground, #333);
}
.url-input:focus {
  outline: none;
  border-color: var(--ring, #ff6a00);
}
/* 炫彩「下载 skill」按钮（INT-1140）：引用 tokens.css 彩虹渐变令牌，不硬编码。
   已从全局 button.css 无背景规则排除（:not(.btn-magic)），此处补 cursor 指针。 */
.btn-magic {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 18px;
  font-size: 14px;
  font-weight: 600;
  color: var(--magic-foreground, #fff);
  border: none;
  border-radius: 9999px;
  background: var(--magic-gradient);
  cursor: pointer;
  transition: filter 0.2s, transform 0.05s;
}
.btn-magic:hover:not(:disabled) {
  background: var(--magic-gradient);
  filter: brightness(1.1);
}
.btn-magic:active:not(:disabled) {
  transform: translateY(1px);
}
.btn-magic:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
.btn-secondary {
  padding: 8px 16px;
  background: var(--background, #fff);
  border: 1px solid var(--secondary, #1976d2);
  color: var(--secondary, #1976d2);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}
.btn-secondary:hover {
  background: var(--secondary-light, #e3f2fd);
}
.error-msg {
  color: var(--destructive, #f5222d);
  font-size: 14px;
  margin-bottom: 10px;
}
.success-msg {
  color: var(--success, #52c41a);
  font-size: 14px;
  margin-top: 10px;
}
</style>
