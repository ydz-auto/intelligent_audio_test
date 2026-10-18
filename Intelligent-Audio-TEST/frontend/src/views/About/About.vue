<template>
  <div class="about-page">
    <div class="about-container">
      <!-- 平台介绍（默认中文正文，INT-745 A07） -->
      <article class="about-content">
        <h1 class="about-h1">关于智能语音测试平台</h1>
        <p class="about-lead">
          智能语音测试平台为智能语音产品提供一站式测试能力：端到端测试、API 测试、用例管理、
          设备管理、音频导入与报告对比，覆盖测试执行、质量评估与报告分析全流程。
        </p>

        <h2 class="about-h2">平台能力</h2>
        <ul class="about-list">
          <li>
            <router-link to="/E2ETest">端到端测试</router-link> 与
            <router-link to="/APITest">API 测试</router-link>：五步向导完成测试准备与执行，实时查看进度与日志。
          </li>
          <li>
            <router-link to="/TestCaseManager">用例管理</router-link>：分组、标签与参考参数组织测试用例，支持导入导出。
          </li>
          <li>
            <router-link to="/Device">设备与音频</router-link>（<router-link to="/AudioImport">音频管理</router-link>）：管理被测设备、播放设备与测试音频。
          </li>
          <li>
            <router-link to="/history-reports">报告生成与对比</router-link>：生成测试报告、对比历史报告并下载日志。
          </li>
          <li>
            <router-link to="/Evaluation">评估维度</router-link> 与
            <router-link to="/SPLMapping">SPL 映射</router-link>：配置评估指标与声压级映射。
          </li>
        </ul>

        <h2 class="about-h2">版本与服务状态</h2>
        <p class="about-lead">
          当前平台版本以服务状态卡为准（V9.7.31 起）。服务状态来自平台健康检查接口，反映网关可达性。
        </p>

        <h2 class="about-h2">文档链接</h2>
        <p class="about-lead">
          首次使用与功能操作说明见<router-link to="/user-guide">使用手册</router-link>；
          接口认证、示例与错误码见<router-link to="/user-guide-api">API 手册</router-link>。
          角色与权限说明见平台文档（<code>docs/RBAC权限划分.md</code>，仓库内文档）。
        </p>

        <h2 class="about-h2">联系我们</h2>
        <p class="about-lead">
          使用或接入中遇到问题，请联系平台管理员；反馈时请附上功能模块、操作步骤、发生时间与错误提示，并隐藏账号等个人敏感信息。
        </p>

        <h2 class="about-h2">版权声明</h2>
        <p class="about-lead">© {{ year }} 智能语音测试平台。保留所有权利。</p>
      </article>

      <!-- 版本与服务状态卡（GET /health + GET /auth/mode） -->
      <section class="about-card">
        <div class="about-card-header">
          <h3 class="about-card-title">版本与服务状态</h3>
          <button
            type="button"
            class="refresh-btn"
            :class="{ loading: loading }"
            title="刷新服务状态"
            :aria-label="loading ? '正在检测服务状态' : '刷新服务状态'"
            @click="loadHealth"
          >
            <i class="fas fa-sync-alt" :class="{ spinning: loading }"></i>
          </button>
        </div>
        <div class="status-rows">
          <div class="status-row">
            <span class="status-label">平台版本</span>
            <span class="status-value">
              <span class="status-version">{{ health ? health.version : '—' }}</span>
              <span class="status-badge" :class="badgeClass(health ? 'ok' : 'failed')">{{ health ? '正常' : '检测中' }}</span>
            </span>
          </div>
          <div class="status-row">
            <span class="status-label">API 网关</span>
            <span class="status-value">
              <span class="status-version">{{ health ? health.service : '—' }}</span>
              <span class="status-badge" :class="badgeClass(health?.status)">{{ badgeText(health?.status) }}</span>
            </span>
          </div>
          <div class="status-row">
            <span class="status-label">数据库</span>
            <span class="status-value status-db">{{ health ? health.database : '—' }}</span>
          </div>
          <div class="status-row">
            <span class="status-label">认证模式</span>
            <span class="status-value">
              <span class="status-version">{{ authMode || '—' }}</span>
            </span>
          </div>
        </div>
        <p v-if="error" class="status-error">
          服务状态检测失败，请稍后重试或联系管理员。
        </p>
        <p class="status-note">服务状态来自平台健康检查接口，反映网关可达性。</p>
      </section>

      <!-- 文档链接卡组 -->
      <section class="about-card">
        <h3 class="about-card-title">文档链接</h3>
        <div class="doc-links">
          <router-link to="/user-guide" class="doc-link">
            <i class="fas fa-book doc-link-icon"></i>
            <span class="doc-link-text">
              <span class="doc-link-title">使用手册</span>
              <span class="doc-link-desc">首次使用与功能操作指引</span>
            </span>
            <i class="fas fa-arrow-right doc-link-arrow"></i>
          </router-link>
          <router-link to="/user-guide-api" class="doc-link">
            <i class="fas fa-code doc-link-icon"></i>
            <span class="doc-link-text">
              <span class="doc-link-title">API 手册</span>
              <span class="doc-link-desc">接口认证、示例与错误码</span>
            </span>
            <i class="fas fa-arrow-right doc-link-arrow"></i>
          </router-link>
          <router-link to="/history-reports" class="doc-link">
            <i class="fas fa-file-alt doc-link-icon"></i>
            <span class="doc-link-text">
              <span class="doc-link-title">报告中心</span>
              <span class="doc-link-desc">查看测试报告与历史报告</span>
            </span>
            <i class="fas fa-arrow-right doc-link-arrow"></i>
          </router-link>
          <div class="doc-link doc-link-static">
            <i class="fas fa-shield-alt doc-link-icon"></i>
            <span class="doc-link-text">
              <span class="doc-link-title">权限说明</span>
              <span class="doc-link-desc">角色与权限说明（仓库内文档 docs/RBAC权限划分.md）</span>
            </span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { healthApi } from '../../infrastructure/api/healthApi'
import { authApi } from '../../infrastructure/api/authApi'
import type { HealthStatus } from '../../domain/model/system'

/** 关于页（INT-745 A07）：平台介绍 + 版本/健康状态 + 文档链接；公开阅读页 */
const year = new Date().getFullYear()

const health = ref<HealthStatus | null>(null)
const authMode = ref('')
const loading = ref(false)
const error = ref('')

type BadgeTone = 'ok' | 'error' | 'muted'

function badgeClass(status?: string): string {
  if (status === 'ok') return 'badge-ok'
  if (status === 'failed' || status === 'error') return 'badge-error'
  return 'badge-muted'
}

function badgeText(status?: string): string {
  if (status === 'ok') return '正常'
  if (status === 'error' || status === 'failed') return '异常'
  return '检测中'
}

async function loadHealth() {
  loading.value = true
  error.value = ''
  try {
    const data = await healthApi.getHealth()
    health.value = data
  } catch (e: any) {
    health.value = null
    error.value = e?.message || '服务状态检测失败'
  } finally {
    loading.value = false
  }
}

async function loadAuthMode() {
  try {
    authMode.value = await authApi.getAuthMode()
  } catch {
    authMode.value = ''
  }
}

onMounted(() => {
  loadHealth()
  loadAuthMode()
})
</script>

<style scoped>
.about-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 32px 20px 48px;
}
.about-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.about-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.about-h1 {
  margin: 0;
  font-size: 26px;
  font-weight: 600;
  color: var(--foreground);
}
.about-lead {
  margin: 0;
  font-size: 14px;
  line-height: 1.8;
  color: var(--muted-foreground);
}
.about-h2 {
  margin: 12px 0 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--foreground);
}
.about-list {
  margin: 0;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 14px;
  line-height: 1.8;
  color: var(--muted-foreground);
}
.about-list a,
.about-lead a {
  color: var(--primary);
  text-decoration: none;
}
.about-list a:hover,
.about-lead a:hover {
  text-decoration: underline;
}
.about-lead code {
  background: var(--muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 1px 5px;
  font-size: 12px;
}
/* 状态卡 */
.about-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px;
}
.about-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.about-card-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
}
.refresh-btn {
  width: 30px;
  height: 30px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--muted-foreground);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.refresh-btn:hover {
  color: var(--primary);
  border-color: var(--primary);
}
.spinning {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.status-rows {
  display: flex;
  flex-direction: column;
}
.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  font-size: 14px;
}
.status-row:last-of-type {
  border-bottom: none;
}
.status-label {
  color: var(--muted-foreground);
}
.status-value {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-mono);
  color: var(--foreground);
}
.status-version {
  font-size: 14px;
}
.status-db {
  font-size: 13px;
}
.status-badge {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-family: var(--font-sans);
}
.badge-ok {
  background: var(--success-light);
  color: var(--success-dark);
}
.badge-error {
  background: var(--destructive-light);
  color: var(--destructive);
}
.badge-muted {
  background: var(--muted);
  color: var(--muted-foreground);
}
.status-note {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--muted-foreground);
}
.status-error {
  margin: 10px 0 0;
  font-size: 13px;
  color: var(--destructive);
}
/* 文档链接 */
.doc-links {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.doc-link {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--background);
  text-decoration: none;
  color: var(--foreground);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.doc-link:hover {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--accent);
}
.doc-link-static {
  cursor: default;
  opacity: 0.85;
}
.doc-link-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: var(--primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  flex-shrink: 0;
}
.doc-link-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.doc-link-title {
  font-size: 14px;
  font-weight: 600;
}
.doc-link-desc {
  font-size: 12px;
  color: var(--muted-foreground);
}
.doc-link-arrow {
  color: var(--muted-foreground);
  font-size: 13px;
}
</style>
