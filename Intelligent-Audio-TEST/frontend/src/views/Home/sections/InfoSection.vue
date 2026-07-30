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
          您可以查看左侧导航栏中的各项功能进行操作。
        </p>
        <div class="help-links">
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            class="help-link"
          >
            <i class="fas fa-external-link-alt"></i>使用帮助文档
          </a>
          <router-link
            v-for="link in helpLinks"
            :key="String(link.to)"
            :to="link.to"
            class="help-link"
          >
            <i :class="link.icon"></i>
            {{ link.text }}
          </router-link>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { systemInfo, helpLinks } from '../homeData'
</script>
