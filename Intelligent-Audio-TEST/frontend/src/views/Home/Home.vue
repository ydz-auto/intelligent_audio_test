<template>
  <div class="home-page" ref="homePageRef">
    <!-- Hero -->
    <section class="hero-section">
      <div class="hero-content">
        <div class="hero-icon">
          <i class="fas fa-microphone-alt"></i>
        </div>
        <h1 class="hero-title">智能语音测试系统</h1>
        <p class="hero-subtitle">Intelligent Voice Testing System</p>
        <p class="hero-description">
          一站式语音测试与评估解决方案，支持多维度语音评估，
          提供完整的测试任务管理、报告分析功能。
        </p>
      </div>
    </section>

    <!-- INT-745：业务统计已移交工作台 /dashboard（02_工作台卡），公共门户不再展示 -->

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
import WorkflowSection from './sections/WorkflowSection.vue'
import DetailSection from './sections/DetailSection.vue'
import FeaturesSection from './sections/FeaturesSection.vue'
import InfoSection from './sections/InfoSection.vue'
import { detailSections } from './homeData'

const homePageRef = ref<HTMLElement | null>(null)

onMounted(() => {
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

  // INT-279：.scroll-animate 动画只在 Home 根作用域内初始化，避免给其他页面同名元素挂类
  const root = homePageRef.value
  if (!root) return

  const sections = root.querySelectorAll('.hero-section, .workflow-section, .detail-section, .features-section, .info-section')
  sections.forEach(section => {
    section.classList.add('scroll-animate')
    observer.observe(section)
  })

  const cards = root.querySelectorAll('.feature-card, .detail-main-card, .detail-side-card, .stat-card, .test-type-card')
  cards.forEach(card => {
    card.classList.add('scroll-animate')
    observer.observe(card)
  })
}
</script>

<style src="./home.css"></style>
