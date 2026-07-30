<template>
  <section class="quick-stats">
    <router-link
      v-for="(item, idx) in statCards"
      :key="String(item.to)"
      :to="item.to"
      class="stat-card"
    >
      <div class="stat-icon">
        <i :class="item.icon"></i>
      </div>
      <div class="stat-content">
        <h3 class="stat-number">{{ animatedStats[item.numberKey] }}</h3>
        <p class="stat-label">{{ item.label }}</p>
        <p class="stat-sub">{{ item.subLabel(animatedStats[item.subKey]) }}</p>
      </div>
    </router-link>
  </section>
</template>

<script setup lang="ts">
import { statCards, type AnimatedStats } from '../homeData'

defineProps<{
  animatedStats: AnimatedStats
}>()
</script>
