<template>
  <section class="detail-section" :class="{ 'alt-bg': section.altBg }">
    <h2 class="section-title">{{ section.title }}</h2>
    <p class="section-subtitle">{{ section.subtitle }}</p>

    <div class="detail-cards" :class="{ reverse: section.reverse }">
      <div class="detail-main-card">
        <div class="detail-icon-large" :class="section.variant">
          <i :class="section.iconLarge"></i>
        </div>
        <h3 class="detail-title">{{ section.mainTitle }}</h3>
        <p class="detail-description">{{ section.mainDescription }}</p>
        <div class="detail-features">
          <div
            v-for="(feat, i) in section.features"
            :key="i"
            class="detail-feature"
          >
            <i :class="feat.icon"></i>
            <span>{{ feat.text }}</span>
          </div>
        </div>
      </div>

      <div class="detail-side-cards">
        <div
          v-for="(card, i) in section.sideCards"
          :key="i"
          class="detail-side-card"
        >
          <div class="detail-side-icon" :class="section.variant">
            <i :class="card.icon"></i>
          </div>
          <h4>{{ card.title }}</h4>
          <p>{{ card.desc }}</p>
        </div>
      </div>
    </div>

    <div class="detail-cta-section">
      <a href="javascript:void(0)" class="detail-cta-btn" :class="`cta-${section.ctaVariant}`" @click.prevent="handleEntry(section.ctaTo, section.title)">
        <span>{{ section.ctaText }}</span>
        <i class="fas fa-arrow-right"></i>
      </a>
      <router-link to="/user-guide" class="detail-help-link-inline" v-if="showHelpLink">
        <i class="fas fa-book"></i>
        <span>使用文档</span>
      </router-link>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { DetailSection } from '../homeData'
import { useLoginRequired } from '../../../composables/shared/useLoginRequired'

defineProps<{
  section: DetailSection
  showHelpLink?: boolean
}>()

// INT-745：详情区业务入口在未登录+认证开启时弹「需要登录」Dialog（受限项）
const { navigateEntry } = useLoginRequired()

function handleEntry(to: any, title: string) {
  navigateEntry(to, title)
}
</script>
