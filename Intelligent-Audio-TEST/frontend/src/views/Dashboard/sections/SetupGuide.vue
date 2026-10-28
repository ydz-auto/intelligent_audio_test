<template>
  <section class="dashboard-card setup-guide">
    <!-- 折叠态横条 -->
    <div v-if="!expanded" class="setup-guide-collapsed">
      <div class="collapsed-left">
        <span class="collapsed-icon"><i class="fas fa-check-circle"></i></span>
        <span class="collapsed-title">开始使用</span>
        <span class="collapsed-progress">已完成 {{ completedCount }}/4</span>
        <span class="collapsed-hint">引导已收起，随时可再次展开。</span>
      </div>
      <div class="collapsed-right">
        <button
          v-for="action in collapsedActions"
          :key="action.to"
          type="button"
          class="btn btn-secondary quick-action-btn"
          @click="go(action.to)"
        >
          <i :class="action.icon"></i> {{ action.label }}
        </button>
        <button type="button" class="btn btn-primary" @click="expanded = true">
          <i class="fas fa-chevron-up"></i> 显示引导
        </button>
      </div>
    </div>

    <!-- 展开态 -->
    <div v-else class="setup-guide-expanded">
      <div class="setup-guide__grid">
        <!-- 左列：接口驱动测试卡 -->
        <div class="setup-api-card">
          <div class="setup-api-card__glow"></div>
          <h3 class="setup-api-title">通过 API 驱动测试</h3>
          <p class="setup-api-desc">
            平台能力以 Skill / MCP 形式开放：下载 skill 包、配置服务地址与 Access Token 即可接入 Claude Code、Codex 等外部 agent；Access Token 授权、按 scopes 收权，205 个工具覆盖任务、用例、音频、设备、评估、报告、算法等 13 个业务域，创建任务、查询进度、拉取报告全程可用。
          </p>
          <button
            v-if="can('task:execute')"
            type="button"
            class="btn btn-primary setup-api-cta"
            @click="$router.push('/start-test')"
          >
            <i class="fas fa-play"></i> 开始测试
          </button>
          <details class="setup-api-details">
            <summary>开发者 API 示例 <i class="fas fa-chevron-down"></i></summary>
            <div class="api-example-block">
              <div class="api-example-dots">
                <span></span><span></span><span></span>
              </div>
              <code>curl -X GET {{ apiExampleUrl }}</code>
              <button type="button" class="api-copy-btn" @click="copyApiExample">
                <i class="fas fa-copy"></i> 复制 curl
              </button>
            </div>
          </details>
          <div class="setup-api-signals">
            <div class="signal-row">
              <span class="signal-icon signal-info"><i class="fas fa-headphones"></i></span>
              <span class="signal-label">设备接入</span>
              <span class="signal-value">{{ details?.devices?.online ?? 0 }} 台在线</span>
            </div>
            <div class="signal-row">
              <span class="signal-icon signal-success"><i class="fas fa-list-check"></i></span>
              <span class="signal-label">用例就绪</span>
              <span class="signal-value">{{ details?.testCases?.total ?? 0 }} 条</span>
            </div>
            <div class="signal-row">
              <span class="signal-icon signal-chart"><i class="fas fa-file-alt"></i></span>
              <span class="signal-label">报告产出</span>
              <span class="signal-value">{{ details?.reports ?? 0 }} 份</span>
            </div>
          </div>
        </div>

        <!-- 右列：推荐操作 + 四步完成度 -->
        <div class="setup-guide-right">
          <div class="setup-guide-right__head">
            <span class="card-eyebrow">推荐操作</span>
            <h3 class="setup-guide-right__title">让平台保持就绪</h3>
            <button type="button" class="btn btn-secondary hide-guide-btn" @click="expanded = false">
              <i class="fas fa-chevron-up"></i> 隐藏引导
            </button>
          </div>
          <div class="quick-actions">
            <div
              v-for="action in visibleActions"
              :key="action.to"
              role="button"
              tabindex="0"
              class="quick-action"
              @click="go(action.to)"
              @keydown.enter="go(action.to)"
            >
              <span class="quick-action-icon"><i :class="action.icon"></i></span>
              <span class="quick-action-text">
                <span class="quick-action-title">{{ action.label }}</span>
                <span class="quick-action-desc">{{ action.desc }}</span>
              </span>
            </div>
          </div>
          <div class="setup-steps">
            <div
              v-for="(step, idx) in steps"
              :key="step.key"
              class="setup-step"
              :class="{ 'is-done': stepCompleted(step.key) }"
            >
              <span class="setup-step-icon">
                <i :class="stepCompleted(step.key) ? 'fas fa-check' : 'fas ' + step.icon"></i>
              </span>
              <span class="setup-step-text">
                <span class="setup-step-label">{{ step.label }}</span>
                <span class="setup-step-desc">{{ step.desc }}</span>
              </span>
              <span class="setup-step-index">{{ idx + 1 }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useNotification } from '../../../composables/modal/useNotification'
import { useDashboardPermission } from '../../../composables/dashboard/useDashboardPermission'
import { useSetupGuide } from '../../../composables/dashboard/useSetupGuide'
import type { HomeStatsDetails } from '../../../domain/model/stats'

const props = defineProps<{
  details: HomeStatsDetails | null
}>()

const router = useRouter()
const notification = useNotification()
const { can } = useDashboardPermission()
const { steps, stepCompleted, completedCount, expanded, init } = useSetupGuide(() => props.details)

const apiExampleUrl = `${location.origin}/api/v1/tasks/1/progress`

interface QuickAction {
  to: string
  icon: string
  label: string
  desc: string
  permission: string
}

const QUICK_ACTIONS: QuickAction[] = [
  { to: '/start-test', icon: 'fa-play', label: '开始测试', desc: '选择用例与设备/API，执行语音测试流程', permission: 'task:execute' },
  { to: '/tasks', icon: 'fa-clipboard-list', label: '任务管理', desc: '查看与管理所有测试任务的执行记录', permission: 'task:read' },
  { to: '/TestCaseManager', icon: 'fa-list-check', label: '用例管理', desc: '统一管理测试用例，支持分类、标签与批量操作', permission: 'testcase:read' },
  { to: '/AudioImport', icon: 'fa-music', label: '音频管理', desc: '批量导入测试音频并自动生成用例', permission: 'audio:read' },
  { to: '/Device', icon: 'fa-headphones', label: '设备管理', desc: '管理测试设备与播放设备，监控在线状态', permission: 'device:read' },
  { to: '/history-reports', icon: 'fa-file-bar-chart', label: '报告中心', desc: '集中查看、发布与管理测试报告', permission: 'report:read' },
  { to: '/Evaluation', icon: 'fa-star', label: '评估维度', desc: '配置语音测试的评估维度与指标', permission: 'evaluation:read' },
]

const visibleActions = computed(() => QUICK_ACTIONS.filter(a => can(a.permission)))

/** 折叠态横排入口 = 前四项 */
const collapsedActions = computed(() => visibleActions.value.slice(0, 4))

function go(to: string) {
  router.push(to)
}

async function copyApiExample() {
  try {
    await navigator.clipboard.writeText(`curl ${apiExampleUrl}`)
    notification.success('已复制')
  } catch {
    notification.error('复制失败')
  }
}

onMounted(() => {
  init()
})
</script>
