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
      <router-link
        v-for="card in testTypeCards"
        :key="String(card.to)"
        :to="card.to"
        class="test-type-card"
        :class="card.variant"
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
      </router-link>
    </div>
  </section>
</template>

<script setup lang="ts">
import { workflowSteps, testTypeCards } from '../homeData'
</script>
