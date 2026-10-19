<template>
  <section class="features-section">
    <h2 class="section-title">核心功能</h2>
    <p class="section-subtitle">提供完整的语音测试解决方案</p>
    <div class="features-grid">
      <a
        v-for="card in featureCards"
        :key="String(card.to)"
        href="javascript:void(0)"
        class="feature-card"
        :class="card.variant"
        @click.prevent="handleEntry(card.to, card.title)"
      >
        <div class="feature-icon">
          <i :class="card.icon"></i>
        </div>
        <h3 class="feature-title">{{ card.title }}</h3>
        <p class="feature-description">{{ card.description }}</p>
        <ul class="feature-list">
          <li v-for="(li, i) in card.list" :key="i">{{ li }}</li>
        </ul>
        <span class="feature-link">
          {{ card.link }} <i class="fas fa-arrow-right"></i>
        </span>
      </a>
    </div>
  </section>
</template>

<script setup lang="ts">
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/layouts/main.css'

import { featureCards } from '../homeData'
import { useLoginRequired } from '../../../composables/shared/useLoginRequired'

// INT-745：功能入口卡在未登录+认证开启时弹「需要登录」Dialog（受限项）
const { navigateEntry } = useLoginRequired()

function handleEntry(to: any, title: string) {
  navigateEntry(to, title)
}
</script>
