<template>
  <section class="workflow-section">
    <h2 class="section-title">开始测试</h2>
    <p class="section-subtitle">选择测试类型开始语音测试</p>

    <div class="progress-nav">
      <template v-for="(step, idx) in workflowSteps" :key="idx">
        <div class="progress-step active">
          <div class="progress-step-number" :class="{ active: idx === 1 || idx === 3 }">
            {{ idx + 1 }}
          </div>
          <div class="progress-step-content">
            <div class="progress-step-label">{{ step.label }}</div>
            <div class="progress-step-desc">{{ step.desc }}</div>
          </div>
        </div>
        <div v-if="idx < workflowSteps.length - 1" class="progress-line"></div>
      </template>
    </div>

    <div class="test-type-cards">
      <a
        v-for="card in testTypeCards"
        :key="String(card.to)"
        href="javascript:void(0)"
        class="test-type-card"
        :class="card.variant"
        @click.prevent="handleEntry(card.to, card.title)"
      >
        <div class="test-type-icon">
          <i :class="card.icon"></i>
        </div>
        <div class="test-type-content">
          <h3 class="test-type-title">{{ card.title }}</h3>
          <p class="test-type-description">{{ card.description }}</p>
          <ul class="test-type-list">
            <li v-for="(li, i) in card.list" :key="i">{{ li }}</li>
          </ul>
        </div>
        <div class="test-type-action-btn">
          <span>开始测试</span>
          <i class="fas fa-arrow-right"></i>
        </div>
      </a>
    </div>
  </section>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

import { workflowSteps, testTypeCards } from '../homeData'
import { useLoginRequired } from '../../../composables/shared/useLoginRequired'

// INT-745：「开始测试」等业务入口在未登录+认证开启时弹「需要登录」Dialog（受限项）
const { navigateEntry } = useLoginRequired()

function handleEntry(to: any, title: string) {
  navigateEntry(to, title)
}
</script>
