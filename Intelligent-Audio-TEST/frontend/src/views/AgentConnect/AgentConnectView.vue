<template>
  <div class="agent-connect-page">
    <!-- 页面标题 -->
    <section class="page-header">
      <div class="header-left">
        <h2 class="page-title">
          <i class="fas fa-plug"></i>
          联接你的 agent
        </h2>
        <p class="page-description">用 Access Token 与智能音频测试 skill / MCP，让外部 agent 调用平台能力</p>
      </div>
    </section>

    <div class="agent-connect-body">
      <!-- ① 使用说明 -->
      <section class="agent-card">
        <div class="agent-card-header">
          <span class="card-icon info"><i class="fas fa-book-open"></i></span>
          <div class="card-title-group">
            <h3 class="card-title">使用说明</h3>
            <p class="card-desc">三步让外部 agent（Claude Code / Codex 等）接入平台能力</p>
          </div>
        </div>
        <ol class="steps">
          <li class="step">
            <span class="step-index">1</span>
            <div class="step-copy">
              <h4 class="step-title">创建 Access Token</h4>
              <p class="step-desc">进入「个人配置页 → Access Token」创建访问令牌（仅创建时明文显示一次），可配置权限（scopes）与有效时间。</p>
              <button type="button" class="btn btn-outline btn-sm" @click="goProfile">
                <i class="fas fa-user-cog"></i> 前往个人配置页
              </button>
            </div>
          </li>
          <li class="step">
            <span class="step-index">2</span>
            <div class="step-copy">
              <h4 class="step-title">安装 skill</h4>
              <p class="step-desc">点击下方「下载 skill」获取 skill 包（SKILL.md + MCP 配置模板），解压后放入你的 agent 工作区。</p>
            </div>
          </li>
          <li class="step">
            <span class="step-index">3</span>
            <div class="step-copy">
              <h4 class="step-title">配置 MCP</h4>
              <p class="step-desc">在 mcp.json 中填入 Access Token，导入 MCP 客户端即可调用平台能力（skill 与 MCP 使用同一 Access Token）。</p>
            </div>
          </li>
        </ol>
      </section>

      <!-- ② skill 服务地址配置 -->
      <section class="agent-card">
        <div class="agent-card-header">
          <span class="card-icon neutral"><i class="fas fa-globe"></i></span>
          <div class="card-title-group">
            <h3 class="card-title">skill 服务地址</h3>
            <p class="card-desc">下载的 skill 包内 MCP 配置模板将预填此地址（默认取浏览器地址栏，可改）</p>
          </div>
        </div>
        <div class="url-row">
          <input
            v-model.trim="serviceUrl"
            class="url-input"
            type="text"
            placeholder="https://your-server.example.com"
            aria-label="skill 服务地址"
          />
          <button type="button" class="btn btn-primary" :disabled="saving" @click="handleSaveUrl">
            <i class="fas" :class="saving ? 'fa-spinner fa-spin' : 'fa-save'"></i>
            {{ saving ? '保存中…' : '保存配置' }}
          </button>
        </div>
        <p class="field-hint">支持 IP 或 http(s) 链接；多网络环境请改成外部 agent 可访问的地址。</p>
      </section>

      <!-- ③ Access Token 指引 -->
      <section class="agent-card">
        <div class="agent-card-header">
          <span class="card-icon info"><i class="fas fa-key"></i></span>
          <div class="card-title-group">
            <h3 class="card-title">Access Token</h3>
            <p class="card-desc">skill / MCP 调用平台能力时的鉴权凭证</p>
          </div>
        </div>
        <p class="token-copy">Access Token 用于 skill 与 MCP 调用平台能力时的鉴权，可配置权限与有效时间；创建、复制与管理统一在个人配置页完成。</p>
        <button type="button" class="btn btn-outline" @click="goProfile">
          <i class="fas fa-user-cog"></i> 前往个人配置页管理 Access Token
        </button>
      </section>

      <!-- ④ 下载 skill -->
      <section class="agent-card">
        <div class="agent-card-header">
          <span class="card-icon magic"><i class="fas fa-wand-magic-sparkles"></i></span>
          <div class="card-title-group">
            <h3 class="card-title">下载 skill</h3>
            <p class="card-desc">获取 SKILL.md 与 MCP 配置模板 zip 包</p>
          </div>
        </div>
        <div class="download-row">
          <button
            type="button"
            class="skill-download-button"
            data-layout-btn
            :disabled="downloading"
            @click="handleDownload"
          >
            <span class="skill-download-button__word">
              <i class="fas" :class="downloading ? 'fa-spinner fa-spin' : 'fa-wand-magic-sparkles'"></i>
              {{ downloading ? '下载中…' : '下载 skill' }}
            </span>
          </button>
          <span class="download-note">服务端 skill 下载能力上线前为契约示例包，上线后自动切换为真实 skill 包。</span>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/card.css'
import '../../assets/styles/layouts/main.css'

import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useNotification } from '../../composables/modal/useNotification'
import { useAgentConnect } from '../../composables/agentConnect/useAgentConnect'
import { downloadBlob } from '../../utils/utils'
import { toUserErrorMessage } from '../../utils/errorMessage'

/**
 * 「联接你的 agent」入口页（INT-1154）
 * 内容：使用说明（创建 Access Token / 安装 skill / 配置 MCP）+ skill 服务地址配置
 * （默认取浏览器地址栏、可改、保存后预填进下载包）+ Access Token 指引（跳 /profile）
 * + 炫彩「下载 skill」按钮（--ai-magic 令牌，不硬编码）。
 * 下载经基础设施层 agentSkillApi（// 待接线 契约桩，后端 INT-1150 合栈后切真实请求）。
 */
const router = useRouter()
const notification = useNotification()
const { serviceUrl, saveServiceUrl, downloadSkill } = useAgentConnect()

const saving = ref(false)
const downloading = ref(false)

function goProfile() {
  router.push('/profile')
}

async function handleSaveUrl() {
  if (!serviceUrl.value) {
    notification.warning('请填写 skill 服务地址')
    return
  }
  saving.value = true
  try {
    saveServiceUrl(serviceUrl.value)
    notification.success('skill 服务地址已保存')
  } finally {
    saving.value = false
  }
}

async function handleDownload() {
  if (downloading.value) return
  downloading.value = true
  try {
    const blob = await downloadSkill()
    downloadBlob(blob, 'intelligent-audio-test-skill.zip')
    notification.success('skill 包已开始下载')
  } catch (err) {
    notification.error(toUserErrorMessage(err, 'skill 包下载失败'))
  } finally {
    downloading.value = false
  }
}
</script>

<style src="./AgentConnectView.css"></style>
