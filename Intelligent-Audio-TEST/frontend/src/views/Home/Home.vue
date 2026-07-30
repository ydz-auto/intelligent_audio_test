<template>
  <div class="home-page">
    <!-- Hero -->
    <section class="hero-section">
      <div class="hero-content">
        <div class="hero-icon">
          <i class="fas fa-microphone-alt"></i>
        </div>
        <h1 class="hero-title">智能语音测试系统</h1>
        <p class="hero-subtitle">Intelligent Voice Testing System</p>
        <p class="hero-description">
          专业的端到端测试与API测试解决方案，支持多维度语音评估，
          提供完整的测试任务管理、报告分析功能。
        </p>
      </div>
    </section>

    <!-- 快速统计 -->
    <QuickStats :animated-stats="animatedStats" />

    <!-- 开始测试 + 流程 -->
    <WorkflowSection />

    <!-- 详情区块（数据驱动） -->
    <DetailSection
      v-for="(section, idx) in detailSections"
      :key="idx"
      :section="section"
      :show-help-link="true"
    />

    <!-- 核心功能网格 -->
    <FeaturesSection />

    <!-- 系统信息 / 帮助 -->
    <InfoSection />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { statsApi } from '../../utils/api'
import QuickStats from './sections/QuickStats.vue'
import WorkflowSection from './sections/WorkflowSection.vue'
import DetailSection from './sections/DetailSection.vue'
import FeaturesSection from './sections/FeaturesSection.vue'
import InfoSection from './sections/InfoSection.vue'
import { detailSections, type AnimatedStats } from './homeData'

const stats = ref({
  testCases: { total: 0, groups: 0 },
  tasks: { total: 0, completed: 0, running: 0, failed: 0 },
  devices: { online: 0, offline: 0, total: 0 },
  audioFiles: { total: 0, dry: 0, noise: 0, prompt: 0, duration: { total: 0, dry: 0, noise: 0, prompt: 0 } },
  apis: { online: 0, offline: 0, total: 0 },
  dimensions: { total: 0, withEndpoints: 0, endpoints: 0 }
})

const animatedStats = ref<AnimatedStats>({
  testCasesTotal: 0,
  testCasesGroups: 0,
  tasksTotal: 0,
  tasksCompleted: 0,
  devicesOnline: 0,
  devicesOffline: 0,
  audioFilesTotal: 0,
  audioFilesDry: 0,
  audioFilesDuration: 0,
  apisOnline: 0,
  apisTotal: 0,
  dimensionsTotal: 0,
  dimensionsEndpoints: 0
})

function animateNumber(targetValue: number, duration = 1200, onUpdate?: (val: number) => void) {
  const startValue = 0
  const startTime = performance.now()

  function update(currentTime: number) {
    const elapsed = currentTime - startTime
    const progress = Math.min(elapsed / duration, 1)
    const easeOutQuart = 1 - Math.pow(1 - progress, 4)
    const currentValue = Math.round(startValue + (targetValue - startValue) * easeOutQuart)

    if (onUpdate) {
      onUpdate(currentValue)
    }

    if (progress < 1) {
      requestAnimationFrame(update)
    }
  }

  requestAnimationFrame(update)
}

onMounted(async () => {
  try {
    const statsData = await statsApi.getStatsDetails()
    const getCaseInsensitive = (obj: any, key: string) => {
      if (!obj) return undefined
      return obj[key] || obj[key.toLowerCase()] || obj[key.charAt(0).toUpperCase() + key.slice(1).toLowerCase()]
    }
    const newStats = {
      testCases: getCaseInsensitive(statsData, 'testCases') || { total: 0, groups: 0 },
      tasks: statsData.tasks || { total: 0, completed: 0, running: 0, failed: 0 },
      devices: statsData.devices || { online: 0, offline: 0, total: 0 },
      audioFiles: getCaseInsensitive(statsData, 'audioFiles') || { total: 0, dry: 0, noise: 0, prompt: 0, duration: { total: 0, dry: 0, noise: 0, prompt: 0 } },
      apis: statsData.apis || { online: 0, offline: 0, total: 0 },
      dimensions: statsData.dimensions || { total: 0, withendpoints: 0, endpoints: 0 }
    }

    stats.value = newStats

    animateNumber(newStats.testCases.total, 1200, val => animatedStats.value.testCasesTotal = val)
    animateNumber(newStats.testCases.groups || 0, 1200, val => animatedStats.value.testCasesGroups = val)
    animateNumber(newStats.tasks.total, 1200, val => animatedStats.value.tasksTotal = val)
    animateNumber(newStats.tasks.completed || 0, 1200, val => animatedStats.value.tasksCompleted = val)
    animateNumber(newStats.devices.online, 1200, val => animatedStats.value.devicesOnline = val)
    animateNumber(newStats.devices.offline, 1200, val => animatedStats.value.devicesOffline = val)
    animateNumber(newStats.audioFiles.total, 1200, val => animatedStats.value.audioFilesTotal = val)
    animateNumber(newStats.audioFiles.dry || 0, 1200, val => animatedStats.value.audioFilesDry = val)
    animateNumber(newStats.audioFiles.duration?.total || 0, 1200, val => animatedStats.value.audioFilesDuration = val)
    animateNumber(newStats.apis.online, 1200, val => animatedStats.value.apisOnline = val)
    animateNumber(newStats.apis.total, 1200, val => animatedStats.value.apisTotal = val)
    animateNumber(newStats.dimensions.total || 0, 1200, val => animatedStats.value.dimensionsTotal = val)
    animateNumber(newStats.dimensions.endpoints || 0, 1200, val => animatedStats.value.dimensionsEndpoints = val)
  } catch (error) {
    console.error('获取统计数据失败:', error)
  }

  initScrollAnimations()
})

function initScrollAnimations() {
  const observerOptions = {
    root: null,
    rootMargin: '0px',
    threshold: 0.1
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('animate')
      } else {
        entry.target.classList.remove('animate')
      }
    })
  }, observerOptions)

  const sections = document.querySelectorAll('.hero-section, .quick-stats, .workflow-section, .detail-section, .features-section, .info-section')
  sections.forEach(section => {
    section.classList.add('scroll-animate')
    observer.observe(section)
  })

  const cards = document.querySelectorAll('.feature-card, .detail-main-card, .detail-side-card, .stat-card, .test-type-card')
  cards.forEach(card => {
    card.classList.add('scroll-animate')
    observer.observe(card)
  })
}
</script>

<style src="./home.css"></style>
