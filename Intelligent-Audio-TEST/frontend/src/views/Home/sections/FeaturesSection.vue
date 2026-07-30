<template>
  <section class="features-section">
    <h2 class="section-title">核心功能</h2>
    <p class="section-subtitle">提供完整的语音测试解决方案</p>
    <div class="features-grid">
      <router-link
        v-for="card in featureCards"
        :key="String(card.to)"
        :to="card.to"
        class="feature-card"
        :class="card.variant"
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
      </router-link>
    </div>
  </section>
</template>

<script setup lang="ts">
import { featureCards } from '../homeData'
</script>
