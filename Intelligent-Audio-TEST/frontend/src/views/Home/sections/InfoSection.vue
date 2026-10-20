<template>
  <section class="info-section">
    <div class="info-card">
      <div class="info-header">
        <i class="fas fa-info-circle"></i>
        <h3>系统信息</h3>
      </div>
      <div class="info-content">
        <div v-for="row in systemInfo" :key="row.label" class="info-row">
          <span class="info-label">{{ row.label }}</span>
          <span class="info-value">{{ row.value }}</span>
        </div>
      </div>
    </div>

    <div class="info-card">
      <div class="info-header">
        <i class="fas fa-book"></i>
        <h3>使用帮助</h3>
      </div>
      <div class="info-content">
        <p class="help-text">
          首次使用请先配置评估维度和播放设备，然后导入测试音频。
          登录后可使用上方导航进入平台各功能模块。
        </p>
        <div class="help-links">
          <router-link
            to="/user-guide"
            class="help-link"
          >
            <i class="fas fa-book"></i>使用手册
          </router-link>
          <a
            v-for="link in helpLinks"
            :key="String(link.to)"
            href="javascript:void(0)"
            class="help-link"
            @click.prevent="handleEntry(link.to, link.text)"
          >
            <i :class="link.icon"></i>
            {{ link.text }}
          </a>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/card.css'
import '../../../assets/styles/components/form.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

import { systemInfo, helpLinks } from '../homeData'
import { useLoginRequired } from '../../../composables/shared/useLoginRequired'

// INT-745：「使用帮助文档」外链占位（https://github.com）废除，改链站内 /user-guide；
// 配置设备/维度/音频等业务入口在未登录+认证开启时弹「需要登录」Dialog（受限项）
const { navigateEntry } = useLoginRequired()

function handleEntry(to: any, text: string) {
  navigateEntry(to, text)
}
</script>
